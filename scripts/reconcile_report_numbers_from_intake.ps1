param(
    [Parameter(Mandatory = $true)]
    [string]$JobsDir,

    [Parameter(Mandatory = $true)]
    [string]$IntakePath,

    [string]$OutputRoot = "outputs",

    [switch]$PublishResults,

    [switch]$DryRun,

    [switch]$NoOverwrite
)

$ErrorActionPreference = "Stop"

$dry = "False"
if ($DryRun) {
    $dry = "True"
}
$publish = "False"
if ($PublishResults) {
    $publish = "True"
}
$overwrite = "True"
if ($NoOverwrite) {
    $overwrite = "False"
}

@"
from core.intake.report_number_reconcile import reconcile_report_numbers_from_intake
payload = reconcile_report_numbers_from_intake(
    r'$JobsDir',
    r'$IntakePath',
    dry_run=$dry,
    output_root=r'$OutputRoot',
    publish_results=$publish,
    overwrite=$overwrite,
)
print("status:", payload["status"])
print("updated_count:", payload["updated_count"])
print("unchanged_count:", payload["unchanged_count"])
print("pending_count:", payload["pending_count"])
print("published_count:", payload["published_count"])
"@ | python -

