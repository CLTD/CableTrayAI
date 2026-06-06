from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_FEEDBACK_DIR = Path("docs/operator_feedback")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any, *, max_len: int = 4000) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len] + "...[truncated]"
    return text


def record_feedback(payload: dict[str, Any], *, client_ip: str = "", store_dir: Path | str = DEFAULT_FEEDBACK_DIR) -> dict[str, Any]:
    root = Path(store_dir)
    root.mkdir(parents=True, exist_ok=True)
    item = {
        "feedback_id": uuid4().hex,
        "created_at": _now(),
        "client_ip": _clean_text(payload.get("client_ip") or client_ip, max_len=80),
        "operator": _clean_text(payload.get("operator"), max_len=120),
        "job_id": _clean_text(payload.get("job_id"), max_len=180),
        "report_number": _clean_text(payload.get("report_number"), max_len=180),
        "page": _clean_text(payload.get("page"), max_len=240),
        "severity": _clean_text(payload.get("severity") or "suggestion", max_len=40),
        "bug_reason": _clean_text(payload.get("bug_reason")),
        "suggested_fix": _clean_text(payload.get("suggested_fix")),
        "status": "open",
    }
    if not item["bug_reason"] and not item["suggested_fix"]:
        raise ValueError("bug_reason or suggested_fix is required")
    jsonl = root / "feedback_items.jsonl"
    with jsonl.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    _write_summary(root)
    return item


def read_feedback(store_dir: Path | str = DEFAULT_FEEDBACK_DIR, *, limit: int = 200) -> list[dict[str, Any]]:
    jsonl = Path(store_dir) / "feedback_items.jsonl"
    if not jsonl.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in jsonl.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"raw": line, "status": "parse_error"})
    return rows[-limit:]


def _write_summary(root: Path) -> None:
    rows = read_feedback(root, limit=100000)
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in rows:
        by_severity[str(row.get("severity") or "unknown")] = by_severity.get(str(row.get("severity") or "unknown"), 0) + 1
        by_status[str(row.get("status") or "unknown")] = by_status.get(str(row.get("status") or "unknown"), 0) + 1
    summary = {
        "updated_at": _now(),
        "count": len(rows),
        "by_severity": by_severity,
        "by_status": by_status,
        "latest": rows[-20:],
    }
    (root / "feedback_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_path = root / "feedback_items.csv"
    fieldnames = [
        "feedback_id",
        "created_at",
        "client_ip",
        "operator",
        "job_id",
        "report_number",
        "page",
        "severity",
        "bug_reason",
        "suggested_fix",
        "status",
    ]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
