from __future__ import annotations

import json
import os
import re
import shutil
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.optimizer.square_section_summary import write_square_section_selection_summary

DEFAULT_OUTPUT_ROOT = Path(os.environ.get("CABLETRAYAI_OUTPUT_ROOT", "outputs"))
REVIEW_RAW_RESULT_FILES = {
    "SQUAREBEAMSTRESS.LIS",
    "MAXBEAMSTRESS.LIS",
    "TMAXBEAMSTRESS.LIS",
    "JCZH.LIS",
    "HF-FORCE.LIS",
    "LS-FORCE.LIS",
    "LS-FORCE-NODES.LIS",
    "Mode.oup",
}
AUDIT_COMMAND_STREAMS = (
    ("modeling", "generated_model.mac", True),
    ("calculation", "generated_solve.mac", True),
    ("result_extraction", "generated_post.mac", True),
    ("model_topology_manifest", "apdl_topology_manifest.json", False),
    ("tray_load_command_audit", "tray_load_command_audit.json", False),
    ("spectrum_full_audit", "ansys_spectrum.mac", False),
    ("spectrum_sl1_solve", "ansys_spectrum_sl1.mac", False),
    ("spectrum_sl2_solve", "ansys_spectrum_sl2.mac", False),
    ("spectrum_workbook_format_review", "ansys_spectrum_workbook_format.mac", False),
    ("residual_mass_static_correction", "ansys_zpa_parameters.mac", False),
    ("platform_standard_calculation_shadow", "platform_standard_solve.mac", False),
    ("platform_standard_result_extraction_shadow", "platform_standard_post.mac", False),
    ("platform_standard_numeric_extraction_shadow", "platform_standard_post_numeric.mac", False),
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_or_default(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def sanitize_order_id(value: str) -> str:
    text = str(value).strip()
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", "_", text)
    text = text.strip("._ ")
    return text or "unknown_order"


def intake_order_id_from_job(job_dir: Path | str, fallback: str | None = None) -> str:
    job_dir = Path(job_dir)
    fallback = fallback or job_dir.name
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return sanitize_order_id(fallback)
    payload = _read_json(input_path)
    metadata = payload.get("metadata") or {}
    for key in ("report_number", "calculation_batch", "intake_order_id", "intake_number", "order_id", "intake_row_id"):
        if metadata.get(key):
            return sanitize_order_id(str(metadata[key]))
    project = payload.get("project") or {}
    pieces = [project.get("project_code"), project.get("building"), project.get("area"), fallback]
    return sanitize_order_id("_".join(str(piece) for piece in pieces if piece))


def write_command_stream_manifest(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    streams = []
    for role, filename, required in AUDIT_COMMAND_STREAMS:
        path = job_dir / filename
        streams.append(
            {
                "role": role,
                "file": filename,
                "exists": path.exists(),
                "required": required,
                "audit_policy": (
                    "Model, solve, and post streams are required for every review publish. "
                    "Response-spectrum jobs also publish the generated spectrum and ZPA/static-correction streams "
                    "when present because they materially affect the calculation. Platform-standard shadow streams "
                    "are optional review artifacts for baseline comparison and are not production entrypoints yet."
                ),
            }
        )
    manifest = {
        "status": "pass" if all(item["exists"] for item in streams if item["required"]) else "warning",
        "job_dir": str(job_dir),
        "command_stream_count": len(streams),
        "published_command_stream_count": sum(1 for item in streams if item["exists"]),
        "streams": streams,
        "notes": [
            "run_all.mac remains an internal ANSYS batch entrypoint and is intentionally not part of the review publish set.",
            "The reviewed streams include modeling, calculation, result extraction, response-spectrum commands, and residual-mass/static-correction parameters when generated.",
            "platform_standard_* streams, when present, are shadow review/baseline streams and do not replace generated_solve.mac or generated_post_numeric.mac.",
        ],
    }
    (job_dir / "command_stream_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _clear_directory(target_dir: Path, output_root: Path) -> None:
    target_resolved = target_dir.resolve()
    output_resolved = output_root.resolve()
    if target_resolved == output_resolved or not target_resolved.is_relative_to(output_resolved):
        raise ValueError(f"Refusing to clean outside output root: {target_dir}")
    if not target_dir.exists():
        return
    for child in target_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _copy_file(source: Path, target: Path, copied: list[dict[str, Any]], category: str) -> None:
    if not source.exists() or not source.is_file():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    copied.append(
        {
            "category": category,
            "source": str(source),
            "target": str(target),
            "relative_target": target.name if target.parent == target.parent.parent else target.as_posix(),
            "name": target.name,
            "size": target.stat().st_size,
        }
    )


def _copy_manifest_figures(job_dir: Path, target_dir: Path, copied: list[dict[str, Any]]) -> list[dict[str, str]]:
    manifest_path = job_dir / "figures_manifest.json"
    if not manifest_path.exists():
        return []
    figures = json.loads(manifest_path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    published: list[dict[str, str]] = []
    for figure in figures:
        for key in ("target_file", "source_file", "path"):
            value = figure.get(key)
            if not value:
                continue
            source = job_dir / str(value)
            if source.exists() and source.is_file():
                break
        else:
            continue
        target = target_dir / "figures" / source.name
        unique_key = target.name.upper()
        if unique_key in seen:
            continue
        seen.add(unique_key)
        _copy_file(source, target, copied, "figure")
        published.append(
            {
                "figure_id": str(figure.get("figure_id") or ""),
                "source_file": str(figure.get("source_file") or source.name),
                "published_file": f"figures/{source.name}",
            }
        )
    return published


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict):
            for inner_key, inner_value in value.items():
                if isinstance(inner_value, dict):
                    for leaf_key, leaf_value in inner_value.items():
                        flat[f"{key}.{inner_key}.{leaf_key}"] = leaf_value
                else:
                    flat[f"{key}.{inner_key}"] = inner_value
        elif isinstance(value, list):
            flat[key] = json.dumps(value, ensure_ascii=False)
        else:
            flat[key] = value
    return flat


def _write_csv(path: Path, rows: list[dict[str, Any]], copied: list[dict[str, Any]], *, category: str = "table") -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    flat_rows = [_flatten_row(dict(row)) for row in rows]
    fieldnames: list[str] = []
    for row in flat_rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(flat_rows)
    copied.append({"category": category, "target": str(path), "name": path.name, "size": path.stat().st_size})


def _write_review_tables(job_dir: Path, target_dir: Path, copied: list[dict[str, Any]]) -> None:
    tables_dir = target_dir / "tables"
    _write_csv(tables_dir / "modal_results.csv", _read_json_or_default(job_dir / "modal_results.json", []), copied)
    _write_csv(tables_dir / "beam_stress_results.csv", _read_json_or_default(job_dir / "beam_stress_results.json", []), copied)
    _write_csv(tables_dir / "weld_force_results.csv", _read_json_or_default(job_dir / "weld_force_results.json", []), copied)
    _write_csv(tables_dir / "bolt_force_results.csv", _read_json_or_default(job_dir / "bolt_force_results.json", []), copied)
    _write_csv(tables_dir / "connection_node_force_results.csv", _read_json_or_default(job_dir / "connection_node_force_results.json", []), copied)
    _write_csv(tables_dir / "foundation_loads.csv", _read_json_or_default(job_dir / "foundation_loads.json", []), copied)
    square = _read_json_or_default(
        job_dir / "square_section_selection_summary.json",
        _read_json_or_default(job_dir / "square_section_selection.json", {}),
    )
    _write_csv(tables_dir / "square_section_selection.csv", [square] if square else [], copied)


def _write_readme(target_dir: Path, order_id: str, command_stream_manifest: dict[str, Any], square_section_selection: dict[str, Any], copied: list[dict[str, Any]]) -> None:
    lines = [
        f"CableTrayAI published result: {order_id}",
        "",
        "Folders:",
        "- command_streams: APDL command streams for engineering review, including spectrum and residual-mass/static-correction files when generated.",
        "- tables: CSV tables for result/report comparison and extracted values.",
        "- figures: only figures required by the current intake/report logic.",
    "- raw_results: canonical LIS/OUP files used by result extraction.",
        "- reports: generated template report files, when report injection has been run.",
        "",
        "Not published here:",
        "- JSON workflow files, markdown reports, ANSYS .out logs, and .err logs.",
        "- Those files remain in the job workspace for traceability.",
        "",
        f"Command stream count: {command_stream_manifest.get('command_stream_count')}",
        f"Square section: {square_section_selection.get('section_name')}",
        f"Square outer width mm: {square_section_selection.get('outer_mm')}",
        f"Square thickness mm: {square_section_selection.get('thickness_mm')}",
        f"Controlling ratio: {square_section_selection.get('controlling_ratio')}",
        f"Published at: {datetime.now(timezone.utc).isoformat()}",
    ]
    path = target_dir / "README.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    copied.append({"category": "index", "target": str(path), "name": path.name, "size": path.stat().st_size})


def publish_result_outputs(
    job_dir: Path | str,
    *,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    intake_order_id: str | None = None,
    overwrite: bool = True,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    if not job_dir.exists():
        raise FileNotFoundError(f"Job directory does not exist: {job_dir}")
    output_root = Path(output_root)
    order_id = sanitize_order_id(intake_order_id or intake_order_id_from_job(job_dir))
    target_dir = output_root / order_id
    if overwrite:
        _clear_directory(target_dir, output_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    command_stream_manifest = write_command_stream_manifest(job_dir)
    square_section_selection = write_square_section_selection_summary(job_dir)

    copied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for role, filename, _required in AUDIT_COMMAND_STREAMS:
        _copy_file(job_dir / filename, target_dir / "command_streams" / filename, copied, f"command_stream:{role}")
    figure_publications = _copy_manifest_figures(job_dir, target_dir, copied)
    _write_review_tables(job_dir, target_dir, copied)
    report_names = []
    for report_path in sorted(job_dir.glob("*.docx")):
        if report_path.name.lower().endswith(".docx"):
            _copy_file(report_path, target_dir / "reports" / report_path.name, copied, "report")
            report_names.append(f"reports/{report_path.name}")
    for filename in REVIEW_RAW_RESULT_FILES:
        _copy_file(job_dir / filename, target_dir / "raw_results" / filename, copied, "raw_result")
    _write_readme(target_dir, order_id, command_stream_manifest, square_section_selection, copied)

    manifest = {
        "status": "pass" if copied else "warning",
        "job_dir": str(job_dir),
        "output_root": str(output_root),
        "intake_order_id": order_id,
        "target_dir": str(target_dir),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "command_stream_manifest": command_stream_manifest,
        "square_section_selection": square_section_selection,
        "figure_publications": figure_publications,
        "report_publications": report_names,
        "copied_files": copied,
        "skipped_files": skipped,
        "notes": [
            "This output folder is a clean engineering-review publish copy; source_materials is never modified.",
            "JSON, markdown, .out logs, and .err logs are intentionally not published here.",
            "Full trace files remain in the job workspace.",
        ],
    }
    (job_dir / "published_results_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest
