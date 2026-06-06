from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class SpectrumColumnMapping(BaseModel):
    project_code: str | None = None
    building: str | None = None
    area: str | None = None
    elevation: str | None = None
    damping: str | None = None
    level: str | None = None
    direction: str | None = None
    frequency_hz: str
    acceleration_g: str | None = None
    acceleration_columns: dict[str, str] = Field(default_factory=dict)


class SpectrumFormatConfig(BaseModel):
    workbook_pattern: str = "*.xls*"
    sheet_pattern: str | None = None
    sheet: str | None = None
    header_row: int | None = None
    columns: SpectrumColumnMapping
    defaults: dict[str, str | float] = Field(default_factory=dict)


def load_spectrum_format_config(path: Path | str) -> SpectrumFormatConfig:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if hasattr(SpectrumFormatConfig, "model_validate"):
        return SpectrumFormatConfig.model_validate(payload)
    return SpectrumFormatConfig.parse_obj(payload)


def column_index(column: str) -> int:
    column = column.strip().upper()
    index = 0
    for char in column:
        if not ("A" <= char <= "Z"):
            raise ValueError(f"Invalid Excel column: {column}")
        index = index * 26 + ord(char) - ord("A") + 1
    return index
