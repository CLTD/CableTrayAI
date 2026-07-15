from __future__ import annotations

import json
from pathlib import Path

from core.optimizer.support_spacing_recovery import (
    apply_support_spacing_recovery,
    plan_support_spacing_recovery_from_final_ratio,
    plan_support_spacing_recovery_from_selection,
)


def _write_job(job_dir: Path) -> None:
    job_dir.mkdir(parents=True)
    payload = {
        "support": {
            "support_spacing_m": 2.0,
            "support_section_id": "160-160-8",
            "allowed_square_section_ids": ["100-100-8", "140-140-8", "160-160-8"],
        },
        "metadata": {
            "square_section_selection_status": "auto_selected_by_real_ansys",
            "square_section_selected": "160-160-8",
            "square_section_selected_ratio": 1.18,
            "square_section_outer_mm": 160.0,
            "square_section_thickness_mm": 8.0,
        },
        "sections": [{"section_id": "160-160-8", "sect_file": "160-160-8"}],
    }
    (job_dir / "input.json").write_text(json.dumps(payload), encoding="utf-8")


def _write_catalog(source_root: Path) -> None:
    source_root.mkdir(parents=True)
    for section in ("100-100-8", "140-140-8", "160-160-8"):
        (source_root / f"{section}.SECT").write_text("sect", encoding="utf-8")


