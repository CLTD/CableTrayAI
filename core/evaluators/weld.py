from __future__ import annotations

import math

from core.evaluators.formula_status import formula_status


SOURCE_WELD_THROAT = "电缆桥架结果评定-q235材料.xlsx:异型钢焊缝评定!J30"
SOURCE_WELD_RATIO = "电缆桥架结果评定-q235材料.xlsx:异型钢焊缝评定!I34:O34"
SOURCE_WELD_EQUIVALENT = "电缆桥架结果评定-q235材料.xlsx:异型钢焊缝评定!C39:K41"
TODO_SOURCE = "TODO_FORMULA_SOURCE_REQUIRED"

WELD_AREA_M2 = 0.000684
WELD_IYY_M4 = 7.24e-7
WELD_IZZ_M4 = 2.13e-6
WELD_YMAX_M = 0.15 / 2.0 + 0.002 * math.sqrt(2.0) / 2.0
WELD_ZMAX_M = 0.08 / 2.0 + 0.002 * math.sqrt(2.0) / 2.0
WELD_IP_M4 = WELD_IYY_M4 + WELD_IZZ_M4
WELD_SHEAR_COEFF_YY = 0.61
WELD_SHEAR_COEFF_ZZ = 0.39
WELD_BASE_ALLOWABLE_MPA = 145.0
WELD_ACCIDENT_FACTOR = 1.545
CANTILEVER_ROOT_WELD_EQUIVALENT_COEFFICIENT = 0.526
CANTILEVER_ROOT_WELD_EQUIVALENT_SOURCE = (
    "report_evaluation_tables:表6-2-1 托臂根部焊缝评定结果;"
    "source=TMAXBEAMSTRESS.LIS;equivalent_coefficient=0.526"
)


def effective_weld_throat_mm(weld_size_mm: float) -> dict:
    return {
        "value": weld_size_mm * math.sqrt(2.0) / 2.0,
        "unit": "mm",
        "source_ref": SOURCE_WELD_THROAT,
    }


def _metric_value(values: dict, key: str, default: float = 0.0) -> float:
    value = values.get(key)
    if isinstance(value, dict):
        value = value.get("value", value.get("normalized_value", value.get("raw_value")))
    if value is None:
        return default
    return float(value)


def weld_equivalent_from_loads(
    fx_n: float,
    fy_n: float,
    fz_n: float,
    mx_nm: float,
    my_nm: float,
    mz_nm: float,
    *,
    accident: bool = False,
) -> dict[str, float]:
    """Replicate the confirmed workbook weld stress path from force resultants.

    Formula source: `异型钢焊缝评定!C39:K41`.
    """
    axial_mpa = abs(fx_n) / WELD_AREA_M2 / 1_000_000.0
    shear_y_mpa = abs(fy_n) / WELD_AREA_M2 / WELD_SHEAR_COEFF_YY / 1_000_000.0
    shear_z_mpa = abs(fz_n) / WELD_AREA_M2 / WELD_SHEAR_COEFF_ZZ / 1_000_000.0
    bending_y_mpa = abs(my_nm) / WELD_IYY_M4 * WELD_ZMAX_M / 1_000_000.0
    bending_z_mpa = abs(mz_nm) / WELD_IZZ_M4 * WELD_YMAX_M / 1_000_000.0
    torsion_y_mpa = abs(mx_nm) / WELD_IP_M4 * WELD_ZMAX_M / 1_000_000.0
    torsion_z_mpa = abs(mx_nm) / WELD_IP_M4 * WELD_YMAX_M / 1_000_000.0
    shear_resultant_mpa = ((shear_y_mpa + torsion_y_mpa) ** 2 + (shear_z_mpa + torsion_z_mpa) ** 2) ** 0.5
    membrane_mpa = (axial_mpa**2 + 3.0 * shear_resultant_mpa**2) ** 0.5
    equivalent_mpa = ((axial_mpa + bending_y_mpa + bending_z_mpa) ** 2 + 3.0 * shear_resultant_mpa**2) ** 0.5
    allowable = WELD_BASE_ALLOWABLE_MPA * (WELD_ACCIDENT_FACTOR if accident else 1.0)
    return {
        "shear_mpa": shear_resultant_mpa,
        "membrane_mpa": membrane_mpa,
        "equivalent_mpa": equivalent_mpa,
        "allowable_shear_mpa": 0.6 * allowable,
        "allowable_equivalent_mpa": allowable,
    }


