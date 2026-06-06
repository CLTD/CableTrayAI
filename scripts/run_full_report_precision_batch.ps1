param(
    [int]$Nproc = 0,
    [int]$ResponseSpectrumNproc = 0,
    [int]$TimeoutMinutes = 30,
    [int]$Limit = 0,
    [string[]]$ReportNumbers = @(),
    [string]$JobsRoot = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$OutputRoot = Join-Path $Root "outputs"

Set-Location $Root

if ([string]::IsNullOrWhiteSpace($JobsRoot)) {
    $JobsRoot = "jobs/full_report_runs/$(Get-Date -Format 'yyyyMMdd_HHmmss')/full_report_workspaces"
}

$limitExpr = "None"
if ($Limit -gt 0) {
    $limitExpr = $Limit.ToString()
}
$reportNumbersExpr = "None"
$reportNumberItems = @()
foreach ($value in $ReportNumbers) {
    if ($null -eq $value) {
        continue
    }
    $reportNumberItems += ($value -split ",") | Where-Object { $_.Trim() } | ForEach-Object { $_.Trim() }
}
if ($reportNumberItems.Count -gt 0) {
    $items = $reportNumberItems | ForEach-Object { "'" + ($_.Replace("'", "\\'")) + "'" }
    $reportNumbersExpr = "[" + ($items -join ", ") + "]"
}

@"
from pathlib import Path

from core.calibration.full_report_runner import DEFAULT_FULL_REPORT_OUTPUT, run_full_report_precision_batch
from core.validation.precision_dashboard import write_precision_dashboard

result = run_full_report_precision_batch(
    jobs_root=Path(r"$JobsRoot"),
    nproc=$Nproc,
    response_spectrum_nproc=$ResponseSpectrumNproc,
    timeout_minutes=$TimeoutMinutes,
    limit=$limitExpr,
    report_numbers=$reportNumbersExpr,
    output_root=Path(r"$OutputRoot"),
)
print("full report batch:", result["status"], "cases", result["case_count"], "passed", result["passed_case_count"], "failed", result["failed_case_count"], "blocked", result["blocked_case_count"])
print("max_gate_error", result.get("max_gate_error"))
for item in result["results"]:
    print(item.get("report_no"), item.get("status"), item.get("ansys_status"), item.get("comparison_status"), item.get("failure_reason", ""))
if result.get("blocked_cases"):
    print("blocked source packages:")
    for item in result["blocked_cases"]:
        print(item.get("report_no"), item.get("failure_reason"))

dashboard = write_precision_dashboard(
    batch_paths=(DEFAULT_FULL_REPORT_OUTPUT,),
    output_root=Path(r"$OutputRoot"),
    publish_outputs=False,
)
print("dashboard:", dashboard["status"], "cases", dashboard["case_count"], "max_gate_error_percent", dashboard["max_gate_error_percent"])
"@ | python -

