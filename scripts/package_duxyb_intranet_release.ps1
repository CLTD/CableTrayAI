param(
    [string]$OutputRoot = "C:\Users\duxy\Desktop\duxyb",
    [switch]$BuildPortableRuntime,
    [switch]$BuildDesktopRuntime,
    [switch]$BuildInstallerRuntime
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
$PackageDir = Join-Path $OutputRoot "CableTrayAI"
$ZipPath = Join-Path $OutputRoot "CableTrayAI.zip"
$SourceMaterialsRoot = [System.IO.Path]::GetFullPath((Join-Path $Root "source_materials")).TrimEnd('\')

function Assert-Under {
    param([string]$Path, [string]$Parent)
    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $fullParent = [System.IO.Path]::GetFullPath($Parent).TrimEnd('\')
    if (-not $fullPath.StartsWith($fullParent, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe path outside output root: $fullPath"
    }
}

function Should-SkipPath {
    param([string]$Path)
    $name = Split-Path -Leaf $Path
    if ($name -in @("__pycache__", ".pytest_cache", ".pytest_tmp", ".git")) {
        return $true
    }
    if ($name -like "_pyinstaller_*") {
        return $true
    }
    if ($name -in @("ansys.local.toml", "ansys.local.discovered.toml", "ansys_discovery.json", "operator.local.json")) {
        return $true
    }
    $ext = [System.IO.Path]::GetExtension($Path)
    $fullPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $rootFullPath = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ($fullPath.StartsWith($rootFullPath + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        $relativePath = $fullPath.Substring($rootFullPath.Length + 1)
        $topLevelName = ($relativePath -split '[\\/]', 2)[0]
        $isTopLevelEntry = ($relativePath -eq $topLevelName)
        if ($isTopLevelEntry -and $topLevelName -in @("jobs", "uploads", "outputs", "logs", "_internal_update", "_review_pre_real")) {
            return $true
        }
        if ($relativePath -match '^docs[\\/](web_runs|production_runs|precision_gate)([\\/]|$)') {
            return $true
        }
        if ($relativePath -match '^docs[\\/](web_error_log\.jsonl|ansys_discovery\.json)$') {
            return $true
        }
        if ($relativePath -match '^config[\\/].*\.local(\..*)?\.(toml|json)$') {
            return $true
        }
        if ($relativePath -match '^runtime[\\/]auth_sessions\.json$') {
            return $true
        }
    }
    if ($fullPath.StartsWith($SourceMaterialsRoot, [System.StringComparison]::OrdinalIgnoreCase) -and $ext -in @(".docx", ".pdf", ".bak")) {
        return $true
    }
    return $ext -in @(".pyc", ".pyo", ".bak", ".tmp")
}

function Copy-TreeFiltered {
    param([string]$Source, [string]$Target)
    if (-not (Test-Path -LiteralPath $Source)) {
        return
    }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    foreach ($entry in Get-ChildItem -LiteralPath $Source -Force) {
        if (Should-SkipPath $entry.FullName) {
            continue
        }
        $dest = Join-Path $Target $entry.Name
        if ($entry.PSIsContainer) {
            Copy-TreeFiltered -Source $entry.FullName -Target $dest
        }
        else {
            Copy-Item -LiteralPath $entry.FullName -Destination $dest -Force
        }
    }
}

if ($BuildPortableRuntime) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\build_portable_runtime.ps1")
    if ($LASTEXITCODE -ne 0) { throw "build_portable_runtime.ps1 failed" }
}
if ($BuildDesktopRuntime) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\build_desktop_runtime.ps1")
    if ($LASTEXITCODE -ne 0) { throw "build_desktop_runtime.ps1 failed" }
}
if ($BuildInstallerRuntime) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\build_installer_runtime.ps1")
    if ($LASTEXITCODE -ne 0) { throw "build_installer_runtime.ps1 failed" }
}

$serverExe = Join-Path $Root "runtime\CableTrayAI_Server\CableTrayAI_Server.exe"
$desktopExe = Join-Path $Root "runtime\CableTrayAI_Desktop\CableTrayAI.exe"
$installerExe = Join-Path $Root "runtime\CableTrayAI_Installer\CableTrayAI_Installer.exe"
foreach ($required in @($serverExe, $desktopExe, $installerExe)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing runtime artifact: $required"
    }
}

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
Assert-Under -Path $PackageDir -Parent $OutputRoot
if (Test-Path -LiteralPath $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

$dirs = @(
    ".agents",
    "apps",
    "config",
    "core",
    "data",
    "docs",
    "prompts",
    "runtime",
    "scripts",
    "source_materials",
    "templates"
)
foreach ($dir in $dirs) {
    Copy-TreeFiltered -Source (Join-Path $Root $dir) -Target (Join-Path $PackageDir $dir)
}

$rootFiles = @(".gitignore", "AGENTS.md", "README.md", "pyproject.toml", "requirements.txt")
foreach ($file in $rootFiles) {
    $src = Join-Path $Root $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $PackageDir $file) -Force
    }
}
Copy-Item -LiteralPath $desktopExe -Destination (Join-Path $PackageDir "CableTrayAI.exe") -Force
Copy-Item -LiteralPath $installerExe -Destination (Join-Path $PackageDir "CableTrayAI_Installer.exe") -Force

$readmeLines = @(
    "CableTrayAI deployment package",
    "",
    "Install:",
    "1. Extract CableTrayAI.zip.",
    "2. Double-click CableTrayAI\CableTrayAI_Installer.exe.",
    "3. Select an installation folder when prompted.",
    "4. Start CableTrayAI from the desktop shortcut.",
    "",
    "Login:",
    "- First install creates config/auth.local.json locally.",
    "- The generated initial password is written only to install_manifest.json on that machine.",
    "- Do not publish or commit local credentials.",
    "",
    "Notes:",
    "- The package includes standard APDL/PIP/MAC/SECT sources, templates, source_materials, and runtime files.",
    "- Historical jobs, uploads, outputs, logs, cache folders, and local ansys.local.toml are not packaged.",
    "- Keeping historical generated results out of the package prevents stale data from polluting new intake calculations.",
    "- ANSYS is discovered by the application and can also be set manually in the web UI.",
    "- Production conclusions still come from ANSYS outputs, Excel/deterministic formulas, and source_ref traceability."
)
$readmeLines | Set-Content -Encoding UTF8 -Path (Join-Path $PackageDir "README_INSTALL.txt")

$manifest = [ordered]@{
    package_name = "CableTrayAI"
    created_at = (Get-Date).ToString("s")
    source_root = $Root
    excludes = @("jobs", "uploads", "outputs", "logs", ".git", ".pytest_cache", ".pytest_tmp", "config/ansys.local.toml")
    entry = "CableTrayAI_Installer.exe"
    desktop_runtime = "runtime/CableTrayAI_Desktop/CableTrayAI.exe"
    server_runtime = "runtime/CableTrayAI_Server/CableTrayAI_Server.exe"
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -Path (Join-Path $PackageDir "release_manifest.json")

$gateScript = Join-Path $Root "scripts\deployment_package_gate.py"
if (Test-Path -LiteralPath $gateScript) {
    $python = Get-Command python -ErrorAction Stop
    & $python.Source $gateScript --package-dir $PackageDir
    if ($LASTEXITCODE -ne 0) {
        throw "deployment_package_gate.py failed; package was not zipped"
    }
}

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force

Write-Host "CableTrayAI deployment package created:"
Write-Host $PackageDir
Write-Host $ZipPath
Write-Host ("Zip size MB: {0:N2}" -f ((Get-Item -LiteralPath $ZipPath).Length / 1MB))
