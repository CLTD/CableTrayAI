from __future__ import annotations

from core.evaluators.formula_status import formula_status


SOURCE_BOLT_DIRECT = "电缆桥架结果评定-q235材料.xlsx:螺栓!E53:E54"
SOURCE_BOLT_COMBINED = "电缆桥架结果评定-q235材料.xlsx:螺栓!E57"
SOURCE_BOLT_FORCE_TO_STRESS = "电缆桥架结果评定-q235材料.xlsx:螺栓!E51:E57"
TODO_SOURCE = "TODO_FORMULA_SOURCE_REQUIRED"

M8_BOLT_STRESS_AREA_M2 = 3.66e-5
M12_BOLT_GROUP_AREA_M2 = 8.43e-5
BOLT_GROUP_LEVER_ARM_M = 0.241
M12_BOLT_LEVER_ARM_BY_TRAY_WIDTH_M = {
    300: 0.241,
    500: 0.441,
    600: 0.541,
}
DEFAULT_ALLOWABLE_SHEAR_MPA = 100.0
DEFAULT_ALLOWABLE_TENSION_MPA = 240.0
SOURCE_BOLT_SIZE_FROM_TRAY_WIDTH = (
    "1818T5013.pdf: Std.1 uses M12x35 for tray 600/500/300; "
    "Std.2 uses M8x35 for tray 200/100/50"
)
SOURCE_BOLT_FORMULA_M12 = "电缆桥架结果评定-q235材料.xlsx:螺栓 300/500/600!E7:E15,N7:N15"
SOURCE_BOLT_FORMULA_M8 = "电缆桥架结果评定-q235材料.xlsx:螺栓 200!E7:E15,N7:N15"


def _value(force_result: dict, key: str) -> float:
    return float(force_result["values"][key]["value"])


def _metric_value(values: dict, key: str, default: float = 0.0) -> float:
    value = values.get(key)
    if isinstance(value, dict):
        value = value.get("value", value.get("normalized_value", value.get("raw_value")))
    if value is None:
        return default
    return float(value)


def _item(
    check_id: str,
    category: str,
    calculation: float,
    allowable: float,
    source_ref: str,
    *,
    notes: str | None = None,
) -> dict:
    ratio = abs(calculation) / allowable if allowable else None
    item_source_ref = source_ref if ratio is not None else TODO_SOURCE
    return {
        "check_id": check_id,
        "category": category,
        "calculation_value": calculation,
        "allowable_value": allowable,
        "ratio": ratio,
        "pass_fail": "待确认" if ratio is None else ("不满足" if ratio > 1.0 else "满足"),
        "unit": "MPa",
        "source_ref": item_source_ref,
        "formula_status": formula_status(item_source_ref),
        "notes": notes if ratio is not None else "allowable value is missing or zero",
    }


def bolt_tension_shear_interaction(tension_ratio: float, shear_ratio: float) -> float:
    return tension_ratio**2 + shear_ratio**2


def bolt_stresses_from_group_loads(
    fx_n: float,
    fy_n: float,
    fz_n: float,
    my_nm: float,
    mz_nm: float,
    *,
    area_m2: float = M12_BOLT_GROUP_AREA_M2,
    lever_arm_m: float | None = BOLT_GROUP_LEVER_ARM_M,
    force_share_count: float = 2.0,
) -> dict[str, float]:
    """Replicate the workbook bolt-load-to-stress path.

    M12 tray widths 300/500/600 use force sharing and a lever arm:
    shear = sqrt(FX^2 + FY^2) / 2 + MZ / L,
    tension = FZ / 2 + MY / L.

    M8 tray widths 200/100/50 use the workbook 200-page path:
    shear = sqrt(FX^2 + FY^2) + MZ,
    tension = FZ + MY.
    """
    share = max(float(force_share_count or 1.0), 1.0)
    moment_shear_n = abs(mz_nm) if lever_arm_m is None else abs(mz_nm) / lever_arm_m
    moment_tension_n = abs(my_nm) if lever_arm_m is None else abs(my_nm) / lever_arm_m
    shear_force_n = (fx_n**2 + fy_n**2) ** 0.5 / share + moment_shear_n
    tension_force_n = abs(fz_n) / share + moment_tension_n
    shear_mpa = shear_force_n / area_m2 / 1_000_000.0 / 0.9
    tension_mpa = tension_force_n / area_m2 / 1_000_000.0
    return {
        "shear_force_n": shear_force_n,
        "tension_force_n": tension_force_n,
        "shear_mpa": shear_mpa,
        "tension_mpa": tension_mpa,
    }


