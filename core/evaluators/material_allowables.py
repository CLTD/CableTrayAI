from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BasicMaterialStrength:
    material_id: str
    yield_strength_mpa: float
    tensile_strength_mpa: float
    source_ref: str


@dataclass(frozen=True)
class BasicAllowables:
    material_id: str
    tension_mpa: float
    bending_mpa: float
    shear_mpa: float
    accident_factor: float
    accident_tension_mpa: float
    accident_bending_mpa: float
    accident_shear_mpa: float
    source_ref: str


def normal_tension_allowable(yield_strength_mpa: float, tensile_strength_mpa: float) -> float:
    return min(0.45 * yield_strength_mpa, 0.37 * tensile_strength_mpa)


def normal_bending_allowable(yield_strength_mpa: float, tensile_strength_mpa: float) -> float:
    return min(0.66 * yield_strength_mpa, 0.55 * tensile_strength_mpa)


def normal_shear_allowable(yield_strength_mpa: float, tensile_strength_mpa: float) -> float:
    return min(0.4 * yield_strength_mpa, 0.33 * tensile_strength_mpa)


def accident_allowable_factor(yield_strength_mpa: float, tensile_strength_mpa: float) -> float:
    if tensile_strength_mpa >= 1.2 * yield_strength_mpa:
        return min(1.66, 1.167 * tensile_strength_mpa / yield_strength_mpa)
    return 1.4


def basic_allowables(strength: BasicMaterialStrength) -> BasicAllowables:
    tension = normal_tension_allowable(strength.yield_strength_mpa, strength.tensile_strength_mpa)
    bending = normal_bending_allowable(strength.yield_strength_mpa, strength.tensile_strength_mpa)
    shear = normal_shear_allowable(strength.yield_strength_mpa, strength.tensile_strength_mpa)
    factor = accident_allowable_factor(strength.yield_strength_mpa, strength.tensile_strength_mpa)
    return BasicAllowables(
        material_id=strength.material_id,
        tension_mpa=tension,
        bending_mpa=bending,
        shear_mpa=shear,
        accident_factor=factor,
        accident_tension_mpa=tension * factor,
        accident_bending_mpa=bending * factor,
        accident_shear_mpa=shear * factor,
        source_ref=strength.source_ref,
    )


Q235_STRENGTH = BasicMaterialStrength(
    material_id="q235",
    yield_strength_mpa=235.0,
    tensile_strength_mpa=370.0,
    source_ref="电缆桥架--.xlsx:Q235!D2:J3",
)

Q355_STRENGTH = BasicMaterialStrength(
    material_id="q355",
    yield_strength_mpa=355.0,
    tensile_strength_mpa=470.0,
    source_ref="电缆桥架--.xlsx:Q355!D2:J3",
)


def known_basic_allowables() -> dict[str, BasicAllowables]:
    return {
        "q235": basic_allowables(Q235_STRENGTH),
        "q355": basic_allowables(Q355_STRENGTH),
    }
