from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.validation.result_requirements import CANTILEVER_FIGURES, MODAL_FIGURES, MODEL_FIGURES, SQUARE_SUPPORT_FIGURES

SQUARE_SECTION_CANTILEVER_CLOUD_MAX_OUTER_MM = 120.0
SQUARE_SECTION_WELD_PRINCIPLE_GT_OUTER_MM = 120.0
CANTILEVER_ROOT_WELD_EQUIVALENT_COEFFICIENT = 0.526


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_text(item) for item in value)
    return str(value)


def _bool_from_metadata(metadata: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in metadata:
            continue
        value = metadata.get(key)
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "include", "required"}:
            return True
        if text in {"0", "false", "no", "n", "exclude", "not_required"}:
            return False
    return None


def parse_tray_load_description(description: Any) -> dict[str, Any]:
    text = _text(description)
    widths = [int(match) for match in re.findall(r"(\d{2,4})\s*mm?\s*托盘|(\d{2,4})\s*宽", text) for match in match if match]
    layer_numbers = [int(value) for value in re.findall(r"(\d+)\s*层", text)]
    return {
        "raw_description": text,
        "side_layout": "double" if "双侧" in text else "single" if "单侧" in text else "unknown",
        "has_tray": "托盘" in text or bool(widths),
        "has_cantilever_arm": "托臂" in text or "托盘" in text or "单侧" in text or "双侧" in text,
        "tray_widths_mm": widths,
        "declared_layer_count": max(layer_numbers) if layer_numbers else None,
    }


def parse_square_section_spec(value: Any) -> dict[str, float | None] | None:
    text = _text(value).strip()
    if not text:
        return None
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*[-*xX×]\s*(\d+(?:\.\d+)?)\s*(?:[-*xX×]\s*(\d+(?:\.\d+)?))?",
        text,
    )
    if match and abs(float(match.group(1)) - float(match.group(2))) < 1e-6:
        return {
            "outer_mm": float(match.group(1)),
            "thickness_mm": float(match.group(3)) if match.group(3) else None,
        }
    match = re.search(r"(\d+(?:\.\d+)?)\s*方", text)
    if match:
        return {"outer_mm": float(match.group(1)), "thickness_mm": None}
    return None


def parse_square_outer_width_mm(value: Any) -> float | None:
    parsed = parse_square_section_spec(value)
    return float(parsed["outer_mm"]) if parsed else None


def square_section_spec_from_input(input_payload: dict[str, Any]) -> dict[str, float | None] | None:
    metadata = input_payload.get("metadata") or {}
    support = input_payload.get("support") or {}
    raw_row = metadata.get("raw_intake_row") or {}
    candidates = [
        metadata.get("square_section_current_model_spec"),
        metadata.get("square_section_selected"),
        metadata.get("square_section_spec"),
        support.get("support_section_id"),
        raw_row.get("埋件"),
        raw_row.get("埋板"),
        raw_row.get("方钢截面"),
        raw_row.get("方钢尺寸"),
    ]
    for section in input_payload.get("sections") or []:
        candidates.append(section.get("sect_file"))
        candidates.append(section.get("section_id"))
    for candidate in candidates:
        parsed = parse_square_section_spec(candidate)
        if parsed is not None:
            return parsed
    return None


def square_outer_width_from_input(input_payload: dict[str, Any]) -> float | None:
    parsed = square_section_spec_from_input(input_payload)
    return float(parsed["outer_mm"]) if parsed else None


def appendix_c_mode_for_square_section(square_outer_width_mm: float | None) -> tuple[str, str]:
    if square_outer_width_mm is None:
        return "needs_square_section_selection", "square_section_unknown"
    if square_outer_width_mm <= SQUARE_SECTION_CANTILEVER_CLOUD_MAX_OUTER_MM:
        return "cantilever_stress_cloud", "square_outer_width_le_120_requires_cantilever_stress_clouds"
    return "weld_evaluation_principle", "square_outer_width_gt_120_uses_weld_principle_appendix"


