param(
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "apps\web"
$ViteScript = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
$Backend = $null
$Frontend = $null

function Write-Step([string]$Message) {
    Write-Host "[GFM] $Message" -ForegroundColor Cyan
}

function Invoke-NativeCommand(
    [string]$FilePath,
    [string[]]$Arguments,
    [switch]$Quiet
) {
    # Windows PowerShell 5.1 can promote native stderr to an ErrorRecord when
    # ErrorActionPreference is Stop. Dependency probes intentionally use a
    # non-zero exit code, so inspect LASTEXITCODE instead of catching stderr.
    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        if ($Quiet) {
            & $FilePath @Arguments 2>$null | Out-Null
        }
        else {
            & $FilePath @Arguments 2>&1 | Out-Host
        }
        return [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }
}

function Wait-Http([string]$Url, [int]$Attempts = 40) {
    for ($Index = 0; $Index -lt $Attempts; $Index++) {
        try {
            $Response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 2
            if ($Response.StatusCode -eq 200) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    return $false
}

function Stop-ProjectListener([int]$Port, [string]$ExpectedCommandFragment) {
    $Connections = Get-NetTCPConnection `
        -LocalPort $Port `
        -State Listen `
        -ErrorAction SilentlyContinue
    foreach ($Connection in @($Connections)) {
        $ServiceProcess = Get-CimInstance `
            -ClassName Win32_Process `
            -Filter "ProcessId=$($Connection.OwningProcess)" `
            -ErrorAction SilentlyContinue
        if (
            $null -ne $ServiceProcess -and
            $ServiceProcess.CommandLine -like "*$ExpectedCommandFragment*"
        ) {
            Stop-Process -Id $Connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    Write-Step "Checking runtime dependencies..."
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python was not found. Install Python 3.10 or newer."
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js/npm was not found. Install Node.js 20 or newer."
    }

    $BackendProbeExitCode = Invoke-NativeCommand python @(
        "-c", "import fastapi, uvicorn, pydantic"
    ) -Quiet
    if ($BackendProbeExitCode -ne 0) {
        Write-Step "Installing backend dependencies..."
        $RequirementsPath = Join-Path $ProjectRoot "backend\requirements.txt"
        $PipExitCode = Invoke-NativeCommand python @(
            "-m", "pip", "install", "-r", $RequirementsPath
        )
        if ($PipExitCode -ne 0) {
            throw "Backend dependency installation failed (exit code $PipExitCode)."
        }
    }

    if (-not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
        Write-Step "Installing frontend dependencies..."
        Push-Location $FrontendRoot
        try {
            $NpmExitCode = Invoke-NativeCommand npm.cmd @("install")
            if ($NpmExitCode -ne 0) {
                throw "Frontend dependency installation failed (exit code $NpmExitCode)."
            }
        }
        finally {
            Pop-Location
        }
    }

    Write-Step "Starting analysis API..."
    $Backend = Start-Process python `
        -ArgumentList "-m", "uvicorn", "backend.api.app:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru

    if (-not (Test-Path $ViteScript)) {
        throw "Vite executable was not found after dependency installation."
    }
    Write-Step "Starting web interface..."
    $Frontend = Start-Process node `
        -ArgumentList $ViteScript, "--host", "127.0.0.1" `
        -WorkingDirectory $FrontendRoot `
        -WindowStyle Hidden `
        -PassThru

    if (-not (Wait-Http "http://127.0.0.1:8000/api/health")) {
        throw "The analysis API did not become ready in time."
    }
    if (-not (Wait-Http "http://127.0.0.1:5173")) {
        throw "The web interface did not become ready in time."
    }

    Write-Host ""
    Write-Host "Platform ready: http://127.0.0.1:5173" -ForegroundColor Green
    if ($SmokeTest) {
        Write-Host "FULLSTACK_LAUNCHER_SMOKE_OK" -ForegroundColor Green
    }
    else {
        Start-Process "http://127.0.0.1:5173"
        Write-Host "The browser is open. Keep this window open; press Enter to stop the platform."
        Read-Host | Out-Null
    }
}
catch {
    Write-Host ""
    Write-Host "Startup failed: $($_.Exception.Message)" -ForegroundColor Red
    if (-not $SmokeTest) {
        Write-Host "Press Enter to close this window."
        Read-Host | Out-Null
    }
    exit 1
}
finally {
    Write-Step "Stopping services..."
    # Some Python/Node launchers detach from the Start-Process wrapper. Stop
    # only listeners whose command lines match this project, never unrelated
    # services that happen to use Python or Node.
    Stop-ProjectListener 5173 $ViteScript
    Stop-ProjectListener 8000 "backend.api.app:app"
    foreach ($Process in @($Frontend, $Backend)) {
        if ($null -ne $Process -and -not $Process.HasExited) {
            Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue
            $Process.WaitForExit(3000) | Out-Null
            if (-not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            }
        }
    }
}
