param(
    [int]$Index,
    [switch]$Interactive,
    [switch]$Force,
    [switch]$AllowFallback,
    [string]$PreferredVersion = "182",
    [string]$DiscoveryPath = "docs\ansys_discovery.json",
    [string]$ConfigPath = "config\ansys.local.toml",
    [string]$OutputRoot = "outputs"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path $DiscoveryPath)) {
    Write-Host "Discovery report not found. Running scripts\find_ansys.ps1 -ReportOnly first..."
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\find_ansys.ps1 -ReportOnly
}

$Discovery = Get-Content -Raw -Encoding UTF8 $DiscoveryPath | ConvertFrom-Json
$Candidates = @($Discovery.candidates)
if ($Candidates.Count -eq 0) {
    throw "No ANSYS candidates were found in $DiscoveryPath."
}

Write-Host "ANSYS executable candidates:"
for ($i = 0; $i -lt $Candidates.Count; $i++) {
    $Candidate = $Candidates[$i]
    $Number = $i + 1
    $Executable = [string]$Candidate.executable
    $Version = if ($Candidate.version_hint) { [string]$Candidate.version_hint } else { "" }
    $Source = if ($Candidate.source) { [string]$Candidate.source } else { "" }
    $Path = Split-Path -Parent $Executable
    Write-Host ("[{0}] version={1} source={2}" -f $Number, $Version, $Source)
    Write-Host ("    executable: {0}" -f $Executable)
    Write-Host ("    path:       {0}" -f $Path)
}

if (-not $PSBoundParameters.ContainsKey("Index") -or $Index -le 0) {
    if ($Interactive) {
        $RawIndex = Read-Host "Select ANSYS Mechanical APDL candidate index"
        if (-not [int]::TryParse($RawIndex, [ref]$Index)) {
            throw "Invalid candidate index: $RawIndex"
        }
    }
    else {
        $Index = 0
    }
}

$ForceFlag = if ($Force) { "true" } else { "false" }
$AllowFallbackFlag = if ($AllowFallback) { "true" } else { "false" }

@'
import json
import sys
from pathlib import Path

from core.ansys.candidate_selection import (
    choose_preferred_candidate,
    is_preferred_version_candidate,
    load_discovery_candidates,
    select_candidate,
    write_selected_candidate_config,
)

index = int(sys.argv[1])
preferred_version = sys.argv[2]
discovery_path = Path(sys.argv[3])
config_path = Path(sys.argv[4])
force = sys.argv[5].lower() == "true"
output_root = sys.argv[6]
allow_fallback = sys.argv[7].lower() == "true"
project_root = Path.cwd()

candidates = load_discovery_candidates(discovery_path)
if index <= 0:
    candidate = choose_preferred_candidate(candidates, preferred_version=preferred_version)
    if not candidate:
        raise SystemExit("No selectable ANSYS candidate found.")
    if not is_preferred_version_candidate(candidate, preferred_version) and not allow_fallback:
        raise SystemExit(f"ANSYS {preferred_version} / v{preferred_version} Mechanical APDL was not found. Re-run with -AllowFallback if another version is intentionally accepted.")
    index = candidates.index(candidate) + 1
else:
    candidate = select_candidate(candidates, index)

result = write_selected_candidate_config(
    candidate,
    index=index,
    config_path=config_path,
    force=force,
    project_root=project_root,
    output_dir=output_root,
    mode="real",
)
print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))
'@ | python - $Index $PreferredVersion $DiscoveryPath $ConfigPath $ForceFlag $OutputRoot $AllowFallbackFlag

Write-Host ""
Write-Host "Selected candidate was written to $ConfigPath."
Write-Host "runner.mode is real. ANSYS was not executed by this selection script."
