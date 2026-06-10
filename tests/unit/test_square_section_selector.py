from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.optimizer.square_section_selector import (
    SquareSectionCandidate,
    candidate_publishable_ratio,
    replace_square_and_arm_sections_in_model,
    run_square_section_search,
    select_best_square_section,
)
from core.validation.analysis_scope import classify_scope_from_input


def _write_minimal_job(job_dir: Path) -> None:
    job_dir.mkdir(parents=True)
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "H1=0.1",
                "SECREAD,100-100-6,SECT",
                "SECREAD,50-42,SECT",
                "SECREAD,CAOGANG42DAN,SECT",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "input.json").write_text("{}", encoding="utf-8")
    (job_dir / "evaluation_summary.json").write_text(
        json.dumps(
            [
                {
                    "check_id": "square_support.old",
                    "ratio": 0.11,
                }
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "result.json").write_text('{"stale": true}', encoding="utf-8")
    (job_dir / "MAXBEAMSTRESS.LIS").write_text("stale lis", encoding="utf-8")
    (job_dir / "MOTAI-1.PNG").write_bytes(b"stale image")
    raw = job_dir / "raw_results"
    raw.mkdir()
    (raw / "Mode.oup").write_text("stale mode", encoding="utf-8")


def test_run_square_section_search_does_not_copy_stale_outputs_into_trials(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("120-120-6", "50-42", "CAOGANG42DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    def runner(trial_dir: Path) -> dict[str, str]:
        assert not (trial_dir / "result.json").exists()
        assert not (trial_dir / "evaluation_summary.json").exists()
        assert not (trial_dir / "MAXBEAMSTRESS.LIS").exists()
        assert not (trial_dir / "MOTAI-1.PNG").exists()
        assert not (trial_dir / "raw_results").exists()
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps(
                [
                    {
                        "check_id": "square_support.fresh",
                        "ratio": 0.93,
                    }
                ]
            ),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": "pass", "checks": [{"check_id": "evaluation_ratio_limit", "status": "pass"}]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="120-120-6",
                outer_mm=120,
                thickness_mm=6,
                source_file=str(source_root / "120-120-6.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
    )

    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "120-120-6"
    assert selection["selected"]["controlling_ratio"] == 0.93
    assert selection["candidate_results"][0]["trial_stale_output_cleanup"]["status"] == "pass"


def test_run_square_section_search_refreshes_existing_trial_by_default(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("120-120-6", "50-42", "CAOGANG42DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    existing_trial = tmp_path / "trials" / "120-120-6"
    existing_trial.mkdir(parents=True)
    (existing_trial / "result_validation.json").write_text(
        json.dumps({"status": "pass", "checks": [{"check_id": "evaluation_ratio_limit", "status": "pass"}]}),
        encoding="utf-8",
    )
    (existing_trial / "evaluation_summary.json").write_text(
        json.dumps([{"check_id": "square_support.stale", "ratio": 0.12}]),
        encoding="utf-8",
    )

    def runner(trial_dir: Path) -> dict[str, str]:
        assert not (trial_dir / "evaluation_summary.json").exists()
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": 0.91}]),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": "pass", "checks": [{"check_id": "evaluation_ratio_limit", "status": "pass"}]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="120-120-6",
                outer_mm=120,
                thickness_mm=6,
                source_file=str(source_root / "120-120-6.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
    )

    assert selection["status"] == "pass"
    assert selection["overwrite_trials"] is True
    assert selection["candidate_results"][0]["run_status"] == "success"
    assert selection["candidate_results"][0]["controlling_ratio"] == 0.91


def test_run_square_section_search_requires_result_validation_by_default(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("120-120-6", "50-42", "CAOGANG42DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    def runner(trial_dir: Path) -> dict[str, str]:
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps(
                [
                    {
                        "check_id": "square_support.fresh",
                        "ratio": 0.93,
                    }
                ]
            ),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="120-120-6",
                outer_mm=120,
                thickness_mm=6,
                source_file=str(source_root / "120-120-6.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
    )

    assert selection["status"] == "fail"
    assert selection["candidate_results"][0]["result_gate_status"] == "missing_validation"
    assert "result_validation" in selection["candidate_results"][0]["diagnosis"]["domains"]


def test_static_square_section_trial_ignores_report_only_modal_frequency_checks(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    (base_job / "input.json").write_text(
        json.dumps({"metadata": {"analysis_method": "static"}}),
        encoding="utf-8",
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("140-140-8", "50-42", "CAOGANG42DAN", "YIXINGGANG150", "YIXINGGANG150DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    def runner(trial_dir: Path) -> dict[str, str]:
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": 0.934}]),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps(
                {
                    "status": "fail",
                    "checks": [
                        {"check_id": "evaluation_ratio_limit", "status": "pass"},
                        {"check_id": "required_file_Mode.oup", "status": "fail"},
                        {"check_id": "modal_frequency_table", "status": "fail"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="140-140-8",
                outer_mm=140,
                thickness_mm=8,
                source_file=str(source_root / "140-140-8.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
    )

    result = selection["candidate_results"][0]
    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "140-140-8"
    assert result["failed_non_ratio_checks"] == []
    assert result["diagnosis"]["domains"] == []
    assert result["diagnosis"]["ignored_trial_only_checks"] == [
        "required_file_Mode.oup",
        "modal_frequency_table",
    ]


def test_response_spectrum_square_section_trial_uses_formal_validation_when_mode_file_missing(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    (base_job / "input.json").write_text(
        json.dumps({"metadata": {"analysis_method": "response_spectrum"}}),
        encoding="utf-8",
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("140-140-8", "50-42", "CAOGANG42DAN", "YIXINGGANG150", "YIXINGGANG150DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    def runner(trial_dir: Path) -> dict[str, str]:
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": 0.934}]),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps(
                {
                    "status": "fail",
                    "checks": [
                        {"check_id": "evaluation_ratio_limit", "status": "pass"},
                        {"check_id": "required_file_Mode.oup", "status": "fail"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="140-140-8",
                outer_mm=140,
                thickness_mm=8,
                source_file=str(source_root / "140-140-8.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
    )

    result = selection["candidate_results"][0]
    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "140-140-8"
    assert selection["selection_validation_mode"] == "formal_full_run_required"
    assert selection["selected"]["formal_validation_required"] is True
    assert result["status"] == "fail"
    assert result["failed_non_ratio_checks"] == ["required_file_Mode.oup"]
    assert result["diagnosis"]["formal_validation_retryable"] is True
    assert result["diagnosis"]["formal_validation_retryable_failed_checks"] == ["required_file_Mode.oup"]
    assert selection["early_stop"]["formal_validation_retryable"] is True


def test_square_section_trial_does_not_formal_fallback_for_spectrum_error(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    (base_job / "input.json").write_text(
        json.dumps({"metadata": {"analysis_method": "response_spectrum"}}),
        encoding="utf-8",
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("140-140-8", "50-42", "CAOGANG42DAN", "YIXINGGANG150", "YIXINGGANG150DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    def runner(trial_dir: Path) -> dict[str, str]:
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": 0.934}]),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps(
                {
                    "status": "fail",
                    "checks": [
                        {"check_id": "evaluation_ratio_limit", "status": "pass"},
                        {"check_id": "spectrum_values", "status": "fail"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="140-140-8",
                outer_mm=140,
                thickness_mm=8,
                source_file=str(source_root / "140-140-8.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
    )

    result = selection["candidate_results"][0]
    assert selection["status"] == "fail"
    assert result["diagnosis"]["formal_validation_retryable"] is False
    assert selection["early_stop"]["formal_validation_retryable"] is False


def test_candidate_ratio_uses_fresh_evaluation_summary_when_validation_ratio_evidence_is_stale(tmp_path: Path) -> None:
    trial_dir = tmp_path / "trial"
    trial_dir.mkdir()
    (trial_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "checks": [
                    {
                        "check_id": "evaluation_ratio_limit",
                        "status": "fail",
                        "evidence": [
                            {
                                "check_id": "stale_square_support",
                                "ratio": 1.01,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = candidate_publishable_ratio(
        trial_dir,
        [
            {"check_id": "square_support.fresh", "ratio": 0.88},
            {"check_id": "weld_force_raw_faulted_weld_equivalent", "ratio": 0.99},
        ],
    )

    assert result["status"] == "pass"
    assert result["controlling_ratio"] == 0.99
    assert result["dominant_check_id"] == "weld_force_raw_faulted_weld_equivalent"
    assert result["validation_ratio_limit_ratio"] == 1.01
    assert result["validation_ratio_limit_status"] == "ignored_for_candidate_ratio_recomputed_from_evaluation_summary"


def test_smart_jump_skips_only_after_failed_square_support_ratio(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    section_names = ("100-100-6", "100-100-8", "120-120-6", "120-120-10", "50-42", "CAOGANG42DAN")
    for section_name in section_names:
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    ratios = {
        "100-100-6": 1.65,
        "120-120-6": 0.82,
        "120-120-10": 0.64,
    }

    def runner(trial_dir: Path) -> dict[str, str]:
        ratio = ratios[trial_dir.name]
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": ratio}]),
            encoding="utf-8",
        )
        status = "fail" if ratio > 1.0 else "pass"
        check = {"check_id": "evaluation_ratio_limit", "status": status}
        if ratio > 1.0:
            check["evidence"] = [{"check_id": "square_support.fresh", "ratio": ratio}]
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": status, "checks": [check]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(section_name="100-100-6", outer_mm=100, thickness_mm=6, source_file=str(source_root / "100-100-6.SECT")),
            SquareSectionCandidate(section_name="100-100-8", outer_mm=100, thickness_mm=8, source_file=str(source_root / "100-100-8.SECT")),
            SquareSectionCandidate(section_name="120-120-6", outer_mm=120, thickness_mm=6, source_file=str(source_root / "120-120-6.SECT")),
            SquareSectionCandidate(section_name="120-120-10", outer_mm=120, thickness_mm=10, source_file=str(source_root / "120-120-10.SECT")),
        ],
        runner=runner,
        source_root=source_root,
        stop_after_first_feasible=False,
        smart_order=False,
        smart_jumps_enabled=True,
    )

    assert selection["economy_corrections"][0]["after_section"] == "100-100-6"
    assert selection["economy_corrections"][0]["direction"] == "larger"
    assert [item["section_name"] for item in selection["candidate_results"]] == [
        "100-100-6",
        "120-120-10",
    ]
    assert selection["selected"]["section_name"] == "120-120-10"


def test_two_trial_economy_search_stops_after_first_economic_ratio(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("100-100-8", "120-120-6", "50-42", "CAOGANG42DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    run_sections: list[str] = []

    def runner(trial_dir: Path) -> dict[str, str]:
        run_sections.append(trial_dir.name)
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": 0.83}]),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": "pass", "checks": [{"check_id": "evaluation_ratio_limit", "status": "pass"}]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(section_name="100-100-8", outer_mm=100, thickness_mm=8, source_file=str(source_root / "100-100-8.SECT")),
            SquareSectionCandidate(section_name="120-120-6", outer_mm=120, thickness_mm=6, source_file=str(source_root / "120-120-6.SECT")),
        ],
        runner=runner,
        source_root=source_root,
        max_evaluated_candidates=2,
    )

    assert run_sections == ["100-100-8"]
    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "100-100-8"
    assert selection["selected_economic_status"] == "economic"
    assert selection["evaluated_candidate_count"] == 1


def test_two_trial_economy_search_uses_one_modulus_correction_after_over_limit(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("100-100-6", "100-100-8", "120-120-6", "140-140-8", "50-42", "CAOGANG42DAN", "YIXINGGANG150", "YIXINGGANG150DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    ratios = {
        "100-100-6": 1.42,
        "140-140-8": 0.78,
    }
    run_sections: list[str] = []
    progress_events: list[dict[str, object]] = []

    def runner(trial_dir: Path) -> dict[str, str]:
        run_sections.append(trial_dir.name)
        ratio = ratios[trial_dir.name]
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": ratio}]),
            encoding="utf-8",
        )
        status = "fail" if ratio > 1.0 else "pass"
        check = {"check_id": "evaluation_ratio_limit", "status": status}
        if ratio > 1.0:
            check["evidence"] = [{"check_id": "square_support.fresh", "ratio": ratio}]
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": status, "checks": [check]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(section_name="100-100-6", outer_mm=100, thickness_mm=6, source_file=str(source_root / "100-100-6.SECT")),
            SquareSectionCandidate(section_name="100-100-8", outer_mm=100, thickness_mm=8, source_file=str(source_root / "100-100-8.SECT")),
            SquareSectionCandidate(section_name="120-120-6", outer_mm=120, thickness_mm=6, source_file=str(source_root / "120-120-6.SECT")),
            SquareSectionCandidate(section_name="140-140-8", outer_mm=140, thickness_mm=8, source_file=str(source_root / "140-140-8.SECT")),
        ],
        runner=runner,
        source_root=source_root,
        max_evaluated_candidates=2,
        progress_callback=progress_events.append,
    )

    assert run_sections == ["100-100-6", "140-140-8"]
    assert progress_events
    assert {event["candidate_count"] for event in progress_events} == {2}
    assert selection["evaluated_candidate_count"] == 2
    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "140-140-8"
    assert selection["economy_corrections"][0]["direction"] == "larger"


def test_overlimit_pair_extends_to_two_larger_allowed_sections(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in (
        "100-100-6",
        "120-120-10",
        "140-140-8",
        "160-160-8",
        "50-42",
        "CAOGANG42DAN",
        "YIXINGGANG150",
        "YIXINGGANG150DAN",
    ):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    ratios = {
        "100-100-6": 1.18,
        "120-120-10": 1.12,
        "160-160-8": 0.91,
    }
    run_sections: list[str] = []
    progress_events: list[dict[str, object]] = []

    def runner(trial_dir: Path) -> dict[str, str]:
        run_sections.append(trial_dir.name)
        ratio = ratios[trial_dir.name]
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": ratio}]),
            encoding="utf-8",
        )
        status = "fail" if ratio > 1.0 else "pass"
        check = {"check_id": "evaluation_ratio_limit", "status": status}
        if ratio > 1.0:
            check["evidence"] = [{"check_id": "square_support.fresh", "ratio": ratio}]
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": status, "checks": [check]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(section_name="100-100-6", outer_mm=100, thickness_mm=6, source_file=str(source_root / "100-100-6.SECT")),
            SquareSectionCandidate(section_name="120-120-10", outer_mm=120, thickness_mm=10, source_file=str(source_root / "120-120-10.SECT")),
            SquareSectionCandidate(section_name="140-140-8", outer_mm=140, thickness_mm=8, source_file=str(source_root / "140-140-8.SECT")),
            SquareSectionCandidate(section_name="160-160-8", outer_mm=160, thickness_mm=8, source_file=str(source_root / "160-160-8.SECT")),
        ],
        runner=runner,
        source_root=source_root,
        max_evaluated_candidates=2,
        progress_callback=progress_events.append,
    )

    assert run_sections == ["100-100-6", "120-120-10", "160-160-8"]
    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "160-160-8"
    assert selection["evaluated_candidate_count"] == 3
    assert selection["max_evaluated_candidates"] == 2
    assert selection["effective_evaluated_candidate_budget"] == 4
    assert selection["overlimit_recovery_extensions"]
    assert selection["overlimit_recovery_extensions"][0]["overlimit_sections"] == ["100-100-6", "120-120-10"]
    assert 2 in {event["candidate_count"] for event in progress_events}
    assert 4 in {event["candidate_count"] for event in progress_events}


def test_low_ratio_recovery_candidate_downshifts_one_allowed_section(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in (
        "100-100-6",
        "120-120-10",
        "140-140-8",
        "160-160-8",
        "50-42",
        "CAOGANG42DAN",
        "YIXINGGANG150",
        "YIXINGGANG150DAN",
    ):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    ratios = {
        "100-100-6": 1.35,
        "120-120-10": 1.64,
        "160-160-8": 0.613,
        "140-140-8": 0.82,
    }
    run_sections: list[str] = []

    def runner(trial_dir: Path) -> dict[str, str]:
        run_sections.append(trial_dir.name)
        ratio = ratios[trial_dir.name]
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": ratio}]),
            encoding="utf-8",
        )
        status = "fail" if ratio > 1.0 else "pass"
        check = {"check_id": "evaluation_ratio_limit", "status": status}
        if ratio > 1.0:
            check["evidence"] = [{"check_id": "square_support.fresh", "ratio": ratio}]
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": status, "checks": [check]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(section_name="100-100-6", outer_mm=100, thickness_mm=6, source_file=str(source_root / "100-100-6.SECT")),
            SquareSectionCandidate(section_name="120-120-10", outer_mm=120, thickness_mm=10, source_file=str(source_root / "120-120-10.SECT")),
            SquareSectionCandidate(section_name="140-140-8", outer_mm=140, thickness_mm=8, source_file=str(source_root / "140-140-8.SECT")),
            SquareSectionCandidate(section_name="160-160-8", outer_mm=160, thickness_mm=8, source_file=str(source_root / "160-160-8.SECT")),
        ],
        runner=runner,
        source_root=source_root,
        max_evaluated_candidates=2,
    )

    assert run_sections == ["100-100-6", "120-120-10", "160-160-8", "140-140-8"]
    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "140-140-8"
    assert selection["evaluated_candidate_count"] == 4
    assert selection["effective_evaluated_candidate_budget"] == 4
    assert selection["economy_corrections"][-1]["direction"] == "smaller"
    assert selection["economy_corrections"][-1]["after_section"] == "160-160-8"
    assert selection["economy_corrections"][-1]["next_section"] == "140-140-8"


def test_low_ratio_downshift_keeps_larger_section_when_lower_section_fails(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in (
        "100-100-6",
        "120-120-10",
        "140-140-8",
        "160-160-8",
        "50-42",
        "CAOGANG42DAN",
        "YIXINGGANG150",
        "YIXINGGANG150DAN",
    ):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    ratios = {
        "100-100-6": 1.35,
        "120-120-10": 1.64,
        "160-160-8": 0.613,
        "140-140-8": 1.11,
    }
    run_sections: list[str] = []

    def runner(trial_dir: Path) -> dict[str, str]:
        run_sections.append(trial_dir.name)
        ratio = ratios[trial_dir.name]
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": ratio}]),
            encoding="utf-8",
        )
        status = "fail" if ratio > 1.0 else "pass"
        check = {"check_id": "evaluation_ratio_limit", "status": status}
        if ratio > 1.0:
            check["evidence"] = [{"check_id": "square_support.fresh", "ratio": ratio}]
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": status, "checks": [check]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(section_name="100-100-6", outer_mm=100, thickness_mm=6, source_file=str(source_root / "100-100-6.SECT")),
            SquareSectionCandidate(section_name="120-120-10", outer_mm=120, thickness_mm=10, source_file=str(source_root / "120-120-10.SECT")),
            SquareSectionCandidate(section_name="140-140-8", outer_mm=140, thickness_mm=8, source_file=str(source_root / "140-140-8.SECT")),
            SquareSectionCandidate(section_name="160-160-8", outer_mm=160, thickness_mm=8, source_file=str(source_root / "160-160-8.SECT")),
        ],
        runner=runner,
        source_root=source_root,
        max_evaluated_candidates=2,
    )

    assert run_sections == ["100-100-6", "120-120-10", "160-160-8", "140-140-8"]
    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "160-160-8"
    assert selection["selected"]["controlling_ratio"] == 0.613
    assert selection["candidate_results"][-1]["section_name"] == "140-140-8"
    assert selection["candidate_results"][-1]["status"] == "fail"


def test_select_best_square_section_chooses_minimum_when_all_feasible_are_low_utilization() -> None:
    selection = select_best_square_section(
        [
            {
                "section_name": "100-100-6",
                "status": "pass",
                "controlling_ratio": 0.18,
                "estimated_bending_section_modulus_mm3": 100.0,
                "estimated_area_mm2": 50.0,
            },
            {
                "section_name": "100-100-8",
                "status": "pass",
                "controlling_ratio": 0.45,
                "estimated_bending_section_modulus_mm3": 140.0,
                "estimated_area_mm2": 70.0,
            },
            {
                "section_name": "120-120-6",
                "status": "pass",
                "controlling_ratio": 0.58,
                "estimated_bending_section_modulus_mm3": 220.0,
                "estimated_area_mm2": 90.0,
            },
        ]
    )

    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "100-100-6"
    assert "light-duty row" in selection["policy"]
    assert selection["selected_economic_status"] == "below_economic_range"


def test_select_best_square_section_chooses_closest_to_one_when_economy_target_is_available() -> None:
    selection = select_best_square_section(
        [
            {
                "section_name": "100-100-6",
                "status": "fail",
                "controlling_ratio": 1.12,
                "estimated_bending_section_modulus_mm3": 100.0,
                "estimated_area_mm2": 50.0,
            },
            {
                "section_name": "100-100-8",
                "status": "pass",
                "controlling_ratio": 0.72,
                "estimated_bending_section_modulus_mm3": 140.0,
                "estimated_area_mm2": 70.0,
            },
            {
                "section_name": "120-120-6",
                "status": "pass",
                "controlling_ratio": 0.96,
                "estimated_bending_section_modulus_mm3": 220.0,
                "estimated_area_mm2": 90.0,
            },
            {
                "section_name": "140-140-8",
                "status": "pass",
                "controlling_ratio": 0.81,
                "estimated_bending_section_modulus_mm3": 360.0,
                "estimated_area_mm2": 120.0,
            },
        ]
    )

    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "120-120-6"
    assert "0.60 <= ratio <= 0.9999" in selection["policy"]


def test_select_best_square_section_accepts_exact_limit_ratio() -> None:
    selection = select_best_square_section(
        [
            {
                "section_name": "160-160-8",
                "status": "pass",
                "controlling_ratio": 1.0,
                "estimated_bending_section_modulus_mm3": 400.0,
                "estimated_area_mm2": 150.0,
            }
        ]
    )

    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "160-160-8"
    assert selection["selected"]["controlling_ratio"] == 1.0


def _write_section_sources(source_root: Path) -> None:
    source_root.mkdir()
    for section_name in ("100-100-6", "120-120-6", "50-42", "CAOGANG42DAN", "500-75-2mm"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")


def _write_job_with_required_tray(job_dir: Path, model_text: str) -> None:
    job_dir.mkdir(parents=True)
    (job_dir / "input.json").write_text(
        json.dumps(
            {
                "sections": [
                    {"section_id": "square", "sect_file": "100-100-6.SECT"},
                    {"section_id": "tray-500", "sect_file": "500-75-2mm.SECT"},
                ],
                "tray_layers": [{"tray_width_m": 0.5, "tray_section_id": "tray-500"}],
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_model.mac").write_text(model_text, encoding="utf-8")


def test_square_section_replacement_preserves_intake_tray_secreads(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_section_sources(source_root)
    job_dir = tmp_path / "job"
    _write_job_with_required_tray(
        job_dir,
        "\n".join(
            [
                "SECREAD,100-100-6,SECT",
                "SECREAD,50-42,SECT",
                "SECREAD,CAOGANG42DAN,SECT",
                "SECREAD,500-75-2mm,SECT",
            ]
        ),
    )

    audit = replace_square_and_arm_sections_in_model(job_dir, "120-120-6", source_root=source_root)

    text = (job_dir / "generated_model.mac").read_text(encoding="utf-8")
    assert "500-75-2mm" in text
    assert audit["tray_section_preservation_audit"]["status"] == "pass"


def test_square_section_replacement_fails_when_input_tray_section_is_missing(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_section_sources(source_root)
    job_dir = tmp_path / "job"
    _write_job_with_required_tray(
        job_dir,
        "\n".join(
            [
                "SECREAD,100-100-6,SECT",
                "SECREAD,50-42,SECT",
                "SECREAD,CAOGANG42DAN,SECT",
            ]
        ),
    )

    with pytest.raises(ValueError, match="500-75-2mm"):
        replace_square_and_arm_sections_in_model(job_dir, "120-120-6", source_root=source_root)


def test_candidate_trial_syncs_input_and_post_branch_before_runner(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    base_job.mkdir()
    (base_job / "generated_model.mac").write_text(
        "\n".join(
            [
                "SECREAD,100-100-8,SECT",
                "SECREAD,50-42,SECT",
                "SECREAD,CAOGANG42DAN,SECT",
                "SECREAD,500-75-2mm,SECT",
            ]
        ),
        encoding="utf-8",
    )
    (base_job / "generated_post.mac").write_text(
        "\n".join(
            [
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "ALLSEL",
                "*END",
            ]
        ),
        encoding="utf-8",
    )
    (base_job / "input.json").write_text(
        json.dumps(
            {
                "project": {"description": "双侧3+3层500"},
                "support": {
                    "support_type": "S2",
                    "support_section_id": "100-100-8",
                    "square_tube_width_m": 0.1,
                },
                "sections": [
                    {"section_id": "100-100-8", "sect_file": "100-100-8"},
                    {"section_id": "arm-main", "sect_file": "50-42"},
                    {"section_id": "arm-secondary", "sect_file": "CAOGANG42DAN"},
                    {"section_id": "tray-500", "sect_file": "500-75-2mm"},
                ],
                "tray_layers": [{"tray_width_m": 0.5, "tray_section_id": "tray-500"}],
                "metadata": {
                    "analysis_method": "response_spectrum",
                    "square_section_selection_status": "auto_selected_by_real_ansys",
                    "square_section_selected": "140-140-8",
                    "square_section_selected_ratio": 0.91,
                    "square_section_current_model_spec": "140-140-8",
                    "square_section_outer_mm": 100.0,
                    "square_section_thickness_mm": 8.0,
                    "tray_load_description": "双侧3+3层500",
                },
            }
        ),
        encoding="utf-8",
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("120-120-6", "50-42", "CAOGANG42DAN", "500-75-2mm"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    def runner(trial_dir: Path) -> dict[str, str]:
        payload = json.loads((trial_dir / "input.json").read_text(encoding="utf-8"))
        assert payload["support"]["support_section_id"] == "120-120-6"
        assert payload["support"]["square_tube_width_m"] == pytest.approx(0.12)
        assert payload["metadata"]["square_section_current_model_spec"] == "120-120-6"
        assert payload["metadata"]["square_section_outer_mm"] == 120.0
        assert payload["metadata"]["square_section_thickness_mm"] == 6.0
        assert payload["metadata"]["square_section_selection_status"] == "candidate_input_synced"
        assert "square_section_selected" not in payload["metadata"]
        assert "square_section_selected_ratio" not in payload["metadata"]
        scope = classify_scope_from_input(payload)
        assert scope["appendix_c_mode"] == "cantilever_stress_cloud"
        assert scope["requires"]["cantilever_root_weld_equivalent_stress_table"] is True
        scope_file = json.loads((trial_dir / "analysis_scope.json").read_text(encoding="utf-8"))
        assert scope_file["square_outer_width_mm"] == 120.0
        assert scope_file["appendix_c_mode"] == "cantilever_stress_cloud"
        post_text = (trial_dir / "generated_post.mac").read_text(encoding="utf-8")
        assert "H1=0.120000" in post_text
        assert "H2=0.006000" in post_text
        model_text = (trial_dir / "generated_model.mac").read_text(encoding="utf-8")
        assert "H1=0.120000" in model_text
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": 0.96}]),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": "pass", "checks": [{"check_id": "evaluation_ratio_limit", "status": "pass"}]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="120-120-6",
                outer_mm=120,
                thickness_mm=6,
                source_file=str(source_root / "120-120-6.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
    )

    audit = selection["candidate_results"][0]["trial_section_replace_audit"]["trial_input_sync_audit"]
    assert selection["status"] == "pass"
    assert audit["status"] == "pass"
    assert audit["postprocessor_alignment"]["branch_parameters"]["H1_m"] == pytest.approx(0.12)
    assert selection["candidate_results"][0]["trial_section_replace_audit"]["model_h1_sync_audit"]["H1_m"] == pytest.approx(0.12)


def test_model_h1_tracks_square_outer_width_not_thickness(tmp_path: Path) -> None:
    base_job = tmp_path / "base"
    _write_minimal_job(base_job)
    (base_job / "generated_post.mac").write_text(
        "\n".join(
            [
                "*CREATE,TMAXBEAMSTRESS-WRITE,MAC",
                "ALLSEL",
                "*END",
            ]
        ),
        encoding="utf-8",
    )
    source_root = tmp_path / "source"
    source_root.mkdir()
    for section_name in ("120-120-8", "50-42", "CAOGANG42DAN"):
        (source_root / f"{section_name}.SECT").write_text("sect", encoding="utf-8")

    def runner(trial_dir: Path) -> dict[str, str]:
        model_text = (trial_dir / "generated_model.mac").read_text(encoding="utf-8")
        post_text = (trial_dir / "generated_post.mac").read_text(encoding="utf-8")
        payload = json.loads((trial_dir / "input.json").read_text(encoding="utf-8"))
        assert "H1=0.120000" in model_text
        assert "H1=0.120000" in post_text
        assert "H2=0.008000" in post_text
        assert payload["support"]["square_tube_width_m"] == pytest.approx(0.12)
        (trial_dir / "evaluation_summary.json").write_text(
            json.dumps([{"check_id": "square_support.fresh", "ratio": 0.82}]),
            encoding="utf-8",
        )
        (trial_dir / "result_validation.json").write_text(
            json.dumps({"status": "pass", "checks": [{"check_id": "evaluation_ratio_limit", "status": "pass"}]}),
            encoding="utf-8",
        )
        return {"status": "success"}

    selection = run_square_section_search(
        base_job,
        tmp_path / "trials",
        candidates=[
            SquareSectionCandidate(
                section_name="120-120-8",
                outer_mm=120,
                thickness_mm=8,
                source_file=str(source_root / "120-120-8.SECT"),
            )
        ],
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
    )

    assert selection["status"] == "pass"
    assert selection["selected"]["section_name"] == "120-120-8"
