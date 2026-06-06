param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [string]$ConfirmedBy = $env:USERNAME
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

@'
import json
import sys
from pathlib import Path
from core.spectra.config_wizard import confirm_spectrum_config

job_dir = Path("jobs") / sys.argv[1]
result = confirm_spectrum_config(job_dir, confirmed_by=sys.argv[2] or "operator")
print(json.dumps(result, ensure_ascii=False, indent=2))
'@ | python - $JobId $ConfirmedBy

