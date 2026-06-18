from __future__ import annotations

from pathlib import Path

from core.apdl.postprocessor_alignment import align_postprocessor_to_intake
from core.apdl.section_specific_export import augment_square_support_export


def test_source_family_tbmodel_selector_uses_type1_section_filter(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.14},"metadata":{"square_section_outer_mm":140}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "LATT,1,,1,,,,1",
                "LATT,1,,1,,,,2",
                "LATT,1,,1,,,,3",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "! CableTrayAI: export a dedicated cantilever/tray-arm model figure for report Fig. 5.2.",
                "ESEL,NONE",
                "*DO,_CTAI_LAYER,1,10,1",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+2",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+3",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+4",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+2",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+3",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+4",
                "*ENDDO",
                "*GET,_CTAI_TB_ECOUNT,ELEM,0,COUNT",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    audit = align_postprocessor_to_intake(job_dir)
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")

    assert audit["tbmodel_selector"]["status"] == "source_topology_applied"
    assert "ESEL,S,TYPE,,1" in text
    assert "ESEL,U,SEC,,1" in text
    assert "10*_CTAI_LAYER" not in text


def test_grouped_mixed_tmax_selector_uses_arm_sections(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.10},"metadata":{"square_section_outer_mm":100}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "! CableTrayAI current-type grouped mixed tray model",
                "ARM_ET(NARM)=2",
                "ARM_SEC(NARM)=2",
                "ARM_ET(NARM)=2",
                "ARM_SEC(NARM)=3",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "ESEL,NONE",
                "*DO,_CTAI_LAYER,1,10,1",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+2",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+3",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+4",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+2",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+3",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+4",
                "*ENDDO",
                "ALLSEL",
                "! CableTrayAI audited cantilever selector for parameterized S2 models.",
                "! front/back layer-specific selector",
                "ESEL,NONE",
                "*DO,I,1,qiancengshu,1",
                "ESEL,A,TYPE,,10*I+2",
                "ESEL,A,TYPE,,10*I+3",
                "*ENDDO",
                "*DO,I,1,houcengshu,1",
                "ESEL,A,TYPE,,200*I+2",
                "ESEL,A,TYPE,,200*I+3",
                "*ENDDO",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    audit = align_postprocessor_to_intake(job_dir)
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")
    before_tmax = text.split("*CREATE,TMAXBEAMSTRESS-WRITE,MAC", 1)[0]

    assert audit["section_based_arm_topology"] is True
    assert audit["tbmodel_selector"]["status"] == "section_topology_applied"
    assert "ESEL,A,SEC,,4,9" in before_tmax
    assert audit["tmax_selector"]["status"] == "applied"
    assert audit["tmax_selector"]["replacement_mode"] == "parameterized_selector_replaced"
    assert "ESEL,S,SEC,,2" in before_tmax
    assert "ESEL,A,SEC,,3" in before_tmax
    assert "10*_CTAI_LAYER" not in before_tmax
    assert "10*I+2" not in before_tmax


def test_ctai_mixed_component_topology_uses_declared_components(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.10},"metadata":{"square_section_outer_mm":100}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "CM,CTAI_SUPPORT_ELEMS,ELEM",
                "CM,CTAI_ARM_ELEMS,ELEM",
                "CM,CTAI_TRAY_ELEMS,ELEM",
                "CM,CTAI_BOLT_ELEMS,ELEM",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "ESEL,NONE",
                "*DO,_CTAI_LAYER,1,10,1",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+2",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+3",
                "  ESEL,A,TYPE,,10*_CTAI_LAYER+4",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+2",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+3",
                "  ESEL,A,TYPE,,200*_CTAI_LAYER+4",
                "*ENDDO",
                "ALLSEL",
                "! CableTrayAI audited cantilever selector for parameterized S2 models.",
                "ESEL,NONE",
                "*DO,I,1,qiancengshu,1",
                "ESEL,A,TYPE,,10*I+2",
                "ESEL,A,TYPE,,10*I+3",
                "*ENDDO",
                "*DO,I,1,houcengshu,1",
                "ESEL,A,TYPE,,200*I+2",
                "ESEL,A,TYPE,,200*I+3",
                "*ENDDO",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    audit = align_postprocessor_to_intake(job_dir)
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")
    before_tmax = text.split("*CREATE,TMAXBEAMSTRESS-WRITE,MAC", 1)[0]

    assert audit["component_topology"] is True
    assert audit["tbmodel_selector"]["status"] == "component_topology_applied"
    assert audit["tmax_selector"]["status"] == "applied"
    assert "CMSEL,S,CTAI_ARM_ELEMS,ELEM" in before_tmax
    assert "CMSEL,A,CTAI_TRAY_ELEMS,ELEM" in before_tmax
    assert "10*_CTAI_LAYER" not in before_tmax
    assert "10*I+2" not in before_tmax


