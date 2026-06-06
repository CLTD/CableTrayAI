$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "Running pytest..."
pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed"
}

Write-Host "Checking hardcoded sample tokens in core/apps/templates..."
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
if ($LASTEXITCODE -eq 0) {
    throw "Hardcoded sample token found in core/apps/templates"
}
if ($LASTEXITCODE -gt 1) {
    throw "rg failed"
}

Write-Host "Stage 2 self-check passed."
