from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from uuid import uuid4

from core.apdl.modal_policy import coerce_modal_mode_count, modal_mode_count_from_payload, modal_policy_audit
from core.intake.intake_excel_reader import read_and_validate_intake, read_tabular_intake_rows
from core.intake.tray_load_parser import parse_tray_load_description
from core.audit.job_state import write_job_state
from core.evaluators.material_policy import material_policy_metadata, production_material_inputs
from core.jobs.sample_job_builder import sample_input_payload
from core.optimizer.square_section_selector import parse_square_section_name
from core.schemas.input_models import parse_cable_input
from core.schemas.job_models import JobState
from core.spectra.static_coefficients import derive_static_acceleration_coefficients


def _safe_job_id(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value).strip())
    text = re.sub(r"_+", "_", text)
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text or uuid4().hex


def _normalise_square_section_ids(values: object) -> list[str]:
    if values in (None, ""):
        return []
    raw_items = list(values) if isinstance(values, (list, tuple, set)) else re.split(r"[,，;；、\s]+", str(values))
    normalised: list[str] = []
    for item in raw_items:
        text = re.sub(r"[×xX*＊]", "-", str(item or "").strip())
        text = re.sub(r"\s+", "", text)
        parsed = parse_square_section_name(text)
        if not parsed:
            continue
        section_id = f"{parsed.outer_mm:g}-{parsed.outer_mm:g}-{parsed.thickness_mm:g}"
        if section_id not in normalised:
            normalised.append(section_id)
    return normalised


def _intake_modal_mode_count(payload: dict, tray_mapping: dict | None, base_payload: dict | None) -> tuple[int, str]:
    explicit = payload.get("modal_mode_count")
    if explicit not in (None, ""):
        return coerce_modal_mode_count(explicit), "intake_modal_mode_count_override"
    base_payload = base_payload or {}
    base_metadata = base_payload.get("metadata") or {}
    base_count = base_metadata.get("modal_mode_count")
    if base_count not in (None, ""):
        return coerce_modal_mode_count(base_count), "base_payload_modal_mode_count"
    modal_payload = {
        "project": base_payload.get("project") or {},
        "support": base_payload.get("support") or {},
        "metadata": {
            **base_metadata,
            "analysis_method": payload.get("analysis_method") or base_metadata.get("analysis_method") or "response_spectrum",
            "tray_load_mapping": tray_mapping,
        },
        "tray_layers": base_payload.get("tray_layers") or [],
    }
    assigned = modal_mode_count_from_payload(modal_payload)
    audit = modal_policy_audit(modal_payload)
    source = audit.get("assigned_modal_mode_count_source") or "modal_policy"
    if source == "inferred_layer_count":
        source = "intake_rule_layer_count_modal_count"
    elif source == "learned_similar_intake_cache":
        source = "learned_similar_intake_modal_cache"
    elif source == "default_initial_count":
        source = "fallback_default_40_no_tray_layer_mapping"
    return assigned, str(source)


def _row_identity(row: dict) -> str:
    for key in ("report_number", "calculation_batch", "intake_order_id", "provisional_intake_id"):
        value = row.get(key)
        if value not in (None, ""):
            return _safe_job_id(str(value))
    return _safe_job_id(str(row.get("intake_row_number") or uuid4().hex))


def _arm_section_family(square_section_spec: str, tray_mapping: dict | None = None) -> tuple[str, str, str]:
    parsed_square = parse_square_section_name(square_section_spec) if square_section_spec else None
    square_outer_mm = parsed_square.outer_mm if parsed_square else 0.0
    if square_outer_mm > 120.0:
        return "YIXINGGANG150", "YIXINGGANG150DAN", "square_gt_120_yixing_arm_family"
    return "50-42", "CAOGANG42DAN", "square_le_120_standard_channel_family"


def _current_square_section_spec(base: dict, explicit_square_section_spec: str) -> str:
    if explicit_square_section_spec:
        return explicit_square_section_spec
    support = base.get("support") or {}
    support_section_id = str(support.get("support_section_id") or "")
    for section in base.get("sections") or []:
        if str(section.get("section_id") or "") == support_section_id and section.get("sect_file"):
            return str(section["sect_file"])
    for section in base.get("sections") or []:
        value = str(section.get("sect_file") or section.get("section_id") or "")
        if parse_square_section_name(value):
            return value
    return ""


