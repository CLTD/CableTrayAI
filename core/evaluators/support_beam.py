from __future__ import annotations

import math
import re

from core.evaluators.formula_status import formula_status
from core.evaluators.material_allowables import accident_allowable_factor
from core.evaluators.materials import material_allowables
from core.schemas.input_models import MaterialInput


TODO_SOURCE = "TODO_FORMULA_SOURCE_REQUIRED"
COMBINATION_SOURCE_REF = "report_evaluation_tables:拉弯组合/压弯组合_allowable_1.0_ratio_sum"

NORMAL_LOAD_CASES = {"NORMAL", "UPSET", "B", "SL-1", "SL1"}
ACCIDENT_LOAD_CASES = {"FAULTED", "D", "SL-2", "SL2", "ACCIDENT"}
COMPRESSION_ALLOWABLE_SOURCE_REF = "电缆桥架--.xlsx:许用应力!A1:L13;Q235/Q355!H2"
SECTION_AI_BY_OUTER_THICKNESS = {
    (100.0, 6.0): (0.002194, 3.19e-06, "许用应力!E4:F4"),
    (100.0, 8.0): (0.002779, 3.80e-06, "许用应力!E5:F5"),
    (120.0, 6.0): (0.002674, 5.73e-06, "许用应力!E6:F6"),
    (120.0, 8.0): (0.003419, 6.97e-06, "许用应力!E7:F7"),
    (120.0, 10.0): (0.004142, 8.08e-06, "许用应力!E8:F8"),
    (120.0, 12.0): (0.004813, 8.97e-06, "许用应力!E9:F9"),
    (140.0, 6.0): (0.003154, 9.35e-06, "许用应力!E10:F10"),
    (140.0, 8.0): (0.004059, 1.15e-05, "许用应力!E11:F11"),
    (160.0, 8.0): (0.004699, 1.78e-05, "许用应力!E12:F12"),
    (160.0, 12.0): (0.006733, 2.39e-05, "许用应力!E13:F13"),
}


def _pass_fail(ratio: float | None) -> str:
    if ratio is None:
        return "待确认"
    return "不满足" if ratio > 1.0 else "满足"


def _evaluation_item(
    check_id: str,
    category: str,
    calculation_value: float | None,
    allowable_value: float | None,
    unit: str | None,
    source_ref: str,
    notes: str | None = None,
    **extra: object,
) -> dict:
    ratio = None
    if calculation_value is not None and allowable_value not in (None, 0):
        ratio = abs(calculation_value) / allowable_value
    item = {
        "check_id": check_id,
        "category": category,
        "calculation_value": calculation_value,
        "allowable_value": allowable_value,
        "ratio": ratio,
        "pass_fail": _pass_fail(ratio),
        "unit": unit,
        "source_ref": source_ref,
        "formula_status": formula_status(source_ref),
        "notes": notes,
    }
    item.update(extra)
    return item


def _canonical_stress_type(stress_type: str) -> str:
    aliases = {
        "TENSION": "SDIR_TENSION",
        "SDIR_TEN": "SDIR_TENSION",
        "COMPRESSION": "SDIR_COMPRESSION",
        "SDIR_COM": "SDIR_COMPRESSION",
        "BEND": "SBEND",
        "SSHEAR": "SHEAR",
    }
    key = aliases.get(stress_type.upper(), stress_type.upper())
    if key.startswith("SBEND"):
        return "SBEND"
    if key.startswith("SHEAR"):
        return "SHEAR"
    return key


def _max_stress_by_type(beam_rows: list[dict], load_cases: set[str] | None = None) -> dict[str, float]:
    max_by_type: dict[str, float] = {}
    for row in beam_rows:
        if load_cases is not None:
            load_case = str(row.get("load_case") or "").upper()
            if not load_case:
                if not {"NORMAL", "UPSET"} <= load_cases:
                    continue
            elif load_case not in load_cases:
                continue
        stress_type = _canonical_stress_type(str(row["stress_type"]))
        value = abs(float(row["value_mpa"]))
        max_by_type[stress_type] = max(value, max_by_type.get(stress_type, 0.0))
    return max_by_type