def _normalise_bolt_result(
    row: dict,
    *,
    area_m2: float = M12_BOLT_GROUP_AREA_M2,
    lever_arm_m: float | None = BOLT_GROUP_LEVER_ARM_M,
    force_share_count: float = 2.0,
    bolt_size: str = "M12",
    geometry_source_ref: str = SOURCE_BOLT_FORCE_TO_STRESS,
    formula_source_ref: str = SOURCE_BOLT_FORCE_TO_STRESS,
) -> dict | None:
    values = row.get("values") or {}
    required = {"tension_mpa", "shear_mpa", "allowable_tension_mpa", "allowable_shear_mpa"}
    if required.issubset(values):
        return row
    force_keys = {"fx", "fy", "fz", "my", "mz"}
    if not force_keys.issubset(values):
        return None
    stresses = bolt_stresses_from_group_loads(
        _metric_value(values, "fx"),
        _metric_value(values, "fy"),
        _metric_value(values, "fz"),
        _metric_value(values, "my"),
        _metric_value(values, "mz"),
        area_m2=area_m2,
        lever_arm_m=lever_arm_m,
        force_share_count=force_share_count,
    )
    enriched = dict(row)
    enriched_values = dict(values)
    enriched_values.update(
        {
            "tension_mpa": {
                "value": stresses["tension_mpa"],
                "unit": "MPa",
                "source_ref": formula_source_ref,
            },
            "shear_mpa": {
                "value": stresses["shear_mpa"],
                "unit": "MPa",
                "source_ref": formula_source_ref,
            },
            "bolt_size": {
                "value": bolt_size,
                "unit": None,
                "source_ref": geometry_source_ref,
            },
            "bolt_stress_area_m2": {
                "value": area_m2,
                "unit": "m^2",
                "source_ref": geometry_source_ref,
            },
            "bolt_group_lever_arm_m": {
                "value": lever_arm_m,
                "unit": "m",
                "source_ref": formula_source_ref,
            },
            "bolt_force_share_count": {
                "value": force_share_count,
                "unit": None,
                "source_ref": formula_source_ref,
            },
            "allowable_tension_mpa": {
                "value": DEFAULT_ALLOWABLE_TENSION_MPA,
                "unit": "MPa",
                "source_ref": "电缆桥架结果评定-q235材料.xlsx:螺栓!E56",
            },
            "allowable_shear_mpa": {
                "value": DEFAULT_ALLOWABLE_SHEAR_MPA,
                "unit": "MPa",
                "source_ref": "电缆桥架结果评定-q235材料.xlsx:螺栓!E55",
            },
        }
    )
    enriched["values"] = enriched_values
    enriched["bolt_stress_source_ref"] = formula_source_ref
    enriched["bolt_size"] = bolt_size
    enriched["bolt_stress_area_m2"] = area_m2
    enriched["bolt_group_lever_arm_m"] = lever_arm_m
    enriched["bolt_force_share_count"] = force_share_count
    enriched["bolt_geometry_source_ref"] = geometry_source_ref
    enriched["bolt_formula_source_ref"] = formula_source_ref
    return enriched


def evaluate_bolt_forces(
    bolt_results: list[dict],
    *,
    bolt_size: str = "M12",
    bolt_area_m2: float = M12_BOLT_GROUP_AREA_M2,
    bolt_moment_lever_arm_m: float | None = BOLT_GROUP_LEVER_ARM_M,
    bolt_force_share_count: float = 2.0,
    bolt_geometry_source_ref: str = SOURCE_BOLT_FORCE_TO_STRESS,
    bolt_formula_source_ref: str = SOURCE_BOLT_FORCE_TO_STRESS,
) -> list[dict]:
    items: list[dict] = []
    for row in bolt_results:
        row = _normalise_bolt_result(
            row,
            area_m2=bolt_area_m2,
            lever_arm_m=bolt_moment_lever_arm_m,
            force_share_count=bolt_force_share_count,
            bolt_size=bolt_size,
            geometry_source_ref=bolt_geometry_source_ref,
            formula_source_ref=bolt_formula_source_ref,
        )
        if row is None:
            continue
        name = row["name"]
        load_case = row["load_case"]
        tension = _value(row, "tension_mpa")
        shear = _value(row, "shear_mpa")
        allowable_tension = _value(row, "allowable_tension_mpa")
        allowable_shear = _value(row, "allowable_shear_mpa")
        tension_ratio = tension / allowable_tension if allowable_tension else None
        shear_ratio = shear / allowable_shear if allowable_shear else None
        combined = (
            bolt_tension_shear_interaction(tension_ratio, shear_ratio)
            if tension_ratio is not None and shear_ratio is not None
            else None
        )
        prefix = f"{name}_{load_case}".lower()
        geometry_note = (
            f"bolt_size={row.get('bolt_size') or bolt_size}; "
            f"stress_area_m2={float(row.get('bolt_stress_area_m2') or bolt_area_m2):g}; "
            f"force_share_count={float(row.get('bolt_force_share_count') or bolt_force_share_count):g}; "
            f"moment_lever_arm_m={row.get('bolt_group_lever_arm_m')}; "
            f"geometry_source={bolt_geometry_source_ref}; "
            f"formula_source={row.get('bolt_formula_source_ref') or bolt_formula_source_ref}"
        )
        direct_source_ref = row.get("bolt_formula_source_ref") or bolt_formula_source_ref
        items.append(
            _item(
                f"{prefix}_bolt_tension",
                "机械螺栓拉伸",
                tension,
                allowable_tension,
                direct_source_ref,
                notes=geometry_note,
            )
        )
        items.append(
            _item(
                f"{prefix}_bolt_shear",
                "机械螺栓剪切",
                shear,
                allowable_shear,
                direct_source_ref,
                notes=geometry_note,
            )
        )
        items.append(
            {
                "check_id": f"{prefix}_bolt_combined",
                "category": "机械螺栓拉剪组合",
                "calculation_value": combined,
                "allowable_value": 1.0,
                "ratio": combined,
                "pass_fail": "待确认" if combined is None else ("不满足" if combined > 1.0 else "满足"),
                "unit": None,
                "source_ref": direct_source_ref if combined is not None else TODO_SOURCE,
                "formula_status": formula_status(direct_source_ref if combined is not None else TODO_SOURCE),
                "notes": f"Excel formula pattern: tension_ratio^2 + shear_ratio^2; {geometry_note}" if combined is not None else "allowable value is missing or zero",
            }
        )
    return items
