param(
    [string]$IntakePath = "",
    [string]$SourceRoot = "source_materials/model_commands",
    [string]$SpectrumFile = "",
    [int]$Limit = 0,
    [string[]]$ReportNumber = @()
)

$ErrorActionPreference = "Stop"

$kwargs = @(
    "source_root=r'$SourceRoot'"
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

$call = "run_intake_as_new_precision_batch(" + ($kwargs -join ", ") + ")"

@"
from core.calibration.intake_as_new_runner import run_intake_as_new_precision_batch
payload = $call
print("status:", payload["status"])
print("selected_case_count:", payload["selected_case_count"])
print("ready_for_real_ansys_count:", payload["ready_for_real_ansys_count"])
print("blocked_case_count:", payload["blocked_case_count"])
print("output: docs/precision_gate/intake_as_new_precision_batch.json")
"@ | python -
