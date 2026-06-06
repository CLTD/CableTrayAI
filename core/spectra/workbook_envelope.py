from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.spectra.static_coefficients import (
    DAMPING_BY_LEVEL,
    SpectrumCurve,
    _interp_log_frequency,
    _normalise_rows,
    _read_segmented_sheet,
    _read_workbook_rows,
)


@dataclass(frozen=True)
class EnvelopeInput:
    sheet: str
    elevation: float


@dataclass(frozen=True)
class SimplifyControl:
    group_index: int
    source_range: str
    values: tuple[float, ...]

    @property
    def spacing_values(self) -> tuple[float, float, float, float]:
        return (self.values[1], self.values[3], self.values[5], self.values[7])

    @property
    def mode(self) -> str:
        if all(abs(value) < 1e-12 for value in self.spacing_values):
            return "finest_control"
        if all(abs(value - 10.0) < 1e-12 for value in self.spacing_values):
            return "coarsest_control"
        return "custom_control"


GROUP_SEQUENCE: tuple[tuple[int, str, str], ...] = (
    (1, "SL-1", "X"),
    (2, "SL-1", "Y"),
    (3, "SL-1", "Z"),
    (4, "SL-1", "XY"),
    (5, "SL-2", "X"),
    (6, "SL-2", "Y"),
    (7, "SL-2", "Z"),
    (8, "SL-2", "XY"),
)
ANSYS_BLOCK_SEQUENCE: tuple[tuple[str, str, int], ...] = (
    ("SL-1", "XY", 4),
    ("SL-1", "Z", 3),
    ("SL-2", "XY", 8),
    ("SL-2", "Z", 7),
)


def _excel_col_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _control_sheet(workbook: Any) -> Any:
    for sheet in workbook.worksheets:
        if str(sheet.title).strip() == "精度控制":
            return sheet
    for sheet in workbook.worksheets:
        if "控制" in str(sheet.title):
            return sheet
    if len(workbook.worksheets) >= 3:
        return workbook.worksheets[2]
    raise ValueError("Spectrum workbook is missing the precision-control sheet")


def _control_sheet_rows(sheet_items: list[tuple[str, list[tuple[Any, ...]]]]) -> tuple[str, list[tuple[Any, ...]]]:
    control_title = "\u7cbe\u5ea6\u63a7\u5236"
    control_keyword = "\u63a7\u5236"
    for sheet_name, rows in sheet_items:
        text = str(sheet_name).strip()
        if text == control_title or text.lower().replace(" ", "_") in {"precision", "precision_control"}:
            return sheet_name, rows
    for sheet_name, rows in sheet_items:
        text = str(sheet_name).strip()
        lowered = text.lower()
        if control_keyword in text or "control" in lowered or "precision" in lowered:
            return sheet_name, rows
    if len(sheet_items) >= 3:
        return sheet_items[2]
    raise ValueError("Spectrum workbook is missing the precision-control sheet")


