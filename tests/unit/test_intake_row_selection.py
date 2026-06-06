import pytest

from core.intake import job_input_builder as builder
from core.intake import intake_excel_reader as reader


def test_selected_row_number_matches_physical_excel_row_only() -> None:
    assert builder._row_matches_selected_number({"intake_row_number": 4, "intake_serial": 99}, {4}) is True
    assert builder._row_matches_selected_number({"intake_row_number": 5, "intake_serial": 4}, {4}) is False


def test_row_override_number_fallback_ignores_engineering_serial() -> None:
    rows = [
        {"intake_row_number": 4, "intake_serial": 1, "provisional_intake_id": "row_4"},
        {"intake_row_number": 5, "intake_serial": 4, "provisional_intake_id": "row_5"},
    ]
    selected = builder._select_rows_from_overrides(rows, [{"intake_row_number": 4}])

    assert [row["provisional_intake_id"] for row in selected] == ["row_4"]


def test_safe_job_id_is_ascii_for_ansys_parallel_workdirs() -> None:
    job_id = builder._safe_job_id("1818 S2支架需求汇总20240711_副本_S2形式_row_6")

    assert job_id == "1818_S2_20240711_S2_row_6"
    assert job_id.isascii()


def test_selected_filter_without_matches_fails_instead_of_zero_job_pass(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        builder,
        "read_tabular_intake_rows",
        lambda _path: [
            {
                "intake_row_number": 2,
                "report_number": "18185NI-LXSJ4210",
                "calculation_batch": "18185NI-LXSJ4210",
                "provisional_intake_id": "row_2",
            }
        ],
    )

    with pytest.raises(ValueError, match="未匹配到任何提资行"):
        builder.create_jobs_from_intake_workbook(
            tmp_path / "intake.xlsx",
            jobs_dir=tmp_path / "jobs",
            selected_row_numbers=[4210],
        )


def test_allowed_square_sections_are_extracted_from_calculation_note_without_unlisted_sections() -> None:
    note = "计算说明：方钢候选 100*100*6、100*100*8、120*120*6、120*120*10、140*140*8、160*160*8 均需试算。"

    assert reader._extract_allowed_square_sections_from_text(note) == [
        "100-100-6",
        "100-100-8",
        "120-120-6",
        "120-120-10",
        "140-140-8",
        "160-160-8",
    ]

    found = reader._find_allowed_square_sections_from_sheet_items(
        [
            ("支架需求", [("历史参考 120*120*8",)]),
            ("计算说明", [(note,)]),
        ]
    )

    assert found["allowed_square_section_status"] == "provided_by_intake_calculation_notes"
    assert found["allowed_square_section_source_ref"] == "计算说明!R1C1"
    assert found["allowed_square_section_ids"] == [
        "100-100-6",
        "100-100-8",
        "120-120-6",
        "120-120-10",
        "140-140-8",
        "160-160-8",
    ]
    assert "120-120-8" not in found["allowed_square_section_ids"]
