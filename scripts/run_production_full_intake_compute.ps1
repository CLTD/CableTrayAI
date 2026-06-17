param(
    [string]$IntakePath = "",
    [string]$SpectrumFile = "",
    [string]$OutputRoot = "outputs",
    [string]$JobsRoot = "",
    [string]$PreferredAnsysExe = "",
    [double]$NprocPercent = 0.35,
    [int]$TimeoutMinutes = 120,
    [int]$SquareSectionCandidateLimit = 0,
    [int]$Limit = 0,
    [int]$ModalModeCount = 0,
    [int[]]$SelectedRowNumbers = @(),
    [string]$SelectedRowNumbersCsv = "",
    [switch]$FreezeProvidedSquareSections
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Resolve-CableTrayPython {
    $candidates = @(
        $env:CABLETRAYAI_PYTHON,
        $env:CABLETRAYAI_PACKAGE_PYTHON,
        (Join-Path $Root ".venv\Scripts\python.exe"),
        "D:\miniconda3\python.exe",
        "python"
    ) | Where-Object { $_ -and $_.Trim() }

    foreach ($candidate in $candidates) {
        $resolved = $candidate
        if ($candidate -ne "python" -and -not (Test-Path $candidate)) {
            continue
        }
        try {
            & $resolved -c "import pydantic, openpyxl" *> $null
            if ($LASTEXITCODE -eq 0) {
                return $resolved
            }
        }
        catch {
            continue
        }
    }
    throw "No usable Python runtime found. Set CABLETRAYAI_PYTHON to a Python that can import pydantic and openpyxl."
}

$PythonExe = Resolve-CableTrayPython

if (-not $IntakePath) {
    $intakeCandidate = Get-ChildItem -Path "uploads\intake" -File -Filter "*.xlsx" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*S2*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $intakeCandidate) {
        $intakeCandidate = Get-ChildItem -Path "uploads\intake" -File -Filter "*.xlsx" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
    }
    if ($intakeCandidate) {
        $IntakePath = $intakeCandidate.FullName
    }
}

if (-not $SpectrumFile) {
    $spectrumCandidate = Get-ChildItem -Path "uploads\spectrum","source_materials\model_commands" -Recurse -File -Include "*.xlsm","*.xlsx" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "ANSYS" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($spectrumCandidate) {
        $SpectrumFile = $spectrumCandidate.FullName
    }
}

if (-not (Test-Path $IntakePath)) {
    throw "IntakePath not found: $IntakePath"
}
if (-not (Test-Path $SpectrumFile)) {
    throw "SpectrumFile not found: $SpectrumFile"
}
if (-not $JobsRoot) {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $JobsRoot = "jobs\production_full_intake_runs\$stamp"
}

New-Item -ItemType Directory -Force -Path "docs\production_runs" | Out-Null
New-Item -ItemType Directory -Force -Path $JobsRoot | Out-Null

if ($SelectedRowNumbersCsv) {
    $SelectedRowNumbers = @(
        $SelectedRowNumbersCsv -split "," |
            Where-Object { $_.Trim() } |
            ForEach-Object { [int]$_.Trim() }
    )
}

$RunName = Split-Path -Leaf (Resolve-Path $JobsRoot).Path
$RunDocDir = Join-Path "docs\production_runs" $RunName
New-Item -ItemType Directory -Force -Path $RunDocDir | Out-Null
$ProgressPath = Join-Path $RunDocDir "full_intake_compute_progress.jsonl"
$StatusPath = Join-Path $RunDocDir "full_intake_compute_status.json"
$ResultPath = Join-Path $RunDocDir "full_intake_compute_result.json"
$LatestProgressPath = "docs\production_runs\full_intake_compute_progress.jsonl"
$LatestStatusPath = "docs\production_runs\full_intake_compute_status.json"
$LatestResultPath = "docs\production_runs\full_intake_compute_result.json"
$LockPath = "docs\production_runs\full_intake_compute.lock.json"

