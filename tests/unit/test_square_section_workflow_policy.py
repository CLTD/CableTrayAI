from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from core.optimizer import square_section_workflow as workflow
from core.optimizer.square_section_selector import SquareSectionCandidate, replace_square_and_arm_sections_in_model


def _write_job(job_dir: Path, *, allowed: list[str] | None) -> None:
    job_dir.mkdir(parents=True)
    payload = {
        "metadata": {
            "square_section_selection_status": "auto_selection_required",
            "analysis_method": "response_spectrum",
        },
        "support": {
            "allowed_square_section_ids": allowed or [],
        },
        "sections": [{"section_id": "square", "sect_file": "100-100-6"}],
        "tray_layers": [{"width_mm": 500, "load_kg_m": 90.5}],
    }
    (job_dir / "input.json").write_text(json.dumps(payload), encoding="utf-8")


def _candidates() -> list[SquareSectionCandidate]:
    return [
        SquareSectionCandidate(section_name="100-100-6", outer_mm=100, thickness_mm=6, source_file="100-100-6.SECT"),
        SquareSectionCandidate(section_name="100-100-8", outer_mm=100, thickness_mm=8, source_file="100-100-8.SECT"),
        SquareSectionCandidate(section_name="120-120-6", outer_mm=120, thickness_mm=6, source_file="120-120-6.SECT"),
        SquareSectionCandidate(section_name="120-120-8", outer_mm=120, thickness_mm=8, source_file="120-120-8.SECT"),
        SquareSectionCandidate(section_name="120-120-10", outer_mm=120, thickness_mm=10, source_file="120-120-10.SECT"),
        SquareSectionCandidate(section_name="140-140-8", outer_mm=140, thickness_mm=8, source_file="140-140-8.SECT"),
        SquareSectionCandidate(section_name="160-160-8", outer_mm=160, thickness_mm=8, source_file="160-160-8.SECT"),
    ]


def _write_minimal_model_with_sections(job_dir: Path) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "SECREAD,100-100-6,SECT",
                "SECREAD,PLACEHOLDER-ARM-A,SECT",
                "SECREAD,PLACEHOLDER-ARM-B,SECT",
            ]
        ),
        encoding="utf-8",
    )


def _write_section_catalog(source_root: Path, names: list[str]) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (source_root / f"{name}.SECT").write_text("! test sect\n", encoding="utf-8")


def test_trial_section_replacement_uses_same_arm_branch_as_final_model(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_section_catalog(
        source_root,
        [
            "120-120-6",
            "140-140-8",
            "50-42",
            "CAOGANG42DAN",
            "YIXINGGANG150",
            "YIXINGGANG150DAN",
        ],
    )

    standard_job = tmp_path / "standard"
    _write_minimal_model_with_sections(standard_job)
    standard_audit = replace_square_and_arm_sections_in_model(standard_job, "120-120-6", source_root=source_root)
    standard_text = (standard_job / "generated_model.mac").read_text(encoding="utf-8")

    assert standard_audit["arm_section_family"] == "square_le_120_standard_channel_family"
    assert "SECREAD,120-120-6,SECT" in standard_text
    assert "SECREAD,50-42,SECT" in standard_text
    assert "SECREAD,CAOGANG42DAN,SECT" in standard_text

    shaped_job = tmp_path / "shaped"
    _write_minimal_model_with_sections(shaped_job)
    shaped_audit = replace_square_and_arm_sections_in_model(shaped_job, "140-140-8", source_root=source_root)
    shaped_text = (shaped_job / "generated_model.mac").read_text(encoding="utf-8")

    assert shaped_audit["arm_section_family"] == "square_gt_120_yixing_arm_family"
    assert "SECREAD,140-140-8,SECT" in shaped_text
    assert "SECREAD,YIXINGGANG150,SECT" in shaped_text
    assert "SECREAD,YIXINGGANG150DAN,SECT" in shaped_text


def test_yixing_trial_replacement_removes_channel_secondary_offset(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_section_catalog(
        source_root,
        [
            "120-120-6",
            "140-140-8",
            "50-42",
            "CAOGANG42DAN",
            "YIXINGGANG150",
            "YIXINGGANG150DAN",
        ],
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "SECREAD,100-100-6,SECT",
                "SECOFFSET,cent,",
                "SECREAD,50-42,SECT",
                "SECOFFSET,user,,-0.03249",
                "SECREAD,CAOGANG42DAN,SECT",
            ]
        ),
        encoding="utf-8",
    )

    audit = replace_square_and_arm_sections_in_model(job_dir, "140-140-8", source_root=source_root)
    text = (job_dir / "generated_model.mac").read_text(encoding="utf-8")

    assert audit["arm_section_family"] == "square_gt_120_yixing_arm_family"
    assert audit["arm_section_replace_audit"]["yixing_secoffset_replacements"] == 1
    assert "SECOFFSET,user,,-0.03249\nSECREAD,YIXINGGANG150DAN" not in text
    assert "SECOFFSET,user\nSECREAD,YIXINGGANG150DAN" in text


