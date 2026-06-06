$ErrorActionPreference = "Stop"

param(
    [string]$JobDir = "jobs/s2_dry_run_sample"
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$env:JOB_DIR = $JobDir
@'
from pathlib import Path
import os
from core.ansys.runner import run_ansys

job_dir = Path(os.environ.get("JOB_DIR", "jobs/s2_dry_run_sample"))
audit = run_ansys(job_dir, mode="dry_run")
print(audit)
'@ | python -
