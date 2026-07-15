from __future__ import annotations

from pathlib import Path

from core.apdl.result_source_map import extract_result_source_map


def test_component_topology_tmax_maps_to_cantilever_arm(tmp_path: Path) -> None:
    post = tmp_path / "generated_post.mac"
    post.write_text(
        "\n".join(
            [
                "*CREATE,SQUAREBEAMSTRESS-WRITE,MAC",
                "*END",
                "*CREATE,MAXBEAMSTRESS-WRITE,MAC",
                "*END",
                "ALLSEL",
                "CMSEL,S,CTAI_ARM_ELEMS,ELEM",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    payload = extract_result_source_map(post)
    tmax = payload["outputs"]["TMAXBEAMSTRESS.LIS"]

    assert tmax["status"] == "mapped"
    assert tmax["component_scope"] == "ctai_cantilever_arm_component"
    assert tmax["report_component_hint"] == "cantilever_arm"
    assert tmax["selector_commands"] == [{"line": 6, "command": "CMSEL,S,CTAI_ARM_ELEMS,ELEM"}]


def test_component_topology_max_maps_to_type1_equivalent_component(tmp_path: Path) -> None:
    post = tmp_path / "generated_post.mac"
    post.write_text(
        "\n".join(
            [
                "ALLSEL",
                "CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM",
                "*CREATE,SQUAREBEAMSTRESS-WRITE,MAC",
                "*END",
                "ALLSEL",
                "CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM",
                "CMSEL,A,CTAI_ARM_ELEMS,ELEM",
                "*CREATE,MAXBEAMSTRESS-WRITE,MAC",
                "*END",
                "ALLSEL",
                "CMSEL,S,CTAI_ARM_ELEMS,ELEM",
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "*END",
            ]
        ),
        encoding="utf-8",
    )

    payload = extract_result_source_map(post)
    square = payload["outputs"]["SQUAREBEAMSTRESS.LIS"]
    maxbeam = payload["outputs"]["MAXBEAMSTRESS.LIS"]
    tmax = payload["outputs"]["TMAXBEAMSTRESS.LIS"]

    assert square["component_scope"] == "ctai_support_component"
    assert square["report_component_hint"] == "square_support"
    assert maxbeam["component_scope"] == "ctai_type1_component"
    assert maxbeam["report_component_hint"] == "mixed_beam_type_1"
    assert tmax["component_scope"] == "ctai_cantilever_arm_component"