def test_channel_trial_replacement_keeps_channel_secondary_offset(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_section_catalog(
        source_root,
        [
            "120-120-6",
            "50-42",
            "CAOGANG42DAN",
        ],
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "SECREAD,100-100-6,SECT",
                "SECOFFSET,cent,",
                "SECREAD,50-42,SECT",
                "SECOFFSET,user,,-0.03249",
                "SECREAD,CAOGANG42DAN,SECT",
            ]
        ),
        encoding="utf-8",
    )

    audit = replace_square_and_arm_sections_in_model(job_dir, "120-120-6", source_root=source_root)
    text = (job_dir / "generated_model.mac").read_text(encoding="utf-8")

    assert audit["arm_section_family"] == "square_le_120_standard_channel_family"
    assert audit["arm_section_replace_audit"]["yixing_secoffset_replacements"] == 0
    assert "SECOFFSET,user,,-0.03249\nSECREAD,CAOGANG42DAN" in text


def test_trial_section_replacement_does_not_overwrite_tray_secreads(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_section_catalog(
        source_root,
        [
            "100-100-8",
            "500-75-2mm",
            "50-42",
            "CAOGANG42DAN",
        ],
    )
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "generated_model.mac").write_text(
        "\n".join(
            [
                "SECREAD,100-100-6,SECT",
                "SECREAD,500-75-2mm,SECT",
                "SECREAD,500-75-2mm,SECT",
                "SECREAD,CAOGANG42DAN,SECT",
            ]
        ),
        encoding="utf-8",
    )

    audit = replace_square_and_arm_sections_in_model(job_dir, "100-100-8", source_root=source_root)
    text = (job_dir / "generated_model.mac").read_text(encoding="utf-8")

    assert audit["status"] == "pass"
    assert "SECREAD,100-100-8,SECT" in text
    assert text.count("SECREAD,500-75-2mm,SECT") == 2
    assert "SECREAD,50-42,SECT" not in text
    assert "SECREAD,CAOGANG42DAN,SECT" in text


