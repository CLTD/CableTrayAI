$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "Running pytest..."
$PytestOutput = pytest -q 2>&1
$PytestOutput | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
    throw "pytest failed"
}

$CollectOutput = pytest --collect-only -q 2>&1
if ($LASTEXITCODE -ne 0) {
    $CollectOutput | ForEach-Object { Write-Host $_ }
    throw "pytest collection failed"
}

$Passed = 0
foreach ($Line in $CollectOutput) {
    if ($Line -match ":\s*(\d+)$") {
        $Passed += [int]$Matches[1]
    }
}
if ($Passed -lt 60) {
    throw "Stage 4 requires at least 60 collected tests; got $Passed"
}

Write-Host "Checking hardcoded sample tokens in core/apps/templates..."
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
if ($LASTEXITCODE -eq 0) {
    throw "Hardcoded sample tokens found in core/apps/templates"
}
if ($LASTEXITCODE -gt 1) {
    throw "rg hardcode scan failed"
}

Write-Host "Checking ANSYS candidate selector safety..."
$SelectorTemp = Join-Path ([System.IO.Path]::GetTempPath()) ("CableTrayAI-selector-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $SelectorTemp | Out-Null
$DiscoveryPath = Join-Path $SelectorTemp "ansys_discovery.json"
$ConfigPath = Join-Path $SelectorTemp "ansys.local.toml"
@{
    status = "multiple_candidates"
    candidate_count = 1
    candidates = @(
        @{
            executable = "D:/ANSYS Inc/v182/ansys/bin/winx64/ANSYS182.exe"
            source = "self_check"
            version_hint = "v182"
        }
    )
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $DiscoveryPath

powershell -ExecutionPolicy Bypass -File scripts\select_ansys_candidate.ps1 -Index 1 -DiscoveryPath $DiscoveryPath -ConfigPath $ConfigPath | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "ANSYS candidate selector failed"
}
if (-not (Test-Path $ConfigPath)) {
    throw "ANSYS candidate selector did not write config"
}
$SelectorConfig = Get-Content -Raw -Encoding UTF8 $ConfigPath
if ($SelectorConfig -notmatch 'mode = "real"') {
    throw "ANSYS candidate selector did not write real mode"
}
if ($SelectorConfig -notmatch 'output_import') {
    throw "ANSYS candidate selector did not write output_import config"
}

Write-Host "Stage 4 self-check passed with $Passed tests."

