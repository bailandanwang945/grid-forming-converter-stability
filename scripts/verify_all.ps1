param(
    [switch]$NoBootstrap,
    [switch]$SkipMatlab
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "apps\web"
$BackendDevRequirements = Join-Path $ProjectRoot "backend\requirements-dev.txt"
$LauncherPath = Join-Path $ProjectRoot "scripts\start_dev.ps1"
$script:Results = New-Object System.Collections.Generic.List[object]
$script:HasFailure = $false

function Write-Step([string]$Message) {
    Write-Host "[GFM Verify] $Message" -ForegroundColor Cyan
}

function Add-Result(
    [string]$Stage,
    [string]$Status,
    [double]$Seconds,
    [string]$Detail
) {
    $script:Results.Add([pscustomobject]@{
        Stage = $Stage
        Status = $Status
        Seconds = [Math]::Round($Seconds, 2)
        Detail = $Detail
    })
}

function Invoke-NativeCommand(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory,
    [switch]$Quiet
) {
    $PreviousPreference = $ErrorActionPreference
    Push-Location $WorkingDirectory
    try {
        # Windows PowerShell 5.1 may turn native stderr into ErrorRecord when
        # ErrorActionPreference is Stop. Exit codes are the acceptance source.
        $ErrorActionPreference = "Continue"
        if ($Quiet) {
            & $FilePath @Arguments 2>$null | Out-Null
        }
        else {
            # Do not merge stderr into the PowerShell pipeline: unittest and
            # npm use stderr for ordinary progress/warnings, which Windows
            # PowerShell 5.1 otherwise renders as misleading ErrorRecords.
            & $FilePath @Arguments | Out-Host
        }
        return [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
        Pop-Location
    }
}

function Assert-NativeSuccess(
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory
) {
    $ExitCode = Invoke-NativeCommand $FilePath $Arguments $WorkingDirectory
    if ($ExitCode -ne 0) {
        throw "Command failed with exit code ${ExitCode}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-Stage([string]$Name, [scriptblock]$Action) {
    Write-Step "Starting: $Name"
    $Timer = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        & $Action
        $Timer.Stop()
        Add-Result $Name "PASS" $Timer.Elapsed.TotalSeconds "completed"
        Write-Host "[GFM Verify] PASS: $Name" -ForegroundColor Green
    }
    catch {
        $Timer.Stop()
        $script:HasFailure = $true
        $Message = $_.Exception.Message
        Add-Result $Name "FAIL" $Timer.Elapsed.TotalSeconds $Message
        Write-Host "[GFM Verify] FAIL: $Name - $Message" -ForegroundColor Red
    }
}

function Add-SkippedStage([string]$Name, [string]$Reason) {
    Add-Result $Name "SKIP" 0 $Reason
    Write-Host "[GFM Verify] SKIP: $Name - $Reason" -ForegroundColor Yellow
}

function Resolve-MatlabExecutable {
    $Command = Get-Command matlab -ErrorAction SilentlyContinue
    if ($null -ne $Command) {
        return $Command.Source
    }

    if (-not [string]::IsNullOrWhiteSpace($env:MATLAB_ROOT)) {
        $Candidate = Join-Path $env:MATLAB_ROOT "bin\matlab.exe"
        if (Test-Path -LiteralPath $Candidate) {
            return $Candidate
        }
    }

    $DefaultRoot = "C:\Program Files\MATLAB"
    if (Test-Path -LiteralPath $DefaultRoot) {
        $Installations = Get-ChildItem -LiteralPath $DefaultRoot -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending
        foreach ($Installation in $Installations) {
            $Candidate = Join-Path $Installation.FullName "bin\matlab.exe"
            if (Test-Path -LiteralPath $Candidate) {
                return $Candidate
            }
        }
    }

    return $null
}

Invoke-Stage "Python unittest" {
    $Python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $Python) {
        throw "Python was not found. Install Python 3.10 or newer."
    }

    $ProbeCode = "import fastapi, uvicorn, pydantic, numpy, scipy, httpx"
    $ProbeExitCode = Invoke-NativeCommand $Python.Source @("-c", $ProbeCode) $ProjectRoot -Quiet
    if ($ProbeExitCode -ne 0) {
        if ($NoBootstrap) {
            throw "Python test dependencies are missing and -NoBootstrap was requested."
        }
        if (-not (Test-Path -LiteralPath $BackendDevRequirements)) {
            throw "Backend development requirements were not found: $BackendDevRequirements"
        }
        Write-Step "Installing Python test dependencies..."
        Assert-NativeSuccess $Python.Source @(
            "-m", "pip", "install", "-r", $BackendDevRequirements
        ) $ProjectRoot
    }

    Assert-NativeSuccess $Python.Source @(
        "-m", "unittest", "discover",
        "-s", "backend/tests",
        "-p", "test_*.py",
        "-v"
    ) $ProjectRoot
}

Invoke-Stage "Frontend production build" {
    $Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($null -eq $Npm) {
        throw "Node.js/npm was not found. Install Node.js 20 or newer."
    }

    $ViteScript = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
    if (-not (Test-Path -LiteralPath $ViteScript)) {
        if ($NoBootstrap) {
            throw "Frontend dependencies are missing and -NoBootstrap was requested."
        }
        Write-Step "Installing pinned frontend dependencies with npm ci..."
        Assert-NativeSuccess $Npm.Source @("ci") $FrontendRoot
    }

    Assert-NativeSuccess $Npm.Source @("run", "build") $FrontendRoot
}

Invoke-Stage "Launcher smoke test" {
    $WindowsPowerShell = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if ($null -eq $WindowsPowerShell) {
        throw "Windows PowerShell was not found."
    }
    if (-not (Test-Path -LiteralPath $LauncherPath)) {
        throw "Launcher script was not found: $LauncherPath"
    }

    Assert-NativeSuccess $WindowsPowerShell.Source @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $LauncherPath,
        "-SmokeTest"
    ) $ProjectRoot
}