def test_selection_failure_max_allowed_overlimit_plans_spacing_reduction(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    source_root = tmp_path / "source"
    _write_job(job_dir)
    _write_catalog(source_root)
    selection = {
        "status": "fail",
        "reason": "all allowed failed",
        "candidate_results": [
            {
                "section_name": "160-160-8",
                "status": "fail",
                "run_status": "success",
                "controlling_ratio": 1.18,
                "section_selection_ratio": 1.18,
                "failed_non_ratio_checks": [],
                "diagnosis": {"continue_square_section_search": True},
            }
        ],
    }

    plan = plan_support_spacing_recovery_from_selection(
        job_dir,
        selection,
        source_root=source_root,
        attempt_index=1,
    )

    assert plan["status"] == "pass"
    assert plan["max_allowed_square_section"] == "160-160-8"
    assert plan["current_support_spacing_m"] == 2.0
    assert plan["new_support_spacing_m"] < 2.0
    assert plan["failed_ratio"] == 1.18


def test_selection_failure_does_not_adjust_when_max_allowed_not_evaluated(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    source_root = tmp_path / "source"
    _write_job(job_dir)
    _write_catalog(source_root)

    plan = plan_support_spacing_recovery_from_selection(
        job_dir,
        {
            "status": "fail",
            "candidate_results": [
                {
                    "section_name": "140-140-8",
                    "run_status": "success",
                    "controlling_ratio": 1.2,
                    "failed_non_ratio_checks": [],
                }
            ],
        },
        source_root=source_root,
    )

    assert plan["status"] == "skipped"
    assert plan["reason"] == "maximum_allowed_square_section_was_not_evaluated"


def test_apply_spacing_recovery_resets_square_selection_and_writes_audit(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    source_root = tmp_path / "source"
    _write_job(job_dir)
    _write_catalog(source_root)
    selection = {
        "status": "fail",
        "candidate_results": [
            {
                "section_name": "160-160-8",
                "status": "fail",
                "run_status": "success",
                "controlling_ratio": 1.18,
                "failed_non_ratio_checks": [],
                "diagnosis": {"continue_square_section_search": True},
            }
        ],
    }
    plan = plan_support_spacing_recovery_from_selection(job_dir, selection, source_root=source_root)

    applied = apply_support_spacing_recovery(job_dir, plan)
    payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    history = json.loads((job_dir / "support_spacing_adjustments.json").read_text(encoding="utf-8"))

    assert applied["status"] == "pass"
    assert payload["support"]["support_spacing_m"] == plan["new_support_spacing_m"]
    assert payload["metadata"]["square_section_selection_status"] == "auto_selection_required"
    assert "square_section_selected" not in payload["metadata"]
    assert payload["metadata"]["support_spacing_original_m"] == 2.0
    assert len(history) == 1


def test_final_ratio_recovery_requires_current_section_to_be_max_allowed(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    source_root = tmp_path / "source"
    _write_job(job_dir)
    _write_catalog(source_root)
    payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    payload["metadata"]["square_section_selected"] = "140-140-8"
    payload["support"]["support_section_id"] = "140-140-8"
    (job_dir / "input.json").write_text(json.dumps(payload), encoding="utf-8")
    (job_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "checks": [
                    {
                        "check_id": "evaluation_ratio_limit",
                        "status": "fail",
                        "evidence": [
                            {"check_id": "square_support.bending", "component": "square_support", "ratio": 1.2}
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = plan_support_spacing_recovery_from_final_ratio(job_dir, source_root=source_root)

    assert plan["status"] == "skipped"
    assert plan["reason"] == "current_square_section_is_not_maximum_allowed"


def test_final_ratio_recovery_does_not_reduce_spacing_before_larger_allowed_section(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    source_root = tmp_path / "source"
    _write_job(job_dir)
    _write_catalog(source_root)
    payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    payload["metadata"]["square_section_selected"] = "140-140-8"
    payload["support"]["support_section_id"] = "140-140-8"
    payload["sections"][0]["section_id"] = "140-140-8"
    payload["sections"][0]["sect_file"] = "140-140-8"
    (job_dir / "input.json").write_text(json.dumps(payload), encoding="utf-8")
    (job_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "checks": [
                    {
                        "check_id": "evaluation_ratio_limit",
                        "status": "fail",
                        "evidence": [
                            {
                                "check_id": "cantilever_root_weld_equivalent.accident.bending",
                                "ratio": 1.496,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = plan_support_spacing_recovery_from_final_ratio(job_dir, source_root=source_root)

    assert plan["status"] == "skipped"
    assert plan["reason"] == "current_square_section_is_not_maximum_allowed"
    assert plan["current_square_section"] == "140-140-8"
    assert plan["max_allowed_square_section"] == "160-160-8"


def test_final_ratio_recovery_allows_weld_ratio_when_max_section_is_active(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    source_root = tmp_path / "source"
    _write_job(job_dir)
    _write_catalog(source_root)
    (job_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "checks": [
                    {
                        "check_id": "evaluation_ratio_limit",
                        "status": "fail",
                        "evidence": [
                            {
                                "check_id": "cantilever_root_weld.faulted.equivalent",
                                "ratio": 1.0367,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = plan_support_spacing_recovery_from_final_ratio(job_dir, source_root=source_root, attempt_index=2)

    assert plan["status"] == "pass"
    assert plan["trigger"] == "final_result_ratio_failure"
    assert plan["failed_ratio"] == 1.0367
    assert plan["new_support_spacing_m"] < 2.0
    assert plan["evidence"]["ratio_evidence"] == [
        {"check_id": "cantilever_root_weld.faulted.equivalent", "ratio": 1.0367}
    ]


def test_final_ratio_recovery_normalises_text_allowed_sections_and_sect_suffix(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    source_root = tmp_path / "source"
    _write_job(job_dir)
    _write_catalog(source_root)
    payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    payload["support"]["allowed_square_section_ids"] = "100x8， 140x8; 160x8"
    payload["support"]["support_section_id"] = ""
    payload["metadata"].pop("square_section_selected", None)
    payload["sections"] = [{"section_id": "square", "sect_file": "160-160-8.SECT"}]
    (job_dir / "input.json").write_text(json.dumps(payload), encoding="utf-8")
    (job_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "checks": [
                    {
                        "check_id": "evaluation_ratio_limit",
                        "status": "fail",
                        "evidence": [{"check_id": "weld.faulted.equivalent", "ratio": 1.2}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    plan = plan_support_spacing_recovery_from_final_ratio(job_dir, source_root=source_root)

    assert plan["status"] == "pass"
    assert plan["max_allowed_square_section"] == "160-160-8"
    assert plan["evidence"]["current_square_section"] == "160-160-8"
