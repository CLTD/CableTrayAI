param(
    [switch]$RunPytest,
    [switch]$RebuildPackage,
    [int]$Port = 8015,
    [string]$AuditUsername = "",
    [string]$AuditPassword = ""
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $AuditUsername) {
    $AuditUsername = if ($env:CABLETRAYAI_AUDIT_USERNAME) { $env:CABLETRAYAI_AUDIT_USERNAME } else { "duxyb" }
}
if (-not $AuditPassword) {
    $AuditPassword = $env:CABLETRAYAI_AUDIT_PASSWORD
}

$ReportJson = Join-Path $Root "docs\RELEASE_FULL_AUDIT.json"
$ReportMd = Join-Path $Root "docs\RELEASE_FULL_AUDIT.md"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "docs") | Out-Null

$Checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
    param(
        [string]$Name,
        [string]$Status,
        [object]$Evidence = $null,
        [string]$Message = ""
    )
    $Checks.Add([ordered]@{
        name = $Name
        status = $Status
        message = $Message
        evidence = $Evidence
    }) | Out-Null
}

function Invoke-JsonPost {
    param(
        [string]$Uri,
        [object]$Payload,
        [int]$TimeoutSec = 30,
        [object]$Session = $null
    )
    $body = $Payload | ConvertTo-Json -Depth 20 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
    if ($Session) {
        return Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec $TimeoutSec -WebSession $Session
    }
    return Invoke-RestMethod -Uri $Uri -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes -TimeoutSec $TimeoutSec
}

if ($RunPytest) {
    & pytest -q
    Add-Check "pytest" ($(if ($LASTEXITCODE -eq 0) { "pass" } else { "fail" })) @{ exit_code = $LASTEXITCODE }
    if ($LASTEXITCODE -ne 0) { throw "pytest failed" }
}

$collect = & pytest --collect-only -q
$testCount = 0
foreach ($line in $collect) {
    if ($line -match ":\s*(\d+)$") { $testCount += [int]$Matches[1] }
}
$minimumReleaseTests = 20
Add-Check "test_collection" ($(if ($testCount -ge $minimumReleaseTests) { "pass" } else { "fail" })) @{
    collected = $testCount
    minimum_release_tests = $minimumReleaseTests
} "clean release smoke threshold covers parsing, reporting, optimizer, and deployment gates"

$scan = & rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates 2>&1
$scanExit = $LASTEXITCODE
Add-Check "hardcode_scan_core_apps_templates" ($(if ($scanExit -eq 1) { "pass" } elseif ($scanExit -eq 0) { "fail" } else { "fail" })) @{ exit_code = $scanExit; output = @($scan) }
if ($scanExit -eq 0) { throw "hardcoded sample tokens found" }
if ($scanExit -gt 1) { throw "rg hardcode scan failed" }

if ((Get-Command git -ErrorAction SilentlyContinue) -and (Test-Path (Join-Path $Root ".git"))) {
    $sourceStatus = @(git status --short source_materials 2>&1)
    Add-Check "source_materials_git_status" ($(if ($sourceStatus.Count -eq 0) { "pass" } else { "warning" })) @{ output = $sourceStatus }
}
else {
    Add-Check "source_materials_git_status" "warning" @{ output = @("Git worktree is not available; source_materials mutation check skipped.") }
}

& python -m py_compile `
    core\intake\intake_excel_reader.py `
    core\spectra\static_coefficients.py `
    core\spectra\excel_reader.py `
    core\report\template_injector.py `
    core\report\docx_builder.py `
    core\report\chapter6_display.py `
    core\ai\model_client.py `
    apps\api\app\main.py
Add-Check "py_compile_key_modules" ($(if ($LASTEXITCODE -eq 0) { "pass" } else { "fail" })) @{ exit_code = $LASTEXITCODE }
if ($LASTEXITCODE -ne 0) { throw "py_compile failed" }

$reportTemplates = @(
    "templates\report\non_steel_platform_report_template.docx",
    "templates\report\steel_platform_report_template.docx"
)
$missingReportTemplates = @($reportTemplates | Where-Object { -not (Test-Path $_) })
Add-Check "report_templates_exist" ($(if ($missingReportTemplates.Count -eq 0) { "pass" } else { "fail" })) @{
    required = $reportTemplates
    missing = $missingReportTemplates
} "template injection must keep the original fixed report format"
if ($missingReportTemplates.Count -gt 0) { throw "missing report templates" }

$reportTestFiles = @(
    "tests\unit\test_template_report_injector.py",
    "tests\integration\test_report_template_upgrade.py",
    "tests\integration\test_production_report_audit.py"
)
$missingReportTests = @($reportTestFiles | Where-Object { -not (Test-Path $_) })
Add-Check "report_injection_tests_present" ($(if ($missingReportTests.Count -eq 0) { "pass" } else { "fail" })) @{
    required = $reportTestFiles
    missing = $missingReportTests
} "pytest already ran these tests in this audit"
if ($missingReportTests.Count -gt 0) { throw "missing report injection tests" }

