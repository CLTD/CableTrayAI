import json

from core.optimizer.square_section_economy import square_section_economy_metrics
from core.optimizer.square_section_selector import SquareSectionCandidate, select_best_square_section


def test_default_economy_basis_is_traceable_quantity_not_public_price() -> None:
    metrics_100x8 = square_section_economy_metrics(outer_mm=100, thickness_mm=8)
    metrics_120x6 = square_section_economy_metrics(outer_mm=120, thickness_mm=6)

    assert metrics_100x8["estimated_mass_kg_per_m"] > metrics_120x6["estimated_mass_kg_per_m"]
    assert metrics_100x8["estimated_square_material_cost_cny_per_m"] is None
    assert metrics_100x8["pricing_status"] == "not_configured"
    assert metrics_100x8["estimated_area_mm2"] == 2944.0
    assert metrics_100x8["estimated_outer_surface_area_m2_per_m"] == 0.4
    assert metrics_100x8["economy_authority"] == "deterministic_quantity_proxy_not_project_cost"
    assert metrics_100x8["economy_selection_scope"] == "main_square_tube_material_quantity_only"


def test_unit_approved_price_book_must_be_explicit_and_section_specific(tmp_path) -> None:
    config_path = tmp_path / "economy.json"
    config_path.write_text(
        json.dumps(
            {
                "steel_density_kg_m3": 7850.0,
                "selection_basis": "unit_approved_material_price",
                "selection_scope": "main_square_tube_material_quantity_only",
                "authority": "unit_approved_price_book",
                "unit_approved_price_book": {
                    "enabled": True,
                    "table_id": "UNIT-COST-001",
                    "revision": "R1",
                    "approval_status": "approved_active",
                    "approval_ref": "approval-record",
                    "prices_cny_per_tonne_by_section": {"140-140-8": 4000.0},
                },
            }
        ),
        encoding="utf-8",
    )

    metrics = square_section_economy_metrics(
        outer_mm=140,
        thickness_mm=8,
        config_path=str(config_path),
    )

    assert metrics["pricing_status"] == "approved_active"
    assert metrics["price_book_table_id"] == "UNIT-COST-001"
    assert metrics["price_book_revision"] == "R1"
    assert metrics["estimated_square_material_cost_cny_per_m"] == 132.6336


def test_low_utilization_is_not_rejected_when_candidate_is_lowest_quantity_pass() -> None:
    candidate = SquareSectionCandidate("100-100-6", 100, 6, "100-100-6.SECT")
    selection = select_best_square_section(
        [
            {
                "section_name": candidate.section_name,
                "status": "pass",
                "controlling_ratio": 0.42,
                "estimated_area_mm2": candidate.estimated_area_mm2,
                "estimated_bending_section_modulus_mm3": candidate.estimated_bending_section_modulus_mm3,
            }
        ]
    )

    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "100-100-6"
    assert selection["selected_economic_status"] == "below_economic_range"
    assert selection["economic_ratio_range_role"] == "utilization_review_only_not_a_hard_gate"
