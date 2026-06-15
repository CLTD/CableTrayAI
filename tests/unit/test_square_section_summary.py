from __future__ import annotations

import json
from pathlib import Path

from core.optimizer.square_section_summary import write_square_section_selection_summary


def test_square_section_summary_prefers_formal_section_6_1_ratio(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "generated_model.mac").write_text("SECREAD,120-120-6,SECT\n", encoding="utf-8")
    (job_dir / "input.json").write_text("{}", encoding="utf-8")
    (job_dir / "square_section_selection.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "selected": {
                    "section_name": "120-120-6",
                    "controlling_ratio": 0.98,
                    "square_support_ratio": 0.98,
                },
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "evaluation_summary.json").write_text(
        json.dumps(
            [
                {
                    "check_id": "square_support.support_bending",
                    "ratio": 0.15,
                },
                {
                    "check_id": "bolt.combination",
                    "ratio": 0.22,
                },
            ]
        ),
        encoding="utf-8",
    )

    summary = write_square_section_selection_summary(job_dir)

    assert summary["controlling_ratio"] == 0.15
    assert summary["final_controlling_ratio"] == 0.15
    assert summary["final_section_selection_ratio"] == 0.15
    assert summary["final_chapter6_controlling_ratio"] == 0.22
    assert summary["final_square_support_ratio"] == 0.15
    assert summary["trial_controlling_ratio"] == 0.98
    assert summary["ratio_source"] == "evaluation_summary.json:Chapter 6.1 structural member ratios"
    assert summary["ratio_consistency_status"] == "fail"
    assert summary["status"] == "fail"
    assert summary["selection_acceptance"] == "fail"
    assert summary["is_design_acceptable"] is False
    assert (job_dir / "square_section_selection_summary.json").exists()
    original = json.loads((job_dir / "square_section_selection.json").read_text(encoding="utf-8"))
    assert original["selected"]["section_name"] == "120-120-6"


def test_square_section_summary_blocks_legacy_flat_ratio_mismatch(tmp_path: Path) -> None:
    job_dir = tmp_path / "legacy-job"
    job_dir.mkdir()
    (job_dir / "generated_model.mac").write_text("SECREAD,120-120-6,SECT\n", encoding="utf-8")
    (job_dir / "input.json").write_text("{}", encoding="utf-8")
    (job_dir / "square_section_selection.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "section_name": "120-120-6",
                "trial_controlling_ratio": 0.9828,
                "final_controlling_ratio": 0.1476,
                "selection_acceptance": "pass",
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "evaluation_summary.json").write_text(
        json.dumps([{"check_id": "square_support.support_bending", "ratio": 0.1476}]),
        encoding="utf-8",
    )

    summary = write_square_section_selection_summary(job_dir)

    assert summary["ratio_consistency_status"] == "fail"
    assert summary["status"] == "fail"
    assert summary["selection_acceptance"] == "fail"
    assert summary["is_design_acceptable"] is False
