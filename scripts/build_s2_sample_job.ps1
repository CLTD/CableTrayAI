$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

@'
from core.jobs.sample_job_builder import build_s2_dry_run_sample

result = build_s2_dry_run_sample()
print(result)
'@ | python -
