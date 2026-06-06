param(
    [switch]$ReportOnly,
    [switch]$Force,
    [switch]$AllowFallback,
    [string]$PreferredVersion = "182",
    [string]$ConfigPath = "config\ansys.local.toml",
    [string]$OutputRoot = "outputs"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$ForceFlag = if ($Force) { "true" } else { "false" }
$ReportOnlyFlag = if ($ReportOnly) { "true" } else { "false" }
$AllowFallbackFlag = if ($AllowFallback) { "true" } else { "false" }

@'
import json
import sys
from pathlib import Path

from core.ansys.candidate_selection import choose_preferred_candidate, is_preferred_version_candidate, write_selected_candidate_config
from core.ansys.discovery import discover_ansys, write_discovery_report

preferred_version = sys.argv[1]
config_path = Path(sys.argv[2])
force = sys.argv[3].lower() == "true"
report_only = sys.argv[4].lower() == "true"
output_root = sys.argv[5]
allow_fallback = sys.argv[6].lower() == "true"
project_root = Path.cwd()

payload = discover_ansys(project_root=project_root)
write_discovery_report(payload)

result = {
    "status": payload.get("status"),
    "candidate_count": payload.get("candidate_count", 0),
    "preferred_version": preferred_version,
    "did_not_execute_ansys": True,
    "discovery_path": "docs/ansys_discovery.json",
    "config_path": str(config_path),
}

if not report_only:
    candidates = list(payload.get("candidates", []))
    selected = choose_preferred_candidate(candidates, preferred_version=preferred_version)
    if selected and not is_preferred_version_candidate(selected, preferred_version) and not allow_fallback:
        selected = None
    if selected:
        selected_index = candidates.index(selected) + 1
        try:
            selection = write_selected_candidate_config(
                selected,
                index=selected_index,
                config_path=config_path,
                force=force,
                project_root=project_root,
                output_dir=output_root,
                mode="real",
            )
            result.update(
                {
                    "status": "config_written",
                    "selected_index": selected_index,
                    "selected_executable": selection.executable,
                    "selected_version": selection.version,
                    "runner_mode": "real",
                }
            )
        except FileExistsError:
            result.update(
                {
                    "status": "existing_config_preserved",
                    "message": f"{config_path} exists. Re-run with -Force to overwrite.",
                }
            )
    else:
        result.update({"status": "preferred_version_not_found", "message": f"ANSYS {preferred_version} / v{preferred_version} Mechanical APDL was not found. Discovery did not execute ANSYS."})
        print(json.dumps({"discovery": payload, "auto_config": result}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

print(json.dumps({"discovery": payload, "auto_config": result}, ensure_ascii=False, indent=2))
'@ | python - $PreferredVersion $ConfigPath $ForceFlag $ReportOnlyFlag $OutputRoot $AllowFallbackFlag

Write-Host ""
Write-Host "ANSYS discovery completed. ANSYS was not executed."
Write-Host "Discovery report: docs\ansys_discovery.json"
if (-not $ReportOnly) {
    Write-Host "Auto-selection prefers ANSYS $PreferredVersion and writes $ConfigPath when possible."
    Write-Host "Use -Force to overwrite an existing local config."
}
