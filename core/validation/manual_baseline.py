from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_TOLERANCES = {
    "modal_frequency_rel": 0.05,
    "stress_rel": 0.05,
    "load_rel": 0.05,
    "ratio_abs": 0.03,
    "ratio_rel": 0.05,
}


def relative_error(value: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if value == 0 else float("inf")
    return abs(value - baseline) / abs(baseline)


def compare_scalar(name: str, value: float, baseline: float, tolerance: float) -> dict[str, Any]:
    error = relative_error(value, baseline)
    return {
        "name": name,
        "value": value,
        "baseline": baseline,
        "relative_error": error,
        "tolerance": tolerance,
        "status": "pass" if error <= tolerance else "fail",
    }


def compare_modal_frequencies(result: dict, baseline: dict, tolerance: float = DEFAULT_TOLERANCES["modal_frequency_rel"]) -> list[dict]:
    result_modes = {int(item["mode"]): float(item["frequency_hz"]) for item in result.get("modal_results", [])}
    baseline_modes = {int(item["mode"]): float(item["frequency_hz"]) for item in baseline.get("modal_results", [])}
    return [
        compare_scalar(f"mode_{mode}_frequency", result_modes[mode], baseline_modes[mode], tolerance)
        for mode in sorted(result_modes.keys() & baseline_modes.keys())
    ]


def compare_baseline(result: dict, baseline: dict | None, *, tolerances: dict | None = None) -> dict[str, Any]:
    if not baseline:
        return {
            "status": "blocked",
            "precision_verified": False,
            "message": "No manual baseline was provided; precision is awaiting baseline validation.",
            "comparisons": [],
        }
    tolerances = {**DEFAULT_TOLERANCES, **(tolerances or {})}
    comparisons = compare_modal_frequencies(result, baseline, tolerances["modal_frequency_rel"])
    status = "pass" if comparisons and all(item["status"] == "pass" for item in comparisons) else "fail"
    return {"status": status, "precision_verified": status == "pass", "comparisons": comparisons, "tolerances": tolerances}


def write_baseline_comparison(job_dir: Path | str, baseline_path: Path | str | None = None) -> dict[str, Any]:
    job_dir = Path(job_dir)
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    if baseline_path and Path(baseline_path).suffix.lower() == ".docx":
        from core.validation.report_baseline import write_report_baseline_comparison

        return write_report_baseline_comparison(job_dir, baseline_path, tolerance=0.01)
    baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8")) if baseline_path else None
    comparison = compare_baseline(result, baseline)
    (job_dir / "baseline_comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Baseline Comparison", "", f"Status: {comparison['status']}", f"Precision verified: {comparison['precision_verified']}"]
    if comparison["status"] == "blocked":
        lines.append(comparison["message"])
    for item in comparison.get("comparisons", []):
        lines.append(f"- {item['name']}: {item['status']} rel_error={item['relative_error']:.6g}")
    (job_dir / "baseline_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (job_dir / "precision_acceptance_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return comparison
