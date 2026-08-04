$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Backend = Start-Process python `
    -ArgumentList "-m", "uvicorn", "backend.api.app:app", "--port", "8000" `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -PassThru

try {
    Set-Location (Join-Path $ProjectRoot "apps\web")
    npm run dev
}
finally {
    if (-not $Backend.HasExited) {
        Stop-Process -Id $Backend.Id
    }
}
