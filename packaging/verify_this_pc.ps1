param(
    [switch]$NonInteractive,
    [switch]$DeclareOffline,
    [switch]$DeclareCleanEnvironment,
    [int]$PreferredPort = 18080
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$PackageRoot = [IO.Path]::GetFullPath($PSScriptRoot)
$ManifestPath = Join-Path $PackageRoot "release-manifest.json"
$ExecutablePath = Join-Path $PackageRoot "GFM-Stability-Platform.exe"
$Timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$SafeComputerName = ($env:COMPUTERNAME -replace '[^0-9A-Za-z_-]', '_')
if ([string]::IsNullOrWhiteSpace($SafeComputerName)) {
    $SafeComputerName = "unknown-pc"
}
$ResultDirectory = Join-Path $PackageRoot "acceptance-results\$Timestamp-$SafeComputerName"
New-Item -ItemType Directory -Force -Path $ResultDirectory | Out-Null
$RuntimeEvidencePath = Join-Path $ResultDirectory "runtime-evidence.json"
$ConsoleLogPath = Join-Path $ResultDirectory "runtime-console.log"
$EvidencePath = Join-Path $ResultDirectory "cross-machine-acceptance.json"
$SummaryPath = Join-Path $ResultDirectory "acceptance-summary.txt"

function Read-YesNo([string]$Prompt) {
    $Answer = Read-Host "$Prompt [y/N]"
    return $Answer -match '^(y|yes|是)$'
}

function Find-FreePort([int]$StartPort) {
    foreach ($Candidate in $StartPort..([Math]::Min($StartPort + 20, 65535))) {
        $Listener = $null
        try {
            $Listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Candidate)
            $Listener.Start()
            return $Candidate
        }
        catch {
            continue
        }
        finally {
            if ($null -ne $Listener) {
                $Listener.Stop()
            }
        }
    }
    throw "No free loopback port was found from $StartPort to $([Math]::Min($StartPort + 20, 65535))."
}

function Test-PortAvailable([int]$Port) {
    $Listener = $null
    try {
        $Listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, $Port)
        $Listener.Start()
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $Listener) {
            $Listener.Stop()
        }
    }
}

if (-not $NonInteractive) {
    if (-not $DeclareOffline) {
        $DeclareOffline = Read-YesNo "测试过程中是否已经断开 Wi-Fi、网线和其他互联网连接？"
    }
    if (-not $DeclareCleanEnvironment) {
        $DeclareCleanEnvironment = Read-YesNo "这台电脑是否未安装 Python、Node.js 和 MATLAB？"
    }
}

$DetectedRuntimes = [ordered]@{}
foreach ($Runtime in @("python.exe", "node.exe", "matlab.exe")) {
    $Command = Get-Command $Runtime -ErrorAction SilentlyContinue
    $DetectedRuntimes[$Runtime] = if ($null -eq $Command) { $null } else { $Command.Source }
}
$RuntimeCommandsAbsent = @($DetectedRuntimes.Values | Where-Object { $null -ne $_ }).Count -eq 0
$ManifestErrors = New-Object System.Collections.Generic.List[string]
$Manifest = $null
$RuntimeExitCode = $null
$RuntimeEvidence = $null
$SelectedPort = $null
$PortReleased = $false
$Failure = $null

try {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "release-manifest.json is missing."
    }
    if (-not (Test-Path -LiteralPath $ExecutablePath -PathType Leaf)) {
        throw "GFM-Stability-Platform.exe is missing."
    }

    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Manifest.fileCount -ne @($Manifest.files).Count) {
        $ManifestErrors.Add("manifest fileCount does not match the file list")
    }
    foreach ($Entry in $Manifest.files) {
        $RelativePath = ([string]$Entry.path).Replace('/', [IO.Path]::DirectorySeparatorChar)
        $FilePath = [IO.Path]::GetFullPath((Join-Path $PackageRoot $RelativePath))
        if (-not $FilePath.StartsWith($PackageRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            $ManifestErrors.Add("unsafe manifest path: $($Entry.path)")
            continue
        }
        if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
            $ManifestErrors.Add("missing file: $($Entry.path)")
            continue
        }
        $ActualHash = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($ActualHash -ne $Entry.sha256) {
            $ManifestErrors.Add("hash mismatch: $($Entry.path)")
        }
    }
    if ($ManifestErrors.Count -ne 0) {
        throw "Release manifest verification failed."
    }

    $SelectedPort = Find-FreePort $PreferredPort
    $RuntimeOutput = & $ExecutablePath --smoke-test --no-browser --port $SelectedPort --evidence-file $RuntimeEvidencePath 2>&1
    $RuntimeExitCode = $LASTEXITCODE
    $RuntimeOutput | Set-Content -LiteralPath $ConsoleLogPath -Encoding UTF8
    $RuntimeOutput | ForEach-Object { Write-Host $_ }
    if ($RuntimeExitCode -ne 0) {
        throw "Packaged runtime acceptance returned exit code $RuntimeExitCode."
    }
    if (-not (Test-Path -LiteralPath $RuntimeEvidencePath -PathType Leaf)) {
        throw "Runtime evidence JSON was not produced."
    }
    $RuntimeEvidence = Get-Content -LiteralPath $RuntimeEvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($RuntimeEvidence.status -ne "passed") {
        throw "Runtime evidence did not report passed status."
    }
    Start-Sleep -Milliseconds 300
    $PortReleased = Test-PortAvailable $SelectedPort
    if (-not $PortReleased) {
        throw "The local service port was not released after the test."
    }
}
catch {
    $Failure = $_.Exception.Message
}