def classify_scope_from_input(input_payload: dict[str, Any]) -> dict[str, Any]:
    metadata = input_payload.get("metadata") or {}
    support = input_payload.get("support") or {}
    project = input_payload.get("project") or {}
    raw_row = metadata.get("raw_intake_row") or {}
    combined = " ".join(
        _text(value)
        for value in (
            metadata,
            support,
            project,
            raw_row,
            input_payload.get("tray_layers") or [],
        )
    )
    description = (
        metadata.get("tray_load_description")
        or metadata.get("description")
        or support.get("description")
        or raw_row.get("托盘载荷")
        or raw_row.get("托盘荷载")
        or project.get("description")
    )
    tray = parse_tray_load_description(description)
    square_section = square_section_spec_from_input(input_payload)
    square_outer_width_mm = float(square_section["outer_mm"]) if square_section else None
    square_thickness_mm = square_section["thickness_mm"] if square_section else None
    support_type = str(support.get("support_type") or raw_row.get("支架形式") or "").strip().upper()
    explicit_method = str(metadata.get("analysis_method") or input_payload.get("analysis_method") or "").strip().lower()
    if explicit_method in {"static", "静力", "静力法"} or "钢平台" in combined:
        analysis_method = "static"
    elif explicit_method in {"response_spectrum", "spectrum", "反应谱", "反应谱法"}:
        analysis_method = "response_spectrum"
    else:
        analysis_method = "response_spectrum"

    has_cantilever = bool(tray["has_cantilever_arm"] or support_type.startswith("S2"))
    has_tray_connection = bool(has_cantilever and (tray["has_tray"] or input_payload.get("tray_layers")))
    appendix_c_mode, decision_source = appendix_c_mode_for_square_section(square_outer_width_mm)
    if has_cantilever and appendix_c_mode == "needs_square_section_selection":
        cantilever_clouds = False
        scope_status = "needs_square_section_selection"
    elif has_cantilever and appendix_c_mode == "cantilever_stress_cloud":
        cantilever_clouds = True
        scope_status = "pass"
    elif has_cantilever and appendix_c_mode == "weld_evaluation_principle":
        cantilever_clouds = False
        scope_status = "pass"
    elif has_cantilever:
        cantilever_clouds = False
        scope_status = "needs_scope_confirmation"
    else:
        cantilever_clouds = False
        scope_status = "pass"
        appendix_c_mode = "not_applicable"
        decision_source = "no_cantilever_arm"
    has_root_weld = bool(has_cantilever and square_outer_width_mm is not None)
    equivalent_weld_eval = bool(
        has_cantilever
        and square_outer_width_mm is not None
        and square_outer_width_mm <= SQUARE_SECTION_CANTILEVER_CLOUD_MAX_OUTER_MM
    )

    required_figures: list[str] = list(MODEL_FIGURES)
    modal_figures_required = bool(support_type.startswith("S2") or has_cantilever)
    modal_required = bool(analysis_method != "static" and modal_figures_required)
    if modal_figures_required:
        required_figures.extend(MODAL_FIGURES)
    required_figures.extend(SQUARE_SUPPORT_FIGURES)
    if cantilever_clouds:
        required_figures.extend(CANTILEVER_FIGURES)

    payload = {
        "status": scope_status,
        "classification": "steel_platform" if analysis_method == "static" else "non_steel_platform",
        "analysis_method": analysis_method,
        "support_type": support_type or None,
        "tray": tray,
        "square_outer_width_mm": square_outer_width_mm,
        "square_thickness_mm": square_thickness_mm,
        "square_section_cantilever_cloud_max_outer_mm": SQUARE_SECTION_CANTILEVER_CLOUD_MAX_OUTER_MM,
        "square_section_weld_principle_gt_outer_mm": SQUARE_SECTION_WELD_PRINCIPLE_GT_OUTER_MM,
        "has_cantilever_arm": has_cantilever,
        "has_tray_arm_connection": has_tray_connection,
        "has_cantilever_root_weld": has_root_weld,
        "cantilever_root_weld_equivalent_eval": equivalent_weld_eval,
        "cantilever_root_weld_equivalent_coefficient": CANTILEVER_ROOT_WELD_EQUIVALENT_COEFFICIENT
        if equivalent_weld_eval
        else None,
        "appendix_c_mode": appendix_c_mode if has_cantilever else "not_applicable",
        "cantilever_stress_clouds_required": cantilever_clouds,
        "cantilever_stress_cloud_decision_source": decision_source,
        "requires": {
            "modal_analysis": modal_required,
            "modal_figures": modal_figures_required,
            "modal_frequency_table": modal_figures_required,
            "square_support_stress_eval": True,
            "cantilever_stress_eval": cantilever_clouds,
            "cantilever_root_weld_eval": has_root_weld,
            "cantilever_root_weld_equivalent_stress_table": equivalent_weld_eval,
            "foundation_loads": True,
            "tray_arm_connection_loads": has_tray_connection,
            "bolt_stress_eval": has_tray_connection,
            "appendix_c_cantilever_figures": cantilever_clouds,
        },
        "required_figures": required_figures,
        "forbidden_figures": [] if cantilever_clouds else CANTILEVER_FIGURES,
        "policy": [
            "New intake scope is derived from intake topology and confirmed template/config, not from a future report appendix.",
            "Cantilever root weld loads/evaluation are required for every confirmed S2 cantilever branch. Square tube outer width <= 120 mm uses the equivalent-stress table with coefficient 0.526 and also requires cantilever stress clouds.",
            "Steel-platform support uses static method for seismic loading; S2 reports still require MOTAI appendix figures, but these are generated as post-only low-order modal graphics and do not create a 50 Hz MT gate.",
            "Square tube outer width <= 120 mm uses appendix C cantilever stress-cloud output; outer width > 120 mm uses appendix C weld-evaluation-principle output.",
            "If square tube size is unknown, select a candidate section before publishing cantilever figures.",
        ],
    }
    return payload


def classify_scope_from_job(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    input_path = job_dir / "input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8")) if input_path.exists() else {"metadata": {}}
    scope = classify_scope_from_input(payload)
    (job_dir / "analysis_scope.json").write_text(json.dumps(scope, ensure_ascii=False, indent=2), encoding="utf-8")
    return scope