def test_apply_selected_square_section_records_formal_validation_mode(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _write_section_catalog(
        source_root,
        [
            "140-140-8",
            "YIXINGGANG150",
            "YIXINGGANG150DAN",
        ],
    )
    job_dir = tmp_path / "job"
    _write_job(job_dir, allowed=["140-140-8"])
    _write_minimal_model_with_sections(job_dir)
    selection = {
        "status": "pass",
        "selection_validation_mode": "formal_full_run_required",
        "policy": "test formal fallback",
        "selected": {
            "section_name": "140-140-8",
            "controlling_ratio": 0.91,
            "formal_validation_required": True,
        },
    }

    audit = workflow.apply_selected_square_section(job_dir, selection, source_root=source_root)
    payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    metadata = payload["metadata"]

    assert audit["status"] == "pass"
    assert metadata["square_section_selection_validation_mode"] == "formal_full_run_required"
    assert metadata["square_section_selection_requires_formal_validation"] is True
    assert metadata["square_section_selected"] == "140-140-8"


def test_allowed_square_sections_use_verified_smart_search_without_unlisted_sections(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(
        job_dir,
        allowed=["100-100-6", "100-100-8", "120-120-6", "120-120-10", "140-140-8", "160-160-8"],
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(workflow, "apply_selected_square_section", lambda *args, **kwargs: {"status": "pass"})

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "pass",
            "selected": {"section_name": "100-100-8", "controlling_ratio": 0.91},
            "candidate_results": [
                {"section_name": "100-100-6", "status": "pass", "controlling_ratio": 0.42},
                {"section_name": "100-100-8", "status": "pass", "controlling_ratio": 0.91},
                {"section_name": "120-120-6", "status": "pass", "controlling_ratio": 0.63},
                {"section_name": "120-120-10", "status": "pass", "controlling_ratio": 0.68},
                {"section_name": "140-140-8", "status": "pass", "controlling_ratio": 0.74},
                {"section_name": "160-160-8", "status": "pass", "controlling_ratio": 0.58},
            ],
            "policy": "test",
        }

    monkeypatch.setattr(workflow, "run_square_section_search", fake_search)

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        runner=lambda trial_dir: {"status": "pass"},
    )

    assert result["status"] == "pass"
    captured_names = [candidate.section_name for candidate in captured["candidates"]]
    assert captured_names == ["100-100-6", "100-100-8", "120-120-6", "120-120-10", "140-140-8", "160-160-8"]
    assert "120-120-8" not in captured_names
    assert captured["stop_after_first_feasible"] is True
    assert captured["feasible_confirmation_count"] == 1
    assert captured["smart_jumps_enabled"] is True
    assert captured["smart_order"] is True
    assert captured["lower_neighbor_count"] == 0
    assert captured["limit"] is None
    assert captured["max_evaluated_candidates"] == 2
    assert captured["overwrite_trials"] is True


def test_successful_square_section_selection_retains_trial_root(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(job_dir, allowed=["140-140-8"])

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(workflow, "apply_selected_square_section", lambda *args, **kwargs: {"status": "pass"})

    def fake_search(base_job_dir, trial_root, *args, **kwargs):
        trial_root = Path(trial_root)
        trial_dir = trial_root / "140-140-8"
        trial_dir.mkdir(parents=True)
        (trial_dir / "ansys_live_status.json").write_text('{"stage":"finished"}', encoding="utf-8")
        return {
            "status": "pass",
            "selected": {
                "section_name": "140-140-8",
                "controlling_ratio": 0.91,
                "trial_dir": str(trial_dir),
            },
            "candidate_results": [
                {
                    "section_name": "140-140-8",
                    "status": "pass",
                    "controlling_ratio": 0.91,
                    "trial_dir": str(trial_dir),
                }
            ],
            "policy": "test",
        }

    monkeypatch.setattr(workflow, "run_square_section_search", fake_search)

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        runner=lambda trial_dir: {"status": "pass"},
    )
    summary = json.loads((job_dir / "square_section_trial_summary.json").read_text(encoding="utf-8"))
    trial_root = Path(result["trial_root"])

    assert result["status"] == "pass"
    assert trial_root.exists()
    assert (trial_root / "140-140-8" / "ansys_live_status.json").exists()
    assert summary["trial_root_removed"] is False
    assert "retained" in summary["trial_root_retention_policy"]


def test_real_ansys_section_trial_runner_forwards_live_progress(tmp_path: Path, monkeypatch) -> None:
    trial_dir = tmp_path / "160-160-8"
    trial_dir.mkdir()
    events: list[dict] = []

    monkeypatch.setattr(workflow, "cleanup_stale_ansys_locks", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(workflow, "_section_trial_config", lambda config: config)
    monkeypatch.setattr(workflow, "assemble_result", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(workflow, "cleanup_heavy_solver_artifacts", lambda *args, **kwargs: {"status": "pass"})

    def fake_run_real_ansys(*args, **kwargs):
        kwargs["progress_callback"](
            {
                "stage": "running_ansys",
                "elapsed_seconds": 125.0,
                "total_output_bytes": 2 * 1024 * 1024,
            }
        )
        return {"status": "success"}

    monkeypatch.setattr(workflow, "run_real_ansys", fake_run_real_ansys)

    result = workflow.real_ansys_section_trial_runner(
        trial_dir,
        config=SimpleNamespace(),
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        progress_callback=events.append,
    )

    assert result["status"] == "pass"
    assert events
    assert events[0]["candidate_section"] == "160-160-8"
    assert events[0]["trial_dir"] == str(trial_dir)
    assert events[0]["trial_status_file"].endswith("ansys_live_status.json")


def test_allowed_square_sections_ignore_similar_cache_window_and_keep_smaller_candidates(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(job_dir, allowed=["100-100-6", "100-100-8", "120-120-6"])
    captured: dict[str, object] = {}

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(workflow, "apply_selected_square_section", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(
        workflow,
        "_read_similar_cached_selection",
        lambda *args, **kwargs: {
            "status": "hit",
            "selected_section_hint": "120-120-6",
            "similarity": {"score": 1.0},
        },
    )

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "pass",
            "selected": {"section_name": "100-100-6", "controlling_ratio": 0.52},
            "candidate_results": [{"section_name": "100-100-6", "status": "pass", "controlling_ratio": 0.52}],
            "policy": "test",
        }

    monkeypatch.setattr(workflow, "run_square_section_search", fake_search)

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        runner=lambda trial_dir: {"status": "pass"},
        cache_path=tmp_path / "cache.json",
    )

    assert result["status"] == "pass"
    captured_names = [candidate.section_name for candidate in captured["candidates"]]
    assert captured_names == ["100-100-6", "100-100-8", "120-120-6"]
    assert captured["stop_after_first_feasible"] is True
    assert captured["smart_order"] is True
    assert captured["smart_jumps_enabled"] is True
    assert captured["max_evaluated_candidates"] == 2


def test_allowed_square_sections_use_learned_start_inside_allowed_list(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(
        job_dir,
        allowed=["100-100-6", "100-100-8", "120-120-6", "120-120-10", "140-140-8", "160-160-8"],
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(workflow, "apply_selected_square_section", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(
        workflow,
        "_read_similar_cached_selection",
        lambda *args, **kwargs: {
            "status": "hit",
            "selected_section_hint": "140-140-8",
            "source_job_dir": "jobs/history/similar_row",
            "cache_key": "similar-cache-key",
            "similarity": {"score": 0.97},
            "historical_candidate_results": [
                {"section_name": "100-100-8", "status": "fail", "controlling_ratio": 1.07},
                {"section_name": "140-140-8", "status": "pass", "controlling_ratio": 0.91},
            ],
        },
    )

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "pass",
            "selected": {"section_name": "140-140-8", "controlling_ratio": 0.91},
            "candidate_results": [
                {"section_name": "120-120-6", "status": "fail", "controlling_ratio": 1.2},
                {"section_name": "120-120-10", "status": "fail", "controlling_ratio": 1.05},
                {"section_name": "140-140-8", "status": "pass", "controlling_ratio": 0.91},
            ],
            "policy": "test",
        }

    monkeypatch.setattr(workflow, "run_square_section_search", fake_search)

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        runner=lambda trial_dir: {"status": "pass"},
        cache_path=tmp_path / "cache.json",
    )

    assert result["status"] == "pass"
    assert [candidate.section_name for candidate in captured["candidates"]] == [
        "100-100-6",
        "100-100-8",
        "120-120-6",
        "120-120-10",
        "140-140-8",
        "160-160-8",
    ]
    assert "120-120-8" not in [candidate.section_name for candidate in captured["candidates"]]
    assert result["learned_allowed_section_start"]["status"] == "applied"
    assert result["learned_allowed_section_start"]["skipped_lower_allowed_sections"] == [
        "100-100-6",
        "100-100-8",
    ]
    assert result["learned_allowed_section_start"]["selected_section_hint"] == "140-140-8"
    assert captured["stop_after_first_feasible"] is True
    assert captured["smart_order"] is True


def test_high_similarity_learned_selection_can_skip_duplicate_downshift_trial(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(
        job_dir,
        allowed=["100-100-6", "100-100-8", "120-120-6", "120-120-10", "140-140-8", "160-160-8"],
    )
    applied: dict[str, object] = {}

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(
        workflow,
        "_read_similar_cached_selection",
        lambda *args, **kwargs: {
            "status": "hit",
            "selected_section_hint": "160-160-8",
            "source_job_dir": "jobs/history/4211",
            "cache_key": "similar-cache-key",
            "similarity": {"score": 1.0},
            "historical_candidate_results": [
                {
                    "section_name": "160-160-8",
                    "status": "pass",
                    "run_status": "pass",
                    "controlling_ratio": 0.6125,
                    "dominant_check_id": "weld_force_raw_faulted_weld_equivalent",
                },
                {
                    "section_name": "140-140-8",
                    "status": "fail",
                    "run_status": "pass",
                    "controlling_ratio": 1.113,
                    "dominant_check_id": "mixed_beam_type_1.support_tension_bending_combined_accident",
                },
            ],
        },
    )
    monkeypatch.setattr(
        workflow,
        "run_square_section_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("duplicate candidate trials should be skipped")),
    )

    def fake_apply(job_dir_arg, selection, **kwargs):
        applied.update(selection)
        return {"status": "pass"}

    monkeypatch.setattr(workflow, "apply_selected_square_section", fake_apply)

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        cache_path=tmp_path / "cache.json",
    )

    assert result["status"] == "pass"
    assert result["selection_validation_mode"] == "learned_formal_validation"
    assert result["selected"]["section_name"] == "160-160-8"
    assert result["learned_formal_validation"]["lower_economy_check"]["status"] == "pass"
    assert applied["selected"]["section_name"] == "160-160-8"
    summary = json.loads((job_dir / "square_section_trial_summary.json").read_text(encoding="utf-8"))
    assert summary["trial_root_removed"] is True


def test_learned_low_ratio_selection_without_lower_failure_runs_normal_downshift(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(
        job_dir,
        allowed=["100-100-6", "100-100-8", "120-120-6", "120-120-10", "140-140-8", "160-160-8"],
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(workflow, "apply_selected_square_section", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(
        workflow,
        "_read_similar_cached_selection",
        lambda *args, **kwargs: {
            "status": "hit",
            "selected_section_hint": "160-160-8",
            "similarity": {"score": 1.0},
            "historical_candidate_results": [
                {"section_name": "160-160-8", "status": "pass", "run_status": "pass", "controlling_ratio": 0.6125}
            ],
        },
    )

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "pass",
            "selected": {"section_name": "160-160-8", "controlling_ratio": 0.6125},
            "candidate_results": [{"section_name": "160-160-8", "status": "pass", "controlling_ratio": 0.6125}],
            "policy": "test",
        }

    monkeypatch.setattr(workflow, "run_square_section_search", fake_search)

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        cache_path=tmp_path / "cache.json",
    )

    assert result["status"] == "pass"
    assert "learned_formal_validation" not in result
    assert captured["max_evaluated_candidates"] == 2
    assert captured["stop_after_first_feasible"] is True


def test_similar_selection_cache_prefers_current_newer_entry_on_tie(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    _write_job(
        job_dir,
        allowed=["100-100-6", "100-100-8", "120-120-6", "120-120-10", "140-140-8", "160-160-8"],
    )
    payload = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    features = workflow._selection_similarity_features(payload)
    cache_path = tmp_path / "square_section_selection_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "cache_version": workflow.SQUARE_SECTION_CACHE_VERSION,
                "entries": {
                    "old": {
                        "status": "pass",
                        "selected": {"section_name": "100-100-6"},
                        "similarity_features": features,
                        "cache_version": "square-section-cache-v5-final-ratio-economy-proof",
                        "updated_at": "2026-06-05T00:00:00+00:00",
                    },
                    "new": {
                        "status": "pass",
                        "selected": {"section_name": "140-140-8"},
                        "similarity_features": features,
                        "cache_version": workflow.SQUARE_SECTION_CACHE_VERSION,
                        "updated_at": "2026-06-06T00:00:00+00:00",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    hit = workflow._read_similar_cached_selection(job_dir, cache_path=cache_path, threshold=0.1)

    assert hit["cache_key"] == "new"
    assert hit["selected_section_hint"] == "140-140-8"
    assert hit["entry_cache_version"] == workflow.SQUARE_SECTION_CACHE_VERSION


def test_allowed_square_sections_keep_modulus_jump_inside_allowed_list(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(job_dir, allowed=["100-100-6", "100-100-8", "120-120-6"])
    captured: dict[str, object] = {}

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(workflow, "apply_selected_square_section", lambda *args, **kwargs: {"status": "pass"})

    def fake_search(*args, **kwargs):
        captured.update(kwargs)
        return {
            "status": "pass",
            "selected": {"section_name": "120-120-6", "controlling_ratio": 0.83},
            "candidate_results": [
                {"section_name": "100-100-6", "status": "fail", "controlling_ratio": 1.24},
                {"section_name": "100-100-8", "status": "fail", "controlling_ratio": 1.05},
                {"section_name": "120-120-6", "status": "pass", "controlling_ratio": 0.83},
            ],
            "policy": "test",
        }

    monkeypatch.setattr(workflow, "run_square_section_search", fake_search)

    workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        runner=lambda trial_dir: {"status": "pass"},
    )

    assert captured["smart_jumps_enabled"] is True
    assert captured["smart_order"] is True
    assert [candidate.section_name for candidate in captured["candidates"]] == [
        "100-100-6",
        "100-100-8",
        "120-120-6",
    ]


def test_missing_intake_allowed_square_sections_blocks_local_catalog_fallback(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(job_dir, allowed=None)

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(
        workflow,
        "run_square_section_search",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("local catalog fallback must not run")),
    )

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        runner=lambda trial_dir: {"status": "pass"},
    )

    assert result["status"] == "fail"
    assert result["allowed_square_section_filter"]["status"] == "missing_required"
    assert "缺少提资计算说明允许方钢截面" in result["reason"]
    summary = json.loads((job_dir / "square_section_trial_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "fail"
    assert summary["allowed_square_section_filter"]["status"] == "missing_required"


def test_trial_final_ratio_mismatch_triggers_clean_reselection_not_upgrade(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "checks": [
                    {
                        "check_id": "square_section_trial_final_ratio_mismatch",
                        "status": "fail",
                        "message": "trial/final mismatch",
                        "evidence": {"trial_controlling_ratio": 0.98, "final_controlling_ratio": 0.15},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert workflow.result_validation_needs_square_section_clean_reselection(job_dir) is True
    assert workflow.result_validation_needs_square_section_upgrade(job_dir) is False


def test_square_support_ratio_over_limit_triggers_upgrade_not_clean_reselection(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "status": "fail",
                "checks": [
                    {
                        "check_id": "evaluation_ratio_limit",
                        "status": "fail",
                        "message": "ratio > 1",
                        "evidence": [{"check_id": "square_support.support_bending", "ratio": 1.08}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert workflow.result_validation_needs_square_section_clean_reselection(job_dir) is False
    assert workflow.result_validation_needs_square_section_upgrade(job_dir) is True


def test_force_reselect_resets_previous_auto_selected_state(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    _write_job(job_dir, allowed=["100-100-6", "100-100-8"])
    input_path = job_dir / "input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    payload["metadata"].update(
        {
            "square_section_selection_status": "auto_selected_by_real_ansys",
            "square_section_selected": "100-100-8",
            "square_section_selected_ratio": 0.98,
        }
    )
    input_path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(workflow, "discover_square_section_candidates", lambda *args, **kwargs: _candidates())
    monkeypatch.setattr(workflow, "apply_selected_square_section", lambda *args, **kwargs: {"status": "pass"})
    monkeypatch.setattr(
        workflow,
        "run_square_section_search",
        lambda *args, **kwargs: {
            "status": "pass",
            "selected": {"section_name": "100-100-6", "controlling_ratio": 0.82},
            "candidate_results": [{"section_name": "100-100-6", "status": "pass", "controlling_ratio": 0.82}],
            "policy": "test",
        },
    )

    result = workflow.select_and_apply_square_section(
        job_dir,
        config=None,
        config_path=tmp_path / "ansys.toml",
        confirm_user="tester",
        runner=lambda trial_dir: {"status": "pass"},
        force_reselect=True,
    )

    assert result["status"] == "pass"
    reset_audit = json.loads((job_dir / "square_section_reselection_reset.json").read_text(encoding="utf-8"))
    assert reset_audit["status"] == "pass"
    assert reset_audit["previous"]["metadata"]["square_section_selected"] == "100-100-8"