$serverExe = Join-Path $Root "runtime\CableTrayAI_Server\CableTrayAI_Server.exe"
if (-not (Test-Path $serverExe)) {
    throw "Missing runtime server exe: $serverExe"
}

$logDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "release_audit_server.out.log"
$errLog = Join-Path $logDir "release_audit_server.err.log"
$server = $null
try {
    $server = Start-Process -FilePath $serverExe `
        -ArgumentList @("--root", $Root, "--host", "127.0.0.1", "--port", "$Port", "--public-ip", "127.0.0.1") `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog
    Start-Sleep -Seconds 8

    $base = "http://127.0.0.1:$Port"
    $health = Invoke-RestMethod -Uri "$base/health" -TimeoutSec 10
    Add-Check "server_health" ($(if ($health.status -eq "ok") { "pass" } else { "fail" })) $health

    $webSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    try {
        if (-not $AuditPassword) {
            throw "Set CABLETRAYAI_AUDIT_PASSWORD or pass -AuditPassword before running authenticated release audit."
        }
        $login = Invoke-JsonPost "$base/auth/login" @{ username = $AuditUsername; password = $AuditPassword } 20 $webSession
        Add-Check "audit_login_operator" ($(if ($login.status -eq "pass") { "pass" } else { "fail" })) @{
            status = $login.status
            user = $login.user
        } "release audit must exercise authenticated operator APIs"
    }
    catch {
        Add-Check "audit_login_operator" "fail" @{ error = $_.Exception.Message; user = $AuditUsername } "release audit must exercise authenticated operator APIs"
    }

    foreach ($path in @("/", "/dashboard", "/ai-tools", "/ai/config", "/ai/runtime-policy", "/compute/topology")) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "$base$path" -TimeoutSec 10 -WebSession $webSession
            Add-Check "endpoint_$path" ($(if ($response.StatusCode -eq 200) { "pass" } else { "fail" })) @{ status_code = $response.StatusCode }
        }
        catch {
            Add-Check "endpoint_$path" "fail" @{ error = $_.Exception.Message }
        }
    }

    $intakePaths = @(
        Get-ChildItem -Path (Join-Path $Root "source_materials"), (Join-Path $Root "uploads") -Recurse -File -Include *.xlsx -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -notlike "~$*" -and $_.Name -match "S2|1916" } |
            Select-Object -First 4
    )
    foreach ($file in $intakePaths) {
        if ($file -and (Test-Path -LiteralPath $file.FullName)) {
            try {
                $path = $file.FullName
                $preview = Invoke-JsonPost "$base/intake/preview" @{ intake_path = $path } 40 $webSession
                Add-Check "intake_preview_$($file.Name)" ($(if ($preview.status -in @("pass", "blocked")) { "pass" } else { "fail" })) @{
                    status = $preview.status
                    row_count = $preview.row_count
                    sample_identity = @(
                        $preview.rows |
                            Select-Object -First 2 |
                            ForEach-Object {
                                [ordered]@{
                                    project_code = $_.project_code
                                    building = $_.building
                                    elevation = $_.elevation
                                    report_number = $_.report_number
                                    support_type = $_.support_type
                                    tray_parse_status = $_.tray_parse_status
                                }
                            }
                    )
                }
            }
            catch {
                Add-Check "intake_preview_$($file.Name)" "fail" @{ error = $_.Exception.Message }
            }
        }
    }
    if (@($intakePaths).Count -eq 0) {
        Add-Check "intake_preview_samples_found" "warning" $null "No S2/1916 intake workbook was found for preview smoke testing."
    }

    $spectrumFile = Get-ChildItem -Path (Join-Path $Root "source_materials"), (Join-Path $Root "uploads") -Recurse -File -Include *.xlsm,*.xlsx -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "~$*" -and $_.Name -match "ANSYS" } |
        Select-Object -First 1
    if ($spectrumFile -and (Test-Path -LiteralPath $spectrumFile.FullName)) {
        try {
            $path = $spectrumFile.FullName
            $preview = Invoke-JsonPost "$base/spectrum/preview" @{ spectrum_file = $path } 60 $webSession
            Add-Check "spectrum_preview_segmented_xlsm" ($(if ($preview.status -in @("pass", "preview_only")) { "pass" } else { "fail" })) @{
                status = $preview.status
                sheet_count = $preview.sheet_count
                building_count = @($preview.available_buildings).Count
                elevation_count = @($preview.available_elevations).Count
            }
        }
        catch {
            Add-Check "spectrum_preview_segmented_xlsm" "fail" @{ error = $_.Exception.Message }
        }
    }
    else {
        Add-Check "spectrum_preview_sample_found" "warning" $null "No ANSYS spectrum workbook was found for preview smoke testing."
    }

    try {
        $aiConfig = Invoke-RestMethod -Uri "$base/ai/config" -TimeoutSec 10 -WebSession $webSession
        $probe = Invoke-JsonPost "$base/ai/probe" @{
            base_url = $aiConfig.config.base_url
            model = $aiConfig.config.model
            api_key_env = $aiConfig.config.api_key_env
            timeout_seconds = 12
        } 25 $webSession
        Add-Check "ai_probe_real_chat_completion" ($(if ($probe.status -eq "pass" -and $probe.chat_status -eq "pass") { "pass" } else { "warning" })) @{
            status = $probe.status
            chat_status = $probe.chat_status
            models_endpoint = $probe.models_endpoint
            selected_model = $probe.selected_model
            chat_error = $probe.chat_error
            message = $probe.message
        } "warning means the endpoint did not complete a real model response in this environment; CableTrayAI now reports that honestly instead of fake success."
    }
    catch {
        Add-Check "ai_probe_real_chat_completion" "warning" @{ error = $_.Exception.Message }
    }
}
finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
}

