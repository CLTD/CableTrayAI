from __future__ import annotations

from core.evaluators.bolt import M8_BOLT_STRESS_AREA_M2, M12_BOLT_GROUP_AREA_M2, evaluate_bolt_forces
from core.evaluators.summary import build_evaluation_summary
from core.schemas.input_models import parse_cable_input


def _bolt_force_row() -> dict:
    return {
        "name": "BOLT_FORCE_RAW",
        "load_case": "FAULTED",
        "values": {
            "fx": {"value": 1200.0},
            "fy": {"value": 800.0},
            "fz": {"value": 2600.0},
            "my": {"value": 120.0},
            "mz": {"value": 20.0},
        },
    }


def _input_for_tray_width(width_m: float):
    payload = {
        "project": {"project_code": "T", "building": "NR", "area": "NR", "elevation": 8.5},
        "spectrum": {"spectrum_file": "spectrum.xlsm", "spectrum_level": "SL-1", "damping_ratio": 0.1},
        "support": {
            "support_type": "S2",
            "square_tube_width_m": 0.1,
            "support_height_m": 1.8,
            "support_spacing_m": 2.0,
            "layers_front": 1,
            "layers_back": 0,
            "support_section_id": "100-100-8",
            "material_id": "Q355",
            "weld_size_mm": 6,
        },
        "tray_layers": [
            {
                "side": "front",
                "layer_index": 1,
                "tray_width_m": width_m,
                "arm_a_length_m": 0.35,
                "arm_b_length_m": 0.2,
                "arm_section_id": "arm",
                "tray_section_id": "tray",
                "tray_density_kg_m3": 7850,
                "material_id": "Q355",
            }
        ],
        "materials": [
            {
                "material_id": "Q355",
                "name": "Q355",
                "elastic_modulus_pa": 2.06e11,
                "poisson_ratio": 0.3,
                "density_kg_m3": 7850,
                "yield_strength_mpa": 355,
                "tensile_strength_mpa": 470,
                "allowable_normal_mpa": 240,
                "allowable_shear_mpa": 100,
                "allowable_tension_mpa": 240,
                "allowable_bending_mpa": 240,
            }
        ],
        "sections": [{"section_id": "100-100-8", "sect_file": "100-100-8.SECT"}],
        "load_cases": [],
        "metadata": {},
    }
    return parse_cable_input(payload)


def _combined_note(items: list[dict]) -> str:
    combined = next(item for item in items if item["check_id"].endswith("_bolt_combined"))
    return str(combined.get("notes") or "")


def test_m8_policy_changes_area_force_share_and_moment_path() -> None:
    m8_items = evaluate_bolt_forces(
        [_bolt_force_row()],
        bolt_size="M8",
        bolt_area_m2=M8_BOLT_STRESS_AREA_M2,
        bolt_moment_lever_arm_m=None,
        bolt_force_share_count=1.0,
    )
    m12_items = evaluate_bolt_forces(
        [_bolt_force_row()],
        bolt_size="M12",
        bolt_area_m2=M12_BOLT_GROUP_AREA_M2,
        bolt_moment_lever_arm_m=0.241,
        bolt_force_share_count=2.0,
    )

    m8_tension = next(item for item in m8_items if item["check_id"].endswith("_bolt_tension"))
    m12_tension = next(item for item in m12_items if item["check_id"].endswith("_bolt_tension"))
    assert m8_tension["calculation_value"] > m12_tension["calculation_value"]
    assert "bolt_size=M8" in _combined_note(m8_items)
    assert "force_share_count=1" in _combined_note(m8_items)
    assert "moment_lever_arm_m=None" in _combined_note(m8_items)
    assert "bolt_size=M12" in _combined_note(m12_items)
    assert "force_share_count=2" in _combined_note(m12_items)
    assert "moment_lever_arm_m=0.241" in _combined_note(m12_items)


def test_build_evaluation_summary_uses_m8_for_tray_width_le_200_and_m12_above_200() -> None:
    result = {"beam_stress_results": [], "bolt_force_results": [_bolt_force_row()], "weld_force_results": []}

    m8_summary = build_evaluation_summary(result, _input_for_tray_width(0.2))
    m12_summary = build_evaluation_summary(result, _input_for_tray_width(0.3))

    assert "bolt_size=M8" in _combined_note(m8_summary)
    assert "force_share_count=1" in _combined_note(m8_summary)
    assert "moment_lever_arm_m=None" in _combined_note(m8_summary)
    assert "bolt_size=M12" in _combined_note(m12_summary)
    assert "force_share_count=2" in _combined_note(m12_summary)
    assert "moment_lever_arm_m=0.241" in _combined_note(m12_summary)


def test_m12_lever_arm_tracks_reviewed_tray_width_pages() -> None:
    result = {"beam_stress_results": [], "bolt_force_results": [_bolt_force_row()], "weld_force_results": []}

    summary_500 = build_evaluation_summary(result, _input_for_tray_width(0.5))
    summary_600 = build_evaluation_summary(result, _input_for_tray_width(0.6))

    assert "moment_lever_arm_m=0.441" in _combined_note(summary_500)
    assert "tray_width_page=500" in _combined_note(summary_500)
    assert "moment_lever_arm_m=0.541" in _combined_note(summary_600)
    assert "tray_width_page=600" in _combined_note(summary_600)