def test_component_topology_maxbeam_uses_type1_equivalent_component(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.14},"metadata":{"square_section_outer_mm":140}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "CM,CTAI_SUPPORT_ELEMS,ELEM",
                "CM,CTAI_ARM_ELEMS,ELEM",
                "CM,CTAI_TRAY_ELEMS,ELEM",
                "CM,CTAI_BOLT_ELEMS,ELEM",
                "CM,CTAI_STRUCTURAL_ELEMS,ELEM",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "/PREP7",
                "ESEL,S,TYPE,,1",
                "*CREATE,MAXBEAMSTRESS-WRITE,MAC",
                "*END",
                "MAXBEAMSTRESS-WRITE",
                "ALLSEL",
                "ESEL,S,TYPE,,1",
                "ESEL,U,SEC,,1",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    audit = align_postprocessor_to_intake(job_dir)
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")
    before_max = text.split("*CREATE,MAXBEAMSTRESS-WRITE,MAC", 1)[0]

    assert audit["maxbeam_selector"]["status"] == "applied"
    assert audit["maxbeam_selector"]["new_selector"] == [
        "CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM",
        "CMSEL,A,CTAI_ARM_ELEMS,ELEM",
    ]
    assert "CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM" in before_max
    assert "CMSEL,A,CTAI_ARM_ELEMS,ELEM" in before_max
    assert "CMSEL,A,CTAI_TRAY_ELEMS,ELEM" not in before_max
    assert "CMSEL,S,CTAI_STRUCTURAL_ELEMS,ELEM" not in before_max
    assert "ESEL,S,TYPE,,1" not in before_max


def test_component_topology_tmax_selector_is_idempotent(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.14},"metadata":{"square_section_outer_mm":140}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "CM,CTAI_SUPPORT_ELEMS,ELEM",
                "CM,CTAI_ARM_ELEMS,ELEM",
                "CM,CTAI_TRAY_ELEMS,ELEM",
                "CM,CTAI_BOLT_ELEMS,ELEM",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "/PREP7",
                "ESEL,S,TYPE,,1",
                "*CREATE,MAXBEAMSTRESS-WRITE,MAC",
                "*END",
                "MAXBEAMSTRESS-WRITE",
                "ALLSEL",
                "ESEL,S,TYPE,,1",
                "ESEL,U,SEC,,1",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    first = align_postprocessor_to_intake(job_dir)
    second = align_postprocessor_to_intake(job_dir)
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")
    before_tmax = text.split("*CREATE,TMAXBEAMSTRESS-WRITE,MAC", 1)[0]

    assert first["tmax_selector"]["replacement_mode"] == "legacy_type1_replaced"
    assert second["tmax_selector"]["replacement_mode"] == "already_aligned"
    assert before_tmax.count("CMSEL,S,CTAI_ARM_ELEMS,ELEM") == 1


