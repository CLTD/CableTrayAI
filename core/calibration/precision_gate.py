from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from core.calibration.legacy_release import DEFAULT_LEGACY_RELEASE, load_legacy_alignment, write_legacy_lessons_doc
from core.calibration.sample_inventory import prepare_calibration_workspaces
from core.evaluators.formula_registry import formula_source_audit


STRICT_TOLERANCE = 0.01
MIN_BASELINE_ABS = 1.0e-9

REQUIRED_REPORT_AREAS = {
    "support_stress_evaluation": ("bolt_stresses", "welds", "connection_loads"),
    "cantilever_root_loads": ("connection_loads",),
    "root_weld_evaluation": ("welds",),
    "foundation_loads": ("connection_loads",),
    "bolt_loads": ("connection_loads",),
    "bolt_stress_evaluation": ("bolt_stresses",),
    "modal_results": ("modal", "mode", "frequency"),
    "stress_figures": ("figure", "image", "stress"),
}


def _walk_numbers(payload: Any, *, path: str = "") -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            child = f"{path}.{key}" if path else str(key)
            values.extend(_walk_numbers(value, path=child))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            values.extend(_walk_numbers(value, path=f"{path}[{index}]"))
    elif isinstance(payload, (int, float)):
        values.append((path, float(payload)))
    return values


def _case_error_items(case: dict[str, Any], *, tolerance: float = STRICT_TOLERANCE) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for root_name in ("comparison", "xyz_validation", "comparison_after_report_alignment", "xyz_validation_after_report_alignment"):
        root = case.get(root_name)
        if not isinstance(root, dict):
            continue
        for path, value in _walk_numbers(root, path=root_name):
            lower = path.lower()
            if not lower.endswith(("abs_rel_error", "relative_error", "rel_error", "max_xyz_abs_rel_error")):
                continue
            if value > tolerance:
                items.append(
                    {
                        "case_id": str(case.get("case_id")),
                        "report_no": case.get("report_no"),
                        "template_key": case.get("template_key"),
                        "path": path,
                        "error": value,
                        "tolerance": tolerance,
                        "status": "fail",
                    }
                )
    return items


def _case_required_files(case: dict[str, Any]) -> list[dict[str, Any]]:
    workspace = Path(str(case.get("workspace") or ""))
    expected = ["01_build_model.PIP", "02_solve.mac", "03_extract.mac", "04_visualize.mac"]
    return [
        {
            "case_id": str(case.get("case_id")),
            "workspace": str(workspace),
            "file": name,
            "exists": (workspace / name).exists(),
            "status": "pass" if (workspace / name).exists() else "fail",
        }
        for name in expected
    ]


def _select_cases(cases: list[dict[str, Any]], count: int, *, seed: int) -> list[dict[str, Any]]:
    ordered = list(cases)
    rng = random.Random(seed)
    rng.shuffle(ordered)
    return ordered[: min(count, len(ordered))]


