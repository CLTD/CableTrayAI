param(
    [string]$SourceDir = "outputs",

    [Parameter(Mandatory = $true)]
    [string]$JobId,

    [switch]$BuildReport,

    [switch]$NoParse
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$JobDir = Join-Path $Root "jobs\$JobId"
New-Item -ItemType Directory -Force -Path $JobDir | Out-Null

$ParseFlag = if ($NoParse) { "false" } else { "true" }
$ReportFlag = if ($BuildReport) { "true" } else { "false" }

@'
import json
import sys
from pathlib import Path

from core.results.real_output_importer import import_real_outputs

source_dir = Path(sys.argv[1])
job_dir = Path(sys.argv[2])
parse = sys.argv[3].lower() == "true"
build_report = sys.argv[4].lower() == "true"
manifest = import_real_outputs(source_dir, job_dir, parse=parse, build_report_doc=build_report)
print(json.dumps(manifest, ensure_ascii=False, indent=2))
if manifest.get("validation_status") != "pass":
    sys.exit(2)
'@ | python - $SourceDir $JobDir $ParseFlag $ReportFlag
