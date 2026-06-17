from __future__ import annotations

from pathlib import Path

from core.apdl.postprocessor_alignment import align_postprocessor_to_intake


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
