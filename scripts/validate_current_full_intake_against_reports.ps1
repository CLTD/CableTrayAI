param(
    [Parameter(Mandatory = $true)]
    [string]$JobsRoot,
    [string]$SourceRoot = "source_materials/model_commands",
    [double]$Tolerance = 0.01
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path $JobsRoot)) {
    throw "JobsRoot not found: $JobsRoot"
}

$RunName = Split-Path -Leaf (Resolve-Path $JobsRoot).Path
$OutDir = Join-Path "docs\production_runs" $RunName
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$env:CABLETRAY_VALIDATE_JOBS_ROOT = (Resolve-Path $JobsRoot).Path
$env:CABLETRAY_VALIDATE_SOURCE_ROOT = $SourceRoot
$env:CABLETRAY_VALIDATE_TOLERANCE = "$Tolerance"
$env:CABLETRAY_VALIDATE_OUTPUT_JSON = (Join-Path $OutDir "report_validation.json")
$env:CABLETRAY_VALIDATE_OUTPUT_MD = (Join-Path $OutDir "report_validation.md")

@'
from pathlib import Path
import json
import os
import sys
import traceback

from core.calibration.sample_inventory import discover_report_command_cases
from core.calibration.report_intake_matcher import select_representative_intake_rows
from core.validation.report_baseline import write_report_baseline_comparison

jobs_root = Path(os.environ["CABLETRAY_VALIDATE_JOBS_ROOT"])
source_root = Path(os.environ["CABLETRAY_VALIDATE_SOURCE_ROOT"])
tolerance = float(os.environ["CABLETRAY_VALIDATE_TOLERANCE"])
output_json = Path(os.environ["CABLETRAY_VALIDATE_OUTPUT_JSON"])
output_md = Path(os.environ["CABLETRAY_VALIDATE_OUTPUT_MD"])
selection_json = output_json.with_name("representative_intake_selection.json")

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))

def row_from_job(job, payload):
    metadata = payload.get("metadata") or {}
    support = payload.get("support") or {}
    project = payload.get("project") or {}
    return {
        "job_dir": str(job),
        "report_number": metadata.get("report_number") or metadata.get("calculation_batch") or metadata.get("intake_order_id") or job.name,
        "calculation_batch": metadata.get("calculation_batch"),
        "intake_order_id": metadata.get("intake_order_id"),
        "intake_row_number": metadata.get("intake_row_number"),
        "intake_serial": (metadata.get("raw_intake_row") or {}).get("序号") or metadata.get("intake_row_number"),
        "support_height_m": support.get("support_height_m"),
        "support_spacing_m": support.get("support_spacing_m"),
        "building": project.get("building"),
        "elevation": project.get("elevation"),
        "elevation_candidates": metadata.get("elevation_candidates"),
        "square_section_spec": metadata.get("square_section_spec") or metadata.get("square_section_selected") or (payload.get("sections") or [{}])[0].get("sect_file"),
        "description": metadata.get("tray_load_description") or project.get("description"),
        "analysis_method": metadata.get("analysis_method"),
        "source_policy": "Input-side facts from job input.json only; no result values are used for selecting the baseline row.",
    }

jobs_by_report = {}
selection_rows = []
for job in sorted((path for path in jobs_root.iterdir() if path.is_dir() and not path.name.startswith("_")), key=lambda p: p.stat().st_mtime):
    input_path = job / "input.json"
    result_path = job / "result.json"
    if not input_path.exists() or not result_path.exists():
        continue
    try:
        payload = read_json(input_path)
        metadata = payload.get("metadata") or {}
        report_no = str(
            metadata.get("report_number")
            or metadata.get("calculation_batch")
            or metadata.get("intake_order_id")
            or job.name
        ).strip()
    except Exception:
        continue
    selection_rows.append(row_from_job(job, payload))
    validation_status = None
    validation_path = job / "result_validation.json"
    if validation_path.exists():
        try:
            validation_status = read_json(validation_path).get("status")
        except Exception:
            validation_status = "invalid"
    jobs_by_report.setdefault(report_no, []).append(
        {
            "job_dir": str(job),
            "intake_row_number": (payload.get("metadata") or {}).get("intake_row_number"),
            "result_validation_status": validation_status,
            "mtime": job.stat().st_mtime,
        }
    )

cases = [case for case in discover_report_command_cases(source_root) if case.get("report_docx")]
reports_by_number = {str(case.get("report_no")): str(case.get("report_docx")) for case in cases if case.get("report_no")}
selection_audit = select_representative_intake_rows(selection_rows, reports_by_number)
selection_json.write_text(json.dumps(selection_audit, ensure_ascii=False, indent=2), encoding="utf-8")
selection_by_report = {str(item.get("report_no")): item for item in selection_audit.get("selected") or []}

