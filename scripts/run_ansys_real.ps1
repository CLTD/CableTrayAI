$ErrorActionPreference = "Stop"

param(
    [string]$JobDir = "jobs/s2_dry_run_sample"
)

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "Real ANSYS run is gated by config/ansys.local.toml runner.mode=real and preflight pass."
$env:JOB_DIR = $JobDir
@'
from pathlib import Path
import os
from core.ansys.config import load_ansys_config
from core.ansys.runner import run_real_ansys

job_dir = Path(os.environ["JOB_DIR"])
config = load_ansys_config("config/ansys.local.toml")
audit = run_real_ansys(job_dir, config=config)
print(audit)
'@ | python -
