from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.ansys.config import AnsysLocalConfig, load_ansys_config


BLOCKING_STATES = {"running", "failed"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def command_hash(command_payload: dict[str, Any]) -> str:
    encoded = json.dumps(command_payload.get("command", command_payload), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check(check_id: str, ok: bool, message: str, evidence: Any = None) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "pass" if ok else "fail",
        "message": message,
        "evidence": evidence,
    }


def _load_preflight(job_dir: Path, preflight: dict[str, Any] | None) -> dict[str, Any] | None:
    if preflight is not None:
        return preflight
    path = job_dir / "ansys_preflight.json"
    if path.exists():
        return _read_json(path)
    return None


def _spectrum_config_confirmed(job_dir: Path) -> tuple[bool, Any]:
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return False, "input.json missing"
    try:
        payload = _read_json(input_path)
    except Exception as exc:
        return False, f"input.json unreadable: {exc}"
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    root_value = payload.get("spectrum_config_confirmed") if isinstance(payload, dict) else None
    metadata_value = metadata.get("spectrum_config_confirmed") if isinstance(metadata, dict) else None
    confirmed = root_value is True or metadata_value is True
    return confirmed, {"root": root_value, "metadata": metadata_value}


def evaluate_real_run_guard(
    job_dir: Path | str,
    *,
    config_path: Path | str = Path("config/ansys.local.toml"),
    config: AnsysLocalConfig | None = None,
    preflight: dict[str, Any] | None = None,
    confirm_real_run: bool = False,
    confirm_user: str | None = None,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    config_path = Path(config_path)
    checks: list[dict[str, Any]] = []

    config_exists = config_path.exists()
    checks.append(_check("config_file_exists", config_exists, "config/ansys.local.toml exists", str(config_path)))
    loaded_config = config or (load_ansys_config(config_path) if config_exists else AnsysLocalConfig())

    checks.append(_check("runner_mode_real", loaded_config.runner.mode == "real", "runner.mode is real", loaded_config.runner.mode))

    executable = Path(loaded_config.ansys.executable or "")
    checks.append(
        _check(
            "ansys_executable_exists",
            bool(loaded_config.ansys.executable) and executable.exists(),
            "Configured ANSYS executable exists",
            str(executable) if loaded_config.ansys.executable else None,
        )
    )

    preflight_payload = _load_preflight(job_dir, preflight)
    preflight_failures: list[dict[str, Any]] = []
    if preflight_payload:
        preflight_failures = [item for item in preflight_payload.get("checks", []) if item.get("status") == "fail"]
    checks.append(
        _check(
            "preflight_has_no_fail",
            bool(preflight_payload) and preflight_payload.get("status") == "pass" and not preflight_failures,
            "Real run requires ansys_preflight.json status=pass and zero fail checks",
            {"status": preflight_payload.get("status") if preflight_payload else None, "fail_count": len(preflight_failures)},
        )
    )

    state_path = job_dir / "job_state.json"
    state = _read_json(state_path) if state_path.exists() else {"status": "created"}
    state_status = state.get("status")
    checks.append(
        _check(
            "job_state_allows_real_run",
            state_status not in BLOCKING_STATES,
            "job_state allows a real run attempt",
            state,
        )
    )

    checks.append(_check("confirm_real_run", confirm_real_run, "User supplied explicit real-run confirmation flag", confirm_real_run))

    spectrum_confirmed, spectrum_evidence = _spectrum_config_confirmed(job_dir)
    checks.append(
        _check(
            "spectrum_config_confirmed",
            spectrum_confirmed,
            "spectrum_config_confirmed is true in input.json metadata or root",
            spectrum_evidence,
        )
    )

    command_path = job_dir / "ansys_command.json"
    command_payload = _read_json(command_path) if command_path.exists() else {}
    hash_value = command_hash(command_payload) if command_payload else None
    checks.append(_check("command_hash_available", hash_value is not None, "ANSYS command hash is available", hash_value))

    reasons = [check["message"] for check in checks if check["status"] == "fail"]
    accepted = not reasons
    resolved_user = confirm_user or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown"
    payload = {
        "status": "pass" if accepted else "rejected",
        "accepted": accepted,
        "job_id": job_dir.name,
        "confirm_user": resolved_user if confirm_real_run else None,
        "confirm_time": _now() if confirm_real_run else None,
        "command_hash": hash_value,
        "checks": checks,
        "rejection_reasons": reasons,
    }
    _write_json(job_dir / "real_run_guard.json", payload)
    return payload


def write_rejected_real_run_audit(job_dir: Path | str, guard: dict[str, Any], preflight_status: str | None = None) -> dict[str, Any]:
    job_dir = Path(job_dir)
    audit = {
        "status": "rejected",
        "mode": "real",
        "executed": False,
        "preflight_status": preflight_status,
        "guard_status": guard.get("status"),
        "rejection_reasons": guard.get("rejection_reasons", []),
        "guard_file": "real_run_guard.json",
        "kept_job_directory": True,
        "notes": ["Real ANSYS run was blocked by the Stage 4 guard."],
    }
    _write_json(job_dir / "ansys_run_audit.json", audit)
    return audit