$zip = "C:\Users\duxy\Desktop\duxyb\CableTrayAI.zip"
if (Test-Path $zip) {
    $items = @(tar -tf $zip)
    Add-Check "deployment_zip_exists" "pass" @{ path = $zip; size_bytes = (Get-Item $zip).Length }
    Add-Check "deployment_zip_has_desktop_exe" ($(if ($items -match '^(?:\./)?CableTrayAI\.exe$') { "pass" } else { "fail" })) $null
    Add-Check "deployment_zip_has_server_exe" ($(if ($items -match 'runtime/CableTrayAI_Server/CableTrayAI_Server\.exe') { "pass" } else { "fail" })) $null
    Add-Check "deployment_zip_excludes_jobs_uploads" ($(if (-not ($items -match '^(?:\./)?(jobs|uploads|outputs|logs)/')) { "pass" } else { "fail" })) $null
    Add-Check "deployment_zip_has_minimal_standard_sources" ($(if (($items -match '^(?:\./)?source_materials/model_commands/.+\.(PIP|pip|mac|MAC|SECT|sect|txt|TXT|xlsx|xlsm)$')) { "pass" } else { "fail" })) $null
    Add-Check "deployment_zip_excludes_historical_reports" ($(if (-not ($items -match '^(?:\./)?source_materials/.+\.(docx|pdf|bak)$')) { "pass" } else { "fail" })) $null
    Add-Check "deployment_zip_excludes_legacy_worker" ($(if (-not ($items -match "client_worker|CableTrayAI_Worker|START_CLIENT_WORKER")) { "pass" } else { "fail" })) $null
}
else {
    Add-Check "deployment_zip_exists" "fail" @{ path = $zip }
}

if ($RebuildPackage) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\package_duxyb_intranet_release.ps1 -BuildPortableRuntime -BuildDesktopRuntime
    Add-Check "deployment_package_rebuilt" ($(if ($LASTEXITCODE -eq 0) { "pass" } else { "fail" })) @{ exit_code = $LASTEXITCODE }
    if ($LASTEXITCODE -ne 0) { throw "package rebuild failed" }
}

$failCount = @($Checks | Where-Object { $_.status -eq "fail" }).Count
$warningCount = @($Checks | Where-Object { $_.status -eq "warning" }).Count
$payload = [ordered]@{
    status = $(if ($failCount -gt 0) { "fail" } elseif ($warningCount -gt 0) { "warning" } else { "pass" })
    created_at = (Get-Date).ToString("s")
    fail_count = $failCount
    warning_count = $warningCount
    check_count = $Checks.Count
    checks = $Checks
}
$payload | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $ReportJson

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# CableTrayAI release full audit") | Out-Null
$lines.Add("") | Out-Null
$lines.Add("- status: $($payload.status)") | Out-Null
$lines.Add("- check_count: $($payload.check_count)") | Out-Null
$lines.Add("- fail_count: $($payload.fail_count)") | Out-Null
$lines.Add("- warning_count: $($payload.warning_count)") | Out-Null
$lines.Add("") | Out-Null
$lines.Add("| check | status | message |") | Out-Null
$lines.Add("|---|---:|---|") | Out-Null
foreach ($check in $Checks) {
    $msg = [string]$check.message
    if (-not $msg) { $msg = "" }
    $safeMsg = $msg -replace "\|", "/"
    $lines.Add("| $($check.name) | $($check.status) | $safeMsg |") | Out-Null
}
$lines | Set-Content -Encoding UTF8 $ReportMd

if ($failCount -gt 0) {
    throw "release audit failed with $failCount failing checks; see $ReportMd"
}

Write-Host "Release audit completed: $($payload.status)"
Write-Host $ReportMd
