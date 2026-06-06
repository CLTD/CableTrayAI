from __future__ import annotations

from collections import defaultdict
from typing import Any

from core.report.template_injector import _condition_rows, choose_report_template
from core.validation.analysis_scope import classify_scope_from_input


def _metric_number(value: Any) -> float | None:
    if isinstance(value, dict):
        return _metric_number(value.get("value", value.get("normalized_value", value.get("raw_value"))))
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_number(value: Any, digits: int = 1) -> str:
    number = _metric_number(value)
    if number is None:
        return "-"
    if abs(number) < 1e-12:
        return "0"
    text = f"{number:.{digits}f}"
    if float(text) == 0.0:
        text = f"{number:.6g}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _load_title(scope: str) -> str:
    if scope == "weld_root":
        return "6.2 托臂根部所受载荷"
    if scope == "foundation":
        return "6.3 支架基础载荷"
    if scope in {"bolt_connection", "connection_nodes"}:
        return "6.4 支架连接螺栓载荷"
    return "6.x 其它载荷提取"


def _node_display(row: dict[str, Any]) -> str:
    node = str(row.get("node") or row.get("keypoint") or row.get("node_id") or "").strip()
    if node and node.upper() != "UNKNOWN":
        return node
    keypoints = row.get("source_keypoints")
    if isinstance(keypoints, list) and keypoints:
        values = [str(item) for item in keypoints if item not in (None, "")]
        return "KP " + ", ".join(values[:12]) + (f" 等{len(values)}点" if len(values) > 12 else "")
    block = row.get("source_block")
    if block:
        return str(block)
    return "未解析到节点"


def _stress_table(title: str, rows: list[list[Any]]) -> dict[str, Any]:
    return {
        "kind": "stress",
        "title": title,
        "columns": ["工况", "应力类型", "计算值(MPa)", "许用值(MPa)", "应力比"],
        "rows": rows,
        "row_count": len(rows),
    }


def _load_table(title: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "kind": "load",
        "title": title,
        "columns": ["工况", "节点/关键点", "FX(N)", "FY(N)", "FZ(N)", "MY(Nm)", "MZ(Nm)", "来源"],
        "rows": [
            [
                row.get("load_case") or "-",
                row.get("node_display") or _node_display(row),
                _fmt_number(row.get("fx")),
                _fmt_number(row.get("fy")),
                _fmt_number(row.get("fz")),
                _fmt_number(row.get("my")),
                _fmt_number(row.get("mz")),
                row.get("source_file") or "-",
            ]
            for row in rows
        ],
        "row_count": len(rows),
    }


def _bolt_condition(check_id: str) -> str:
    lowered = check_id.lower()
    if "faulted" in lowered:
        return "事故"
    if "upset" in lowered:
        return "异常"
    return "-"


def _bolt_stress_type(check_id: str, category: Any) -> str:
    lowered = check_id.lower()
    if "combined" in lowered:
        return "拉剪组合"
    if "tension" in lowered:
        return "拉伸应力"
    if "shear" in lowered:
        return "剪切应力"
    return str(category or check_id)


def _bolt_stress_table(evaluation: list[dict[str, Any]]) -> dict[str, Any] | None:
    order = {"upset": 0, "faulted": 1, "tension": 0, "shear": 1, "combined": 2}
    rows: list[dict[str, Any]] = []
    for item in evaluation:
        check_id = str(item.get("check_id") or "")
        if "bolt" not in check_id.lower() or item.get("ratio") is None:
            continue
        rows.append(item)
    if not rows:
        return None

    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        check_id = str(item.get("check_id") or "").lower()
        condition_rank = 9
        type_rank = 9
        for key, value in order.items():
            if key in check_id and key in {"upset", "faulted"}:
                condition_rank = value
            if key in check_id and key in {"tension", "shear", "combined"}:
                type_rank = value
        return condition_rank, type_rank, check_id

    return {
        "kind": "stress",
        "title": "6.4 支架螺栓应力评定表（MPa）",
        "columns": ["工况", "应力类型", "计算值(MPa)", "许用值(MPa)", "应力比"],
        "rows": [
            [
                _bolt_condition(str(item.get("check_id") or "")),
                _bolt_stress_type(str(item.get("check_id") or ""), item.get("category")),
                _fmt_number(item.get("calculation_value"), 3),
                _fmt_number(item.get("allowable_value"), 3),
                _fmt_number(item.get("ratio"), 3),
            ]
            for item in sorted(rows, key=sort_key)
        ],
        "row_count": len(rows),
    }


def _weld_condition(check_id: str) -> str:
    lowered = check_id.lower()
    if "faulted" in lowered:
        return "事故"
    if "upset" in lowered:
        return "异常"
    return "-"


def _weld_stress_type(check_id: str, category: Any) -> str:
    lowered = check_id.lower()
    if "equivalent" in lowered:
        return "焊缝等效应力"
    if "shear" in lowered:
        return "焊缝剪切"
    return str(category or check_id)


