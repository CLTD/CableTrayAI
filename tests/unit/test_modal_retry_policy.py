from __future__ import annotations

import json
from pathlib import Path

from core.pipeline.one_click import _modal_retry_plan


def test_modal_retry_uses_audited_source_count_after_normal_cap(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "result_validation.json").write_text(
        json.dumps(
            {
                "checks": [
                    {
                        "check_id": "modal_mt_cutoff",
                        "status": "fail",
                        "evidence": {"last_frequency_hz": 21.8866546846},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
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

    plan = _modal_retry_plan(240, job_dir)

    assert plan["status"] == "audited_source_retry"
    assert plan["next_modal_mode_count"] == 887
