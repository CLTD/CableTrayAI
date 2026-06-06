param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [switch]$IUnderstandThisWillRunANSYS,

    [string]$ConfirmUser = $env:USERNAME
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$JobDir = Join-Path $Root "jobs\$JobId"
if (-not (Test-Path $JobDir)) {
    throw "Job directory not found: $JobDir"
}

$ConfirmFlag = if ($IUnderstandThisWillRunANSYS) { "true" } else { "false" }

@'
import json
import sys
from pathlib import Path

from core.ansys.config import load_ansys_config
from core.ansys.runner import run_real_ansys

job_dir = Path(sys.argv[1])
confirm = sys.argv[2].lower() == "true"
confirm_user = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else None
config_path = Path("config/ansys.local.toml")
config = load_ansys_config(config_path)
audit = run_real_ansys(
    job_dir,
    config=config,
    config_path=config_path,
    confirm_real_run=confirm,
    confirm_user=confirm_user,
)
print(json.dumps(audit, ensure_ascii=False, indent=2))
if audit.get("status") != "success":
    sys.exit(2)
'@ | python - $JobDir $ConfirmFlag $ConfirmUser

