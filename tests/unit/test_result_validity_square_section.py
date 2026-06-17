from __future__ import annotations

import json
from pathlib import Path

import core.validation.result_validity_gate as gate


def _minimal_modal_job(
    job_dir: Path,
    *,
    frequency_hz: float = 21.8866546846,
    cutoff_status: str = "insufficient_modes_below_50hz",
    include_mode_file: bool = True,
) -> dict:
    job_dir.mkdir()
    (job_dir / "input.json").write_text(json.dumps({"support": {"support_type": "S2"}}), encoding="utf-8")
    required_files = ["MAXBEAMSTRESS.LIS", "JCZH.LIS"]
    if include_mode_file:
        required_files.append("Mode.oup")
    for file_name in required_files:
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")
    return {
        "beam_stress_results": [{"value_mpa": 1.0}],
        "foundation_loads": [],
        "modal_results": [
            {
                "mode": 240,
                "mt_mode": 240,
                "frequency_hz": frequency_hz,
                "modal_cutoff_status": cutoff_status,
            }
        ],
        "evaluation_summary": [{"check_id": "square_support.support_bending", "ratio": 0.9, "allowable_value": 234.3}],
    }


def _requirements_for_method(analysis_method: str) -> dict:
    modal_required = analysis_method != "static"
    modal_frequency_table = True
    return {
        "status": "pass",
        "classification": "steel_platform" if analysis_method == "static" else "non_steel_platform",
        "analysis_method": analysis_method,
        "support_type": "S2",
        "requires": {
            "modal_analysis": modal_required,
            "modal_frequency_table": modal_frequency_table,
            "square_support_stress_eval": True,
            "cantilever_stress_eval": False,
            "cantilever_root_weld_eval": False,
            "foundation_loads": False,
            "tray_arm_connection_loads": False,
            "bolt_stress_eval": False,
        },
        "required_figures": [],
    }


def _foundation_requirements() -> dict:
    return {
        "status": "pass",
        "classification": "steel_platform",
        "analysis_method": "static",
        "support_type": "S2",
        "requires": {
            "modal_analysis": False,
            "modal_frequency_table": False,
            "square_support_stress_eval": True,
            "cantilever_stress_eval": False,
            "cantilever_root_weld_eval": False,
            "foundation_loads": True,
            "tray_arm_connection_loads": False,
            "bolt_stress_eval": False,
        },
        "required_figures": [],
    }


def _dw_vertical_only_result() -> dict:
    return {
        "beam_stress_results": [{"value_mpa": 1.0}],
        "foundation_loads": [{"load_case": "DW", "node": "N1", "fx": 0.0, "fy": 0.0, "fz": 10.0, "mx": 0.0, "my": 0.0, "mz": 0.0}],
        "evaluation_summary": [{"check_id": "square_support.support_bending", "ratio": 0.9, "allowable_value": 234.3}],
    }


def test_result_gate_does_not_require_modal_cutoff_for_static_method(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "static-job"
    result = _minimal_modal_job(job_dir)
    monkeypatch.setattr(gate, "classify_job_requirements", lambda _job_dir: _requirements_for_method("static"))

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    modal_gate = [item for item in payload["checks"] if item["check_id"] == "modal_mt_cutoff"]
    frequency_table_gate = [item for item in payload["checks"] if item["check_id"] == "modal_frequency_table"]
    assert not modal_gate
    assert frequency_table_gate
    assert frequency_table_gate[0]["status"] == "pass"
    assert payload["status"] == "pass"


def test_result_gate_keeps_response_spectrum_50hz_modal_cutoff(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "spectrum-job"
    result = _minimal_modal_job(job_dir)
    monkeypatch.setattr(
        gate,
        "classify_job_requirements",
        lambda _job_dir: _requirements_for_method("response_spectrum"),
    )

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    modal_gate = [item for item in payload["checks"] if item["check_id"] == "modal_mt_cutoff"]
    assert modal_gate
    assert modal_gate[0]["status"] == "fail"
    assert payload["status"] == "fail"


def test_result_gate_allows_vertical_only_dw_for_symmetric_double_side_counts(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "symmetric-dw"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        json.dumps({"support": {"support_type": "S2", "side_count": 2, "layers_front": 12, "layers_back": 12}}),
        encoding="utf-8",
    )
    for file_name in ("MAXBEAMSTRESS.LIS", "JCZH.LIS"):
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(gate, "classify_job_requirements", lambda _job_dir: _foundation_requirements())

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=_dw_vertical_only_result())

    symmetry = [item for item in payload["checks"] if item["check_id"] == "foundation_dw_self_weight_symmetry"]
    assert symmetry
    assert symmetry[0]["status"] == "pass"
    assert symmetry[0]["evidence"]["symmetry"]["layer_stack_evidence"] == "symmetric_layer_counts"
    assert not [item for item in payload["checks"] if item["check_id"] == "foundation_dw_moment_zero"]
    assert payload["status"] == "pass"


def test_result_gate_blocks_vertical_only_dw_for_asymmetric_double_side_counts(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "asymmetric-dw"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        json.dumps({"support": {"support_type": "S2", "side_count": 2, "layers_front": 12, "layers_back": 11}}),
        encoding="utf-8",
    )
    for file_name in ("MAXBEAMSTRESS.LIS", "JCZH.LIS"):
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(gate, "classify_job_requirements", lambda _job_dir: _foundation_requirements())

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=_dw_vertical_only_result())

    gate_rows = [item for item in payload["checks"] if item["check_id"] == "foundation_dw_moment_zero"]
    assert gate_rows
    assert gate_rows[0]["status"] == "fail"
    assert payload["status"] == "fail"


