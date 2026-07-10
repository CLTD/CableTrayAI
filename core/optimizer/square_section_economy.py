from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


DEFAULT_ECONOMY_CONFIG = Path(__file__).resolve().parents[2] / "config" / "square_section_economy.json"


@lru_cache(maxsize=4)
def load_square_section_economy_config(config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_ECONOMY_CONFIG
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Square-section economy config must be an object: {path}")
    payload = dict(payload)
    payload["config_path"] = str(path)
    return payload


def square_section_economy_metrics(
    *,
    outer_mm: float,
    thickness_mm: float,
    config_path: str | None = None,
) -> dict[str, Any]:
    config = load_square_section_economy_config(config_path)
    inner_mm = max(0.0, float(outer_mm) - 2.0 * float(thickness_mm))
    area_mm2 = float(outer_mm) ** 2 - inner_mm**2
    density = float(config.get("steel_density_kg_m3") or 7850.0)
    mass_kg_m = area_mm2 * 1e-6 * density
    prices = config.get("price_cny_per_tonne_by_outer_mm") or {}
    price_per_tonne = prices.get(str(int(round(float(outer_mm)))))
    material_cost_per_m = None
    if price_per_tonne is not None:
        material_cost_per_m = mass_kg_m * float(price_per_tonne) / 1000.0
    price_reference = config.get("price_reference") if isinstance(config.get("price_reference"), dict) else {}
    arm_family = "yixing_arm" if float(outer_mm) > 120.0 else "channel_arm"
    return {
        "estimated_mass_kg_per_m": round(mass_kg_m, 6),
        "estimated_square_material_cost_cny_per_m": (
            round(material_cost_per_m, 6) if material_cost_per_m is not None else None
        ),
        "reference_price_cny_per_tonne": float(price_per_tonne) if price_per_tonne is not None else None,
        "economy_selection_scope": str(config.get("selection_scope") or "square_tube_material_only"),
        "economy_authority": str(config.get("authority") or "advisory_candidate_ordering_only"),
        "economy_price_reference_date": price_reference.get("quotation_date"),
        "economy_price_reference_url": price_reference.get("url"),
        "economy_price_limitations": price_reference.get("limitations"),
        "arm_family": arm_family,
    }


def economy_cost_key(payload: dict[str, Any]) -> tuple[float, float, float, str]:
    cost = payload.get("estimated_square_material_cost_cny_per_m")
    mass = payload.get("estimated_mass_kg_per_m")
    area = payload.get("estimated_area_mm2")
    try:
        cost_value = float(cost)
    except (TypeError, ValueError):
        cost_value = float("inf")
    try:
        mass_value = float(mass)
    except (TypeError, ValueError):
        mass_value = float("inf")
    try:
        area_value = float(area)
    except (TypeError, ValueError):
        area_value = float("inf")
    return cost_value, mass_value, area_value, str(payload.get("section_name") or "")
