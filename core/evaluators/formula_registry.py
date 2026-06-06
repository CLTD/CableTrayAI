from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from core.evaluators.bolt import SOURCE_BOLT_COMBINED, bolt_tension_shear_interaction
from core.evaluators.materials import SOURCE_ALLOWABLE_NORMAL, SOURCE_ALLOWABLE_SHEAR
from core.evaluators.weld import SOURCE_WELD_THROAT
from core.evaluators.material_allowables import normal_shear_allowable, normal_tension_allowable


TODO_FORMULA_SOURCE_REQUIRED = "TODO_FORMULA_SOURCE_REQUIRED"


@dataclass(frozen=True)
class FormulaRecord:
    formula_id: str
    status: str
    source_ref: str
    description: str
    function: Callable[..., float] | None = None


def material_allowable_normal(yield_strength_mpa: float, tensile_strength_mpa: float) -> float:
    return normal_tension_allowable(yield_strength_mpa, tensile_strength_mpa)


def material_allowable_shear(yield_strength_mpa: float, tensile_strength_mpa: float) -> float:
    return normal_shear_allowable(yield_strength_mpa, tensile_strength_mpa)


def direct_stress_ratio(stress_mpa: float, allowable_mpa: float) -> float:
    if allowable_mpa == 0:
        raise ZeroDivisionError("allowable_mpa must not be zero")
    return abs(stress_mpa) / allowable_mpa


def weld_effective_throat(weld_size_mm: float) -> float:
    return weld_size_mm * math.sqrt(2.0) / 2.0


FORMULA_REGISTRY: dict[str, FormulaRecord] = {
    "material_allowable_normal": FormulaRecord(
        "material_allowable_normal",
        "implemented",
        SOURCE_ALLOWABLE_NORMAL,
        "Normal allowable stress from confirmed evaluation workbook pattern.",
        material_allowable_normal,
    ),
    "material_allowable_shear": FormulaRecord(
        "material_allowable_shear",
        "implemented",
        SOURCE_ALLOWABLE_SHEAR,
        "Shear allowable stress from confirmed evaluation workbook pattern.",
        material_allowable_shear,
    ),
    "direct_stress_ratio": FormulaRecord(
        "direct_stress_ratio",
        "implemented",
        "电缆桥架结果评定-q235材料.xlsx:应力评定!K20/T20",
        "Direct stress ratio is calculation value divided by allowable value.",
        direct_stress_ratio,
    ),
    "bolt_tension_shear_combination": FormulaRecord(
        "bolt_tension_shear_combination",
        "implemented",
        SOURCE_BOLT_COMBINED,
        "Mechanical bolt interaction as tension_ratio^2 + shear_ratio^2.",
        bolt_tension_shear_interaction,
    ),
    "weld_effective_throat": FormulaRecord(
        "weld_effective_throat",
        "implemented",
        SOURCE_WELD_THROAT,
        "Effective weld throat for fillet welds.",
        weld_effective_throat,
    ),
    "support_tension_bending_combination": FormulaRecord(
        "support_tension_bending_combination",
        "todo",
        TODO_FORMULA_SOURCE_REQUIRED,
        "Requires workbook cell and RCC-M clause confirmation.",
    ),
    "support_compression_bending_combination": FormulaRecord(
        "support_compression_bending_combination",
        "todo",
        TODO_FORMULA_SOURCE_REQUIRED,
        "Requires workbook cell and RCC-M clause confirmation.",
    ),
    "weld_equivalent_stress": FormulaRecord(
        "weld_equivalent_stress",
        "todo",
        TODO_FORMULA_SOURCE_REQUIRED,
        "Requires confirmed component stress combination.",
    ),
    "expansion_bolt_combination": FormulaRecord(
        "expansion_bolt_combination",
        "todo",
        TODO_FORMULA_SOURCE_REQUIRED,
        "Requires confirmed expansion bolt interaction equation.",
    ),
}


def implemented_formulas() -> dict[str, FormulaRecord]:
    return {key: value for key, value in FORMULA_REGISTRY.items() if value.status == "implemented"}


def todo_formulas() -> dict[str, FormulaRecord]:
    return {key: value for key, value in FORMULA_REGISTRY.items() if value.status != "implemented"}


def formula_source_audit() -> dict:
    records = []
    for formula_id, record in FORMULA_REGISTRY.items():
        has_source = bool(record.source_ref) and record.source_ref != TODO_FORMULA_SOURCE_REQUIRED
        records.append(
            {
                "formula_id": formula_id,
                "status": record.status,
                "source_ref": record.source_ref,
                "has_confirmed_source": has_source,
                "can_support_final_pass": record.status == "implemented" and has_source,
            }
        )
    blockers = [
        item
        for item in records
        if item["status"] == "implemented" and not item["has_confirmed_source"]
    ]
    todos = [item for item in records if item["status"] != "implemented"]
    return {
        "status": "fail" if blockers else ("warning" if todos else "pass"),
        "records": records,
        "blockers": blockers,
        "todo_formulas": todos,
        "policy": "No formula may be used for a final pass unless it has an Excel/report/manual/spec source_ref.",
    }
