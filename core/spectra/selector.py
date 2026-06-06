from __future__ import annotations

import json
from pathlib import Path

from core.spectra.ansys_writer import spectrum_to_ansys_mac
from core.spectra.excel_reader import read_spectrum_workbook


SPECTRUM_ELEVATION_LOWER_TOLERANCE_M = 0.1


def _metadata_match(point: dict, query: dict, include_elevation: bool = True) -> bool:
    keys = ["project_code", "building", "area", "level", "direction"]
    if include_elevation:
        keys.append("elevation")
    for key in keys:
        if key == "elevation":
            if float(point[key]) != float(query[key]):
                return False
        elif str(point[key]).upper() != str(query[key]).upper():
            return False
    return abs(float(point["damping"]) - float(query["damping"])) < 1e-9


def _group_points(points: list[dict]) -> dict[float, list[dict]]:
    grouped: dict[float, list[dict]] = {}
    for point in points:
        grouped.setdefault(float(point["elevation"]), []).append(point)
    for rows in grouped.values():
        rows.sort(key=lambda item: float(item["frequency_hz"]))
    return grouped


def select_spectrum_points(spectrum_data: dict, query: dict) -> dict:
    candidates = [point for point in spectrum_data["points"] if _metadata_match(point, query, include_elevation=False)]
    if not candidates:
        raise ValueError("No spectrum rows match project/building/area/level/direction/damping")
    target_elevation = float(query["elevation"])
    exact = [point for point in candidates if float(point["elevation"]) == target_elevation]
    if exact:
        exact.sort(key=lambda item: float(item["frequency_hz"]))
        return {
            "selection_mode": "exact",
            "source_elevations": [target_elevation],
            "points": [{"frequency_hz": row["frequency_hz"], "acceleration_g": row["acceleration_g"]} for row in exact],
            "source_refs": [row["source_ref"] for row in exact],
        }

    grouped = _group_points(candidates)
    minimum_allowed = target_elevation - SPECTRUM_ELEVATION_LOWER_TOLERANCE_M
    selectable = sorted(value for value in grouped if value >= minimum_allowed - 1e-8)
    if not selectable:
        raise ValueError(
            "No spectrum elevation is available within the 0.1 m lower tolerance or above "
            f"target elevation={target_elevation:g}"
        )
    selected_elevation = selectable[0]
    rows = grouped[selected_elevation]
    mode = (
        "lower_floor_within_0p1m_tolerance"
        if selected_elevation < target_elevation
        else "next_upper_floor"
    )
    return {
        "selection_mode": mode,
        "requested_elevation": target_elevation,
        "selected_elevation": selected_elevation,
        "lower_tolerance_m": SPECTRUM_ELEVATION_LOWER_TOLERANCE_M,
        "source_elevations": [selected_elevation],
        "points": [{"frequency_hz": row["frequency_hz"], "acceleration_g": row["acceleration_g"]} for row in rows],
        "source_refs": [row["source_ref"] for row in rows],
    }


def select_spectrum_from_workbook(
    workbook_path: Path | str,
    query: dict,
    output_dir: Path | str,
    config: dict | None = None,
) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    spectrum_data = read_spectrum_workbook(workbook_path, config=config)
    selection = select_spectrum_points(spectrum_data, query)
    selection_payload = {
        "workbook": spectrum_data["workbook"],
        "workbook_sha256": spectrum_data["sha256"],
        "query": query,
        **selection,
    }
    points_payload = {"points": selection["points"]}
    (output_dir / "spectrum_selection.json").write_text(
        json.dumps(selection_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "spectrum_points.json").write_text(
        json.dumps(points_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    spectrum_to_ansys_mac(selection["points"], float(query["damping"]), output_dir / "ansys_spectrum.mac")
    audit = {
        "status": "pass",
        "selection_mode": selection["selection_mode"],
        "point_count": len(selection["points"]),
        "workbook_sha256": spectrum_data["sha256"],
    }
    (output_dir / "spectrum_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return selection_payload
