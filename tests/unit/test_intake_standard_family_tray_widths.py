from __future__ import annotations

import re
from pathlib import Path

from core.apdl.intake_standard_family_renderer import (
    _apply_post_keypoint_numbering,
    _current_type_mixed_family_covers_payload,
    _modal_policy_source_bundle,
    _render_model_from_family,
    _render_solve_from_source,
    _standard_family_keypoint_numbering,
    render_intake_standard_family_commands,
    select_standard_model_family,
)
from core.apdl.mixed_tray_model import render_mixed_tray_layer_model, should_use_mixed_tray_layer_renderer
from core.apdl.modal_policy import parse_source_modal_mode_count
from core.apdl.intake_template_context import build_standard_s2_template_context
from core.apdl.source_diff import read_text_with_encoding


def _has_legacy_bolt_latt_pollution(text: str) -> bool:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines):
        if not re.match(
            r"\s*LSEL\s*,\s*S\s*,\s*LOC\s*,\s*X\s*,\s*KX\s*\(\s*(?:516|1516)\s*\)",
            line,
            flags=re.IGNORECASE,
        ):
            continue
        for inner in lines[index + 1 : min(len(lines), index + 25)]:
            if re.match(r"\s*ALLSEL\b", inner, flags=re.IGNORECASE):
                break
            if re.match(r"\s*LATT\s*,\s*1\s*,\s*,\s*4\s*,\s*,\s*,\s*,\s*10\b", inner, flags=re.IGNORECASE):
                return True
    return False


