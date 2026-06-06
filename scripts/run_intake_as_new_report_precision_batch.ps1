param(
    [string]$IntakePath = "",
    [string]$SourceRoot = "source_materials/model_commands",
    [string]$SpectrumFile = "",
    [string[]]$ReportNumber = @(),
    [int]$Limit = 0,
    [int]$Nproc = 0,
    [int]$TimeoutMinutes = 120,
    [switch]$DryRunOnly,
    [switch]$NoPublish
)

$ErrorActionPreference = "Stop"

$kwargs = @(
    "source_root=r'$SourceRoot'",
    "nproc=$Nproc",
    "timeout_minutes=$TimeoutMinutes",
    "run_real=$((!$DryRunOnly).ToString())",
    "publish_outputs=$((!$NoPublish).ToString())"
)

if ($IntakePath) {
    $kwargs += "intake_path=r'$IntakePath'"
}
if ($SpectrumFile) {
    $kwargs += "spectrum_file=r'$SpectrumFile'"
}
if ($Limit -gt 0) {
    $kwargs += "limit=$Limit"
}
if ($ReportNumber.Count -gt 0) {
    $expandedReports = @()
    foreach ($item in $ReportNumber) {
        $expandedReports += ($item -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
    $quoted = ($expandedReports | ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }) -join ", "
    $kwargs += "report_numbers=[$quoted]"
}

$call = "run_intake_as_new_report_precision_batch(" + ($kwargs -join ", ") + ")"

@"
from core.calibration.intake_as_new_runner import run_intake_as_new_report_precision_batch
payload = $call
print("status:", payload["status"])
print("selected_case_count:", payload["selected_case_count"])
print("case_count:", payload["case_count"])
print("passed_case_count:", payload["passed_case_count"])
print("failed_case_count:", payload["failed_case_count"])
print("blocked_case_count:", payload["blocked_case_count"])
print("max_gate_error:", payload.get("max_gate_error"))
print("output: docs/precision_gate/intake_as_new_report_precision_batch.json")
"@ | python -
