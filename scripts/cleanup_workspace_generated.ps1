param(
    [switch]$IncludeLogs,
    [switch]$IncludeUploads,
    [switch]$IncludeOutputs
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")

$safeRelativePaths = @(
    ".pytest_cache",
    ".pytest_tmp",
    "_pyinstaller_desktop_build",
    "_pyinstaller_desktop_dist",
    "_pyinstaller_desktop_spec"
)

if ($IncludeLogs) {
    $safeRelativePaths += "logs"
}
if ($IncludeUploads) {
    $safeRelativePaths += "uploads"
}
if ($IncludeOutputs) {
    $safeRelativePaths += "outputs"
}

$forbiddenTopLevel = @(
    ".git",
    "source_materials",
    "jobs",
    "core",
    "apps",
    "templates",
    "data",
    "config",
    "tests",
    "docs",
    "scripts"
)

$removed = @()
foreach ($relative in $safeRelativePaths) {
    $firstSegment = ($relative -split "[/\\]")[0]
    if ($forbiddenTopLevel -contains $firstSegment) {
        throw "Refusing to clean protected path: $relative"
    }
    $target = Join-Path $Root $relative
    if (-not (Test-Path -LiteralPath $target)) {
        continue
    }
    $resolved = Resolve-Path -LiteralPath $target
    if (-not $resolved.Path.StartsWith($Root.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean path outside workspace: $($resolved.Path)"
    }
    try {
        Get-ChildItem -LiteralPath $resolved.Path -Force -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $_.Attributes = "Normal"
            } catch {
                # Best effort: a locked cache file should not stop source cleanup.
            }
        }
        $item = Get-Item -LiteralPath $resolved.Path -Force
        $item.Attributes = "Normal"
        Remove-Item -LiteralPath $resolved.Path -Recurse -Force
        $removed += $relative
    } catch {
        $removed += "$relative (skipped: $($_.Exception.Message))"
    }
}

[pscustomobject]@{
    status = "pass"
    root = $Root.Path
    removed = $removed
    protected = $forbiddenTopLevel
} | ConvertTo-Json -Depth 3
