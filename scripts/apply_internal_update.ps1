param(
    [Parameter(Mandatory = $true)]
    [string]$UpdateZip,
    [string]$TargetRoot = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if (-not $TargetRoot) {
    $TargetRoot = Split-Path -Parent $PSScriptRoot
}
$TargetRoot = (Resolve-Path $TargetRoot).Path
$UpdateZip = (Resolve-Path $UpdateZip).Path

$backupRoot = Join-Path $TargetRoot "_update_backups"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $backupRoot $stamp
$extract = Join-Path $TargetRoot "_internal_update\apply_$stamp"

function Stop-CableTrayAIProcesses {
    foreach ($name in @("CableTrayAI_Server", "CableTrayAI")) {
        Get-Process -Name $name -ErrorAction SilentlyContinue |
            Stop-Process -Force -ErrorAction SilentlyContinue
    }
    try {
        $currentPid = $PID
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object {
                $_.ProcessId -ne $currentPid -and
                $_.CommandLine -match "portable_server\.py|uvicorn.*apps\.api\.app"
            } |
            ForEach-Object {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
    }
    catch {
    }
}

Stop-CableTrayAIProcesses

New-Item -ItemType Directory -Force -Path $backup | Out-Null
New-Item -ItemType Directory -Force -Path $extract | Out-Null

Expand-Archive -Path $UpdateZip -DestinationPath $extract -Force

$protected = @("jobs", "uploads", "outputs")
$staleRelativeFiles = @(
    "core\spectra\interpolation.py"
)
foreach ($name in $protected) {
    if (Test-Path (Join-Path $extract $name)) {
        throw "Unsafe update package contains protected path: $name"
    }
}

Get-ChildItem -Path $extract -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.FullName -match '\\config\\.*\.local(\..*)?\.toml$' -or
        $_.FullName -match '\\config\\.*\.local(\..*)?\.json$'
    } |
    ForEach-Object { throw "Unsafe update package contains local config: $($_.FullName)" }

$paths = @("apps", "core", "templates", "data", "scripts", "docs", ".agents", "config", "runtime")
$files = @("README.md", "AGENTS.md", "pyproject.toml", "requirements.txt", ".gitignore", "CableTrayAI.exe")

foreach ($path in $paths) {
    $src = Join-Path $extract $path
    if (-not (Test-Path $src)) {
        continue
    }
    $dst = Join-Path $TargetRoot $path
    if (Test-Path $dst) {
        Copy-Item -Path $dst -Destination (Join-Path $backup $path) -Recurse -Force
    }
    Copy-Item -Path $src -Destination $TargetRoot -Recurse -Force
}

foreach ($file in $files) {
    $src = Join-Path $extract $file
    if (-not (Test-Path $src)) {
        continue
    }
    $dst = Join-Path $TargetRoot $file
    if (Test-Path $dst) {
        Copy-Item -Path $dst -Destination (Join-Path $backup $file) -Force
    }
    Copy-Item -Path $src -Destination $dst -Force
}

$sourceSrc = Join-Path $extract "source_materials"
if (Test-Path $sourceSrc) {
    Copy-Item -Path $sourceSrc -Destination $TargetRoot -Recurse -Force
}

Get-ChildItem -Path $extract -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Extension -in @(".cmd", ".ps1", ".txt") -and $_.Name -notlike "*manifest*" } |
    ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $TargetRoot $_.Name) -Force
    }

$removedStaleFiles = @()
$targetPrefix = [System.IO.Path]::GetFullPath($TargetRoot)
if (-not $targetPrefix.EndsWith("\")) {
    $targetPrefix = "$targetPrefix\"
}
foreach ($relative in $staleRelativeFiles) {
    $candidate = [System.IO.Path]::GetFullPath((Join-Path $TargetRoot $relative))
    if (-not $candidate.StartsWith($targetPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove stale file outside target root: $relative"
    }
    if (Test-Path -LiteralPath $candidate) {
        $backupCandidate = Join-Path $backup $relative
        $backupDir = Split-Path -Parent $backupCandidate
        New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
        Copy-Item -LiteralPath $candidate -Destination $backupCandidate -Force
        Remove-Item -LiteralPath $candidate -Force
        $removedStaleFiles += $relative
    }
}

$audit = [ordered]@{
    status = "pass"
    update_zip = $UpdateZip
    target_root = $TargetRoot
    backup = $backup
    applied_at = (Get-Date).ToString("s")
    protected_paths_preserved = $protected
    minimal_source_materials_applied = (Test-Path $sourceSrc)
    local_configs_preserved = $true
    removed_stale_files = $removedStaleFiles
}
$audit | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $TargetRoot "docs\last_internal_update_apply.json")

Write-Host "Update applied."
Write-Host "Backup: $backup"
Write-Host "Restart the CableTrayAI server after applying the update."
