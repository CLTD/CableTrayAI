param(
    [string]$PackageRoot = "",
    [string]$TargetRoot = "",
    [switch]$VerifyOnly,
    [switch]$NoRestart,
    [switch]$NoHealthCheck,
    [int]$HealthTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

function Resolve-FullPath {
    param([string]$Path)
    try {
        return [System.IO.Path]::GetFullPath($Path)
    }
    catch [System.IO.PathTooLongException] {
        if ([System.IO.Path]::IsPathRooted($Path)) {
            return $Path
        }
        return (Join-Path (Get-Location).Path $Path)
    }
}

function Get-RelativePathCompat {
    param([string]$BasePath, [string]$FullPath)
    $base = Resolve-FullPath $BasePath
    if (-not $base.EndsWith("\")) {
        $base = "$base\"
    }
    $full = Resolve-FullPath $FullPath
    if (-not $full.StartsWith($base, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside expected root: $FullPath"
    }
    return $full.Substring($base.Length)
}

function Assert-Under {
    param([string]$Path, [string]$Parent, [string]$Message)
    $fullPath = (Resolve-FullPath $Path).TrimEnd("\")
    $fullParent = (Resolve-FullPath $Parent).TrimEnd("\")
    if (-not ($fullPath.Equals($fullParent, [System.StringComparison]::OrdinalIgnoreCase) -or $fullPath.StartsWith($fullParent + "\", [System.StringComparison]::OrdinalIgnoreCase))) {
        throw $Message
    }
}

function Remove-TempTree {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) {
        return
    }
    $shortTempRoot = Join-Path $env:SystemDrive "CableTrayAI_Update_Temp"
    $tempRoot = [System.IO.Path]::GetFullPath($shortTempRoot).TrimEnd("\")
    Assert-Under -Path $Path -Parent $tempRoot -Message "Refusing to remove non-temp update path: $Path"
    Remove-Item -LiteralPath $Path -Recurse -Force
}

function Test-UpdatePayloadSafety {
    param([string]$ExtractRoot)
    foreach ($name in @("jobs", "uploads", "outputs", "logs")) {
        if (Test-Path -LiteralPath (Join-Path $ExtractRoot $name)) {
            throw "Unsafe update payload contains protected runtime directory: $name"
        }
    }
    $localConfigs = @(
        Get-ChildItem -LiteralPath $ExtractRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -match '\\config\\.*\.local(\..*)?\.(toml|json)$' -or
                $_.FullName -match '\\runtime\\auth_sessions\.json$'
            }
    )
    if ($localConfigs.Count -gt 0) {
        throw "Unsafe update payload contains local runtime config/session file: $($localConfigs[0].FullName)"
    }
    foreach ($required in @(
        "runtime\CableTrayAI_Server\CableTrayAI_Server.exe",
        "scripts\apply_internal_update.ps1",
        "scripts\deployment_package_gate.py"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $ExtractRoot $required))) {
            throw "Update payload is missing required file: $required"
        }
    }
}

function Expand-AndVerifyPayload {
    param([string]$PackageRoot, [string]$PayloadZip, [string]$PayloadManifestPath)
    $stamp = Get-Date -Format "yyyyMMddHHmmssffff"
    $shortTempRoot = Join-Path $env:SystemDrive "CableTrayAI_Update_Temp"
    New-Item -ItemType Directory -Force -Path $shortTempRoot | Out-Null
    $extractRoot = Join-Path $shortTempRoot "u_$stamp"
    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    Expand-Archive -LiteralPath $PayloadZip -DestinationPath $extractRoot -Force

    $convertedManifest = Get-Content -LiteralPath $PayloadManifestPath -Raw | ConvertFrom-Json
    $manifest = @()
    if ($convertedManifest -is [System.Array]) {
        foreach ($entry in $convertedManifest) {
            $manifest += $entry
        }
    }
    else {
        $manifest += $convertedManifest
    }
    if ($manifest.Count -eq 0) {
        throw "Payload file manifest is empty."
    }

    $expected = @{}
    foreach ($item in $manifest) {
        $relative = ([string]$item.path).Replace("/", "\")
        if ([System.IO.Path]::IsPathRooted($relative) -or $relative.Split("\") -contains "..") {
            throw "Unsafe payload manifest path: $relative"
        }
        $expected[$relative.ToLowerInvariant()] = $item
        $candidate = Join-Path $extractRoot $relative
        Assert-Under -Path $candidate -Parent $extractRoot -Message "Unsafe payload manifest path: $relative"
        if (-not (Test-Path -LiteralPath $candidate)) {
            throw "Payload file missing after extraction: $relative"
        }
        $file = Get-Item -LiteralPath $candidate
        if ([int64]$item.length -ne [int64]$file.Length) {
            throw "Payload file size mismatch: $relative"
        }
        $hash = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($hash -ne ([string]$item.sha256).ToLowerInvariant()) {
            throw "Payload file hash mismatch: $relative"
        }
    }

    $actualFiles = @(Get-ChildItem -LiteralPath $extractRoot -Recurse -File -ErrorAction SilentlyContinue)
    foreach ($file in $actualFiles) {
        $relative = (Get-RelativePathCompat -BasePath $extractRoot -FullPath $file.FullName).ToLowerInvariant()
        if (-not $expected.ContainsKey($relative)) {
            throw "Payload contains unmanifested file: $relative"
        }
    }

    Test-UpdatePayloadSafety -ExtractRoot $extractRoot
    return $extractRoot
}

function Resolve-TargetRoot {
    param([string]$Requested)
    if ($Requested) {
        if (-not (Test-Path -LiteralPath $Requested)) {
            throw "TargetRoot does not exist: $Requested"
        }
        return (Resolve-Path -LiteralPath $Requested).Path
    }

    $regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CableTrayAI"
    if (Test-Path $regPath) {
        $installLocation = (Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue).InstallLocation
        if ($installLocation -and (Test-Path -LiteralPath $installLocation)) {
            return (Resolve-Path -LiteralPath $installLocation).Path
        }
    }

    foreach ($candidate in @("D:\CableTrayAI", "C:\CableTrayAI")) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    throw "Cannot find CableTrayAI install folder. Re-run with -TargetRoot D:\CableTrayAI or the actual install path."
}

function Start-CableTrayAIServer {
    param([string]$TargetRoot)
    $server = Join-Path $TargetRoot "runtime\CableTrayAI_Server\CableTrayAI_Server.exe"
    if (-not (Test-Path -LiteralPath $server)) {
        throw "Cannot restart service; missing server runtime: $server"
    }
    Start-Process -FilePath $server -WorkingDirectory $TargetRoot -WindowStyle Hidden | Out-Null
}

function Wait-CableTrayAIHealth {
    param([int]$TimeoutSeconds)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
                return $true
            }
        }
        catch {
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Restore-BackupOverlay {
    param([string]$TargetRoot, [string]$BackupRoot)
    if (-not $BackupRoot -or -not (Test-Path -LiteralPath $BackupRoot)) {
        return $false
    }
    Assert-Under -Path $BackupRoot -Parent (Join-Path $TargetRoot "_update_backups") -Message "Refusing rollback from outside target backup root: $BackupRoot"
    foreach ($entry in Get-ChildItem -LiteralPath $BackupRoot -Force) {
        $destination = Join-Path $TargetRoot $entry.Name
        if ($entry.PSIsContainer) {
            Copy-Item -LiteralPath $entry.FullName -Destination $TargetRoot -Recurse -Force
        }
        else {
            Copy-Item -LiteralPath $entry.FullName -Destination $destination -Force
        }
    }
    return $true
}

if (-not $PackageRoot) {
    $PackageRoot = $PSScriptRoot
}
$PackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
$manifestRoot = Join-Path $PackageRoot "manifest"
$updateManifestPath = Join-Path $manifestRoot "update_manifest.json"
$payloadManifestPath = Join-Path $manifestRoot "payload_file_manifest.json"
$payloadZip = Join-Path $PackageRoot "payload\CableTrayAI_payload.zip"

foreach ($requiredPath in @($updateManifestPath, $payloadManifestPath, $payloadZip)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Update package is incomplete; missing $requiredPath"
    }
}

$updateManifest = Get-Content -LiteralPath $updateManifestPath -Raw | ConvertFrom-Json
$payloadZipHash = (Get-FileHash -LiteralPath $payloadZip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($payloadZipHash -ne ([string]$updateManifest.payload_zip_sha256).ToLowerInvariant()) {
    throw "Payload zip hash mismatch. The update package may be corrupted."
}

$verifiedExtract = $null
try {
    $verifiedExtract = Expand-AndVerifyPayload -PackageRoot $PackageRoot -PayloadZip $payloadZip -PayloadManifestPath $payloadManifestPath
    Write-Host "Update package verification passed."

    if ($VerifyOnly) {
        return
    }

    $target = Resolve-TargetRoot -Requested $TargetRoot
    Write-Host "Target install folder: $target"

    $applyScript = Join-Path $verifiedExtract "scripts\apply_internal_update.ps1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $applyScript -UpdateZip $payloadZip -TargetRoot $target -Force
    if ($LASTEXITCODE -ne 0) {
        throw "apply_internal_update.ps1 failed with exit code $LASTEXITCODE"
    }

    $lastApplyPath = Join-Path $target "docs\last_internal_update_apply.json"
    $lastApply = $null
    if (Test-Path -LiteralPath $lastApplyPath) {
        $lastApply = Get-Content -LiteralPath $lastApplyPath -Raw | ConvertFrom-Json
    }

    if (-not $NoRestart) {
        Start-CableTrayAIServer -TargetRoot $target
    }

    $healthStatus = "skipped"
    if (-not $NoHealthCheck) {
        if (Wait-CableTrayAIHealth -TimeoutSeconds $HealthTimeoutSeconds) {
            $healthStatus = "pass"
        }
        else {
            $healthStatus = "fail"
            $backupPath = if ($lastApply) { [string]$lastApply.backup } else { "" }
            $restored = Restore-BackupOverlay -TargetRoot $target -BackupRoot $backupPath
            if (-not $NoRestart) {
                Start-CableTrayAIServer -TargetRoot $target
            }
            throw "Update applied but health check failed; rollback overlay attempted=$restored, backup=$backupPath"
        }
    }

    $report = [ordered]@{
        status = "pass"
        update_package = $PackageRoot
        payload_zip_sha256 = $payloadZipHash
        target_root = $target
        applied_at = (Get-Date).ToString("s")
        health = $healthStatus
        backup = if ($lastApply) { $lastApply.backup } else { $null }
        policy = "Local jobs/uploads/outputs/logs and config/*.local.* are preserved; payload hashes are verified before any target files are copied."
    }
    $reportPath = Join-Path $target "docs\last_mail_update_apply.json"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
    $report | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -Path $reportPath

    Write-Host "CableTrayAI update applied successfully."
    Write-Host "Health: $healthStatus"
    if ($lastApply) {
        Write-Host "Backup: $($lastApply.backup)"
    }
}
finally {
    Remove-TempTree -Path $verifiedExtract
}
