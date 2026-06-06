from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExcelCellMapping:
    name: str
    sheet: str
    cell: str
    direction: str
    source_ref: str


DEFAULT_EXCEL_MAPPINGS = [
    ExcelCellMapping("max_support_ratio", "Summary", "B10", "output", "docs/formula_traceability.md"),
    ExcelCellMapping("max_weld_ratio", "Summary", "B11", "output", "docs/formula_traceability.md"),
    ExcelCellMapping("max_bolt_ratio", "Summary", "B12", "output", "docs/formula_traceability.md"),
]


def mappings_to_dict(mappings: list[ExcelCellMapping] | None = None) -> list[dict]:
    return [mapping.__dict__ for mapping in (mappings or DEFAULT_EXCEL_MAPPINGS)]


def validate_excel_mappings(mappings: list[dict]) -> dict:
    missing = [item for item in mappings if not item.get("sheet") or not item.get("cell") or not item.get("source_ref")]
    return {"status": "fail" if missing else "pass", "missing_count": len(missing)}
