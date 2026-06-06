from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


HEAVY_SOLVER_EXTENSIONS = {
    ".rst",
    ".mode",
    ".full",
    ".emat",
    ".esav",
    ".db",
    ".page",
    ".mntr",
    ".rdb",
    ".ldhi",
    ".l39",
    ".l40",
    ".l41",
    ".l61",
    ".l62",
    ".l80",
    ".l81",
    ".l82",
    ".l83",
    ".l84",
    ".l92",
    ".l93",
    ".l99",
}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def cleanup_heavy_solver_artifacts(
    job_dir: Path | str,
    *,
    enabled: bool = True,
    recursive: bool = True,
    extensions: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Remove regenerable ANSYS database/result-cache files from one job workspace.

    The cleanup intentionally keeps command streams, LIS/OUP text results, BMP/PNG
    figures, JSON/CSV result tables, and out/err logs. It is meant to run after
    result parsing and publication, so repeated validation batches do not fill the
    calculation disk with large binary solver caches.
    """

    root = Path(job_dir).resolve()
    if "source_materials" in {part.lower() for part in root.parts}:
        raise ValueError(f"Refusing to clean inside source_materials: {root}")

    suffixes = {str(item).lower() if str(item).startswith(".") else f".{str(item).lower()}" for item in (extensions or HEAVY_SOLVER_EXTENSIONS)}
    audit_path = root / "solver_artifact_cleanup.json"
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    if not enabled:
        audit = {
            "status": "skipped",
            "job_dir": str(root),
            "removed_count": 0,
            "removed_bytes": 0,
            "removed": removed,
            "skipped": skipped,
        }
        root.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        return audit

    if not root.exists():
        return {
            "status": "missing_job_dir",
            "job_dir": str(root),
            "removed_count": 0,
            "removed_bytes": 0,
            "removed": removed,
            "skipped": skipped,
        }

    iterator = root.rglob("*") if recursive else root.iterdir()
    for path in sorted((item for item in iterator if item.is_file()), key=lambda item: str(item).lower()):
        if path.suffix.lower() not in suffixes:
            continue
        resolved = path.resolve()
        if not _is_relative_to(resolved, root):
            skipped.append({"file": str(path), "reason": "outside_job_dir"})
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            removed.append(
                {
                    "file": str(path.relative_to(root)),
                    "extension": path.suffix.lower(),
                    "size": size,
                }
            )
        except OSError as exc:
            skipped.append({"file": str(path.relative_to(root)), "reason": str(exc)})

    removed_bytes = sum(int(item["size"]) for item in removed)
    audit = {
        "status": "pass" if not skipped else "warning",
        "job_dir": str(root),
        "policy": (
            "Only regenerable heavy ANSYS solver artifacts are removed. Command streams, LIS/OUP files, "
            "figures, JSON/CSV tables, and out/err logs are retained for engineering review."
        ),
        "extensions": sorted(suffixes),
        "removed_count": len(removed),
        "removed_bytes": removed_bytes,
        "removed_gb": round(removed_bytes / (1024**3), 3),
        "removed": removed,
        "skipped": skipped,
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
    }
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