if (Test-Path $LockPath) {
    $lock = $null
    try {
        $lock = Get-Content -Raw -Encoding UTF8 $LockPath | ConvertFrom-Json
    }
    catch {
        $lock = $null
    }
    $lockPid = if ($lock -and $lock.pid) { [int]$lock.pid } else { 0 }
    if ($lockPid -gt 0 -and (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) {
        throw "已有 CableTrayAI 计算正在运行，PID=$lockPid。请先在网页点击'停止当前计算'，或等待当前任务结束后再启动。"
    }
    Remove-Item $LockPath -Force -ErrorAction SilentlyContinue
}

@{
    pid = $PID
    run_name = $RunName
    jobs_root = $JobsRoot
    intake_path = (Resolve-Path $IntakePath).Path
    started_at = (Get-Date).ToString("s")
} | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $LockPath

Set-Content -Encoding UTF8 -Path $ProgressPath -Value ""
Set-Content -Encoding UTF8 -Path $LatestProgressPath -Value ""

if (Test-Path "config\ansys.local.toml") {
    $configText = Get-Content -Raw -Encoding UTF8 "config\ansys.local.toml"
    $configText = [regex]::Replace($configText, '(?m)^\s*timeout_minutes\s*=.*$', "timeout_minutes = $TimeoutMinutes")
    if ($configText -match '(?m)^\s*nproc_percent\s*=') {
        $configText = [regex]::Replace($configText, '(?m)^\s*nproc_percent\s*=.*$', "nproc_percent = $NprocPercent")
    }
    else {
        $configText = $configText -replace '(?m)^\[ansys\]\s*$', "[ansys]`r`nnproc_percent = $NprocPercent"
    }
    Set-Content -Encoding UTF8 -Path "config\ansys.local.toml" -Value $configText
}

$limitLiteral = if ($Limit -gt 0) { "$Limit" } else { "None" }
$squareLimitLiteral = if ($SquareSectionCandidateLimit -gt 0) { "$SquareSectionCandidateLimit" } else { "None" }
$selectedRowLiteral = if ($SelectedRowNumbers -and $SelectedRowNumbers.Count -gt 0) {
    "[" + (($SelectedRowNumbers | ForEach-Object { [int]$_ }) -join ", ") + "]"
} else {
    "None"
}
$env:CABLETRAY_FULL_INTAKE_PATH = (Resolve-Path $IntakePath).Path
$env:CABLETRAY_FULL_SPECTRUM_FILE = (Resolve-Path $SpectrumFile).Path
$env:CABLETRAY_FULL_OUTPUT_ROOT = $OutputRoot
$env:CABLETRAY_FULL_JOBS_ROOT = $JobsRoot
$env:CABLETRAY_FULL_PREFERRED_ANSYS = $PreferredAnsysExe
if ($ModalModeCount -gt 0) {
    $env:CABLETRAY_FULL_MODAL_MODE_COUNT = "$ModalModeCount"
}
else {
    Remove-Item Env:\CABLETRAY_FULL_MODAL_MODE_COUNT -ErrorAction SilentlyContinue
}
$env:CABLETRAY_FULL_FREEZE_PROVIDED_SQUARE_SECTIONS = if ($FreezeProvidedSquareSections) { "1" } else { "0" }
$env:CABLETRAY_FULL_PROGRESS_PATH = $ProgressPath
$env:CABLETRAY_FULL_STATUS_PATH = $StatusPath
$env:CABLETRAY_FULL_RESULT_PATH = $ResultPath
$env:CABLETRAY_FULL_LATEST_PROGRESS_PATH = $LatestProgressPath
$env:CABLETRAY_FULL_LATEST_STATUS_PATH = $LatestStatusPath
$env:CABLETRAY_FULL_LATEST_RESULT_PATH = $LatestResultPath

@"
from pathlib import Path
import json
from datetime import datetime
import os

from core.intake.intake_excel_reader import read_tabular_intake_rows
from core.pipeline.one_click import run_operator_one_click

intake = Path(os.environ["CABLETRAY_FULL_INTAKE_PATH"])
spectrum = Path(os.environ["CABLETRAY_FULL_SPECTRUM_FILE"])
jobs_root = Path(os.environ["CABLETRAY_FULL_JOBS_ROOT"])
progress_path = Path(os.environ["CABLETRAY_FULL_PROGRESS_PATH"])
status_path = Path(os.environ["CABLETRAY_FULL_STATUS_PATH"])
result_path = Path(os.environ["CABLETRAY_FULL_RESULT_PATH"])
latest_progress_path = Path(os.environ["CABLETRAY_FULL_LATEST_PROGRESS_PATH"])
latest_status_path = Path(os.environ["CABLETRAY_FULL_LATEST_STATUS_PATH"])
latest_result_path = Path(os.environ["CABLETRAY_FULL_LATEST_RESULT_PATH"])
progress_path.parent.mkdir(parents=True, exist_ok=True)
latest_progress_path.parent.mkdir(parents=True, exist_ok=True)
rows = read_tabular_intake_rows(intake)
modal_override_env = (os.environ.get("CABLETRAY_FULL_MODAL_MODE_COUNT") or "").strip()
modal_override = int(modal_override_env) if modal_override_env else None
row_overrides = []
if modal_override is not None:
    row_overrides = [
        {"intake_row_number": row.get("intake_row_number"), "modal_mode_count": modal_override}
        for row in rows
    ]

def write_status(payload):
    payload = dict(payload)
    payload["updated_at"] = datetime.now().isoformat(timespec="seconds")
    payload["run_name"] = jobs_root.name
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write_text(status_path, text)
    atomic_write_text(latest_status_path, text)

def atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

def progress(event):
    event = dict(event)
    event["time"] = datetime.now().isoformat(timespec="seconds")
    event["run_name"] = jobs_root.name
    event["no_report_validation_before_all_compute"] = True
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    with latest_progress_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    write_status({
        "status": "running",
        "stage": event.get("stage"),
        "message": event.get("message"),
        "progress": event.get("progress"),
        "job_id": event.get("job_id"),
        "intake_path": str(intake),
        "spectrum_file": str(spectrum),
        "jobs_root": str(jobs_root),
        "parsed_row_count": len(rows),
        "limit": $limitLiteral,
        "policy": "Compute all selected intake rows first. Do not inspect or compare baseline reports or historical command packages until all computation attempts finish.",
    })

write_status({
    "status": "starting",
    "intake_path": str(intake),
    "spectrum_file": str(spectrum),
    "jobs_root": str(jobs_root),
    "parsed_row_count": len(rows),
    "limit": $limitLiteral,
    "selected_row_numbers": $selectedRowLiteral,
    "modal_mode_count_override": modal_override,
    "freeze_provided_square_sections": os.environ.get("CABLETRAY_FULL_FREEZE_PROVIDED_SQUARE_SECTIONS") == "1",
    "no_report_validation_before_all_compute": True,
})

payload = run_operator_one_click(
    intake_path=intake,
    spectrum_file=spectrum,
    output_root=Path(os.environ["CABLETRAY_FULL_OUTPUT_ROOT"]),
    jobs_dir=jobs_root,
    execute_real=True,
    confirm_user="production_full_intake_compute",
    preferred_ansys_executable=os.environ.get("CABLETRAY_FULL_PREFERRED_ANSYS") or None,
    limit=$limitLiteral,
    selected_row_numbers=$selectedRowLiteral,
    row_overrides=row_overrides,
    square_section_candidate_limit=$squareLimitLiteral,
    freeze_provided_square_sections=os.environ.get("CABLETRAY_FULL_FREEZE_PROVIDED_SQUARE_SECTIONS") == "1",
    progress_callback=progress,
)

payload["no_report_validation_before_all_compute"] = True
payload["jobs_root"] = str(jobs_root)
payload["parsed_row_count"] = len(rows)
payload["modal_mode_count_override"] = modal_override
payload["freeze_provided_square_sections"] = os.environ.get("CABLETRAY_FULL_FREEZE_PROVIDED_SQUARE_SECTIONS") == "1"
payload["finished_at"] = datetime.now().isoformat(timespec="seconds")
result_text = json.dumps(payload, ensure_ascii=False, indent=2)
atomic_write_text(result_path, result_text)
atomic_write_text(latest_result_path, result_text)
write_status({
    "status": payload.get("status"),
    "job_count": payload.get("job_count"),
    "failed_count": len([item for item in payload.get("jobs", []) if item.get("status") == "fail"]),
    "passed_count": len([item for item in payload.get("jobs", []) if item.get("status") == "pass"]),
    "jobs_root": str(jobs_root),
    "result_file": str(result_path),
    "latest_result_file": str(latest_result_path),
    "no_report_validation_before_all_compute": True,
})
print(json.dumps({
    "status": payload.get("status"),
    "job_count": payload.get("job_count"),
    "jobs_root": str(jobs_root),
    "result_file": "docs/production_runs/full_intake_compute_result.json",
}, ensure_ascii=False, indent=2))
"@ | & $PythonExe -

$pythonExit = $LASTEXITCODE
Remove-Item $LockPath -Force -ErrorAction SilentlyContinue
if ($pythonExit -ne 0) {
    exit $pythonExit
}