Invoke-Stage "Browser end-to-end smoke" {
    $BrowserPowerShell = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if ($null -eq $BrowserPowerShell) {
        throw "Windows PowerShell was not found."
    }
    $BrowserSmoke = Join-Path $ProjectRoot "scripts\run_browser_smoke.ps1"
    if (-not (Test-Path -LiteralPath $BrowserSmoke)) {
        throw "Browser smoke script was not found: $BrowserSmoke"
    }
    $PlaywrightCore = Join-Path $FrontendRoot "node_modules\playwright-core\index.mjs"
    if (-not (Test-Path -LiteralPath $PlaywrightCore)) {
        throw "playwright-core is missing; run npm ci in apps/web."
    }
    Assert-NativeSuccess $BrowserPowerShell.Source @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $BrowserSmoke
    ) $ProjectRoot
}

$MatlabStage = "MATLAB unit tests"
if ($SkipMatlab) {
    Add-SkippedStage $MatlabStage "explicitly skipped with -SkipMatlab"
}
else {
    $Matlab = Resolve-MatlabExecutable
    if ([string]::IsNullOrWhiteSpace($Matlab)) {
        Add-SkippedStage $MatlabStage "MATLAB not found on PATH, MATLAB_ROOT, or the default installation path"
    }
    else {
        Invoke-Stage $MatlabStage {
            $MatlabRoot = $ProjectRoot.Replace("\", "/").Replace("'", "''")
            $BatchCommand = "cd('$MatlabRoot'); run('experiments/run_unit_tests.m');"
            Assert-NativeSuccess $Matlab @("-batch", $BatchCommand) $ProjectRoot
        }
    }
}

Write-Host ""
Write-Host "[GFM Verify] Acceptance summary" -ForegroundColor Cyan
$script:Results | Format-Table Stage, Status, Seconds, Detail -AutoSize | Out-Host

$PassCount = @($script:Results | Where-Object Status -eq "PASS").Count
$FailCount = @($script:Results | Where-Object Status -eq "FAIL").Count
$SkipCount = @($script:Results | Where-Object Status -eq "SKIP").Count
Write-Host "[GFM Verify] PASS=$PassCount FAIL=$FailCount SKIP=$SkipCount"

if ($script:HasFailure) {
    Write-Host "VERIFY_ALL_FAILED" -ForegroundColor Red
    exit 1
}
if ($SkipCount -gt 0) {
    Write-Host "VERIFY_ALL_OK_WITH_SKIPS" -ForegroundColor Yellow
}
else {
    Write-Host "VERIFY_ALL_OK" -ForegroundColor Green
}
exit 0