def read_simplify_controls(workbook_path: Path | str) -> list[SimplifyControl]:
    workbook_path = Path(workbook_path)
    sheet_name, rows = _control_sheet_rows(_read_workbook_rows(workbook_path))
    rows = _normalise_rows(rows)
    controls: list[SimplifyControl] = []
    for group_index in range(1, 9):
        row0 = 5 + ((group_index - 1) % 4) * 19
        col0 = 1 + ((group_index - 1) // 4) * 11
        values: list[float] = []
        for offset in range(9):
            row_index = row0 + offset - 1
            col_index = col0 - 1
            value = rows[row_index][col_index] if row_index < len(rows) and col_index < len(rows[row_index]) else None
            if not isinstance(value, int | float):
                raise ValueError(
                    f"Invalid spectrum precision-control value at "
                    f"{sheet_name}!{_excel_col_name(col0)}{row0 + offset}: {value!r}"
                )
            values.append(float(value))
        source_range = f"{sheet_name}!{_excel_col_name(col0)}{row0}:{_excel_col_name(col0)}{row0 + 8}"
        controls.append(SimplifyControl(group_index, source_range, tuple(values)))
    return controls


def _unique_sorted(values: list[float] | tuple[float, ...]) -> tuple[float, ...]:
    return tuple(sorted(dict.fromkeys(float(value) for value in values)))


def _union_frequencies(curves: list[SpectrumCurve] | tuple[SpectrumCurve, ...]) -> tuple[float, ...]:
    frequencies: list[float] = []
    for curve in curves:
        frequencies.extend(float(value) for value in curve.frequency_hz if abs(float(value)) > 1e-12)
    return _unique_sorted(frequencies)


def _curve_on_frequencies(curve: SpectrumCurve, frequencies: tuple[float, ...], source_ref: str | None = None) -> SpectrumCurve:
    return SpectrumCurve(
        frequencies,
        tuple(_interp_log_frequency(curve, frequency) for frequency in frequencies),
        source_ref or curve.source_ref,
    )


def _available_elevations(
    curves: dict[tuple[str, str, float, float], SpectrumCurve],
    *,
    level: str,
    direction: str,
    damping: float,
) -> tuple[float, ...]:
    elevations = [
        elevation
        for curve_level, curve_direction, elevation, curve_damping in curves
        if curve_level == level and curve_direction == direction and abs(curve_damping - damping) < 1e-12
    ]
    if not elevations:
        raise ValueError(f"No source spectrum for level={level}, direction={direction}, damping={damping:g}")
    return _unique_sorted(elevations)


def _curve_at_source_elevation(
    curves: dict[tuple[str, str, float, float], SpectrumCurve],
    *,
    level: str,
    direction: str,
    elevation: float,
    damping: float,
) -> SpectrumCurve:
    try:
        return curves[(level, direction, float(elevation), damping)]
    except KeyError as exc:
        available = _available_elevations(curves, level=level, direction=direction, damping=damping)
        raise ValueError(
            f"No source spectrum at elevation={float(elevation):g} for "
            f"level={level}, direction={direction}, damping={damping:g}; available={available}"
        ) from exc


def _curve_at_requested_elevation(
    curves: dict[tuple[str, str, float, float], SpectrumCurve],
    *,
    sheet: str,
    level: str,
    direction: str,
    elevation: float,
    damping: float,
) -> tuple[SpectrumCurve, dict[str, Any]]:
    requested = float(elevation)
    available = _available_elevations(curves, level=level, direction=direction, damping=damping)
    exact = [item for item in available if abs(item - requested) < 1e-8]
    if exact:
        source_elevation = exact[0]
        curve = _curve_at_source_elevation(
            curves,
            level=level,
            direction=direction,
            elevation=source_elevation,
            damping=damping,
        )
        return curve, {
            "mode": "exact_source_elevation",
            "requested_elevation": requested,
            "lower_elevation": source_elevation,
            "upper_elevation": source_elevation,
            "source_elevations": [source_elevation],
        }

    if requested < available[0]:
        source_elevation = available[0]
        curve = _curve_at_source_elevation(
            curves,
            level=level,
            direction=direction,
            elevation=source_elevation,
            damping=damping,
        )
        return curve, {
            "mode": "clamped_to_lowest_source_elevation",
            "requested_elevation": requested,
            "lower_elevation": source_elevation,
            "upper_elevation": source_elevation,
            "source_elevations": [source_elevation],
        }

    if requested > available[-1]:
        source_elevation = available[-1]
        curve = _curve_at_source_elevation(
            curves,
            level=level,
            direction=direction,
            elevation=source_elevation,
            damping=damping,
        )
        return curve, {
            "mode": "clamped_to_highest_source_elevation",
            "requested_elevation": requested,
            "lower_elevation": source_elevation,
            "upper_elevation": source_elevation,
            "source_elevations": [source_elevation],
        }

    lower = max(item for item in available if item < requested)
    upper = min(item for item in available if item > requested)
    lower_curve = _curve_at_source_elevation(curves, level=level, direction=direction, elevation=lower, damping=damping)
    upper_curve = _curve_at_source_elevation(curves, level=level, direction=direction, elevation=upper, damping=damping)
    frequencies = _union_frequencies([lower_curve, upper_curve])
    lower_on_union = _curve_on_frequencies(lower_curve, frequencies)
    upper_on_union = _curve_on_frequencies(upper_curve, frequencies)
    ratio = (requested - lower) / (upper - lower)
    values = tuple(
        lower_value + ratio * (upper_value - lower_value)
        for lower_value, upper_value in zip(lower_on_union.acceleration_g, upper_on_union.acceleration_g)
    )
    source_ref = (
        f"{sheet}:vba_linear_elevation_interpolation:"
        f"{level}:{direction}:{damping:g}:{lower:g}-{upper:g}->{requested:g}"
    )
    return SpectrumCurve(frequencies, values, source_ref), {
        "mode": "vba_linear_elevation_interpolation",
        "requested_elevation": requested,
        "lower_elevation": lower,
        "upper_elevation": upper,
        "source_elevations": [lower, upper],
    }


def _envelope_curves(curves: list[SpectrumCurve] | tuple[SpectrumCurve, ...], source_ref: str) -> SpectrumCurve:
    if not curves:
        raise ValueError("No curves available for spectrum envelope")
    if len(curves) == 1:
        curve = curves[0]
        return SpectrumCurve(curve.frequency_hz, curve.acceleration_g, source_ref)
    frequencies = _union_frequencies(curves)
    interpolated = [_curve_on_frequencies(curve, frequencies) for curve in curves]
    values = tuple(max(curve.acceleration_g[index] for curve in interpolated) for index in range(len(frequencies)))
    return SpectrumCurve(frequencies, values, source_ref)


def _slope(before_frequency: float, before_acceleration: float, after_frequency: float, after_acceleration: float) -> float:
    return math.log10(after_acceleration / before_acceleration) / math.log10(after_frequency / before_frequency)


def simplify_curve_like_workbook(curve: SpectrumCurve, control: SimplifyControl) -> SpectrumCurve:
    frequencies = tuple(float(value) for value in curve.frequency_hz)
    accelerations = tuple(float(value) for value in curve.acceleration_g)
    rows = len(frequencies)
    if rows <= 2:
        return curve
    values = control.values
    out_frequencies = [frequencies[0]]
    out_accelerations = [accelerations[0]]
    for index in range(1, rows - 2):
        k_before = _slope(frequencies[index - 1], accelerations[index - 1], frequencies[index], accelerations[index])
        k_after = _slope(frequencies[index], accelerations[index], frequencies[index + 1], accelerations[index + 1])
        keep_turning_point = k_after < k_before
        keep_band_1 = frequencies[index] > values[8] and frequencies[index] <= values[6] and frequencies[index] - out_frequencies[-1] >= values[7]
        keep_band_2 = frequencies[index] > values[6] and frequencies[index] <= values[4] and frequencies[index] - out_frequencies[-1] >= values[5]
        keep_band_3 = frequencies[index] > values[4] and frequencies[index] <= values[2] and frequencies[index] - out_frequencies[-1] >= values[3]
        keep_band_4 = frequencies[index] > values[2] and frequencies[index] <= values[0] and frequencies[index] - out_frequencies[-1] >= values[1]
        if keep_turning_point or keep_band_1 or keep_band_2 or keep_band_3 or keep_band_4:
            out_frequencies.append(frequencies[index])
            out_accelerations.append(accelerations[index])
    out_frequencies.append(frequencies[-2])
    out_accelerations.append(accelerations[-2])
    out_frequencies.append(frequencies[-1])
    out_accelerations.append(accelerations[-1])
    return SpectrumCurve(tuple(out_frequencies), tuple(out_accelerations), curve.source_ref)


def generate_workbook_envelope(
    workbook_path: Path | str,
    *,
    inputs: list[EnvelopeInput] | tuple[EnvelopeInput, ...],
) -> dict[str, Any]:
    workbook_path = Path(workbook_path)
    if not inputs:
        raise ValueError("At least one spectrum envelope input is required")
    controls = read_simplify_controls(workbook_path)
    control_by_group = {control.group_index: control for control in controls}
    curves_by_sheet = {input_item.sheet: _read_segmented_sheet(workbook_path, input_item.sheet) for input_item in inputs}

    raw_curves: dict[tuple[str, str], SpectrumCurve] = {}
    elevation_audit: list[dict[str, Any]] = []
    for level, damping in DAMPING_BY_LEVEL.items():
        for direction in ("X", "Y", "Z"):
            input_curves: list[SpectrumCurve] = []
            for input_item in inputs:
                curve, audit = _curve_at_requested_elevation(
                    curves_by_sheet[input_item.sheet],
                    sheet=input_item.sheet,
                    level=level,
                    direction=direction,
                    elevation=input_item.elevation,
                    damping=damping,
                )
                input_curves.append(curve)
                elevation_audit.append(
                    {
                        "sheet": input_item.sheet,
                        "level": level,
                        "direction": direction,
                        "damping": damping,
                        **audit,
                    }
                )
            raw_curves[(level, direction)] = _envelope_curves(
                input_curves,
                source_ref=(
                    f"{workbook_path.name}:vba_envelope:{level}:{direction}:"
                    + ",".join(f"{item.sheet}@{item.elevation:g}" for item in inputs)
                ),
            )

    raw_curves[("SL-1", "XY")] = _envelope_curves(
        [raw_curves[("SL-1", "X")], raw_curves[("SL-1", "Y")]],
        source_ref=f"{workbook_path.name}:vba_horizontal_xy_envelope:SL-1",
    )
    raw_curves[("SL-2", "XY")] = _envelope_curves(
        [raw_curves[("SL-2", "X")], raw_curves[("SL-2", "Y")]],
        source_ref=f"{workbook_path.name}:vba_horizontal_xy_envelope:SL-2",
    )

    simplified_by_group: dict[int, dict[str, Any]] = {}
    for group_index, level, direction_group in GROUP_SEQUENCE:
        control = control_by_group[group_index]
        raw_curve = raw_curves[(level, direction_group)]
        simplified_curve = simplify_curve_like_workbook(raw_curve, control)
        simplified_by_group[group_index] = {
            "level": level,
            "direction_group": direction_group,
            "raw_curve": raw_curve,
            "curve": simplified_curve,
            "control": control,
        }

    blocks: dict[tuple[str, str], dict[str, Any]] = {}
    for level, direction_group, group_index in ANSYS_BLOCK_SEQUENCE:
        item = simplified_by_group[group_index]
        curve = item["curve"]
        control = item["control"]
        blocks[(level, direction_group)] = {
            "level": level,
            "direction_group": direction_group,
            "damping": DAMPING_BY_LEVEL[level],
            "curve": curve,
            "point_count": len(curve.frequency_hz),
            "raw_point_count": len(item["raw_curve"].frequency_hz),
            "simplification": {
                "method": "vba_precision_control",
                "source_range": control.source_range,
                "control_values": list(control.values),
                "control_mode": control.mode,
                "original_point_count": len(item["raw_curve"].frequency_hz),
                "ansys_point_count": len(curve.frequency_hz),
                "resampled": len(item["raw_curve"].frequency_hz) != len(curve.frequency_hz),
            },
            "source_ref": curve.source_ref,
        }

    return {
        "status": "pass",
        "source_mode": "python_vba_envelope_replicator",
        "workbook": str(workbook_path),
        "inputs": [{"sheet": item.sheet, "elevation": item.elevation} for item in inputs],
        "controls": [
            {
                "group_index": control.group_index,
                "source_range": control.source_range,
                "values": list(control.values),
                "mode": control.mode,
            }
            for control in controls
        ],
        "elevation_audit": elevation_audit,
        "blocks": blocks,
    }
