param(
    [ValidateSet("train", "validation", "both")]
    [string]$Dataset = "train",
    [int]$Limit = 0,
    [int]$Nproc = 1
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$limitExpr = "None"
if ($Limit -gt 0) {
    $limitExpr = $Limit.ToString()
}

@"
from core.calibration.real_batch_runner import run_real_precision_batch
result = run_real_precision_batch(dataset="$Dataset", limit=$limitExpr, nproc=$Nproc)
print("real precision batch:", result["status"], "cases", result["case_count"])
for item in result["results"]:
    print(item.get("report_no"), item.get("status"), item.get("ansys_status"), item.get("comparison_status"), item.get("failure_reason", ""))
"@ | python -

