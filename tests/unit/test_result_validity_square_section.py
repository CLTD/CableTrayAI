from __future__ import annotations

import json
from pathlib import Path

from core.validation.result_validity_gate import validate_result_outputs


def test_result_gate_blocks_square_section_trial_final_ratio_mismatch(tmp_path: Path) -> None:
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

    payload = validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    mismatch = [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_mismatch"]
    assert mismatch
    assert mismatch[0]["status"] == "fail"
    assert payload["status"] == "fail"


def test_result_gate_blocks_legacy_flat_square_section_ratio_mismatch(tmp_path: Path) -> None:
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

    payload = validate_result_outputs(job_dir, raw={"missing_expected_files": []}, result=result)

    mismatch = [item for item in payload["checks"] if item["check_id"] == "square_section_trial_final_ratio_mismatch"]
    assert mismatch
    assert mismatch[0]["status"] == "fail"
    assert payload["status"] == "fail"
