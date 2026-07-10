from core.optimizer.square_section_economy import square_section_economy_metrics
from core.optimizer.square_section_selector import SquareSectionCandidate, select_best_square_section


def test_published_price_snapshot_keeps_mass_and_cost_traceable() -> None:
    metrics_100x8 = square_section_economy_metrics(outer_mm=100, thickness_mm=8)
    metrics_120x6 = square_section_economy_metrics(outer_mm=120, thickness_mm=6)

    assert metrics_100x8["estimated_mass_kg_per_m"] > metrics_120x6["estimated_mass_kg_per_m"]
    assert (
        metrics_100x8["estimated_square_material_cost_cny_per_m"]
        > metrics_120x6["estimated_square_material_cost_cny_per_m"]
    )
    assert metrics_100x8["economy_authority"] == "advisory_candidate_ordering_only"
    assert metrics_100x8["economy_selection_scope"] == "square_tube_material_only"


def test_low_utilization_is_not_rejected_when_candidate_is_lowest_cost_pass() -> None:
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
