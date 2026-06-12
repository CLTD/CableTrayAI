from __future__ import annotations

import json
from pathlib import Path

from core.pipeline.one_click import _clean_regenerable_outputs_for_rerun, _retain_solver_artifacts_after_failure


def test_one_click_cleanup_removes_square_section_state_and_trials(tmp_path: Path) -> None:
    jobs_root = tmp_path / "jobs"
    job_dir = jobs_root / "job-1"
    job_dir.mkdir(parents=True)
    for name in (
        "square_section_selection.json",
        "square_section_selection_summary.json",
        "square_section_trial_summary.json",
        "square_section_upgrade_after_ratio_fail.json",
        "square_section_selection_applied.json",
    ):
        (job_dir / name).write_text("{}", encoding="utf-8")
    trial_dir = jobs_root / "_square_section_trials" / job_dir.name
    trial_dir.mkdir(parents=True)
    (trial_dir / "old.txt").write_text("old", encoding="utf-8")
    upgrade_trial_dir = jobs_root / "_square_section_upgrade_trials" / job_dir.name
    upgrade_trial_dir.mkdir(parents=True)
    (upgrade_trial_dir / "old.txt").write_text("old", encoding="utf-8")

    audit = _clean_regenerable_outputs_for_rerun(job_dir)

    assert audit["removed_count"] >= 5
    assert not (job_dir / "square_section_selection.json").exists()
    assert not (job_dir / "square_section_selection_summary.json").exists()
    assert not trial_dir.exists()
    assert not upgrade_trial_dir.exists()


def test_post_figure_license_failure_retains_solver_artifacts_for_retry(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "ansys_run_audit.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "completion_marker_detection": {"status": "pass"},
                "post_export_failure": {"name": "figure_export", "status": "failed"},
                "post_export_license_unavailable": True,
                "figure_export_audit": {
                    "status": "failed",
                    "license_retry_attempts": [{"license_unavailable": True}],
                },
            }
        ),
        encoding="utf-8",
    )

    assert _retain_solver_artifacts_after_failure(job_dir) is True