def evaluate_alignment_cases(
    cases: list[dict[str, Any]],
    *,
    tolerance: float = STRICT_TOLERANCE,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    file_checks: list[dict[str, Any]] = []
    for case in cases:
        failures.extend(_case_error_items(case, tolerance=tolerance))
        file_checks.extend(_case_required_files(case))
    missing_files = [item for item in file_checks if item["status"] == "fail"]
    status = "pass" if not failures and not missing_files and cases else "fail"
    return {
        "status": status,
        "case_count": len(cases),
        "tolerance": tolerance,
        "failure_count": len(failures),
        "missing_required_file_count": len(missing_files),
        "max_error": max((item["error"] for item in failures), default=0.0),
        "failures": sorted(failures, key=lambda item: item["error"], reverse=True),
        "required_file_checks": file_checks,
    }


def run_legacy_precision_gate(
    *,
    release_dir: Path | str = DEFAULT_LEGACY_RELEASE,
    output_dir: Path | str = Path("docs/precision_gate"),
    train_count: int = 15,
    validation_count: int = 20,
    seed: int = 20260515,
    tolerance: float = STRICT_TOLERANCE,
    prepare_workspaces: bool = True,
) -> dict[str, Any]:
    payload = load_legacy_alignment(release_dir)
    train_cases = list((payload.get("train") or {}).get("cases") or [])
    validation_cases = list((payload.get("validation") or {}).get("cases") or [])
    selected_train = _select_cases(train_cases, train_count, seed=seed)
    selected_validation = _select_cases(validation_cases, validation_count, seed=seed + 1)
    workspace_audit = None
    if prepare_workspaces:
        unique_by_report = {}
        for case in [*selected_train, *selected_validation]:
            unique_by_report[str(case.get("report_no"))] = case
        workspace_audit = prepare_calibration_workspaces(list(unique_by_report.values()))
        workspace_by_report = {
            item["report_no"]: item.get("workspace")
            for item in workspace_audit.get("prepared", [])
            if item.get("workspace")
        }
        for case in [*selected_train, *selected_validation]:
            workspace = workspace_by_report.get(str(case.get("report_no")))
            if workspace:
                case["workspace"] = workspace
    train_result = evaluate_alignment_cases(selected_train, tolerance=tolerance)
    validation_result = evaluate_alignment_cases(selected_validation, tolerance=tolerance)
    lessons = write_legacy_lessons_doc(release_dir=release_dir)
    formula_audit = formula_source_audit()
    result = {
        "status": "pass" if train_result["status"] == "pass" and validation_result["status"] == "pass" and formula_audit["status"] != "fail" else "fail",
        "tolerance": tolerance,
        "release_dir": str(release_dir),
        "seed": seed,
        "legacy_lessons": lessons,
        "training_sample_ids": [case.get("case_id") for case in selected_train],
        "validation_sample_ids": [case.get("case_id") for case in selected_validation],
        "training": train_result,
        "validation": validation_result,
        "formula_source_audit": formula_audit,
        "workspace_audit": workspace_audit,
        "required_report_areas": REQUIRED_REPORT_AREAS,
        "next_action": "Fix command generation/result extraction/evaluation until all failures are <= 1%; do not release UI as accurate while this gate fails.",
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "precision_gate_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(output_dir / "precision_gate_result.md", result)
    return result


def _write_markdown(path: Path, result: dict[str, Any]) -> None:
    lines = [
        "# 1% Precision Gate",
        "",
        f"Status: `{result['status']}`",
        f"Tolerance: `{result['tolerance']:.2%}`",
        f"Training sample IDs: {', '.join(map(str, result['training_sample_ids']))}",
        f"Validation sample IDs: {', '.join(map(str, result['validation_sample_ids']))}",
        "",
        "## Training",
        "",
        f"- Status: `{result['training']['status']}`",
        f"- Failures: {result['training']['failure_count']}",
        f"- Missing required files: {result['training']['missing_required_file_count']}",
        f"- Max error: {result['training']['max_error']:.6g}",
        "",
        "## Validation",
        "",
        f"- Status: `{result['validation']['status']}`",
        f"- Failures: {result['validation']['failure_count']}",
        f"- Missing required files: {result['validation']['missing_required_file_count']}",
        f"- Max error: {result['validation']['max_error']:.6g}",
        "",
        "## Formula Source Audit",
        "",
        f"- Status: `{result['formula_source_audit']['status']}`",
        f"- TODO formulas: {len(result['formula_source_audit']['todo_formulas'])}",
        f"- Blocking implemented formulas without source: {len(result['formula_source_audit']['blockers'])}",
        "",
        "## Worst Failures",
        "",
    ]
    worst = (result["training"]["failures"] + result["validation"]["failures"])[:30]
    for item in sorted(worst, key=lambda row: row["error"], reverse=True):
        lines.append(
            f"- case {item['case_id']} {item.get('report_no')} `{item['path']}` error={item['error']:.6g}"
        )
    lines.extend(["", "## Policy", "", result["next_action"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")