def _weld_items_from_force_row(row: dict) -> list[dict]:
    values = row.get("values") or {}
    if not {"fx", "fy", "fz", "mx", "my", "mz"}.issubset(values):
        return []
    load_case = str(row.get("load_case") or "").upper()
    accident = load_case in {"FAULTED", "D", "SL-2", "ACCIDENT"}
    stresses = weld_equivalent_from_loads(
        _metric_value(values, "fx"),
        _metric_value(values, "fy"),
        _metric_value(values, "fz"),
        _metric_value(values, "mx"),
        _metric_value(values, "my"),
        _metric_value(values, "mz"),
        accident=accident,
    )
    prefix = f"{row.get('name', 'weld_force')}_{row.get('load_case', 'case')}".lower()
    output: list[dict] = []
    for suffix, category, value_key, allowable_key in (
        ("weld_shear", "焊缝剪切", "shear_mpa", "allowable_shear_mpa"),
        ("weld_equivalent", "焊缝等效应力", "equivalent_mpa", "allowable_equivalent_mpa"),
    ):
        value = stresses[value_key]
        allowable = stresses[allowable_key]
        ratio = value / allowable if allowable else None
        output.append(
            {
                "check_id": f"{prefix}_{suffix}",
                "category": category,
                "calculation_value": value,
                "allowable_value": allowable,
                "ratio": ratio,
                "pass_fail": "待确认" if ratio is None else ("不满足" if ratio > 1.0 else "满足"),
                "unit": "MPa",
                "source_ref": SOURCE_WELD_EQUIVALENT,
                "formula_status": formula_status(SOURCE_WELD_EQUIVALENT),
                "notes": "Weld force-to-stress path follows the confirmed evaluation workbook.",
            }
        )
    return output


def evaluate_weld_forces(weld_results: list[dict], weld_size_mm: float | None = None) -> list[dict]:
    items: list[dict] = []
    if weld_size_mm is not None:
        throat = effective_weld_throat_mm(weld_size_mm)
        items.append(
            {
                "check_id": "weld_effective_throat",
                "category": "焊缝有效焊喉",
                "calculation_value": throat["value"],
                "allowable_value": None,
                "ratio": None,
                "pass_fail": "记录",
                "unit": throat["unit"],
                "source_ref": throat["source_ref"],
                "formula_status": formula_status(throat["source_ref"]),
                "notes": "Geometry-derived value used by downstream weld stress checks.",
            }
        )
    for row in weld_results:
        derived_items = _weld_items_from_force_row(row)
        if derived_items:
            items.extend(derived_items)
            continue
        stress = float(row["values"]["stress_mpa"]["value"])
        allowable = float(row["values"]["allowable_mpa"]["value"])
        ratio = stress / allowable if allowable else None
        source_ref = SOURCE_WELD_RATIO if ratio is not None else TODO_SOURCE
        items.append(
            {
                "check_id": f"{row['name']}_{row['load_case']}_weld_stress".lower(),
                "category": "焊缝应力",
                "calculation_value": stress,
                "allowable_value": allowable,
                "ratio": ratio,
                "pass_fail": "待确认" if ratio is None else ("不满足" if ratio > 1.0 else "满足"),
                "unit": "MPa",
                "source_ref": source_ref,
                "formula_status": formula_status(source_ref),
                "notes": None if ratio is not None else "allowable value is missing or zero",
            }
        )
    return items


def evaluate_cantilever_root_equivalent_weld_from_stress_items(support_items: list[dict]) -> list[dict]:
    """Build <=120 mm cantilever-root weld equivalent-stress checks.

    This branch is different from the large-section HF-FORCE branch.  The
    report table uses the cantilever/root stress extraction from
    TMAXBEAMSTRESS.LIS and converts it by the confirmed report coefficient
    0.526 before comparing against the same stress-type allowable.
    """

    stress_type_names = {
        "SDIR_TENSION": "拉伸应力",
        "SDIR_COMPRESSION": "压缩应力",
        "SBEND": "弯曲应力",
        "SHEAR": "剪切应力",
    }
    suffixes = {
        "SDIR_TENSION": "tension",
        "SDIR_COMPRESSION": "compression",
        "SBEND": "bending",
        "SHEAR": "shear",
    }
    output: list[dict] = []
    for item in support_items:
        stress_type = str(item.get("stress_type") or "").upper()
        if stress_type not in stress_type_names:
            continue
        base_value = abs(float(item.get("calculation_value") or 0.0))
        allowable = item.get("allowable_value")
        if allowable is None:
            continue
        equivalent_value = base_value / CANTILEVER_ROOT_WELD_EQUIVALENT_COEFFICIENT
        ratio = equivalent_value / float(allowable) if float(allowable) else None
        group = str(item.get("load_case_group") or "case")
        group_label = item.get("load_case_group_label")
        output.append(
            {
                "check_id": f"cantilever_root_weld_equivalent.{group}.{suffixes[stress_type]}",
                "category": stress_type_names[stress_type],
                "calculation_value": base_value,
                "equivalent_stress_value": equivalent_value,
                "equivalent_coefficient": CANTILEVER_ROOT_WELD_EQUIVALENT_COEFFICIENT,
                "allowable_value": float(allowable),
                "ratio": ratio,
                "pass_fail": "待确认" if ratio is None else ("不满足" if ratio > 1.0 else "满足"),
                "unit": "MPa",
                "source_ref": CANTILEVER_ROOT_WELD_EQUIVALENT_SOURCE,
                "formula_status": formula_status(CANTILEVER_ROOT_WELD_EQUIVALENT_SOURCE),
                "notes": "Square tube outer width <= 120 mm branch: TMAXBEAMSTRESS.LIS stress divided by equivalent coefficient 0.526.",
                "stress_type": stress_type,
                "load_case_group": group,
                "load_case_group_label": group_label,
                "load_cases": item.get("load_cases"),
                "component": "cantilever_root_weld",
                "material_id": item.get("material_id"),
                "source_file": "TMAXBEAMSTRESS.LIS",
                "base_component_check_id": item.get("check_id"),
            }
        )
    return output
