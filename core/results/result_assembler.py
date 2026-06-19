from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.apdl.result_source_map import write_result_source_map
from core.evaluators.summary import build_audit_comments, build_evaluation_summary
from core.results.figure_collector import collect_figures
from core.results.lis_parser import (
    parse_beam_stress_lis,
    parse_bolt_force_lis,
    parse_connection_node_force_lis,
    parse_foundation_load_lis,
    parse_modal_oup,
    parse_weld_force_lis,
)
from core.schemas.input_models import parse_cable_input
from core.schemas.result_models import (
    BeamStressResult,
    FigureItem,
    ForceResult,
    FoundationLoad,
    MetricValue,
    ModalResult,
    ResultJson,
    model_to_dict,
)
from core.optimizer.square_section_summary import write_square_section_selection_summary
from core.validation.result_requirements import classify_job_requirements
from core.validation.result_validity_gate import validate_result_outputs


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_input_payload(job_dir: Path) -> dict[str, Any]:
    return json.loads((job_dir / "input.json").read_text(encoding="utf-8-sig"))


def _metric(value: float, unit: str, source_ref: str) -> MetricValue:
    return MetricValue(value=value, raw_value=value, unit=unit, source_ref=source_ref)


def _force_result(row: dict, value_units: dict[str, str]) -> ForceResult:
    source_ref = row["source_ref"]
    values = {
        key: _metric(float(row[key]), unit, source_ref)
        for key, unit in value_units.items()
        if key in row
    }
    return ForceResult(
        name=row["name"],
        load_case=row["load_case"],
        values=values,
        source_ref=source_ref,
        source_file=row.get("source_file"),
        source_hash=row.get("source_hash"),
        source_line=row.get("source_line"),
        source_block=row.get("source_block"),
        raw_value=row.get("raw_value"),
        normalized_value=row.get("normalized_value"),
        parser_version=row.get("parser_version"),
    )


def _parse_if_exists(path: Path, parser) -> list[dict]:
    return parser(path) if path.exists() else []


def _ensure_modal_output_file(job_dir: Path) -> dict[str, Any]:
    """Normalize source MAPDL modal output to Mode.oup when needed.

    Some audited S2 command streams write the modal frequency listing to
    8TEG*.TXT through /OUTPUT instead of the platform-standard Mode.oup name.
    The normalized file is still copied from real ANSYS text output; no modal
    frequency is synthesized here.
    """

    mode_path = job_dir / "Mode.oup"
    audit_path = job_dir / "modal_source_selection.json"
    if mode_path.exists():
        payload = {
            "status": "existing_mode_oup",
            "selected_source": mode_path.name,
            "normalized_target": mode_path.name,
        }
        _write_json(audit_path, payload)
        return payload

    candidates = sorted(job_dir.glob("8TEG*.TXT")) + sorted(job_dir.glob("8TEG*.txt"))
    candidates.extend([job_dir / "ansys.out"])
    checked: list[str] = []
    errors: list[dict[str, str]] = []
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        checked.append(candidate.name)
        try:
            rows = parse_modal_oup(candidate)
        except Exception as exc:
            errors.append({"file": candidate.name, "error": str(exc)})
            continue
        if not rows:
            continue
        shutil.copyfile(candidate, mode_path)
        payload = {
            "status": "normalized_from_ansys_output",
            "selected_source": candidate.name,
            "normalized_target": mode_path.name,
            "modal_row_count": len(rows),
            "mt_mode": rows[0].get("mt_mode"),
            "source_policy": (
                "Mode.oup was missing, so CableTrayAI copied the real MAPDL modal "
                "frequency output from the audited command stream output file."
            ),
            "checked_sources": checked,
        }
        _write_json(audit_path, payload)
        return payload

    payload = {
        "status": "missing_modal_output",
        "selected_source": None,
        "normalized_target": mode_path.name,
        "checked_sources": checked,
        "errors": errors,
    }
    _write_json(audit_path, payload)
    return payload


