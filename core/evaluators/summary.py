from __future__ import annotations

from core.evaluators.bolt import (
    M8_BOLT_STRESS_AREA_M2,
    M12_BOLT_GROUP_AREA_M2,
    M12_BOLT_LEVER_ARM_BY_TRAY_WIDTH_M,
    SOURCE_BOLT_FORMULA_M8,
    SOURCE_BOLT_FORMULA_M12,
    SOURCE_BOLT_SIZE_FROM_TRAY_WIDTH,
    evaluate_bolt_forces,
)
from core.evaluators.material_policy import component_material_id
from core.evaluators.support_beam import evaluate_support_beam
from core.evaluators.weld import evaluate_cantilever_root_equivalent_weld_from_stress_items, evaluate_weld_forces
from core.schemas.input_models import CableTrayInput
from core.validation.analysis_scope import classify_scope_from_input


def _input_payload(cable_input: CableTrayInput) -> dict:
    if hasattr(cable_input, "model_dump"):
        return cable_input.model_dump(mode="json")
    return cable_input.dict()


def _has_nonzero_stress(rows: list[dict]) -> bool:
    for row in rows:
        try:
            if abs(float(row.get("value_mpa") or 0.0)) > 1e-9:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _bolt_geometry_from_input(cable_input: CableTrayInput) -> dict:
    widths = [
        float(layer.tray_width_m) * 1000.0
        for layer in cable_input.tray_layers
        if getattr(layer, "tray_width_m", None) is not None
    ]
    max_width = max(widths) if widths else None
    if max_width is not None and max_width <= 200.0:
        return {
            "bolt_size": "M8",
            "bolt_area_m2": M8_BOLT_STRESS_AREA_M2,
            "bolt_moment_lever_arm_m": None,
            "bolt_force_share_count": 1.0,
            "bolt_geometry_source_ref": SOURCE_BOLT_SIZE_FROM_TRAY_WIDTH,
            "bolt_formula_source_ref": SOURCE_BOLT_FORMULA_M8,
            "max_tray_width_mm": max_width,
            "formula_policy": "tray_width_le_200_uses_workbook_200_m8_single_bolt_path",
        }
    standard_width = 300
    if max_width is not None:
        if max_width <= 300.0:
            standard_width = 300
        elif max_width <= 500.0:
            standard_width = 500
        else:
            standard_width = 600
    return {
        "bolt_size": "M12",
        "bolt_area_m2": M12_BOLT_GROUP_AREA_M2,
        "bolt_moment_lever_arm_m": M12_BOLT_LEVER_ARM_BY_TRAY_WIDTH_M[standard_width],
        "bolt_force_share_count": 2.0,
        "bolt_geometry_source_ref": SOURCE_BOLT_SIZE_FROM_TRAY_WIDTH,
        "bolt_formula_source_ref": f"{SOURCE_BOLT_FORMULA_M12}:tray_width_page={standard_width}",
        "max_tray_width_mm": max_width,
        "formula_policy": f"tray_width_gt_200_uses_workbook_{standard_width}_m12_two_bolt_lever_arm_path",
    }


def build_evaluation_summary(result: dict, cable_input: CableTrayInput) -> list[dict]:
    items: list[dict] = []
    scope = classify_scope_from_input(_input_payload(cable_input))
    requires = scope.get("requires") or {}
    beam_rows = result.get("beam_stress_results", [])
    grouped: dict[str, list[dict]] = {}
    for row in beam_rows:
        component = str(row.get("report_component_hint") or row.get("component") or "support")
        grouped.setdefault(component, []).append(row)
    if not grouped:
        grouped["support"] = []
    component_eval_items: dict[str, list[dict]] = {}
    for component, rows in grouped.items():
        if component == "cantilever_arm" and not requires.get("cantilever_stress_eval") and not _has_nonzero_stress(rows):
            continue
        material_id = component_material_id(component, cable_input.metadata)
        try:
            material = cable_input.material_by_id(material_id)
        except KeyError:
            material = cable_input.material_by_id(cable_input.support.material_id)
        section_id = cable_input.support.support_section_id if component != "cantilever_arm" else None
        member_length_m = cable_input.support.support_height_m if component != "cantilever_arm" else None
        for item in evaluate_support_beam(
            rows,
            material,
            section_id=section_id,
            member_length_m=member_length_m,
        ):
            item["component"] = component
            item["material_id"] = material.material_id
            item["check_id"] = f"{component}.{item['check_id']}"
            item["notes"] = "component material policy applied" if item.get("notes") is None else item.get("notes")
            items.append(item)
            component_eval_items.setdefault(component, []).append(item)
    if requires.get("cantilever_root_weld_equivalent_stress_table"):
        items.extend(
            evaluate_cantilever_root_equivalent_weld_from_stress_items(
                component_eval_items.get("cantilever_arm") or component_eval_items.get("mixed_beam_type_1") or []
            )
        )
    bolt_geometry = _bolt_geometry_from_input(cable_input)
    items.extend(
        evaluate_bolt_forces(
            result.get("bolt_force_results", []),
            bolt_size=bolt_geometry["bolt_size"],
            bolt_area_m2=bolt_geometry["bolt_area_m2"],
            bolt_moment_lever_arm_m=bolt_geometry["bolt_moment_lever_arm_m"],
            bolt_force_share_count=bolt_geometry["bolt_force_share_count"],
            bolt_geometry_source_ref=bolt_geometry["bolt_geometry_source_ref"],
            bolt_formula_source_ref=bolt_geometry["bolt_formula_source_ref"],
        )
    )
    items.extend(
        evaluate_weld_forces(
            result.get("weld_force_results", []),
            weld_size_mm=cable_input.support.weld_size_mm,
        )
    )
    return items


def build_audit_comments(evaluation_summary: list[dict]) -> list[dict]:
    comments: list[dict] = []
    for item in evaluation_summary:
        ratio = item.get("ratio")
        if item.get("pass_fail") == "不满足":
            comments.append(
                {
                    "severity": "必改",
                    "location": item["check_id"],
                    "issue": "Evaluation ratio exceeds 1.0.",
                    "evidence": f"ratio={ratio}",
                    "suggested_fix": "Revise input, support section, weld, or bolt design and rerun deterministic calculation.",
                    "source_ref": item["source_ref"],
                    "accepted": False,
                    "ignored_reason": None,
                }
            )
        elif ratio is not None and ratio < 0.7:
            comments.append(
                {
                    "severity": "经济性",
                    "location": item["check_id"],
                    "issue": "Evaluation ratio is below 0.7 and may indicate conservative sizing.",
                    "evidence": f"ratio={ratio}",
                    "suggested_fix": "Optimization is only advisory; any adopted change must be recalculated.",
                    "source_ref": item["source_ref"],
                    "accepted": False,
                    "ignored_reason": None,
                }
            )
        elif item.get("source_ref") == "TODO_FORMULA_SOURCE_REQUIRED":
            comments.append(
                {
                    "severity": "风险",
                    "location": item["check_id"],
                    "issue": "Formula source is not confirmed.",
                    "evidence": item.get("notes"),
                    "suggested_fix": "Confirm the workbook cell and RCC-M clause before production use.",
                    "source_ref": item["source_ref"],
                    "accepted": False,
                    "ignored_reason": None,
                }
            )
    return comments
