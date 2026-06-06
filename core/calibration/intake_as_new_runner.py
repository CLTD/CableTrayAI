from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from core.ansys.artifact_cleanup import cleanup_heavy_solver_artifacts
from core.ansys.config import AnsysExecutableConfig, AnsysLocalConfig, AnsysRunnerConfig, load_ansys_config
from core.ansys.lock_cleanup import cleanup_stale_ansys_locks
from core.ansys.runner import run_real_ansys
from core.apdl.source_conflict_resolver import apply_source_conflict_resolutions
from core.apdl.intake_standard_family_renderer import (
    find_adjacent_solve_command,
    render_intake_standard_family_commands,
    select_standard_model_family,
)
from core.apdl.template_renderer import render_apdl_templates
from core.calibration.report_intake_matcher import select_representative_intake_rows, write_selection_audit
from core.calibration.sample_inventory import discover_report_command_cases
from core.intake.intake_excel_reader import read_tabular_intake_rows
from core.intake.job_input_builder import create_job_from_intake
from core.results.output_workspace import DEFAULT_OUTPUT_ROOT, publish_result_outputs
from core.results.result_assembler import assemble_result
from core.spectra.response_spectrum_writer import write_segmented_response_spectrum_mac
from core.validation.report_baseline import extract_report_baseline, write_report_baseline_comparison


DEFAULT_INTAKE_PATTERN = "*S2*.xlsx"
DEFAULT_OUTPUT_JSON = Path("docs/precision_gate/intake_as_new_precision_batch.json")
DEFAULT_REPORT_OUTPUT_JSON = Path("docs/precision_gate/intake_as_new_report_precision_batch.json")
DEFAULT_SPECTRUM_PATTERNS = ("*楼层谱*ANSYS格式*标高线性*.xlsm", "*楼层谱*.xlsm", "*楼层谱*.xlsx")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_token(value: Any) -> str:
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "").strip())
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text or "unknown"


def find_default_intake_workbook(source_root: Path | str = Path("source_materials/model_commands")) -> Path:
    source_root = Path(source_root)
    candidates = [
        path
        for path in source_root.rglob(DEFAULT_INTAKE_PATTERN)
        if path.is_file() and not path.name.startswith("~$")
    ]
    for candidate in candidates:
        try:
            rows = read_tabular_intake_rows(candidate)
        except Exception:
            continue
        if rows:
            return candidate
    raise FileNotFoundError(f"No tabular S2 intake workbook found under {source_root}")


def find_default_spectrum_workbook(source_root: Path | str = Path("source_materials/model_commands")) -> Path | None:
    source_root = Path(source_root)
    for pattern in DEFAULT_SPECTRUM_PATTERNS:
        candidates = sorted(
            path
            for path in source_root.rglob(pattern)
            if path.is_file() and not path.name.startswith("~$")
        )
        if candidates:
            return candidates[0]
    return None


def discover_intake_as_new_cases(
    *,
    intake_path: Path | str | None = None,
    source_root: Path | str = Path("source_materials/model_commands"),
) -> dict[str, Any]:
    source_root = Path(source_root)
    intake_path = Path(intake_path) if intake_path else find_default_intake_workbook(source_root)
    rows = read_tabular_intake_rows(intake_path)
    reports = {
        str(case.get("report_no")): case
        for case in discover_report_command_cases(source_root)
        if case.get("report_docx")
    }
    matched_rows = [
        {
            "report_no": str(row.get("report_number") or row.get("calculation_batch") or row.get("intake_order_id")),
            "intake_row_number": row.get("intake_row_number"),
            "intake_serial": row.get("intake_serial"),
            "analysis_method": row.get("analysis_method"),
            "square_section_spec": row.get("square_section_spec"),
            "building": row.get("building"),
            "elevation": row.get("elevation"),
            "support_spacing_m": row.get("support_spacing_m"),
            "support_height_m": row.get("support_height_m"),
            "baseline_report": reports[str(row.get("report_number") or row.get("calculation_batch") or row.get("intake_order_id"))]["report_docx"],
        }
        for row in rows
        if str(row.get("report_number") or row.get("calculation_batch") or row.get("intake_order_id")) in reports
    ]
    counts = Counter(item["report_no"] for item in matched_rows)
    return {
        "status": "pass" if matched_rows else "fail",
        "intake_path": str(intake_path),
        "source_root": str(source_root),
        "intake_row_count": len(rows),
        "historical_report_count": len(reports),
        "matched_row_count": len(matched_rows),
        "matched_report_count": len(set(item["report_no"] for item in matched_rows)),
        "duplicate_report_rows": {key: value for key, value in sorted(counts.items()) if value > 1},
        "cases": matched_rows,
        "policy": (
            "Historical reports are used only as baselines. Each validation job is generated from the intake row "
            "through the current command renderer; report command packages are not copied or auto-resolved."
        ),
    }


