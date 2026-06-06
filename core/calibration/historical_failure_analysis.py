from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DOMAIN_LABELS = {
    "modal": "模态",
    "stress": "应力评定",
    "weld": "焊缝",
    "foundation_load": "基础载荷",
    "connection_bolt": "连接螺栓",
    "derived_ratio": "派生比值",
    "source_conflict": "历史报告/源文件冲突",
}


def _load_json(path: Path | str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def classify_failed_metric(item: dict[str, Any]) -> dict[str, str]:
    metric_type = str(item.get("metric_type") or "")
    source_file = str(item.get("result_source_file") or "")
    name = str(item.get("name") or "")

    if metric_type == "modal_frequency":
        return {
            "domain": "modal",
            "likely_cause": "模型拓扑、约束、质量或谱/静力方法与历史报告不同；模态频率不由后处理公式产生。",
            "code_boundary": "优先审查 generated_model.mac / generated_solve.mac 的 K/L/LATT/LMESH、D/CP/CPCYC、质量和支架层数。",
        }
    if metric_type == "foundation_load" or source_file == "JCZH.LIS":
        return {
            "domain": "foundation_load",
            "likely_cause": "基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。",
            "code_boundary": "审查 post_extract 的根部节点/组件、FSUM/PRRSOL 输出块、单位换算和工况包络顺序。",
        }
    if "connection" in metric_type or source_file.startswith("LS-FORCE"):
        return {
            "domain": "connection_bolt",
            "likely_cause": "托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。",
            "code_boundary": "审查 LS-FORCE.LIS 的连接组件、节点号映射、UPSET/FAULTED 工况和力矩基准点。",
        }
    if "weld" in metric_type or source_file == "HF-FORCE.LIS":
        return {
            "domain": "weld",
            "likely_cause": "焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。",
            "code_boundary": "审查 HF-FORCE.LIS 的托臂根部组件、焊缝尺寸、剪切/等效应力公式 source_ref。",
        }
    if "stress" in metric_type or source_file in {"MAXBEAMSTRESS.LIS", "TMAXBEAMSTRESS.LIS", "SQUAREBEAMSTRESS.LIS"}:
        return {
            "domain": "stress",
            "likely_cause": "梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。",
            "code_boundary": "审查 MAXBEAMSTRESS、TMAXBEAMSTRESS、SQUAREBEAMSTRESS 的组件来源、应力类型和报告 6.1/6.2 映射。",
        }
    if "ratio" in metric_type or "combination" in metric_type or name.startswith("combination."):
        return {
            "domain": "derived_ratio",
            "likely_cause": "派生比值依赖上游应力/载荷和许用值；通常不是独立后处理源。",
            "code_boundary": "先定位同一工况下的应力计算值和许用值 source_ref，再复核组合公式。",
        }
    return {
        "domain": "derived_ratio",
        "likely_cause": "未归类的派生指标偏差。",
        "code_boundary": "检查 comparison name、result.json 字段和报告表格映射。",
    }


def _top_failures(failures: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    def gate(item: dict[str, Any]) -> float:
        value = item.get("gate_error")
        if isinstance(value, (int, float)):
            return float(value)
        value = item.get("relative_error")
        return float(value) if isinstance(value, (int, float)) else 0.0

    rows: list[dict[str, Any]] = []
    for item in sorted(failures, key=gate, reverse=True)[:limit]:
        diagnosis = classify_failed_metric(item)
        rows.append(
            {
                "name": item.get("name"),
                "metric_type": item.get("metric_type"),
                "domain": diagnosis["domain"],
                "value": item.get("value"),
                "baseline": item.get("baseline"),
                "gate_error": item.get("gate_error"),
                "relative_error": item.get("relative_error"),
                "source_file": item.get("result_source_file"),
                "likely_cause": diagnosis["likely_cause"],
            }
        )
    return rows


def analyze_historical_validation(validation_path: Path | str) -> dict[str, Any]:
    validation_path = Path(validation_path)
    payload = _load_json(validation_path)
    root = validation_path.parent

    domain_counts: Counter[str] = Counter()
    metric_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    case_rows: list[dict[str, Any]] = []
    domain_cases: defaultdict[str, set[str]] = defaultdict(set)

    for row in payload.get("results") or []:
        if row.get("status") != "fail":
            continue
        selected_job = (row.get("selected_job") or {}).get("job_dir")
        comparison_path = Path(selected_job or "") / "baseline_comparison.json"
        if not comparison_path.exists():
            continue
        comparison = _load_json(comparison_path)
        failures = [
            item
            for item in comparison.get("comparisons") or []
            if item.get("status") not in {"pass", "baseline_conflict"}
        ]
        case_domain_counts: Counter[str] = Counter()
        for item in failures:
            diagnosis = classify_failed_metric(item)
            domain = diagnosis["domain"]
            domain_counts[domain] += 1
            case_domain_counts[domain] += 1
            domain_cases[domain].add(str(row.get("report_no")))
            metric_counts[str(item.get("metric_type") or "unknown")] += 1
            source_counts[str(item.get("result_source_file") or "none")] += 1
        case_rows.append(
            {
                "report_no": row.get("report_no"),
                "selected_job": selected_job,
                "max_gate_error": row.get("max_gate_error"),
                "failed_metric_count": len(failures),
                "domain_counts": dict(case_domain_counts),
                "top_failures": _top_failures(failures),
                "recommended_next_review": _recommended_next_review(case_domain_counts),
            }
        )

    conflict_checks: Counter[str] = Counter()
    conflict_spectrum_sources: Counter[str] = Counter()
    report_command_conflict_count = 0
    conflict_rows: list[dict[str, Any]] = []
    for row in payload.get("results") or []:
        if row.get("status") != "baseline_conflict":
            continue
        checks = row.get("failed_required_checks") or []
        report_features = ((row.get("representative_selection") or {}).get("report_features") or {})
        spectrum_source = report_features.get("spectrum_elevation_source")
        if spectrum_source:
            conflict_spectrum_sources[str(spectrum_source)] += 1
        if report_features.get("report_command_spectrum_conflict"):
            report_command_conflict_count += 1
        for check in checks:
            conflict_checks[str(check.get("check_id") or "unknown")] += 1
        conflict_rows.append(
            {
                "report_no": row.get("report_no"),
                "reason": row.get("failure_reason"),
                "failed_required_checks": checks,
                "spectrum_elevation_source": spectrum_source,
                "report_spectrum_elevations": report_features.get("report_spectrum_elevations") or [],
                "command_spectrum_elevations": report_features.get("command_spectrum_elevations") or [],
                "report_command_spectrum_conflict": bool(report_features.get("report_command_spectrum_conflict")),
                "command_spectrum_source_refs": (report_features.get("command_spectrum_source_refs") or [])[:3],
                "selected_job": (row.get("selected_job") or {}).get("job_dir"),
            }
        )

    return {
        "source_validation_json": str(validation_path),
        "validation_summary": {
            key: payload.get(key)
            for key in (
                "status",
                "report_case_count",
                "pass_count",
                "fail_count",
                "baseline_conflict_count",
                "blocked_count",
                "error_count",
                "max_gate_error",
            )
        },
        "policy": (
            "历史报告只作为后验校验和冲突发现依据；生产逻辑以标准命令流、规范公式、Excel 权威评定、"
            "真实 ANSYS 输出和 source_ref 为准。不能用报告数值硬凑结果。"
        ),
        "domain_summary": [
            {
                "domain": domain,
                "label": DOMAIN_LABELS.get(domain, domain),
                "failed_metric_count": count,
                "case_count": len(domain_cases.get(domain, set())),
                "cases": sorted(domain_cases.get(domain, set())),
            }
            for domain, count in domain_counts.most_common()
        ],
        "metric_counts": dict(metric_counts.most_common()),
        "source_counts": dict(source_counts.most_common()),
        "failed_cases": sorted(case_rows, key=lambda item: float(item.get("max_gate_error") or 0.0), reverse=True),
        "baseline_conflict_summary": {
            "count": len(conflict_rows),
            "failed_required_check_counts": dict(conflict_checks.most_common()),
            "spectrum_elevation_source_counts": dict(conflict_spectrum_sources.most_common()),
            "report_command_spectrum_conflict_count": report_command_conflict_count,
            "most_common_meaning": _conflict_meaning(conflict_checks),
        },
        "baseline_conflicts": conflict_rows,
        "output_root": str(root),
    }


def _recommended_next_review(domain_counts: Counter[str]) -> list[str]:
    ordered = [domain for domain, _ in domain_counts.most_common()]
    recommendations: list[str] = []
    for domain in ordered:
        if domain == "modal":
            recommendations.append("先审建模与约束：模态偏差优先级高于后处理。")
        elif domain == "stress":
            recommendations.append("审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。")
        elif domain == "weld":
            recommendations.append("审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。")
        elif domain == "foundation_load":
            recommendations.append("审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。")
        elif domain == "connection_bolt":
            recommendations.append("审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。")
        elif domain == "derived_ratio":
            recommendations.append("派生比值先追上游应力/载荷，再审许用值和组合公式。")
    return recommendations or ["无失败域。"]


def _conflict_meaning(counter: Counter[str]) -> str:
    if not counter:
        return "未记录冲突检查项。"
    if counter.get("spectrum_elevation_m", 0) >= max(counter.values()):
        return "主要冲突是历史报告或对应命令流采用多楼层包络谱/不同标高谱，而提资行只给出单一标高；需以命令流 source_ref 判定，不能用报告数值反推新提资谱选择。"
    return "主要冲突来自提资字段与历史报告结构参数不一致，应作为人工审查样例，不用于调参。"


def write_historical_failure_analysis(
    validation_path: Path | str,
    output_json: Path | str,
    output_md: Path | str,
) -> dict[str, Any]:
    analysis = analyze_historical_validation(validation_path)
    output_json = Path(output_json)
    output_md = Path(output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(_format_markdown(analysis), encoding="utf-8")
    return analysis


def _format_markdown(analysis: dict[str, Any]) -> str:
    summary = analysis.get("validation_summary") or {}
    lines = [
        "# Historical Batch Failure Review",
        "",
        "## 结论",
        "",
        f"- 状态：`{summary.get('status')}`",
        f"- 报告样例数：{summary.get('report_case_count')}",
        f"- 通过：{summary.get('pass_count')}",
        f"- 仍需排查：{summary.get('fail_count')}",
        f"- 已判为历史报告/源文件冲突：{summary.get('baseline_conflict_count')}",
        f"- 最大剩余门控误差：{summary.get('max_gate_error')}",
        "",
        analysis.get("policy") or "",
        "",
        "## 按问题域统计",
        "",
        "| 问题域 | 失败指标数 | 涉及报告 | 主要判断 |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in analysis.get("domain_summary") or []:
        lines.append(
            f"| {row.get('label')} | {row.get('failed_metric_count')} | {row.get('case_count')} | "
            f"{_domain_statement(str(row.get('domain')))} |"
        )
    lines.extend(
        [
            "",
            "## 历史报告/源文件冲突",
            "",
            f"- 冲突数：{(analysis.get('baseline_conflict_summary') or {}).get('count')}",
            f"- 主要含义：{(analysis.get('baseline_conflict_summary') or {}).get('most_common_meaning')}",
            f"- 检查项统计：`{json.dumps((analysis.get('baseline_conflict_summary') or {}).get('failed_required_check_counts') or {}, ensure_ascii=False)}`",
            f"- 谱标高证据来源：`{json.dumps((analysis.get('baseline_conflict_summary') or {}).get('spectrum_elevation_source_counts') or {}, ensure_ascii=False)}`",
            f"- 报告文字与命令流谱标高不一致数：{(analysis.get('baseline_conflict_summary') or {}).get('report_command_spectrum_conflict_count')}",
            "",
            "## 剩余失败样例",
            "",
        ]
    )
    for case in analysis.get("failed_cases") or []:
        lines.append(f"### {case.get('report_no')}")
        lines.append("")
        lines.append(f"- job：`{case.get('selected_job')}`")
        lines.append(f"- 最大门控误差：{case.get('max_gate_error')}")
        lines.append(f"- 失败指标数：{case.get('failed_metric_count')}")
        lines.append(f"- 域统计：`{json.dumps(case.get('domain_counts') or {}, ensure_ascii=False)}`")
        for recommendation in case.get("recommended_next_review") or []:
            lines.append(f"- 建议：{recommendation}")
        lines.append("")
        lines.append("| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |")
        lines.append("| --- | --- | ---: | ---: | ---: | --- | --- |")
        for item in case.get("top_failures") or []:
            lines.append(
                f"| `{item.get('name')}` | {DOMAIN_LABELS.get(item.get('domain'), item.get('domain'))} | "
                f"{item.get('value')} | {item.get('baseline')} | {item.get('gate_error')} | "
                f"{item.get('source_file')} | {item.get('likely_cause')} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _domain_statement(domain: str) -> str:
    if domain == "stress":
        return "优先看输出集合和表章节映射，不允许按接近值替代。"
    if domain == "foundation_load":
        return "优先看根部反力组件、谱/静力系数和力矩参考点。"
    if domain == "connection_bolt":
        return "优先看 LS-FORCE 托盘-托臂连接节点集。"
    if domain == "weld":
        return "优先看 HF-FORCE 根部载荷和焊缝公式输入。"
    if domain == "modal":
        return "优先看模型拓扑、质量和约束。"
    return "先追上游物理量，再审派生公式。"
