param(
    [string]$OutputDir = "C:\Users\duxy\Desktop\duxyb-up"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$stage = Join-Path $OutputDir "CableTrayAI_startup_hotfix_$stamp"
$zip = Join-Path $OutputDir "CableTrayAI_startup_hotfix_$stamp.zip"

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
}

Get-ChildItem -Path $OutputDir -Filter "CableTrayAI_startup_hotfix_*.zip" -File -ErrorAction SilentlyContinue |
    Remove-Item -Force
Get-ChildItem -Path $OutputDir -Filter "CableTrayAI_startup_hotfix_*" -Directory -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force

New-Item -ItemType Directory -Force -Path $stage | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage "scripts") | Out-Null

foreach ($file in @("APPLY_STARTUP_FIX.cmd", "APPLY_STARTUP_FIX.ps1", "INSTALL_AND_START.ps1", "START_CABLETRAYAI.cmd", "README.md")) {
    if (Test-Path $file) {
        Copy-Item -Path $file -Destination (Join-Path $stage $file) -Force
    }
}

Get-ChildItem -Path $Root -Filter "*.cmd" -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        Copy-Item -Path $_.FullName -Destination (Join-Path $stage $_.Name) -Force
    }

foreach ($file in @("find_ansys.ps1", "select_ansys_candidate.ps1", "start_internal_server.ps1")) {
    Copy-Item -Path (Join-Path "scripts" $file) -Destination (Join-Path (Join-Path $stage "scripts") $file) -Force
}

$readme = @"
CableTrayAI startup hotfix

This is not a full redeployment package.

Usage on the deployed unit computer:
1. Extract this zip.
2. Double-click APPLY_STARTUP_FIX.cmd.
3. If Windows asks for administrator permission, click Yes.
4. Select the existing CableTrayAI deployment folder.
5. The hotfix only updates startup scripts and restarts the web service.

Preserved folders:
- source_materials
- jobs
- uploads
- outputs
- config

What this fixes:
- The service is started from the correct folder instead of system32.
- The startup scripts use ASCII-only PowerShell content to avoid encoding parse errors.
- The web service starts even when ANSYS 18.2 discovery only produces a warning.
- TCP port 8000 is allowed through Windows firewall when administrator permission is available.
- The installer performs a local http://127.0.0.1:8000 health check before reporting success.

If the browser still cannot open the main URL, check:
- docs\one_click_deploy_last_run.json
- logs\internal_server.log
- logs\internal_server.err.log
"@
$readme | Set-Content -Encoding UTF8 -Path (Join-Path $stage "STARTUP_HOTFIX_README.txt")

$manifest = [ordered]@{
    status = "pass"
    type = "startup_hotfix"
    created_at = (Get-Date).ToString("s")
    zip = $zip
    protected_paths_preserved = @("source_materials", "jobs", "uploads", "outputs", "config")
    included = @(
        "APPLY_STARTUP_FIX.cmd",
        "APPLY_STARTUP_FIX.ps1",
        "INSTALL_AND_START.ps1",
        "START_CABLETRAYAI.cmd",
        "scripts/find_ansys.ps1",
        "scripts/select_ansys_candidate.ps1",
        "scripts/start_internal_server.ps1"
    )
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $stage "hotfix_manifest.json")

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -Force

Write-Host "Startup hotfix package created:"
Write-Host $zip
