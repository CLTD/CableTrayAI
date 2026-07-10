from __future__ import annotations

import json
import math
import shutil
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from core.ansys.artifact_cleanup import cleanup_heavy_solver_artifacts
from core.ansys.auto_config import ensure_ansys_config
from core.ansys.lock_cleanup import cleanup_stale_ansys_locks
from core.ansys.runner import run_real_ansys
from core.apdl.modal_policy import (
    MODAL_RETRY_SEQUENCE,
    audited_source_modal_mode_count_from_job,
    modal_mode_count_from_job_dir,
    record_modal_mode_count_learning,
    rewrite_modal_mode_count,
)
from core.apdl.llm_orchestrated_renderer import render_llm_orchestrated_command_package
from core.apdl.intake_standard_family_renderer import find_adjacent_solve_command, select_standard_model_family
from core.audit.job_state import fail_job_state, update_job_state
from core.intake.job_input_builder import create_jobs_from_intake_workbook
from core.optimizer.square_section_workflow import (
    result_validation_needs_square_section_clean_reselection,
    result_validation_needs_final_ratio_section_recovery,
    result_validation_needs_square_section_upgrade,
    select_and_apply_square_section,
    square_section_auto_selection_required,
    upgrade_square_section_after_ratio_fail,
)
from core.pipeline.exact_result_cache import (
    copy_exact_cached_outputs,
    find_exact_cached_result,
    register_exact_cached_result,
)
from core.results.output_workspace import DEFAULT_OUTPUT_ROOT, publish_result_outputs
from core.results.result_assembler import assemble_result
from core.spectra.config_wizard import confirm_spectrum_config
from core.spectra.response_spectrum_writer import write_segmented_response_spectrum_mac

MODAL_RETRY_MAX_FORMAL_RERUNS = 4
AUTO_SUPPORT_GEOMETRY_RECOVERY_ENABLED = False
ANSYS_FORMAL_LICENSE_RETRY_DELAYS_SECONDS = (20, 45)
ANSYS_LICENSE_FAILURE_TOKENS = (
    "ansys license manager error",
    "ansys license not available",
    "ansysli exited",
    "could not read server port ansysli",
)


def _square_section_selection_failure_message(selection: dict[str, Any]) -> str:
    reason = str(selection.get("reason") or "未找到通过完整门禁的候选方钢截面。")
    early_stop = selection.get("early_stop") if isinstance(selection.get("early_stop"), dict) else {}
    candidate_rows = selection.get("candidate_results") or []
    summaries: list[str] = []
    if isinstance(candidate_rows, list):
        for row in candidate_rows[:8]:
            if not isinstance(row, dict):
                continue
            section_name = row.get("section_name") or row.get("candidate_section") or "unknown"
            ratio = row.get("controlling_ratio")
            if ratio is None:
                ratio_text = "未取得"
            else:
                try:
                    ratio_text = f"{float(ratio):.3f}"
                except (TypeError, ValueError):
                    ratio_text = str(ratio)
            status = row.get("status") or row.get("result_gate_status") or row.get("run_status") or "unknown"
            diagnosis = row.get("diagnosis") if isinstance(row.get("diagnosis"), dict) else {}
            failed_checks = row.get("failed_non_ratio_checks") or diagnosis.get("failed_checks") or []
            failed_text = ""
            if failed_checks:
                failed_text = f", failed_checks={','.join(str(item) for item in failed_checks[:5])}"
            trial_dir = row.get("trial_dir")
            trial_text = f", trial_dir={trial_dir}" if trial_dir else ""
            summaries.append(f"{section_name}: ratio={ratio_text}, status={status}{failed_text}{trial_text}")
    summary_text = "；".join(summaries) if summaries else "无候选摘要"
    early_detail = ""
    if early_stop:
        early_detail = (
            f" early_stop candidate={early_stop.get('candidate_section') or 'unknown'}, "
            f"run_status={early_stop.get('run_status') or 'unknown'}, "
            f"domains={','.join(str(item) for item in early_stop.get('domains') or []) or 'none'}, "
            f"failed_checks={','.join(str(item) for item in early_stop.get('failed_checks') or []) or 'none'}, "
            f"trial_dir={early_stop.get('trial_dir') or 'unknown'}."
        )
    return (
        f"方钢截面自动选型未通过：{reason}。候选概要：{summary_text}。{early_detail}"
        "正式计算已阻断并保留 job 目录；请检查 result_validation.json、ansys_run_audit.json、"
        "ansys_stdout.log/ansys_stderr.log 和上面列出的 trial_dir。"
    )


def _progress_stage_cap(stage: str) -> int:
    """Keep active stages below final completion in the operator UI."""

    if stage in {"completed", "failed", "cancelled"}:
        return 100
    caps = {
        "creating_jobs": 8,
        "ansys_config": 12,
        "job_started": 15,
        "startup_cleanup": 18,
        "confirm_spectrum": 24,
        "write_spectrum": 30,
        "render_commands": 38,
        "select_square_section": 55,
        "running_ansys": 82,
        "ansys_startup_retry": 82,
        "ansys_resource_retry": 82,
        "ansys_license_retry": 82,
        "rerunning_ansys_after_modal_retry": 84,
        "rerunning_ansys_after_section_reselection": 84,
        "rerunning_ansys_after_section_upgrade": 84,
        "final_ratio_section_recovery": 94,
        "rerunning_ansys_after_final_ratio_recovery": 84,
        "ansys_output_monitor": 85,
        "exporting_connection_nodes": 86,
        "exporting_figures": 88,
        "ansys_post_exports_done": 90,
        "parsing_results": 92,
        "reuse_exact_result": 92,
        "upgrade_square_section": 94,
        "dry_run": 90,
        "publish_outputs": 96,
        "job_finished": 99,
    }
    return caps.get(stage, 95)


def _clamp_progress(stage: str, percent: int) -> int:
    cap = _progress_stage_cap(stage)
    return max(0, min(cap, int(percent)))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _clone_config_with_explicit_nproc(config: Any, nproc: int) -> Any:
    clone = config.model_copy(deep=True) if hasattr(config, "model_copy") else config.copy(deep=True)
    clone.ansys.nproc = int(nproc)
    clone.ansys.nproc_percent = None
    clone.ansys.high_modal_nproc_cap = None
    return clone


def _clone_config_with_resources(config: Any, nproc: int, memory: str | None) -> Any:
    clone = _clone_config_with_explicit_nproc(config, nproc)
    clone.ansys.memory = memory
    return clone


def _startup_retry_sequence(config: Any, attempted_nproc: int | None) -> list[int]:
    values = list(getattr(getattr(config, "ansys", None), "startup_retry_nproc", []) or [4, 2, 1])
    sequence: list[int] = []
    for raw in values:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        if attempted_nproc and value >= attempted_nproc:
            continue
        if value not in sequence:
            sequence.append(value)
    if 1 not in sequence:
        sequence.append(1)
    return sequence


def _ansys_memory_resource_failure(audit: dict[str, Any]) -> bool:
    payload = {
        "status": audit.get("status"),
        "failure_reason": audit.get("failure_reason"),
        "fatal_output_detection": audit.get("fatal_output_detection"),
        "stderr_tail": audit.get("stderr_tail"),
        "stdout_tail": audit.get("stdout_tail"),
    }
    text = json.dumps(payload, ensure_ascii=False).lower()
    return any(
        token in text
        for token in (
            "memory (-m)",
            "not currently available",
            "worker processes requested",
            "insufficient memory",
            "not enough memory",
        )
    )


