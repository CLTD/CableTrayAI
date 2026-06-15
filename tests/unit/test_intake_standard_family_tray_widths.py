from __future__ import annotations

from pathlib import Path

from core.apdl.intake_standard_family_renderer import (
    _apply_post_keypoint_numbering,
    _modal_policy_source_bundle,
    _render_model_from_family,
    _render_solve_from_source,
    _standard_family_keypoint_numbering,
)
from core.apdl.modal_policy import parse_source_modal_mode_count
from core.apdl.intake_template_context import build_standard_s2_template_context


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
