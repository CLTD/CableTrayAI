param(
    [string]$OutputRoot = "C:\Users\duxy\Desktop\duxyb-update",
    [string]$DeploymentOutputRoot = "C:\Users\duxy\Desktop\duxyb",
    [string]$UpdateBaseName = "",
    [switch]$BuildPortableRuntime,
    [switch]$BuildDesktopRuntime,
    [switch]$BuildInstallerRuntime,
    [switch]$ReuseExistingDeploymentZip
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$DeploymentOutputRoot = [System.IO.Path]::GetFullPath($DeploymentOutputRoot)
$DeploymentPackageDir = Join-Path $DeploymentOutputRoot "CableTrayAI"
$DeploymentZip = Join-Path $DeploymentOutputRoot "CableTrayAI.zip"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $UpdateBaseName) {
    $UpdateBaseName = "$([char]0x66F4)$([char]0x65B0)$([char]0x5305)"
}
$UpdateName = $UpdateBaseName
$UpdateDir = Join-Path $OutputRoot $UpdateName
$UpdateZip = Join-Path $OutputRoot "$UpdateName.zip"

function Resolve-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path)
}

function Assert-Under {
    param([string]$Path, [string]$Parent)
    $fullPath = (Resolve-FullPath $Path).TrimEnd("\")
    $fullParent = (Resolve-FullPath $Parent).TrimEnd("\")
    if (-not ($fullPath.Equals($fullParent, [System.StringComparison]::OrdinalIgnoreCase) -or $fullPath.StartsWith($fullParent + "\", [System.StringComparison]::OrdinalIgnoreCase))) {
        throw "Unsafe output path outside expected root: $fullPath"
    }
}

function Get-RelativePathCompat {
    param([string]$BasePath, [string]$FullPath)
    $base = Resolve-FullPath $BasePath
    if (-not $base.EndsWith("\")) {
        $base = "$base\"
    }
    $baseUri = New-Object System.Uri($base)
    $pathUri = New-Object System.Uri((Resolve-FullPath $FullPath))
    return [System.Uri]::UnescapeDataString($baseUri.MakeRelativeUri($pathUri).ToString()).Replace("/", "\")
}

function New-FileManifest {
    param([string]$SourceRoot, [string]$ManifestPath)
    $items = @()
    foreach ($file in Get-ChildItem -LiteralPath $SourceRoot -Recurse -File -Force | Sort-Object FullName) {
        $relative = Get-RelativePathCompat -BasePath $SourceRoot -FullPath $file.FullName
        $items += [ordered]@{
            path = $relative
            length = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
    $items | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 -Path $ManifestPath
    return $items
}

function Assert-PayloadSafety {
    param([string]$PayloadRoot)
    foreach ($name in @("jobs", "uploads", "outputs", "logs")) {
        if (Test-Path -LiteralPath (Join-Path $PayloadRoot $name)) {
            throw "Deployment payload contains protected runtime directory: $name"
        }
    }
    $forbidden = @(
        Get-ChildItem -LiteralPath $PayloadRoot -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object {
                $_.FullName -match '\\config\\.*\.local(\..*)?\.(toml|json)$' -or
                $_.FullName -match '\\runtime\\auth_sessions\.json$'
            }
    )
    if ($forbidden.Count -gt 0) {
        throw "Deployment payload contains forbidden local runtime file: $($forbidden[0].FullName)"
    }
    foreach ($required in @(
        "runtime\CableTrayAI_Server\CableTrayAI_Server.exe",
        "runtime\CableTrayAI_Desktop\CableTrayAI.exe",
        "runtime\CableTrayAI_Installer\CableTrayAI_Installer.exe",
        "scripts\apply_internal_update.ps1",
        "scripts\deployment_package_gate.py"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $PayloadRoot $required))) {
            throw "Deployment payload is missing required file: $required"
        }
    }
}

if (-not $ReuseExistingDeploymentZip) {
    $packageArgs = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (Join-Path $Root "scripts\package_duxyb_intranet_release.ps1"),
        "-OutputRoot",
        $DeploymentOutputRoot
    )
    if ($BuildPortableRuntime) { $packageArgs += "-BuildPortableRuntime" }
    if ($BuildDesktopRuntime) { $packageArgs += "-BuildDesktopRuntime" }
    if ($BuildInstallerRuntime) { $packageArgs += "-BuildInstallerRuntime" }
    & powershell @packageArgs
    if ($LASTEXITCODE -ne 0) {
        throw "package_duxyb_intranet_release.ps1 failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $DeploymentZip)) {
    throw "Missing deployment zip: $DeploymentZip"
}
if (-not (Test-Path -LiteralPath $DeploymentPackageDir)) {
    throw "Missing deployment package directory: $DeploymentPackageDir"
}

Assert-PayloadSafety -PayloadRoot $DeploymentPackageDir

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
Assert-Under -Path $UpdateDir -Parent $OutputRoot
Assert-Under -Path $UpdateZip -Parent $OutputRoot
if (Test-Path -LiteralPath $UpdateDir) {
    Remove-Item -LiteralPath $UpdateDir -Recurse -Force
}
if (Test-Path -LiteralPath $UpdateZip) {
    Remove-Item -LiteralPath $UpdateZip -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $UpdateDir "payload") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $UpdateDir "manifest") | Out-Null
Copy-Item -LiteralPath $DeploymentZip -Destination (Join-Path $UpdateDir "payload\CableTrayAI_payload.zip") -Force
Copy-Item -LiteralPath (Join-Path $Root "scripts\install_update_package.ps1") -Destination (Join-Path $UpdateDir "install_update.ps1") -Force

$cmdLines = @(
    "@echo off",
    "cd /d ""%~dp0""",
    "powershell -NoProfile -ExecutionPolicy Bypass -File ""%~dp0install_update.ps1""",
    "pause"
)
$cmdLines | Set-Content -Encoding ASCII -Path (Join-Path $UpdateDir "Install_Update.cmd")

$payloadFileManifest = New-FileManifest -SourceRoot $DeploymentPackageDir -ManifestPath (Join-Path $UpdateDir "manifest\payload_file_manifest.json")
$payloadZipPath = Join-Path $UpdateDir "payload\CableTrayAI_payload.zip"
$payloadZipItem = Get-Item -LiteralPath $payloadZipPath
$updateManifest = [ordered]@{
    package_name = "CableTrayAI internal update"
    created_at = (Get-Date).ToString("s")
    update_name = $UpdateName
    build_stamp = $Stamp
    source_root = $Root
    deployment_package_zip = $DeploymentZip
    payload_zip = "payload/CableTrayAI_payload.zip"
    payload_zip_length = $payloadZipItem.Length
    payload_zip_sha256 = (Get-FileHash -LiteralPath $payloadZipPath -Algorithm SHA256).Hash.ToLowerInvariant()
    payload_file_count = $payloadFileManifest.Count
    apply_script = "install_update.ps1"
    one_click_script = "Install_Update.cmd"
    target_policy = "Preserve target-machine jobs/uploads/outputs/logs, config/*.local.*, runtime/auth_sessions.json, and ANSYS local config."
    verification_policy = "install_update.ps1 verifies payload zip SHA256 and every expanded payload file before applying."
    rollback_policy = "install_update.ps1 uses the backup written by scripts/apply_internal_update.ps1 and overlays it back if health check fails."
}
$updateManifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -Path (Join-Path $UpdateDir "manifest\update_manifest.json")

$readmeLines = @(
    "CableTrayAI internal mail update package",
    "",
    "Recommended usage:",
    "1. Extract this zip on the unit computer.",
    "2. Double-click Install_Update.cmd. If cmd files are blocked, open PowerShell in this folder and run:",
    "   powershell -NoProfile -ExecutionPolicy Bypass -File .\install_update.ps1",
    "3. The script auto-detects the installed folder. If it is not D:\CableTrayAI, run:",
    "   powershell -NoProfile -ExecutionPolicy Bypass -File .\install_update.ps1 -TargetRoot <actual install folder>",
    "",
    "Pre-apply verification:",
    "- Verify payload/CableTrayAI_payload.zip SHA256.",
    "- Verify every expanded payload file against manifest/payload_file_manifest.json by SHA256 and file size.",
    "- Reject payloads containing jobs/uploads/outputs/logs, config/*.local.*, or runtime/auth_sessions.json.",
    "- Require runtime/CableTrayAI_Server/CableTrayAI_Server.exe and apply_internal_update.ps1.",
    "",
    "Update policy:",
    "- Update application code, web UI, formulas, templates, runtime, and standard command-stream materials.",
    "- Preserve local jobs/uploads/outputs/logs, config/auth.local.json, and config/ansys.local.toml.",
    "- Back up the previous version to <install folder>\_update_backups\<timestamp> before copying.",
    "- Restart the service and check http://127.0.0.1:8000/health after copying.",
    "- If the health check fails, the script attempts a backup overlay rollback and restart.",
    "",
    "Verify package only:",
    "powershell -NoProfile -ExecutionPolicy Bypass -File .\install_update.ps1 -VerifyOnly",
    "",
    "Important:",
    "- Do not add unit-local config/auth.local.json or ansys.local.toml to this update package.",
    "- Run -VerifyOnly after transfer if you need to confirm the package was not corrupted."
)
$readmeLines | Set-Content -Encoding UTF8 -Path (Join-Path $UpdateDir "README_UPDATE.txt")

Compress-Archive -Path (Join-Path $UpdateDir "*") -DestinationPath $UpdateZip -Force

& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $UpdateDir "install_update.ps1") -VerifyOnly
if ($LASTEXITCODE -ne 0) {
    throw "Update package self-verification failed"
}

$updateZipHash = (Get-FileHash -LiteralPath $UpdateZip -Algorithm SHA256).Hash
$updateZipHash | Set-Content -Encoding ASCII -Path "$UpdateZip.sha256.txt"

$latestPath = Join-Path $OutputRoot "update_package_latest.txt"
@(
    "latest_update_zip=$UpdateZip",
    "latest_update_dir=$UpdateDir",
    "created_at=$((Get-Date).ToString("s"))",
    "update_zip_sha256=$updateZipHash",
    "payload_zip_sha256=$($updateManifest.payload_zip_sha256)",
    "payload_file_count=$($updateManifest.payload_file_count)"
) | Set-Content -Encoding UTF8 -Path $latestPath

Write-Host "CableTrayAI internal update package created:"
Write-Host $UpdateDir
Write-Host $UpdateZip
Write-Host ("Update zip size MB: {0:N2}" -f ((Get-Item -LiteralPath $UpdateZip).Length / 1MB))
Write-Host "Update zip SHA256: $updateZipHash"
Write-Host "Self verification: pass"
