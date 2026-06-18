from __future__ import annotations

import json
from pathlib import Path

from core.apdl.modal_policy import (
    audited_source_modal_mode_count_from_job,
    modal_mode_count_from_layer_count,
    modal_mode_count_from_payload,
    modal_policy_audit,
    record_modal_mode_count_learning,
)


def test_six_layer_new_intake_starts_at_bounded_safe_initial_count() -> None:
    assert modal_mode_count_from_layer_count(6) == 80


def test_one_layer_new_intake_starts_at_department_20_mode_rule() -> None:
    assert modal_mode_count_from_layer_count(1) == 20


def test_payload_infers_layer_count_when_explicit_modal_count_absent() -> None:
    payload = {
        "support": {"layers_front": 4, "layers_back": 2},
        "metadata": {},
        "tray_layers": [
            {"side": "front", "layer_index": 1, "width_mm": 500},
            {"side": "front", "layer_index": 2, "width_mm": 500},
            {"side": "front", "layer_index": 3, "width_mm": 500},
            {"side": "front", "layer_index": 4, "width_mm": 500},
            {"side": "back", "layer_index": 1, "width_mm": 500},
            {"side": "back", "layer_index": 2, "width_mm": 500},
        ],
    }

    assert modal_mode_count_from_payload(payload, source_text="MT=40") == 40
    audit = modal_policy_audit(payload, source_text="MT=40")
    assert audit["assigned_modal_mode_count"] == 40
    assert audit["assigned_modal_mode_count_source"] == "audited_source_safe_count"
    assert audit["inferred_layer_count"] == 4


def test_double_sided_mixed_payload_uses_vertical_levels_not_total_runs_for_initial_mt() -> None:
    payload = {
        "support": {"layers_front": 5, "layers_back": 5, "side_count": 2},
        "metadata": {
            "tray_load_mapping": {
                "front_layers": 5,
                "back_layers": 5,
                "layers": [
                    {"side": "front", "layer_index": index}
                    for index in range(1, 6)
                ]
                + [
                    {"side": "back", "layer_index": index}
                    for index in range(1, 6)
                ],
            }
        },
        "tray_layers": [
            {"side": "front", "layer_index": index, "tray_width_m": width}
            for index, width in enumerate((0.1, 0.2, 0.3, 0.5, 0.6), start=1)
        ]
        + [
            {"side": "back", "layer_index": index, "tray_width_m": width}
            for index, width in enumerate((0.1, 0.2, 0.3, 0.5, 0.6), start=1)
        ],
    }

    assert modal_mode_count_from_payload(payload, source_text="MT=120") == 120
    audit = modal_policy_audit(payload, source_text="MT=120")
    assert audit["inferred_layer_count"] == 5
    assert audit["assigned_modal_mode_count"] == 120
    assert audit["assigned_modal_mode_count_source"] == "audited_source_safe_count"


def test_learned_metadata_above_layer_band_is_trusted_as_real_run_evidence() -> None:
    payload = {
        "support": {"layers_front": 5, "layers_back": 5, "side_count": 2},
        "metadata": {
            "modal_mode_count": 110,
            "modal_mode_count_source": "learned_similar_intake_modal_cache",
            "tray_load_mapping": {
                "front_layers": 5,
                "back_layers": 5,
                "layers": [
                    {"side": "front", "layer_index": index}
                    for index in range(1, 6)
                ]
                + [
                    {"side": "back", "layer_index": index}
                    for index in range(1, 6)
                ],
            },
        },
    }

    assert modal_mode_count_from_payload(payload, source_text="MT=120") == 110
    audit = modal_policy_audit(payload, source_text="MT=120")
    assert audit["assigned_modal_mode_count"] == 110
    assert audit["assigned_modal_mode_count_source"] == "learned_similar_intake_metadata"


def test_auto_layer_metadata_above_layer_band_falls_back_to_inferred_layers() -> None:
    payload = {
        "support": {"layers_front": 5, "layers_back": 5, "side_count": 2},
        "metadata": {
            "modal_mode_count": 110,
            "modal_mode_count_source": "intake_rule_layer_count_modal_count",
            "tray_load_mapping": {
                "front_layers": 5,
                "back_layers": 5,
                "layers": [
                    {"side": "front", "layer_index": index}
                    for index in range(1, 6)
                ]
                + [
                    {"side": "back", "layer_index": index}
                    for index in range(1, 6)
                ],
            },
        },
    }

    assert modal_mode_count_from_payload(payload, source_text=None) == 70
    audit = modal_policy_audit(payload, source_text=None)
    assert audit["assigned_modal_mode_count"] == 70
    assert audit["assigned_modal_mode_count_source"] == "inferred_layer_count"


