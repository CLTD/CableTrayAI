from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.evaluators.excel_mapping import mappings_to_dict, validate_excel_mappings


def excel_com_available() -> bool:
    try:
        import win32com.client  # type: ignore  # noqa: F401
        return True
    except Exception:
        return False


def prepare_evaluation_workbook(source_workbook: Path | str, job_dir: Path | str) -> Path:
    source_workbook = Path(source_workbook)
    target_dir = Path(job_dir) / "evaluation_workbooks"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source_workbook.name
    shutil.copy2(source_workbook, target)
    return target


def run_excel_authoritative_evaluation(
    job_dir: Path | str,
    source_workbook: Path | str | None = None,
    *,
    mappings: list[dict] | None = None,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    mappings = mappings or mappings_to_dict()
    mapping_validation = validate_excel_mappings(mappings)
    workbook_path = None
    blockers: list[str] = []
    if source_workbook:
        workbook_path = str(prepare_evaluation_workbook(source_workbook, job_dir))
    else:
        blockers.append("No source workbook was provided.")
    if not excel_com_available():
        blockers.append("Excel COM is not available in this runtime.")
    if mapping_validation["status"] != "pass":
        blockers.append("Excel cell mapping is incomplete.")

    status = "blocked" if blockers else "pass"
    payload = {
        "status": status,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "evaluated_workbook_path": workbook_path,
        "formula_cells": [item for item in mappings if item.get("direction") != "input"],
        "result_cells": [item for item in mappings if item.get("direction") == "output"],
        "source_ref": str(source_workbook) if source_workbook else None,
        "blockers": blockers,
        "can_authorize_unconfirmed_formulas": status == "pass",
        "notes": ["Excel authoritative evaluation never modifies source_materials; it works on a job-local copy."],
    }
    (job_dir / "excel_evaluation_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
