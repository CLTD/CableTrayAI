param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [switch]$IUnderstandThisWillRunANSYS,
    [string]$ConfirmUser = $env:USERNAME
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $IUnderstandThisWillRunANSYS) {
    throw "Real ANSYS requires -IUnderstandThisWillRunANSYS."
}

powershell -ExecutionPolicy Bypass -File scripts\run_ansys_real_once.ps1 -JobId $JobId -IUnderstandThisWillRunANSYS -ConfirmUser $ConfirmUser

@'
import json
import sys
from pathlib import Path
from core.report.docx_builder import build_report
from core.results.result_assembler import assemble_result

job_dir = Path("jobs") / sys.argv[1]
audit = json.loads((job_dir / "ansys_run_audit.json").read_text(encoding="utf-8"))
if audit.get("status") == "success":
    assemble_result(job_dir)
    report_audit = build_report(job_dir)
    print(json.dumps({"result_file": "result.json", "report_audit": report_audit}, ensure_ascii=False, indent=2))
else:
    print(json.dumps({"status": "blocked", "ansys_run_audit": audit}, ensure_ascii=False, indent=2))
    sys.exit(2)
'@ | python - $JobId

