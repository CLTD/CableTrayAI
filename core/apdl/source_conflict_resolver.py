from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_CONFLICT_MANIFEST = Path("data/calibration/source_conflict_resolutions.json")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"resolutions": []}
    return json.loads(path.read_text(encoding="utf-8"))


def apply_source_conflict_resolutions(
    job_dir: Path | str,
    *,
    package_id: str | None,
    manifest_path: Path | str = DEFAULT_SOURCE_CONFLICT_MANIFEST,
) -> dict[str, Any]:
    """Apply audited source-conflict corrections for report reproduction only.

    These corrections are intentionally data-driven. They are not template defaults
    and they are not used unless a manifest entry names the current command package.
    """

    job_dir = Path(job_dir)
    manifest_path = Path(manifest_path)
    manifest = _load_manifest(manifest_path)
    package_id = str(package_id or "")
    entries = [
        item
        for item in manifest.get("resolutions", [])
        if str(item.get("package_id") or "") == package_id and item.get("enabled", True)
    ]
    if not entries:
        payload = {
            "status": "not_applicable",
            "package_id": package_id,
            "manifest": str(manifest_path),
            "applied": [],
            "policy": "No source-conflict correction applies to this command package.",
        }
        (job_dir / "source_conflict_resolution_audit.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload

    applied: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for entry in entries:
        target_name = str(entry.get("target") or "")
        target = job_dir / target_name
        match = str(entry.get("match") or "")
        match_regex = str(entry.get("match_regex") or "")
        replacement = str(entry.get("replacement") or "")
        expected_count = int(entry.get("expected_count") or 1)
        row: dict[str, Any] = {
            "target": target_name,
            "source_ref": entry.get("source_ref"),
            "reason": entry.get("reason"),
            "scope": entry.get("scope"),
        }
        optional = bool(entry.get("optional_alternative"))
        if not target.exists():
            if optional:
                skipped.append({**row, "status": "skipped", "message": "optional alternative target missing"})
                continue
            failed.append({**row, "status": "fail", "message": "target file missing"})
            continue
        text = target.read_text(encoding="utf-8")
        if match_regex:
            count = len(re.findall(match_regex, text, flags=re.MULTILINE))
        else:
            count = text.count(match)
        if count != expected_count:
            if optional and count == 0:
                skipped.append({**row, "status": "skipped", "message": "optional alternative did not match"})
                continue
            failed.append(
                {
                    **row,
                    "status": "fail",
                    "message": f"expected {expected_count} match(es), found {count}",
                }
            )
            continue
        if match_regex:
            patched = re.sub(match_regex, replacement, text, count=expected_count, flags=re.MULTILINE)
        else:
            patched = text.replace(match, replacement, expected_count)
        target.write_text(patched, encoding="utf-8", newline="\n")
        applied.append(
            {
                **row,
                "status": "applied",
                "match": match,
                "match_regex": match_regex or None,
                "replacement": replacement,
                "expected_count": expected_count,
            }
        )

    payload = {
        "status": "pass" if applied and not failed else "fail",
        "package_id": package_id,
        "manifest": str(manifest_path),
        "applied": applied,
        "failed": failed,
        "skipped": skipped,
        "policy": (
            "Source-conflict corrections are calibration-only, exact-match patches. "
            "They preserve the original source files and write an audit trail for review."
        ),
    }
    (job_dir / "source_conflict_resolution_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
