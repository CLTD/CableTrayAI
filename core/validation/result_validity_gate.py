from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.optimizer.square_section_selector import controlling_section_selection_ratio
from core.validation.result_requirements import classify_job_requirements


FORCE_FIELDS = ("fx", "fy", "fz", "mx", "my", "mz")


def _metric_value(value: Any) -> float | None:
    if isinstance(value, dict):
        return _metric_value(value.get("value", value.get("normalized_value", value.get("raw_value"))))
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _all_force_values_zero(rows: list[dict[str, Any]], fields: tuple[str, ...] = FORCE_FIELDS) -> bool:
    if not rows:
        return True
    seen = False
    for row in rows:
        for field in fields:
            nested_values = row.get("values") if isinstance(row.get("values"), dict) else {}
            value = _metric_value(row.get(field, nested_values.get(field)))
            if value is None:
                continue
            seen = True
            if abs(value) > 1e-9:
                return False
    return True


def _rows_have_unknown_nodes(rows: list[dict[str, Any]]) -> bool:
    for row in rows:
        node = str(row.get("node") or row.get("node_id") or "").strip().upper()
        if not node or node == "UNKNOWN":
            return True
    return False


def _beam_rows_all_zero(rows: list[dict[str, Any]]) -> bool:
    if not rows:
        return True
    seen = False
    for row in rows:
        value = _metric_value(row.get("value_mpa"))
        if value is None:
            continue
        seen = True
        if abs(value) > 1e-9:
            return False
    return True


