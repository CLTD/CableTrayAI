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
    outer_surface_area_m2_m = 4.0 * float(outer_mm) / 1000.0
    section_name = f"{int(round(float(outer_mm)))}-{int(round(float(outer_mm)))}-{int(round(float(thickness_mm)))}"
    price_book = config.get("unit_approved_price_book")
    if not isinstance(price_book, dict):
        price_book = {}
    price_book_active = (
        str(config.get("selection_basis") or "theoretical_mass") == "unit_approved_material_price"
        and bool(price_book.get("enabled"))
        and str(price_book.get("approval_status") or "").strip().lower()
        in {"approved", "approved_active"}
    )
    prices = price_book.get("prices_cny_per_tonne_by_section") or {}
    price_per_tonne = prices.get(section_name) if price_book_active else None
    material_cost_per_m = None
    if price_per_tonne is not None:
        material_cost_per_m = mass_kg_m * float(price_per_tonne) / 1000.0
    arm_family = "yixing_arm" if float(outer_mm) > 120.0 else "channel_arm"
    ranking_basis = (
        "unit_approved_square_tube_material_price"
        if material_cost_per_m is not None
        else "theoretical_square_tube_mass"
    )
    return {
        "estimated_area_mm2": round(area_mm2, 6),
        "estimated_mass_kg_per_m": round(mass_kg_m, 6),
        "estimated_outer_surface_area_m2_per_m": round(outer_surface_area_m2_m, 6),
        "estimated_square_material_cost_cny_per_m": (
            round(material_cost_per_m, 6) if material_cost_per_m is not None else None
        ),
        "reference_price_cny_per_tonne": float(price_per_tonne) if price_per_tonne is not None else None,
        "economy_selection_scope": str(
            config.get("selection_scope") or "main_square_tube_material_quantity_only"
        ),
        "economy_authority": str(
            config.get("authority") or "deterministic_quantity_proxy_not_project_cost"
        ),
        "economy_ranking_basis": ranking_basis,
        "pricing_status": "approved_active" if material_cost_per_m is not None else "not_configured",
        "price_book_table_id": price_book.get("table_id") if material_cost_per_m is not None else None,
        "price_book_revision": price_book.get("revision") if material_cost_per_m is not None else None,
        "price_book_approval_ref": price_book.get("approval_ref") if material_cost_per_m is not None else None,
        "comprehensive_cost_status": str(
            (config.get("comprehensive_costing") or {}).get("status") or "not_configured"
        ),
        "economy_price_limitations": (
            "Only the main square-tube theoretical material quantity is available. "
            "This is not a nuclear-project comprehensive cost."
            if material_cost_per_m is None
            else "Unit-approved price covers square-tube material only; other project cost scopes remain separate."
        ),
        "arm_family": arm_family,
    }


def economy_cost_key(payload: dict[str, Any]) -> tuple[float, float, float, str]:
    """Rank by approved price only when present; otherwise use material quantity."""

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
    if str(payload.get("pricing_status") or "") == "approved_active" and cost_value != float("inf"):
        return cost_value, mass_value, area_value, str(payload.get("section_name") or "")
    return float("inf"), mass_value, area_value, str(payload.get("section_name") or "")
