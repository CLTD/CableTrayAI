from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def draft_spectrum_config(workbook_path: Path | str, output_path: Path | str) -> dict[str, Any]:
    workbook_path = Path(workbook_path)
    draft = {
        "status": "draft_requires_human_confirmation",
        "workbook": str(workbook_path),
        "workbook_pattern": workbook_path.name,
        "sheet_pattern": None,
        "header_row": 1,
        "columns": {
            "project_code": "A",
            "building": "B",
            "area": "C",
            "elevation": "D",
            "damping": "E",
            "level": "F",
            "direction": "G",
            "frequency_hz": "H",
            "acceleration_g": "I",
        },
        "confirmed": False,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


def confirm_spectrum_config(job_dir: Path | str, *, confirmed_by: str = "operator") -> dict[str, Any]:
    job_dir = Path(job_dir)
    input_path = job_dir / "input.json"
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    metadata = payload.setdefault("metadata", {})
    metadata["spectrum_config_confirmed"] = True
    metadata["spectrum_config_confirmed_by"] = confirmed_by
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    audit = {"status": "pass", "confirmed": True, "confirmed_by": confirmed_by}
    (job_dir / "spectrum_config_confirmation.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def spectrum_config_status(job_dir: Path | str) -> dict[str, Any]:
    input_path = Path(job_dir) / "input.json"
    if not input_path.exists():
        return {"status": "fail", "confirmed": False, "reason": "input.json missing"}
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    confirmed = bool(payload.get("spectrum_config_confirmed") or payload.get("metadata", {}).get("spectrum_config_confirmed"))
    return {"status": "pass" if confirmed else "blocked", "confirmed": confirmed}