results = []
for case in cases:
    report_no = str(case.get("report_no") or "").strip()
    report_docx = case.get("report_docx")
    if not report_docx:
        continue
    candidates = jobs_by_report.get(report_no) or []
    selected = None
    selection = selection_by_report.get(report_no)
    if candidates:
        if selection and selection.get("intake_row_number") is not None:
            same_row = [
                item
                for item in candidates
                if str(item.get("intake_row_number")) == str(selection.get("intake_row_number"))
            ]
            selected = same_row[0] if same_row else None
        if selected is None and len(candidates) == 1:
            selected = candidates[0]
    row = {
        "report_no": report_no,
        "baseline_report": report_docx,
        "selected_job": selected,
        "representative_selection": selection,
        "status": "blocked",
    }
    if selection and selection.get("selection_conflict_status") == "conflict":
        row.update(
            {
                "status": "baseline_conflict",
                "precision_verified": False,
                "failure_reason": selection.get("selection_conflict_reason"),
                "failed_required_checks": selection.get("failed_required_checks"),
            }
        )
        results.append(row)
        continue
    if not selected:
        row["failure_reason"] = "No unambiguous result.json for this report number and representative intake row in the specified JobsRoot."
        results.append(row)
        continue
    if selected.get("result_validation_status") != "pass":
        row.update(
            {
                "status": "fail",
                "failure_reason": "Selected computation did not pass result_validity_gate; baseline comparison is blocked until extraction is valid.",
                "result_validation_status": selected.get("result_validation_status"),
            }
        )
        results.append(row)
        continue
    try:
        comparison = write_report_baseline_comparison(Path(selected["job_dir"]), report_docx, tolerance=tolerance)
        failed_metrics = [
            {
                "name": item.get("name"),
                "metric_type": item.get("metric_type"),
                "value": item.get("value"),
                "baseline": item.get("baseline"),
                "relative_error": item.get("relative_error"),
                "absolute_error": item.get("absolute_error"),
                "gate_error": item.get("gate_error"),
                "status": item.get("status"),
                "result_source_file": item.get("result_source_file"),
                "table_caption": item.get("table_caption"),
                "message": item.get("message"),
            }
            for item in (comparison.get("comparisons") or [])
            if item.get("status") not in {"pass", "baseline_conflict"}
        ]
        comparison_status = comparison.get("status")
        if comparison_status == "pass" and int(comparison.get("baseline_conflict_count") or 0) > 0:
            comparison_status = "baseline_conflict"
        row.update(
            {
                "status": comparison_status,
                "precision_verified": comparison.get("precision_verified"),
                "comparison_count": len(comparison.get("comparisons") or []),
                "baseline_conflict_count": comparison.get("baseline_conflict_count"),
                "max_relative_error": comparison.get("max_relative_error"),
                "max_absolute_error": comparison.get("max_absolute_error"),
                "max_gate_error": comparison.get("max_gate_error"),
                "failed_metric_count": len(failed_metrics),
                "failed_metrics": failed_metrics[:30],
            }
        )
    except Exception as exc:
        row.update({"status": "error", "failure_reason": str(exc), "traceback": traceback.format_exc()[-2000:]})
    results.append(row)

summary = {
    "status": "pass" if results and all(row.get("status") in {"pass", "baseline_conflict"} for row in results) else "fail",
    "jobs_root": str(jobs_root),
    "source_root": str(source_root),
    "tolerance": tolerance,
    "policy": "Compare only the specified full-intake JobsRoot against historical reports after all computation attempts have finished. Select duplicate report-number rows by input-side design facts, never by numerical result closeness.",
    "representative_selection_json": str(selection_json),
    "report_case_count": len(results),
    "pass_count": len([row for row in results if row.get("status") == "pass"]),
    "fail_count": len([row for row in results if row.get("status") == "fail"]),
    "baseline_conflict_count": len([row for row in results if row.get("status") == "baseline_conflict"]),
    "blocked_count": len([row for row in results if row.get("status") == "blocked"]),
    "error_count": len([row for row in results if row.get("status") == "error"]),
    "max_gate_error": max((float(row["max_gate_error"]) for row in results if isinstance(row.get("max_gate_error"), (int, float))), default=None),
    "results": results,
}
output_json.parent.mkdir(parents=True, exist_ok=True)
output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    "# Full-Intake Report Validation",
    "",
    f"- status: `{summary['status']}`",
    f"- jobs_root: `{summary['jobs_root']}`",
    f"- report_case_count: {summary['report_case_count']}",
    f"- pass_count: {summary['pass_count']}",
    f"- fail_count: {summary['fail_count']}",
    f"- baseline_conflict_count: {summary['baseline_conflict_count']}",
    f"- blocked_count: {summary['blocked_count']}",
    f"- error_count: {summary['error_count']}",
    f"- max_gate_error: {summary['max_gate_error']}",
    f"- representative_selection_json: `{summary['representative_selection_json']}`",
    "",
    "## Non-Pass Cases",
    "",
]
for row in results:
    if row.get("status") == "pass":
        continue
    selected_job = (row.get("selected_job") or {}).get("job_dir")
    selected_row = (row.get("representative_selection") or {}).get("intake_row_number")
    lines.append(f"- `{row.get('report_no')}` status=`{row.get('status')}` intake_row=`{selected_row}` job=`{selected_job}` reason={row.get('failure_reason', '')}")
    for item in row.get("failed_metrics") or []:
        lines.append(
            f"  - `{item.get('name')}` type=`{item.get('metric_type')}` value={item.get('value')} baseline={item.get('baseline')} gate={item.get('gate_error')} source={item.get('result_source_file')}"
        )
output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

print(json.dumps({key: summary[key] for key in ("status", "report_case_count", "pass_count", "fail_count", "baseline_conflict_count", "blocked_count", "error_count", "max_gate_error")}, ensure_ascii=False, indent=2))
print(str(output_json))
'@ | python -