def _sync_support_square_section(base: dict, square_section_spec: str, *, source_ref: str) -> None:
    parsed_square = parse_square_section_name(square_section_spec) if square_section_spec else None
    if not parsed_square:
        return
    support = base.get("support") or {}
    support["square_tube_width_m"] = parsed_square.outer_mm / 1000.0
    if source_ref:
        support["source_ref"] = source_ref
    base["support"] = support
    metadata = base.get("metadata") or {}
    metadata.update(
        {
            "square_section_current_model_spec": square_section_spec,
            "square_section_outer_mm": parsed_square.outer_mm,
            "square_section_thickness_mm": parsed_square.thickness_mm,
        }
    )
    base["metadata"] = metadata


def build_input_from_intake_payload(payload: dict, *, spectrum_file: str | None = None, spectrum_confirmed: bool = False) -> dict:
    base = sample_input_payload()
    analysis_method = str(payload.get("analysis_method") or "response_spectrum")
    formal_report_number = payload.get("report_number") or payload.get("calculation_batch")
    intake_order_id = payload.get("intake_order_id") or formal_report_number or payload.get("provisional_intake_id")
    project = base["project"]
    project["project_code"] = str(payload["project_code"])
    project["building"] = str(payload["building"])
    project["area"] = str(payload["area"])
    project["elevation"] = float(payload["elevation"])
    project["description"] = str(payload.get("description") or "Production intake job")

    base["spectrum"]["spectrum_file"] = spectrum_file or str(payload.get("spectrum_file") or "")
    base["spectrum"]["damping_ratio"] = float(payload["damping_ratio"])
    base["spectrum"]["spectrum_level"] = str(payload.get("spectrum_level") or "SL-2")
    base["spectrum"]["directions"] = str(payload.get("directions") or "X,Y,Z").replace(";", ",").split(",")
    if analysis_method == "static":
        base["spectrum"]["spectrum_file"] = base["spectrum"]["spectrum_file"] or ""
        base["spectrum"]["source_ref"] = "static_method_no_response_spectrum_required"
    static_coefficients_metadata: dict = {}
    static_coefficients_error: str | None = None
    if analysis_method == "static" and base["spectrum"]["spectrum_file"]:
        try:
            static_coefficients_metadata = derive_static_acceleration_coefficients(
                base["spectrum"]["spectrum_file"],
                project_code=str(project["project_code"]),
                building=str(project["building"]),
                elevation=float(project["elevation"]),
            )
            base["spectrum"]["source_ref"] = "static_method_coefficients_from_spectrum_peak"
        except Exception as exc:
            static_coefficients_error = str(exc)
    base["support"]["support_type"] = str(payload.get("support_type") or base["support"]["support_type"])
    if payload.get("support_spacing_m") is not None:
        base["support"]["support_spacing_m"] = float(payload["support_spacing_m"])
    if payload.get("support_height_m") is not None:
        base["support"]["support_height_m"] = float(payload["support_height_m"])
    tray_mapping: dict | None = None
    tray_mapping_error: str | None = None
    try:
        tray_mapping = parse_tray_load_description(payload.get("description") or "")
        base["support"]["layers_front"] = int(tray_mapping["front_layers"])
        base["support"]["layers_back"] = int(tray_mapping["back_layers"])
        base["support"]["side_count"] = int(tray_mapping.get("side_count") or 1)
        base["support"]["layers_third"] = int(tray_mapping.get("third_layers") or 0)
        base["tray_layers"] = [
            {
                "side": layer["side"],
                "layer_index": int(layer["layer_index"]),
                "tray_width_m": float(layer["tray_width_mm"]) / 1000.0,
                "arm_a_length_m": float(layer["arm_a_length_m"]),
                "arm_b_length_m": float(layer["arm_b_length_m"]),
                "arm_section_id": "arm-main",
                "tray_section_id": f"tray-{layer['tray_width_mm']}",
                "tray_density_kg_m3": float(layer["tray_density_kg_m3"]),
                "material_id": "q355",
                "source_ref": "intake_tray_load_text",
            }
            for layer in tray_mapping["layers"]
        ]
    except Exception as exc:
        tray_mapping_error = str(exc)
    square_section_spec = str(payload.get("square_section_spec") or "").strip()
    square_section_status = "provided_by_intake_column_i" if square_section_spec else "auto_selection_required"
    allowed_square_section_ids = _normalise_square_section_ids(
        payload.get("allowed_square_section_ids") or payload.get("allowed_square_sections")
    )
    allowed_square_section_source_ref = payload.get("allowed_square_section_source_ref")
    allowed_square_section_status = payload.get("allowed_square_section_status") or (
        "provided_by_intake_calculation_notes" if allowed_square_section_ids else "not_found"
    )
    base["support"]["material_id"] = "q355"
    if allowed_square_section_ids:
        base["support"]["allowed_square_section_ids"] = allowed_square_section_ids
    base["materials"] = production_material_inputs()
    current_square_section_spec = _current_square_section_spec(base, square_section_spec)
    if square_section_spec:
        parsed_square = parse_square_section_name(square_section_spec)
        section_id = square_section_spec.lower()
        base["support"]["support_section_id"] = section_id
        base["support"]["source_ref"] = "intake_column_I_embedded_plate_header_is_square_section"
        if parsed_square:
            base["support"]["square_tube_width_m"] = parsed_square.outer_mm / 1000.0
            base["metadata"] = {
                **base.get("metadata", {}),
                "square_section_outer_mm": parsed_square.outer_mm,
                "square_section_thickness_mm": parsed_square.thickness_mm,
            }
        if base.get("sections"):
            base["sections"][0]["section_id"] = section_id
            base["sections"][0]["sect_file"] = square_section_spec
            base["sections"][0]["source_ref"] = "intake_column_I_embedded_plate_header_is_square_section"
        current_square_section_spec = square_section_spec
    else:
        _sync_support_square_section(
            base,
            current_square_section_spec,
            source_ref="current_model_square_section_pending_auto_selection",
        )
    if tray_mapping:
        arm_primary, arm_secondary, arm_policy = _arm_section_family(current_square_section_spec, tray_mapping)
        existing_sections = {
            str(section.get("section_id")): section
            for section in base.get("sections", [])
            if not str(section.get("section_id") or "").startswith("tray-")
            and str(section.get("section_id") or "") != "tray-main"
        }
        existing_sections["arm-main"] = {
            "section_id": "arm-main",
            "sect_file": arm_primary,
            "section_type": "BEAM_MESH",
            "source_ref": arm_policy,
        }
        existing_sections["arm-secondary"] = {
            "section_id": "arm-secondary",
            "sect_file": arm_secondary,
            "section_type": "BEAM_MESH",
            "source_ref": arm_policy,
        }
        for layer in tray_mapping["layers"]:
            existing_sections[f"tray-{layer['tray_width_mm']}"] = {
                "section_id": f"tray-{layer['tray_width_mm']}",
                "sect_file": layer["tray_section_file"],
                "section_type": "BEAM_MESH",
                "source_ref": "intake_tray_load_text",
            }
        base["sections"] = list(existing_sections.values())
    modal_mode_count, modal_mode_count_source = _intake_modal_mode_count(payload, tray_mapping, base)
    topology_side_count = int(tray_mapping.get("side_count") or 1) if tray_mapping else None
    topology_blocked = bool(topology_side_count and topology_side_count > 2)
    effective_spectrum_confirmed = spectrum_confirmed or analysis_method == "static"
    base["metadata"] = {
        **base.get("metadata", {}),
        **material_policy_metadata(analysis_method, square_section_status),
        **{
            key: value
            for key, value in static_coefficients_metadata.items()
            if key.startswith("zpa_") or key in {"static_acceleration_factor"}
        },
        "created_from_intake": True,
        "spectrum_config_confirmed": effective_spectrum_confirmed,
        "spectrum_config_confirmed_by": "static_method_no_response_spectrum" if analysis_method == "static" else None,
        "analysis_method": analysis_method,
        "static_acceleration_status": static_coefficients_metadata.get("status")
        if static_coefficients_metadata
        else ("fail" if static_coefficients_error else ("missing_spectrum_file" if analysis_method == "static" else "not_required")),
        "static_acceleration_source": static_coefficients_metadata,
        "static_acceleration_error": static_coefficients_error,
        "report_number": formal_report_number,
        "calculation_batch": formal_report_number,
        "intake_order_id": intake_order_id,
        "provisional_intake_id": payload.get("provisional_intake_id"),
        "intake_identity_status": payload.get("intake_identity_status"),
        "intake_row_number": payload.get("intake_row_number"),
        "intake_serial": payload.get("intake_serial"),
        "intake_sheet": payload.get("intake_sheet"),
        "support_id": payload.get("support_id"),
        "elevation_raw": payload.get("elevation_raw"),
        "elevation_candidates": payload.get("elevation_candidates"),
        "static_elevation_policy": "single_current_intake_elevation_only_no_multi_elevation_envelope",
        "raw_intake_row": payload.get("raw_intake_row"),
        "tray_load_description": payload.get("description"),
        "tray_load_mapping_status": "pass" if tray_mapping else "fail",
        "tray_load_mapping": tray_mapping,
        "tray_load_mapping_error": tray_mapping_error,
        "topology_side_count": topology_side_count,
        "layers_third": int(tray_mapping.get("third_layers") or 0) if tray_mapping else None,
        "topology_calculation_status": "blocked_requires_human_review" if topology_blocked else "pass",
        "topology_calculation_message": (
            "Three-side S2 intake is parsed for review but skipped for production calculation until an audited three-side command-flow family is confirmed."
            if topology_blocked
            else None
        ),
        "topology_generalization_policy": (
            "S2 single/double/three-side intakes are parsed into explicit side/layer topology. "
            "Executable APDL must be produced by the approved S2 parametric topology compiler or a matching standard source family; "
            "LLM output is proposal-only and cannot directly become APDL."
        ),
        "arm_section_family": _arm_section_family(current_square_section_spec, tray_mapping)[2] if tray_mapping else None,
        "cantilever_evaluation_mode": payload.get("cantilever_evaluation_mode"),
        "square_section_spec": square_section_spec or None,
        "square_section_source": payload.get("square_section_source") or square_section_status,
        "square_section_selection_rule": (
            "If intake column I is blank, use only square sections allowed by the intake calculation notes when such a list is present. "
            "Run candidates in increasing economy order, allow deterministic smart jumps only after a real failed ratio, and stop at the first "
            "fresh real-ANSYS candidate whose controlling ratio is < 1.0. Later larger sections are not run after a pass because they are less economical. "
            "If no allowed section satisfies ratio < 1.0, fail with 提资允许截面不足."
        ),
        "allowed_square_section_ids": allowed_square_section_ids,
        "allowed_square_section_source_ref": allowed_square_section_source_ref,
        "allowed_square_section_status": allowed_square_section_status,
        "operator_flow": "upload_intake_select_spectrum_one_click",
        "modal_mode_count": modal_mode_count,
        "modal_mode_count_source": modal_mode_count_source,
        "modal_mode_policy": "MT is assigned before ANSYS solves. Use explicit intake metadata first, then similar successful real-run modal cache, then safe audited source/layer fallback; verify Mode.oup exceeds 50 Hz and retry upward only when coverage is short.",
    }
    return base


