$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

pytest -q
if ($LASTEXITCODE -ne 0) { throw "pytest failed" }

$Collect = pytest --collect-only -q
$Count = 0
foreach ($Line in $Collect) {
    if ($Line -match ":\s*(\d+)$") { $Count += [int]$Matches[1] }
}
if ($Count -lt 120) { throw "Production requires at least 120 collected tests; got $Count" }

rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
if ($LASTEXITCODE -eq 0) { throw "Hardcoded sample tokens found" }
if ($LASTEXITCODE -gt 1) { throw "rg scan failed" }

powershell -ExecutionPolicy Bypass -File scripts\stage4_prepare_real_run.ps1
if ($LASTEXITCODE -ne 0) { throw "stage4_prepare_real_run failed" }

Write-Host "Production final self-check passed with $Count tests."

