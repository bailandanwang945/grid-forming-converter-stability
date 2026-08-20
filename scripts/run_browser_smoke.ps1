$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Backend = $null
$Frontend = $null
$BackendPort = 8000
$FrontendPort = 5173

function Assert-PortAvailable([int]$Port) {
    $Listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($null -ne $Listener) {
        throw "Port $Port is already occupied; browser smoke will not reuse or stop an existing service."
    }
}

function Find-AvailablePort([int]$PreferredPort, [int]$SearchCount = 40) {
    for ($Offset = 0; $Offset -lt $SearchCount; $Offset++) {
        $Candidate = $PreferredPort + $Offset
        $Listener = Get-NetTCPConnection -LocalPort $Candidate -State Listen -ErrorAction SilentlyContinue
        if ($null -eq $Listener) { return $Candidate }
    }
    throw "No available port was found from $PreferredPort through $($PreferredPort + $SearchCount - 1)."
}

function Wait-Http([string]$Url, [System.Diagnostics.Process]$Process) {
    for ($Index = 0; $Index -lt 40; $Index++) {
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "The process for $Url exited early with code $($Process.ExitCode)."
        }
        try {
            $Response = Invoke-WebRequest $Url -UseBasicParsing -TimeoutSec 1
            if ($Response.StatusCode -eq 200) { return $true }
        }
        catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

function Assert-OwnsListener([int]$Port, [System.Diagnostics.Process]$Process) {
    $Owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($Owners.Count -ne 1 -or $Owners[0] -ne $Process.Id) {
        throw "The listener on port $Port is not owned by this smoke-test run."
    }
}

function Stop-OwnedProcess([System.Diagnostics.Process]$Process) {
    if ($null -ne $Process) {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

try {
    $BackendPort = Find-AvailablePort $BackendPort
    $FrontendPort = Find-AvailablePort $FrontendPort
    Assert-PortAvailable $BackendPort
    Assert-PortAvailable $FrontendPort
    $Backend = Start-Process python `
        -ArgumentList "-m", "uvicorn", "backend.api.app:app", "--host", "127.0.0.1", "--port", "$BackendPort" `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
    $ViteScript = Join-Path $ProjectRoot "apps\web\node_modules\vite\bin\vite.js"
    $env:GFM_BACKEND_URL = "http://127.0.0.1:$BackendPort"
    $Frontend = Start-Process node `
        -ArgumentList $ViteScript, "--host", "127.0.0.1", "--port", "$FrontendPort", "--strictPort" `
        -WorkingDirectory (Join-Path $ProjectRoot "apps\web") -WindowStyle Hidden -PassThru

    if (-not (Wait-Http "http://127.0.0.1:$BackendPort/api/health" $Backend)) { throw "Analysis API did not become ready." }
    if (-not (Wait-Http "http://127.0.0.1:$FrontendPort" $Frontend)) { throw "Web interface did not become ready." }
    Assert-OwnsListener $BackendPort $Backend
    Assert-OwnsListener $FrontendPort $Frontend

    $env:GFM_BASE_URL = "http://127.0.0.1:$FrontendPort"
    & node (Join-Path $ProjectRoot "scripts\browser_smoke.mjs")
    if ($LASTEXITCODE -ne 0) { throw "Browser end-to-end smoke test failed." }
}
finally {
    Stop-OwnedProcess $Frontend
    Stop-OwnedProcess $Backend
}
