$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$LegacyRelease = "C:\Users\duxy\Desktop\tray_platform_onefile_release"

Set-Location $Root

@'
from core.calibration.sample_inventory import write_calibration_inventory
from core.calibration.precision_gate import run_legacy_precision_gate

inventory = write_calibration_inventory()
gate = run_legacy_precision_gate(release_dir=r"C:\Users\duxy\Desktop\tray_platform_onefile_release")

print("Calibration inventory:", inventory["status"], "ready", inventory["ready_case_count"], "/", inventory["case_count"])
print("1% precision gate:", gate["status"])
print("training failures:", gate["training"]["failure_count"], "validation failures:", gate["validation"]["failure_count"])
print("missing files:", gate["training"]["missing_required_file_count"] + gate["validation"]["missing_required_file_count"])
'@ | python -