$SiblingZipPath = "$PackageRoot.zip"
$ZipEvidence = if (Test-Path -LiteralPath $SiblingZipPath -PathType Leaf) {
    [ordered]@{
        path = $SiblingZipPath
        sha256 = (Get-FileHash -LiteralPath $SiblingZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
        size_bytes = (Get-Item -LiteralPath $SiblingZipPath).Length
    }
} else {
    $null
}

$FunctionalPassed = $null -eq $Failure -and $ManifestErrors.Count -eq 0 -and $RuntimeExitCode -eq 0 -and $PortReleased
$M5Qualified = $FunctionalPassed -and [bool]$DeclareOffline -and [bool]$DeclareCleanEnvironment -and $RuntimeCommandsAbsent -and [Environment]::Is64BitOperatingSystem
$Evidence = [ordered]@{
    schema_version = "gfm-cross-machine-acceptance/1.0"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    package = if ($null -eq $Manifest) { $null } else { [ordered]@{
        product = $Manifest.product
        version = $Manifest.version
        commit = $Manifest.commit
        working_tree_dirty = $Manifest.workingTreeDirty
        manifest_file_count = $Manifest.fileCount
    }}
    machine = [ordered]@{
        computer_name = $env:COMPUTERNAME
        os_version = [Environment]::OSVersion.VersionString
        os_64_bit = [Environment]::Is64BitOperatingSystem
        process_64_bit = [Environment]::Is64BitProcess
        powershell_version = $PSVersionTable.PSVersion.ToString()
    }
    qualification = [ordered]@{
        offline_user_declared = [bool]$DeclareOffline
        offline_evidence_kind = "user-declaration-only"
        clean_environment_user_declared = [bool]$DeclareCleanEnvironment
        runtime_command_detection_method = "PATH command lookup"
        detected_runtime_commands = $DetectedRuntimes
        runtime_commands_absent = $RuntimeCommandsAbsent
        m5_offline_no_dev_environment_qualified = $M5Qualified
    }
    checks = [ordered]@{
        manifest_verified = $ManifestErrors.Count -eq 0
        manifest_errors = @($ManifestErrors)
        runtime_exit_code = $RuntimeExitCode
        runtime_evidence_file = $RuntimeEvidencePath
        runtime_status = if ($null -eq $RuntimeEvidence) { $null } else { $RuntimeEvidence.status }
        selected_port = $SelectedPort
        port_released = $PortReleased
        functional_passed = $FunctionalPassed
    }
    source_zip = $ZipEvidence
    failure = $Failure
}
$Evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $EvidencePath -Encoding UTF8

$FailureLine = if ($null -eq $Failure) { "" } else { "失败原因：$Failure" }
$Summary = @(
    "构网型变流器稳定性分析平台：异机验收摘要"
    "生成时间（UTC）：$($Evidence.generated_at_utc)"
    "软件版本：$(if ($null -eq $Manifest) { '未知' } else { $Manifest.version })"
    "源代码提交：$(if ($null -eq $Manifest) { '未知' } else { $Manifest.commit })"
    "包内文件校验：$(if ($ManifestErrors.Count -eq 0) { '通过' } else { '失败' })"
    "运行时功能验收：$(if ($FunctionalPassed) { '通过' } else { '失败' })"
    "断网且无开发环境资格：$(if ($M5Qualified) { '满足' } else { '未满足或证据不足' })"
    "离线状态仅由操作者声明，脚本不能独立证明物理断网。"
    "详细证据：$EvidencePath"
    $FailureLine
)
$Summary | Set-Content -LiteralPath $SummaryPath -Encoding UTF8
$Summary | ForEach-Object { if (-not [string]::IsNullOrWhiteSpace($_)) { Write-Host $_ } }

if ($FunctionalPassed) {
    Write-Host "GFM_CROSS_MACHINE_FUNCTIONAL_OK" -ForegroundColor Green
    if ($M5Qualified) {
        Write-Host "GFM_M5_QUALIFIED" -ForegroundColor Green
    } else {
        Write-Host "GFM_M5_QUALIFICATION_INCOMPLETE" -ForegroundColor Yellow
    }
    exit 0
}
Write-Host "GFM_CROSS_MACHINE_FUNCTIONAL_FAILED" -ForegroundColor Red
exit 1

