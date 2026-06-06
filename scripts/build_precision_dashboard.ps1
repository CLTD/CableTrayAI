$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$OutputRoot = Join-Path $Root "outputs"

Set-Location $Root

@"
from core.validation.precision_dashboard import write_precision_dashboard

payload = write_precision_dashboard(
    output_root=r"$OutputRoot",
    publish_outputs=True,
)
print("precision_dashboard_status", payload["status"])
print("case_count", payload["case_count"])
print("passed_case_count", payload["passed_case_count"])
print("failed_case_count", payload["failed_case_count"])
print("max_gate_error_percent", payload["max_gate_error_percent"])
"@ | python -

Write-Host ""
Write-Host "Precision dashboard data:"
Write-Host (Join-Path $Root "docs\precision_gate\precision_dashboard_data.json")
Write-Host ""
Write-Host "Published result root:"
Write-Host $OutputRoot

