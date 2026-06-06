param(
    [string]$RuntimeRoot = "runtime",
    [switch]$KeepBuildArtifacts
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$pyinstaller = Get-Command pyinstaller -ErrorAction Stop
$distRoot = Join-Path $Root "_pyinstaller_dist"
$buildRoot = Join-Path $Root "_pyinstaller_build"
$specRoot = Join-Path $Root "_pyinstaller_spec"
$runtimeTarget = Join-Path $Root "$RuntimeRoot\CableTrayAI_Server"

foreach ($path in @($distRoot, $buildRoot, $specRoot, $runtimeTarget)) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root $RuntimeRoot) | Out-Null

$args = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", "CableTrayAI_Server",
    "--distpath", $distRoot,
    "--workpath", $buildRoot,
    "--specpath", $specRoot,
    "--paths", $Root,
    "--hidden-import", "apps.api.app.main",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "pyexpat",
    "--hidden-import", "_elementtree",
    "--hidden-import", "xml.parsers.expat",
    "--hidden-import", "xml.etree.ElementTree",
    "--hidden-import", "xml.etree.cElementTree",
    "--collect-submodules", "xml.parsers",
    "--collect-all", "uvicorn",
    "--collect-all", "starlette",
    "--collect-all", "jinja2",
    "--collect-all", "openpyxl",
    "--collect-all", "docx",
    "--exclude-module", "pytest",
    "--exclude-module", "pandas.tests",
    "--exclude-module", "numpy.tests",
    "--exclude-module", "matplotlib",
    "--exclude-module", "PyQt5",
    "--exclude-module", "pyarrow",
    "--exclude-module", "sqlalchemy",
    "--exclude-module", "numba",
    "--exclude-module", "pkg_resources",
    "scripts\portable_server.py"
)

& $pyinstaller.Source @args
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$built = Join-Path $distRoot "CableTrayAI_Server"
if (-not (Test-Path (Join-Path $built "CableTrayAI_Server.exe"))) {
    throw "Portable server executable was not created."
}

Copy-Item -Path $built -Destination $runtimeTarget -Recurse -Force

$internal = Join-Path $runtimeTarget "_internal"
foreach ($required in @("pyexpat.pyd", "_elementtree.pyd", "libexpat.dll")) {
    if (-not (Test-Path -LiteralPath (Join-Path $internal $required))) {
        throw "Portable runtime is missing XML support file: $required"
    }
}

$manifest = [ordered]@{
    status = "pass"
    runtime = "runtime\CableTrayAI_Server\CableTrayAI_Server.exe"
    pyinstaller = $pyinstaller.Source
    built_at = (Get-Date).ToString("s")
    note = "This executable bundles the web server runtime so deployment does not depend on unit-computer Python packages."
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Root "$RuntimeRoot\portable_runtime_manifest.json")

if (-not $KeepBuildArtifacts) {
    foreach ($path in @($distRoot, $buildRoot, $specRoot)) {
        if (Test-Path $path) {
            Remove-Item $path -Recurse -Force
        }
    }
}

Write-Host "Portable runtime created:"
Write-Host (Join-Path $runtimeTarget "CableTrayAI_Server.exe")
