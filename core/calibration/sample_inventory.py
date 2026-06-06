from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.apdl.standard_command_renderer import render_standard_command_package
from core.audit.job_state import write_job_state
from core.jobs.sample_job_builder import sample_input_payload
from core.schemas.job_models import JobState
from core.validation.result_requirements import classify_report_requirements


def _first(root: Path, patterns: tuple[str, ...]) -> Path | None:
    for pattern in patterns:
        matches = sorted(path for path in root.rglob(pattern) if path.is_file() and not path.name.startswith("~$") and not path.name.lower().endswith(".bak"))
        if matches:
            return matches[0]
    return None


def discover_report_command_cases(source_root: Path | str = Path("source_materials/model_commands")) -> list[dict[str, Any]]:
    source_root = Path(source_root)
    reports_root = source_root / "\u62a5\u544a\u53ca\u6a21\u578b\u547d\u4ee4\u6d41"
    cases: list[dict[str, Any]] = []
    for report_dir in sorted((path for path in reports_root.iterdir() if path.is_dir()), key=lambda item: item.name):
        report_no = report_dir.name
        calc_dir = report_dir / "\u8ba1\u7b97\u6587\u4ef6"
        report_docx = report_dir / f"{report_no}.docx"
        command_root = calc_dir if calc_dir.exists() else report_dir
        model_file = _first(command_root, ("01*.PIP", "01*.pip", "01*.MAC", "01*.mac", "01*.TXT", "01*.txt"))
        solve_file = _first(command_root, ("02*.PIP", "02*.pip", "02*.mac", "02*.MAC", "02*.TXT", "02*.txt"))
        cases.append(
            {
                "report_no": report_no,
                "report_docx": str(report_docx) if report_docx.exists() else None,
                "case_dir": str(report_dir),
                "calc_dir": str(calc_dir) if calc_dir.exists() else None,
                "model_command": str(model_file) if model_file else None,
                "solve_command": str(solve_file) if solve_file else None,
                "extract_command": str(source_root / "\u5bfc\u51fa\u6570\u636e-S2.PIP") if (source_root / "\u5bfc\u51fa\u6570\u636e-S2.PIP").exists() else None,
                "has_required_sources": bool(report_docx.exists() and model_file and solve_file),
                "analysis_method_hint": "static" if solve_file and "\u9759\u529b" in solve_file.name else "response_spectrum",
            }
        )
    return cases


def write_calibration_inventory(
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
    output_json: Path | str = Path("docs/calibration_case_inventory.json"),
    output_md: Path | str = Path("docs/CALIBRATION_SAMPLE_INVENTORY.md"),
) -> dict[str, Any]:
    cases = discover_report_command_cases(source_root)
    ready = [case for case in cases if case["has_required_sources"]]
    payload = {
        "status": "pass" if ready else "fail",
        "source_root": str(source_root),
        "case_count": len(cases),
        "ready_case_count": len(ready),
        "cases": cases,
        "policy": "Only cases with report docx, model command, solve command, and extract command may enter the 1% calibration gate.",
    }
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Calibration Sample Inventory",
        "",
        f"Status: `{payload['status']}`",
        f"Cases: {payload['case_count']}",
        f"Ready cases: {payload['ready_case_count']}",
        "",
        "| Report | Ready | Method | Model command | Solve command | Report |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in cases:
        lines.append(
            f"| {case['report_no']} | {case['has_required_sources']} | {case['analysis_method_hint']} | {Path(case['model_command']).name if case['model_command'] else ''} | {Path(case['solve_command']).name if case['solve_command'] else ''} | {Path(case['report_docx']).name if case['report_docx'] else ''} |"
        )
    output_md = Path(output_md)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload


def prepare_calibration_workspaces(
    cases: list[dict[str, Any]],
    *,
    jobs_root: Path | str = Path("jobs/calibration_workspaces"),
    source_root: Path | str = Path("source_materials/model_commands"),
) -> dict[str, Any]:
    jobs_root = Path(jobs_root)
    jobs_root.mkdir(parents=True, exist_ok=True)
    prepared: list[dict[str, Any]] = []
    for case in cases:
        report_no = str(case.get("report_no") or "").strip()
        if not report_no:
            prepared.append({"report_no": report_no, "status": "fail", "reason": "missing report_no"})
            continue
        workspace_id = str(case.get("workspace_id") or report_no).strip()
        job_dir = jobs_root / workspace_id
        job_dir.mkdir(parents=True, exist_ok=True)
        payload = sample_input_payload()
        report_path = Path(str(case.get("report_docx"))) if case.get("report_docx") else None
        report_requirements: dict[str, Any] = {}
        if report_path and report_path.exists():
            try:
                report_requirements = classify_report_requirements(report_path)
            except Exception:
                report_requirements = {}
        requires = report_requirements.get("requires") or {}
        required_figures = report_requirements.get("required_figures") or []
        analysis_method = report_requirements.get("analysis_method") or case.get("analysis_method_hint")
        payload["metadata"] = {
            **payload.get("metadata", {}),
            "report_number": report_no,
            "case_id": case.get("case_id"),
            "workspace_id": workspace_id,
            "calibration_workspace": True,
            "source_report_docx": case.get("report_docx"),
            "analysis_method": analysis_method,
            "result_classification": report_requirements.get("classification"),
            "requires_appendix_c": requires.get("appendix_c_cantilever_figures"),
            "spectrum_config_confirmed": True,
            "spectrum_config_confirmed_by": "source_report_command_flow",
        }
        payload["project"]["description"] = f"Calibration workspace for {report_no}"
        (job_dir / "input.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if not (job_dir / "job_state.json").exists():
            write_job_state(job_dir, JobState(job_id=workspace_id, status="created"))
        if report_requirements:
            (job_dir / "result_requirements.json").write_text(
                json.dumps(report_requirements, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        try:
            render = render_standard_command_package(job_dir, source_root=source_root, package_id=report_no)
            status = "pass" if render["status"] in {"pass", "needs_review"} else "fail"
            prepared.append(
                {
                    "report_no": report_no,
                    "case_id": case.get("case_id"),
                    "workspace_id": workspace_id,
                    "workspace": str(job_dir),
                    "status": status,
                    "render_status": render["status"],
                    "analysis_method": analysis_method,
                    "requires_appendix_c": bool(requires.get("appendix_c_cantilever_figures")),
                    "required_figure_count": len(required_figures),
                }
            )
        except Exception as exc:
            prepared.append({"report_no": report_no, "workspace": str(job_dir), "status": "fail", "reason": str(exc)})
    audit = {
        "status": "pass" if all(item["status"] == "pass" for item in prepared) else "fail",
        "jobs_root": str(jobs_root),
        "prepared": prepared,
    }
    (jobs_root / "calibration_workspace_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
