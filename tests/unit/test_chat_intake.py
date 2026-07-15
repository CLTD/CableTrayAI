from __future__ import annotations

from pathlib import Path

from core.intake.chat_intake import STANDARD_CHAT_SQUARE_SECTIONS, parse_chat_intake, write_chat_intake_workbook
from core.intake.intake_excel_reader import read_tabular_intake_rows


def test_standard_chat_square_sections_match_department_list() -> None:
    assert STANDARD_CHAT_SQUARE_SECTIONS == [
        "100-100-6",
        "100-100-8",
        "120-120-6",
        "120-120-8",
        "120-120-10",
        "140-140-8",
        "160-160-8",
    ]


def test_chat_intake_parses_double_side_600_with_explicit_sections() -> None:
    draft = parse_chat_intake(
        {
            "message": (
                "18185NI-LXSJ9001，项目1818，NR厂房，标高8.5m，"
                "双侧2+2层600，支架间距2m，方钢长度1.8m，允许100x8、120x8、140x8"
            ),
            "spectrum_file": "uploads/spectrum/floor.xlsm",
        }
    )

    assert draft["status"] == "pass"
    payload = draft["intake_payload"]
    assert payload["project_code"] == "1818"
    assert payload["building"] == "NR"
    assert payload["elevation"] == 8.5
    assert payload["description"] == "双侧2+2层600"
    assert payload["report_number"].startswith("CHAT-")
    assert payload["intake_identity_status"] == "chat_generated_request_id"
    assert payload["raw_intake_row"]["detected_reference_number"] == "18185NI-LXSJ9001"
    assert payload["support_spacing_m"] == 2.0
    assert payload["support_height_m"] == 1.8
    assert payload["allowed_square_section_ids"] == ["100-100-8", "120-120-8", "140-140-8"]
    assert draft["tray_mapping"]["side_count"] == 2
    assert draft["tray_mapping"]["front_layers"] == 2
    assert draft["tray_mapping"]["back_layers"] == 2


def test_chat_intake_can_expand_single_side_five_layers_500_to_600() -> None:
    draft = parse_chat_intake(
        {
            "message": "项目1818 厂房NR 标高21.95 单侧五层600 托盘长度2m 方钢长度1.7m",
            "spectrum_file": "uploads/spectrum/floor.xlsm",
            "use_standard_square_sections": True,
        }
    )

    assert draft["status"] == "pass"
    assert draft["intake_payload"]["description"] == "单侧5层600"
    assert draft["tray_mapping"]["side_count"] == 1
    assert draft["tray_mapping"]["front_layers"] == 5
    assert [item["tray_width_mm"] for item in draft["tray_mapping"]["layers"]] == [600, 600, 600, 600, 600]
    assert "100-100-6" in draft["intake_payload"]["allowed_square_section_ids"]


def test_chat_intake_blocks_when_spectrum_and_allowed_sections_are_missing() -> None:
    draft = parse_chat_intake(
        {
            "message": "项目1818 NR厂房 标高8.5m 单侧2层500 间距2m 方钢长度1.8m",
        }
    )

    assert draft["status"] == "blocked"
    assert "spectrum_file" in draft["missing_fields"]
    assert "allowed_square_section_ids" in draft["missing_fields"]


def test_chat_intake_workbook_roundtrips_through_tabular_reader(tmp_path: Path) -> None:
    draft = parse_chat_intake(
        {
            "message": "项目1818 NR厂房 标高8.5m 双侧2+2层500 间距2m 方钢长度1.8m 允许100x8 120x10 140x8",
            "spectrum_file": "uploads/spectrum/floor.xlsm",
        }
    )
    written = write_chat_intake_workbook(draft, output_dir=tmp_path)

    rows = read_tabular_intake_rows(written["intake_path"])

    assert len(rows) == 1
    row = rows[0]
    assert row["project_code"] == "1818"
    assert row["building"] == "NR"
    assert row["description"] == "双侧2+2层500"
    assert row["allowed_square_section_ids"] == ["100-100-8", "120-120-10", "140-140-8"]
