from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.intake.intake_excel_reader import read_tabular_intake_rows
from core.results.output_workspace import DEFAULT_OUTPUT_ROOT, publish_result_outputs, sanitize_order_id


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("intake_sheet") or ""), str(row.get("intake_serial") or row.get("intake_row_number") or ""))


def _job_key(metadata: dict[str, Any]) -> tuple[str, str]:
    return (str(metadata.get("intake_sheet") or ""), str(metadata.get("intake_serial") or metadata.get("intake_row_number") or ""))


def reconcile_report_numbers_from_intake(
    jobs_dir: Path | str,
    intake_path: Path | str,
    *,
    dry_run: bool = False,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    publish_results: bool = False,
    overwrite: bool = True,
) -> dict[str, Any]:
    """Update provisional jobs after report/calculation numbers are filled in the intake workbook.

    The stable link is the intake sheet plus the original serial/row number. This keeps
    early calculation jobs usable before the formal report number exists.
    """

    jobs_dir = Path(jobs_dir)
    rows = read_tabular_intake_rows(intake_path)
    rows_by_key = {_row_key(row): row for row in rows if row.get("report_number") or row.get("calculation_batch")}
    updates: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    published: list[dict[str, Any]] = []

    for input_path in sorted(jobs_dir.rglob("input.json")):
        payload = _read_json(input_path)
        metadata = payload.get("metadata") or {}
        key = _job_key(metadata)
        formal = metadata.get("report_number") or metadata.get("calculation_batch")
        row = rows_by_key.get(key)
        if not row:
            missing.append({"job_dir": str(input_path.parent), "intake_key": key, "status": "pending_report_number"})
            continue
        new_report = row.get("report_number") or row.get("calculation_batch")
        if formal == new_report:
            unchanged.append({"job_dir": str(input_path.parent), "report_number": formal, "status": "unchanged"})
            if publish_results:
                if dry_run:
                    published.append(
                        {
                            "job_dir": str(input_path.parent),
                            "report_number": formal,
                            "target_dir": str(Path(output_root) / sanitize_order_id(str(formal))),
                            "status": "would_publish",
                        }
                    )
                else:
                    manifest = publish_result_outputs(
                        input_path.parent,
                        output_root=output_root,
                        intake_order_id=str(formal),
                        overwrite=overwrite,
                    )
                    published.append(
                        {
                            "job_dir": str(input_path.parent),
                            "report_number": formal,
                            "target_dir": manifest.get("target_dir"),
                            "status": manifest.get("status"),
                        }
                    )
            continue
        metadata["report_number"] = new_report
        metadata["calculation_batch"] = new_report
        metadata["intake_order_id"] = new_report
        metadata["intake_identity_status"] = "formal_report_number_provided"
        metadata["report_number_reconciled_from_intake"] = str(intake_path)
        payload["metadata"] = metadata
        if not dry_run:
            _write_json(input_path, payload)
        updates.append(
            {
                "job_dir": str(input_path.parent),
                "intake_key": key,
                "old_report_number": formal,
                "new_report_number": new_report,
                "status": "updated" if not dry_run else "would_update",
            }
        )
        if publish_results:
            if dry_run:
                published.append(
                    {
                        "job_dir": str(input_path.parent),
                        "report_number": new_report,
                        "target_dir": str(Path(output_root) / sanitize_order_id(str(new_report))),
                        "status": "would_publish",
                    }
                )
            else:
                manifest = publish_result_outputs(
                    input_path.parent,
                    output_root=output_root,
                    intake_order_id=str(new_report),
                    overwrite=overwrite,
                )
                published.append(
                    {
                        "job_dir": str(input_path.parent),
                        "report_number": new_report,
                        "target_dir": manifest.get("target_dir"),
                        "status": manifest.get("status"),
                    }
                )

    payload = {
        "status": "pass",
        "jobs_dir": str(jobs_dir),
        "intake_path": str(intake_path),
        "dry_run": dry_run,
        "output_root": str(output_root),
        "publish_results": publish_results,
        "updated_count": len(updates),
        "unchanged_count": len(unchanged),
        "pending_count": len(missing),
        "published_count": len(published),
        "updates": updates,
        "unchanged": unchanged,
        "pending": missing,
        "published": published,
        "policy": "Jobs may be created before report numbers exist; later workbook revisions can bind them to formal report/calculation batch numbers by intake sheet and serial.",
    }
    audit_path = jobs_dir / "report_number_reconcile_audit.json"
    if not dry_run:
        _write_json(audit_path, payload)
    return payload