def _weld_stress_table(evaluation: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [
        item
        for item in evaluation
        if "weld" in str(item.get("check_id") or "").lower() and item.get("ratio") is not None
    ]
    if not rows:
        return None

    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        check_id = str(item.get("check_id") or "").lower()
        condition_rank = 0 if "upset" in check_id else 1 if "faulted" in check_id else 9
        type_rank = 0 if "shear" in check_id else 1 if "equivalent" in check_id else 9
        return condition_rank, type_rank, check_id

    return {
        "kind": "stress",
        "title": "6.3 托臂根部焊缝评定结果（应力比）",
        "columns": ["工况", "应力类型", "计算值(MPa)", "许用值(MPa)", "应力比"],
        "rows": [
            [
                _weld_condition(str(item.get("check_id") or "")),
                _weld_stress_type(str(item.get("check_id") or ""), item.get("category")),
                _fmt_number(item.get("calculation_value"), 3),
                _fmt_number(item.get("allowable_value"), 3),
                _fmt_number(item.get("ratio"), 3),
            ]
            for item in sorted(rows, key=sort_key)
        ],
        "row_count": len(rows),
    }


def _weld_equivalent_table_621(evaluation: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = [
        item
        for item in evaluation
        if str(item.get("check_id") or "").startswith("cantilever_root_weld_equivalent.")
        and item.get("ratio") is not None
    ]
    if not rows:
        return None
    condition_rank = {"normal_abnormal": 0, "accident": 1}
    type_rank = {"SDIR_TENSION": 0, "SDIR_COMPRESSION": 1, "SBEND": 2, "SHEAR": 3}

    def sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        return (
            condition_rank.get(str(item.get("load_case_group") or ""), 9),
            type_rank.get(str(item.get("stress_type") or "").upper(), 9),
            str(item.get("check_id") or ""),
        )

    return {
        "kind": "stress",
        "title": "6.2-1 托臂根部焊缝评定结果（应力比）",
        "columns": ["工况", "应力类型", "计算值(MPa)", "等效应力(MPa)", "许用值(MPa)", "应力比"],
        "rows": [
            [
                item.get("load_case_group_label") or _weld_condition(str(item.get("check_id") or "")),
                item.get("category") or "-",
                _fmt_number(item.get("calculation_value"), 3),
                _fmt_number(item.get("equivalent_stress_value"), 3),
                _fmt_number(item.get("allowable_value"), 3),
                _fmt_number(item.get("ratio"), 3),
            ]
            for item in sorted(rows, key=sort_key)
        ],
        "row_count": len(rows),
        "source_policy": "TMAXBEAMSTRESS.LIS / 0.526; applies when square tube outer width <= 120 mm.",
    }


def build_chapter6_display_tables(
    *,
    input_payload: dict[str, Any],
    result: dict[str, Any],
    evaluation: list[dict[str, Any]],
    scope: dict[str, Any] | None = None,
    load_extractions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return the same chapter-six table payload the operator should see.

    The browser uses this payload instead of recomputing report rows in
    JavaScript.  This keeps the web page and Word-template injection aligned and
    prevents display-only logic from drifting away from the deterministic
    result/Excel/source_ref chain.
    """

    scope = scope or classify_scope_from_input(input_payload)
    mode = choose_report_template(input_payload)["mode"]
    requires = scope.get("requires") or {}
    square_outer_width = scope.get("square_outer_width_mm")
    large_square_weld_principle = isinstance(square_outer_width, (int, float)) and float(square_outer_width) > 120.0
    equivalent_weld_branch = bool(requires.get("cantilever_root_weld_equivalent_stress_table"))

    if mode == "steel_platform":
        if large_square_weld_principle:
            stress_mapping = [("表 6-1-1 支架应力评定", "mixed_beam_type_1"), ("表 6-1-2 支架方钢应力评定", "square_support")]
        else:
            stress_mapping = [("表 6-1-1 支架方钢应力评定", "square_support"), ("表 6-1-2 托臂应力评定", "cantilever_arm")]
    else:
        stress_mapping = [("表 6-1-1 · 支架应力评定", "mixed_beam_type_1")]

    tables: list[dict[str, Any]] = []
    for title, component in stress_mapping:
        candidates = [component]
        if component == "mixed_beam_type_1":
            candidates.extend(["square_support", "support"])
        elif component == "cantilever_arm":
            candidates.append("mixed_beam_type_1")
        for candidate in candidates:
            rows = _condition_rows(candidate, result, evaluation)
            if rows:
                table = _stress_table(title, rows)
                table["component"] = candidate
                tables.append(table)
                break

    grouped_loads: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in load_extractions or []:
        grouped_loads[str(row.get("scope") or "")].append(row)
    for scope_name in ("weld_root", "foundation", "bolt_connection", "connection_nodes"):
        if scope_name == "weld_root" and equivalent_weld_branch:
            continue
        rows = grouped_loads.get(scope_name) or []
        if scope_name == "weld_root" and not requires.get("cantilever_root_weld_eval") and not rows:
            continue
        if not rows:
            continue
        tables.append(_load_table(_load_title(scope_name), rows))
        if scope_name == "weld_root":
            weld_stress = _weld_stress_table(evaluation)
            if weld_stress:
                tables.append(weld_stress)
        if scope_name == "bolt_connection":
            bolt_stress = _bolt_stress_table(evaluation)
            if bolt_stress:
                tables.append(bolt_stress)
    if equivalent_weld_branch:
        weld_equivalent = _weld_equivalent_table_621(evaluation)
        if weld_equivalent:
            insert_at = 1 if tables else 0
            tables.insert(insert_at, weld_equivalent)
    return tables
