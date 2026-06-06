param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [string]$SourceWorkbook
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

@'
import json
import sys
from pathlib import Path
from core.evaluators.excel_authoritative import run_excel_authoritative_evaluation

job_dir = Path("jobs") / sys.argv[1]
source = sys.argv[2] or None
result = run_excel_authoritative_evaluation(job_dir, source_workbook=source)
print(json.dumps(result, ensure_ascii=False, indent=2))
if result["status"] != "pass":
    sys.exit(2)
'@ | python - $JobId $SourceWorkbook

