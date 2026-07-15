from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from core.intake.tray_load_parser import parse_tray_load_description


STANDARD_CHAT_SQUARE_SECTIONS = [
    "100-100-6",
    "100-100-8",
    "120-120-6",
    "120-120-8",
    "120-120-10",
    "140-140-8",
    "160-160-8",
]

REQUIRED_CHAT_FIELDS = [
    "project_code",
    "building",
    "elevation",
    "description",
    "support_spacing_m",
    "support_height_m",
    "allowed_square_section_ids",
]


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def _cn_number_to_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    digits = {
        "零": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if text == "十":
        return 10
    if text.startswith("十") and len(text) == 2 and text[1] in digits:
        return 10 + digits[text[1]]
    if text.endswith("十") and len(text) == 2 and text[0] in digits:
        return digits[text[0]] * 10
    if "十" in text:
        left, right = text.split("十", 1)
        if left in digits and right in digits:
            return digits[left] * 10 + digits[right]
    if text in digits:
        return digits[text]
    return None


def _normalise_layer_text(text: str) -> str:
    def replace_count(match: re.Match[str]) -> str:
        number = _cn_number_to_int(match.group(1))
        return f"{number}层" if number is not None else match.group(0)

    normalised = re.sub(r"([一二两三四五六七八九十]+)\s*层", replace_count, text)
    normalised = normalised.replace("双层", "2层").replace("两层", "2层")
    normalised = normalised.replace("单层", "1层")
    return normalised


def _first_float(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        try:
            return float(match.group(1))
        except (TypeError, ValueError):
            continue
    return None


def _first_text(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        value = match.group(1).strip(" ：:，,；;。.\n\t")
        if value:
            return value
    return None


def _report_number(text: str) -> str | None:
    match = re.search(r"\b(\d{4,5}NI[-_]?LXSJ\d{3,6})\b", text, flags=re.I)
    if match:
        return match.group(1).replace("_", "-").upper()
    match = re.search(r"\b(18185NI[-_]?LXSJ\d{3,6})\b", text, flags=re.I)
    return match.group(1).replace("_", "-").upper() if match else None


def _project_code(text: str, report_number: str | None) -> str | None:
    explicit = _first_text(
        [
            r"(?:项目号|项目代码|项目|工程号)\s*[:：]?\s*([A-Za-z0-9_-]{4,20})",
            r"\b(project|proj)\s*[:：=]\s*([A-Za-z0-9_-]{4,20})",
        ],
        text,
    )
    if explicit:
        if explicit.lower() in {"project", "proj"}:
            match = re.search(r"\b(?:project|proj)\s*[:：=]\s*([A-Za-z0-9_-]{4,20})", text, flags=re.I)
            return match.group(1) if match else None
        return explicit
    if report_number and re.match(r"\d{4}", report_number):
        return report_number[:4]
    match = re.search(r"\b(\d{4})\b", text)
    return match.group(1) if match else None


def _building(text: str) -> str | None:
    patterns = [
        r"(?<![A-Za-z0-9_\-\u4e00-\u9fff])([A-Za-z0-9_\-]{1,24}|[\u4e00-\u9fff]{1,12})\s*(?:厂房|厂区|区域)",
        r"(?:厂房|厂区|谱表|区域)\s*[:：]\s*([A-Za-z0-9_\-\u4e00-\u9fff]+)",
        r"(?:厂房|厂区|谱表|区域)\s+(?:为|是)?\s*([A-Za-z0-9_\-]{1,24}|[\u4e00-\u9fff]{1,12})",
        r"(?:厂房|厂区|谱表|区域)\s*([A-Za-z0-9_\-]{1,24}|[\u4e00-\u9fff]{1,12})",
    ]
    value = None
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if not match:
            continue
        value = match.group(1).strip(" ：:，,；;。.\n\t")
        if value:
            break
    if not value:
        return None
    value = re.sub(r"(?:厂房|厂区|区域|谱表)$", "", value).strip()
    if re.match(r"^(?:标高|生根|楼层|单侧|双侧|两侧|三侧|间距|跨距|托盘|方钢|支架)", value):
        return None
    return value or None


def _spectrum_file_from_payload(payload: dict[str, Any], text: str) -> str | None:
    direct = payload.get("spectrum_file") or payload.get("spectrum_path")
    if direct:
        return str(direct).strip()
    for item in payload.get("attachments") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or item.get("file_path") or "")
        if path.lower().endswith((".xlsm", ".xlsx")):
            return path
    match = re.search(r"([A-Za-z]:\\[^\n\r;；,，]+?\.(?:xlsm|xlsx))", text, flags=re.I)
    if match:
        return match.group(1).strip()
    match = re.search(r"((?:uploads|\.{0,2}/)[^\n\r;；,，]+?\.(?:xlsm|xlsx))", text, flags=re.I)
    return match.group(1).strip() if match else None


def _extract_square_sections(text: str, *, allow_standard: bool) -> tuple[list[str], str | None, str]:
    found: list[str] = []
    for match in re.finditer(
        r"(?<!\d)(\d{2,3})\s*[-*xX×]\s*(\d{2,3})\s*[-*xX×]\s*(\d{1,2})(?!\d)",
        text,
    ):
        first, second, third = (int(value) for value in match.groups())
        if first != second:
            continue
        section = f"{first}-{second}-{third}"
        if section not in found:
            found.append(section)
    for match in re.finditer(r"(?<!\d)(\d{2,3})\s*[-*xX×]\s*(\d{1,2})(?!\d)", text):
        outer, thickness = (int(value) for value in match.groups())
        if outer < 50 or thickness > 20:
            continue
        section = f"{outer}-{outer}-{thickness}"
        if section not in found:
            found.append(section)
    if found:
        return found, "chat_message_explicit_square_sections", "provided_by_chat_message"
    if allow_standard:
        return (
            list(STANDARD_CHAT_SQUARE_SECTIONS),
            "operator_confirmed_standard_chat_square_section_list",
            "operator_confirmed_standard_chat_square_section_list",
        )
    return [], None, "missing_required"


def _extract_tray_description(text: str) -> tuple[str | None, dict[str, Any] | None, str | None]:
    normalised = _normalise_layer_text(text)
    side_match = re.search(r"(单侧|双侧|两侧|三侧)", normalised)
    if not side_match:
        return None, None, "missing side keyword: 单侧/双侧/两侧/三侧"
    tail = normalised[side_match.start() :]
    fragment = re.split(
        r"(?:\n|。|；|;|，|,|支架间距|间距|跨距|托盘长度|桥架跨度|跨度|方钢长度|支架高度|立柱长度|H1)",
        tail,
        maxsplit=1,
    )[0].strip()
    width_match = re.search(r"(600|500|300|200|100|50)", fragment)
    if not width_match:
        return None, None, "missing tray width: 600/500/300/200/100/50"
    try:
        parsed = parse_tray_load_description(fragment)
    except Exception as exc:
        return fragment, None, str(exc)
    return fragment, parsed, None


def parse_chat_intake(payload: dict[str, Any]) -> dict[str, Any]:
    message = _clean_text(payload.get("message") or payload.get("text") or payload.get("prompt"))
    if not message:
        return {
            "status": "blocked",
            "missing_fields": ["message"],
            "prompts": ["请输入支架提资描述，例如：项目1818，NR厂房，标高8.5m，双侧2+2层600，间距2m，方钢长度1.8m。"],
        }
    text = _normalise_layer_text(message)
    detected_reference_number = _report_number(text)
    explicit_formal_report_number = (
        str(payload.get("report_number") or "").strip()
        if bool(payload.get("allow_formal_report_number"))
        else ""
    ) or None
    report_number = explicit_formal_report_number
    project_code = str(payload.get("project_code") or _project_code(text, detected_reference_number) or "").strip() or None
    building = str(payload.get("building") or _building(text) or "").strip() or None
    area = str(payload.get("area") or building or "").strip() or None
    elevation = payload.get("elevation")
    if elevation in (None, ""):
        elevation = _first_float(
            [
                r"(?:标高|生根层|生根|楼层|EL|el|\+)\s*([-+]?\d+(?:\.\d+)?)\s*(?:m|米)?",
                r"(?:高度)\s*([-+]?\d+(?:\.\d+)?)\s*(?:m|米)",
            ],
            text,
        )
    support_spacing = payload.get("support_spacing_m")
    if support_spacing in (None, ""):
        support_spacing = _first_float(
            [
                r"(?:支架间距|间距|跨距|托盘长度|桥架跨度|跨度)\s*[:：]?\s*([-+]?\d+(?:\.\d+)?)\s*(?:m|米)?",
            ],
            text,
        )
    support_height = payload.get("support_height_m")
    if support_height in (None, ""):
        support_height = _first_float(
            [
                r"(?:方钢长度|支架高度|立柱长度|H1)\s*[:：]?\s*([-+]?\d+(?:\.\d+)?)\s*(?:m|米)?",
            ],
            text,
        )
    damping_ratio = payload.get("damping_ratio")
    if damping_ratio in (None, ""):
        damping_ratio = _first_float([r"(?:阻尼比|阻尼)\s*[:：]?\s*([-+]?\d+(?:\.\d+)?)\s*%?"], text)
        if damping_ratio and damping_ratio > 1:
            damping_ratio = float(damping_ratio) / 100.0
    if damping_ratio in (None, ""):
        damping_ratio = 0.10
    material = str(payload.get("material") or "Q355").strip()
    support_type = str(payload.get("support_type") or _first_text([r"\b(S\d+[A-Za-z]?)\b"], text) or "S2").strip()
    analysis_method = str(payload.get("analysis_method") or "").strip().lower()
    if not analysis_method:
        analysis_method = "static" if re.search(r"静力|钢平台", text) else "response_spectrum"
    tray_description, tray_mapping, tray_error = _extract_tray_description(text)
    spectrum_file = _spectrum_file_from_payload(payload, text)
    allowed_sections, allowed_source_ref, allowed_status = _extract_square_sections(
        text,
        allow_standard=bool(payload.get("use_standard_square_sections") or payload.get("allow_standard_square_sections")),
    )
    if payload.get("allowed_square_section_ids"):
        allowed_sections = [str(item) for item in payload.get("allowed_square_section_ids") or [] if str(item).strip()]
        allowed_source_ref = "chat_payload_allowed_square_section_ids"
        allowed_status = "provided_by_chat_payload"

    stable_hash = hashlib.sha1(message.encode("utf-8")).hexdigest()[:10]
    if not report_number:
        report_number = f"CHAT-{datetime.now().strftime('%Y%m%d')}-{stable_hash}"
    raw_intake_row = {"chat_message": message}
    if detected_reference_number:
        raw_intake_row["detected_reference_number"] = detected_reference_number
    intake_payload: dict[str, Any] = {
        "project_code": project_code,
        "building": building,
        "area": area,
        "elevation": elevation,
        "elevation_raw": elevation,
        "damping_ratio": damping_ratio,
        "material": material,
        "support_type": support_type,
        "support_spacing_m": support_spacing,
        "support_height_m": support_height,
        "description": tray_description,
        "report_number": report_number,
        "calculation_batch": report_number,
        "intake_order_id": report_number,
        "provisional_intake_id": f"chat_{stable_hash}",
        "intake_identity_status": "formal_report_number_provided" if explicit_formal_report_number else "chat_generated_request_id",
        "support_id": payload.get("support_id"),
        "analysis_method": analysis_method,
        "allowed_square_section_ids": allowed_sections,
        "allowed_square_section_source_ref": allowed_source_ref,
        "allowed_square_section_status": allowed_status,
        "raw_intake_row": raw_intake_row,
    }
    missing = [field for field in REQUIRED_CHAT_FIELDS if intake_payload.get(field) in (None, "", [])]
    if analysis_method != "static" and not spectrum_file:
        missing.append("spectrum_file")
    if not tray_mapping:
        if "description" not in missing:
            missing.append("description")
    prompts = _missing_prompts(missing)
    warnings: list[str] = []
    if tray_error:
        warnings.append(f"托盘描述解析失败：{tray_error}")
    if allowed_status.startswith("operator_confirmed"):
        warnings.append("已采用对话界面确认的单位默认候选方钢清单；最终截面仍需 ANSYS 和确定性评定通过。")
    if damping_ratio == 0.10 and "阻尼" not in text:
        warnings.append("未识别到阻尼比，按 SL-2 常用 10% 阻尼预填；正式运行前可修改。")
    status = "pass" if not missing else "blocked"
    return {
        "status": status,
        "message": message,
        "intake_payload": {key: value for key, value in intake_payload.items() if value not in (None, "")},
        "spectrum_file": spectrum_file,
        "missing_fields": missing,
        "prompts": prompts,
        "warnings": warnings,
        "tray_mapping": tray_mapping,
        "parse_policy": {
            "authority": "AI/chat only prepares an auditable intake row; ANSYS and deterministic gates remain authoritative.",
            "source": "deterministic_chat_parser_with_optional_operator_confirmed_square_section_list",
        },
    }


def _missing_prompts(missing: list[str]) -> list[str]:
    labels = {
        "project_code": "项目号，例如 1818。",
        "building": "厂房/区域，例如 NR 或 NS环形区。",
        "elevation": "生根标高，例如 标高8.5m。",
        "description": "桥架布置，例如 单侧2层600 或 双侧2+2层500。",
        "support_spacing_m": "支架间距/托盘长度，例如 间距2m。",
        "support_height_m": "方钢长度/支架高度，例如 方钢长度1.8m。",
        "allowed_square_section_ids": "允许参与选型的方钢截面，例如 100x8、120x8、140x8；或勾选单位默认候选清单。",
        "spectrum_file": "反应谱 Excel/XLSM 文件路径，或上传谱文件。",
        "message": "对话提资文字。",
    }
    return [labels.get(field, field) for field in missing]


def write_chat_intake_workbook(
    draft: dict[str, Any],
    *,
    output_dir: Path | str,
) -> dict[str, Any]:
    if draft.get("status") != "pass":
        raise ValueError(f"Chat intake is incomplete: {draft.get('missing_fields')}")
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("openpyxl is required to write chat intake workbooks") from exc
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(draft["intake_payload"])
    report_number = str(payload.get("report_number") or "chat_intake")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", report_number).strip("._") or "chat_intake"
    path = output_dir / f"{safe_name}.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "chat_intake"
    headers = [
        "serial",
        "report_number",
        "support_type",
        "support_spacing_m",
        "support_height_m",
        "description",
        "building",
        "area",
        "elevation",
        "support_id",
        "project_code",
        "damping_ratio",
        "material",
        "analysis_method",
    ]
    sheet.append(headers)
    sheet.append([1, *[payload.get(header) for header in headers[1:]]])
    note = workbook.create_sheet("计算说明")
    sections = payload.get("allowed_square_section_ids") or []
    if sections:
        note["A1"] = "允许方钢截面：" + "、".join(sections)
        note["A2"] = payload.get("allowed_square_section_source_ref") or "chat_intake"
    workbook.save(path)
    workbook.close()
    return {
        "status": "pass",
        "intake_path": str(path),
        "report_number": report_number,
        "row_number": 2,
    }
