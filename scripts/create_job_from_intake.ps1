param(
    [Parameter(Mandatory = $true)]
    [string]$IntakePath,

    [string]$JobId,
    [string]$SpectrumFile,
    [switch]$SpectrumConfigConfirmed
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

@'
import json
import sys
from core.intake.job_input_builder import create_job_from_intake

intake_path = sys.argv[1]
job_id = sys.argv[2] or None
spectrum_file = sys.argv[3] or None
confirmed = sys.argv[4].lower() == "true"
result = create_job_from_intake(intake_path, job_id=job_id, spectrum_file=spectrum_file, spectrum_confirmed=confirmed)
print(json.dumps({"job_id": result["job_id"], "job_dir": result["job_dir"], "audit": result["audit"]}, ensure_ascii=False, indent=2))
'@ | python - $IntakePath $JobId $SpectrumFile $SpectrumConfigConfirmed.IsPresent

