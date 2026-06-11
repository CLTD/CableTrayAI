from __future__ import annotations

from core.ansys.config import AnsysLocalConfig
from core.ansys.runner import (
    _LIVE_OUTPUT_SUFFIXES,
    _ansys_main_stream_succeeded,
    _cleanup_stale_completion_outputs,
    _detect_ansys_completion_marker,
    _effective_real_run_timeout_policy,
)
from core.optimizer.square_section_workflow import _section_trial_config


def test_real_runner_clamps_stale_unit_timeout_config() -> None:
    config = AnsysLocalConfig()
    config.ansys.timeout_minutes = 12
    config.ansys.startup_no_output_timeout_seconds = 45
    config.ansys.output_stall_timeout_seconds = 180

    policy = _effective_real_run_timeout_policy(config)

    assert policy["status"] == "clamped"
    assert policy["configured_timeout_seconds"] == 720
    assert policy["timeout_seconds"] == 7200
    assert policy["startup_no_output_timeout_seconds"] == 90
    assert policy["output_stall_timeout_seconds"] == 300


def test_real_runner_preserves_safer_timeout_config() -> None:
    config = AnsysLocalConfig()
    config.ansys.timeout_minutes = 150
    config.ansys.startup_no_output_timeout_seconds = 120
    config.ansys.output_stall_timeout_seconds = 600

    policy = _effective_real_run_timeout_policy(config)

    assert policy["status"] == "unchanged"
    assert policy["timeout_seconds"] == 9000
    assert policy["startup_no_output_timeout_seconds"] == 120
    assert policy["output_stall_timeout_seconds"] == 600


def test_square_section_trial_config_uses_production_safe_watchdogs() -> None:
    config = AnsysLocalConfig()
    config.ansys.timeout_minutes = 12
    config.ansys.startup_no_output_timeout_seconds = 45
    config.ansys.output_stall_timeout_seconds = 180

    trial_config = _section_trial_config(config)

    assert config.ansys.timeout_minutes == 12
    assert trial_config.ansys.timeout_minutes == 120
    assert trial_config.ansys.startup_no_output_timeout_seconds == 90
    assert trial_config.ansys.output_stall_timeout_seconds == 0


def test_output_stall_watchdog_can_be_disabled_for_section_trials() -> None:
    config = AnsysLocalConfig()
    config.ansys.output_stall_timeout_seconds = 0

    policy = _effective_real_run_timeout_policy(config)

    assert policy["output_stall_timeout_seconds"] == 0
    assert policy["output_stall_hard_kill_enabled"] is False


def test_completion_marker_accepts_ansys_negative_launcher_return(tmp_path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    output = job_dir / "8TEG009010.TXT"
    output.write_text(
        "\n".join(
            [
                " ***** ROUTINE COMPLETED *****  CP =       510.266",
                "",
                " EXIT ANSYS WITHOUT SAVING DATABASE",
                "",
                " NUMBER OF WARNING MESSAGES ENCOUNTERED=        119",
                " NUMBER OF ERROR   MESSAGES ENCOUNTERED=          0",
            ]
        ),
        encoding="utf-8",
    )

    detection = _detect_ansys_completion_marker(job_dir, {"output_file": str(job_dir / "ansys.out")})

    assert detection["status"] == "pass"
    assert detection["matches"][0]["file"].endswith("8TEG009010.TXT")
    assert _ansys_main_stream_succeeded(4294967295, detection) is True
    assert ".txt" in _LIVE_OUTPUT_SUFFIXES


def test_completion_marker_does_not_accept_nonzero_mapdl_error_count(tmp_path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "8TEG009010.TXT").write_text(
        "\n".join(
            [
                " ***** ROUTINE COMPLETED *****  CP =       510.266",
                " EXIT ANSYS WITHOUT SAVING DATABASE",
                " NUMBER OF ERROR   MESSAGES ENCOUNTERED=          1",
            ]
        ),
        encoding="utf-8",
    )

    detection = _detect_ansys_completion_marker(job_dir, {"output_file": str(job_dir / "ansys.out")})

    assert detection["status"] == "not_detected"
    assert detection["partial_matches"][0]["error_count"] == 1
    assert _ansys_main_stream_succeeded(4294967295, detection) is False


def test_stale_completion_outputs_are_removed_before_real_rerun(tmp_path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    stale = job_dir / "8TEG009010.TXT"
    stale.write_text(
        "\n".join(
            [
                " ***** ROUTINE COMPLETED *****",
                " EXIT ANSYS WITHOUT SAVING DATABASE",
                " NUMBER OF ERROR   MESSAGES ENCOUNTERED=          0",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "ansys.out").write_text("old output", encoding="utf-8")

    audit = _cleanup_stale_completion_outputs(job_dir, {"output_file": str(job_dir / "ansys.out")})

    assert audit["status"] == "pass"
    assert audit["removed_count"] == 2
    assert not stale.exists()
    assert not (job_dir / "ansys.out").exists()
    assert _detect_ansys_completion_marker(job_dir, {"output_file": str(job_dir / "ansys.out")})["status"] == "not_detected"
