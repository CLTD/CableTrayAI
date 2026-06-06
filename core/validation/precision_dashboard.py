from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.optimizer.square_section_summary import write_square_section_selection_summary
from core.results.output_workspace import DEFAULT_OUTPUT_ROOT, publish_result_outputs
from core.results.result_assembler import assemble_result
from core.validation.result_requirements import classify_job_requirements


DEFAULT_BATCH_FILES = (
    Path("docs/precision_gate/intake_as_new_report_precision_batch.json"),
)
DEFAULT_DASHBOARD_DATA = Path("docs/precision_gate/precision_dashboard_data.json")
DEFAULT_DASHBOARD_DOC = Path("docs/WEB_DASHBOARD_AND_PRECISION_GATE.md")


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _percent(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric * 100.0


def _comparison_section(row: dict[str, Any]) -> str:
    mapping = str(row.get("mapping_source_ref") or "")
    metric_type = str(row.get("metric_type") or "")
    name = str(row.get("name") or "")
    source_file = str(row.get("result_source_file") or "")
    text = f"{mapping} {metric_type} {name} {source_file}"
    if "modal" in metric_type or "mode_" in name:
        return "附录A 模态分析结果"
    if "foundation" in metric_type or "foundation" in name or "JCZH" in source_file:
        return "第六章 支架基础载荷"
    if "bolt" in metric_type or "bolt" in name or "LS-FORCE" in source_file:
        return "第六章 支架连接螺栓载荷及螺栓应力评定"
    if "weld" in metric_type or "焊缝" in text or "HF-FORCE" in source_file:
        return "第六章 托臂根部焊缝评定"
    if "托臂" in text or "TMAXBEAMSTRESS" in source_file or "MAXBEAMSTRESS" in source_file:
        return "第六章 支架托臂应力评定"
    if "方钢" in text or "square" in metric_type or "SQUAREBEAMSTRESS" in source_file:
        return "第六章 支架方钢应力评定"
    return mapping or metric_type or "其它评定项"


def _display_name(row: dict[str, Any]) -> str:
    name = str(row.get("name") or "")
    if name:
        return name
    return str(row.get("mapping_source_ref") or row.get("metric_type") or "metric")


def _summarize_comparisons(job_dir: Path) -> dict[str, Any]:
    payload = _read_json(job_dir / "baseline_comparison.json", {})
    comparisons = list(payload.get("comparisons") or [])
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    max_row: dict[str, Any] | None = None
    for row in comparisons:
        gate_error = row.get("gate_error", row.get("relative_error"))
        if max_row is None or float(gate_error or 0.0) > float(max_row.get("gate_error", max_row.get("relative_error")) or 0.0):
            max_row = row
        groups[_comparison_section(row)].append(
            {
                "name": _display_name(row),
                "value": row.get("value"),
                "baseline": row.get("baseline"),
                "relative_error_percent": _percent(row.get("relative_error")),
                "absolute_error": row.get("absolute_error"),
                "gate_error_percent": _percent(gate_error),
                "tolerance_percent": _percent(row.get("tolerance")),
                "status": row.get("status"),
                "metric_type": row.get("metric_type"),
                "source_ref": row.get("source_ref"),
                "mapping_source_ref": row.get("mapping_source_ref"),
                "result_source_file": row.get("result_source_file"),
                "result_component_scope": row.get("result_component_scope"),
            }
        )

    section_payload = []
    for section, rows in sorted(groups.items()):
        failed = sum(1 for item in rows if item.get("status") != "pass")
        section_payload.append(
            {
                "section": section,
                "count": len(rows),
                "failed_count": failed,
                "max_gate_error_percent": max((float(item.get("gate_error_percent") or 0.0) for item in rows), default=0.0),
                "rows": rows,
            }
        )

    return {
        "status": payload.get("status") or "missing",
        "precision_verified": bool(payload.get("precision_verified")),
        "tolerance_percent": _percent(payload.get("tolerance")),
        "comparison_count": len(comparisons),
        "max_relative_error_percent": _percent(payload.get("max_relative_error")),
        "max_absolute_error": payload.get("max_absolute_error"),
        "max_gate_error_percent": _percent(payload.get("max_gate_error")),
        "max_error_row": {
            "name": _display_name(max_row or {}),
            "section": _comparison_section(max_row or {}),
            "gate_error_percent": _percent((max_row or {}).get("gate_error", (max_row or {}).get("relative_error"))),
            "status": (max_row or {}).get("status"),
        }
        if max_row
        else None,
        "sections": section_payload,
        "baseline_report": payload.get("baseline_report"),
        "baseline_file": payload.get("baseline_file"),
    }


def _summarize_figures(job_dir: Path) -> dict[str, Any]:
    figures = _read_json(job_dir / "figures_manifest.json", [])
    requirements = _read_json(job_dir / "result_requirements.json", {})
    appendix_counter = Counter(str(item.get("appendix") or "未分附录") for item in figures)
    scope_counter = Counter(str(item.get("component_scope") or "unknown") for item in figures)
    return {
        "status": "pass" if len(figures) >= len(requirements.get("required_figures") or []) else "warning",
        "count": len(figures),
        "required_count": len(requirements.get("required_figures") or []),
        "forbidden_count": len(requirements.get("forbidden_figures") or []),
        "appendix_counts": dict(sorted(appendix_counter.items())),
        "component_counts": dict(sorted(scope_counter.items())),
        "required_figures": requirements.get("required_figures") or [],
        "forbidden_figures": requirements.get("forbidden_figures") or [],
        "figures": [
            {
                "figure_id": item.get("figure_id"),
                "file": item.get("target_file") or item.get("path"),
                "published_file": f"figures/{Path(str(item.get('target_file') or item.get('path') or item.get('source_file') or '')).name}",
                "source_file": item.get("source_file"),
                "appendix": item.get("appendix"),
                "component_scope": item.get("component_scope"),
                "case": item.get("case") or item.get("load_case"),
                "stress_type": item.get("stress_type"),
            }
            for item in figures
        ],
        "requirements": requirements,
    }


def _load_batches(batch_paths: list[Path] | tuple[Path, ...]) -> list[dict[str, Any]]:
    batches = []
    for path in batch_paths:
        payload = _read_json(path, {})
        if not payload:
            continue
        payload = dict(payload)
        payload["path"] = str(path)
        batches.append(payload)
    return batches


def build_precision_dashboard_payload(
    *,
    batch_paths: list[Path] | tuple[Path, ...] = DEFAULT_BATCH_FILES,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    publish_outputs: bool = False,
) -> dict[str, Any]:
    batches = _load_batches(batch_paths)
    entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for batch in batches:
        for row in batch.get("results") or []:
            entries.append((batch, row))
    workspace_counts = Counter(str(row.get("workspace_id") or row.get("report_no") or "") for _, row in entries)
    cases: list[dict[str, Any]] = []
    publish_results: list[dict[str, Any]] = []
    for batch, row in entries:
        dataset = batch.get("dataset") or Path(str(batch.get("path"))).stem
        job_dir = Path(str(row.get("job_dir") or ""))
        workspace_id = str(row.get("workspace_id") or row.get("report_no") or job_dir.name)
        case_id = str(row.get("case_id") or "").strip()
        published_workspace_id = workspace_id
        if workspace_counts[workspace_id] > 1 and case_id and f"__case_{case_id}" not in workspace_id:
            published_workspace_id = f"{workspace_id}__case_{case_id}"
        case_payload: dict[str, Any] = {
            "dataset": dataset,
            "report_no": row.get("report_no"),
            "case_id": row.get("case_id"),
            "workspace_id": workspace_id,
            "published_workspace_id": published_workspace_id,
            "job_dir": str(job_dir),
            "status": row.get("status"),
            "ansys_status": row.get("ansys_status"),
            "comparison_status": row.get("comparison_status"),
            "comparison_count": row.get("comparison_count"),
            "max_relative_error_percent": _percent(row.get("max_relative_error")),
            "max_absolute_error": row.get("max_absolute_error"),
            "max_gate_error_percent": _percent(row.get("max_gate_error")),
            "modal_count": row.get("modal_count"),
            "beam_count": row.get("beam_count"),
            "weld_count": row.get("weld_count"),
            "bolt_count": row.get("bolt_count"),
            "foundation_count": row.get("foundation_count"),
            "failure_reason": row.get("failure_reason"),
        }
        if job_dir.exists():
            if publish_outputs:
                classify_job_requirements(job_dir)
                assemble_result(job_dir)
                publish_manifest = publish_result_outputs(
                    job_dir,
                    output_root=output_root,
                    intake_order_id=published_workspace_id,
                    overwrite=True,
                )
                publish_results.append(
                    {
                        "workspace_id": workspace_id,
                        "published_workspace_id": published_workspace_id,
                        "target_dir": publish_manifest.get("target_dir"),
                        "copied_count": len(publish_manifest.get("copied_files") or []),
                        "status": publish_manifest.get("status"),
                    }
                )
                case_payload["published_to"] = publish_manifest.get("target_dir")
            else:
                published = _read_json(job_dir / "published_results_manifest.json", {})
                case_payload["published_to"] = published.get("target_dir")
            case_payload["comparison"] = _summarize_comparisons(job_dir)
            case_payload["figures"] = _summarize_figures(job_dir)
            case_payload["square_section_selection"] = write_square_section_selection_summary(job_dir)
            command_manifest = _read_json(job_dir / "command_stream_manifest.json", {})
            case_payload["command_streams"] = command_manifest or {
                "command_stream_count": 3,
                "streams": [
                    {"role": "modeling", "file": "generated_model.mac", "exists": (job_dir / "generated_model.mac").exists()},
                    {"role": "calculation", "file": "generated_solve.mac", "exists": (job_dir / "generated_solve.mac").exists()},
                    {"role": "result_extraction", "file": "generated_post.mac", "exists": (job_dir / "generated_post.mac").exists()},
                ],
            }
        else:
            case_payload["comparison"] = {"status": "missing_job_dir", "sections": []}
            case_payload["figures"] = {"status": "missing_job_dir", "count": 0, "figures": []}
            case_payload["square_section_selection"] = {"status": "missing_job_dir"}
        cases.append(case_payload)

    max_gate_error_percent = max((float(case.get("max_gate_error_percent") or 0.0) for case in cases), default=0.0)
    failed = [case for case in cases if case.get("status") != "pass" or case.get("comparison_status") != "pass"]
    payload = {
        "status": "pass" if cases and not failed and max_gate_error_percent <= 1.0 else "fail",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tolerance_percent": 1.0,
        "case_count": len(cases),
        "passed_case_count": len(cases) - len(failed),
        "failed_case_count": len(failed),
        "max_gate_error_percent": max_gate_error_percent,
        "datasets": [
            {
                "dataset": batch.get("dataset"),
                "status": batch.get("status"),
                "case_count": batch.get("case_count"),
                "nproc": batch.get("nproc"),
                "path": batch.get("path"),
            }
            for batch in batches
        ],
        "cases": cases,
        "publish_results": publish_results,
        "notes": [
            "Precision is evaluated against report table values using baseline_comparison.json for every published case.",
            "The gate error is used for 1% acceptance because near-zero report values can make raw relative error meaningless.",
            "Only three command streams are published for engineering review: generated_model.mac, generated_solve.mac, generated_post.mac.",
            "Cantilever cloud output follows square tube outer width: <=120 mm publishes TB/TD, >120 mm uses weld evaluation principle and forbids TB/TD.",
        ],
    }
    return _json_safe(payload)


def write_precision_dashboard(
    *,
    output_path: Path | str = DEFAULT_DASHBOARD_DATA,
    output_root: Path | str = DEFAULT_OUTPUT_ROOT,
    batch_paths: list[Path] | tuple[Path, ...] = DEFAULT_BATCH_FILES,
    publish_outputs: bool = False,
) -> dict[str, Any]:
    payload = build_precision_dashboard_payload(batch_paths=batch_paths, output_root=output_root, publish_outputs=publish_outputs)
    output_path = Path(output_path)
    _write_json(output_path, payload)
    _write_dashboard_doc(payload, DEFAULT_DASHBOARD_DOC)
    return payload


def _write_dashboard_doc(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Web Dashboard And Precision Gate",
        "",
        f"- current_reference_batch: `{', '.join(str(path) for path in DEFAULT_BATCH_FILES)}`",
        f"- status: {payload.get('status')}",
        f"- case_count: {payload.get('case_count')}",
        f"- passed_case_count: {payload.get('passed_case_count')}",
        f"- failed_case_count: {payload.get('failed_case_count')}",
        f"- max_gate_error_percent: {payload.get('max_gate_error_percent')}",
        f"- tolerance_percent: {payload.get('tolerance_percent')}",
        "",
        "## Gate Policy",
        "",
        "- Standard command streams, deterministic/spec formulas, and job-local Excel authoritative evaluation are the production authority.",
        "- Historical reports are calibration and conflict-discovery references, not the sole authority.",
        "- Audited historical report conflicts remain visible in comparison data but are excluded from the historical numerical gate only after evidence is recorded.",
        "- Conflict exclusions never alter ANSYS output, formulas, Excel evaluation, or new-intake production logic.",
        "",
        "## Output Policy",
        "",
        "- The dashboard reads `docs/precision_gate/precision_dashboard_data.json` through the API endpoint `/dashboard-data`.",
        "- Published result folders use a clean review layout: `command_streams`, `tables`, `figures`, and `raw_results`.",
        "- Published result folders do not contain workflow JSON, Markdown, ANSYS `.out` logs, or `.err` logs.",
        "- The only `.mac` files in each published result folder are the three engineering review command streams: modeling, calculation, and result extraction.",
        "- Figure publishing follows `figures_manifest.json`; unrelated QA/signature or extra cloud images are not copied.",
        "- Square tube outer width `<= 120 mm` publishes TB/TD cantilever cloud figures. Width `> 120 mm` does not publish TB/TD and uses weld-evaluation-principle appendix mode.",
        "",
        "## Web UI Contest Position",
        "",
        "- The dashboard presents CableTrayAI as an AI-assisted engineering design and quality-control platform for the `人工智能工程设计应用` competition direction.",
        "- AI features are framed as intake parsing, rule audit, source traceability, anomaly diagnosis, economical-section suggestion, and source/report conflict review.",
        "- AI does not replace ANSYS, APDL, Excel, or confirmed formulas.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
