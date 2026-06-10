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
