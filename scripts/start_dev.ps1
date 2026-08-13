param(
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "apps\web"
$ViteScript = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
$BackendPort = 8000
$FrontendPort = 5173
$Backend = $null
$Frontend = $null
$PreviousBackendUrl = $env:GFM_BACKEND_URL

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

function Find-AvailablePort(
    [int]$PreferredPort,
    [int]$MaximumAttempts = 100
) {
    for ($Offset = 0; $Offset -lt $MaximumAttempts; $Offset++) {
        $Candidate = $PreferredPort + $Offset
        $Listener = Get-NetTCPConnection -LocalPort $Candidate -State Listen -ErrorAction SilentlyContinue
        if ($null -eq $Listener) {
            return $Candidate
        }
    }
    throw "No available local port was found from $PreferredPort to $($PreferredPort + $MaximumAttempts - 1)."
}

function Wait-Http(
    [string]$Url,
    [System.Diagnostics.Process]$Process,
    [int]$Attempts = 40
) {
    for ($Index = 0; $Index -lt $Attempts; $Index++) {
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "The process for $Url exited early with code $($Process.ExitCode)."
        }
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

function Assert-OwnsListener([int]$Port, [System.Diagnostics.Process]$Process) {
    $Owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($Owners.Count -ne 1 -or $Owners[0] -ne $Process.Id) {
        throw "The service on port $Port is not owned by the process started in this run."
    }
}

function Stop-OwnedProcess([System.Diagnostics.Process]$Process) {
    if ($null -ne $Process) {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -ErrorAction SilentlyContinue
            $Process.WaitForExit(3000) | Out-Null
            $Process.Refresh()
            if (-not $Process.HasExited) {
                Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
            }
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
    $BackendPort = Find-AvailablePort $BackendPort
    $FrontendPort = Find-AvailablePort $FrontendPort
    if ($BackendPort -ne 8000) {
        Write-Step "Port 8000 is in use; using analysis API port $BackendPort instead."
    }
    if ($FrontendPort -ne 5173) {
        Write-Step "Port 5173 is in use; using web interface port $FrontendPort instead."
    }

    $BackendProbeExitCode = Invoke-NativeCommand python @(
        "-c", "import fastapi, uvicorn, pydantic, numpy, scipy"
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
        -ArgumentList "-m", "uvicorn", "backend.api.app:app", "--host", "127.0.0.1", "--port", "$BackendPort" `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -PassThru

    if (-not (Test-Path $ViteScript)) {
        throw "Vite executable was not found after dependency installation."
    }
    $env:GFM_BACKEND_URL = "http://127.0.0.1:$BackendPort"
    Write-Step "Starting web interface..."
    $Frontend = Start-Process node `
        -ArgumentList $ViteScript, "--host", "127.0.0.1", "--port", "$FrontendPort", "--strictPort" `
        -WorkingDirectory $FrontendRoot `
        -WindowStyle Hidden `
        -PassThru

    if (-not (Wait-Http "http://127.0.0.1:$BackendPort/api/health" $Backend)) {
        throw "The analysis API did not become ready in time."
    }
    if (-not (Wait-Http "http://127.0.0.1:$FrontendPort" $Frontend)) {
        throw "The web interface did not become ready in time."
    }
    Assert-OwnsListener $BackendPort $Backend
    Assert-OwnsListener $FrontendPort $Frontend

    Write-Host ""
    $PlatformUrl = "http://127.0.0.1:$FrontendPort"
    Write-Host "Platform ready: $PlatformUrl" -ForegroundColor Green
    if ($SmokeTest) {
        Write-Host "FULLSTACK_LAUNCHER_SMOKE_OK" -ForegroundColor Green
    }
    else {
        Start-Process $PlatformUrl
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
    Stop-OwnedProcess $Frontend
    Stop-OwnedProcess $Backend
    if ($null -eq $PreviousBackendUrl) {
        Remove-Item Env:GFM_BACKEND_URL -ErrorAction SilentlyContinue
    }
    else {
        $env:GFM_BACKEND_URL = $PreviousBackendUrl
    }
}