def _metric_number(value: Any) -> float | None:
    if isinstance(value, dict):
        return _metric_number(value.get("value", value.get("normalized_value", value.get("raw_value"))))
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _all_force_rows_zero(rows: list[dict], fields: tuple[str, ...] = ("fx", "fy", "fz", "mx", "my", "mz")) -> bool:
    if not rows:
        return True
    saw_value = False
    for row in rows:
        values = row.get("values") if isinstance(row.get("values"), dict) else {}
        for field in fields:
            number = _metric_number(row.get(field, values.get(field)))
            if number is None:
                continue
            saw_value = True
            if abs(number) > 1e-9:
                return False
    return True


def _connection_nodes_to_bolt_rows(rows: list[dict]) -> list[dict]:
    """Envelope connection-node export into the report bolt-load rows.

    Some standard PIP variants can leave the legacy two-line LS-FORCE.LIS at
    zero when the actual tray-arm connection element forces are available in
    LS-FORCE-NODES.LIS.  The fallback is limited to the standard suffix-9
    LS-FORCE keypoint family used by the shared S2 post stream. Other exported
    connection nodes remain diagnostic evidence and must not replace the
    published tray-arm connection-load selector.
    """

    selected_rows, topology_selection = _select_connection_node_rows_for_bolt_envelope(rows)

    envelopes: dict[str, dict[str, Any]] = {}
    for row in selected_rows:
        load_case = str(row.get("load_case") or "UNKNOWN")
        bucket = envelopes.setdefault(
            load_case,
            {
                "name": "BOLT_FORCE_CONNECTION_NODE_ENVELOPE",
                "load_case": load_case,
                "force_unit": "N",
                "moment_unit": "N*m",
                "result_kind": "tray_arm_connection_load",
                "source_ref": "LS-FORCE-NODES.LIS:connection-node-envelope",
                "source_file": row.get("source_file") or "LS-FORCE-NODES.LIS",
                "source_hash": row.get("source_hash"),
                "source_line": row.get("source_line"),
                "source_block": "LS-FORCE-NODES.LIS",
                "raw_value": row.get("raw_value"),
                "normalized_value": row.get("normalized_value"),
                "parser_version": row.get("parser_version"),
                "source_keypoints": [],
                "fallback_reason": "LS-FORCE.LIS is zero; using deterministic envelope from exported connection nodes.",
                "topology_selection": topology_selection,
                "fx": 0.0,
                "fy": 0.0,
                "fz": 0.0,
                "mx": 0.0,
                "my": 0.0,
                "mz": 0.0,
            },
        )
        keypoint = row.get("keypoint")
        if keypoint is not None and keypoint not in bucket["source_keypoints"]:
            bucket["source_keypoints"].append(keypoint)
        for field in ("fx", "fy", "fz", "mx", "my", "mz"):
            number = _metric_number(row.get(field))
            if number is None:
                continue
            bucket[field] = max(float(bucket[field]), abs(number))
            if abs(number) >= abs(float(bucket.get("normalized_value") or 0.0)):
                bucket["raw_value"] = str(number)
                bucket["normalized_value"] = abs(number)
    return list(envelopes.values())


def _select_connection_node_rows_for_bolt_envelope(rows: list[dict]) -> tuple[list[dict], dict[str, Any]]:
    """Choose the source-command bolt keypoint family before enveloping.

    The standard LS-FORCE block builds the tray-arm connection family with
    suffix-9 keypoints. Physical bolt keypoints such as suffix 6/7/8 and CP
    interface points are exported for diagnosis only; using them as a published
    replacement can hide a model/post topology mismatch.
    """

    usable = [row for row in rows if _metric_number(row.get("fx")) is not None]

    def _kp(row: dict) -> int:
        try:
            return int(row.get("keypoint") or 0)
        except (TypeError, ValueError):
            return 0

    def _select_by_suffix(suffixes: tuple[int, ...]) -> list[dict]:
        selected = []
        for row in usable:
            keypoint = _kp(row)
            if keypoint <= 0:
                continue
            if keypoint % 10 not in suffixes:
                continue
            if 500 <= keypoint < 10000:
                selected.append(row)
        return selected

    selected = _select_by_suffix((9,))
    if selected:
        selected_all_zero = _all_force_rows_zero(selected)
        return selected, {
            "status": "pass" if not selected_all_zero else "selected_all_zero",
            "policy": "standard_kyals_suffix_9",
            "selected_suffixes": [9],
            "selected_keypoints": sorted({_kp(row) for row in selected}),
            "diagnostic_keypoints": sorted({_kp(row) for row in usable if _kp(row) % 10 != 9}),
            "selected_all_zero": selected_all_zero,
            "source_ref": "generated_post.mac:KYALS / LS-FORCE-NODES.LIS",
        }
    return [], {
        "status": "missing_standard_suffix9",
        "policy": (
            "No non-zero suffix-9 LS-FORCE-NODES rows were exported. Suffix 6/7/8 physical bolt "
            "geometry or suffix-2 CP interface rows are diagnostic only and are not publishable as "
            "tray-arm connection loads."
        ),
        "selected_suffixes": [9],
        "selected_keypoints": [],
        "diagnostic_keypoints": sorted({_kp(row) for row in usable}),
        "selected_all_zero": True,
        "source_ref": "generated_post.mac:KYALS / LS-FORCE-NODES.LIS",
    }


