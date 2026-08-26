param(
    [string]$Version = "0.4.0-rc2",
    [switch]$SkipSmokeTest,
    [switch]$AllowDirtyWorktree
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ReleaseRoot = Join-Path $ProjectRoot "output\release"
$BuildRoot = Join-Path $ReleaseRoot "_pyinstaller_build"
$DistRoot = Join-Path $ReleaseRoot "_pyinstaller_dist"
$FrontendSnapshot = Join-Path $ReleaseRoot "_frontend_snapshot"
$FrontendRoot = Join-Path $ProjectRoot "apps\web"
$FrontendDist = Join-Path $FrontendRoot "dist"
$MetadataPath = Join-Path $ReleaseRoot "build_info.json"
$PackagedSmokeEvidence = Join-Path $ReleaseRoot "_packaged_smoke_evidence.json"
$SpecPath = Join-Path $ProjectRoot "packaging\gfm_windows.spec"
$PackageName = "GFM-Stability-Platform-$Version-windows-x64"
$PackagePath = Join-Path $ReleaseRoot $PackageName
$ZipPath = "$PackagePath.zip"

function Write-Step([string]$Message) {
    Write-Host "[GFM Release] $Message" -ForegroundColor Cyan
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments) {
    $PreviousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 promotes native stderr (including harmless
        # Vite/PyInstaller warnings) to ErrorRecord when the global preference
        # is Stop. The process exit code is the authoritative result here.
        $ErrorActionPreference = "Continue"
        & $FilePath @Arguments 2>&1 | Out-Host
        $ExitCode = [int]$LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousPreference
    }
    if ($ExitCode -ne 0) {
        throw "$FilePath failed with exit code $ExitCode."
    }
}

function Assert-InReleaseRoot([string]$Path) {
    $ResolvedRelease = [IO.Path]::GetFullPath($ReleaseRoot).TrimEnd('\') + '\'
    $ResolvedTarget = [IO.Path]::GetFullPath($Path)
    if (-not $ResolvedTarget.StartsWith($ResolvedRelease, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside output\release: $ResolvedTarget"
    }
}

if ($Version -notmatch '^[0-9A-Za-z][0-9A-Za-z._-]{0,63}$') {
    throw "Version contains unsupported filename characters: $Version"
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is required only on the build machine."
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Node.js/npm is required only on the build machine."
}

$Commit = (& git -C $ProjectRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read the Git commit."
}
$Dirty = -not [string]::IsNullOrWhiteSpace((& git -C $ProjectRoot status --porcelain))
if ($Dirty -and -not $AllowDirtyWorktree) {
    throw "The Git worktree is dirty. Commit the intended release scope, or use -AllowDirtyWorktree only for a non-release development candidate."
}

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
foreach ($Path in @($BuildRoot, $DistRoot, $FrontendSnapshot, $PackagedSmokeEvidence, $PackagePath, $ZipPath)) {
    Assert-InReleaseRoot $Path
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

Write-Step "Building the production web interface..."
Push-Location $FrontendRoot
try {
    if (-not (Test-Path (Join-Path $FrontendRoot "node_modules"))) {
        Invoke-Native npm.cmd @("ci")
    }
    Invoke-Native npm.cmd @("run", "build")
}
finally {
    Pop-Location
}
if (-not (Test-Path (Join-Path $FrontendDist "index.html"))) {
    throw "Frontend build output is missing: $FrontendDist\index.html"
}
Write-Step "Freezing the frontend build for reproducible collection..."
Copy-Item -LiteralPath $FrontendDist -Destination $FrontendSnapshot -Recurse
if (-not (Test-Path (Join-Path $FrontendSnapshot "index.html"))) {
    throw "Unable to create the frontend release snapshot."
}

$BuildTime = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$BuildInfo = [ordered]@{
    product = "GFM Stability Analysis Platform"
    version = $Version
    commit = $Commit
    workingTreeDirty = $Dirty
    builtAtUtc = $BuildTime
    platform = "windows-x64"
    runtime = "self-contained-pyinstaller-onedir"
}
$BuildInfo | ConvertTo-Json | Set-Content -LiteralPath $MetadataPath -Encoding UTF8

$PyInstallerProbe = & python -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Step "Installing PyInstaller on the build machine..."
    Invoke-Native python @("-m", "pip", "install", "PyInstaller>=6.11,<7")
}

Write-Step "Creating the self-contained Windows package..."
$env:GFM_BUILD_INFO = $MetadataPath
$env:GFM_FRONTEND_DIST = $FrontendSnapshot
try {
    Invoke-Native python @(
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--workpath", $BuildRoot,
        "--distpath", $DistRoot,
        $SpecPath
    )
}
finally {
    Remove-Item Env:GFM_BUILD_INFO -ErrorAction SilentlyContinue
    Remove-Item Env:GFM_FRONTEND_DIST -ErrorAction SilentlyContinue
}

$BuiltApp = Join-Path $DistRoot "GFM-Stability-Platform"
if (-not (Test-Path (Join-Path $BuiltApp "GFM-Stability-Platform.exe"))) {
    throw "PyInstaller did not produce the expected executable."
}
Copy-Item -LiteralPath $BuiltApp -Destination $PackagePath -Recurse
Copy-Item -LiteralPath (Join-Path $ProjectRoot "packaging\WINDOWS_RELEASE_README.txt") `
    -Destination (Join-Path $PackagePath "README.txt")
Copy-Item -LiteralPath (Join-Path $ProjectRoot "packaging\VERIFY_THIS_PC.cmd") `
    -Destination (Join-Path $PackagePath "VERIFY_THIS_PC.cmd")
Copy-Item -LiteralPath (Join-Path $ProjectRoot "packaging\verify_this_pc.ps1") `
    -Destination (Join-Path $PackagePath "verify_this_pc.ps1")

Write-Step "Generating third-party notices from the packaged executable..."
$ThirdPartyGenerator = Join-Path $ProjectRoot "scripts\generate_third_party_notices.py"
$AuthorLicense = Join-Path $ProjectRoot "external\cifelli-small-gain-phase\LICENSE"
$SiennaLicense = Join-Path $ProjectRoot "packaging\research-licenses\PowerSimulationsDynamics-v0.16.2-LICENSE.txt"
$PythonControlLicense = Join-Path $ProjectRoot "packaging\research-licenses\python-control-0.10.2-LICENSE.txt"
Invoke-Native python @(
    $ThirdPartyGenerator,
    "--executable", (Join-Path $PackagePath "GFM-Stability-Platform.exe"),
    "--frontend-root", $FrontendRoot,
    "--author-license", $AuthorLicense,
    "--sienna-license", $SiennaLicense,
    "--python-control-license", $PythonControlLicense,
    "--output-root", $PackagePath
)
$SbomPath = Join-Path $PackagePath "third-party-sbom.json"
$NoticesPath = Join-Path $PackagePath "THIRD_PARTY_NOTICES.md"
if (-not (Test-Path -LiteralPath $SbomPath -PathType Leaf) -or -not (Test-Path -LiteralPath $NoticesPath -PathType Leaf)) {
    throw "Third-party notices or SBOM were not generated."
}
$Sbom = Get-Content -LiteralPath $SbomPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($Sbom.schema_version -ne "gfm-third-party-sbom/1.0" -or $Sbom.component_count -lt 10 -or @($Sbom.components).Count -ne $Sbom.component_count) {
    throw "Third-party SBOM validation failed."
}

$Forbidden = Get-ChildItem -LiteralPath $PackagePath -Recurse -Force | Where-Object {
    $_.FullName -match '(^|\\)(node_modules|__pycache__|\.pytest_cache|external)(\\|$)'
}
if ($Forbidden) {
    throw "Release contains forbidden development or third-party repository paths."
}

Write-Step "Computing the release file manifest..."
$ManifestPath = Join-Path $PackagePath "release-manifest.json"
$Files = Get-ChildItem -LiteralPath $PackagePath -Recurse -File |
    Where-Object { $_.FullName -ne $ManifestPath } |
    Sort-Object FullName
$ManifestFiles = foreach ($File in $Files) {
    [ordered]@{
        path = $File.FullName.Substring($PackagePath.Length + 1).Replace('\', '/')
        sizeBytes = $File.Length
        sha256 = (Get-FileHash -LiteralPath $File.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$Manifest = [ordered]@{
    schemaVersion = "1.0"
    product = $BuildInfo.product
    version = $Version
    commit = $Commit
    workingTreeDirty = $Dirty
    builtAtUtc = $BuildTime
    platform = "windows-x64"
    fileCount = @($ManifestFiles).Count
    manifestSelfExcluded = $true
    excludedSourceTrees = @("node_modules", "cache directories", "external repositories")
    files = @($ManifestFiles)
}
$Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8
foreach ($Entry in $ManifestFiles) {
    $VerifiedPath = Join-Path $PackagePath ($Entry.path.Replace('/', '\'))
    $VerifiedHash = (Get-FileHash -LiteralPath $VerifiedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($VerifiedHash -ne $Entry.sha256) {
        throw "Release manifest verification failed: $($Entry.path)"
    }
}

if (-not $SkipSmokeTest) {
    Write-Step "Running the packaged startup and shutdown smoke test..."
    $Executable = Join-Path $PackagePath "GFM-Stability-Platform.exe"
    Invoke-Native $Executable @(
        "--smoke-test", "--no-browser", "--port", "18080",
        "--evidence-file", $PackagedSmokeEvidence
    )
    $SmokeEvidence = Get-Content -LiteralPath $PackagedSmokeEvidence -Raw -Encoding UTF8 | ConvertFrom-Json
    if (
        $SmokeEvidence.status -ne "passed" -or
        $SmokeEvidence.checks.fig8_sensitivity.nine_point_uncovered_count -ne 0 -or
        $SmokeEvidence.checks.fig8_sensitivity.nine_point_missed_full_uncovered_count -ne 75 -or
        $SmokeEvidence.checks.fig8_sensitivity.maximum_tolerance_mismatch_count -ne 0 -or
        $SmokeEvidence.checks.fig8_sensitivity.maximum_scale_mismatch_count -ne 0 -or
        $SmokeEvidence.checks.fig8_sensitivity.report -ne "passed" -or
        $SmokeEvidence.checks.reduced_order.stability -ne "stable" -or
        $SmokeEvidence.checks.reduced_order.report -ne "passed" -or
        $SmokeEvidence.checks.average_dq.stability -ne "stable" -or
        $SmokeEvidence.checks.average_dq.pole_count -ne 16 -or
        $SmokeEvidence.checks.average_dq.reduction_frequency_relative_error -ge 0.05 -or
        $SmokeEvidence.checks.average_dq.reduction_decay_relative_error -ge 0.05 -or
        $SmokeEvidence.checks.average_dq.hierarchy_scan_point_count -ne 42 -or
        $SmokeEvidence.checks.average_dq.hierarchy_scan_agreement_count -ne 39 -or
        $SmokeEvidence.checks.average_dq.hierarchy_scan_disagreement_count -ne 3 -or
        $SmokeEvidence.checks.average_dq.report -ne "passed"
    ) {
        throw "Packaged runtime evidence verification failed."
    }
    Start-Sleep -Milliseconds 300
    $Listener = Get-NetTCPConnection -LocalPort 18080 -State Listen -ErrorAction SilentlyContinue
    if ($Listener) {
        throw "Packaged smoke test exited but port 18080 is still listening."
    }
}

Write-Step "Creating the distributable ZIP archive..."
Compress-Archive -LiteralPath $PackagePath -DestinationPath $ZipPath -CompressionLevel Optimal
$ZipHash = (Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$PackageBytes = (Get-ChildItem -LiteralPath $PackagePath -Recurse -File | Measure-Object Length -Sum).Sum

Write-Step "Removing reproducible build intermediates..."
foreach ($Path in @($BuildRoot, $DistRoot, $FrontendSnapshot, $MetadataPath, $PackagedSmokeEvidence)) {
    Assert-InReleaseRoot $Path
    if (Test-Path $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

Write-Host ""
Write-Host "GFM_RELEASE_BUILD_OK" -ForegroundColor Green
Write-Host "Package: $PackagePath"
Write-Host "ZIP: $ZipPath"
Write-Host "Package bytes: $PackageBytes"
Write-Host "ZIP SHA-256: $ZipHash"