def _resource_retry_sequence(config: Any, attempted_nproc: int | None) -> list[dict[str, Any]]:
    nprocs = _startup_retry_sequence(config, attempted_nproc)
    memory_by_nproc = {
        4: "4096",
        3: "4096",
        2: "2048",
        1: None,
    }
    variants: list[dict[str, Any]] = []
    for nproc in nprocs:
        memory = memory_by_nproc.get(nproc, "4096")
        item = {"nproc": nproc, "memory": memory}
        if item not in variants:
            variants.append(item)
    if {"nproc": 1, "memory": None} not in variants:
        variants.append({"nproc": 1, "memory": None})
    return variants


def _next_modal_retry_count(current_count: int | None, job_dir: Path | str | None = None) -> int | None:
    plan = _modal_retry_plan(current_count, job_dir)
    value = plan.get("next_modal_mode_count")
    return int(value) if value is not None else None


def _last_modal_frequency_hz(job_dir: Path | str) -> float | None:
    job_dir = Path(job_dir)
    validation = _read_validation_status(job_dir)
    for item in validation.get("checks") or []:
        if not isinstance(item, dict) or item.get("check_id") != "modal_mt_cutoff":
            continue
        evidence = item.get("evidence")
        if isinstance(evidence, dict):
            try:
                return float(evidence.get("last_frequency_hz"))
            except (TypeError, ValueError):
                pass

    modal_path = job_dir / "modal_results.json"
    if not modal_path.exists():
        return None
    try:
        rows = json.loads(modal_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    for row in reversed(rows):
        if not isinstance(row, dict):
            continue
        try:
            return float(row.get("frequency_hz"))
        except (TypeError, ValueError):
            continue
    return None


def _modal_retry_plan(current_count: int | None, job_dir: Path | str | None = None) -> dict[str, Any]:
    current = int(current_count or 0)
    normal_cap = max(MODAL_RETRY_SEQUENCE)
    audited_source_count = audited_source_modal_mode_count_from_job(job_dir) if job_dir is not None else None
    if job_dir is not None:
        last_frequency_hz = _last_modal_frequency_hz(job_dir)
        if last_frequency_hz is not None:
            if last_frequency_hz >= 50.0:
                return {
                    "status": "covered",
                    "current_modal_mode_count": current,
                    "last_frequency_hz": last_frequency_hz,
                    "next_modal_mode_count": None,
                    "reason": "Mode.oup already covers the 50 Hz cutoff.",
                }
            if last_frequency_hz > 0:
                estimated_count = int(math.ceil(current * 50.0 / last_frequency_hz * 1.15))
                if (
                    last_frequency_hz < 8.0
                    and current >= normal_cap
                    and not (audited_source_count is not None and current < audited_source_count)
                ):
                    return {
                        "status": "blocked_low_modal_frequency",
                        "current_modal_mode_count": current,
                        "last_frequency_hz": last_frequency_hz,
                        "estimated_modal_mode_count": estimated_count,
                        "next_modal_mode_count": None,
                        "reason": (
                            "The last extracted modal frequency is far below 50 Hz after a bounded initial solve. "
                            "This points to model constraints, mass/loading, stale Mode.oup, or source-command mismatch; "
                            "continuing to enlarge MT would waste time and still not make the result reliable."
                        ),
                    }
                if estimated_count > normal_cap:
                    if audited_source_count is not None and current < audited_source_count:
                        return {
                            "status": "audited_source_retry",
                            "current_modal_mode_count": current,
                            "last_frequency_hz": last_frequency_hz,
                            "estimated_modal_mode_count": estimated_count,
                            "audited_source_modal_mode_count": audited_source_count,
                            "next_modal_mode_count": audited_source_count,
                            "reason": (
                                "Estimated MT exceeds the normal smart-retry cap, but the audited standard model "
                                "command stream contains a higher modal extraction count. Retry once with that "
                                "source-traceable MT before blocking publication."
                            ),
                        }
                    if current < normal_cap:
                        return {
                            "status": "cap_retry",
                            "current_modal_mode_count": current,
                            "last_frequency_hz": last_frequency_hz,
                            "estimated_modal_mode_count": estimated_count,
                            "next_modal_mode_count": normal_cap,
                            "reason": (
                                "Estimated MT exceeds the normal cap; run one capped verification retry after "
                                "cleaning regenerable outputs. If the capped retry still misses 50 Hz, treat it "
                                "as a model/source/output issue instead of looping."
                            ),
                        }
                    return {
                        "status": "blocked_retry_cap_exceeded",
                        "current_modal_mode_count": current,
                        "last_frequency_hz": last_frequency_hz,
                        "estimated_modal_mode_count": estimated_count,
                        "next_modal_mode_count": None,
                        "reason": "Estimated MT exceeds the bounded retry cap; treat as a model/source issue instead of looping.",
                    }
                for value in MODAL_RETRY_SEQUENCE:
                    if int(value) > current and int(value) >= estimated_count:
                        return {
                            "status": "estimated_retry",
                            "current_modal_mode_count": current,
                            "last_frequency_hz": last_frequency_hz,
                            "estimated_modal_mode_count": estimated_count,
                            "next_modal_mode_count": int(value),
                            "reason": "Retry MT is estimated from the last Mode.oup frequency instead of stepping one-by-one.",
                        }

    for value in MODAL_RETRY_SEQUENCE:
        if int(value) > current:
            return {
                "status": "sequence_retry",
                "current_modal_mode_count": current,
                "last_frequency_hz": None,
                "next_modal_mode_count": int(value),
                "reason": "No usable modal frequency evidence; fall back to the bounded retry sequence.",
            }
    if audited_source_count is not None and current < audited_source_count:
        return {
            "status": "audited_source_sequence_retry",
            "current_modal_mode_count": current,
            "last_frequency_hz": None,
            "audited_source_modal_mode_count": audited_source_count,
            "next_modal_mode_count": audited_source_count,
            "reason": "Normal modal retry sequence is exhausted; retry with the audited source modal count.",
        }
    return {
        "status": "blocked_sequence_exhausted",
        "current_modal_mode_count": current,
        "last_frequency_hz": None,
        "next_modal_mode_count": None,
        "reason": "Modal retry sequence exhausted before Mode.oup covered 50 Hz.",
    }


def _modal_cutoff_retry_needed(job_dir: Path) -> bool:
    validation = _read_validation_status(job_dir)
    for item in validation.get("checks") or []:
        if not isinstance(item, dict):
            continue
        if item.get("check_id") == "modal_mt_cutoff" and item.get("status") == "fail":
            return True
    return False


def _rewrite_job_modal_count(job_dir: Path, count: int) -> dict[str, Any]:
    solve_path = job_dir / "generated_solve.mac"
    if not solve_path.exists():
        raise FileNotFoundError(f"generated_solve.mac is missing for modal retry: {solve_path}")
    before = modal_mode_count_from_job_dir(job_dir)
    text = solve_path.read_text(encoding="utf-8", errors="replace")
    solve_path.write_text(rewrite_modal_mode_count(text, count), encoding="utf-8", newline="\n")
    return {
        "status": "pass",
        "before_modal_mode_count": before,
        "after_modal_mode_count": count,
        "file": str(solve_path),
        "policy": "Increase MT only after Mode.oup fails the >50 Hz coverage gate; stop at the first passing retry.",
    }


def _is_relative_to(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _clean_regenerable_outputs_for_rerun(job_dir: Path, *, include_command_streams: bool = False) -> dict[str, Any]:
    suffixes = {".out", ".err", ".rst", ".db", ".lis", ".oup", ".bmp", ".png", ".log"}
    names = {
        "apdl_audit.json",
        "ansys_command.json",
        "ansys_live_status.json",
        "ansys_preflight.json",
        "ansys_run_audit.json",
        "beam_stress_results.json",
        "bolt_eval.json",
        "bolt_force_results.json",
        "chapter6_display.json",
        "connection_node_force_results.json",
        "evaluation_summary.json",
        "figure_export_audit.json",
        "figures_manifest.json",
        "foundation_loads.json",
        "load_extractions.json",
        "modal_mt_policy.json",
        "modal_results.json",
        "postprocess_ai_qc.json",
        "published_results_manifest.json",
        "report_audit.json",
        "report_traceability.json",
        "result.json",
        "result_raw.json",
        "result_validation.json",
        "run_all_audit.json",
        "run_ansys.ps1",
        "generated_square_section_apdl.json",
        "square_section_allowed_sections.json",
        "square_section_candidate_policy.json",
        "square_section_selection_applied.json",
        "square_section_selection.json",
        "square_section_selection_summary.json",
        "square_section_trial_summary.json",
        "square_section_upgrade_after_ratio_fail.json",
        "support_eval.json",
        "template_report_audit.json",
        "template_report_traceability.json",
        "tray_arm_connection_loads.json",
        "weld_eval.json",
        "weld_force_results.json",
    }
    if include_command_streams:
        names.update(
            {
                "generated_model.mac",
                "generated_solve.mac",
                "generated_post.mac",
                "run_all.mac",
            }
        )
    dir_names = {
        "figures",
        "raw_results",
        "reports",
        "report_assets",
        "template_report_assets",
        "post_exports",
        "raw_output_import",
        "imported_outputs",
        "evaluation_workbooks",
    }
    removed: list[str] = []
    removed_dirs: list[str] = []
    root = job_dir.resolve()
    for path in job_dir.iterdir() if job_dir.exists() else []:
        if not _is_relative_to(path, root):
            continue
        if path.is_file() and (path.name in names or path.suffix.lower() in suffixes):
            try:
                path.unlink()
                removed.append(path.name)
            except OSError:
                pass
        elif path.is_dir() and path.name in dir_names:
            try:
                shutil.rmtree(path)
                removed_dirs.append(path.name)
            except OSError:
                pass
    trials_dir = job_dir.parent / "_square_section_trials" / job_dir.name
    if trials_dir.exists() and _is_relative_to(trials_dir, job_dir.parent / "_square_section_trials"):
        try:
            shutil.rmtree(trials_dir)
            removed_dirs.append(str(trials_dir.relative_to(job_dir.parent)))
        except OSError:
            pass
    upgrade_trials_dir = job_dir.parent / "_square_section_upgrade_trials" / job_dir.name
    if upgrade_trials_dir.exists() and _is_relative_to(upgrade_trials_dir, job_dir.parent / "_square_section_upgrade_trials"):
        try:
            shutil.rmtree(upgrade_trials_dir)
            removed_dirs.append(str(upgrade_trials_dir.relative_to(job_dir.parent)))
        except OSError:
            pass
    return {
        "status": "pass",
        "removed_count": len(removed) + len(removed_dirs),
        "removed_files": removed[:80],
        "removed_dirs": removed_dirs[:40],
        "include_command_streams": include_command_streams,
    }


def _metadata(job_dir: Path) -> dict[str, Any]:
    payload = _read_json(job_dir / "input.json")
    metadata = payload.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _render_commands(job_dir: Path, jobs_dir: Path, package_id: str | None, *, source_root: Path, template_dir: Path) -> dict[str, Any]:
    if package_id:
        result = render_llm_orchestrated_command_package(
            job_dir,
            source_root=source_root,
            jobs_dir=jobs_dir,
            template_dir=template_dir,
            package_id=package_id,
            use_model=True,
        )
        result["command_source"] = "standard_source_package"
        result["command_policy"] = "Historical command packages are used only when explicitly requested for source regression, not for intake-as-new validation."
        return result
    input_payload = _read_json(job_dir / "input.json")
    analysis_method = str((input_payload.get("metadata") or {}).get("analysis_method") or "").lower()
    solve_strategy = "adjacent_source" if analysis_method == "static" else "template"
    result = render_llm_orchestrated_command_package(
        job_dir,
        source_root=source_root,
        jobs_dir=jobs_dir,
        template_dir=template_dir,
        use_model=True,
        solve_strategy=solve_strategy,
    )
    result["command_source"] = "intake_standard_family_based_on_standard_sources"
    result["command_policy"] = (
        "Static-method jobs preserve the adjacent audited static calculation command stream and rewrite only equivalent "
        "static ACEL coefficients from the current intake. They do not use response-spectrum modal extraction, MT, or "
        "Mode.oup 50 Hz coverage. Response-spectrum jobs use the controlled spectrum solve template so SL-1/SL-2 and "
        "zero-period correction are generated from the operator-selected spectrum workbook."
        if analysis_method == "static"
        else (
            "Default operator flow treats the uploaded intake as new intake. The LLM may propose a structured engineering intent "
            "and command plan, but the final command streams are compiled from the matched audited standard command-flow family; "
            "the solve command uses the operator-selected spectrum workbook instead of an adjacent historical report solve file."
        )
    )
    result["solve_strategy_requested"] = solve_strategy
    return result


def _write_spectrum_mac_if_needed(
    job_dir: Path,
    spectrum_file: str | None,
    analysis_method: str,
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
) -> dict[str, Any]:
    input_payload = _read_json(job_dir / "input.json")
    if analysis_method == "static":
        return {"status": "not_required", "reason": "static_method_uses_metadata_static_acceleration_coefficients"}
    if not spectrum_file:
        raise ValueError("Response-spectrum jobs require an operator-selected project spectrum workbook.")
    project = input_payload.get("project") or {}
    frequency_guide_source: Path | None = None
    try:
        family = select_standard_model_family(input_payload, source_root)
        frequency_guide_source = find_adjacent_solve_command(family["source"])
    except Exception:
        frequency_guide_source = None
    return write_segmented_response_spectrum_mac(
        spectrum_file,
        job_dir,
        project_code=str(project.get("project_code") or ""),
        building=str(project.get("building") or ""),
        elevation=float(project.get("elevation") or 0.0),
        frequency_guide_source=frequency_guide_source,
    )


def _persist_spectrum_selection_features(
    job_dir: Path,
    spectrum_audit: dict[str, Any],
    analysis_method: str,
) -> dict[str, Any]:
    """Persist compact spectrum/load-intensity features for candidate ordering only."""

    input_path = job_dir / "input.json"
    payload = _read_json(input_path)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    zpa = spectrum_audit.get("static_acceleration_source")
    if not isinstance(zpa, dict):
        zpa = metadata.get("static_acceleration_source") if isinstance(metadata.get("static_acceleration_source"), dict) else {}
    peaks: dict[str, float] = {}
    points_path = job_dir / "spectrum_points.json"
    if analysis_method != "static" and points_path.exists():
        points_payload = _read_json(points_path)
        for step in points_payload.get("load_steps") or []:
            if not isinstance(step, dict):
                continue
            key = f"{str(step.get('level') or '').lower()}_{str(step.get('direction') or '').lower()}"
            values = []
            for point in step.get("points") or []:
                if not isinstance(point, dict):
                    continue
                try:
                    values.append(abs(float(point.get("acceleration_g"))))
                except (TypeError, ValueError):
                    continue
            if values:
                peaks[key] = round(max(values), 9)
    workbook_sha = zpa.get("workbook_sha256")
    features = {
        "schema_version": "spectrum-selection-features-v1",
        "analysis_method": analysis_method,
        "workbook_sha256": workbook_sha,
        "sheet": spectrum_audit.get("sheet") or zpa.get("sheet"),
        "requested_elevation_m": spectrum_audit.get("requested_elevation") or zpa.get("requested_elevation"),
        "selected_elevation_m": spectrum_audit.get("selected_elevation") or zpa.get("selected_elevation"),
        "peak_acceleration_g_by_level_direction": peaks,
        "peak_acceleration_g": round(max(peaks.values()), 9) if peaks else None,
        "zpa_obe_max_g": max(
            [float(zpa.get(key) or 0.0) for key in ("zpa_obe_x_g", "zpa_obe_y_g", "zpa_obe_z_g")],
            default=0.0,
        ),
        "zpa_sse_max_g": max(
            [float(zpa.get(key) or 0.0) for key in ("zpa_sse_x_g", "zpa_sse_y_g", "zpa_sse_z_g")],
            default=0.0,
        ),
        "source_ref": "spectrum_audit.json + spectrum_points.json; candidate ordering only",
        "authority": "ordering_feature_only_not_a_calculation_result",
    }
    metadata["spectrum_selection_features"] = features
    payload["metadata"] = metadata
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return features


def _read_validation_status(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "result_validation.json"
    if not path.exists():
        return {"status": "missing", "fail_count": 1, "reason": "result_validation.json was not generated"}
    try:
        payload = _read_json(path)
    except Exception as exc:
        return {"status": "invalid", "fail_count": 1, "reason": str(exc)}
    return payload


def _ensure_publishable_result(job_dir: Path) -> None:
    validation = _read_validation_status(job_dir)
    if validation.get("status") == "pass":
        return
    failed = [
        str(item.get("check_id"))
        for item in validation.get("checks") or []
        if isinstance(item, dict) and item.get("status") == "fail"
    ]
    detail = ", ".join(failed[:8]) if failed else str(validation.get("reason") or validation.get("status"))
    raise RuntimeError(f"Result validation failed; production publication is blocked: {detail}")


def _sync_square_section_row_result_from_summary(row_result: dict[str, Any], job_dir: Path) -> None:
    summary_path = job_dir / "square_section_selection_summary.json"
    if not summary_path.exists():
        return
    try:
        summary = _read_json(summary_path)
    except Exception:
        return
    section_name = summary.get("section_name")
    final_ratio = summary.get("final_section_selection_ratio")
    controlling_ratio = summary.get("controlling_ratio")
    trial_ratio = summary.get("trial_controlling_ratio")
    if section_name:
        row_result["square_section_selected"] = section_name
    if controlling_ratio is not None:
        row_result["square_section_selected_ratio"] = controlling_ratio
    if final_ratio is not None:
        row_result["square_section_final_section_selection_ratio"] = final_ratio
    if trial_ratio is not None:
        row_result["square_section_trial_controlling_ratio"] = trial_ratio
    row_result["square_section_ratio_consistency_status"] = summary.get("ratio_consistency_status")


def _last_ansys_audit(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "ansys_run_audit.json"
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except Exception:
        return {}


def _post_export_figure_failure_after_main_success(audit: dict[str, Any]) -> bool:
    failure = audit.get("post_export_failure") if isinstance(audit.get("post_export_failure"), dict) else {}
    return (
        audit.get("status") == "failed"
        and (audit.get("completion_marker_detection") or {}).get("status") == "pass"
        and str(failure.get("name") or "") == "figure_export"
    )


def _job_text_contains_license_failure(job_dir: Path) -> bool:
    text = ""
    for name in ("export_figures.out", "figure_export_stdout.log", "figure_export_stderr.log", "CableTrayAI_Run.err"):
        path = job_dir / name
        if not path.exists() or not path.is_file():
            continue
        try:
            text += "\n" + path.read_text(encoding="utf-8", errors="replace")[-8000:]
        except OSError:
            continue
    lower = text.lower()
    return any(token in lower for token in ANSYS_LICENSE_FAILURE_TOKENS)


def _ansys_license_failure(audit: dict[str, Any], job_dir: Path) -> bool:
    if audit.get("status") in {"success", "pass"}:
        return False
    payload = {
        "status": audit.get("status"),
        "failure_reason": audit.get("failure_reason"),
        "failure_category": audit.get("failure_category"),
        "fatal_output_detection": audit.get("fatal_output_detection"),
        "stderr_tail": audit.get("stderr_tail"),
        "stdout_tail": audit.get("stdout_tail"),
    }
    text = json.dumps(payload, ensure_ascii=False).lower()
    return any(token in text for token in ANSYS_LICENSE_FAILURE_TOKENS) or _job_text_contains_license_failure(job_dir)


def _retain_solver_artifacts_after_failure(job_dir: Path) -> bool:
    audit = _last_ansys_audit(job_dir)
    return bool(
        audit.get("post_export_license_unavailable")
        or (
            _post_export_figure_failure_after_main_success(audit)
            and (
                "license" in json.dumps(audit.get("figure_export_audit") or {}, ensure_ascii=False).lower()
                or _job_text_contains_license_failure(job_dir)
            )
        )
    )


def run_operator_one_click(
    *,
    intake_path: Path | str,
    spectrum_file: Path | str | None,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    jobs_dir: Path | str = Path("jobs"),
    source_package_id: str | None = None,
    execute_real: bool = True,
    confirm_user: str = "dashboard",
    preferred_ansys_executable: str | None = None,
    limit: int | None = None,
    selected_row_numbers: list[int] | tuple[int, ...] | None = None,
    selected_intake_order_ids: list[str] | tuple[str, ...] | None = None,
    row_overrides: dict[str, dict] | list[dict] | None = None,
    config_path: Path | str = Path("config/ansys.local.toml"),
    source_root: Path | str = Path("source_materials/model_commands"),
    template_dir: Path | str = Path("templates/apdl"),
    square_section_candidate_limit: int | None = None,
    freeze_provided_square_sections: bool = False,
    allow_exact_result_reuse: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if square_section_candidate_limit is not None:
        try:
            square_section_candidate_limit = int(square_section_candidate_limit)
        except (TypeError, ValueError):
            square_section_candidate_limit = None
        if square_section_candidate_limit is not None and square_section_candidate_limit <= 0:
            square_section_candidate_limit = None

    progress_memory: dict[str, int] = {}

    def progress(stage: str, message: str, percent: int, **extra: Any) -> None:
        if progress_callback:
            clamped_percent = _clamp_progress(stage, int(percent))
            if stage not in {"completed", "failed", "cancelled"}:
                clamped_percent = min(clamped_percent, 99)
            memory_key = str(extra.get("job_id") or "__batch__")
            previous_percent = progress_memory.get(memory_key, 0)
            if stage in {"completed", "failed", "cancelled"}:
                progress_memory[memory_key] = clamped_percent
            else:
                clamped_percent = max(previous_percent, clamped_percent)
                progress_memory[memory_key] = clamped_percent
            progress_callback({"stage": stage, "message": message, "progress": clamped_percent, **extra})

    jobs_dir = Path(jobs_dir)
    output_root = Path(output_root)
    spectrum_text = str(spectrum_file) if spectrum_file else None
    progress("creating_jobs", "正在从提资创建计算任务", 5)
    created = create_jobs_from_intake_workbook(
        intake_path,
        jobs_dir=jobs_dir,
        spectrum_file=spectrum_text,
        spectrum_confirmed=bool(spectrum_text),
        limit=limit,
        selected_row_numbers=selected_row_numbers,
        selected_intake_order_ids=selected_intake_order_ids,
        row_overrides=row_overrides,
    )
    publish_keys = [
        str((item.get("audit") or {}).get("report_number") or (item.get("audit") or {}).get("calculation_batch") or (item.get("audit") or {}).get("intake_order_id") or item.get("job_id"))
        for item in created
    ]
    duplicate_publish_keys = {key for key, count in Counter(publish_keys).items() if count > 1}
    progress("ansys_config", "正在确认 ANSYS 路径和资源配置", 10, job_count=len(created))
    config, ansys_audit = ensure_ansys_config(
        config_path=config_path,
        preferred_executable=preferred_ansys_executable,
        real_mode=execute_real,
        output_dir=str(output_root),
    )

    job_results: list[dict[str, Any]] = []
    total = max(1, len(created))
    for index, item in enumerate(created, start=1):
        job_dir = Path(item["job_dir"])
        metadata = _metadata(job_dir)
        analysis_method = str(metadata.get("analysis_method") or "response_spectrum")
        provided_square_section_frozen = (
            freeze_provided_square_sections
            and metadata.get("square_section_selection_status") == "provided_by_intake_column_i"
        )
        base_progress = 10 + int((index - 1) * 85 / total)
        progress("job_started", f"开始处理 {item['job_id']} ({index}/{total})", base_progress, job_id=item["job_id"])
        row_result: dict[str, Any] = {
            "job_id": item["job_id"],
            "job_dir": str(job_dir),
            "report_number": metadata.get("report_number") or metadata.get("calculation_batch"),
            "intake_order_id": metadata.get("intake_order_id"),
            "provisional_intake_id": metadata.get("provisional_intake_id"),
            "intake_identity_status": metadata.get("intake_identity_status"),
            "analysis_method": analysis_method,
            "status": "created",
        }
        row_result["geometry_recovery_policy"] = "support_spacing_and_support_length_fixed"
        row_result["overlimit_operator_action"] = "revise_confirmed_tray_line_load_and_rerun"
        try:
            if not spectrum_text:
                raise ValueError("Every production job requires an operator-selected project spectrum workbook; static jobs use it to derive audited equivalent-static acceleration coefficients.")
            if execute_real:
                cleanup_audit = _clean_regenerable_outputs_for_rerun(job_dir, include_command_streams=True)
                row_result["startup_regenerable_cleanup"] = cleanup_audit
                if cleanup_audit.get("removed_count"):
                    progress(
                        "startup_cleanup",
                        f"{item['job_id']}：清理上一轮可再生成结果，避免旧门禁误判当前运行",
                        base_progress + 2,
                        job_id=item["job_id"],
                        removed_count=cleanup_audit.get("removed_count"),
                    )
            progress("confirm_spectrum", f"{item['job_id']}：确认反应谱配置", base_progress + 5, job_id=item["job_id"])
            confirm_spectrum_config(job_dir, confirmed_by=confirm_user)
            if execute_real:
                progress("write_spectrum", f"{item['job_id']}：生成 ansys_spectrum.mac 和 ZPA 参数", base_progress + 10, job_id=item["job_id"])
                spectrum_audit = _write_spectrum_mac_if_needed(job_dir, spectrum_text, analysis_method, source_root=source_root)
                row_result["spectrum_status"] = spectrum_audit.get("status")
                row_result["spectrum_selection_features"] = _persist_spectrum_selection_features(
                    job_dir,
                    spectrum_audit,
                    analysis_method,
                )
            else:
                row_result["spectrum_status"] = "deferred_until_real_run"
            progress("render_commands", f"{item['job_id']}：生成建模/计算/提取三份命令流", base_progress + 18, job_id=item["job_id"])
            render_audit = _render_commands(job_dir, jobs_dir, source_package_id, source_root=Path(source_root), template_dir=Path(template_dir))
            row_result["command_source"] = render_audit.get("command_source")
            row_result["command_status"] = render_audit.get("status")
            update_job_state(job_dir, "apdl_rendered", "operator one-click command streams rendered")
            if execute_real:
                def forward_section_progress(event: dict[str, Any]) -> None:
                    candidate_index = int(event.get("candidate_index") or event.get("completed_candidate_count") or 0)
                    candidate_count = max(1, int(event.get("candidate_count") or 1))
                    local_progress = min(42, 30 + int(candidate_index * 12 / candidate_count))
                    progress(
                        "select_square_section",
                        str(event.get("message") or f"{item['job_id']}: square-section auto-selection"),
                        min(base_progress + local_progress, base_progress + 44),
                        job_id=item["job_id"],
                        candidate_section=event.get("candidate_section"),
                        candidate_index=candidate_index,
                        candidate_count=candidate_count,
                        trial_dir=event.get("trial_dir"),
                        trial_status_file=event.get("trial_status_file"),
                        elapsed_seconds=event.get("elapsed_seconds"),
                        no_output_seconds=event.get("no_output_seconds"),
                        total_output_bytes=event.get("total_output_bytes"),
                        process_running=event.get("process_running"),
                        ansys_pid=event.get("ansys_pid"),
                    )

                if square_section_auto_selection_required(job_dir):
                    progress("select_square_section", f"{item['job_id']}：候选方钢截面自动选型", base_progress + 30, job_id=item["job_id"])

                    def section_progress(event: dict[str, Any]) -> None:
                        candidate_index = int(event.get("candidate_index") or event.get("completed_candidate_count") or 0)
                        candidate_count = max(1, int(event.get("candidate_count") or 1))
                        local_progress = min(42, 30 + int(candidate_index * 12 / candidate_count))
                        progress(
                            "select_square_section",
                            str(event.get("message") or f"{item['job_id']}：候选方钢截面自动选型"),
                            min(base_progress + local_progress, base_progress + 44),
                            job_id=item["job_id"],
                            candidate_section=event.get("candidate_section"),
                            candidate_index=candidate_index,
                            candidate_count=candidate_count,
                            trial_dir=event.get("trial_dir"),
                            trial_status_file=event.get("trial_status_file"),
                            elapsed_seconds=event.get("elapsed_seconds"),
                            no_output_seconds=event.get("no_output_seconds"),
                            total_output_bytes=event.get("total_output_bytes"),
                            process_running=event.get("process_running"),
                            ansys_pid=event.get("ansys_pid"),
                        )

                    selection = select_and_apply_square_section(
                        job_dir,
                        config=config,
                        config_path=config_path,
                        confirm_user=confirm_user,
                        source_root=source_root,
                        limit=square_section_candidate_limit,
                        progress_callback=section_progress,
                    )
                    row_result["square_section_selection_status"] = selection.get("status")
                    selected = selection.get("selected") or {}
                    if selected:
                        row_result["square_section_selected"] = selected.get("section_name")
                        row_result["square_section_selected_ratio"] = selected.get("controlling_ratio")
                    if selection.get("status") != "pass":
                        raise RuntimeError(_square_section_selection_failure_message(selection))
                progress("running_ansys", f"{item['job_id']}：正在运行 ANSYS，耗时取决于模型规模和机器核数", base_progress + 45, job_id=item["job_id"])
                cache_hit: dict[str, Any] = {
                    "status": "disabled",
                    "reason": "Exact result reuse is disabled by default for operator production runs.",
                }
                if allow_exact_result_reuse:
                    cache_hit = find_exact_cached_result(job_dir, jobs_dir)
                row_result["exact_result_reuse_status"] = cache_hit.get("status")
                if allow_exact_result_reuse and cache_hit.get("status") == "hit":
                    row_result["ansys_run_status"] = "reused_exact_input_real_result"
                    row_result["exact_result_cache_source"] = cache_hit.get("source_job_dir")
                    progress(
                        "reuse_exact_result",
                        f"{item['job_id']}：输入和命令流完全一致，复用已通过的真实 ANSYS 输出并重新组装当前结果",
                        base_progress + 68,
                        job_id=item["job_id"],
                    )
                    copy_exact_cached_outputs(Path(str(cache_hit["source_job_dir"])), job_dir)
                    assemble_result(job_dir)
                    _ensure_publishable_result(job_dir)
                    _sync_square_section_row_result_from_summary(row_result, job_dir)
                    update_job_state(job_dir, "evaluated", "exact-input real ANSYS outputs reused and parsed")
                else:

                    ansys_progress_floor = {"value": base_progress + 45}

                    def ansys_progress(event: dict[str, Any]) -> None:
                        event_stage = str(event.get("stage") or "running_ansys")
                        if event.get("message"):
                            event_progress = {
                                "exporting_connection_nodes": base_progress + 66,
                                "exporting_figures": base_progress + 68,
                                "ansys_post_exports_done": base_progress + 70,
                                "running_ansys": base_progress + 70,
                            }.get(event_stage, base_progress + 70)
                            if event_stage == "running_ansys" and ansys_progress_floor["value"] >= base_progress + 66:
                                event_stage = "ansys_output_monitor"
                            event_progress = max(event_progress, ansys_progress_floor["value"])
                            ansys_progress_floor["value"] = max(ansys_progress_floor["value"], event_progress)
                            progress(
                                event_stage,
                                f"{item['job_id']}：{event.get('message')}",
                                event_progress,
                                job_id=item["job_id"],
                            )
                            return
                        elapsed = float(event.get("elapsed_seconds") or 0.0)
                        nproc = event.get("nproc") or "?"
                        output_mb = float(event.get("total_output_bytes") or event.get("output_file_bytes") or 0.0) / (1024 * 1024)
                        quiet_seconds = float(event.get("no_output_seconds") or 0.0)
                        quiet_note = f"，{quiet_seconds/60:.1f} 分钟无新增输出" if quiet_seconds >= 300 else ""
                        dynamic_percent = min(base_progress + 70, base_progress + 45 + int(elapsed // 30))
                        event_stage = "running_ansys"
                        if ansys_progress_floor["value"] >= base_progress + 66:
                            event_stage = "ansys_output_monitor"
                        dynamic_percent = max(dynamic_percent, ansys_progress_floor["value"])
                        ansys_progress_floor["value"] = max(ansys_progress_floor["value"], dynamic_percent)
                        progress(
                            event_stage,
                            f"{item['job_id']}：ANSYS 子进程正在计算，当前子进程已运行 {elapsed/60:.1f} 分钟，核数 {nproc}，子进程输出 {output_mb:.1f} MB{quiet_note}",
                            dynamic_percent,
                            job_id=item["job_id"],
                        )

                    def run_formal_ansys_once(stage_suffix: str = "") -> dict[str, Any]:
                        attempts: list[dict[str, Any]] = []

                        def current_attempted_nproc() -> int | None:
                            command_path = job_dir / "ansys_command.json"
                            if not command_path.exists():
                                return None
                            try:
                                resources = _read_json(command_path).get("resources") or {}
                                value = resources.get("nproc")
                                return int(value) if value is not None else None
                            except Exception:
                                return None

                        def run_attempt(attempt_config: Any, label: str) -> dict[str, Any]:
                            audit = run_real_ansys(
                                job_dir,
                                config=attempt_config,
                                config_path=config_path,
                                confirm_real_run=True,
                                confirm_user=confirm_user,
                                progress_callback=ansys_progress,
                            )
                            resources = ((audit.get("command") or {}).get("resources") or {}) or (audit.get("resources") or {})
                            attempts.append(
                                {
                                    "label": label,
                                    "status": audit.get("status"),
                                    "nproc": resources.get("nproc"),
                                    "memory": resources.get("memory")
                                    or getattr(getattr(attempt_config, "ansys", None), "memory", None),
                                    "failure_reason": audit.get("failure_reason"),
                                }
                            )
                            return audit

                        audit_payload = run_attempt(config, "primary")
                        if _ansys_license_failure(audit_payload, job_dir):
                            for retry_index, delay in enumerate(ANSYS_FORMAL_LICENSE_RETRY_DELAYS_SECONDS, start=1):
                                progress(
                                    "ansys_license_retry",
                                    (
                                        f"{item['job_id']}: ANSYS license is temporarily unavailable; "
                                        f"waiting {int(delay)}s before retry {retry_index}."
                                    ),
                                    min(base_progress + 69, base_progress + 70),
                                    job_id=item["job_id"],
                                )
                                _clean_regenerable_outputs_for_rerun(job_dir)
                                cleanup_stale_ansys_locks(job_dir)
                                time.sleep(max(0, int(delay)))
                                audit_payload = run_attempt(config, f"license_retry_{retry_index}")
                                if not _ansys_license_failure(audit_payload, job_dir):
                                    break
                        retryable_startup_statuses = {"startup_no_output_timeout", "output_stall_timeout"}
                        if (
                            audit_payload.get("status") in retryable_startup_statuses
                            and getattr(getattr(config, "ansys", None), "retry_on_startup_no_output", True)
                        ):
                            attempted_nproc = current_attempted_nproc()
                            for retry_nproc in _startup_retry_sequence(config, attempted_nproc):
                                progress(
                                    "ansys_startup_retry",
                                    f"{item['job_id']}：ANSYS 输出停滞，自动降级为 {retry_nproc} 核运行重试",
                                    min(base_progress + 69, base_progress + 70),
                                    job_id=item["job_id"],
                                )
                                audit_payload = run_attempt(
                                    _clone_config_with_explicit_nproc(config, retry_nproc),
                                    f"startup_retry_nproc_{retry_nproc}",
                                )
                                if audit_payload.get("status") not in retryable_startup_statuses:
                                    break
                        if (
                            audit_payload.get("status") != "success"
                            and _ansys_memory_resource_failure(audit_payload)
                            and getattr(getattr(config, "ansys", None), "retry_on_startup_no_output", True)
                        ):
                            attempted_nproc = current_attempted_nproc()
                            for retry in _resource_retry_sequence(config, attempted_nproc):
                                retry_nproc = int(retry["nproc"])
                                retry_memory = retry.get("memory")
                                progress(
                                    "ansys_resource_retry",
                                    (
                                        f"{item['job_id']}：ANSYS 内存/并行资源不足，"
                                        f"自动降级为 {retry_nproc} 核、内存 {retry_memory or 'ANSYS 默认'} 后重试"
                                    ),
                                    min(base_progress + 69, base_progress + 70),
                                    job_id=item["job_id"],
                                )
                                audit_payload = run_attempt(
                                    _clone_config_with_resources(config, retry_nproc, retry_memory),
                                    f"resource_retry_nproc_{retry_nproc}_memory_{retry_memory or 'default'}",
                                )
                                if audit_payload.get("status") == "success" or not _ansys_memory_resource_failure(audit_payload):
                                    break
                        row_result["ansys_run_attempts"] = attempts
                        row_result["ansys_run_status"] = audit_payload.get("status")
                        if audit_payload.get("status") != "success":
                            if _post_export_figure_failure_after_main_success(audit_payload):
                                try:
                                    assemble_result(job_dir)
                                    row_result["partial_result_assembly_status"] = "pass"
                                    row_result["partial_result_assembly_policy"] = (
                                        "Main ANSYS solve completed, but post-only figure export failed. "
                                        "Numeric LIS/OUP results are assembled for diagnosis; publication still requires the figure gate to pass."
                                    )
                                except Exception as partial_exc:
                                    row_result["partial_result_assembly_status"] = "failed"
                                    row_result["partial_result_assembly_reason"] = str(partial_exc)
                            reason = audit_payload.get("failure_reason") or audit_payload.get("failure_category") or "see ansys_run_audit.json"
                            raise RuntimeError(f"ANSYS real run did not finish successfully: {audit_payload.get('status')} - {reason}")
                        progress(
                            "parsing_results",
                            f"{item['job_id']}：解析 LIS/OUP/BMP 并进行评定{stage_suffix}",
                            base_progress + 72,
                            job_id=item["job_id"],
                        )
                        assemble_result(job_dir)
                        return audit_payload

                    run_formal_ansys_once()
                    modal_retry_attempts: list[dict[str, Any]] = []
                    for modal_retry_index in range(MODAL_RETRY_MAX_FORMAL_RERUNS):
                        if not _modal_cutoff_retry_needed(job_dir):
                            break
                        current_modal_count = modal_mode_count_from_job_dir(job_dir)
                        retry_plan = _modal_retry_plan(current_modal_count, job_dir)
                        next_modal_count = retry_plan.get("next_modal_mode_count")
                        if next_modal_count is None:
                            modal_retry_attempts.append(
                                {
                                    "status": "blocked",
                                    "current_modal_mode_count": current_modal_count,
                                    "retry_plan": retry_plan,
                                    "reason": retry_plan.get("reason") or "modal_retry_sequence_exhausted_before_50hz_coverage",
                                }
                            )
                            break
                        rewrite_audit = _rewrite_job_modal_count(job_dir, next_modal_count)
                        cleanup_audit = _clean_regenerable_outputs_for_rerun(job_dir)
                        row_result["rerun_reason"] = "modal_mt_cutoff"
                        row_result["rerun_reason_detail"] = retry_plan.get("reason")
                        row_result["rerun_from_modal_mode_count"] = current_modal_count
                        row_result["rerun_to_modal_mode_count"] = next_modal_count
                        modal_retry_attempts.append(
                            {
                                "status": "retrying",
                                "attempt": modal_retry_index + 1,
                                "from_modal_mode_count": current_modal_count,
                                "to_modal_mode_count": next_modal_count,
                                "retry_plan": retry_plan,
                                "rewrite": rewrite_audit,
                                "cleanup": cleanup_audit,
                            }
                        )
                        progress(
                            "rerunning_ansys_after_modal_retry",
                            (
                                f"{item['job_id']}：评定后触发重跑，原因=模态频率未覆盖 50Hz；"
                                f"MT 从 {current_modal_count} 提高到 {next_modal_count}。"
                                "这不是卡死，是一次有原因的正式重算。"
                            ),
                            min(base_progress + 76, 92),
                            job_id=item["job_id"],
                        )
                        run_formal_ansys_once(f"（MT={next_modal_count} 覆盖 50Hz 重跑）")
                    if _modal_cutoff_retry_needed(job_dir):
                        modal_retry_attempts.append(
                            {
                                "status": "blocked",
                                "current_modal_mode_count": modal_mode_count_from_job_dir(job_dir),
                                "retry_limit": MODAL_RETRY_MAX_FORMAL_RERUNS,
                                "reason": "modal_cutoff_still_failed_after_bounded_smart_retries",
                                "last_frequency_hz": _last_modal_frequency_hz(job_dir),
                            }
                        )
                    row_result["modal_retry_attempts"] = modal_retry_attempts
                    clean_reselection_attempts: list[dict[str, Any]] = []
                    for reselection_attempt in range(1, 2):
                        if not result_validation_needs_square_section_clean_reselection(job_dir):
                            break
                        if provided_square_section_frozen:
                            clean_reselection_attempts.append(
                                {
                                    "status": "skipped_frozen_provided_section",
                                    "attempt": reselection_attempt,
                                    "reason": "Fixed intake/report square sections are not changed automatically.",
                                }
                            )
                            break
                        cleanup_audit = _clean_regenerable_outputs_for_rerun(job_dir)
                        progress(
                            "select_square_section",
                            (
                                f"{item['job_id']}: square-section trial ratio does not match the final Chapter 6 ratio; "
                                f"cleaning stale outputs and rerunning audited section selection (attempt {reselection_attempt})."
                            ),
                            min(base_progress + 77, 92),
                            job_id=item["job_id"],
                        )
                        reselection = select_and_apply_square_section(
                            job_dir,
                            config=config,
                            config_path=config_path,
                            confirm_user=confirm_user,
                            source_root=source_root,
                            limit=square_section_candidate_limit,
                            force_reselect=True,
                        )
                        selected_reselection = reselection.get("selected") or {}
                        clean_reselection_attempts.append(
                            {
                                "status": reselection.get("status"),
                                "attempt": reselection_attempt,
                                "cleanup": cleanup_audit,
                                "selected_section": selected_reselection.get("section_name"),
                                "selected_ratio": selected_reselection.get("controlling_ratio"),
                            }
                        )
                        row_result["square_section_reselection_status"] = reselection.get("status")
                        if selected_reselection:
                            row_result["square_section_selected"] = selected_reselection.get("section_name")
                            row_result["square_section_selected_ratio"] = selected_reselection.get("controlling_ratio")
                        if reselection.get("status") != "pass":
                            raise RuntimeError(
                                "Square section clean reselection failed after trial/final ratio mismatch; "
                                "fix source collections or candidate policy before publishing."
                            )
                        progress(
                            "rerunning_ansys_after_section_reselection",
                            f"{item['job_id']}: rerunning formal ANSYS after clean square-section reselection.",
                            min(base_progress + 80, 94),
                            job_id=item["job_id"],
                        )
                        run_formal_ansys_once("(after clean square-section reselection)")
                    row_result["square_section_clean_reselection_attempts"] = clean_reselection_attempts
                    for upgrade_attempt in range(1, 4):
                        section_ratio_recovery = result_validation_needs_square_section_upgrade(job_dir)
                        final_ratio_recovery = result_validation_needs_final_ratio_section_recovery(job_dir)
                        if not section_ratio_recovery and not final_ratio_recovery:
                            break
                        if provided_square_section_frozen:
                            row_result["square_section_upgrade_status"] = "skipped_frozen_provided_section"
                            row_result["square_section_upgrade_policy"] = (
                                "Historical verification freezes the square section supplied by the intake/report. "
                                "Automatic economic section upgrades are reserved for new intake rows whose column I is blank."
                            )
                            break
                        recovery_mode = "square_section_ratio_gate" if section_ratio_recovery else "final_ratio_design_recovery"
                        recovery_reason = (
                            "Final deterministic Chapter 6.1 square-section ratio exceeded 1.0."
                            if section_ratio_recovery
                            else "Final deterministic weld/bolt/global ratio gate exceeded 1.0; trying a larger allowed section as design recovery."
                        )
                        recovery_stage = (
                            "upgrade_square_section"
                            if section_ratio_recovery
                            else "final_ratio_section_recovery"
                        )
                        rerun_stage = (
                            "rerunning_ansys_after_section_upgrade"
                            if section_ratio_recovery
                            else "rerunning_ansys_after_final_ratio_recovery"
                        )
                        progress(
                            recovery_stage,
                            f"{item['job_id']}: {recovery_reason} Rerun with a larger reviewed SECT (attempt {upgrade_attempt}).",
                            min(base_progress + 78, 92),
                            job_id=item["job_id"],
                        )
                        upgrade = upgrade_square_section_after_ratio_fail(
                            job_dir,
                            config=config,
                            config_path=config_path,
                            confirm_user=confirm_user,
                            source_root=source_root,
                            limit=square_section_candidate_limit,
                            section_selection_only=section_ratio_recovery,
                            upgrade_reason=recovery_reason,
                        )
                        status_key = (
                            "square_section_upgrade_status"
                            if section_ratio_recovery
                            else "final_ratio_section_recovery_status"
                        )
                        row_result[status_key] = upgrade.get("status")
                        row_result["rerun_reason"] = recovery_mode
                        row_result["rerun_reason_detail"] = recovery_reason
                        selected_upgrade = upgrade.get("selected") or {}
                        if selected_upgrade:
                            row_result["square_section_selected"] = selected_upgrade.get("section_name")
                            row_result["square_section_selected_ratio"] = selected_upgrade.get("controlling_ratio")
                        if upgrade.get("status") != "pass":
                            row_result["support_spacing_recovery_status"] = "disabled_by_fixed_geometry_policy"
                            row_result["operator_recovery"] = {
                                "status": "input_revision_required",
                                "fixed_fields": ["support_spacing_m", "support_height_m"],
                                "allowed_action": "revise_confirmed_tray_line_load_and_rerun",
                                "reason": upgrade.get("reason") or upgrade.get("status"),
                            }
                            raise RuntimeError(
                                "All applicable square-section recovery attempts failed while support spacing and support "
                                "length are fixed by upstream layout. Automatic spacing/length reduction is disabled. "
                                "Review and explicitly revise the tray line load in the calculation workspace, then rerun."
                            )
                        cleanup_heavy_solver_artifacts(job_dir)
                        progress(
                            rerun_stage,
                            (
                                f"{item['job_id']}: selected {selected_upgrade.get('section_name')} for "
                                f"{recovery_mode}; rerun formal ANSYS."
                            ),
                            min(base_progress + 80, 94),
                            job_id=item["job_id"],
                        )
                        run_formal_ansys_once("（截面升级后）")
                    if result_validation_needs_square_section_upgrade(job_dir):
                        if provided_square_section_frozen:
                            raise RuntimeError(
                                "Fixed intake/report square section failed the final ratio gate; historical verification "
                                "does not silently change column-I square sections. Treat this as a computation/extraction "
                                "failure or a historical source conflict after report comparison."
                            )
                        raise RuntimeError("Square section upgrade loop ended but final square-support ratio is still above 1.0.")
                    if result_validation_needs_final_ratio_section_recovery(job_dir):
                        raise RuntimeError("Final ratio section-recovery loop ended while a larger allowed section was still available.")
                    _ensure_publishable_result(job_dir)
                    _sync_square_section_row_result_from_summary(row_result, job_dir)
                    modal_learning = record_modal_mode_count_learning(job_dir)
                    row_result["modal_learning_status"] = modal_learning.get("status")
                    row_result["modal_learning_recommended_mt"] = modal_learning.get("recommended_modal_mode_count")
                    register_exact_cached_result(job_dir, jobs_dir)
                    update_job_state(job_dir, "evaluated", "real ANSYS outputs parsed and evaluated")
            else:
                from core.ansys.runner import run_dry_ansys

                if square_section_auto_selection_required(job_dir):
                    row_result["square_section_selection_status"] = "pending_real_ansys_selection"
                progress("dry_run", f"{item['job_id']}：生成 dry-run 命令，不调用 ANSYS", base_progress + 60, job_id=item["job_id"])
                audit = run_dry_ansys(job_dir, config=config)
                row_result["ansys_run_status"] = audit.get("status")
                update_job_state(job_dir, "dry_run", "dry-run command generated")
            # Keep per-job progress below the final batch completion marker.
            # Otherwise the UI can show 100% while the job still needs to
            # parse, validate, publish, and write its final status.
            progress("publish_outputs", f"{item['job_id']}：发布输出文件到结果目录", _progress_stage_cap("publish_outputs"), job_id=item["job_id"])
            publish_key = str(row_result.get("report_number") or row_result.get("intake_order_id") or item["job_id"])
            publish = publish_result_outputs(
                job_dir,
                output_root=output_root,
                intake_order_id=item["job_id"] if publish_key in duplicate_publish_keys else None,
            )
            row_result["published_to"] = publish["target_dir"]
            if execute_real:
                artifact_cleanup = cleanup_heavy_solver_artifacts(job_dir)
                row_result["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
                row_result["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
            row_result["status"] = "pass" if execute_real else "dry_run"
        except Exception as exc:
            if execute_real and job_dir.exists():
                if _retain_solver_artifacts_after_failure(job_dir):
                    row_result["solver_artifact_cleanup_status"] = "skipped_post_export_license_failure"
                    row_result["solver_artifact_cleanup_policy"] = (
                        "Main ANSYS results are retained because the failure happened in post-only figure export "
                        "after a license-manager error. Keeping DB/RST allows a later figure-export retry without rerunning the solve."
                    )
                else:
                    artifact_cleanup = cleanup_heavy_solver_artifacts(job_dir)
                    row_result["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
                    row_result["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
            fail_job_state(job_dir, str(exc))
            row_result["status"] = "fail"
            row_result["failure_reason"] = str(exc)
            progress("failed", f"{item['job_id']}：{exc}", base_progress + 82, job_id=item["job_id"])
        job_results.append(row_result)
        job_finished_percent = max(_progress_stage_cap("job_finished"), 10 + int(index * 85 / total))
        progress("job_finished", f"{item['job_id']}：处理完成", min(job_finished_percent, 99), job_id=item["job_id"])

    payload = {
        "status": "pass" if all(item["status"] in {"pass", "dry_run"} for item in job_results) else "fail",
        "intake_path": str(intake_path),
        "spectrum_file": spectrum_text,
        "output_root": str(output_root),
        "execute_real": execute_real,
        "freeze_provided_square_sections": freeze_provided_square_sections,
        "exact_result_reuse_enabled": allow_exact_result_reuse,
        "ansys_auto_config": ansys_audit,
        "job_count": len(job_results),
        "jobs": job_results,
        "operator_policy": [
            "The operator uploads/selects intake and spectrum files; row numbers are not required.",
            "Output folders are named from formal report_number/calculation_batch when present; before that they use a provisional intake identity based on workbook, sheet, and serial.",
            "After the formal report number is added later, reconcile the workbook to bind existing jobs to the official identifier.",
            "Steel platform rows use static method, but the selected project spectrum workbook is still required for equivalent-static acceleration coefficients.",
            "Baseline comparison remains a developer verification tool and is not part of the main operator workflow.",
        ],
    }
    Path("docs").mkdir(parents=True, exist_ok=True)
    Path("docs/last_one_click_run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    progress("completed", "一键流程结束", 100, status=payload["status"])
    return payload
