$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$distRoot = Join-Path $Root "_pyinstaller_desktop_dist"
$buildRoot = Join-Path $Root "_pyinstaller_desktop_build"
$specRoot = Join-Path $Root "_pyinstaller_desktop_spec"
$runtimeTarget = Join-Path $Root "runtime\CableTrayAI_Desktop"

Remove-Item $distRoot, $buildRoot, $specRoot, $runtimeTarget -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $distRoot, $buildRoot, $specRoot, $runtimeTarget | Out-Null

$args = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name", "CableTrayAI",
    "--distpath", $distRoot,
    "--workpath", $buildRoot,
    "--specpath", $specRoot,
    "scripts\desktop_launcher.py"
)

pyinstaller @args
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller desktop launcher build failed with exit code $LASTEXITCODE"
}

$exe = Join-Path $distRoot "CableTrayAI.exe"
if (-not (Test-Path $exe)) {
    throw "CableTrayAI.exe was not created."
}

Copy-Item -Path $exe -Destination (Join-Path $runtimeTarget "CableTrayAI.exe") -Force

$manifest = [ordered]@{
    status = "pass"
    runtime = "runtime\CableTrayAI_Desktop\CableTrayAI.exe"
    mode = "local_desktop_app"
    note = "Desktop launcher discovers local ANSYS, lets the user select a local output folder, starts the local web service, and opens http://127.0.0.1:8000/."
    created_at = (Get-Date).ToString("s")
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Root "runtime\desktop_runtime_manifest.json")

Write-Host "Desktop runtime created:"
Write-Host (Join-Path $runtimeTarget "CableTrayAI.exe")
