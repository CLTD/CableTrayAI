from __future__ import annotations

from core.ansys.config import AnsysLocalConfig
from core.ansys.runner import _effective_real_run_timeout_policy
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
