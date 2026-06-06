from __future__ import annotations

import json
from pathlib import Path
from collections import Counter
from typing import Any

from core.ansys.artifact_cleanup import cleanup_heavy_solver_artifacts
from core.ansys.config import load_ansys_config
from core.ansys.config import AnsysExecutableConfig, AnsysLocalConfig, AnsysRunnerConfig
from core.ansys.lock_cleanup import cleanup_stale_ansys_locks
from core.ansys.runner import run_real_ansys
from core.calibration.legacy_release import DEFAULT_LEGACY_RELEASE, load_legacy_alignment
from core.calibration.precision_gate import _select_cases
from core.calibration.sample_inventory import prepare_calibration_workspaces
from core.results.result_assembler import assemble_result
from core.validation.report_baseline import write_report_baseline_comparison
from core.validation.result_requirements import classify_job_requirements


def _find_report(report_no: str, source_root: Path) -> Path | None:
    matches = sorted(source_root.rglob(f"{report_no}.docx"))
    return matches[0] if matches else None


def selected_legacy_cases(
    *,
    dataset: str,
    release_dir: Path | str = DEFAULT_LEGACY_RELEASE,
    train_count: int = 15,
    validation_count: int = 20,
    seed: int = 20260515,
) -> list[dict[str, Any]]:
    payload = load_legacy_alignment(release_dir)
    if dataset == "train":
        return _select_cases(list((payload.get("train") or {}).get("cases") or []), train_count, seed=seed)
    if dataset == "validation":
        return _select_cases(list((payload.get("validation") or {}).get("cases") or []), validation_count, seed=seed + 1)
    if dataset == "both":
        return [
            *selected_legacy_cases(dataset="train", release_dir=release_dir, train_count=train_count, validation_count=validation_count, seed=seed),
            *selected_legacy_cases(dataset="validation", release_dir=release_dir, train_count=train_count, validation_count=validation_count, seed=seed),
        ]
    raise ValueError("dataset must be train, validation, or both")


def run_real_precision_batch(
    *,
    dataset: str = "train",
    limit: int | None = None,
    release_dir: Path | str = DEFAULT_LEGACY_RELEASE,
    jobs_root: Path | str = Path("jobs/calibration_workspaces"),
    source_root: Path | str = Path("source_materials/model_commands"),
    config_path: Path | str = Path("config/ansys.local.toml"),
    tolerance: float = 0.01,
    nproc: int = 1,
) -> dict[str, Any]:
    source_root = Path(source_root)
    cases = selected_legacy_cases(dataset=dataset, release_dir=release_dir)
    selected = list(cases)
    if limit is not None:
        selected = selected[:limit]
    report_counts = Counter(str(case.get("report_no")) for case in selected)
    selected_for_workspace: list[dict[str, Any]] = []
    for index, case in enumerate(selected, start=1):
        report_no = str(case.get("report_no") or "").strip()
        case_id = str(case.get("case_id") or index).strip()
        workspace_id = report_no
        if report_counts[report_no] > 1:
            workspace_id = f"{report_no}__case_{case_id}"
        selected_for_workspace.append({**case, "workspace_id": workspace_id})
    workspace_audit = prepare_calibration_workspaces(selected_for_workspace, jobs_root=jobs_root, source_root=source_root)
    loaded = load_ansys_config(config_path)
    config = AnsysLocalConfig(
        ansys=AnsysExecutableConfig(
            executable=loaded.ansys.executable,
            default_workdir=loaded.ansys.default_workdir,
            timeout_minutes=loaded.ansys.timeout_minutes,
            license_wait=loaded.ansys.license_wait,
            product=loaded.ansys.product,
            nproc=nproc,
            memory=loaded.ansys.memory,
            extra_args=loaded.ansys.extra_args,
        ),
        runner=AnsysRunnerConfig(mode="real"),
        output_import=loaded.output_import,
    )
    results: list[dict[str, Any]] = []
    for item in workspace_audit.get("prepared", []):
        report_no = item.get("report_no")
        job_dir = Path(str(item.get("workspace")))
        row: dict[str, Any] = {
            "report_no": report_no,
            "case_id": item.get("case_id"),
            "workspace_id": item.get("workspace_id"),
            "job_dir": str(job_dir),
            "workspace_status": item.get("status"),
        }
        if item.get("status") != "pass":
            row["status"] = "fail"
            row["failure_reason"] = item.get("reason") or item.get("render_status")
            results.append(row)
            continue
        try:
            lock_cleanup = cleanup_stale_ansys_locks(job_dir)
            row["lock_cleanup_status"] = lock_cleanup.get("status")
            ansys_audit = run_real_ansys(job_dir, config=config, config_path=config_path, confirm_real_run=True, confirm_user="precision_batch")
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
            report_path = _find_report(str(report_no), source_root)
            if not report_path:
                row["status"] = "fail"
                row["failure_reason"] = "baseline report docx not found"
                results.append(row)
                continue
            requirements = classify_job_requirements(job_dir, report_path)
            result = assemble_result(job_dir)
            row["classification"] = requirements.get("classification")
            row["analysis_method"] = requirements.get("analysis_method")
            row["required_figure_count"] = len(requirements.get("required_figures", []))
            comparison = write_report_baseline_comparison(job_dir, report_path, tolerance=tolerance)
            row["comparison_status"] = comparison.get("status")
            row["comparison_count"] = len(comparison.get("comparisons", []))
            row["max_relative_error"] = comparison.get("max_relative_error")
            row["max_absolute_error"] = comparison.get("max_absolute_error")
            row["max_gate_error"] = comparison.get("max_gate_error")
            row["modal_count"] = len(result.get("modal_results", []))
            row["beam_count"] = len(result.get("beam_stress_results", []))
            row["weld_count"] = len(result.get("weld_force_results", []))
            row["bolt_count"] = len(result.get("bolt_force_results", []))
            row["foundation_count"] = len(result.get("foundation_loads", []))
            row["status"] = "pass" if comparison.get("status") == "pass" else "fail"
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

    payload = {
        "status": "pass" if results and all(item.get("status") == "pass" for item in results) else "fail",
        "dataset": dataset,
        "limit": limit,
        "nproc": nproc,
        "case_count": len(results),
        "results": results,
        "policy": "All cases must run real ANSYS and compare against report tables within 1%.",
    }
    output_dir = Path("docs/precision_gate")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"real_precision_batch_{dataset}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
