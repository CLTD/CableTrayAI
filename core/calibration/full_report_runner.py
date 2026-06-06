from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from core.ansys.artifact_cleanup import cleanup_heavy_solver_artifacts
from core.ansys.config import AnsysExecutableConfig, AnsysLocalConfig, AnsysRunnerConfig, load_ansys_config
from core.ansys.lock_cleanup import cleanup_stale_ansys_locks
from core.ansys.runner import run_real_ansys
from core.calibration.sample_inventory import discover_report_command_cases, prepare_calibration_workspaces
from core.results.output_workspace import DEFAULT_OUTPUT_ROOT, publish_result_outputs
from core.results.result_assembler import assemble_result
from core.validation.report_baseline import write_report_baseline_comparison
from core.validation.result_requirements import classify_job_requirements


DEFAULT_FULL_REPORT_JOBS_ROOT = Path("jobs/full_report_workspaces")
DEFAULT_FULL_REPORT_OUTPUT = Path("docs/precision_gate/full_report_precision_batch.json")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_dir(path: Path, *, expected_name: str) -> None:
    resolved = path.resolve()
    if resolved.name != expected_name:
        raise ValueError(f"Refusing to clean unexpected directory: {path}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _clean_output_root(path: Path) -> None:
    resolved = path.resolve()
    if resolved.anchor == str(resolved) or resolved.name.lower() not in {"outputs", "ansys output"}:
        raise ValueError(f"Refusing to clean unexpected output root: {path}")
    resolved.mkdir(parents=True, exist_ok=True)
    (resolved / ".cabletrayai_output_root").write_text("CableTrayAI managed output directory\n", encoding="utf-8")
    for child in resolved.iterdir():
        if child.name == ".cabletrayai_output_root":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _config_with_overrides(
    *,
    config_path: Path | str,
    nproc: int,
    timeout_minutes: int,
) -> AnsysLocalConfig:
    loaded = load_ansys_config(config_path)
    explicit_nproc = int(nproc) if int(nproc) > 0 else None
    return AnsysLocalConfig(
        ansys=AnsysExecutableConfig(
            executable=loaded.ansys.executable,
            default_workdir=loaded.ansys.default_workdir,
            timeout_minutes=timeout_minutes,
            license_wait=loaded.ansys.license_wait,
            product=loaded.ansys.product,
            nproc=explicit_nproc,
            nproc_percent=loaded.ansys.nproc_percent,
            memory=loaded.ansys.memory,
            extra_args=loaded.ansys.extra_args,
        ),
        runner=AnsysRunnerConfig(mode="real"),
        output_import=loaded.output_import,
    )


def run_full_report_precision_batch(
    *,
    jobs_root: Path | str = DEFAULT_FULL_REPORT_JOBS_ROOT,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    source_root: Path | str = Path("source_materials/model_commands"),
    config_path: Path | str = Path("config/ansys.local.toml"),
    tolerance: float = 0.01,
    nproc: int = 1,
    response_spectrum_nproc: int | None = 1,
    timeout_minutes: int = 30,
    clean: bool = True,
    limit: int | None = None,
    report_numbers: list[str] | None = None,
) -> dict[str, Any]:
    jobs_root = Path(jobs_root)
    output_root = Path(output_root)
    source_root = Path(source_root)
    if clean:
        _clean_dir(jobs_root, expected_name="full_report_workspaces")
        _clean_output_root(output_root)
    all_cases = discover_report_command_cases(source_root)
    requested_reports = {str(item).strip() for item in (report_numbers or []) if str(item).strip()}
    if requested_reports:
        all_cases = [case for case in all_cases if str(case.get("report_no") or "").strip() in requested_reports]
    ready_cases = [case for case in all_cases if case.get("has_required_sources")]
    blocked_cases = [
        {
            "report_no": case.get("report_no"),
            "status": "blocked",
            "failure_reason": "missing report docx/model command/solve command/extract command",
            "report_docx": case.get("report_docx"),
            "model_command": case.get("model_command"),
            "solve_command": case.get("solve_command"),
        }
        for case in all_cases
        if not case.get("has_required_sources")
    ]
    selected_cases = ready_cases[:limit] if limit is not None else ready_cases
    workspace_audit = prepare_calibration_workspaces(selected_cases, jobs_root=jobs_root, source_root=source_root)
    static_or_default_config = _config_with_overrides(config_path=config_path, nproc=nproc, timeout_minutes=timeout_minutes)
    results: list[dict[str, Any]] = []
    _write_json(
        DEFAULT_FULL_REPORT_OUTPUT,
        _summary_payload(
            all_cases=all_cases,
            selected_cases=selected_cases,
            blocked_cases=blocked_cases,
            results=results,
            nproc=nproc,
            response_spectrum_nproc=response_spectrum_nproc,
            tolerance=tolerance,
            in_progress=True,
        ),
    )
    for item in workspace_audit.get("prepared", []):
        report_no = str(item.get("report_no") or "").strip()
        job_dir = Path(str(item.get("workspace")))
        row: dict[str, Any] = {
            "report_no": report_no,
            "workspace_id": report_no,
            "job_dir": str(job_dir),
            "workspace_status": item.get("status"),
            "analysis_method": item.get("analysis_method"),
            "required_figure_count": item.get("required_figure_count"),
        }
        report_path = next((Path(str(case.get("report_docx"))) for case in selected_cases if case.get("report_no") == report_no), None)
        if item.get("status") != "pass":
            row["status"] = "fail"
            row["failure_reason"] = item.get("reason") or item.get("render_status")
            results.append(row)
            continue
        try:
            cleanup = cleanup_stale_ansys_locks(job_dir)
            row["lock_cleanup_status"] = cleanup.get("status")
            job_nproc = (
                response_spectrum_nproc
                if item.get("analysis_method") == "response_spectrum" and response_spectrum_nproc is not None
                else nproc
            )
            config = (
                _config_with_overrides(config_path=config_path, nproc=int(job_nproc), timeout_minutes=timeout_minutes)
                if job_nproc != nproc
                else static_or_default_config
            )
            row["ansys_nproc_request"] = job_nproc
            ansys_audit = run_real_ansys(
                job_dir,
                config=config,
                config_path=config_path,
                confirm_real_run=True,
                confirm_user="full_report_precision_batch",
            )
            row["ansys_status"] = ansys_audit.get("status")
            row["returncode"] = ansys_audit.get("returncode")
            if ansys_audit.get("status") != "success":
                row["status"] = "fail"
                row["failure_reason"] = f"ANSYS status {ansys_audit.get('status')}"
                artifact_cleanup = cleanup_heavy_solver_artifacts(job_dir)
                row["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
                row["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
                results.append(row)
                continue
            if report_path is None or not report_path.exists():
                row["status"] = "fail"
                row["failure_reason"] = "baseline report docx not found"
                results.append(row)
                continue
            requirements = classify_job_requirements(job_dir, report_path)
            result = assemble_result(job_dir)
            comparison = write_report_baseline_comparison(job_dir, report_path, tolerance=tolerance)
            publish = publish_result_outputs(job_dir, output_root=output_root, intake_order_id=report_no, overwrite=True)
            row.update(
                {
                    "classification": requirements.get("classification"),
                    "analysis_method": requirements.get("analysis_method"),
                    "required_figure_count": len(requirements.get("required_figures") or []),
                    "figure_count": len(result.get("figures") or []),
                    "comparison_status": comparison.get("status"),
                    "comparison_count": len(comparison.get("comparisons") or []),
                    "max_relative_error": comparison.get("max_relative_error"),
                    "max_absolute_error": comparison.get("max_absolute_error"),
                    "max_gate_error": comparison.get("max_gate_error"),
                    "modal_count": len(result.get("modal_results") or []),
                    "beam_count": len(result.get("beam_stress_results") or []),
                    "weld_count": len(result.get("weld_force_results") or []),
                    "bolt_count": len(result.get("bolt_force_results") or []),
                    "foundation_count": len(result.get("foundation_loads") or []),
                    "published_to": publish.get("target_dir"),
                    "status": "pass" if comparison.get("status") == "pass" else "fail",
                }
            )
            artifact_cleanup = cleanup_heavy_solver_artifacts(job_dir)
            row["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
            row["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
        except Exception as exc:
            artifact_cleanup = cleanup_heavy_solver_artifacts(job_dir)
            row["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
            row["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
            row["status"] = "fail"
            row["failure_reason"] = str(exc)
        results.append(row)
        _write_json(
            DEFAULT_FULL_REPORT_OUTPUT,
            _summary_payload(
                all_cases=all_cases,
                selected_cases=selected_cases,
                blocked_cases=blocked_cases,
                results=results,
                nproc=nproc,
                response_spectrum_nproc=response_spectrum_nproc,
                tolerance=tolerance,
                in_progress=True,
            ),
        )
    payload = _summary_payload(
        all_cases=all_cases,
        selected_cases=selected_cases,
        blocked_cases=blocked_cases,
        results=results,
        nproc=nproc,
        response_spectrum_nproc=response_spectrum_nproc,
        tolerance=tolerance,
        in_progress=False,
    )
    _write_json(DEFAULT_FULL_REPORT_OUTPUT, payload)
    _write_markdown(DEFAULT_FULL_REPORT_OUTPUT.with_suffix(".md"), payload)
    return payload


def _summary_payload(
    *,
    all_cases: list[dict[str, Any]],
    selected_cases: list[dict[str, Any]],
    blocked_cases: list[dict[str, Any]],
    results: list[dict[str, Any]],
    nproc: int,
    response_spectrum_nproc: int | None,
    tolerance: float,
    in_progress: bool,
) -> dict[str, Any]:
    failed = [row for row in results if row.get("status") != "pass"]
    max_gate_error = max(
        (
            float(row["max_gate_error"])
            for row in results
            if isinstance(row.get("max_gate_error"), (int, float))
        ),
        default=None,
    )
    return {
        "status": "running" if in_progress else ("pass" if results and not failed else "fail"),
        "dataset": "full_report",
        "policy": "Run every ready historical report command package with real ANSYS and compare against the matching report within 1%.",
        "tolerance": tolerance,
        "nproc": nproc,
        "response_spectrum_nproc": response_spectrum_nproc,
        "source_case_count": len(all_cases),
        "ready_case_count": len([case for case in all_cases if case.get("has_required_sources")]),
        "selected_case_count": len(selected_cases),
        "case_count": len(results),
        "passed_case_count": len(results) - len(failed),
        "failed_case_count": len(failed),
        "blocked_case_count": len(blocked_cases),
        "max_gate_error": max_gate_error,
        "results": results,
        "blocked_cases": blocked_cases,
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Full Report Precision Batch",
        "",
        f"- status: {payload.get('status')}",
        f"- source_case_count: {payload.get('source_case_count')}",
        f"- ready_case_count: {payload.get('ready_case_count')}",
        f"- case_count: {payload.get('case_count')}",
        f"- passed_case_count: {payload.get('passed_case_count')}",
        f"- failed_case_count: {payload.get('failed_case_count')}",
        f"- blocked_case_count: {payload.get('blocked_case_count')}",
        f"- max_gate_error: {payload.get('max_gate_error')}",
        "",
        "## Failed Or Blocked",
        "",
    ]
    for row in payload.get("results") or []:
        if row.get("status") != "pass":
            lines.append(f"- {row.get('report_no')}: {row.get('failure_reason') or row.get('comparison_status')}")
    for row in payload.get("blocked_cases") or []:
        lines.append(f"- {row.get('report_no')}: {row.get('failure_reason')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
