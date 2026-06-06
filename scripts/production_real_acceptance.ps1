param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [string]$BaselinePath
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

@'
import json
import sys
from pathlib import Path
from core.validation.manual_baseline import write_baseline_comparison
from core.validation.production_gate import production_status

job_dir = Path("jobs") / sys.argv[1]
baseline = sys.argv[2] or None
if baseline:
    write_baseline_comparison(job_dir, baseline_path=baseline)
status = production_status(job_dir)
print(json.dumps(status, ensure_ascii=False, indent=2))
if status["status"] != "pass":
    sys.exit(2)
'@ | python - $JobId $BaselinePath

