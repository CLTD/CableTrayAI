from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.schemas.job_models import JobState, JobStatus, model_to_dict


STATE_FILENAME = "job_state.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_path(job_dir: Path | str) -> Path:
    return Path(job_dir) / STATE_FILENAME


def read_job_state(job_dir: Path | str, job_id: str | None = None) -> JobState:
    path = state_path(job_dir)
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if hasattr(JobState, "model_validate"):
            return JobState.model_validate(payload)
        return JobState.parse_obj(payload)
    return JobState(job_id=job_id or Path(job_dir).name, status="created")


def write_job_state(job_dir: Path | str, state: JobState) -> dict:
    path = state_path(job_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = model_to_dict(state)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def update_job_state(
    job_dir: Path | str,
    status: JobStatus,
    message: str | None = None,
    failure_reason: str | None = None,
) -> dict:
    state = read_job_state(job_dir)
    state.status = status
    state.updated_at = _now()
    state.failure_reason = failure_reason
    state.history.append(
        {
            "status": status,
            "updated_at": state.updated_at,
            "message": message,
            "failure_reason": failure_reason,
        }
    )
    return write_job_state(job_dir, state)


def fail_job_state(job_dir: Path | str, failure_reason: str) -> dict:
    return update_job_state(job_dir, "failed", message="job failed", failure_reason=failure_reason)
