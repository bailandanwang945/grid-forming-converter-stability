param(
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot "apps\web"
$Backend = $null
$Frontend = $null

function Write-Step([string]$Message) {
    Write-Host "[GFM] $Message" -ForegroundColor Cyan
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

try {
    Write-Step "Checking runtime dependencies..."
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python was not found. Install Python 3.10 or newer."
    }
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js/npm was not found. Install Node.js 20 or newer."
    }

    python -c "import fastapi, uvicorn, pydantic" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Installing backend dependencies..."
        python -m pip install -r (Join-Path $ProjectRoot "backend\requirements.txt")
        if ($LASTEXITCODE -ne 0) {
            throw "Backend dependency installation failed."
        }
    }

    if (-not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
        Write-Step "Installing frontend dependencies..."
        Push-Location $FrontendRoot
        try {
            npm install
            if ($LASTEXITCODE -ne 0) {
                throw "Frontend dependency installation failed."
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

    $ViteScript = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
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