def create_job_from_intake(
    intake_path: Path | str,
    jobs_dir: Path | str = Path("jobs"),
    *,
    job_id: str | None = None,
    spectrum_file: str | None = None,
    spectrum_confirmed: bool = False,
    intake_order_id: str | None = None,
    report_number: str | None = None,
    row_number: int | None = None,
) -> dict:
    intake = read_and_validate_intake(intake_path, intake_order_id=intake_order_id, report_number=report_number, row_number=row_number)
    if intake["validation"]["status"] != "pass":
        raise ValueError(f"Intake is missing required fields: {intake['validation']['missing_fields']}")
    return create_job_from_intake_payload(
        intake["payload"],
        intake_source=intake_path,
        intake_format=intake.get("intake_format"),
        jobs_dir=jobs_dir,
        job_id=job_id,
        spectrum_file=spectrum_file,
        spectrum_confirmed=spectrum_confirmed,
    )


def create_job_from_intake_payload(
    intake_payload: dict,
    *,
    intake_source: Path | str,
    intake_format: str | None = "tabular",
    jobs_dir: Path | str = Path("jobs"),
    job_id: str | None = None,
    spectrum_file: str | None = None,
    spectrum_confirmed: bool = False,
) -> dict:
    payload = build_input_from_intake_payload(intake_payload, spectrum_file=spectrum_file, spectrum_confirmed=spectrum_confirmed)
    parse_cable_input(payload)

    metadata = payload.get("metadata", {})
    job_id = job_id or _safe_job_id(str(metadata.get("report_number") or metadata.get("calculation_batch") or metadata.get("intake_order_id") or uuid4().hex))
    job_dir = Path(jobs_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "input.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if not (job_dir / "job_state.json").exists():
        state = JobState(job_id=job_id, status="created")
        state.history.append({"status": "created", "message": "job created from intake"})
        write_job_state(job_dir, state)
    audit = {
        "status": "pass",
        "job_id": job_id,
        "input_file": "input.json",
        "intake_source": str(intake_source),
        "intake_format": intake_format,
        "intake_order_id": payload.get("metadata", {}).get("intake_order_id"),
        "report_number": payload.get("metadata", {}).get("report_number"),
        "calculation_batch": payload.get("metadata", {}).get("calculation_batch"),
        "provisional_intake_id": payload.get("metadata", {}).get("provisional_intake_id"),
        "intake_identity_status": payload.get("metadata", {}).get("intake_identity_status"),
        "analysis_method": payload.get("metadata", {}).get("analysis_method"),
        "spectrum_config_confirmed": payload.get("metadata", {}).get("spectrum_config_confirmed"),
    }
    (job_dir / "job_creation_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"job_id": job_id, "job_dir": str(job_dir), "input": payload, "audit": audit}


def _row_matches_selected_number(row: dict, wanted_rows: set[int]) -> bool:
    """Match UI row selections by parsed workbook row number only.

    ``intake_serial`` is the engineering/order number shown in the sheet, not
    the physical Excel row.  Treating it as a row selector makes "row 4" run
    both the real row 4 and any neighbouring row whose serial is 4.
    """

    try:
        return int(float(str(row.get("intake_row_number")))) in wanted_rows
    except (TypeError, ValueError):
        return False


def _coerce_row_numbers_from_item(item: dict) -> set[int]:
    row_numbers: set[int] = set()
    for value in (item.get("intake_row_number"), item.get("_lookup_key")):
        try:
            row_numbers.add(int(float(str(value))))
        except (TypeError, ValueError):
            continue
    return row_numbers


def _row_identity_keys(row: dict) -> set[str]:
    keys: set[str] = set()
    for key in ("intake_order_id", "report_number", "calculation_batch", "provisional_intake_id"):
        value = row.get(key)
        if value not in (None, ""):
            keys.add(str(value))
    return keys


def _normalise_row_override_items(row_overrides: dict[str, dict] | list[dict] | None) -> list[dict]:
    if isinstance(row_overrides, list):
        return [item for item in row_overrides if isinstance(item, dict)]
    if isinstance(row_overrides, dict):
        items: list[dict] = []
        for key, value in row_overrides.items():
            if not isinstance(value, dict):
                continue
            item = dict(value)
            item.setdefault("_lookup_key", key)
            items.append(item)
        return items
    return []


def _select_rows_from_overrides(rows: list[dict], override_items: list[dict]) -> list[dict]:
    """Resolve UI selections by stable row identity before falling back to row number.

    The dashboard can edit report/calculation identifiers after parsing.  When a
    selected row number and a stable row identity disagree, the identity wins so
    we do not run a stale neighbouring row and mark an otherwise valid job fail.
    """

    selected_indices: set[int] = set()
    for item in override_items:
        identity_keys = _row_identity_keys(item)
        matched = False
        if identity_keys:
            for index, row in enumerate(rows):
                if _row_identity_keys(row) & identity_keys:
                    selected_indices.add(index)
                    matched = True
        if matched:
            continue
        row_numbers = _coerce_row_numbers_from_item(item)
        if not row_numbers:
            continue
        for index, row in enumerate(rows):
            if _row_matches_selected_number(row, row_numbers):
                selected_indices.add(index)
    return [row for index, row in enumerate(rows) if index in selected_indices]


def create_jobs_from_intake_workbook(
    intake_path: Path | str,
    jobs_dir: Path | str = Path("jobs"),
    *,
    spectrum_file: str | None = None,
    spectrum_confirmed: bool = False,
    limit: int | None = None,
    selected_row_numbers: list[int] | tuple[int, ...] | None = None,
    selected_intake_order_ids: list[str] | tuple[str, ...] | None = None,
    row_overrides: dict[str, dict] | list[dict] | None = None,
) -> list[dict]:
    rows = read_tabular_intake_rows(intake_path)
    if not rows:
        return [
            create_job_from_intake(
                intake_path,
                jobs_dir=jobs_dir,
                spectrum_file=spectrum_file,
                spectrum_confirmed=spectrum_confirmed,
            )
        ]
    all_rows = list(rows)
    override_items = _normalise_row_override_items(row_overrides)
    selection_requested = bool(override_items or selected_row_numbers or selected_intake_order_ids)
    if override_items:
        rows = _select_rows_from_overrides(rows, override_items)
    elif selected_row_numbers:
        wanted_rows = {int(row_number) for row_number in selected_row_numbers}
        rows = [row for row in rows if _row_matches_selected_number(row, wanted_rows)]
    if selected_intake_order_ids:
        wanted_ids = {str(item) for item in selected_intake_order_ids}
        rows = [
            row
            for row in rows
            if str(row.get("intake_order_id")) in wanted_ids
            or str(row.get("report_number")) in wanted_ids
            or str(row.get("calculation_batch")) in wanted_ids
            or str(row.get("provisional_intake_id")) in wanted_ids
        ]
    if selection_requested and not rows:
        available = [
            {
                "intake_row_number": row.get("intake_row_number"),
                "report_number": row.get("report_number"),
                "calculation_batch": row.get("calculation_batch"),
                "intake_order_id": row.get("intake_order_id"),
                "provisional_intake_id": row.get("provisional_intake_id"),
            }
            for row in all_rows[:20]
        ]
        raise ValueError(
            "未匹配到任何提资行；不能返回 job_count=0 的成功结果。"
            f" selected_row_numbers={list(selected_row_numbers or [])},"
            f" selected_intake_order_ids={list(selected_intake_order_ids or [])},"
            f" row_overrides_count={len(override_items)}, available_rows={available}"
        )
    if limit:
        rows = rows[:limit]
    overrides_by_key: dict[str, dict] = {}
    for item in override_items:
        for key in (
            item.get("_lookup_key"),
            item.get("intake_row_number"),
            item.get("intake_serial"),
            item.get("intake_order_id"),
            item.get("report_number"),
            item.get("calculation_batch"),
            item.get("provisional_intake_id"),
        ):
            if key not in (None, ""):
                overrides_by_key[str(key)] = item
    results: list[dict] = []
    identity_counts = Counter(_row_identity(row) for row in rows)
    for row in rows:
        override = None
        for key in (
            row.get("intake_row_number"),
            row.get("intake_order_id"),
            row.get("report_number"),
            row.get("calculation_batch"),
            row.get("provisional_intake_id"),
        ):
            if key not in (None, "") and str(key) in overrides_by_key:
                override = overrides_by_key[str(key)]
                break
        if override:
            row = {**row, **{key: value for key, value in override.items() if value not in (None, "")}}
        identity = _row_identity(row)
        row_number = row.get("intake_row_number")
        job_id = f"{identity}__row_{_safe_job_id(str(row_number))}" if identity_counts[identity] > 1 and row_number not in (None, "") else None
        results.append(
            create_job_from_intake_payload(
                row,
                intake_source=intake_path,
                intake_format="tabular",
                jobs_dir=jobs_dir,
                job_id=job_id,
                spectrum_file=spectrum_file,
                spectrum_confirmed=spectrum_confirmed,
            )
        )
    return results