def assemble_result(job_dir: Path | str) -> dict:
    job_dir = Path(job_dir)
    cable_input = parse_cable_input(_read_input_payload(job_dir))
    result_source_map = write_result_source_map(job_dir) if (job_dir / "generated_post.mac").exists() else {"outputs": {}}
    classify_job_requirements(job_dir)

    modal_source_selection = _ensure_modal_output_file(job_dir)
    modal_rows = _parse_if_exists(job_dir / "Mode.oup", parse_modal_oup)
    beam_rows = []
    for name in ("SQUAREBEAMSTRESS.LIS", "MAXBEAMSTRESS.LIS", "TMAXBEAMSTRESS.LIS"):
        path = job_dir / name
        if path.exists():
            source_info = (result_source_map.get("outputs") or {}).get(name, {})
            for row in parse_beam_stress_lis(path):
                row["component_scope"] = source_info.get("component_scope")
                row["report_component_hint"] = source_info.get("report_component_hint")
                row["source_selection_ref"] = source_info.get("source_ref")
                beam_rows.append(row)
    weld_rows = _parse_if_exists(job_dir / "HF-FORCE.LIS", parse_weld_force_lis)
    bolt_rows = _parse_if_exists(job_dir / "LS-FORCE.LIS", parse_bolt_force_lis)
    connection_node_rows = _parse_if_exists(job_dir / "LS-FORCE-NODES.LIS", parse_connection_node_force_lis)
    legacy_bolt_rows = list(bolt_rows)
    bolt_source_selection = {
        "selected_source": "LS-FORCE.LIS",
        "fallback_used": False,
        "legacy_ls_force_rows": len(legacy_bolt_rows),
        "connection_node_rows": len(connection_node_rows),
    }
    if _all_force_rows_zero(bolt_rows) and not _all_force_rows_zero(connection_node_rows):
        _, topology_selection = _select_connection_node_rows_for_bolt_envelope(connection_node_rows)
        bolt_rows = _connection_nodes_to_bolt_rows(connection_node_rows)
        bolt_source_selection.update(
            {
                "selected_source": "LS-FORCE-NODES.LIS",
                "fallback_used": True,
                "fallback_reason": "LS-FORCE.LIS parsed as all zero while LS-FORCE-NODES.LIS contains non-zero connection loads.",
                "envelope_rows": len(bolt_rows),
                "topology_selection": topology_selection,
            }
        )
    foundation_rows = _parse_if_exists(job_dir / "JCZH.LIS", parse_foundation_load_lis)
    figures = collect_figures(job_dir, output_manifest=True)

    raw = {
        "SQUAREBEAMSTRESS.LIS": parse_beam_stress_lis(job_dir / "SQUAREBEAMSTRESS.LIS") if (job_dir / "SQUAREBEAMSTRESS.LIS").exists() else [],
        "MAXBEAMSTRESS.LIS": parse_beam_stress_lis(job_dir / "MAXBEAMSTRESS.LIS") if (job_dir / "MAXBEAMSTRESS.LIS").exists() else [],
        "TMAXBEAMSTRESS.LIS": parse_beam_stress_lis(job_dir / "TMAXBEAMSTRESS.LIS") if (job_dir / "TMAXBEAMSTRESS.LIS").exists() else [],
        "Mode.oup": modal_rows,
        "HF-FORCE.LIS": weld_rows,
        "LS-FORCE.LIS": legacy_bolt_rows,
        "LS-FORCE.SELECTED": bolt_rows,
        "LS-FORCE-NODES.LIS": connection_node_rows,
        "JCZH.LIS": foundation_rows,
        "modal_source_selection": modal_source_selection,
        "missing_expected_files": [
            name
            for name in ("Mode.oup", "MAXBEAMSTRESS.LIS", "HF-FORCE.LIS", "LS-FORCE.LIS", "JCZH.LIS")
            if not (job_dir / name).exists()
        ],
    }
    _write_json(job_dir / "result_raw.json", raw)
    _write_json(job_dir / "modal_results.json", modal_rows)
    _write_json(job_dir / "beam_stress_results.json", beam_rows)
    _write_json(job_dir / "weld_force_results.json", weld_rows)
    _write_json(job_dir / "bolt_force_results.json", bolt_rows)
    _write_json(job_dir / "bolt_force_source_selection.json", bolt_source_selection)
    _write_json(job_dir / "connection_node_force_results.json", connection_node_rows)
    _write_json(job_dir / "foundation_loads.json", foundation_rows)

    result = ResultJson(
        project=model_to_dict(cable_input.project),
        modal_results=[ModalResult(**row) for row in modal_rows],
        beam_stress_results=[BeamStressResult(**row) for row in beam_rows],
        weld_force_results=[
            _force_result(
                row,
                {
                    "force_n": "N",
                    "fx": "N",
                    "fy": "N",
                    "fz": "N",
                    "mx": "N*m",
                    "my": "N*m",
                    "mz": "N*m",
                    "stress_mpa": "MPa",
                    "allowable_mpa": "MPa",
                },
            )
            for row in weld_rows
        ],
        bolt_force_results=[
            _force_result(
                row,
                {
                    "tension_mpa": "MPa",
                    "shear_mpa": "MPa",
                    "allowable_tension_mpa": "MPa",
                    "allowable_shear_mpa": "MPa",
                    "fx": "N",
                    "fy": "N",
                    "fz": "N",
                    "mx": "N*m",
                    "my": "N*m",
                    "mz": "N*m",
                },
            )
            for row in bolt_rows
        ],
        foundation_loads=[FoundationLoad(**row) for row in foundation_rows],
        figures=[FigureItem(**row) for row in figures],
        raw_files={
            "beam_stress": "beam_stress_results.json",
            "modal": "modal_results.json",
            "weld_force": "weld_force_results.json",
            "bolt_force": "bolt_force_results.json",
            "foundation_loads": "foundation_loads.json",
            "result_source_map": "result_source_map.json",
        },
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    result_dict = model_to_dict(result)
    result_dict["figures"] = figures
    result_dict["connection_node_force_results"] = connection_node_rows
    evaluation_summary = build_evaluation_summary(result_dict, cable_input)
    result_dict["evaluation_summary"] = evaluation_summary
    result_validation = validate_result_outputs(job_dir, raw=raw, result=result_dict)
    result_dict["result_validation"] = result_validation
    result_dict["result_status"] = "blocked" if result_validation["status"] == "fail" else "usable"
    _write_json(job_dir / "evaluation_summary.json", evaluation_summary)
    _write_json(job_dir / "audit_comments.json", build_audit_comments(evaluation_summary))
    try:
        result_dict["square_section_selection_summary"] = write_square_section_selection_summary(job_dir)
    except Exception as exc:
        result_dict["square_section_selection_summary"] = {
            "status": "warning",
            "reason": str(exc),
        }
    _write_json(job_dir / "result.json", result_dict)
    try:
        from core.ai.model_client import audit_postprocess_with_model

        postprocess_qc = audit_postprocess_with_model(job_dir, result=result_dict)
        result_dict["postprocess_ai_qc"] = {
            "status": postprocess_qc.get("status"),
            "model_status": postprocess_qc.get("model_status"),
            "file": "postprocess_ai_qc.json",
        }
        _write_json(job_dir / "result.json", result_dict)
    except Exception as exc:
        _write_json(
            job_dir / "postprocess_ai_qc.json",
            {
                "status": "warning",
                "provider": "internal",
                "issue": "postprocess AI/rule QC failed to run",
                "error": str(exc),
                "authority_policy": "This file is advisory; result_validation and deterministic evaluation remain authoritative.",
            },
        )
    return result_dict
