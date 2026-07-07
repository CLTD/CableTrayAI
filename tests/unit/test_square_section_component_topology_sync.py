from __future__ import annotations

import json
from pathlib import Path

from core.optimizer.square_section_selector import (
    _sync_component_topology_ql3a_to_square_section,
    _sync_topology_manifest_to_square_section,
)


def test_component_topology_ql3a_tracks_selected_square_outer_width(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    model = job_dir / "generated_model.mac"
    model.write_text(
        "\n".join(
            [
                "QCODE(1)=600",
                "QL3A(1)=0.2",
                "QCODE(2)=500",
                "QL3A(2)=0.2",
                "QCODE(3)=300",
                "QL3A(3)=0.15",
                "QCODE(4)=200",
                "QL3A(4)=0.15",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    audit = _sync_component_topology_ql3a_to_square_section(job_dir, "160-160-8")
    text = model.read_text(encoding="utf-8")

    assert audit["status"] == "updated"
    assert audit["updated_count"] == 2
    assert "QL3A(1)=0.15" in text
    assert "QL3A(2)=0.15" in text
    assert "QL3A(3)=0.15" in text
    assert "QL3A(4)=0.15" in text


def test_component_topology_ql3a_keeps_wide_tail_0p20_for_120_square_and_small_tail_0p15(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    model = job_dir / "generated_model.mac"
    model.write_text(
        "\n".join(
            [
                "QCODE(1)=600",
                "QL3A(1)=0.15",
                "QCODE(2)=500",
                "QL3A(2)=0.15",
                "QCODE(3)=300",
                "QL3A(3)=0.2",
                "QCODE(4)=200",
                "QL3A(4)=0.2",
                "QCODE(5)=100",
                "QL3A(5)=0.2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    audit = _sync_component_topology_ql3a_to_square_section(job_dir, "120-120-10")
    text = model.read_text(encoding="utf-8")

    assert audit["status"] == "updated"
    assert audit["updated_count"] == 5
    assert "QL3A(1)=0.2" in text
    assert "QL3A(2)=0.2" in text
    assert "QL3A(3)=0.15" in text
    assert "QL3A(4)=0.15" in text
    assert "QL3A(5)=0.15" in text


def test_topology_manifest_tracks_selected_square_section_and_l3(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    manifest = {
        "components": [
            {"name": "CTAI_SUPPORT_ELEMS", "section": "100-100-8"},
            {"name": "CTAI_ARM_ELEMS", "section": ["50-42", "CAOGANG42DAN"]},
        ],
        "layers": [
            {"model_layer_index": 1, "width_mm": 600, "l3_tail_m": 0.2},
            {"model_layer_index": 2, "width_mm": 300, "l3_tail_m": 0.15},
        ],
    }
    (job_dir / "apdl_topology_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    audit = _sync_topology_manifest_to_square_section(
        job_dir,
        "160-160-8",
        arm_primary="YIXINGGANG150",
        arm_secondary="YIXINGGANG150DAN",
    )
    updated = json.loads((job_dir / "apdl_topology_manifest.json").read_text(encoding="utf-8"))

    assert audit["status"] == "updated"
    assert updated["components"][0]["section"] == "160-160-8"
    assert updated["components"][1]["section"] == ["YIXINGGANG150", "YIXINGGANG150DAN"]
    assert updated["layers"][0]["l3_tail_m"] == 0.15
    assert updated["layers"][0]["l3_tail_policy"] == "wide_tray_square_outer_gt_120_ql3a_0p15m"
    assert updated["square_section_sync"]["section_name"] == "160-160-8"
