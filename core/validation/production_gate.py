from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def production_status(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    blockers: list[str] = []
    result_path = job_dir / "result.json"
    audit_path = job_dir / "ansys_run_audit.json"
    report_audit_path = job_dir / "report_audit.json"
    baseline_path = job_dir / "baseline_comparison.json"
    if not result_path.exists():
        blockers.append("result.json is missing")
        result = {}
    else:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    if not audit_path.exists():
        blockers.append("ansys_run_audit.json is missing")
        audit = {}
    else:
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("mode") in {"mock", "dry_run"}:
            blockers.append("Formal conclusion cannot be based on mock or dry_run")
        if audit.get("mode") == "real" and audit.get("executed") is not True:
            blockers.append("real run audit does not show executed=true")
    baseline = None
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline.get("precision_verified") is not True:
            blockers.append("1% baseline precision comparison has not passed")
    else:
        blockers.append("1% baseline precision comparison is missing")
    if report_audit_path.exists() and json.loads(report_audit_path.read_text(encoding="utf-8")).get("status") == "fail":
        blockers.append("report_audit.json exists and is failing")
    if any(item.get("formula_status") == "unconfirmed_todo" for item in result.get("evaluation_summary", [])):
        excel_path = job_dir / "excel_evaluation_results.json"
        excel_ok = excel_path.exists() and json.loads(excel_path.read_text(encoding="utf-8")).get("status") == "pass"
        baseline_ratio_ok = bool(
            baseline
            and baseline.get("precision_verified") is True
            and any(item.get("metric_type") == "evaluation_ratio" for item in baseline.get("comparisons", []))
        )
        if not excel_ok and not baseline_ratio_ok:
            blockers.append("Unconfirmed formulas require successful Excel authoritative evaluation")
    status = "pass" if not blockers else "blocked"
    payload = {"status": status, "blockers": blockers, "job_dir": str(job_dir)}
    (job_dir / "production_status.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