def test_component_topology_square_export_keeps_square_support_selector(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.14},"metadata":{"square_section_outer_mm":140}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "CM,CTAI_SUPPORT_ELEMS,ELEM",
                "CM,CTAI_ARM_ELEMS,ELEM",
                "CM,CTAI_TRAY_ELEMS,ELEM",
                "CM,CTAI_BOLT_ELEMS,ELEM",
                "CM,CTAI_STRUCTURAL_ELEMS,ELEM",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "/PREP7",
                "ESEL,S,TYPE,,1",
                "*CREATE,MAXBEAMSTRESS-WRITE,MAC",
                "*CFOPEN,MAXBEAMSTRESS,LIS",
                "*CFCLOS",
                "*END",
                "MAXBEAMSTRESS-WRITE",
                "*IF,H1,LE,0.120001,THEN",
                "ALLSEL",
                "ESEL,S,TYPE,,1",
                "ESEL,U,SEC,,1",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    align_postprocessor_to_intake(job_dir)
    square_audit = augment_square_support_export(job_dir / "generated_post.mac")
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")
    square_block = text.split("*CREATE,SQUAREBEAMSTRESS-WRITE,MAC", 1)[0]
    square_block = square_block.rsplit("! CableTrayAI", 1)[-1]

    assert square_audit["status"] == "added"
    assert square_audit["selector"] == ["CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM"]
    assert "CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM" in square_block
    assert "CMSEL,S,CTAI_STRUCTURAL_ELEMS,ELEM" not in square_block


def test_square_export_does_not_copy_model_or_cloud_figures(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.14},"metadata":{"square_section_outer_mm":140}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "CM,CTAI_SUPPORT_ELEMS,ELEM",
                "CM,CTAI_ARM_ELEMS,ELEM",
                "CM,CTAI_TRAY_ELEMS,ELEM",
                "CM,CTAI_BOLT_ELEMS,ELEM",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "/PREP7",
                "ALLSEL",
                "EPLOT",
                "/image,save,TBMODEL,bmp",
                "/PREP7",
                "ElasM=2.04E11",
                "ESEL,S,TYPE,,1",
                "PLLS,SDIR,SDIR,1,0",
                "/image,save,B1SDIR1,bmp",
                "*CREATE,MAXBEAMSTRESS-WRITE,MAC",
                "*CFOPEN,MAXBEAMSTRESS,LIS",
                "*CFCLOS",
                "*END",
                "MAXBEAMSTRESS-WRITE",
            ]
        ),
        encoding="utf-8",
    )

    align_postprocessor_to_intake(job_dir)
    audit = augment_square_support_export(job_dir / "generated_post.mac")
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")
    create_index = text.index("*CREATE,SQUAREBEAMSTRESS-WRITE,MAC")
    segment_start = text.rfind("/PREP7", 0, create_index)
    call_index = text.index("SQUAREBEAMSTRESS-WRITE", create_index + 1)
    square_segment = text[segment_start:call_index]

    assert audit["removed_plot_commands"] == 2
    assert "TBMODEL" not in square_segment
    assert "EPLOT" not in square_segment
    assert "PLLS" not in square_segment
    assert "/image,save" not in square_segment.lower()
    assert "SQ-" not in square_segment


def test_source_topology_maxbeam_preserves_type1_selector(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        '{"support":{"square_tube_width_m":0.14},"metadata":{"square_section_outer_mm":140}}',
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "LATT,1,,1,,,,1",
                "LATT,1,,1,,,,2",
                "LATT,1,,1,,,,3",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "/PREP7",
                "ESEL,S,TYPE,,1",
                "*CREATE,MAXBEAMSTRESS-WRITE,MAC",
                "*END",
                "ALLSEL",
                "ESEL,S,TYPE,,1",
                "ESEL,U,SEC,,1",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    audit = align_postprocessor_to_intake(job_dir)
    text = (job_dir / "generated_post.mac").read_text(encoding="utf-8")
    before_max = text.split("*CREATE,MAXBEAMSTRESS-WRITE,MAC", 1)[0]

    assert audit["maxbeam_selector"]["status"] == "source_topology_preserved"
    assert "ESEL,S,TYPE,,1" in before_max
    assert "CTAI_STRUCTURAL_ELEMS" not in before_max
