$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

@'
import json
from pathlib import Path

from core.jobs.sample_job_builder import build_s2_dry_run_sample

result = build_s2_dry_run_sample(Path("."), job_id="s2_real_run_candidate")
print(json.dumps(result, ensure_ascii=False, indent=2))
'@ | python -

Write-Host ""
Write-Host "Prepared jobs\s2_real_run_candidate for controlled dry-run review."
Write-Host "Real execution still requires config\ansys.local.toml, clean preflight, and scripts\run_ansys_real_once.ps1 -IUnderstandThisWillRunANSYS."