def select_intake_as_new_report_cases(
    *,
    intake_path: Path | str | None = None,
    source_root: Path | str = Path("source_materials/model_commands"),
    report_numbers: list[str] | None = None,
) -> dict[str, Any]:
    source_root = Path(source_root)
    intake_path = Path(intake_path) if intake_path else find_default_intake_workbook(source_root)
    rows = read_tabular_intake_rows(intake_path)
    reports = {
        str(case.get("report_no")): str(case.get("report_docx"))
        for case in discover_report_command_cases(source_root)
        if case.get("report_docx")
    }
    requested = {str(item).strip() for item in (report_numbers or []) if str(item).strip()}
    if requested:
        reports = {key: value for key, value in reports.items() if key in requested}
    selection = select_representative_intake_rows(rows, reports)
    selection.update(
        {
            "intake_path": str(intake_path),
            "source_root": str(source_root),
            "available_report_count": len(reports),
            "intake_row_count": len(rows),
        }
    )
    return selection


def _write_connection_export_requirement(job_dir: Path, baseline_report: Path | str) -> dict[str, Any]:
    baseline_report = Path(baseline_report)
    try:
        baseline = extract_report_baseline(baseline_report)
        required_rows = [
            row
            for row in baseline.get("loads", [])
            if row.get("result_source_file") == "LS-FORCE-NODES.LIS"
            or row.get("load_kind") == "tray_arm_connection_derived_bolt_load"
        ]
        payload = {
            "required": bool(required_rows),
            "required_count": len(required_rows),
            "source": str(baseline_report),
            "policy": "Run expensive connection-node export only when the report mapping declares LS-FORCE-NODES.LIS or derived tray-arm bolt-load rows.",
        }
    except Exception as exc:
        payload = {
            "required": True,
            "required_count": None,
            "source": str(baseline_report),
            "error": str(exc),
            "policy": "Fallback to running connection-node export if the report mapping cannot be inspected.",
        }
    (job_dir / "connection_node_export_required.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def _check(status: str, check_id: str, message: str, evidence: str = "", suggested_fix: str = "") -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "message": message,
        "evidence": evidence,
        "suggested_fix": suggested_fix,
    }


