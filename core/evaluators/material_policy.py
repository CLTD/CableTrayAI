from __future__ import annotations

from typing import Any

from core.evaluators.material_allowables import known_basic_allowables


Q235_BENDING_ALLOWABLE_MPA = 155.10
Q355_BENDING_ALLOWABLE_MPA = 234.30

Q235_SOURCE_REF = "电缆桥架--.xlsx:Q235!G2:J3"
Q355_SOURCE_REF = "电缆桥架--.xlsx:Q355!G2:J3"

DEFAULT_STRUCTURAL_MATERIAL_ID = "q355"
STEEL_PLATFORM_SQUARE_SUPPORT_MATERIAL_ID = "q235"


def is_steel_platform_job(metadata_or_payload: dict[str, Any] | None) -> bool:
    payload = metadata_or_payload or {}
    analysis_method = str(payload.get("analysis_method") or "").strip().lower()
    if analysis_method == "static":
        return True
    combined = " ".join(str(value) for value in payload.values() if value is not None)
    return "钢平台" in combined


def component_material_id(component: str, metadata_or_payload: dict[str, Any] | None) -> str:
    if component == "square_support" and is_steel_platform_job(metadata_or_payload):
        return STEEL_PLATFORM_SQUARE_SUPPORT_MATERIAL_ID
    return DEFAULT_STRUCTURAL_MATERIAL_ID


def production_material_inputs() -> list[dict[str, Any]]:
    allowables = known_basic_allowables()
    q355 = allowables["q355"]
    q235 = allowables["q235"]
    return [
        {
            "material_id": "q355",
            "name": "Q355",
            "elastic_modulus_pa": 2.04e11,
            "poisson_ratio": 0.3,
            "density_kg_m3": 7850,
            "yield_strength_mpa": 355,
            "tensile_strength_mpa": 470,
            "allowable_normal_mpa": q355.tension_mpa,
            "allowable_tension_mpa": q355.tension_mpa,
            "allowable_bending_mpa": q355.bending_mpa,
            "allowable_shear_mpa": q355.shear_mpa,
            "source_ref": Q355_SOURCE_REF,
        },
        {
            "material_id": "q235",
            "name": "Q235",
            "elastic_modulus_pa": 2.04e11,
            "poisson_ratio": 0.3,
            "density_kg_m3": 7850,
            "yield_strength_mpa": 235,
            "tensile_strength_mpa": 370,
            "allowable_normal_mpa": q235.tension_mpa,
            "allowable_tension_mpa": q235.tension_mpa,
            "allowable_bending_mpa": q235.bending_mpa,
            "allowable_shear_mpa": q235.shear_mpa,
            "source_ref": Q235_SOURCE_REF,
        },
    ]


def material_policy_metadata(analysis_method: str, square_section_status: str) -> dict[str, Any]:
    return {
        "material_policy": "default_q355_with_steel_platform_square_support_q235",
        "default_material_id": DEFAULT_STRUCTURAL_MATERIAL_ID,
        "steel_platform_square_support_material_id": STEEL_PLATFORM_SQUARE_SUPPORT_MATERIAL_ID,
        "q355_bending_allowable_mpa": Q355_BENDING_ALLOWABLE_MPA,
        "q235_bending_allowable_mpa": Q235_BENDING_ALLOWABLE_MPA,
        "allowable_formula_source": "电缆桥架--.xlsx:Q235/Q355 normal=min(0.45*Sy,0.37*Su), bending=min(0.66*Sy,0.55*Su), shear=min(0.4*Sy,0.33*Su)",
        "analysis_method": analysis_method,
        "square_section_selection_status": square_section_status,
    }
