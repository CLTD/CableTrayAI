from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def cleanup_stale_ansys_locks(job_dir: Path | str, *, enabled: bool = True) -> dict[str, Any]:
    job_dir = Path(job_dir).resolve()
    removed: list[dict[str, Any]] = []
    skipped: list[str] = []
    if not enabled:
        audit = {"status": "skipped", "job_dir": str(job_dir), "removed": removed, "skipped": skipped}
        (job_dir / "ansys_lock_cleanup.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        return audit
    if not job_dir.exists():
        return {"status": "missing_job_dir", "job_dir": str(job_dir), "removed": removed, "skipped": skipped}

    for path in sorted(job_dir.glob("*.lock")):
        resolved = path.resolve()
        if resolved.parent != job_dir:
            skipped.append(str(path))
            continue
        removed.append(
            {
                "file": path.name,
                "size": path.stat().st_size,
                "last_write_time": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
        path.unlink()

    audit = {
        "status": "removed" if removed else "pass",
        "job_dir": str(job_dir),
        "removed": removed,
        "skipped": skipped,
        "policy": "Only stale ANSYS *.lock files inside the current job directory are removed before a calibration rerun. Source materials and result files are untouched.",
    }
    (job_dir / "ansys_lock_cleanup.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
