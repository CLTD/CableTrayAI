from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _classify_failure(item: dict[str, Any]) -> str:
    metric_type = str(item.get("metric_type") or "")
    name = str(item.get("name") or "")
    baseline = item.get("baseline")
    absolute_error = item.get("absolute_error")
    if metric_type in {"missing_result_mapping", "mapping_scope"}:
        return "output_mapping_or_missing_lis"
    if metric_type == "foundation_load":
        return "support_reaction_load_or_jczh_extraction"
    if metric_type == "tray_arm_connection_load":
        return "tray_arm_connection_load_or_ls_force_extraction"
    if metric_type in {"beam_calculation_value", "weld_equivalent_stress_value"}:
        if isinstance(baseline, (int, float)) and abs(float(baseline)) < 0.5 and isinstance(absolute_error, (int, float)) and abs(float(absolute_error)) < 0.01:
            return "small_report_rounded_value"
        return "beam_result_value_mismatch"
    if metric_type == "evaluation_ratio":
        return "ratio_followed_from_result_or_allowable"
    if metric_type == "combination_ratio_value":
        return "combination_ratio_followed_from_component_ratios"
    if "foundation_loads" in name:
        return "support_reaction_load_or_jczh_extraction"
    return "unclassified_precision_failure"


def _material_allowable_check(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for row in baseline.get("evaluation_ratios", []) or []:
        component = row.get("component")
        stress_type = str(row.get("stress_type") or "")
        if "弯曲" not in stress_type:
            continue
        allowable = row.get("allowable_value")
        if component == "square_support":
            expected = 155.10 if row.get("case") != "事故" else None
            checks.append(
                {
                    "component": component,
                    "case": row.get("case"),
                    "stress_type": stress_type,
                    "allowable_value": allowable,
                    "expected_normal_upset_bending_allowable_mpa": 155.10,
                    "policy": "steel-platform square support uses Q235 bending allowable for conservative evaluation",
                    "status": "pass" if row.get("case") == "正常异常" and abs(float(allowable) - 155.10) < 1e-9 else "not_checked",
                }
            )
        elif component == "cantilever_arm":
            checks.append(
                {
                    "component": component,
                    "case": row.get("case"),
                    "stress_type": stress_type,
                    "allowable_value": allowable,
                    "expected_normal_upset_bending_allowable_mpa": 234.30,
                    "policy": "non-square support members use Q355 bending allowable",
                    "status": "pass" if row.get("case") == "正常异常" and abs(float(allowable) - 234.30) < 1e-9 else "not_checked",
                }
            )
    return checks


def diagnose_precision_case(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    comparison = _read_json(job_dir / "baseline_comparison.json")
    baseline = _read_json(job_dir / "baseline_from_report.json") if (job_dir / "baseline_from_report.json").exists() else {}
    source_map = _read_json(job_dir / "result_source_map.json") if (job_dir / "result_source_map.json").exists() else {}
    trace = _read_json(job_dir / "command_source_traceability.json") if (job_dir / "command_source_traceability.json").exists() else {}
    failures = [item for item in comparison.get("comparisons", []) if item.get("status") != "pass"]
    classified: list[dict[str, Any]] = []
    for item in failures:
        classified.append(
            {
                "name": item.get("name"),
                "metric_type": item.get("metric_type"),
                "result_source_file": item.get("result_source_file"),
                "value": item.get("value"),
                "baseline": item.get("baseline"),
                "gate_error": item.get("gate_error"),
                "absolute_error": item.get("absolute_error"),
                "classification": _classify_failure(item),
                "message": item.get("message"),
            }
        )
    by_class: dict[str, int] = {}
    for item in classified:
        key = str(item["classification"])
        by_class[key] = by_class.get(key, 0) + 1
    return {
        "job_dir": str(job_dir),
        "status": "pass" if not failures else "fail",
        "comparison_status": comparison.get("status"),
        "failure_count": len(failures),
        "max_gate_error": comparison.get("max_gate_error"),
        "failure_classes": by_class,
        "failures": classified,
        "material_allowable_checks": _material_allowable_check(baseline),
        "result_source_map_status": source_map.get("status"),
        "result_source_policy": source_map.get("policy"),
        "command_sources": trace.get("source_traces", []),
    }


def write_precision_diagnosis(
    job_dirs: list[Path | str],
    output_path: Path | str = Path("docs/CALIBRATION_4123_4225_DIAGNOSIS.md"),
) -> dict[str, Any]:
    cases = [diagnose_precision_case(path) for path in job_dirs]
    payload = {
        "status": "pass" if all(case["status"] == "pass" for case in cases) else "fail",
        "cases": cases,
        "policy": "Do not change report generation here. Diagnose command generation, result extraction, evaluation mapping, and material allowables only.",
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Calibration Diagnosis 4123 / 4225",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Material Policy",
        "",
        "- Intake column I / 埋件 is treated as the square steel section size, not an embedded plate design result.",
        "- If column I is blank in a first-pass intake, candidate square sections must target 0.60 <= controlling ratio <= 0.9999 within no more than two fresh ANSYS candidate trials; ratio > 1.0 still fails.",
        "- Non-steel-platform support members use Q355 bending allowable `234.30 MPa`.",
        "- Steel-platform square support uses Q235 bending allowable `155.10 MPa` conservatively because only the square steel contacts the steel platform.",
        "",
    ]
    for case in cases:
        lines.extend(
            [
                f"## {Path(case['job_dir']).name}",
                "",
                f"- Comparison status: `{case['comparison_status']}`",
                f"- Failure count: `{case['failure_count']}`",
                f"- Max gate error: `{case['max_gate_error']}`",
                f"- Failure classes: `{case['failure_classes']}`",
                "",
                "### Command Sources",
                "",
            ]
        )
        for source in case.get("command_sources", []):
            lines.append(f"- `{source.get('target')}` <= `{source.get('source')}`")
        lines.extend(["", "### Failures", ""])
        for failure in case["failures"][:20]:
            lines.append(
                f"- `{failure['name']}` class=`{failure['classification']}` source=`{failure.get('result_source_file')}` value={failure.get('value')} baseline={failure.get('baseline')} gate={failure.get('gate_error')}"
            )
        if not case["failures"]:
            lines.append("- None")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return payload
