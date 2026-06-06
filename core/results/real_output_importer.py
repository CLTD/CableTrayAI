from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.report.docx_builder import build_report
from core.results.real_output_validator import TEXT_OUTPUTS, validate_real_output_dir
from core.results.result_assembler import assemble_result


DEFAULT_REAL_OUTPUT_DIR = Path(os.environ.get("CABLETRAYAI_OUTPUT_ROOT", "outputs"))
IMPORT_SUFFIXES = {".lis", ".oup", ".bmp", ".png", ".out", ".err", ".rst"}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _canonical_target_name(source: Path) -> str:
    return TEXT_OUTPUTS.get(source.name.upper(), source.name)


def _iter_importable_files(source_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix().upper())
        if path.is_file() and path.suffix.lower() in IMPORT_SUFFIXES
    ]


def import_real_outputs(
    source_dir: Path | str | None = None,
    job_dir: Path | str = Path("jobs/imported_real_outputs"),
    *,
    parse: bool = True,
    build_report_doc: bool = False,
    overwrite: bool = True,
) -> dict[str, Any]:
    source_dir = Path(source_dir) if source_dir is not None else DEFAULT_REAL_OUTPUT_DIR
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    validation = validate_real_output_dir(source_dir)
    _write_json(job_dir / "real_output_validation.json", validation)

    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for source in _iter_importable_files(source_dir):
        target = job_dir / _canonical_target_name(source)
        if target.exists() and not overwrite:
            skipped.append({"source": str(source), "target": target.name, "reason": "target_exists"})
            continue
        shutil.copy2(source, target)
        imported.append(
            {
                "source": str(source),
                "target": target.name,
                "size": target.stat().st_size,
            }
        )

    result_file = None
    report_audit_file = None
    parse_status = "not_requested"
    report_status = "not_requested"
    if parse:
        if validation["status"] != "pass":
            parse_status = "skipped_validation_failed"
        elif not (job_dir / "input.json").exists():
            parse_status = "skipped_missing_input"
        else:
            result = assemble_result(job_dir)
            result["result_source"] = {
                "type": "external_real_output_import",
                "validation_file": "real_output_validation.json",
                "import_manifest": "imported_outputs_manifest.json",
                "source_dir": str(source_dir),
            }
            _write_json(job_dir / "result.json", result)
            result_file = "result.json"
            parse_status = "parsed"
            if build_report_doc:
                report_audit = build_report(job_dir)
                report_audit_file = "report_audit.json"
                report_status = report_audit["status"]

    manifest = {
        "status": "success" if validation["status"] == "pass" else "validation_failed",
        "mode": "real_output_import",
        "source_dir": str(source_dir),
        "job_dir": str(job_dir),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "imported_files": imported,
        "skipped_files": skipped,
        "validation_file": "real_output_validation.json",
        "validation_status": validation["status"],
        "parse_status": parse_status,
        "report_status": report_status,
        "result_file": result_file,
        "report_audit_file": report_audit_file,
        "executed_ansys": False,
        "notes": ["This mode imports an already completed output directory and never launches ANSYS."],
    }
    _write_json(job_dir / "real_output_import.json", manifest)
    _write_json(job_dir / "imported_outputs_manifest.json", manifest)
    return manifest