def _specific_allowable(material: MaterialInput, field: str, fallback: dict | None) -> dict | None:
    value = getattr(material, field)
    if value is None:
        return fallback
    return {"value": value, "unit": "MPa", "source_ref": material.source_ref}


def _accident_allowable(material: MaterialInput, base: dict | None) -> dict | None:
    if not base or not base.get("value"):
        return base
    if not material.yield_strength_mpa or not material.tensile_strength_mpa:
        return None
    factor = accident_allowable_factor(material.yield_strength_mpa, material.tensile_strength_mpa)
    return {
        "value": float(base["value"]) * factor,
        "unit": "MPa",
        "source_ref": f"{base['source_ref']}:accident_allowable_factor={factor:.12g}",
    }


def _parse_square_section(section_id: str | None) -> tuple[float, float] | None:
    if not section_id:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-*xX×]\s*\1\s*[-*xX×]\s*(\d+(?:\.\d+)?)", section_id)
    if match:
        return float(match.group(1)), float(match.group(2))
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-*xX×]\s*(\d+(?:\.\d+)?)", section_id)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None


def compression_allowable_from_excel_table(
    *,
    section_id: str | None,
    member_length_m: float | None,
    material: MaterialInput,
    k_factor: float = 2.0,
) -> dict | None:
    """Compression allowable from the workbook equation-4/equation-5 path.

    Area A and inertia I are taken from the workbook allowable-stress table.
    The member length L is supplied by the current square-tube/support geometry,
    then equations 4 and 5 decide the compression limit by KL/R versus Cc.
    """

    parsed = _parse_square_section(section_id)
    if parsed is None or member_length_m is None:
        return None
    area_inertia = SECTION_AI_BY_OUTER_THICKNESS.get(parsed)
    if area_inertia is None:
        return None
    area_m2, inertia_m4, source_cell = area_inertia
    if area_m2 <= 0 or inertia_m4 <= 0:
        return None
    elastic_modulus_mpa = float(material.elastic_modulus_pa) / 1_000_000.0
    yield_strength_mpa = float(material.yield_strength_mpa or 0.0)
    if elastic_modulus_mpa <= 0 or yield_strength_mpa <= 0:
        return None
    pi = 3.14
    radius_m = math.sqrt(inertia_m4 / area_m2)
    slenderness = k_factor * float(member_length_m) / radius_m
    cc = math.sqrt(2.0 * pi * pi * elastic_modulus_mpa / yield_strength_mpa)
    equation4 = (
        (1.0 - 0.5 * slenderness**2 / cc**2)
        * yield_strength_mpa
        / (5.0 / 3.0 + 3.0 * slenderness / (8.0 * cc) - slenderness**3 / (8.0 * cc**3))
    )
    equation5 = 12.0 * pi * pi * elastic_modulus_mpa / (23.0 * slenderness**2)
    value = equation4 if slenderness < cc else equation5
    equation_id = "equation4_kl_over_r_lt_cc" if slenderness < cc else "equation5_kl_over_r_ge_cc"
    return {
        "value": value,
        "unit": "MPa",
        "source_ref": (
            f"{COMPRESSION_ALLOWABLE_SOURCE_REF}:{source_cell}:L={float(member_length_m):.6g}m:"
            f"KL/R={slenderness:.6g}:Cc={cc:.6g}:{equation_id}:material={material.source_ref}"
        ),
        "equation_id": equation_id,
        "slenderness_kl_over_r": slenderness,
        "cc": cc,
    }


