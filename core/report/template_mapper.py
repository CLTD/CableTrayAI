from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReportFieldMapping:
    section: str
    table_or_figure: str
    result_path: str | None
    figures_path: str | None
    source_ref: str


REPORT_FIELD_MAPPINGS = [
    ReportFieldMapping("材料参数", "材料参数表", "input.materials", None, "input.json:materials"),
    ReportFieldMapping("结构设计参数", "结构设计参数", "input.support", None, "input.json:support"),
    ReportFieldMapping("工况", "工况表", "input.load_cases", None, "input.json:load_cases"),
    ReportFieldMapping("支架评定", "支架评定表", "result.evaluation_summary", None, "result.json:evaluation_summary"),
    ReportFieldMapping("焊缝评定", "焊缝评定表", "result.evaluation_summary", None, "result.json:evaluation_summary"),
    ReportFieldMapping("基础载荷", "基础载荷表", "result.foundation_loads", None, "result.json:foundation_loads"),
    ReportFieldMapping("螺栓载荷", "螺栓载荷表", "result.bolt_force_results", None, "result.json:bolt_force_results"),
    ReportFieldMapping("螺栓评定", "螺栓评定表", "result.evaluation_summary", None, "result.json:evaluation_summary"),
    ReportFieldMapping("模态", "模态频率表", "result.modal_results", None, "result.json:modal_results"),
    ReportFieldMapping("附录A", "模态图", None, "figures[figure_type=modal]", "figures_manifest.json"),
    ReportFieldMapping("附录B", "应力图", None, "figures[figure_type=stress]", "figures_manifest.json"),
    ReportFieldMapping("结论", "结论", "result.evaluation_summary", None, "result.json:evaluation_summary"),
]


def resolve_path(payload: dict[str, Any], dotted_path: str) -> Any:
    current: Any = payload
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(dotted_path)
    return current


def validate_report_mapping(result: dict, input_payload: dict, figures: list[dict]) -> list[dict]:
    root = {"result": result, "input": input_payload}
    checks: list[dict] = []
    for mapping in REPORT_FIELD_MAPPINGS:
        status = "pass"
        detail = "ok"
        if mapping.result_path:
            try:
                resolve_path(root, mapping.result_path)
            except KeyError:
                status = "fail"
                detail = f"Missing {mapping.result_path}"
        if mapping.figures_path:
            if "modal" in mapping.figures_path:
                matched = [figure for figure in figures if figure.get("figure_type") == "modal" or figure.get("category") == "modal"]
            elif "stress" in mapping.figures_path:
                matched = [figure for figure in figures if figure.get("figure_type") == "stress" or figure.get("category") == "stress"]
            else:
                matched = figures
            if not matched:
                status = "fail"
                detail = f"No figures matched {mapping.figures_path}"
        checks.append(
            {
                "section": mapping.section,
                "table_or_figure": mapping.table_or_figure,
                "result_path": mapping.result_path,
                "figures_path": mapping.figures_path,
                "source_ref": mapping.source_ref,
                "status": status,
                "detail": detail,
            }
        )
    return checks