def _foundation_dw_has_suspicious_zero_moments(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Detect a common JCZH extraction failure for S2 cantilever supports.

    A self-weight foundation row with vertical reaction but no horizontal
    reaction and no support moment is usually not a reliable S2 root-load
    extraction.  It can happen when the post-processing component or moment
    reference point does not match the generated model.
    """

    for row in rows:
        if str(row.get("load_case") or "").strip().upper() != "DW":
            continue
        values = {
            field: _metric_value(row.get(field, (row.get("values") or {}).get(field) if isinstance(row.get("values"), dict) else None))
            for field in FORCE_FIELDS
        }
        fz = values.get("fz") or 0.0
        if abs(fz) <= 1e-9:
            continue
        lateral_and_moment = ("fx", "fy", "mx", "my", "mz")
        if all(abs(values.get(field) or 0.0) <= 1e-9 for field in lateral_and_moment):
            return {
                "load_case": "DW",
                "source_file": row.get("source_file") or row.get("source_ref") or "JCZH.LIS",
                "values": values,
                "reason": "DW has non-zero FZ but FX/FY/MX/MY/MZ are all zero.",
            }
    return None


def _read_job_input(job_dir: Path) -> dict[str, Any]:
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return {}
    try:
        return json.loads(input_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _layer_signature(layer: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(layer.get("layer_index") or 0),
        _metric_value(layer.get("tray_width_mm")),
        str(layer.get("cable_type") or "").strip().lower(),
        _metric_value(layer.get("load_kg_per_m")),
        _metric_value(layer.get("arm_a_length_m")),
        _metric_value(layer.get("arm_b_length_m")),
        str(layer.get("tray_section_file") or "").strip().lower(),
    )


def _same_layer_stack(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    if not left or len(left) != len(right):
        return False
    return sorted(_layer_signature(item) for item in left) == sorted(_layer_signature(item) for item in right)


def _foundation_dw_zero_allowed_by_symmetry(job_dir: Path) -> dict[str, Any]:
    """Return evidence when a vertical-only DW foundation row is expected.

    For a perfectly symmetric S2 double-side tray layout, self-weight produces
    vertical support reaction while horizontal resultants and root moments can
    cancel in the JCZH support component.  This allowance is deliberately narrow:
    it requires explicit parsed topology.  When detailed layer rows exist,
    front/back stacks must match; otherwise the support-level layer counts must
    be symmetric and third-side layers must be absent.
    """

    payload = _read_job_input(job_dir)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    mapping = metadata.get("tray_load_mapping") if isinstance(metadata.get("tray_load_mapping"), dict) else {}
    side_count = int(mapping.get("side_count") or metadata.get("topology_side_count") or (payload.get("support") or {}).get("side_count") or 0)
    front_layers = int(mapping.get("front_layers") or (payload.get("support") or {}).get("layers_front") or 0)
    back_layers = int(mapping.get("back_layers") or (payload.get("support") or {}).get("layers_back") or 0)
    third_layers = int(mapping.get("third_layers") or metadata.get("layers_third") or (payload.get("support") or {}).get("layers_third") or 0)
    layers = mapping.get("layers") if isinstance(mapping.get("layers"), list) else []
    front = [item for item in layers if isinstance(item, dict) and str(item.get("side") or "").lower() == "front"]
    back = [item for item in layers if isinstance(item, dict) and str(item.get("side") or "").lower() == "back"]
    tray_text = str(metadata.get("tray_load_description") or payload.get("project", {}).get("description") or "")
    has_explicit_layer_stack = bool(front or back)
    stack_is_symmetric = _same_layer_stack(front, back) if has_explicit_layer_stack else True
    symmetric = (
        side_count == 2
        and third_layers == 0
        and front_layers > 0
        and front_layers == back_layers
        and stack_is_symmetric
    )
    if symmetric:
        return {
            "status": "pass",
            "reason": "双侧完全对称托盘自重，JCZH 中 DW 横向合力和根部力矩可相互抵消。",
            "side_count": side_count,
            "front_layers": front_layers,
            "back_layers": back_layers,
            "layer_stack_evidence": "explicit_stack_match" if has_explicit_layer_stack else "symmetric_layer_counts",
            "tray_load_description": tray_text,
            "source_ref": "input.json:metadata.tray_load_mapping or input.json:support.layers_front/layers_back",
        }
    return {
        "status": "fail",
        "reason": "不是明确的双侧完全对称自重拓扑，DW 横向力/力矩全零仍按异常处理。",
        "side_count": side_count,
        "front_layers": front_layers,
        "back_layers": back_layers,
        "third_layers": third_layers,
        "front_layer_count": len(front),
        "back_layer_count": len(back),
        "tray_load_description": tray_text,
    }


def _is_s2_support(requirements: dict[str, Any]) -> bool:
    return str(requirements.get("support_type") or "").strip().upper().startswith("S2")


def _figure_names(figures: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in figures:
        for key in ("target_file", "source_file", "path"):
            value = item.get(key)
            if value:
                names.add(Path(str(value)).name.upper())
    return names


def _figure_path(job_dir: Path, figures: list[dict[str, Any]], file_name: str) -> Path | None:
    wanted = file_name.upper()
    for item in figures:
        for key in ("target_file", "path", "source_file"):
            value = item.get(key)
            if not value or Path(str(value)).name.upper() != wanted:
                continue
            candidate = job_dir / str(value)
            if candidate.exists():
                return candidate
    candidate = job_dir / file_name
    return candidate if candidate.exists() else None


def _uses_equivalent_cantilever_weld_table(requires: dict[str, Any], requirements: dict[str, Any]) -> bool:
    """Return true for the <=120 mm cantilever-root equivalent-stress branch.

    In that branch the source output is the cantilever stress extraction
    (TMAXBEAMSTRESS.LIS) and appendix-C cloud figures.  HF-FORCE.LIS belongs to
    the large-section weld-principle branch and should not be required here.
    """

    return bool(
        requires.get("cantilever_root_weld_equivalent_stress_table")
        or requirements.get("cantilever_root_weld_equivalent_eval")
        or requirements.get("appendix_c_mode") == "cantilever_stress_cloud"
        or requirements.get("cantilever_stress_clouds_required")
    )


def _image_difference_ratio(left: Path, right: Path) -> float | None:
    try:
        from PIL import Image, ImageChops

        with Image.open(left) as left_image, Image.open(right) as right_image:
            a = left_image.convert("RGB")
            b = right_image.convert("RGB")
            if a.size != b.size:
                b = b.resize(a.size)
            diff = ImageChops.difference(a, b)
            total = sum(sum(pixel) for pixel in diff.getdata())
            return total / (a.size[0] * a.size[1] * 3 * 255)
    except Exception:
        return None


def _check(checks: list[dict[str, Any]], check_id: str, status: str, message: str, evidence: Any = None) -> None:
    checks.append(
        {
            "check_id": check_id,
            "status": status,
            "message": message,
            "evidence": evidence,
        }
    )


def _bolt_combined_zero_conflicts(evaluation_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, float]] = {}
    for row in evaluation_rows:
        check_id = str(row.get("check_id") or "").lower()
        if "_bolt_" not in check_id:
            continue
        prefix, kind = check_id.rsplit("_bolt_", 1)
        ratio_value = _metric_value(row.get("ratio"))
        calculation_value = _metric_value(row.get("calculation_value"))
        value = ratio_value if ratio_value is not None else calculation_value
        if value is None:
            continue
        grouped.setdefault(prefix, {})[kind] = float(value)
    conflicts: list[dict[str, Any]] = []
    for prefix, values in grouped.items():
        combined = values.get("combined")
        tension = values.get("tension", 0.0)
        shear = values.get("shear", 0.0)
        if combined is None:
            continue
        if abs(combined) <= 1e-12 and (abs(tension) > 1e-12 or abs(shear) > 1e-12):
            conflicts.append(
                {
                    "case": prefix,
                    "combined_ratio": combined,
                    "tension_ratio": tension,
                    "shear_ratio": shear,
                }
            )
    return conflicts


def _read_square_section_selection(job_dir: Path) -> dict[str, Any]:
    path = job_dir / "square_section_selection.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _max_evaluation_ratio(evaluation_rows: list[dict[str, Any]]) -> float | None:
    ratios: list[float] = []
    for row in evaluation_rows:
        value = _metric_value(row.get("ratio"))
        if value is not None:
            ratios.append(float(value))
    return max(ratios) if ratios else None


def _square_section_selection_ratio(evaluation_rows: list[dict[str, Any]]) -> float | None:
    return controlling_section_selection_ratio(evaluation_rows)


SQUARE_SECTION_TRIAL_FINAL_RATIO_TOLERANCE = 0.01


def _square_section_trial_final_ratio_check(job_dir: Path, evaluation_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    input_payload = _read_job_input(job_dir)
    metadata = input_payload.get("metadata") if isinstance(input_payload.get("metadata"), dict) else {}
    selection = _read_square_section_selection(job_dir)
    selected = selection.get("selected") if isinstance(selection.get("selected"), dict) else {}
    if not selected and isinstance(selection, dict) and selection.get("section_name"):
        # Backward compatibility for older packaged builds that wrote the
        # flattened square-section summary to square_section_selection.json.
        selected = selection
    auto_selected = (
        metadata.get("square_section_selection_status") == "auto_selected_by_real_ansys"
        or bool(selected.get("section_name"))
        or selection.get("selection_status") == "auto_selected_by_real_ansys"
    )
    if not auto_selected:
        return None
    validation_mode = str(
        metadata.get("square_section_selection_validation_mode")
        or selection.get("selection_validation_mode")
        or ""
    )
    if validation_mode == "learned_formal_validation":
        return {
            "check_id": "square_section_formal_validation_mode",
            "status": "pass",
            "message": "Square section came from a learned high-similarity hint; current formal ANSYS/evaluation results are used directly instead of comparing against a historical trial ratio.",
            "evidence": {
                "section_name": selected.get("section_name") or metadata.get("square_section_selected"),
                "validation_mode": validation_mode,
                "historical_ratio": selected.get("historical_controlling_ratio")
                or selected.get("controlling_ratio")
                or metadata.get("square_section_selected_ratio"),
                "source_ref": "square_section_selection.json:learned_formal_validation",
            },
        }
    final_ratio = _square_section_selection_ratio(evaluation_rows)
    final_chapter6_ratio = _max_evaluation_ratio(evaluation_rows)
    trial_ratio = _metric_value(
        selected.get("trial_controlling_ratio")
        or selected.get("controlling_ratio")
        or selection.get("trial_controlling_ratio")
        or metadata.get("square_section_selected_ratio")
    )
    evidence = {
        "section_name": selected.get("section_name") or metadata.get("square_section_selected"),
        "final_section_selection_ratio": final_ratio,
        "final_chapter6_controlling_ratio": final_chapter6_ratio,
        "trial_controlling_ratio": trial_ratio,
        "source_ref": "evaluation_summary.json + square_section_selection.json",
    }
    if trial_ratio is None:
        return {
            "check_id": "square_section_trial_ratio_missing",
            "status": "fail",
            "message": "Auto-selected square section has no traceable trial controlling ratio; section economy cannot be audited.",
            "evidence": evidence,
        }
    if final_ratio is None:
        return {
            "check_id": "square_section_final_ratio_missing",
            "status": "fail",
            "message": "Formal Chapter 6.1 section-selection ratio is missing; square-section trial cannot be compared with final evaluation.",
            "evidence": evidence,
        }
    delta = abs(float(final_ratio) - float(trial_ratio))
    evidence["absolute_delta"] = delta
    evidence["tolerance"] = SQUARE_SECTION_TRIAL_FINAL_RATIO_TOLERANCE
    if delta > SQUARE_SECTION_TRIAL_FINAL_RATIO_TOLERANCE:
        return {
            "check_id": "square_section_trial_final_ratio_mismatch",
            "status": "fail",
            "message": "Square-section trial ratio differs from the final Chapter 6.1 section-selection ratio by more than 0.01; rerun clean trials before accepting the selected section.",
            "evidence": evidence,
        }
    return {
        "check_id": "square_section_trial_final_ratio_match",
        "status": "pass",
        "message": "Square-section trial ratio matches the final Chapter 6.1 section-selection ratio.",
        "evidence": evidence,
    }


def validate_result_outputs(job_dir: Path | str, *, raw: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Block production display when required ANSYS/PIP outputs are missing or invalid.

    This gate is intentionally stricter than parser unit tests. A syntactically
    valid LIS file that contains only zeros, UNKNOWN nodes, or missing required
    report sections is not a usable engineering result and must not be shown as
    a passing calculation.
    """

    job_dir = Path(job_dir)
    checks: list[dict[str, Any]] = []
    try:
        requirements = classify_job_requirements(job_dir)
    except Exception as exc:  # pragma: no cover - defensive for damaged jobs
        requirements = {"status": "fail", "requires": {}, "error": str(exc)}
        _check(checks, "result_scope_classification", "fail", "Could not classify result requirements.", str(exc))

    requires = requirements.get("requires") or {}
    missing = set(raw.get("missing_expected_files") or [])

    required_files = {"MAXBEAMSTRESS.LIS", "JCZH.LIS"}
    if requires.get("modal_analysis") or requires.get("modal_frequency_table"):
        required_files.add("Mode.oup")
    equivalent_cantilever_weld = _uses_equivalent_cantilever_weld_table(requires, requirements)
    if requires.get("cantilever_root_weld_eval") and not equivalent_cantilever_weld:
        required_files.add("HF-FORCE.LIS")
    if requires.get("cantilever_stress_eval") or equivalent_cantilever_weld:
        required_files.add("TMAXBEAMSTRESS.LIS")
    if requires.get("tray_arm_connection_loads") or requires.get("bolt_stress_eval"):
        required_files.add("LS-FORCE.LIS")

    for file_name in sorted(required_files):
        if file_name in missing or not (job_dir / file_name).exists():
            _check(checks, f"required_file_{file_name}", "fail", "Required result file is missing.", file_name)
        else:
            _check(checks, f"required_file_{file_name}", "pass", "Required result file exists.", file_name)

    beam_rows = result.get("beam_stress_results") or []
    if not beam_rows:
        _check(checks, "beam_stress_rows", "fail", "No beam stress rows were parsed from required stress LIS files.")
    elif _beam_rows_all_zero(beam_rows):
        _check(checks, "beam_stress_rows", "fail", "Beam stress rows are all zero; extraction is not usable.")
    else:
        _check(checks, "beam_stress_rows", "pass", "Beam stress rows contain non-zero values.", len(beam_rows))

    foundation_rows = result.get("foundation_loads") or []
    if requires.get("foundation_loads", True):
        suspicious_dw = _foundation_dw_has_suspicious_zero_moments(foundation_rows)
        if not foundation_rows:
            _check(checks, "foundation_load_rows", "fail", "Foundation load extraction produced no rows.")
        elif _rows_have_unknown_nodes(foundation_rows):
            _check(checks, "foundation_load_nodes", "fail", "Foundation load rows contain UNKNOWN nodes.", len(foundation_rows))
        elif _all_force_values_zero(foundation_rows):
            _check(checks, "foundation_load_values", "fail", "Foundation load rows are all zero; RF extraction did not hit valid support nodes.")
        elif _is_s2_support(requirements) and suspicious_dw:
            symmetry = _foundation_dw_zero_allowed_by_symmetry(job_dir)
            if symmetry.get("status") == "pass":
                _check(
                    checks,
                    "foundation_dw_self_weight_symmetry",
                    "pass",
                    "DW foundation row has only vertical reaction, but the parsed tray topology is a symmetric double-side self-weight case where lateral reactions and root moments can cancel.",
                    {"dw_row": suspicious_dw, "symmetry": symmetry},
                )
                _check(checks, "foundation_load_values", "pass", "Foundation load rows contain non-zero values.", len(foundation_rows))
            else:
                _check(
                    checks,
                    "foundation_dw_moment_zero",
                    "fail",
                    "DW foundation load has vertical reaction but no lateral reaction or support moment; JCZH component or moment reference should be checked.",
                    {"dw_row": suspicious_dw, "symmetry": symmetry},
                )
        else:
            _check(checks, "foundation_load_values", "pass", "Foundation load rows contain non-zero values.", len(foundation_rows))

    modal_rows = result.get("modal_results") or []
    if requires.get("modal_analysis"):
        cutoff_statuses = {str(row.get("modal_cutoff_status") or "") for row in modal_rows}
        mt_modes = [row.get("mt_mode") for row in modal_rows if row.get("mt_mode") is not None]
        if not modal_rows:
            _check(checks, "modal_mt_cutoff", "fail", "Mode.oup produced no modal rows.")
        elif "pass" in cutoff_statuses and mt_modes:
            _check(checks, "modal_mt_cutoff", "pass", "Mode.oup contains at least one FREQUENCY (HERTZ) row above 50 Hz.", {"mt_mode": max(mt_modes)})
        else:
            _check(
                checks,
                "modal_mt_cutoff",
                "fail",
                "Mode.oup does not contain any FREQUENCY (HERTZ) row above 50 Hz; MT cannot be determined for the 50 Hz cutoff.",
                {"last_frequency_hz": modal_rows[-1].get("frequency_hz") if modal_rows else None},
            )
    elif requires.get("modal_frequency_table"):
        if not modal_rows:
            _check(checks, "modal_frequency_table", "fail", "Mode.oup did not produce modal frequency rows for the report appendix table.")
        else:
            _check(checks, "modal_frequency_table", "pass", "Mode.oup contains modal frequency rows for the report appendix table.", len(modal_rows))

    bolt_rows = result.get("bolt_force_results") or []
    connection_node_rows = result.get("connection_node_force_results") or []
    if requires.get("tray_arm_connection_loads") or requires.get("bolt_stress_eval"):
        bolt_rows_zero = _all_force_values_zero(bolt_rows, ("fx", "fy", "fz", "mx", "my", "mz", "tension_mpa", "shear_mpa"))
        connection_node_rows_zero = _all_force_values_zero(connection_node_rows)
        if not bolt_rows and not connection_node_rows:
            _check(checks, "connection_load_rows", "fail", "Tray-arm connection load extraction produced no rows.")
        elif bolt_rows and not bolt_rows_zero:
            _check(
                checks,
                "connection_load_values",
                "pass",
                "Connection load extraction contains non-zero LS-FORCE values.",
                {"bolt_rows": len(bolt_rows), "connection_node_rows": len(connection_node_rows)},
            )
        elif connection_node_rows and not connection_node_rows_zero:
            _check(
                checks,
                "connection_load_values",
                "pass",
                "LS-FORCE rows are zero, but connection-node topology export contains non-zero values and is used as the traceable fallback.",
                {"bolt_rows": len(bolt_rows), "connection_node_rows": len(connection_node_rows)},
            )
        elif connection_node_rows:
            _check(checks, "connection_node_values", "fail", "Connection-node force rows are all zero; node topology export is invalid.")
        else:
            _check(checks, "connection_load_values", "fail", "LS-FORCE rows are all zero and no non-zero connection-node fallback exists.")

    tmax_rows = raw.get("TMAXBEAMSTRESS.LIS") or []
    if requires.get("cantilever_stress_eval"):
        if not tmax_rows:
            _check(checks, "cantilever_stress_rows", "fail", "Cantilever stress evaluation is required but TMAXBEAMSTRESS.LIS parsed no rows.")
        elif _beam_rows_all_zero(tmax_rows):
            _check(checks, "cantilever_stress_rows", "fail", "TMAXBEAMSTRESS.LIS is all zero for a required cantilever stress check.")
        else:
            _check(checks, "cantilever_stress_rows", "pass", "Cantilever stress rows contain non-zero values.", len(tmax_rows))
    if requires.get("cantilever_root_weld_eval"):
        if equivalent_cantilever_weld:
            _check(
                checks,
                "cantilever_root_weld_source_branch",
                "pass",
                "Cantilever root weld uses the <=120 mm equivalent-stress table branch; HF-FORCE.LIS is not required for this branch.",
                {
                    "appendix_c_mode": requirements.get("appendix_c_mode"),
                    "equivalent_coefficient": requirements.get("cantilever_root_weld_equivalent_coefficient"),
                },
            )
        else:
            _check(
                checks,
                "cantilever_root_weld_source_branch",
                "pass",
                "Cantilever root weld uses the >120 mm weld-principle branch; HF-FORCE.LIS is required.",
                {"appendix_c_mode": requirements.get("appendix_c_mode")},
            )

    required_figures = [str(name).upper() for name in requirements.get("required_figures") or []]
    if required_figures:
        figure_rows = result.get("figures") or []
        available = _figure_names(figure_rows)
        missing_figures = sorted(name for name in required_figures if name not in available)
        if missing_figures:
            _check(
                checks,
                "required_figures",
                "fail",
                "Required ANSYS cloud/modal figures are missing; result display cannot claim complete extraction.",
                missing_figures,
            )
        else:
            _check(checks, "required_figures", "pass", "All required ANSYS figures are present.", len(required_figures))
        blank_like = [
            row.get("target_file") or row.get("source_file") or row.get("figure_id")
            for row in figure_rows
            if str(row.get("target_file") or row.get("source_file") or "").upper() in required_figures
            and isinstance(row.get("image_quality"), dict)
            and row["image_quality"].get("quality_status") == "blank_like"
        ]
        if blank_like:
            _check(
                checks,
                "required_figure_quality",
                "fail",
                "Required ANSYS figures look blank; cloud/modal image export must be fixed before publication.",
                blank_like[:20],
            )
        whole_model = _figure_path(job_dir, figure_rows, "SHITI.PNG")
        cantilever_model = _figure_path(job_dir, figure_rows, "TBMODEL.PNG")
        if whole_model and cantilever_model:
            ratio = _image_difference_ratio(whole_model, cantilever_model)
            if ratio is not None and ratio < 0.001:
                _check(
                    checks,
                    "model_figure_5_distinct",
                    "fail",
                    "Fig. 5.2 TBMODEL is visually identical to Fig. 5.1 SHITI; the cantilever model selection did not work.",
                    {"difference_ratio": ratio, "fig_5_1": whole_model.name, "fig_5_2": cantilever_model.name},
                )
            elif ratio is not None:
                _check(
                    checks,
                    "model_figure_5_distinct",
                    "pass",
                    "Fig. 5.1 whole-model and Fig. 5.2 cantilever-model images are distinct.",
                    {"difference_ratio": ratio},
                )

    evaluation_rows = result.get("evaluation_summary") or []
    if equivalent_cantilever_weld:
        equivalent_rows = [
            row
            for row in evaluation_rows
            if str(row.get("check_id") or "").startswith("cantilever_root_weld_equivalent.")
        ]
        if not equivalent_rows:
            _check(
                checks,
                "cantilever_root_weld_equivalent_eval_rows",
                "fail",
                "Square tube outer width <= 120 mm requires table 6-2-1 equivalent weld-stress evaluation rows from TMAXBEAMSTRESS.LIS / 0.526.",
                {"coefficient": requirements.get("cantilever_root_weld_equivalent_coefficient")},
            )
        else:
            _check(
                checks,
                "cantilever_root_weld_equivalent_eval_rows",
                "pass",
                "Equivalent weld-stress evaluation rows exist for table 6-2-1.",
                len(equivalent_rows),
            )
    over_limit = []
    for row in evaluation_rows:
        ratio_value = _metric_value(row.get("ratio"))
        if ratio_value is not None and ratio_value > 1.0:
            over_limit.append({"check_id": row.get("check_id"), "ratio": ratio_value})
    if over_limit:
        _check(
            checks,
            "evaluation_ratio_limit",
            "fail",
            "One or more deterministic evaluation ratios exceed 1.0; the selected section/load extraction cannot be published as passing.",
            over_limit[:20],
        )
    zero_allowable = [
        row.get("check_id")
        for row in evaluation_rows
        if row.get("allowable_value") == 0 or row.get("allowable_value") == 0.0
    ]
    if zero_allowable:
        _check(checks, "evaluation_zero_allowable", "fail", "Evaluation contains zero allowable values and cannot be published as passing.", zero_allowable[:20])

    bolt_combined_conflicts = _bolt_combined_zero_conflicts(evaluation_rows)
    if bolt_combined_conflicts:
        _check(
            checks,
            "bolt_combined_ratio_zero_conflict",
            "fail",
            "Bolt combined ratio is zero while bolt tension/shear ratios are non-zero; this indicates an evaluation or display mapping error.",
            bolt_combined_conflicts[:20],
        )

    square_ratio_check = _square_section_trial_final_ratio_check(job_dir, evaluation_rows)
    if square_ratio_check is not None:
        _check(
            checks,
            str(square_ratio_check["check_id"]),
            str(square_ratio_check["status"]),
            str(square_ratio_check["message"]),
            square_ratio_check.get("evidence"),
        )

    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warning_count = sum(1 for item in checks if item["status"] == "warning")
    status = "fail" if fail_count else "warning" if warning_count else "pass"
    payload = {
        "status": status,
        "result_publishable": status == "pass",
        "fail_count": fail_count,
        "warning_count": warning_count,
        "check_count": len(checks),
        "requirements": requirements,
        "checks": checks,
        "policy": [
            "A parsed file is not enough; required engineering outputs must be non-zero and tied to known nodes/sources.",
            "Missing or invalid extraction blocks the operator result page from claiming pass.",
            "Report baseline comparison is a calibration tool, not a runtime answer source for new intakes.",
        ],
    }
    # Keep this gate file ASCII-only so legacy Windows PowerShell and packaged
    # deployments can read it without corrupting Chinese evidence strings before
    # ConvertFrom-Json or the web UI parses it.
    (job_dir / "result_validation.json").write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return payload