def test_explicit_modal_count_still_wins_over_layer_heuristic() -> None:
    payload = {
        "support": {"layers_front": 4, "layers_back": 2},
        "metadata": {"modal_mode_count": 120},
    }

    assert modal_mode_count_from_payload(payload, source_text="MT=40") == 120
    audit = modal_policy_audit(payload, source_text="MT=40")
    assert audit["assigned_modal_mode_count"] == 120
    assert audit["assigned_modal_mode_count_source"] == "input_metadata"


def test_successful_real_run_cache_right_sizes_next_similar_initial_mt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    payload = {
        "support": {
            "support_type": "S2",
            "layers_front": 3,
            "layers_back": 3,
            "side_count": 2,
            "support_spacing_m": 2.0,
            "support_height_m": 1.7,
            "support_section_id": "140-140-8",
        },
        "metadata": {
            "analysis_method": "response_spectrum",
            "square_section_current_model_spec": "140-140-8",
            "square_section_outer_mm": 140.0,
            "square_section_thickness_mm": 8.0,
        },
        "tray_layers": [
            {"tray_width_m": 0.5, "arm_a_length_m": 0.35}
            for _ in range(6)
        ],
    }
    (job_dir / "input.json").write_text(json.dumps(payload), encoding="utf-8")
    (job_dir / "modal_results.json").write_text(
        json.dumps(
            [
                {
                    "mode": 66,
                    "source_mode": 66,
                    "frequency_hz": 50.18,
                    "mt_mode": 80,
                    "mt_mode_first_above_cutoff_hz": 66,
                    "mt_mode_last_above_cutoff_hz": 80,
                    "modal_cutoff_status": "pass",
                },
                {
                    "mode": 80,
                    "source_mode": 80,
                    "frequency_hz": 64.2,
                    "mt_mode": 80,
                    "mt_mode_first_above_cutoff_hz": 66,
                    "mt_mode_last_above_cutoff_hz": 80,
                    "modal_cutoff_status": "pass",
                },
            ]
        ),
        encoding="utf-8",
    )

    learned = record_modal_mode_count_learning(job_dir)

    assert learned["status"] == "pass"
    assert learned["recommended_modal_mode_count"] == 70
    assert modal_mode_count_from_payload(payload, source_text="MT=80") == 70
    audit = modal_policy_audit(payload, source_text="MT=80")
    assert audit["assigned_modal_mode_count"] == 70
    assert audit["assigned_modal_mode_count_source"] == "learned_similar_intake_cache"


def test_audited_source_modal_mode_count_reads_traceability_for_high_retry(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "intake_standard_family_traceability.json").write_text(
        json.dumps(
            {
                "solve_parameterization": {
                    "modal_mode_policy": {
                        "source_modal_mode_count": 887,
                        "source_modal_mode_count_retry_allowed": True,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert audited_source_modal_mode_count_from_job(job_dir) == 887


def test_static_method_does_not_learn_or_apply_modal_mt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = {
        "support": {
            "support_type": "S2",
            "layers_front": 4,
            "layers_back": 2,
            "side_count": 2,
            "support_spacing_m": 2.0,
            "support_height_m": 2.0,
            "support_section_id": "140-140-8",
        },
        "metadata": {
            "analysis_method": "static",
            "modal_mode_count": 80,
            "modal_mode_count_source": "intake_rule_layer_count_modal_count",
            "square_section_current_model_spec": "140-140-8",
            "square_section_outer_mm": 140.0,
            "square_section_thickness_mm": 8.0,
        },
        "tray_layers": [
            {"tray_width_m": 0.5, "arm_a_length_m": 0.35}
            for _ in range(6)
        ],
    }
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(json.dumps(payload), encoding="utf-8")
    (job_dir / "modal_results.json").write_text(
        json.dumps(
            [
                {
                    "mode": 493,
                    "source_mode": 493,
                    "frequency_hz": 50.0045,
                    "mt_mode": 887,
                    "mt_mode_first_above_cutoff_hz": 493,
                    "mt_mode_last_above_cutoff_hz": 887,
                    "modal_cutoff_status": "pass",
                }
            ]
        ),
        encoding="utf-8",
    )

    learned = record_modal_mode_count_learning(job_dir)

    assert learned["status"] == "not_required"
    assert learned["reason"] == "static_method_has_no_modal_mt_learning"
    assert modal_mode_count_from_payload(payload, source_text="MODOPT,LANB,887") == 80
    audit = modal_policy_audit(payload, source_text="MODOPT,LANB,887")
    assert audit["status"] == "not_required"
    assert audit["assigned_modal_mode_count"] is None
    assert audit["assigned_modal_mode_count_source"] == "static_method_not_required"
