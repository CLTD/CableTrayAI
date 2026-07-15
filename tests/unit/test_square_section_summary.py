from __future__ import annotations

import json
from pathlib import Path

from core.optimizer.square_section_summary import write_square_section_selection_summary


def test_square_section_summary_prefers_formal_overall_ratio(tmp_path: Path) -> None:
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

    assert summary["controlling_ratio"] == 0.22
    assert summary["final_controlling_ratio"] == 0.22
    assert summary["final_section_selection_ratio"] == 0.15
    assert summary["final_chapter6_controlling_ratio"] == 0.22
    assert summary["final_square_support_ratio"] == 0.15
    assert summary["trial_controlling_ratio"] == 0.98
    assert summary["ratio_source"] == "evaluation_summary.json:all deterministic stress ratios"
    assert summary["ratio_consistency_status"] == "formal_override"
    assert summary["status"] == "pass"
    assert summary["selection_acceptance"] == "pass"
    assert summary["is_design_acceptable"] is True
    assert (job_dir / "square_section_selection_summary.json").exists()
    original = json.loads((job_dir / "square_section_selection.json").read_text(encoding="utf-8"))
    assert original["selected"]["section_name"] == "120-120-6"


def test_square_section_summary_uses_formal_ratio_for_legacy_flat_ratio_mismatch(tmp_path: Path) -> None:
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

    assert summary["ratio_consistency_status"] == "formal_override"
    assert summary["status"] == "pass"
    assert summary["selection_acceptance"] == "pass"
    assert summary["is_design_acceptable"] is True


def test_square_section_summary_preserves_job_price_snapshot_without_repricing(tmp_path: Path) -> None:
    job_dir = tmp_path / "priced-job"
    job_dir.mkdir()
    (job_dir / "generated_model.mac").write_text("SECREAD,140-140-8,SECT\n", encoding="utf-8")
    (job_dir / "input.json").write_text("{}", encoding="utf-8")
    (job_dir / "square_section_selection.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "selected": {
                    "section_name": "140-140-8",
                    "controlling_ratio": 0.8,
                    "estimated_square_material_cost_cny_per_m": 130.25,
                    "pricing_status": "approved_active",
                    "price_book_table_id": "UNIT-PRICE-01",
                    "price_book_revision": "R2",
                },
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "evaluation_summary.json").write_text(
        json.dumps([{"check_id": "square_support.support_bending", "ratio": 0.8}]),
        encoding="utf-8",
    )

    summary = write_square_section_selection_summary(job_dir)

    assert summary["estimated_square_material_cost_cny_per_m"] == 130.25
    assert summary["pricing_status"] == "approved_active"
    assert summary["price_book_table_id"] == "UNIT-PRICE-01"
    assert summary["price_book_revision"] == "R2"
