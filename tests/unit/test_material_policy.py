from __future__ import annotations

from core.evaluators.material_policy import component_material_id, is_steel_platform_job


def test_non_steel_platform_uses_q355_for_square_component() -> None:
    metadata = {"analysis_method": "response_spectrum", "classification": "non_steel_platform"}

    assert is_steel_platform_job(metadata) is False
    assert component_material_id("square_support", metadata) == "q355"


def test_steel_platform_uses_q235_only_for_square_component() -> None:
    metadata = {"analysis_method": "static", "classification": "steel_platform"}

    assert is_steel_platform_job(metadata) is True
    assert component_material_id("square_support", metadata) == "q235"
    assert component_material_id("cantilever_arm", metadata) == "q355"
    assert component_material_id("mixed_beam_type_1", metadata) == "q355"
