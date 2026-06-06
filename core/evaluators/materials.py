from __future__ import annotations

from core.schemas.input_models import MaterialInput


SOURCE_ALLOWABLE_NORMAL = "电缆桥架结果评定-q235材料.xlsx:应力评定!G2"
SOURCE_ALLOWABLE_SHEAR = "电缆桥架结果评定-q235材料.xlsx:应力评定!J2"


def material_allowables(material: MaterialInput) -> dict[str, dict]:
    allowables: dict[str, dict] = {}
    if material.allowable_normal_mpa is not None:
        allowables["normal"] = {
            "value": material.allowable_normal_mpa,
            "unit": "MPa",
            "source_ref": material.source_ref,
        }
    elif material.yield_strength_mpa and material.tensile_strength_mpa:
        allowables["normal"] = {
            "value": min(0.45 * material.yield_strength_mpa, 0.37 * material.tensile_strength_mpa),
            "unit": "MPa",
            "source_ref": SOURCE_ALLOWABLE_NORMAL,
        }

    if material.allowable_shear_mpa is not None:
        allowables["shear"] = {
            "value": material.allowable_shear_mpa,
            "unit": "MPa",
            "source_ref": material.source_ref,
        }
    elif material.yield_strength_mpa and material.tensile_strength_mpa:
        allowables["shear"] = {
            "value": min(0.4 * material.yield_strength_mpa, 0.33 * material.tensile_strength_mpa),
            "unit": "MPa",
            "source_ref": SOURCE_ALLOWABLE_SHEAR,
        }
    return allowables
