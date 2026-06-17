import math

from core.intake.job_input_builder import build_input_from_intake_payload
from core.intake.tray_load_parser import TRAY_AREA_M2


def _base_payload() -> dict:
    return {
        "project_code": "1818",
        "building": "NR",
        "area": "NR",
        "elevation": 8.5,
        "damping_ratio": 0.1,
        "support_type": "S2",
        "support_spacing_m": 2.0,
        "support_height_m": 1.8,
        "description": "\u5355\u4fa72\u5c42600",
        "analysis_method": "response_spectrum",
    }


def test_tray_line_load_override_updates_only_matching_layer() -> None:
    payload = {
        **_base_payload(),
        "tray_layer_overrides": [
            {
                "side": "front",
                "layer_index": 2,
                "tray_width_mm": 600,
                "load_kg_per_m": 80.0,
            }
        ],
    }

    result = build_input_from_intake_payload(payload)
    layers = result["tray_layers"]
    metadata = result["metadata"]
    mapping_layers = metadata["tray_load_mapping"]["layers"]

    assert len(layers) == 2
    assert layers[0]["tray_density_kg_m3"] != layers[1]["tray_density_kg_m3"]
    assert math.isclose(layers[1]["tray_density_kg_m3"], 80.0 / TRAY_AREA_M2[600])
    assert math.isclose(mapping_layers[1]["load_kg_per_m"], 80.0)
    assert metadata["tray_load_override_status"] == "applied"
    assert metadata["tray_load_override_count"] == 1
    assert metadata["tray_load_original_layers"][1]["load_kg_per_m"] != 80.0
    assert metadata["tray_load_override_layers"][0]["side"] == "front"
    assert metadata["tray_load_override_layers"][0]["layer_index"] == 2

