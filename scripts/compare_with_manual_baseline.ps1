param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [string]$BaselinePath
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$BaselineArg = ""
if ($PSBoundParameters.ContainsKey("BaselinePath") -and $BaselinePath) {
    $BaselineArg = $BaselinePath
}

@'
import json
import sys
from pathlib import Path
from core.validation.manual_baseline import write_baseline_comparison

job_dir = Path("jobs") / sys.argv[1]
baseline = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
result = write_baseline_comparison(job_dir, baseline_path=baseline)
print(json.dumps(result, ensure_ascii=False, indent=2))
'@ | python - $JobId $BaselineArg

