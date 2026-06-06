param(
    [double]$NprocPercent = 0.35,
    [string]$Memory = "4096"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$logical = [int]$cpu.NumberOfLogicalProcessors
if ($NprocPercent -le 0 -or $NprocPercent -gt 1) {
    throw "NprocPercent must be > 0 and <= 1. Example: -NprocPercent 0.35"
}
$effectiveNproc = [Math]::Max(1, [Math]::Floor($logical * $NprocPercent))

$configPath = "config\ansys.local.toml"
if (-not (Test-Path $configPath)) {
    throw "Missing config\ansys.local.toml. Run ANSYS discovery/selection first."
}

$text = Get-Content -Raw -Encoding UTF8 $configPath
if ($text -match '(?m)^nproc\s*=') {
    $text = [regex]::Replace($text, '(?m)^nproc\s*=.*\r?\n?', "")
}

if ($text -match '(?m)^nproc_percent\s*=') {
    $text = [regex]::Replace($text, '(?m)^nproc_percent\s*=.*$', "nproc_percent = $NprocPercent")
}
else {
    $text = [regex]::Replace($text, '(?m)^product\s*=.*$', "`$0`nnproc_percent = $NprocPercent")
}

if ($text -match '(?m)^memory\s*=') {
    $text = [regex]::Replace($text, '(?m)^memory\s*=.*$', "memory = `"$Memory`"")
}
else {
    $text = [regex]::Replace($text, '(?m)^nproc_percent\s*=.*$', "`$0`nmemory = `"$Memory`"")
}

Set-Content -Encoding UTF8 -Path $configPath -Value $text

$audit = [ordered]@{
    status = "pass"
    config_path = (Resolve-Path $configPath).Path
    cpu_name = $cpu.Name
    logical_processors = $logical
    nproc_percent = $NprocPercent
    effective_nproc_on_this_machine = $effectiveNproc
    memory = $Memory
    did_not_execute_ansys = $true
    note = "Only config/ansys.local.toml was updated. ANSYS was not executed. The command builder computes -np from nproc_percent on each machine."
}

$audit | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 docs\ansys_resource_tuning.json
$audit | ConvertTo-Json -Depth 4