def _evaluate_case_group(
    *,
    beam_rows: list[dict],
    group_id: str,
    group_label: str,
    load_cases: set[str],
    tension_allowable: dict | None,
    compression_allowable: dict | None,
    bending_allowable: dict | None,
    shear_allowable: dict | None,
    suffix: str = "",
) -> list[dict]:
    max_by_type = _max_stress_by_type(beam_rows, load_cases)
    checks = [
        ("support_tension", "支架梁拉伸", "SDIR_TENSION", tension_allowable),
        ("support_compression", "支架梁压缩", "SDIR_COMPRESSION", compression_allowable),
        ("support_bending", "支架梁弯曲", "SBEND", bending_allowable),
        ("support_shear", "支架梁剪切", "SHEAR", shear_allowable),
    ]
    items: list[dict] = []
    ratios: dict[str, float | None] = {}
    for check_id, category, stress_type, allowable in checks:
        item = _evaluation_item(
            check_id=f"{check_id}{suffix}",
            category=category,
            calculation_value=max_by_type.get(stress_type),
            allowable_value=allowable["value"] if allowable else None,
            unit="MPa",
            source_ref=allowable["source_ref"] if allowable else TODO_SOURCE,
            notes=None if allowable else TODO_SOURCE,
            stress_type=stress_type,
            load_case_group=group_id,
            load_case_group_label=group_label,
            load_cases=sorted(load_cases),
        )
        items.append(item)
        ratios[check_id] = item["ratio"]

    bending_ratio = ratios.get("support_bending")
    for check_id, category, first_ratio in (
        ("support_tension_bending_combined", "支架梁拉弯组合", ratios.get("support_tension")),
        ("support_compression_bending_combined", "支架梁压弯组合", ratios.get("support_compression")),
    ):
        calculation = first_ratio + bending_ratio if first_ratio is not None and bending_ratio is not None else None
        items.append(
            _evaluation_item(
                check_id=f"{check_id}{suffix}",
                category=category,
                calculation_value=calculation,
                allowable_value=1.0,
                unit="MPa",
                source_ref=COMBINATION_SOURCE_REF,
                notes="Combination check follows the report table convention: stress-ratio sum is checked against allowable value 1.0.",
                stress_type=check_id,
                load_case_group=group_id,
                load_case_group_label=group_label,
                load_cases=sorted(load_cases),
            )
        )
    return items


def evaluate_support_beam(
    beam_rows: list[dict],
    material: MaterialInput,
    *,
    section_id: str | None = None,
    member_length_m: float | None = None,
) -> list[dict]:
    """Evaluate support stresses by report load-case group.

    The report chapter 6 tables are not a single max envelope. They use a
    normal/abnormal group and an accident group with different allowables.
    Collapsing all cases before the allowable check incorrectly makes valid
    accident stresses fail against normal allowables.
    """

    allowables = material_allowables(material)
    normal_allowable = allowables.get("normal")
    shear_allowable = allowables.get("shear")
    tension_allowable = _specific_allowable(material, "allowable_tension_mpa", normal_allowable)
    compression_allowable = compression_allowable_from_excel_table(
        section_id=section_id,
        member_length_m=member_length_m,
        material=material,
    ) or _specific_allowable(material, "allowable_compression_mpa", normal_allowable)
    bending_allowable = _specific_allowable(material, "allowable_bending_mpa", normal_allowable)

    items = _evaluate_case_group(
        beam_rows=beam_rows,
        group_id="normal_abnormal",
        group_label="正常/异常",
        load_cases=NORMAL_LOAD_CASES,
        tension_allowable=tension_allowable,
        compression_allowable=compression_allowable,
        bending_allowable=bending_allowable,
        shear_allowable=shear_allowable,
    )
    items.extend(
        _evaluate_case_group(
            beam_rows=beam_rows,
            group_id="accident",
            group_label="事故",
            load_cases=ACCIDENT_LOAD_CASES,
            tension_allowable=_accident_allowable(material, tension_allowable),
            compression_allowable=_accident_allowable(material, compression_allowable),
            bending_allowable=_accident_allowable(material, bending_allowable),
            shear_allowable=_accident_allowable(material, shear_allowable),
            suffix="_accident",
        )
    )
    return items