def _double_three_by_three_500_payload() -> dict:
    tray_layers = []
    for side in ("front", "back"):
        for index in range(1, 4):
            tray_layers.append(
                {
                    "side": side,
                    "layer_index": index,
                    "tray_width_m": 0.5,
                    "tray_density_kg_m3": 56704.260652,
                    "tray_section_id": "tray-500",
                    "arm_a_length_m": 0.35,
                    "arm_b_length_m": 0.20,
                }
            )
    return {
        "support": {
            "support_section_id": "square",
            "layers_front": 3,
            "layers_back": 3,
            "support_height_m": 2.1,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.1,
        },
        "sections": [
            {"section_id": "square", "sect_file": "100-100-6.SECT"},
            {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
        ],
        "tray_layers": tray_layers,
    }


def _payload_with_uniform_tray_width(width_mm: int) -> dict:
    payload = _double_three_by_three_500_payload()
    tray_section_id = f"tray-{width_mm}"
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = width_mm / 1000.0
        layer["tray_section_id"] = tray_section_id
    payload["sections"] = [
        {"section_id": "square", "sect_file": "100-100-6.SECT"},
        {"section_id": tray_section_id, "sect_file": f"{width_mm}-75-2mm.SECT"},
    ]
    return payload


def _double_two_by_two_mixed_300_500_payload() -> dict:
    tray_layers = []
    for side, width_mm in (("front", 300), ("back", 500)):
        for index in range(1, 3):
            tray_layers.append(
                {
                    "side": side,
                    "layer_index": index,
                    "tray_width_m": width_mm / 1000.0,
                    "tray_density_kg_m3": 44315.0 if width_mm == 300 else 56704.260652,
                    "tray_section_id": f"tray-{width_mm}",
                    "arm_a_length_m": 0.35,
                    "arm_b_length_m": 0.0,
                }
            )
    return {
        "support": {
            "support_section_id": "square",
            "layers_front": 2,
            "layers_back": 2,
            "support_height_m": 2.0,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.1,
        },
        "sections": [
            {"section_id": "square", "sect_file": "100-100-6.SECT"},
            {"section_id": "tray-300", "sect_file": "300-75-2mm.SECT"},
            {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
        ],
        "tray_layers": tray_layers,
    }


def _single_two_layer_600_payload() -> dict:
    tray_layers = []
    for index in range(1, 3):
        tray_layers.append(
            {
                "side": "front",
                "layer_index": index,
                "tray_width_m": 0.6,
                "tray_density_kg_m3": 61234.5,
                "tray_section_id": "tray-600",
                "arm_a_length_m": 0.40,
                "arm_b_length_m": 0.20,
            }
        )
    return {
        "support": {
            "support_section_id": "square",
            "layers_front": 2,
            "layers_back": 0,
            "support_height_m": 2.1,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.1,
        },
        "sections": [
            {"section_id": "square", "sect_file": "100-100-6.SECT"},
            {"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"},
        ],
        "tray_layers": tray_layers,
    }


def _single_two_layer_mixed_300_600_payload() -> dict:
    return {
        "support": {
            "support_section_id": "square",
            "layers_front": 2,
            "layers_back": 0,
            "support_height_m": 2.2,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.1,
        },
        "sections": [
            {"section_id": "square", "sect_file": "100-100-6.SECT"},
            {"section_id": "tray-300", "sect_file": "300-75-2mm.SECT"},
            {"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"},
        ],
        "tray_layers": [
            {
                "side": "front",
                "layer_index": 1,
                "tray_width_m": 0.3,
                "tray_density_kg_m3": 44315.0,
                "tray_section_id": "tray-300",
                "arm_a_length_m": 0.20,
                "arm_b_length_m": 0.15,
            },
            {
                "side": "front",
                "layer_index": 2,
                "tray_width_m": 0.6,
                "tray_density_kg_m3": 65423.0,
                "tray_section_id": "tray-600",
                "arm_a_length_m": 0.47,
                "arm_b_length_m": 0.20,
            },
        ],
    }


def _single_two_layer_mixed_500_600_payload() -> dict:
    payload = _single_two_layer_mixed_300_600_payload()
    payload["sections"] = [
        {"section_id": "square", "sect_file": "100-100-6.SECT"},
        {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
        {"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"},
    ]
    payload["tray_layers"] = [
        {
            "side": "front",
            "layer_index": 1,
            "tray_width_m": 0.5,
            "tray_density_kg_m3": 56704.260652,
            "tray_section_id": "tray-500",
            "arm_a_length_m": 0.35,
            "arm_b_length_m": 0.20,
        },
        {
            "side": "front",
            "layer_index": 2,
            "tray_width_m": 0.6,
            "tray_density_kg_m3": 65423.0,
            "tray_section_id": "tray-600",
            "arm_a_length_m": 0.47,
            "arm_b_length_m": 0.20,
        },
    ]
    return payload


def _single_five_layer_mixed_600_500_300_200_100_payload() -> dict:
    specs = [
        (1, 600, 65423.0, 0.47, 0.20),
        (2, 500, 56704.260652, 0.35, 0.20),
        (3, 300, 44315.0, 0.20, 0.15),
        (4, 200, 51095.0, 0.20, 0.15),
        (5, 100, 38961.0, 0.20, 0.15),
    ]
    return {
        "metadata": {"analysis_method": "response_spectrum"},
        "support": {
            "support_section_id": "square",
            "layers_front": 5,
            "layers_back": 0,
            "support_height_m": 2.1,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.1,
        },
        "sections": [
            {"section_id": "square", "sect_file": "100-100-6.SECT"},
            *[
                {"section_id": f"tray-{width}", "sect_file": f"{width}-75-2mm.SECT"}
                for _, width, *_ in specs
            ],
        ],
        "tray_layers": [
            {
                "side": "front",
                "layer_index": index,
                "tray_width_m": width / 1000.0,
                "tray_density_kg_m3": density,
                "tray_section_id": f"tray-{width}",
                "arm_a_length_m": arm_a,
                "arm_b_length_m": arm_b,
            }
            for index, width, density, arm_a, arm_b in specs
        ],
    }


def _double_three_by_three_mirrored_mixed_100_300_500_payload() -> dict:
    tray_layers = []
    specs = [
        (1, 100, 44315.0, 0.20, 0.15),
        (2, 300, 44315.0, 0.20, 0.15),
        (3, 500, 56704.260652, 0.35, 0.20),
    ]
    for side in ("front", "back"):
        for index, width, density, arm_a, arm_b in specs:
            tray_layers.append(
                {
                    "side": side,
                    "layer_index": index,
                    "tray_width_m": width / 1000.0,
                    "tray_density_kg_m3": density,
                    "tray_section_id": f"tray-{width}",
                    "arm_a_length_m": arm_a,
                    "arm_b_length_m": arm_b,
                }
            )
    return {
        "support": {
            "support_section_id": "square",
            "layers_front": 3,
            "layers_back": 3,
            "support_height_m": 2.0,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.1,
        },
        "sections": [
            {"section_id": "square", "sect_file": "100-100-6.SECT"},
            {"section_id": "tray-100", "sect_file": "100-75-2mm.SECT"},
            {"section_id": "tray-300", "sect_file": "300-75-2mm.SECT"},
            {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
        ],
        "tray_layers": tray_layers,
        "metadata": {"analysis_method": "response_spectrum"},
    }


def _double_two_by_two_mirrored_mixed_500_600_payload() -> dict:
    tray_layers = []
    specs = [
        (1, 500, 56704.260652, 0.35, 0.20),
        (2, 600, 65423.0, 0.47, 0.20),
    ]
    for side in ("front", "back"):
        for index, width, density, arm_a, arm_b in specs:
            tray_layers.append(
                {
                    "side": side,
                    "layer_index": index,
                    "tray_width_m": width / 1000.0,
                    "tray_density_kg_m3": density,
                    "tray_section_id": f"tray-{width}",
                    "arm_a_length_m": arm_a,
                    "arm_b_length_m": arm_b,
                }
            )
    return {
        "support": {
            "support_section_id": "square",
            "layers_front": 2,
            "layers_back": 2,
            "support_height_m": 2.0,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.1,
        },
        "sections": [
            {"section_id": "square", "sect_file": "100-100-6.SECT"},
            {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
            {"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"},
        ],
        "tray_layers": tray_layers,
        "metadata": {"analysis_method": "response_spectrum"},
    }


def _double_five_by_five_mirrored_mixed_100_200_300_500_600_payload() -> dict:
    tray_layers = []
    specs = [
        (1, 100, 3896.1, 0.20, 0.15),
        (2, 200, 51095.0, 0.20, 0.15),
        (3, 300, 44315.0, 0.20, 0.15),
        (4, 500, 56704.260652, 0.35, 0.20),
        (5, 600, 65423.162584, 0.47, 0.20),
    ]
    for side in ("front", "back"):
        for index, width, density, arm_a, arm_b in specs:
            tray_layers.append(
                {
                    "side": side,
                    "layer_index": index,
                    "tray_width_m": width / 1000.0,
                    "tray_density_kg_m3": density,
                    "tray_section_id": f"tray-{width}",
                    "arm_a_length_m": arm_a,
                    "arm_b_length_m": arm_b,
                }
            )
    return {
        "support": {
            "support_section_id": "square",
            "layers_front": 5,
            "layers_back": 5,
            "support_height_m": 1.7,
            "support_spacing_m": 2.0,
            "square_tube_width_m": 0.14,
        },
        "sections": [
            {"section_id": "square", "sect_file": "140-140-8.SECT"},
            {"section_id": "tray-100", "sect_file": "100-75-2mm.SECT"},
            {"section_id": "tray-200", "sect_file": "200-75-2mm.SECT"},
            {"section_id": "tray-300", "sect_file": "300-75-2mm.SECT"},
            {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
            {"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"},
        ],
        "tray_layers": tray_layers,
        "metadata": {"analysis_method": "response_spectrum"},
    }


def _double_layer_payload(layer_count: int) -> dict:
    payload = _double_three_by_three_500_payload()
    tray_layers = []
    for side in ("front", "back"):
        for index in range(1, layer_count + 1):
            tray_layers.append(
                {
                    "side": side,
                    "layer_index": index,
                    "tray_width_m": 0.5,
                    "tray_density_kg_m3": 56704.260652,
                    "tray_section_id": "tray-500",
                    "arm_a_length_m": 0.35,
                    "arm_b_length_m": 0.20,
                }
            )
    payload["tray_layers"] = tray_layers
    payload["support"]["layers_front"] = layer_count
    payload["support"]["layers_back"] = layer_count
    payload["support"]["support_height_m"] = 2.8
    return payload


def _high_layer_source_text() -> str:
    return "\n".join(
        [
            "H1=0.16",
            "H2=2.8",
            "L1=0.55",
            "L2=0.5",
            "L3=0.15",
            "L4=2.0",
            "senum=5",
            "senum1=2",
            "*DO,J,1,3",
            "K,500+100*(J-1),0,0+L4*(J-1),0",
            "*DO,I,1,senum",
            "K,500+I+100*(J-1),0,0+L4*(J-1),0.1+0.2*(I-1)",
            "*ENDDO",
            "K,500+senum+1+100*(J-1),0,0+L4*(J-1),H2",
            "*DO,I,1,senum+1",
            "L,500+(I-1)+100*(J-1),500+I+100*(J-1)",
            "*ENDDO",
            "*DO,I,1,senum",
            "K,501+10*I+100*(J-1),H1/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
            "L,501+10*I+100*(J-1),509+10*I+100*(J-1)",
            "*ENDDO",
            "*DO,I,1,senum1",
            "K,1501+10*I+100*(J-1),-(H1/2),0+L4*(J-1),0.1+0.2*(I-1)",
            "K,1509+10*I+100*(J-1),-(H1/2+L1-L2/2),0+L4*(J-1),0.15+0.2*(I-1)",
            "L,1501+10*I+100*(J-1),1509+10*I+100*(J-1)",
            "*ENDDO",
            "*ENDDO",
            "LSEL,S,LOC,X,KX(516)",
            "LSEL,A,LOC,X,KX(1516)",
            "LSEL,U,LOC,Y,KY(519)",
            "LSEL,U,LOC,Y,KY(619)",
            "LSEL,U,LOC,Y,KY(719)",
            "LSEL,U,LOC,Y,KY(1519)",
            "LSEL,U,LOC,Y,KY(1619)",
            "LSEL,U,LOC,Y,KY(1719)",
            "KSEL,S,KP,,500+senum+1,700+senum+1,100",
            "NKMS01=NODE(KX(501+senum),KY(501+senum),KZ(501+senum))",
            "NKMS02=NODE(KX(601+senum),KY(601+senum),KZ(601+senum))",
            "NKMS03=NODE(KX(701+senum),KY(701+senum),KZ(701+senum))",
            "SECREAD,'100-100-8'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'CAOGANG42DAN'",
        ]
    )


def test_standard_family_rewrites_source_tray_widths_from_current_intake() -> None:
    source_text = "\n".join(
        [
            "H1=0.14",
            "H2=2.0",
            "L1=0.75",
            "L2=0.65",
            "L3=0.6",
            "L4=0.3",
            "L5=0.2",
            "L6=2.0",
            "senum=4",
            "senum1=2",
            "SECREAD,'140-140-8'",
            "SECREAD,'YIXINGGANG150'",
            "SECREAD,'YIXINGGANG150DAN'",
            "SECREAD,'600-75-2mm'",
            "SECREAD,'300-75-2mm'",
            "MP,DENS,2,7850",
            "MP,DENS,3,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert "SECREAD,'600-75-2mm'" not in rendered
    assert "SECREAD,'300-75-2mm'" not in rendered
    assert rendered.count("SECREAD,'500-75-2mm'") == 2
    assert "L3=0.5" in rendered
    assert "L4=0.5" in rendered
    assert "senum=3" in rendered
    assert "senum1=3" in rendered
    assert "MP,DENS,2,56704" in rendered
    assert "MP,DENS,3,56704" in rendered
    assert audit["source_geometry_widths_mm"] == [600, 300]
    assert audit["model_geometry_widths_mm"] == [500]
    assert audit["material_slot_widths_mm"] == [500, 500]
    assert audit["assigned"]["senum"] == 3
    assert audit["assigned"]["senum1"] == 3
    assert audit["section_role_map"]["primary_cantilever_arm"]["section"] == "50-42"
    assert audit["section_role_map"]["tray_equivalent_sections"] == [
        {
            "width_mm": 500,
            "section": "500-75-2mm",
            "meaning": "电缆托盘等效截面；必须按当前提资托盘宽度改写。",
        }
    ]


def test_standard_family_uses_600_tray_section_when_current_intake_width_is_600() -> None:
    source_text = "\n".join(
        [
            "H1=0.14",
            "H2=2.0",
            "L1=0.75",
            "L2=0.65",
            "L3=0.6",
            "L4=0.3",
            "L5=0.2",
            "L6=2.0",
            "senum=4",
            "senum1=2",
            "SECREAD,'100-100-6'",
            "SECREAD,'50-42'",
            "SECREAD,'CAOGANG42DAN'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'500-75-2mm'",
            "MP,DENS,2,7850",
            "MP,DENS,3,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _payload_with_uniform_tray_width(600))

    assert rendered.count("SECREAD,'600-75-2mm'") == 2
    assert "SECREAD,'500-75-2mm'" not in rendered
    assert "SECREAD,'50-42'" in rendered
    assert audit["model_geometry_widths_mm"] == [600]
    assert audit["section_role_map"]["primary_cantilever_arm"]["section"] == "50-42"
    assert audit["section_role_map"]["tray_equivalent_sections"] == [
        {
            "width_mm": 600,
            "section": "600-75-2mm",
            "meaning": "电缆托盘等效截面；必须按当前提资托盘宽度改写。",
        }
    ]


def test_standard_family_keeps_500_tray_slots_when_source_places_trays_before_arm() -> None:
    source_text = "\n".join(
        [
            "H1=0.1",
            "H2=2.1",
            "L1=0.55",
            "L2=0.5",
            "L3=0.2",
            "L4=2.0",
            "senum=3",
            "senum1=3",
            "SECREAD,'100-100-8'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'CAOGANG42DAN'",
            "MP,DENS,2,7850",
            "MP,DENS,3,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert rendered.count("SECREAD,'500-75-2mm'") == 2
    assert "SECREAD,'50-42'" not in rendered
    assert "SECREAD,'CAOGANG42DAN'" in rendered
    assert audit["tray_secread_replacements"] == 2
    assert audit["secondary_arm_secread_replacements"] == 1
    assert audit["section_role_map"]["primary_cantilever_arm"]["section"] == "50-42"
    assert audit["section_role_map"]["tray_equivalent_sections"][0]["section"] == "500-75-2mm"


def test_mixed_width_single_source_uses_governing_max_width_geometry_not_first_width() -> None:
    source_text = "\n".join(
        [
            "H1=0.1",
            "H2=2.0",
            "L1=0.35",
            "L2=0.5",
            "L3=0.2",
            "L4=2.0",
            "senum=2",
            "senum1=2",
            "SECREAD,'100-100-6'",
            "SECREAD,'500-75-2mm'",
            "MP,DENS,2,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_two_by_two_mixed_300_500_payload())

    assert "L2=0.5" in rendered
    assert "SECREAD,'500-75-2mm'" in rendered
    assert "SECREAD,'300-75-2mm'" not in rendered
    assert "MP,DENS,2,56704" in rendered
    assert audit["tray_widths_mm"] == [300, 500]
    assert audit["model_geometry_widths_mm"] == [500]
    assert audit["material_slot_widths_mm"] == [500]
    assert audit["shared_max_width_geometry"]["status"] == "applied"


def test_single_mixed_500_600_uses_current_type_standard_family_variables() -> None:
    source_text, _ = read_text_with_encoding(Path("resources/current_type_command_flows/single_mixed_600_500_300_universal.PIP"))

    rendered, audit = _render_model_from_family(source_text, _single_two_layer_mixed_500_600_payload())

    assert "QTOFF" not in rendered
    assert "QCODE" not in rendered
    assert "senum1=2" in rendered
    assert "senum=2" in rendered
    assert "senum2=2" in rendered
    assert "senum3=1" in rendered
    assert "L1=0.67" in rendered
    assert "L2=0.6" in rendered
    assert "L11=0.55" in rendered
    assert "L12=0.5" in rendered
    assert "L5=0.2" in rendered
    assert "CPCYC,UX,,,,,M1-0.05" in rendered
    assert "*IF,senum3,GT,0,THEN" in rendered
    assert "*IF,senum2,GT,senum3,THEN" in rendered
    assert "*IF,senum1,GT,senum2,THEN" in rendered
    assert rendered.index("SECREAD,'600-75-2mm'") < rendered.index("SECREAD,'500-75-2mm'")
    assert audit["source_mixed_family_shape"] == "single_mixed_600_500_300_universal"
    assert audit["model_geometry_widths_mm"] == [600, 500]
    assert audit["material_slot_widths_mm"] == [600, 500, 300]
    assert audit["standard_mixed_layer_counts"]["senum3"] == 1
    assert audit["standard_mixed_layer_counts"]["senum2"] == 2
    assert audit["optional_mixed_mesh_guards"]["status"] == "guarded"


def test_single_mixed_five_width_uses_department_five_width_standard_family(tmp_path: Path) -> None:
    payload = _single_five_layer_mixed_600_500_300_200_100_payload()
    source = Path(
        "resources/current_type_command_flows/single_mixed_600_500_300_200_100/"
        "single_mixed_600_500_300_200_100_universal.PIP"
    )
    source_text, _ = read_text_with_encoding(source)

    rendered, audit = _render_model_from_family(source_text, payload)

    assert audit["source_mixed_family_shape"] == "single_mixed_600_500_300_200_100_universal"
    assert audit["model_geometry_widths_mm"] == [600, 500, 300, 200, 100]
    assert audit["material_slot_widths_mm"] == [600, 500, 300, 200, 100]
    assert audit["assigned"]["senum5"] == 1
    assert audit["assigned"]["senum4"] == 2
    assert audit["assigned"]["senum3"] == 3
    assert audit["assigned"]["senum2"] == 4
    assert audit["assigned"]["senum1"] == 5
    assert "senum5=1" in rendered
    assert "senum4=2" in rendered
    assert "senum3=3" in rendered
    assert "senum2=4" in rendered
    assert "senum1=5" in rendered
    assert "L7=0.2" in rendered
    assert "L8=0.1" in rendered
    assert "L5=0.2" in rendered
    assert "CPCYC,UX,,,,,M1-0.05" in rendered
    for width in (600, 500, 300, 200, 100):
        assert f"SECREAD,'{width}-75-2mm'" in rendered
    assert "*IF,senum5,GT,0,THEN" in rendered
    assert "*IF,senum4,GT,senum5,THEN" in rendered
    assert "*IF,senum3,GT,senum4,THEN" in rendered
    assert "*IF,senum2,GT,senum3,THEN" in rendered
    assert "*IF,senum1,GT,senum2,THEN" in rendered

    result = render_intake_standard_family_commands("single_five_width_render", payload, jobs_dir=tmp_path)
    post = (tmp_path / "single_five_width_render" / "generated_post.mac").read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["family"]["source"].replace("\\", "/").endswith(
        "single_mixed_600_500_300_200_100/single_mixed_600_500_300_200_100_universal.PIP"
    )
    assert result["parameterization"]["source_family_model_status"] == "bypassed_for_mixed_tray_layer_renderer"
    assert result["parameterization"]["model_source"] == "ctai_layered_mixed_tray_standard"
    assert result["parameterization"]["current_type_mixed_family_cover"]["status"] == "pass"
    assert (tmp_path / "single_five_width_render" / "apdl_topology_manifest.json").exists()
    assert "CM,CTAI_SUPPORT_ELEMS,ELEM" in (tmp_path / "single_five_width_render" / "generated_model.mac").read_text(encoding="utf-8")
    assert "CMSEL,S,CTAI_ARM_ELEMS,ELEM" in post


def test_single_mixed_500_600_yixing_keeps_yixing_standard_offsets() -> None:
    source_text, _ = read_text_with_encoding(Path("resources/current_type_command_flows/single_mixed_500_600_yixing.PIP"))
    payload = _single_two_layer_mixed_500_600_payload()
    payload["support"]["square_tube_width_m"] = 0.14
    payload["sections"][0]["sect_file"] = "140-140-8.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "SECREAD,'YIXINGGANG150DAN'" in rendered
    assert "SECOFFSET,user,,-0.03249\nSECREAD,'YIXINGGANG150DAN'" not in rendered
    assert "SECOFFSET,user\nSECREAD,'YIXINGGANG150DAN'" in rendered
    assert "senum1=2" in rendered
    assert "senum=2" in rendered
    assert "senum3=1" in rendered
    assert "L1=0.67" in rendered
    assert "L2=0.55" in rendered
    assert "L3=0.6" in rendered
    assert "L4=0.5" in rendered
    assert "L5=0.15" in rendered
    assert "CPCYC,UX,,,,,0.068-0.05" in rendered
    assert "*IF,senum3,GT,0,THEN" in rendered
    assert "*IF,senum1,GT,senum3,THEN" in rendered
    assert audit["source_mixed_family_shape"] == "single_mixed_600_500_yixing"


def test_current_type_mixed_cover_accepts_4514_style_single_500_600() -> None:
    source = Path("resources/current_type_command_flows/single_mixed_600_500_300_universal.PIP")
    source_text, _ = read_text_with_encoding(source)

    cover = _current_type_mixed_family_covers_payload(
        _single_two_layer_mixed_500_600_payload(),
        source_text=source_text,
        source_path=source,
    )

    assert cover["status"] == "pass"
    assert cover["reason"] == "single_side_current_type_mixed_family_exact_cover"


def test_current_type_mixed_cover_accepts_single_five_width_source_with_small_trays() -> None:
    source = Path(
        "resources/current_type_command_flows/single_mixed_600_500_300_200_100/"
        "single_mixed_600_500_300_200_100_universal.PIP"
    )
    source_text, _ = read_text_with_encoding(source)

    cover = _current_type_mixed_family_covers_payload(
        _single_five_layer_mixed_600_500_300_200_100_payload(),
        source_text=source_text,
        source_path=source,
    )

    assert cover["status"] == "pass"
    assert cover["source_shape"] == "single_mixed_600_500_300_200_100_universal"


def test_compact_single_500_600_stays_on_three_width_source_family() -> None:
    payload = _single_two_layer_mixed_500_600_payload()

    family = select_standard_model_family(payload)

    assert family["source"].replace("\\", "/").endswith("single_mixed_600_500_300_universal.PIP")
    compact = [check for check in family["checks"] if check["check_id"] == "mixed_width_compact_cover"]
    assert compact
    assert compact[0]["extra_width_count"] == 1


def test_current_type_mixed_cover_rejects_per_side_mixed_4210_style_payload() -> None:
    payload = _double_two_by_two_mixed_300_500_payload()
    payload["sections"].extend(
        [
            {"section_id": "tray-100", "sect_file": "100-75-2mm.SECT"},
            {"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"},
        ]
    )
    payload["tray_layers"] = []
    for side in ("front", "back"):
        for index, width in enumerate((100, 300, 500), start=1):
            payload["tray_layers"].append(
                {
                    "side": side,
                    "layer_index": index,
                    "tray_width_m": width / 1000.0,
                    "tray_density_kg_m3": 44315.0,
                    "tray_section_id": f"tray-{width}",
                    "arm_a_length_m": 0.35 if width >= 500 else 0.20,
                    "arm_b_length_m": 0.20 if width >= 500 else 0.15,
                }
            )
    payload["support"]["layers_front"] = 3
    payload["support"]["layers_back"] = 3
    source = Path("resources/current_type_command_flows/double_mixed_yixing.PIP")
    source_text, _ = read_text_with_encoding(source)

    cover = _current_type_mixed_family_covers_payload(payload, source_text=source_text, source_path=source)

    assert cover["status"] == "fail"
    assert cover["reason"] == "double_side_payload_has_per_side_mixed_widths_or_uncovered_widths"


def test_4210_style_mirrored_mixed_renderer_uses_grouped_current_type_loops() -> None:
    payload = _double_three_by_three_mirrored_mixed_100_300_500_payload()

    rendered, audit = render_mixed_tray_layer_model(payload)

    assert audit["model_source"] == "ctai_grouped_mirrored_mixed_standard"
    assert audit["assigned"]["senum1"] == 3
    assert audit["assigned"]["senum2"] == 2
    assert audit["assigned"]["senum3"] == 1
    assert "senum1=3" in rendered
    assert "senum2=2" in rendered
    assert "senum3=1" in rendered
    assert "SECREAD,'100-75-2mm'" in rendered
    assert "SECREAD,'300-75-2mm'" in rendered
    assert "SECREAD,'500-75-2mm'" in rendered
    assert "SECTYPE,10,BEAM,CSOLID" in rendered
    assert "SECTYPE,11,BEAM,CSOLID" in rendered
    assert "*DIM,ARM_ET,ARRAY" in rendered
    assert "*DIM,TRAY_ET,ARRAY" in rendered
    assert "ARM_ET(NARM)=2" in rendered
    assert "TRAY_ET(NTRAY)=4" in rendered
    assert "BOLT_SEC(NBOLT)=11" in rendered
    assert "BOLT_SEC(NBOLT)=10" in rendered
    assert "LSEL,S,LINE,,LS_BOLT(I)" in rendered
    assert "LATT,1,,4,,,,_BSEC" in rendered
    assert "CM,CTAI_SUPPORT_ELEMS,ELEM" in rendered
    assert "CM,CTAI_ARM_ELEMS,ELEM" in rendered
    assert "CM,CTAI_TRAY_ELEMS,ELEM" in rendered
    assert "CM,CTAI_BOLT_ELEMS,ELEM" in rendered
    assert "SECTYPE,11,BEAM,CSOLID" in rendered
    assert "SECDATA,0.006" in rendered
    assert "SECDATA,0.004" not in rendered
    assert not _has_legacy_bolt_latt_pollution(rendered)
    assert "QCODE" not in rendered
    assert "QW(" not in rendered


def test_4219_style_mirrored_500_600_uses_source_style_variables_and_selected_h1() -> None:
    payload = _double_two_by_two_mirrored_mixed_500_600_payload()
    payload["metadata"]["square_section_selected"] = "120-120-10"
    payload["metadata"]["square_section_outer_mm"] = 120
    payload["metadata"]["square_section_thickness_mm"] = 10
    payload["sections"][0]["sect_file"] = "120-120-10.SECT"

    rendered, audit = render_mixed_tray_layer_model(payload)

    assert audit["model_source"] == "ctai_grouped_mirrored_mixed_standard"
    assert audit["assigned"]["H1"] == 0.12
    assert "H1=0.12" in rendered
    assert "L1=0.67" in rendered
    assert "L2=0.55" in rendered
    assert "L3=0.6" in rendered
    assert "L4=0.5" in rendered
    assert "L5=0.2" in rendered
    assert "H1/2+L1-L3/2" in rendered
    assert "H1/2+L2-L4/2" in rendered
    assert "H1/2+0.67-0.3" not in rendered
    assert audit["command_style"]["source_style_parameter_policy"] == "source_style_two_width_500_600"
    assert "ARM_SEC(NARM)=2" in rendered
    assert "ARM_SEC(NARM)=3" in rendered


def test_4219_full_render_uses_section_based_tmax_for_grouped_500_600(tmp_path: Path) -> None:
    payload = _double_two_by_two_mirrored_mixed_500_600_payload()
    payload["metadata"]["square_section_selected"] = "120-120-10"
    payload["metadata"]["square_section_outer_mm"] = 120
    payload["metadata"]["square_section_thickness_mm"] = 10
    payload["sections"][0]["sect_file"] = "120-120-10.SECT"

    result = render_intake_standard_family_commands("4219_grouped_render", payload, jobs_dir=tmp_path)
    rendered = (tmp_path / "4219_grouped_render" / "generated_model.mac").read_text(encoding="utf-8")
    post = (tmp_path / "4219_grouped_render" / "generated_post.mac").read_text(encoding="utf-8")

    assert result["status"] == "pass"
    assert result["parameterization"]["model_source"] == "ctai_grouped_mirrored_mixed_standard"
    assert "H1=0.12" in rendered
    assert "H1/2+L1-L3/2" in rendered
    assert "H1/2+L2-L4/2" in rendered
    assert "CMSEL,S,CTAI_ARM_ELEMS,ELEM" in post
    assert "CMSEL,A,CTAI_TRAY_ELEMS,ELEM" in post
    assert "10*I+2" not in post.split("*CREATE,TMAXBEAMSTRESS-WRITE,MAC", 1)[0]


def test_4210_style_five_width_mirrored_mixed_renderer_stays_grouped() -> None:
    payload = _double_five_by_five_mirrored_mixed_100_200_300_500_600_payload()

    rendered, audit = render_mixed_tray_layer_model(payload)

    assert audit["model_source"] == "ctai_grouped_mirrored_mixed_standard"
    assert audit["assigned"]["senum1"] == 5
    assert audit["assigned"]["senum2"] == 4
    assert audit["assigned"]["senum3"] == 3
    assert audit["assigned"]["senum4"] == 2
    assert audit["assigned"]["senum5"] == 1
    for width in (100, 200, 300, 500, 600):
        assert f"SECREAD,'{width}-75-2mm'" in rendered
    assert "BOLT_SEC(NBOLT)=11" in rendered
    assert "BOLT_SEC(NBOLT)=10" in rendered
    assert "QCODE" not in rendered
    assert "QW(" not in rendered


def test_4210_full_command_render_uses_grouped_renderer_not_legacy_arrays(tmp_path: Path) -> None:
    payload = _double_three_by_three_mirrored_mixed_100_300_500_payload()

    result = render_intake_standard_family_commands("4210_grouped_render", payload, jobs_dir=tmp_path)
    rendered = (tmp_path / "4210_grouped_render" / "generated_model.mac").read_text(encoding="utf-8")

    assert result["status"] == "pass"
    audit = result["parameterization"]
    assert audit["model_source"] == "ctai_grouped_mirrored_mixed_standard"
    assert "senum1=3" in rendered
    assert "senum2=2" in rendered
    assert "senum3=1" in rendered
    assert "QCODE" not in rendered
    assert "QW(" not in rendered


def test_mixed_tray_layer_renderer_preserves_each_layer_width_and_bolt_topology() -> None:
    payload = _single_two_layer_mixed_300_600_payload()

    rendered, audit = render_mixed_tray_layer_model(payload)

    assert should_use_mixed_tray_layer_renderer(payload)
    assert "SECREAD,'300-75-2mm'" in rendered
    assert "SECREAD,'600-75-2mm'" in rendered
    assert "SECTYPE,10,BEAM,CSOLID" in rendered
    assert "SECDATA,0.006" in rendered
    assert "QW(1)=0.6" in rendered
    assert "QW(2)=0.3" in rendered
    assert "QA(1)=0.47" in rendered
    assert "QB(1)=0.2" in rendered
    assert "QTOFF(1)=0.074" in rendered
    assert "QTCODE=QCODE(I)" in rendered
    assert "QCODE=QCODE(I)" not in rendered
    assert "*ELSEIF,QTCODE,EQ,300,THEN" in rendered
    assert "L,502+KPOFF+10*I+KPFSTEP*(J-1),504+KPOFF+10*I+KPFSTEP*(J-1)" in rendered
    assert "SECOFFSET,user,,-0.03249\nSECREAD,'CAOGANG42DAN'" in rendered
    assert "*DO,I,1,2" in rendered
    assert "K,501+KPOFF+10*I+KPFSTEP*(J-1)" in rendered
    assert "K,506+KPOFF+10*I+KPFSTEP*(J-1)" in rendered
    assert "K,516" not in rendered
    assert audit["shared_max_width_geometry"]["status"] == "not_used"
    assert audit["command_style"]["status"] == "loop_parameterized_component_topology"
    assert "*DIM,LS_ARM,ARRAY" in rendered
    assert "*GET,_LNEW,LINE,0,NUM,MAX" in rendered
    assert "LS_TRAY(NTRAY)=_LNEW" in rendered
    assert "LS_BOLT(NBOLT)=_LNEW" in rendered
    assert "LSEL,S,LINE,,LS_ARM(I)" in rendered
    assert "CM,CTAI_SUPPORT_ELEMS,ELEM" in rendered
    assert "CM,CTAI_ARM_ELEMS,ELEM" in rendered
    assert "CM,CTAI_TRAY_ELEMS,ELEM" in rendered
    assert "CM,CTAI_BOLT_ELEMS,ELEM" in rendered
    assert audit["secondary_arm_offset_policy"] == "channel_secondary_arm_offset_minus_0p03249"
    assert audit["model_geometry_widths_mm"] == [300, 600]
    bottom_layer = [item for item in audit["layer_geometry"] if item["model_layer_index"] == 1][0]
    top_layer = [item for item in audit["layer_geometry"] if item["model_layer_index"] == 2][0]
    assert bottom_layer["width_mm"] == 600
    assert bottom_layer["l3_tail_m"] == 0.2
    assert bottom_layer["original_layer_index"] == 2
    assert top_layer["width_mm"] == 300
    assert top_layer["original_layer_index"] == 1


def test_mixed_tray_layer_renderer_standard_loop_handles_single_side_seven_mixed_layers() -> None:
    payload = _single_two_layer_mixed_300_600_payload()
    widths = [300, 500, 500, 500, 600, 600, 600]
    density_by_width = {300: 44315.0, 500: 56704.260652, 600: 65423.0}
    split_by_width = {300: (0.20, 0.15), 500: (0.35, 0.20), 600: (0.47, 0.20)}
    payload["support"]["layers_front"] = 7
    payload["support"]["support_height_m"] = 2.2
    payload["sections"] = [
        {"section_id": "square", "sect_file": "100-100-6.SECT"},
        {"section_id": "tray-300", "sect_file": "300-75-2mm.SECT"},
        {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
        {"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"},
    ]
    payload["tray_layers"] = []
    for index, width in enumerate(widths, start=1):
        arm_a, arm_b = split_by_width[width]
        payload["tray_layers"].append(
            {
                "side": "front",
                "layer_index": index,
                "tray_width_m": width / 1000.0,
                "tray_density_kg_m3": density_by_width[width],
                "tray_section_id": f"tray-{width}",
                "arm_a_length_m": arm_a,
                "arm_b_length_m": arm_b,
            }
        )

    rendered, audit = render_mixed_tray_layer_model(payload)

    assert "senum=7" in rendered
    assert "*DO,I,1,7" in rendered
    assert "QW(1)=0.6" in rendered
    assert "QW(4)=0.5" in rendered
    assert "QW(7)=0.3" in rendered
    assert "K,571" not in rendered
    assert "K,501+KPOFF+10*I+KPFSTEP*(J-1)" in rendered
    assert [item["width_mm"] for item in audit["layer_geometry"]] == [600, 600, 600, 500, 500, 500, 300]
    assert audit["layer_geometry"][-1]["original_layer_index"] == 1
    assert audit["layer_order_policy"]["status"] == "width_descending_small_trays_above"


def test_mixed_tray_layer_renderer_handles_double_side_mixed_layers_with_same_loop_policy() -> None:
    payload = _double_two_by_two_mixed_300_500_payload()
    payload["tray_layers"].append(
        {
            "side": "front",
            "layer_index": 3,
            "tray_width_m": 0.6,
            "tray_density_kg_m3": 65423.0,
            "tray_section_id": "tray-600",
            "arm_a_length_m": 0.47,
            "arm_b_length_m": 0.20,
        }
    )
    payload["sections"].append({"section_id": "tray-600", "sect_file": "600-75-2mm.SECT"})
    payload["support"]["layers_front"] = 3

    rendered, audit = render_mixed_tray_layer_model(payload)

    assert "qiancengshu=3" in rendered
    assert "houcengshu=2" in rendered
    assert "QW(1)=0.6" in rendered
    assert "HW(1)=0.5" in rendered
    assert "K,KPBKBASE+1+KPOFF+10*I+KPFSTEP*(J-1)" in rendered
    assert "CP,NEXT,ALL,NROOT,NFROOT,NBROOT" in rendered
    assert "K,1501" not in rendered
    front_widths = [item["width_mm"] for item in audit["layer_geometry"] if item["side"] == "front"]
    back_widths = [item["width_mm"] for item in audit["layer_geometry"] if item["side"] == "back"]
    assert front_widths == [600, 300, 300]
    assert back_widths == [500, 500]


def test_mixed_tray_layer_renderer_keeps_yixing_secondary_arm_without_channel_offset() -> None:
    payload = _single_two_layer_mixed_300_600_payload()
    payload["support"]["square_tube_width_m"] = 0.14
    payload["sections"][0]["sect_file"] = "140-140-8.SECT"

    rendered, audit = render_mixed_tray_layer_model(payload)

    assert "SECREAD,'YIXINGGANG150DAN'" in rendered
    assert "SECOFFSET,user,,-0.03249\nSECREAD,'YIXINGGANG150DAN'" not in rendered
    assert "SECOFFSET,user\nSECREAD,'YIXINGGANG150DAN'" in rendered
    assert "QTOFF(1)=0.068" in rendered
    assert audit["secondary_arm_offset_policy"] == "non_channel_secondary_arm_no_offset"


def test_single_width_family_l3_tracks_square_width_le_120() -> None:
    source_text = "\n".join(
        [
            "H1=0.12",
            "H2=2.1",
            "L1=0.55",
            "L2=0.5",
            "L3=0.15",
            "L4=2.0",
            "senum=3",
            "senum1=3",
            "SECREAD,'120-120-8'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'CAOGANG42DAN'",
        ]
    )
    payload = _double_three_by_three_500_payload()
    payload["support"]["square_tube_width_m"] = 0.12
    payload["sections"][0]["sect_file"] = "120-120-8.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "L3=0.2" in rendered
    assert audit["assigned"]["L3"] == 0.2
    assert audit["l3_policy"]["status"] == "square_outer_width_le_120_l3_0p20m"


def test_single_width_family_l3_tracks_square_width_gt_120() -> None:
    source_text = "\n".join(
        [
            "H1=0.14",
            "H2=2.1",
            "L1=0.55",
            "L2=0.5",
            "L3=0.2",
            "L4=2.0",
            "senum=3",
            "senum1=3",
            "SECREAD,'140-140-8'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'YIXINGGANG150DAN'",
        ]
    )
    payload = _double_three_by_three_500_payload()
    payload["support"]["square_tube_width_m"] = 0.14
    payload["sections"][0]["sect_file"] = "140-140-8.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "L3=0.15" in rendered
    assert audit["assigned"]["L3"] == 0.15
    assert audit["l3_policy"]["status"] == "square_outer_width_gt_120_l3_0p15m"


def test_300_single_width_family_keeps_reviewed_l2_half_connection_offset() -> None:
    source_text = "\n".join(
        [
            "ET,4,188",
            "KEYOPT,4,4,2",
            "KEYOPT,4,1,1",
            "SECTYPE,10,BEAM,CSOLID",
            "SECDATA,0.004",
            "SECOFFSET,USER,",
            "H1=0.10",
            "H2=2.0",
            "L1=0.35",
            "L2=0.3",
            "L3=0.15",
            "L4=2.0",
            "senum=2",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,506+10*I+100*(J-1),H1/2+L1-L3,-L4/2+L4*(J-1),0.1+L5+0.2*(I-1)",
            "K,507+10*I+100*(J-1),H1/2+L1-L3,0+L4*(J-1),0.1+L5+0.2*(I-1)",
            "K,508+10*I+100*(J-1),H1/2+L1-L3,L4/2+L4*(J-1),0.1+L5+0.2*(I-1)",
            "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "SECREAD,'100-100-6'",
            "SECREAD,'300-75-2mm'",
        ]
    )
    payload = _single_two_layer_600_payload()
    payload["support"]["square_tube_width_m"] = 0.1
    payload["sections"][0]["sect_file"] = "100-100-6.SECT"
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.3
        layer["tray_section_id"] = "tray-300"
    payload["sections"][1]["section_id"] = "tray-300"
    payload["sections"][1]["sect_file"] = "300-75-2mm.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "L3=0.15" in rendered
    assert "H1/2+L1-L2/2" in rendered
    assert "K,502+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "K,506+10*I+100*(J-1),H1/2+L1-L3" in rendered
    assert "K,507+10*I+100*(J-1),H1/2+L1-L3" in rendered
    assert "K,508+10*I+100*(J-1),H1/2+L1-L3" in rendered
    assert "K,509+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert audit["l3_policy"]["status"] == "tray_width_le_300_l3_0p15m"
    assert audit["single_width_connection_offset"]["status"] == "not_required"


def test_300_standard_family_has_physical_bolt_round_bar_elements_not_only_coupling() -> None:
    source_text = "\n".join(
        [
            "ET,1,188",
            "KEYOPT,1,4,2",
            "ET,2,188",
            "KEYOPT,2,4,2",
            "ET,4,188",
            "KEYOPT,2,4,2",
            "SECTYPE,1,BEAM,MESH",
            "SECREAD,'100-100-6','SECT',,MESH",
            "SECTYPE,4,BEAM,MESH",
            "SECREAD,'300-75-2mm','SECT',,MESH",
            "SECTYPE,10,BEAM,CSOLID",
            "SECDATA,0.006",
            "SECOFFSET,USER,",
            "H1=0.10",
            "H2=2.0",
            "L1=0.35",
            "L2=0.3",
            "L3=0.15",
            "L4=2.0",
            "L5=0.074",
            "senum=2",
            "*DO,J,1,3",
            "*DO,I,1,senum",
            "K,501+10*I+100*(J-1),H1/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,503+10*I+100*(J-1),H1/2+L1,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,506+10*I+100*(J-1),H1/2+L1-L3,-L4/2+L4*(J-1),0.1+L5+0.2*(I-1)",
            "K,507+10*I+100*(J-1),H1/2+L1-L3,0+L4*(J-1),0.1+L5+0.2*(I-1)",
            "K,508+10*I+100*(J-1),H1/2+L1-L3,L4/2+L4*(J-1),0.1+L5+0.2*(I-1)",
            "L,506+10*I+100*(J-1),507+10*I+100*(J-1)",
            "L,507+10*I+100*(J-1),508+10*I+100*(J-1)",
            "*ENDDO",
            "*ENDDO",
            "ALLSEL",
            "LSEL,S,LOC,X,KX(516)",
            "LATT,1,,4,,,,10",
            "LESIZE,ALL,0.05,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "CPCYC,UX,,,,,L5-0.05",
        ]
    )
    payload = _single_two_layer_600_payload()
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.3
        layer["tray_section_id"] = "tray-300"
    payload["sections"][1]["section_id"] = "tray-300"
    payload["sections"][1]["sect_file"] = "300-75-2mm.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "SECTYPE,10,BEAM,CSOLID" in rendered
    assert "SECDATA,0.006" in rendered
    assert "LATT,1,,4,,,,10" in rendered
    assert "CPCYC,UX" in rendered
    assert audit["physical_bolt_modeling"]["status"] == "pass"
    assert audit["physical_bolt_modeling"]["checks"]["front_physical_bolt_lines"] is True


def test_200_small_tray_keeps_physical_bolt_with_reviewed_section_and_type4_keyopts() -> None:
    source_text = "\n".join(
        [
            "ET,4,188",
            "KEYOPT,2,4,2",
            "KEYOPT,2,1,1",
            "SECTYPE,10,BEAM,CSOLID",
            "SECDATA,0.006",
            "SECOFFSET,USER,",
            "H1=0.10",
            "H2=2.0",
            "L1=0.35",
            "L2=0.2",
            "L3=0.15",
            "L4=2.0",
            "L5=0.074",
            "senum=2",
            "SECREAD,'100-100-6'",
            "SECREAD,'200-75-2mm'",
            "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
            "L,503+10*I+100*(J-1),509+10*I+100*(J-1)",
            "ALLSEL",
            "LSEL,S,LOC,X,KX(516)",
            "LSEL,U,LOC,Y,KY(519)",
            "LATT,2,,2,,,,4",
            "LMESH,ALL",
            "ALLSEL",
            "LSEL,S,LOC,X,KX(516)",
            "LATT,1,,4,,,,10",
            "LMESH,ALL",
            "CPCYC,UX,,,,,L5-0.05",
        ]
    )
    payload = _single_two_layer_600_payload()
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.2
        layer["tray_section_id"] = "tray-200"
    payload["sections"][1]["section_id"] = "tray-200"
    payload["sections"][1]["sect_file"] = "200-75-2mm.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "ET,4,188" in rendered
    assert "KEYOPT,4,4,2" in rendered
    assert "KEYOPT,4,1,1" in rendered
    assert "KEYOPT,2,4,2\nKEYOPT,2,1,1\nSECTYPE,10" not in rendered
    assert "SECTYPE,10,BEAM,CSOLID" in rendered
    assert "SECTYPE,10,BEAM,CSOLID\nSECDATA,0.006" in rendered
    assert "SECDATA,0.004" not in rendered
    assert "K,509+10*I+100*(J-1)" in rendered
    assert "L,503+10*I+100*(J-1),509+10*I+100*(J-1)" in rendered
    assert "LSEL,U,LENG,,0.05" in rendered
    assert "LSEL,S,LENG,,0.05" in rendered
    assert "LSEL,U,LOC,Y,KY(519)" not in rendered
    assert "CTAI_SMALL_BOLT_LINES" not in rendered
    assert "LATT,1,,4,,,,10" in rendered
    assert "LATT,2,,2,,,,4" in rendered
    assert not _has_legacy_bolt_latt_pollution(rendered)
    assert audit["small_tray_physical_bolt_policy"]["status"] == "already_present"
    assert audit["small_tray_bolt_mesh_selection"]["status"] == "rewritten"
    assert audit["physical_bolt_modeling"]["status"] == "pass"
    assert audit["physical_bolt_modeling"]["checks"]["tray_mesh_excludes_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["bolt_mesh_selects_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["no_legacy_geometry_latt_pollution"] is True
    assert audit["physical_bolt_element_type_keyopts"]["status"] == "rewritten"
    assert audit["physical_bolt_element_type_keyopts"]["rewritten_count"] == 2
    assert audit["bolt_section_radius"]["status"] in {"already_present", "rewritten"}
    assert audit["bolt_section_radius"]["radius_m"] == 0.006
    assert audit["bolt_section_radius"]["widths_mm"] == [200]


def test_current_type_command_library_is_preferred_for_300_model_family() -> None:
    payload = _single_two_layer_600_payload()
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.3
        layer["tray_section_id"] = "tray-300"
    payload["sections"][1]["section_id"] = "tray-300"
    payload["sections"][1]["sect_file"] = "300-75-2mm.SECT"

    family = select_standard_model_family(payload)

    assert family["source_library"] == "current_type_command_flows"
    assert "resources" in family["source"].replace("\\", "/")
    assert family["source"].endswith("single_300_square.PIP")


def test_current_type_command_library_does_not_use_300_family_for_100_or_200_trays() -> None:
    for width_mm in (100, 200):
        payload = _single_two_layer_600_payload()
        tray_section_id = f"tray-{width_mm}"
        for layer in payload["tray_layers"]:
            layer["tray_width_m"] = width_mm / 1000.0
            layer["tray_section_id"] = tray_section_id
        payload["sections"][1]["section_id"] = tray_section_id
        payload["sections"][1]["sect_file"] = f"{width_mm}-75-2mm.SECT"

        family = select_standard_model_family(payload)

        assert family["source_library"] == "current_type_command_flows"
        assert not family["source"].endswith("single_300_square.PIP")
        assert "small_tray_must_not_use_300_family" not in [
            check.get("reason") for check in family.get("checks") or []
        ]


def test_current_type_single_200_meshes_only_physical_bolt_connector_lines() -> None:
    payload = _single_two_layer_600_payload()
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.2
        layer["tray_section_id"] = "tray-200"
    payload["sections"][1]["section_id"] = "tray-200"
    payload["sections"][1]["sect_file"] = "200-75-2mm.SECT"

    family = select_standard_model_family(payload)
    source_text, _ = read_text_with_encoding(Path(family["source"]))
    rendered, audit = _render_model_from_family(source_text, payload)

    assert not family["source"].endswith("single_300_square.PIP")
    assert "SECREAD,'200-75-2mm'" in rendered
    assert "SECTYPE,10,BEAM,CSOLID\nSECDATA,0.006" in rendered
    assert "SECDATA,0.004" not in rendered
    assert "LSEL,U,LENG,,0.05" in rendered
    assert "LSEL,S,LENG,,0.05" in rendered
    assert "CTAI_SMALL_BOLT_LINES" not in rendered
    assert "L,503+10*I+100*(J-1),509+10*I+100*(J-1)" in rendered
    assert "CPCYC,UX,,,,,L5-0.05" in rendered
    assert not _has_legacy_bolt_latt_pollution(rendered)
    assert audit["small_tray_bolt_mesh_selection"]["status"] == "rewritten"
    assert audit["physical_bolt_modeling"]["status"] == "pass"
    assert audit["physical_bolt_modeling"]["checks"]["tray_mesh_excludes_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["bolt_mesh_selects_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["no_legacy_geometry_latt_pollution"] is True


def test_double_200_small_tray_inserts_missing_physical_bolt_topology() -> None:
    payload = _payload_with_uniform_tray_width(200)

    family = select_standard_model_family(payload)
    source_text, _ = read_text_with_encoding(Path(family["source"]))
    rendered, audit = _render_model_from_family(source_text, payload)
    compact = "".join(rendered.split())

    assert family["source"].endswith("double_uniform_200_square.PIP")
    assert "ET,4,188" in rendered
    assert "KEYOPT,4,4,2" in rendered
    assert "KEYOPT,4,1,1" in rendered
    assert "SECTYPE,10,BEAM,CSOLID" in rendered
    assert "SECTYPE,10,BEAM,CSOLID\nSECDATA,0.006" in rendered
    assert "SECDATA,0.004" not in rendered
    assert "K,509+10*I+100*(J-1)" in rendered
    assert "K,1509+10*I+100*(J-1)" in rendered
    assert "L,503+10*I+100*(J-1),509+10*I+100*(J-1)" in rendered
    assert "L,1503+10*I+100*(J-1),1509+10*I+100*(J-1)" in rendered
    assert "LSEL,U,LENG,,0.05" in rendered
    assert "LSEL,S,LENG,,0.05" in rendered
    assert "LSEL,U,LOC,Y,KY(519)" not in rendered
    assert "LSEL,U,LOC,Y,KY(1519)" not in rendered
    assert "CTAI_SMALL_BOLT_LINES" not in rendered
    assert "CPCYC,UX,,,,,L5-0.05" in rendered
    assert "LATT,1,,4,,,,10" in compact
    assert not _has_legacy_bolt_latt_pollution(rendered)
    assert audit["small_tray_physical_bolt_policy"]["status"] == "already_present"
    assert audit["small_tray_bolt_mesh_selection"]["status"] == "rewritten"
    assert audit["bolt_section_radius"]["radius_m"] == 0.006
    assert audit["physical_bolt_element_type_keyopts"]["status"] in {"already_correct", "inserted", "rewritten"}
    assert audit["physical_bolt_modeling"]["status"] == "pass"
    assert audit["physical_bolt_modeling"]["checks"]["tray_mesh_excludes_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["bolt_mesh_selects_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["no_legacy_geometry_latt_pollution"] is True


def test_current_type_width_families_do_not_mix_100_200_300_or_500_600_topology() -> None:
    def single_payload(width_mm: int, square_section: str = "100-100-6") -> dict:
        payload = _single_two_layer_600_payload()
        tray_section_id = f"tray-{width_mm}"
        for layer in payload["tray_layers"]:
            layer["tray_width_m"] = width_mm / 1000.0
            layer["tray_section_id"] = tray_section_id
        payload["sections"] = [
            {"section_id": "square", "sect_file": f"{square_section}.SECT"},
            {"section_id": tray_section_id, "sect_file": f"{width_mm}-75-2mm.SECT"},
        ]
        outer_mm = int(square_section.split("-")[0])
        payload["support"]["square_tube_width_m"] = outer_mm / 1000.0
        return payload

    for width_mm in (100, 200):
        payload = single_payload(width_mm)
        family = select_standard_model_family(payload)
        source_text, _ = read_text_with_encoding(Path(family["source"]))
        rendered, audit = _render_model_from_family(source_text, payload)

        assert family["source"].endswith("single_uniform_200_square.PIP")
        assert f"SECREAD,'{width_mm}-75-2mm'" in rendered
        assert "SECTYPE,10,BEAM,CSOLID\nSECDATA,0.006" in rendered
        assert "L3=0.15" in rendered
        assert "K,502+10*I+100*(J-1),H1/2+L1-L3" in rendered
        assert "K,503+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "K,506+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "K,509+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "L,503+10*I+100*(J-1),509+10*I+100*(J-1)" in rendered
        assert "LSEL,U,LENG,,0.05" in rendered
        assert "LSEL,S,LENG,,0.05" in rendered
        assert "LSEL,U,LOC,Y,KY(519)" not in rendered
        assert "CTAI_SMALL_BOLT_LINES" not in rendered
        assert audit["physical_bolt_modeling"]["status"] == "pass"

    payload_300 = single_payload(300)
    family_300 = select_standard_model_family(payload_300)
    source_300, _ = read_text_with_encoding(Path(family_300["source"]))
    rendered_300, audit_300 = _render_model_from_family(source_300, payload_300)

    assert family_300["source"].endswith("single_300_square.PIP")
    assert "L3=0.15" in rendered_300
    assert "K,502+10*I+100*(J-1),H1/2+L1-L2/2" in rendered_300
    assert "K,506+10*I+100*(J-1),H1/2+L1-L3" in rendered_300
    assert "K,507+10*I+100*(J-1),H1/2+L1-L3" in rendered_300
    assert "K,508+10*I+100*(J-1),H1/2+L1-L3" in rendered_300
    assert "K,509+10*I+100*(J-1),H1/2+L1-L2/2" in rendered_300
    assert "K,506+10*I+100*(J-1),H1/2+L1-L2/2" not in rendered_300
    assert audit_300["physical_bolt_modeling"]["status"] == "pass"

    for width_mm in (500, 600):
        payload = single_payload(width_mm)
        family = select_standard_model_family(payload)
        source_text, _ = read_text_with_encoding(Path(family["source"]))
        rendered, audit = _render_model_from_family(source_text, payload)

        assert family["source"].endswith("single_uniform_square.PIP")
        assert f"L2={width_mm / 1000:g}" in rendered
        assert "L3=0.2" in rendered
        assert "K,502+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "K,506+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "K,507+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "K,508+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "K,509+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
        assert "SECOFFSET,user,,-0.03249\nSECREAD,'CAOGANG42DAN'" in rendered
        assert audit["l3_policy"]["status"] == "square_outer_width_le_120_l3_0p20m"

        yixing_payload = single_payload(width_mm, square_section="140-140-8")
        yixing_family = select_standard_model_family(yixing_payload)
        yixing_source, _ = read_text_with_encoding(Path(yixing_family["source"]))
        yixing_rendered, yixing_audit = _render_model_from_family(yixing_source, yixing_payload)

        assert yixing_family["source"].endswith("single_uniform_yixing.PIP")
        assert "L3=0.15" in yixing_rendered
        assert "SECOFFSET,user,,-0.03249\nSECREAD,'YIXINGGANG150DAN'" not in yixing_rendered
        assert "SECOFFSET,user\nSECREAD,'YIXINGGANG150DAN'" in yixing_rendered
        assert yixing_audit["l3_policy"]["status"] == "square_outer_width_gt_120_l3_0p15m"


def test_standard_model_renderer_strips_embedded_modal_solve_tail_from_model_stream() -> None:
    source_text = "\n".join(
        [
            "finish",
            "/clear",
            "/prep7",
            "ET,1,188",
            "KEYOPT,1,4,2",
            "KEYOPT,1,1,1",
            "ET,2,188",
            "KEYOPT,2,4,2",
            "KEYOPT,2,1,1",
            "SECTYPE,1,BEAM,MESH",
            "SECREAD,'100-100-6','SECT',,MESH",
            "SECTYPE,2,BEAM,MESH",
            "SECREAD,'50-42','SECT',,MESH",
            "SECTYPE,3,BEAM,MESH",
            "SECOFFSET,user,,-0.03249",
            "SECREAD,'CAOGANG42DAN','SECT',,MESH",
            "SECTYPE,4,BEAM,MESH",
            "SECREAD,'600-75-2mm','SECT',,MESH",
            "H1=0.1",
            "H2=2.0",
            "L1=0.55",
            "L2=0.6",
            "L3=0.2",
            "L4=2.0",
            "senum=2",
            "ALLSEL",
            "CM,YUESHU,NODE",
            "! historical modal tail copied from reviewed 01/PIP source",
            "/OUTPUT,'8TEG009010','TXT','',",
            "FINISH",
            "/SOL",
            "ANTYPE,2",
            "MODOPT,LANB,887",
            "MXPAND,887,,,0",
            "SOLVE",
            "FINI",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _single_two_layer_600_payload())

    assert audit["embedded_analysis_tail"]["status"] == "stripped"
    assert "CM,YUESHU,NODE" in rendered
    assert "/SOL" not in rendered
    assert "ANTYPE,2" not in rendered
    assert "MODOPT,LANB,887" not in rendered
    assert "MXPAND,887" not in rendered
    assert re.search(r"(?im)^\s*SOLVE\b", rendered) is None
    assert rendered.rstrip().endswith("FINISH")


def test_300_modeling_gate_fails_when_only_coupling_exists_without_bolt_elements() -> None:
    source_text = "\n".join(
        [
            "H1=0.10",
            "H2=2.0",
            "L1=0.35",
            "L2=0.3",
            "L3=0.15",
            "L4=2.0",
            "senum=2",
            "SECREAD,'100-100-6'",
            "SECREAD,'300-75-2mm'",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "CPCYC,UX,,,,,L5-0.05",
        ]
    )
    payload = _single_two_layer_600_payload()
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.3
        layer["tray_section_id"] = "tray-300"
    payload["sections"][1]["section_id"] = "tray-300"
    payload["sections"][1]["sect_file"] = "300-75-2mm.SECT"

    _, audit = _render_model_from_family(source_text, payload)

    assert audit["physical_bolt_modeling"]["status"] == "fail"
    assert "round_bar_section_10" in audit["physical_bolt_modeling"]["missing"]
    assert "section_10_latt_meshing" in audit["physical_bolt_modeling"]["missing"]
    assert audit["physical_bolt_modeling"]["checks"]["has_coupling_only_as_supplement"] is True


def test_200_small_tray_reuses_reviewed_small_tray_arm_partition() -> None:
    source_text = "\n".join(
        [
            "ET,4,188",
            "KEYOPT,4,4,2",
            "KEYOPT,4,1,1",
            "SECTYPE,10,BEAM,CSOLID",
            "SECDATA,0.004",
            "SECOFFSET,USER,",
            "H1=0.10",
            "H2=2.0",
            "L1=0.35",
            "L2=0.5",
            "L3=0.2",
            "L4=1.8",
            "L5=0.074",
            "senum=2",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,503+10*I+100*(J-1),H1/2+L1-L3,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,506+10*I+100*(J-1),H1/2+L1-L2/2,-L4/2+L4*(J-1),0.168+0.2*(I-1)",
            "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
            "L,502+10*I+100*(J-1),503+10*I+100*(J-1)",
            "L,502+10*I+100*(J-1),509+10*I+100*(J-1)",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "CPCYC,UX,,,,,0.068-0.05",
            "ALLSEL",
            "LSEL,S,LOC,X,KX(516)",
            "LATT,2,,2,,,,4",
            "LMESH,ALL",
            "ALLSEL",
            "LSEL,S,LOC,X,KX(516)",
            "LATT,1,,4,,,,10",
            "LMESH,ALL",
            "SECREAD,'100-100-6'",
            "SECREAD,'500-75-2mm'",
        ]
    )
    payload = _single_two_layer_600_payload()
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.2
        layer["tray_section_id"] = "tray-200"
    payload["sections"][1]["section_id"] = "tray-200"
    payload["sections"][1]["sect_file"] = "200-75-2mm.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "L2=0.2" in rendered
    assert "L3=0.15" in rendered
    assert "L5=0.074" in rendered
    assert "K,502+10*I+100*(J-1),H1/2+L1-L3" in rendered
    assert "K,503+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "0.1+L5+0.2*(I-1)" in rendered
    assert "CPCYC,UX,,,,,L5-0.05" in rendered
    assert "0.068-0.05" not in rendered
    assert "K,509+10*I+100*(J-1)" in rendered
    assert "L,503+10*I+100*(J-1),509+10*I+100*(J-1)" in rendered
    assert "LSEL,U,LENG,,0.05" in rendered
    assert "LSEL,S,LENG,,0.05" in rendered
    assert "CTAI_SMALL_BOLT_LINES" not in rendered
    assert not _has_legacy_bolt_latt_pollution(rendered)
    assert audit["small_tray_arm_partition"]["status"] == "rewritten"
    assert audit["small_tray_physical_bolt_policy"]["status"] == "already_present"
    assert audit["small_tray_bolt_mesh_selection"]["status"] == "rewritten"
    assert audit["physical_bolt_modeling"]["status"] == "pass"
    assert audit["physical_bolt_modeling"]["checks"]["tray_mesh_excludes_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["bolt_mesh_selects_short_bolt_lines"] is True
    assert audit["small_tray_arm_partition"]["z_offset_replacements"] == 1
    assert audit["small_tray_arm_partition"]["coupling_offset_replacements"] == 1
    assert audit["l3_policy"]["status"] == "tray_width_le_300_l3_0p15m"


def test_100_small_tray_reuses_reviewed_small_tray_arm_partition() -> None:
    source_text = "\n".join(
        [
            "ET,4,188",
            "KEYOPT,4,4,2",
            "KEYOPT,4,1,1",
            "SECTYPE,10,BEAM,CSOLID",
            "SECDATA,0.004",
            "SECOFFSET,USER,",
            "H1=0.10",
            "H2=2.0",
            "L1=0.35",
            "L2=0.5",
            "L3=0.2",
            "L4=1.8",
            "L5=0.074",
            "senum=2",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,503+10*I+100*(J-1),H1/2+L1-L3,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,506+10*I+100*(J-1),H1/2+L1-L2/2,-L4/2+L4*(J-1),0.168+0.2*(I-1)",
            "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
            "L,502+10*I+100*(J-1),503+10*I+100*(J-1)",
            "L,502+10*I+100*(J-1),509+10*I+100*(J-1)",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "CPCYC,UX,,,,,0.068-0.05",
            "ALLSEL",
            "LSEL,S,LOC,X,KX(516)",
            "LATT,2,,2,,,,4",
            "LMESH,ALL",
            "ALLSEL",
            "LSEL,S,LOC,X,KX(516)",
            "LATT,1,,4,,,,10",
            "LMESH,ALL",
            "SECREAD,'100-100-6'",
            "SECREAD,'500-75-2mm'",
        ]
    )
    payload = _single_two_layer_600_payload()
    for layer in payload["tray_layers"]:
        layer["tray_width_m"] = 0.1
        layer["tray_section_id"] = "tray-100"
    payload["sections"][1]["section_id"] = "tray-100"
    payload["sections"][1]["sect_file"] = "100-75-2mm.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "L2=0.1" in rendered
    assert "L3=0.15" in rendered
    assert "L5=0.074" in rendered
    assert "K,502+10*I+100*(J-1),H1/2+L1-L3" in rendered
    assert "K,503+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "K,506+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "0.1+L5+0.2*(I-1)" in rendered
    assert "K,509+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "CPCYC,UX,,,,,L5-0.05" in rendered
    assert "0.068-0.05" not in rendered
    assert "L,503+10*I+100*(J-1),509+10*I+100*(J-1)" in rendered
    assert "LSEL,U,LENG,,0.05" in rendered
    assert "LSEL,S,LENG,,0.05" in rendered
    assert "CTAI_SMALL_BOLT_LINES" not in rendered
    assert not _has_legacy_bolt_latt_pollution(rendered)
    assert audit["small_tray_arm_partition"]["status"] == "rewritten"
    assert audit["small_tray_physical_bolt_policy"]["status"] == "already_present"
    assert audit["small_tray_bolt_mesh_selection"]["status"] == "rewritten"
    assert audit["physical_bolt_modeling"]["status"] == "pass"
    assert audit["physical_bolt_modeling"]["checks"]["tray_mesh_excludes_short_bolt_lines"] is True
    assert audit["physical_bolt_modeling"]["checks"]["bolt_mesh_selects_short_bolt_lines"] is True
    assert audit["small_tray_arm_partition"]["z_offset_replacements"] == 1
    assert audit["small_tray_arm_partition"]["coupling_offset_replacements"] == 1
    assert audit["l3_policy"]["status"] == "tray_width_le_300_l3_0p15m"


def test_500_single_width_family_keeps_reviewed_l2_half_tray_and_bolt_offsets() -> None:
    source_text = "\n".join(
        [
            "H1=0.10",
            "H2=2.0",
            "L1=0.55",
            "L2=0.5",
            "L3=0.2",
            "L4=2.0",
            "L5=0.074",
            "senum=2",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,503+10*I+100*(J-1),H1/2+L1-L3,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,506+10*I+100*(J-1),H1/2+L1-L2/2,-L4/2+L4*(J-1),0.1+L5+0.2*(I-1)",
            "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
            "L,502+10*I+100*(J-1),503+10*I+100*(J-1)",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "SECREAD,'100-100-6'",
            "SECREAD,'500-75-2mm'",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert "L2=0.5" in rendered
    assert "K,502+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "K,503+10*I+100*(J-1),H1/2+L1-L3" in rendered
    assert "K,506+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "K,509+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2" in rendered
    assert audit["assigned"]["L3"] == 0.2
    assert audit["l3_policy"]["status"] == "square_outer_width_le_120_l3_0p20m"
    assert audit["single_width_connection_offset"]["status"] == "not_required"


def test_600_single_width_family_keeps_reviewed_l2_half_tray_and_bolt_offsets() -> None:
    source_text = "\n".join(
        [
            "H1=0.10",
            "H2=2.0",
            "L1=0.35",
            "L2=0.6",
            "L3=0.15",
            "L4=2.0",
            "L5=0.074",
            "senum=2",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,503+10*I+100*(J-1),H1/2+L1-L3,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,506+10*I+100*(J-1),H1/2+L1-L2/2,-L4/2+L4*(J-1),0.1+L5+0.2*(I-1)",
            "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
            "L,502+10*I+100*(J-1),503+10*I+100*(J-1)",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "SECREAD,'100-100-6'",
            "SECREAD,'600-75-2mm'",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _single_two_layer_600_payload())

    assert "K,502+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "K,503+10*I+100*(J-1),H1/2+L1-L3" in rendered
    assert "K,506+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "K,509+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2" in rendered
    assert audit["assigned"]["L3"] == 0.2
    assert audit["l3_policy"]["status"] == "square_outer_width_le_120_l3_0p20m"
    assert audit["single_width_connection_offset"]["status"] == "not_required"


def test_multi_width_family_keeps_l2_half_connection_offset() -> None:
    source_text = "\n".join(
        [
            "H1=0.14",
            "H2=2.0",
            "L1=0.75",
            "L2=0.6",
            "L3=0.6",
            "L4=0.3",
            "L5=0.2",
            "L6=2.0",
            "senum=4",
            "senum1=2",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L6*(J-1),0.1+0.2*(I-1)",
            "SECREAD,'140-140-8'",
            "SECREAD,'YIXINGGANG150'",
            "SECREAD,'YIXINGGANG150DAN'",
            "SECREAD,'600-75-2mm'",
            "SECREAD,'300-75-2mm'",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert "H1/2+L1-L2/2" in rendered
    assert audit["single_width_connection_offset"]["status"] == "not_required"


def test_double_side_single_width_family_keeps_l2_half_for_wide_tray_connection_offset() -> None:
    source_text = "\n".join(
        [
            "H1=0.10",
            "H2=2.0",
            "L1=0.55",
            "L2=0.5",
            "L3=0.15",
            "L4=2.0",
            "senum=2",
            "senum1=2",
            "K,502+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.1+0.2*(I-1)",
            "K,1502+10*I+100*(J-1),-(H1/2+L1-L2/2),0+L4*(J-1),0.1+0.2*(I-1)",
            "K,1509+10*I+100*(J-1),-(H1/2+L1-L2/2),0+L4*(J-1),0.15+0.2*(I-1)",
            "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2",
            "NSEL,A,LOC,X,-(H1/2+L1-L2/2),-(H1/2+L1-L2/2)",
            "SECREAD,'100-100-6'",
            "SECREAD,'500-75-2mm'",
            "SECREAD,'500-75-2mm'",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert "K,502+10*I+100*(J-1),H1/2+L1-L2/2" in rendered
    assert "K,1502+10*I+100*(J-1),-(H1/2+L1-L2/2)" in rendered
    assert "K,1509+10*I+100*(J-1),-(H1/2+L1-L2/2)" in rendered
    assert "NSEL,S,LOC,X,H1/2+L1-L2/2,H1/2+L1-L2/2" in rendered
    assert "NSEL,A,LOC,X,-(H1/2+L1-L2/2),-(H1/2+L1-L2/2)" in rendered
    assert audit["single_width_connection_offset"]["status"] == "not_required"


def test_standard_family_expands_keypoint_numbering_for_twelve_layers() -> None:
    rendered, audit = _render_model_from_family(_high_layer_source_text(), _double_layer_payload(12))

    numbering = audit["keypoint_numbering"]
    assert numbering["status"] == "expanded_for_high_layer_count"
    assert numbering["keypoint_offset"] == 20
    assert numbering["frame_step"] == 200
    assert "KPOFF=20" in rendered
    assert "KPFSTEP=200" in rendered
    assert "K,501+KPOFF+10*I+KPFSTEP*(J-1)" in rendered
    assert "K,501+10*I+100*(J-1)" not in rendered
    assert "K,500+I+KPFSTEP*(J-1)" in rendered
    assert "KSEL,S,KP,,500+senum+1,500+2*KPFSTEP+senum+1,KPFSTEP" in rendered
    assert "KX(500+KPOFF+10+6)" in rendered
    assert "KY(500+2*KPFSTEP+KPOFF+10+9)" in rendered
    assert "KY(KPBKBASE+2*KPFSTEP+KPOFF+10+9)" in rendered
    assert (
        "NKMS02=NODE(KX(500+KPFSTEP+1+senum),KY(500+KPFSTEP+1+senum),"
        "KZ(500+KPFSTEP+1+senum))"
    ) in rendered

    vertical_keypoints = {500 + layer for layer in range(0, 14)}
    first_frame_arm_keypoints = {
        500 + numbering["keypoint_offset"] + 10 * layer + suffix
        for layer in range(1, 13)
        for suffix in (1, 2, 3, 4, 6, 7, 8, 9)
    }
    assert not (vertical_keypoints & first_frame_arm_keypoints)
    assert max(first_frame_arm_keypoints) < 500 + numbering["frame_step"]


def test_post_keypoint_numbering_tracks_high_layer_model_numbering() -> None:
    numbering = _standard_family_keypoint_numbering(12, 12)
    post_text = "\n".join(
        [
            "senum=12",
            "senum1=12",
            "KXALS%3*(I-1)+1%=501+I*10",
            "KXALS%3*(I-1)+2%=601+I*10",
            "KXALS%3*(I-1)+3%=701+I*10",
            "KYALS%3*senum+3*(J-1)+1%=1501+J*10",
            "KYALS%3*senum+3*(J-1)+2%=1601+J*10",
            "KYALS%3*senum+3*(J-1)+3%=1701+J*10",
            "NKMS02=NODE(KX(601+senum),KY(601+senum),KZ(601+senum))",
        ]
    )

    rendered, audit = _apply_post_keypoint_numbering(post_text, numbering)

    assert audit["status"] == "expanded_for_high_layer_count"
    assert "KXALS%3*(I-1)+1%=501+KPOFF+I*10" in rendered
    assert "KXALS%3*(I-1)+2%=500+KPFSTEP+1+KPOFF+I*10" in rendered
    assert "KXALS%3*(I-1)+3%=500+2*KPFSTEP+1+KPOFF+I*10" in rendered
    assert "KYALS%3*senum+3*(J-1)+1%=KPBKBASE+1+KPOFF+J*10" in rendered
    assert "KYALS%3*senum+3*(J-1)+2%=KPBKBASE+KPFSTEP+1+KPOFF+J*10" in rendered
    assert "KYALS%3*senum+3*(J-1)+3%=KPBKBASE+2*KPFSTEP+1+KPOFF+J*10" in rendered
    assert (
        "NKMS02=NODE(KX(500+KPFSTEP+1+senum),KY(500+KPFSTEP+1+senum),"
        "KZ(500+KPFSTEP+1+senum))"
    ) in rendered


def test_standard_family_inserts_zero_secondary_layer_count_for_single_side_source() -> None:
    source_text = "\n".join(
        [
            "H1=0.14",
            "H2=2.0",
            "L1=0.75",
            "L2=0.6",
            "L3=0.2",
            "L4=2.0",
            "senum=4",
            "SECREAD,'100-100-6'",
            "SECREAD,'50-42'",
            "SECREAD,'CAOGANG42DAN'",
            "SECREAD,'500-75-2mm'",
            "MP,DENS,2,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _single_two_layer_600_payload())

    assert "senum=2" in rendered
    assert "senum1=0" in rendered
    assert rendered.index("senum=2") < rendered.index("senum1=0")
    assert "SECREAD,'600-75-2mm'" in rendered
    assert audit["assigned"]["senum"] == 2
    assert audit["assigned"]["senum1"] == 0


def test_standard_family_restores_standard_beam188_warping_keyopts_when_source_omits_them() -> None:
    source_text = "\n".join(
        [
            "H1=0.1",
            "H2=2.1",
            "L1=0.55",
            "L2=0.3",
            "L3=0.2",
            "L4=2.0",
            "senum=2",
            "ET,1,188",
            "KEYOPT,1,4,2",
            "ET,2,188",
            "KEYOPT,2,4,2",
            "SECREAD,'100-100-6'",
            "SECREAD,'300-75-2mm'",
            "ALLSEL",
            "NSEL,S,LOC,X,0,H1/2",
            "CPCYC,ALL,,,H1/2",
        ]
    )
    payload = _single_two_layer_600_payload()
    payload["tray_layers"][0]["tray_width_m"] = 0.3
    payload["tray_layers"][1]["tray_width_m"] = 0.3
    payload["sections"][1]["sect_file"] = "300-75-2mm.SECT"

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "KEYOPT,1,1,1" in rendered
    assert "KEYOPT,2,1,1" in rendered
    assert rendered.index("KEYOPT,1,4,2") < rendered.index("KEYOPT,1,1,1")
    assert rendered.index("KEYOPT,2,4,2") < rendered.index("KEYOPT,2,1,1")
    assert audit["beam188_warping_keyopts"]["status"] == "inserted"
    assert audit["beam188_warping_keyopts"]["inserted_element_types"] == [1, 2]


def test_standard_family_does_not_duplicate_existing_beam188_warping_keyopts() -> None:
    source_text = "\n".join(
        [
            "H1=0.1",
            "H2=2.1",
            "L1=0.55",
            "L2=0.5",
            "L3=0.2",
            "L4=2.0",
            "senum=3",
            "senum1=3",
            "ET,1,188",
            "KEYOPT,1,4,2",
            "KEYOPT,1,1,1",
            "ET,2,188",
            "KEYOPT,2,4,2",
            "KEYOPT,2,1,1",
            "SECREAD,'100-100-6'",
            "SECREAD,'500-75-2mm'",
            "ALLSEL",
            "NSEL,S,LOC,X,0,H1/2",
            "CPCYC,ALL,,,H1/2",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert rendered.count("KEYOPT,1,1,1") == 1
    assert rendered.count("KEYOPT,2,1,1") == 1
    assert audit["beam188_warping_keyopts"]["status"] == "already_present"


def test_standard_family_yixing_rewrite_removes_channel_secondary_offset() -> None:
    payload = _double_three_by_three_500_payload()
    payload["support"]["square_tube_width_m"] = 0.14
    payload["sections"][0]["sect_file"] = "140-140-8.SECT"
    source_text = "\n".join(
        [
            "H1=0.1",
            "H2=2.0",
            "L1=0.55",
            "L2=0.5",
            "L3=0.2",
            "L4=2.0",
            "senum=3",
            "senum1=3",
            "SECREAD,'100-100-6'",
            "SECOFFSET,cent,",
            "SECREAD,'50-42'",
            "SECOFFSET,user,,-0.03249",
            "SECREAD,'CAOGANG42DAN'",
            "SECREAD,'500-75-2mm'",
            "MP,DENS,2,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, payload)

    assert "SECREAD,'YIXINGGANG150'" in rendered
    assert "SECREAD,'YIXINGGANG150DAN'" in rendered
    assert "SECOFFSET,user,,-0.03249\nSECREAD,'YIXINGGANG150DAN'" not in rendered
    assert "SECOFFSET,user\nSECREAD,'YIXINGGANG150DAN'" in rendered
    assert audit["yixing_secoffset_replacements"] == 1


def test_standard_family_rewrites_single_width_source_l2_without_overwriting_arm_tail() -> None:
    source_text = "\n".join(
        [
            "H1=0.14",
            "H2=2.0",
            "L1=0.75",
            "L2=0.6                        ! tray width in this source family",
            "L3=0.2                        ! arm tail / connection geometry, not tray width",
            "L4=2.0",
            "senum=5",
            "senum1=2",
            "SECREAD,'140-140-8'",
            "SECREAD,'YIXINGGANG150'",
            "SECREAD,'YIXINGGANG150DAN'",
            "MP,DENS,2,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert "L2=0.5" in rendered
    assert "L3=0.2" in rendered
    assert "senum=3" in rendered
    assert "senum1=3" in rendered
    assert audit["assigned"]["L2"] == 0.5
    assert audit["assigned"]["L3"] == 0.2
    assert audit["assigned"]["senum"] == 3
    assert audit["assigned"]["senum1"] == 3


def test_template_context_uses_500_tray_section_for_double_three_by_three() -> None:
    context = build_standard_s2_template_context(_double_three_by_three_500_payload())

    assert context["qian_n_layers"] == 3
    assert context["hou_n_layers"] == 3
    for index in range(1, 4):
        assert context["qian"][index]["c"] == 0.5
        assert context["hou"][index]["c"] == 0.5
        assert context["qian"][index]["tray_sect"] == "500-75-2mm"
        assert context["hou"][index]["tray_sect"] == "500-75-2mm"


def test_template_context_uses_600_tray_section_for_600_intake_width() -> None:
    context = build_standard_s2_template_context(_payload_with_uniform_tray_width(600))

    for index in range(1, 4):
        assert context["qian"][index]["c"] == 0.6
        assert context["hou"][index]["c"] == 0.6
        assert context["qian"][index]["tray_sect"] == "600-75-2mm"
        assert context["hou"][index]["tray_sect"] == "600-75-2mm"


def test_standard_family_marks_missing_required_tray_section_when_source_has_no_tray_secread() -> None:
    source_text = "\n".join(
        [
            "H1=0.1",
            "H2=2.1",
            "L1=0.55",
            "L2=0.5",
            "L3=0.2",
            "L4=2.0",
            "senum=3",
            "senum1=3",
            "SECREAD,'100-100-8'",
            "SECREAD,'50-42'",
            "SECREAD,'CAOGANG42DAN'",
            "MP,DENS,2,7850",
            "MP,DENS,3,7850",
        ]
    )

    rendered, audit = _render_model_from_family(source_text, _double_three_by_three_500_payload())

    assert "SECREAD,'500-75-2mm'" not in rendered
    assert audit["tray_section_status"] == "fail"
    assert audit["missing_required_tray_sections"] == ["500-75-2mm"]


def test_modal_policy_source_bundle_uses_same_name_library_modal_source(tmp_path) -> None:
    report_root = tmp_path / "reports"
    current_dir = report_root / "current" / "calc"
    reference_dir = report_root / "reference" / "calc"
    current_dir.mkdir(parents=True)
    reference_dir.mkdir(parents=True)
    current_source = current_dir / "01 same.PIP"
    reference_source = reference_dir / "01 same.PIP"
    current_source.write_text("FINISH\n/PREP7\n", encoding="utf-8")
    reference_source.write_text("ANTYPE,2\nMODOPT,LANB,887\nMXPAND,887,,,0\n", encoding="utf-8")

    bundle = _modal_policy_source_bundle(
        current_source,
        current_source.read_text(encoding="utf-8"),
        "ANTYPE,0\n",
        include_family_literal_modopt=True,
    )

    assert parse_source_modal_mode_count(bundle) == 887
    assert "library_modal_policy_source" in bundle


def test_static_solve_from_source_does_not_insert_modal_or_mt() -> None:
    source_text = "\n".join(
        [
            "/SOL",
            "ANTYPE,0",
            "ACEL,0.1,0.2,0.3",
            "SOLVE",
            "FINISH",
        ]
    )
    payload = {
        "metadata": {
            "analysis_method": "static",
            "zpa_obe_x_g": 0.11,
            "zpa_obe_y_g": 0.12,
            "zpa_obe_z_g": 0.13,
            "zpa_sse_x_g": 0.21,
            "zpa_sse_y_g": 0.22,
            "zpa_sse_z_g": 0.23,
            "static_acceleration_factor": 1.5,
        },
        "project": {"elevation": 8.5},
    }

    rendered, audit = _render_solve_from_source(Path("02静力法-计算文件.PIP"), source_text, payload)

    assert "ANTYPE,2" not in rendered
    assert "MODOPT" not in rendered
    assert "MXPAND" not in rendered
    assert "MT=" not in rendered
    assert "ACEL,1.5*9.81*0.11,1.5*9.81*0.12,1.5*9.81*0.13" in rendered
    assert audit["modal_mode_policy"]["status"] == "not_required"
