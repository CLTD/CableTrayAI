from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal[
    "created",
    "source_scanned",
    "apdl_rendered",
    "spectrum_selected",
    "preflight_checked",
    "dry_run",
    "running",
    "parsed",
    "evaluated",
    "baseline_compared",
    "results_published",
    "reported",
    "failed",
]


class JobState(BaseModel):
    job_id: str
    status: JobStatus
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    failure_reason: str | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)


def model_to_dict(model: BaseModel | dict) -> dict:
    if isinstance(model, dict):
        return model
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()