def test_result_gate_uses_formal_ratio_when_square_section_trial_ratio_mismatches_but_passes(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        json.dumps(
            {
                "support": {"support_type": "S2"},
                "metadata": {
                    "square_section_selection_status": "auto_selected_by_real_ansys",
                    "square_section_selected": "120-120-6",
                    "square_section_selected_ratio": 0.98,
                },
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "square_section_selection.json").write_text(
        json.dumps({"status": "pass", "selected": {"section_name": "120-120-6", "controlling_ratio": 0.98}}),
        encoding="utf-8",
    )
    for file_name in ("MAXBEAMSTRESS.LIS", "JCZH.LIS"):
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")

    result = {
        "beam_stress_results": [{"value_mpa": 1.0}],
        "foundation_loads": [{"load_case": "DW", "node": "N1", "fx": 1.0, "fy": 0.0, "fz": 1.0, "mx": 0.0, "my": 1.0, "mz": 0.0}],
        "evaluation_summary": [
            {"check_id": "square_support.support_bending", "ratio": 0.15, "allowable_value": 234.3},
            {"check_id": "bolt.combination", "ratio": 0.22, "allowable_value": 1.0},
        ],
    }

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    override = [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_formal_override"]
    assert override
    assert override[0]["status"] == "pass"
    assert override[0]["evidence"]["final_section_selection_ratio"] == 0.15
    assert not [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_mismatch"]


def test_result_gate_uses_formal_ratio_for_legacy_flat_square_section_ratio_mismatch(tmp_path: Path) -> None:
    job_dir = tmp_path / "legacy-job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        json.dumps(
            {
                "support": {"support_type": "S2"},
                "metadata": {
                    "square_section_selection_status": "auto_selected_by_real_ansys",
                    "square_section_selected": "120-120-6",
                },
            }
        ),
        encoding="utf-8",
    )
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
    for file_name in ("MAXBEAMSTRESS.LIS", "JCZH.LIS"):
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")

    result = {
        "beam_stress_results": [{"value_mpa": 1.0}],
        "foundation_loads": [
            {"load_case": "DW", "node": "N1", "fx": 1.0, "fy": 0.0, "fz": 1.0, "mx": 0.0, "my": 1.0, "mz": 0.0}
        ],
        "evaluation_summary": [
            {"check_id": "square_support.support_bending", "ratio": 0.1476, "allowable_value": 234.3},
        ],
    }

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    override = [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_formal_override"]
    assert override
    assert override[0]["status"] == "pass"
    assert not [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_mismatch"]


def test_result_gate_still_blocks_square_section_trial_mismatch_when_formal_ratio_over_limit(tmp_path: Path) -> None:
    job_dir = tmp_path / "job-overlimit"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        json.dumps(
            {
                "support": {"support_type": "S2"},
                "metadata": {
                    "square_section_selection_status": "auto_selected_by_real_ansys",
                    "square_section_selected": "120-120-6",
                    "square_section_selected_ratio": 0.62,
                },
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "square_section_selection.json").write_text(
        json.dumps({"status": "pass", "selected": {"section_name": "120-120-6", "controlling_ratio": 0.62}}),
        encoding="utf-8",
    )
    for file_name in ("MAXBEAMSTRESS.LIS", "JCZH.LIS"):
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")

    result = {
        "beam_stress_results": [{"value_mpa": 1.0}],
        "foundation_loads": [{"load_case": "DW", "node": "N1", "fx": 1.0, "fy": 0.0, "fz": 1.0, "mx": 0.0, "my": 1.0, "mz": 0.0}],
        "evaluation_summary": [
            {"check_id": "square_support.support_bending", "ratio": 1.15, "allowable_value": 234.3},
        ],
    }

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    over_limit = [item for item in payload["checks"] if item["check_id"] == "evaluation_ratio_limit"]
    mismatch = [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_mismatch"]
    assert over_limit and over_limit[0]["status"] == "fail"
    assert mismatch and mismatch[0]["status"] == "fail"
    assert payload["status"] == "fail"


def test_result_gate_allows_learned_formal_validation_without_trial_ratio_compare(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "learned-formal"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        json.dumps(
            {
                "support": {"support_type": "S2"},
                "metadata": {
                    "square_section_selection_status": "auto_selected_by_real_ansys",
                    "square_section_selection_validation_mode": "learned_formal_validation",
                    "square_section_selected": "160-160-8",
                    "square_section_selected_ratio": 0.6125,
                },
            }
        ),
        encoding="utf-8",
    )
    (job_dir / "square_section_selection.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "selection_validation_mode": "learned_formal_validation",
                "selected": {
                    "section_name": "160-160-8",
                    "controlling_ratio": 0.6125,
                    "historical_controlling_ratio": 0.6125,
                },
            }
        ),
        encoding="utf-8",
    )
    for file_name in ("MAXBEAMSTRESS.LIS", "JCZH.LIS"):
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        gate,
        "classify_job_requirements",
        lambda _job_dir: {
            "status": "pass",
            "support_type": "S2",
            "requires": {
                "modal_analysis": False,
                "modal_frequency_table": False,
                "foundation_loads": True,
                "tray_arm_connection_loads": False,
                "bolt_stress_eval": False,
            },
            "required_figures": [],
        },
    )

    result = {
        "beam_stress_results": [{"value_mpa": 1.0}],
        "foundation_loads": [
            {"load_case": "DW", "node": "N1", "fx": 1.0, "fy": 0.0, "fz": 1.0, "mx": 0.0, "my": 1.0, "mz": 0.0}
        ],
        "evaluation_summary": [
            {"check_id": "mixed_beam_type_1.support_bending", "ratio": 0.86, "allowable_value": 234.3},
        ],
    }

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    learned = [item for item in payload["checks"] if item["check_id"] == "square_section_formal_validation_mode"]
    mismatch = [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_mismatch"]
    assert learned
    assert learned[0]["status"] == "pass"
    assert not mismatch
    assert payload["status"] == "pass"


def test_result_gate_allows_preserved_section_after_spacing_recovery_without_trial_ratio(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "spacing-recovery-formal"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(
        json.dumps(
            {
                "support": {"support_type": "S2", "support_spacing_m": 1.5},
                "metadata": {
                    "square_section_selection_status": "auto_selected_by_real_ansys",
                    "square_section_selection_validation_mode": "preserved_after_spacing_recovery_pending_formal_validation",
                    "square_section_selected": "120-120-10",
                    "support_spacing_previous_m": 2.0,
                    "support_spacing_current_m": 1.5,
                },
            }
        ),
        encoding="utf-8",
    )
    for file_name in ("MAXBEAMSTRESS.LIS", "JCZH.LIS"):
        (job_dir / file_name).write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(
        gate,
        "classify_job_requirements",
        lambda _job_dir: {
            "status": "pass",
            "support_type": "S2",
            "requires": {
                "modal_analysis": False,
                "modal_frequency_table": False,
                "foundation_loads": True,
                "tray_arm_connection_loads": False,
                "bolt_stress_eval": False,
            },
            "required_figures": [],
        },
    )

    result = {
        "beam_stress_results": [{"value_mpa": 1.0}],
        "foundation_loads": [
            {"load_case": "DW", "node": "N1", "fx": 1.0, "fy": 0.0, "fz": 1.0, "mx": 0.0, "my": 1.0, "mz": 0.0}
        ],
        "evaluation_summary": [
            {"check_id": "mixed_beam_type_1.support_compression_bending_combined_accident", "ratio": 0.5241},
            {"check_id": "cantilever_root_weld_equivalent.accident.bending", "ratio": 0.9617},
        ],
    }

    payload = gate.validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    formal = [item for item in payload["checks"] if item["check_id"] == "square_section_spacing_recovery_formal_validation"]
    missing = [item for item in payload["checks"] if item["check_id"] == "square_section_trial_ratio_missing"]
    assert formal
    assert formal[0]["status"] == "pass"
    assert formal[0]["evidence"]["support_spacing_current_m"] == 1.5
    assert not missing
    assert payload["status"] == "pass"