def audit_intake_generated_commands(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    input_payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    metadata = input_payload.get("metadata") or {}
    model_text = _read_text(job_dir / "generated_model.mac")
    solve_text = _read_text(job_dir / "generated_solve.mac")
    post_text = _read_text(job_dir / "generated_post.mac")
    checks: list[dict[str, Any]] = []

    for filename, text in (
        ("generated_model.mac", model_text),
        ("generated_solve.mac", solve_text),
        ("generated_post.mac", post_text),
    ):
        checks.append(
            _check(
                "pass" if text.strip() else "fail",
                f"{filename}.exists",
                f"{filename} must be generated for engineering review.",
                filename,
            )
        )

    checks.append(
        _check(
            "fail" if "Stage 1 S2 parameterized geometry template" in model_text else "pass",
            "model.not_stage1_skeleton",
            "The intake-as-new gate cannot use the Stage 1 simplified geometry skeleton.",
            "Stage 1 S2 parameterized geometry template" if "Stage 1 S2 parameterized geometry template" in model_text else "",
            "Port the standard S2 model topology into the parameter renderer so tray layers, sides, CP interfaces, and section families come from the intake.",
        )
    )
    checks.append(
        _check(
            "fail" if "Placeholder response-spectrum points" in solve_text else "pass",
            "solve.no_placeholder_spectrum",
            "Response-spectrum jobs must use the selected spectrum workbook, not placeholder spectrum points.",
            "Placeholder response-spectrum points" if "Placeholder response-spectrum points" in solve_text else "",
            "Render ansys_spectrum.mac from the confirmed workbook and include it in generated_solve.mac.",
        )
    )
    checks.append(
        _check(
            "fail" if "Stage 1 post-processing skeleton" in post_text else "pass",
            "post.not_stage1_skeleton",
            "The post processor must be the audited S2 extraction logic, not the Stage 1 placeholder skeleton.",
            "Stage 1 post-processing skeleton" if "Stage 1 post-processing skeleton" in post_text else "",
            "Generate MAXBEAMSTRESS/TMAXBEAMSTRESS/HF-FORCE/LS-FORCE/JCZH from the model-declared component sets and report-table mapping.",
        )
    )
    placeholder_force_patterns = (
        "*VWRITE,'A','WELD',0,0,0",
        "*VWRITE,'A','BOLT',0,0,0,0",
        "*VWRITE,'A',0,0,0,0,0,0,0",
    )
    found_force_placeholders = [pattern for pattern in placeholder_force_patterns if pattern in post_text]
    checks.append(
        _check(
            "fail" if found_force_placeholders else "pass",
            "post.no_zero_force_placeholders",
            "Load result files must be extracted from ANSYS result sets; zero placeholder rows are forbidden.",
            "; ".join(found_force_placeholders),
            "Replace zero VWRITE rows with FSUM/PRRSOL/ETABLE extraction over the exact support, weld, and tray-arm connection sets.",
        )
    )

    analysis_method = str(metadata.get("analysis_method") or "")
    if analysis_method == "static":
        checks.append(
            _check(
                "fail" if "ANTYPE,8" in solve_text.upper() else "pass",
                "solve.static_without_spectrum_analysis",
                "Steel-platform intake rows must use static method and must not run response-spectrum analysis.",
                "ANTYPE,8" if "ANTYPE,8" in solve_text.upper() else "",
                "Render a static-only solve command for steel-platform rows.",
            )
        )
    else:
        checks.append(
            _check(
                "pass" if "ANTYPE,8" in solve_text.upper() else "fail",
                "solve.response_spectrum_present",
                "Non-steel-platform rows require response-spectrum analysis.",
                "ANTYPE,8" if "ANTYPE,8" in solve_text.upper() else "",
            )
        )

    checks.append(
        _check(
            "pass" if metadata.get("tray_load_mapping_status") == "pass" else "fail",
            "intake.tray_loads_structured",
            "The intake tray-load text must be parsed into front/back layer geometry and equivalent tray density before ANSYS runs.",
            str(metadata.get("tray_load_description") or metadata.get("raw_intake_row") or "")[:300],
            "Add a deterministic tray-load parser and write tray_load_mapping_status=pass only after generated_model.mac reflects the parsed layers.",
        )
    )

    failures = [item for item in checks if item["status"] == "fail"]
    payload = {
        "status": "pass" if not failures else "blocked",
        "precision_gate_allowed": not failures,
        "job_dir": str(job_dir),
        "report_number": metadata.get("report_number"),
        "intake_row_number": metadata.get("intake_row_number"),
        "analysis_method": analysis_method,
        "checks": checks,
        "failure_count": len(failures),
        "policy": "Do not run real ANSYS for intake-as-new validation unless generated commands are production-grade and traceable.",
    }
    _write_json(job_dir / "intake_generated_command_audit.json", payload)
    return payload


def run_intake_as_new_precision_batch(
    *,
    intake_path: Path | str | None = None,
    source_root: Path | str = Path("source_materials/model_commands"),
    jobs_root: Path | str | None = None,
    spectrum_file: Path | str | None = None,
    template_dir: Path | str = Path("templates/apdl"),
    limit: int | None = None,
    report_numbers: list[str] | None = None,
    output_json: Path | str = DEFAULT_OUTPUT_JSON,
) -> dict[str, Any]:
    discovered = discover_intake_as_new_cases(intake_path=intake_path, source_root=source_root)
    selected = list(discovered.get("cases") or [])
    requested = {str(item).strip() for item in (report_numbers or []) if str(item).strip()}
    if requested:
        selected = [case for case in selected if str(case.get("report_no")) in requested]
    if limit is not None:
        selected = selected[:limit]

    if spectrum_file is None:
        spectrum_file = find_default_spectrum_workbook(source_root)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jobs_root = Path(jobs_root) if jobs_root else Path("jobs/intake_as_new_runs") / timestamp / "workspaces"
    jobs_root.mkdir(parents=True, exist_ok=True)
    intake_path = Path(discovered["intake_path"])
    results: list[dict[str, Any]] = []

    for case in selected:
        report_no = str(case.get("report_no") or "")
        serial = case.get("intake_serial") or case.get("intake_row_number")
        workspace_id = f"{_safe_token(report_no)}__row_{_safe_token(serial)}"
        row_result: dict[str, Any] = {
            "report_no": report_no,
            "intake_serial": serial,
            "intake_row_number": case.get("intake_row_number"),
            "baseline_report": case.get("baseline_report"),
            "workspace_id": workspace_id,
            "status": "created",
        }
        try:
            created = create_job_from_intake(
                intake_path,
                jobs_dir=jobs_root,
                job_id=workspace_id,
                spectrum_file=str(spectrum_file) if spectrum_file else None,
                spectrum_confirmed=bool(spectrum_file),
                row_number=int(case["intake_row_number"]),
            )
            job_dir = Path(created["job_dir"])
            render = render_intake_standard_family_commands(
                workspace_id,
                job_dir / "input.json",
                jobs_dir=jobs_root,
                template_dir=template_dir,
                source_root=source_root,
            )
            readiness = audit_intake_generated_commands(job_dir)
            row_result.update(
                {
                    "job_dir": str(job_dir),
                    "command_source": "intake_parameterized_standard_command_family",
                    "render_status": render.get("apdl_audit", {}).get("status"),
                    "command_readiness_status": readiness.get("status"),
                    "command_failure_count": readiness.get("failure_count"),
                    "status": "blocked" if readiness.get("status") != "pass" else "ready_for_real_ansys",
                    "failure_reason": None
                    if readiness.get("status") == "pass"
                    else "software-generated command streams are not production-ready for intake-as-new validation",
                }
            )
        except Exception as exc:
            row_result["status"] = "fail"
            row_result["failure_reason"] = str(exc)
        results.append(row_result)

    blocked = [row for row in results if row.get("status") != "ready_for_real_ansys"]
    payload = {
        "status": "pass" if results and not blocked else "blocked",
        "dataset": "intake_as_new",
        "policy": (
            "Treat historical intake rows as new intake. Generate commands from the current software only, then compare "
            "real ANSYS results with the matching report. Historical command packages are forbidden in this gate."
        ),
        "intake_path": str(intake_path),
        "jobs_root": str(jobs_root),
        "spectrum_file": str(spectrum_file) if spectrum_file else None,
        "spectrum_file_policy": "auto_discovered_from_source_root" if spectrum_file else "not_available",
        "selected_case_count": len(selected),
        "prepared_case_count": len(results),
        "ready_for_real_ansys_count": len(results) - len(blocked),
        "blocked_case_count": len(blocked),
        "results": results,
        "discovery": {
            key: value
            for key, value in discovered.items()
            if key not in {"cases"}
        },
    }
    output_json = Path(output_json)
    _write_json(output_json, payload)
    _write_markdown(output_json.with_suffix(".md"), payload)
    return payload


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


def run_intake_as_new_report_precision_batch(
    *,
    intake_path: Path | str | None = None,
    source_root: Path | str = Path("source_materials/model_commands"),
    jobs_root: Path | str | None = None,
    spectrum_file: Path | str | None = None,
    template_dir: Path | str = Path("templates/apdl"),
    report_numbers: list[str] | None = None,
    limit: int | None = None,
    output_json: Path | str = DEFAULT_REPORT_OUTPUT_JSON,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    config_path: Path | str = Path("config/ansys.local.toml"),
    tolerance: float = 0.01,
    nproc: int = 0,
    timeout_minutes: int = 120,
    run_real: bool = True,
    publish_outputs: bool = True,
) -> dict[str, Any]:
    source_root = Path(source_root)
    selection = select_intake_as_new_report_cases(
        intake_path=intake_path,
        source_root=source_root,
        report_numbers=report_numbers,
    )
    selected = list(selection.get("selected") or [])
    if limit is not None:
        selected = selected[:limit]
    if spectrum_file is None:
        spectrum_file = find_default_spectrum_workbook(source_root)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jobs_root = Path(jobs_root) if jobs_root else Path("jobs/intake_as_new_report_runs") / timestamp / "workspaces"
    jobs_root.mkdir(parents=True, exist_ok=True)
    output_json = Path(output_json)
    write_selection_audit(output_json.with_name("intake_as_new_report_selection.json"), selection)
    config = _config_with_overrides(config_path=config_path, nproc=nproc, timeout_minutes=timeout_minutes)
    intake_path = Path(selection["intake_path"])
    results: list[dict[str, Any]] = []

    def write_progress(in_progress: bool) -> dict[str, Any]:
        payload = _report_summary_payload(
            selection=selection,
            selected=selected,
            results=results,
            jobs_root=jobs_root,
            spectrum_file=spectrum_file,
            tolerance=tolerance,
            nproc=nproc,
            run_real=run_real,
            in_progress=in_progress,
        )
        _write_json(output_json, payload)
        _write_markdown(output_json.with_suffix(".md"), payload)
        return payload

    write_progress(in_progress=True)
    for case in selected:
        report_no = str(case.get("report_no") or "").strip()
        workspace_id = _safe_token(report_no)
        row_result: dict[str, Any] = {
            "report_no": report_no,
            "workspace_id": workspace_id,
            "intake_row_number": case.get("intake_row_number"),
            "intake_serial": case.get("intake_serial"),
            "baseline_report": case.get("baseline_report"),
            "selection_score": case.get("score"),
            "selection_tie_count": case.get("tie_count"),
            "selection_conflict_status": case.get("selection_conflict_status"),
            "status": "created",
        }
        if case.get("selection_conflict_status") == "conflict":
            row_result.update(
                {
                    "status": "baseline_conflict",
                    "failure_reason": case.get("selection_conflict_reason"),
                    "failed_required_checks": case.get("failed_required_checks") or [],
                    "policy": (
                        "This case is excluded from the numerical precision gate because the historical intake row "
                        "and report design facts conflict before ANSYS is run. It is not a model-tuning target."
                    ),
                }
            )
            results.append(row_result)
            write_progress(in_progress=True)
            continue
        try:
            created = create_job_from_intake(
                intake_path,
                jobs_dir=jobs_root,
                job_id=workspace_id,
                spectrum_file=str(spectrum_file) if spectrum_file else None,
                spectrum_confirmed=bool(spectrum_file),
                row_number=int(case["intake_row_number"]),
            )
            job_dir = Path(created["job_dir"])
            row_result["job_dir"] = str(job_dir)
            (job_dir / "report_intake_selection.json").write_text(
                json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            input_payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
            metadata = input_payload.get("metadata") or {}
            static_elevations = (case.get("report_features") or {}).get("static_spectrum_elevations") or []
            if len(static_elevations) >= 2 and metadata.get("analysis_method") == "static":
                metadata["static_elevation_candidates"] = static_elevations
                metadata["static_elevation_candidates_source"] = (
                    "baseline_report_load_description_for_validation_only; production UI must provide/confirm "
                    "static-method envelope elevations from the selected spectrum workbook."
                )
                input_payload["metadata"] = metadata
                (job_dir / "input.json").write_text(
                    json.dumps(input_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            if metadata.get("analysis_method") != "static":
                if not spectrum_file:
                    raise ValueError("Response-spectrum validation requires a selected spectrum workbook.")
                family = select_standard_model_family(input_payload, source_root)
                frequency_guide_source = find_adjacent_solve_command(family["source"])
                spectrum_audit = write_segmented_response_spectrum_mac(
                    spectrum_file,
                    job_dir,
                    project_code=str(input_payload.get("project", {}).get("project_code") or ""),
                    building=str(input_payload.get("project", {}).get("building") or ""),
                    elevation=float(input_payload.get("project", {}).get("elevation") or 0.0),
                    frequency_guide_source=frequency_guide_source,
                )
                row_result["spectrum_status"] = spectrum_audit.get("status")
            render = render_intake_standard_family_commands(
                workspace_id,
                job_dir / "input.json",
                jobs_dir=jobs_root,
                template_dir=template_dir,
                source_root=source_root,
            )
            source_conflict = apply_source_conflict_resolutions(job_dir, package_id=report_no)
            readiness = audit_intake_generated_commands(job_dir)
            row_result["command_source"] = "intake_parameterized_standard_command_family"
            row_result["render_status"] = render.get("apdl_audit", {}).get("status")
            row_result["source_conflict_resolution_status"] = source_conflict.get("status")
            row_result["command_readiness_status"] = readiness.get("status")
            row_result["command_failure_count"] = readiness.get("failure_count")
            if readiness.get("status") != "pass":
                row_result["status"] = "blocked"
                row_result["failure_reason"] = "software-generated command streams are not production-ready for intake-as-new validation"
                results.append(row_result)
                write_progress(in_progress=True)
                continue
            if not run_real:
                row_result["status"] = "ready_for_real_ansys"
                results.append(row_result)
                write_progress(in_progress=True)
                continue
            connection_requirement = _write_connection_export_requirement(job_dir, case["baseline_report"])
            row_result["connection_node_export_required"] = connection_requirement.get("required")
            cleanup = cleanup_stale_ansys_locks(job_dir)
            row_result["lock_cleanup_status"] = cleanup.get("status")
            ansys_audit = run_real_ansys(
                job_dir,
                config=config,
                config_path=config_path,
                confirm_real_run=True,
                confirm_user="intake_as_new_report_precision_batch",
            )
            row_result["ansys_status"] = ansys_audit.get("status")
            row_result["returncode"] = ansys_audit.get("returncode")
            row_result["ansys_nproc_request"] = nproc
            if ansys_audit.get("status") != "success":
                row_result["status"] = "fail"
                row_result["failure_reason"] = f"ANSYS status {ansys_audit.get('status')}"
                artifact_cleanup = cleanup_heavy_solver_artifacts(job_dir)
                row_result["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
                row_result["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
                results.append(row_result)
                write_progress(in_progress=True)
                continue
            result = assemble_result(job_dir)
            result_validation = result.get("result_validation") or {}
            comparison = write_report_baseline_comparison(job_dir, case["baseline_report"], tolerance=tolerance)
            publish = (
                publish_result_outputs(job_dir, output_root=output_root, intake_order_id=report_no, overwrite=True)
                if publish_outputs
                else {}
            )
            validation_failed_checks = [
                item.get("check_id")
                for item in result_validation.get("checks") or []
                if item.get("status") == "fail"
            ]
            comparison_status = comparison.get("status")
            validation_status = result_validation.get("status")
            comparison_conflict_count = int(comparison.get("baseline_conflict_count") or 0)
            comparison_has_only_conflicts = comparison_status == "pass" and comparison_conflict_count > 0 and comparison.get("max_gate_error") is None
            combined_status = (
                "baseline_conflict"
                if validation_status == "pass" and comparison_has_only_conflicts
                else ("pass" if comparison_status == "pass" and validation_status == "pass" else "fail")
            )
            row_result.update(
                {
                    "comparison_status": comparison_status,
                    "comparison_baseline_conflict_count": comparison_conflict_count,
                    "result_validation_status": validation_status,
                    "result_validation_fail_count": result_validation.get("fail_count"),
                    "result_validation_failed_checks": validation_failed_checks,
                    "comparison_count": len(comparison.get("comparisons") or []),
                    "max_relative_error": comparison.get("max_relative_error"),
                    "max_absolute_error": comparison.get("max_absolute_error"),
                    "max_gate_error": comparison.get("max_gate_error"),
                    "modal_count": len(result.get("modal_results") or []),
                    "beam_count": len(result.get("beam_stress_results") or []),
                    "weld_count": len(result.get("weld_force_results") or []),
                    "bolt_count": len(result.get("bolt_force_results") or []),
                    "foundation_count": len(result.get("foundation_loads") or []),
                    "figure_count": len(result.get("figures") or []),
                    "published_to": publish.get("target_dir"),
                    "status": combined_status,
                    "failure_reason": None
                    if combined_status in {"pass", "baseline_conflict"}
                    else (
                        "result_validation failed: " + ", ".join(validation_failed_checks)
                        if validation_status != "pass"
                        else f"report comparison status {comparison_status}"
                    ),
                }
            )
            artifact_cleanup = cleanup_heavy_solver_artifacts(job_dir)
            row_result["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
            row_result["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
        except Exception as exc:
            if row_result.get("job_dir"):
                artifact_cleanup = cleanup_heavy_solver_artifacts(row_result["job_dir"])
                row_result["solver_artifact_cleanup_status"] = artifact_cleanup.get("status")
                row_result["solver_artifact_removed_gb"] = artifact_cleanup.get("removed_gb")
            row_result["status"] = "fail"
            row_result["failure_reason"] = str(exc)
        results.append(row_result)
        write_progress(in_progress=True)
    return write_progress(in_progress=False)


def _report_summary_payload(
    *,
    selection: dict[str, Any],
    selected: list[dict[str, Any]],
    results: list[dict[str, Any]],
    jobs_root: Path,
    spectrum_file: Path | str | None,
    tolerance: float,
    nproc: int,
    run_real: bool,
    in_progress: bool,
) -> dict[str, Any]:
    pass_like = {"pass", "ready_for_real_ansys", "baseline_conflict"}
    failed = [row for row in results if row.get("status") not in pass_like]
    max_gate_error = max(
        (
            float(row["max_gate_error"])
            for row in results
            if isinstance(row.get("max_gate_error"), (int, float))
        ),
        default=None,
    )
    all_passed = results and len(results) == len(selected) and all(row.get("status") in pass_like for row in results)
    return {
        "status": "running" if in_progress else ("pass" if all_passed else "fail"),
        "dataset": "intake_as_new_report_level",
        "policy": "Treat each baseline report as one validation case. Select the representative intake row by report design facts and intake fields, then generate commands from the current software only.",
        "tolerance": tolerance,
        "nproc": nproc,
        "run_real": run_real,
        "jobs_root": str(jobs_root),
        "spectrum_file": str(spectrum_file) if spectrum_file else None,
        "available_report_count": selection.get("available_report_count"),
        "selected_case_count": len(selected),
        "case_count": len(results),
        "passed_case_count": len([row for row in results if row.get("status") == "pass"]),
        "baseline_conflict_case_count": len([row for row in results if row.get("status") == "baseline_conflict"]),
        "failed_case_count": len([row for row in results if row.get("status") == "fail"]),
        "blocked_case_count": len([row for row in results if row.get("status") == "blocked"]),
        "ready_case_count": len([row for row in results if row.get("status") == "ready_for_real_ansys"]),
        "max_gate_error": max_gate_error,
        "selection_blocked": selection.get("blocked") or [],
        "failure_count": len(failed),
        "results": results,
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Intake-As-New Precision Batch",
        "",
        f"- status: {payload.get('status')}",
        f"- selected_case_count: {payload.get('selected_case_count')}",
        f"- ready_for_real_ansys_count: {payload.get('ready_for_real_ansys_count')}",
        f"- blocked_case_count: {payload.get('blocked_case_count')}",
        "",
        "## Policy",
        "",
        str(payload.get("policy")),
        "",
        "## Blocked Cases",
        "",
    ]
    for row in payload.get("results") or []:
        if row.get("status") != "ready_for_real_ansys":
            lines.append(f"- {row.get('workspace_id')}: {row.get('failure_reason')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
