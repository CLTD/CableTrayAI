$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BundleDir = Join-Path $Root "_production_review"
$ZipPath = Join-Path $Root "production_final_review_bundle.zip"
if (Test-Path $BundleDir) { Remove-Item $BundleDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $BundleDir "docs") | Out-Null
Copy-Item docs\PRODUCTION_*.md -Destination (Join-Path $BundleDir "docs") -ErrorAction SilentlyContinue
Copy-Item docs\ANSYS_MASTER_MACRO_POLICY.md -Destination (Join-Path $BundleDir "docs") -ErrorAction SilentlyContinue
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $BundleDir "*") -DestinationPath $ZipPath -Force
Write-Host $ZipPath

