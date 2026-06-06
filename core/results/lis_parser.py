from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Iterable


class LisParseError(ValueError):
    pass


HEADER_ALIASES = {
    "case": {"case", "load_case", "lscase", "工况"},
    "value_type": {"value_type", "value_ty", "stress_type", "type", "类型", "应力类型"},
    "element": {"element", "element_id", "elem", "单元", "单元号"},
    "value": {"value", "stress", "应力", "数值"},
    "unit": {"unit", "单位"},
    "mode": {"mode", "模态", "阶次"},
    "frequency_hz": {"frequency_hz", "freq", "frequency", "frequencyhertz", "频率", "频率hz"},
    "period_s": {"period_s", "period", "周期"},
    "mass_x": {"mass_x", "x_mass", "x向质量"},
    "mass_y": {"mass_y", "y_mass", "y向质量"},
    "mass_z": {"mass_z", "z_mass", "z向质量"},
    "component": {"component", "componen", "构件", "name"},
    "force_n": {"force_n", "force", "力"},
    "stress_mpa": {"stress_mpa", "stress_m", "stress", "应力"},
    "allowable_mpa": {"allowable_mpa", "allowabl", "allowable", "许用"},
    "bolt_group": {"bolt_group", "bolt_gro", "boltgroup", "螺栓组", "name"},
    "tension_mpa": {"tension_mpa", "tension_", "tension", "拉应力"},
    "shear_mpa": {"shear_mpa", "shear_mp", "shear", "剪应力"},
    "allowable_tension_mpa": {"allowable_tension_mpa", "allow_tension", "许用拉应力"},
    "allowable_shear_mpa": {"allowable_shear_mpa", "allow_shear", "许用剪应力"},
    "node": {"node", "节点"},
    "fx": {"fx", "fxn", "fxm"},
    "fy": {"fy", "fyn", "fym"},
    "fz": {"fz", "fzn", "fzm"},
    "mx": {"mx", "mxnm"},
    "my": {"my", "mynm"},
    "mz": {"mz", "mznm"},
    "force_unit": {"force_unit", "force_un"},
    "moment_unit": {"moment_unit", "moment_u"},
    "tension": {"tension"},
    "compression": {"compression", "compress"},
    "bend": {"bend"},
}


def _read_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312", "latin1"):
        try:
            return raw.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").splitlines()


def _source_meta(path: Path, raw_value: str | None = None) -> dict:
    return {
        "source_file": path.name,
        "source_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_line": None,
        "source_block": path.name,
        "raw_value": raw_value,
        "normalized_value": _float(raw_value) if raw_value not in (None, "") else None,
        "parser_version": "lis_parser_v2",
    }


def _clean_lines(path: Path) -> list[str]:
    lines = []
    for line in _read_lines(path):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.search(r"^(unit|单位)\s*[:：]", stripped, flags=re.IGNORECASE):
            continue
        lines.append(stripped)
    return lines


def _split(line: str) -> list[str]:
    if "," in line:
        return [part.strip() for part in next(csv.reader([line]))]
    return [part for part in re.split(r"\s+", line.strip()) if part]


def _norm(token: str) -> str:
    return re.sub(r"[\s_()（）/-]+", "", token.strip().lower())


def _alias_key(token: str) -> str | None:
    normalized = _norm(token)
    for key, aliases in HEADER_ALIASES.items():
        if normalized in {_norm(alias) for alias in aliases}:
            return key
    return None


def _float(value: str | float | int) -> float:
    return float(str(value).strip())


def _int(value: str | float | int) -> int:
    return int(float(str(value).strip()))


def _stress_to_mpa(value: str | float | int, unit: str | None = None) -> float:
    numeric = _float(value)
    unit_text = (unit or "").strip().lower()
    if unit_text in {"pa", "n/m2", "n/m^2"}:
        return numeric / 1_000_000.0
    if not unit_text and abs(numeric) > 10000:
        return numeric / 1_000_000.0
    return numeric


def _records_from_table(path: Path) -> list[dict[str, str]]:
    lines = _clean_lines(path)
    if not lines:
        raise LisParseError(f"{path.name}: no parseable data lines")
    header_index = None
    headers: list[str] = []
    for index, line in enumerate(lines):
        parts = _split(line)
        alias_count = sum(1 for part in parts if _alias_key(part) is not None)
        if alias_count >= 2:
            header_index = index
            headers = [_alias_key(part) or _norm(part) for part in parts]
            break
    if header_index is None:
        raise LisParseError(f"{path.name}: no supported table header found")

    records: list[dict[str, str]] = []
    for line in lines[header_index + 1 :]:
        parts = _split(line)
        if len(parts) < 2:
            continue
        if len(parts) < len(headers):
            parts.extend([""] * (len(headers) - len(parts)))
        records.append(dict(zip(headers, parts)))
    if not records:
        raise LisParseError(f"{path.name}: header was found but no data rows were parsed")
    return records


def _numeric_rows(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    for line in _clean_lines(path):
        values = []
        for token in _split(line):
            try:
                values.append(_float(token.replace("±", "")))
            except ValueError:
                pass
        if values:
            rows.append(values)
    return rows


def _require(record: dict[str, str], key: str, path: Path) -> str:
    value = record.get(key)
    if value in (None, ""):
        raise LisParseError(f"{path.name}: missing required field {key}")
    return value


def parse_beam_stress_lis(path: Path | str) -> list[dict]:
    path = Path(path)
    records = _records_from_table(path)
    results: list[dict] = []
    for record in records:
        if any(key in record for key in ("tension", "tension_mpa", "compression", "bend", "shear", "shear_mpa")):
            load_case = record.get("case") or record.get("lscase") or record.get("loadcase") or "UNKNOWN"
            stress_unit = record.get("unit") or "Pa"
            for stress_type, key in (
                ("SDIR_TENSION", "tension"),
                ("SDIR_TENSION", "tension_mpa"),
                ("SDIR_COMPRESSION", "compression"),
                ("SBEND", "bend"),
                ("SHEAR", "shear"),
                ("SHEAR", "shear_mpa"),
            ):
                value = record.get(key)
                if value not in (None, ""):
                    results.append(
                        {
                            "load_case": load_case,
                            "stress_type": stress_type,
                            "element_id": _int(record.get("element") or 0),
                            "value_mpa": _stress_to_mpa(value, stress_unit),
                            "unit": "MPa",
                            "source_ref": path.name,
                            **_source_meta(path, value),
                        }
                    )
            continue
        results.append(
            {
                "load_case": _require(record, "case", path),
                "stress_type": _require(record, "value_type", path).upper(),
                "element_id": _int(record.get("element") or 0),
                "value_mpa": _stress_to_mpa(_require(record, "value", path), record.get("unit")),
                "unit": record.get("unit") or "MPa",
                "source_ref": path.name,
                **_source_meta(path, _require(record, "value", path)),
            }
        )
    if not results:
        raise LisParseError(f"{path.name}: no beam stress rows parsed")
    return results


MODAL_MT_CUTOFF_HZ = 50.0
MODAL_REPORTING_MIN_FREQUENCY_HZ = 1.0


def _modal_cutoff_metadata(rows: list[dict], *, cutoff_hz: float = MODAL_MT_CUTOFF_HZ) -> dict:
    above = [row for row in rows if float(row.get("frequency_hz") or 0.0) > cutoff_hz]
    first_above = above[0] if above else None
    last_above = above[-1] if above else None
    first_source_mode = int(first_above.get("source_mode") or first_above["mode"]) if first_above else None
    last_source_mode = int(last_above.get("source_mode") or last_above["mode"]) if last_above else None
    return {
        "mt_cutoff_hz": cutoff_hz,
        "mt_mode": last_source_mode,
        "mt_mode_first_above_cutoff_hz": first_source_mode,
        "mt_mode_last_above_cutoff_hz": last_source_mode,
        "modal_cutoff_status": "pass" if last_above else "insufficient_modes_below_50hz",
        "modal_cutoff_policy": (
            "MT is the source MODE value corresponding to the last parsed FREQUENCY (HERTZ) row greater than 50 Hz. "
            "If no parsed mode exceeds 50 Hz, increase modal extraction count and rerun."
        ),
    }


def _annotate_modal_cutoff(rows: list[dict]) -> list[dict]:
    if not rows:
        return rows
    metadata = _modal_cutoff_metadata(rows)
    for row in rows:
        row.update(metadata)
    return rows


def _normalize_reportable_modal_rows(rows: list[dict]) -> list[dict]:
    """Number reportable structural modes while preserving ANSYS source MODE."""

    normalized: list[dict] = []
    for row in rows:
        frequency = row.get("frequency_hz")
        if frequency is None or float(frequency) < MODAL_REPORTING_MIN_FREQUENCY_HZ:
            continue
        source_mode = int(row.get("source_mode") or row.get("mode"))
        normalized.append(
            {
                **row,
                "source_mode": source_mode,
                "mode": len(normalized) + 1,
                "modal_reporting_min_frequency_hz": MODAL_REPORTING_MIN_FREQUENCY_HZ,
                "modal_reporting_policy": (
                    "Report modal sequence excludes zero and near-rigid rows below 1 Hz; "
                    "source_mode preserves the original ANSYS MODE for traceability and MT cutoff."
                ),
            }
        )
    return _annotate_modal_cutoff(normalized)


def parse_modal_oup(path: Path | str) -> list[dict]:
    path = Path(path)
    try:
        records = _records_from_table(path)
    except LisParseError:
        records = []
    results: list[dict] = []
    for record in records:
        if not record.get("frequency_hz"):
            continue
        frequency = _float(_require(record, "frequency_hz", path))
        if frequency <= 0:
            continue
        period = _float(record["period_s"]) if record.get("period_s") else 1.0 / frequency
        results.append(
            {
                "mode": _int(_require(record, "mode", path)),
                "source_mode": _int(_require(record, "mode", path)),
                "frequency_hz": frequency,
                "period_s": period,
                "mass_x": _float(record["mass_x"]) if record.get("mass_x") else None,
                "mass_y": _float(record["mass_y"]) if record.get("mass_y") else None,
                "mass_z": _float(record["mass_z"]) if record.get("mass_z") else None,
                "source_ref": path.name,
                **_source_meta(path, str(frequency)),
            }
        )
    if results:
        return _normalize_reportable_modal_rows(results)
    return _normalize_reportable_modal_rows(_parse_mapdl_modal_frequency_table(path))


def _parse_mapdl_modal_frequency_table(path: Path) -> list[dict]:
    results: list[dict] = []
    in_table = False
    numeric = re.compile(r"^\s*(\d+)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)\s*$")
    for line_number, line in enumerate(_read_lines(path), start=1):
        upper = line.upper()
        if re.search(r"\bMODE\b\s+\bFREQUENCY\b\s*\(HERTZ\)", upper):
            in_table = True
            continue
        if not in_table:
            continue
        match = numeric.match(line)
        if match:
            frequency = _float(match.group(2))
            if frequency <= 0:
                continue
            meta = _source_meta(path, match.group(2))
            meta["source_line"] = line_number
            results.append(
                {
                    "mode": _int(match.group(1)),
                    "source_mode": _int(match.group(1)),
                    "frequency_hz": frequency,
                    "period_s": 1.0 / frequency if frequency else None,
                    "mass_x": None,
                    "mass_y": None,
                    "mass_z": None,
                    "source_ref": path.name,
                    **meta,
                }
            )
            continue
        if results and line.strip():
            break
    if not results:
        raise LisParseError(f"{path.name}: no modal frequency rows parsed")
    return results


def parse_weld_force_lis(path: Path | str) -> list[dict]:
    path = Path(path)
    try:
        records = _records_from_table(path)
    except LisParseError:
        return _parse_headerless_force_rows(path, default_name="WELD_FORCE_RAW", value_kind="weld")
    results: list[dict] = []
    for record in records:
        results.append(
            {
                "name": record.get("component") or record.get("name") or record.get("构件") or "WELD",
                "load_case": record.get("load_case") or record.get("case") or record.get("工况") or "UNKNOWN",
                "force_n": _float(record.get("force_n") or record.get("force") or record.get("力") or 0),
                "stress_mpa": _float(record.get("stress_mpa") or record.get("stress") or record.get("应力") or 0),
                "allowable_mpa": _float(record.get("allowable_mpa") or record.get("allowable") or record.get("许用") or 0),
                "source_ref": path.name,
                **_source_meta(path, record.get("stress_mpa") or record.get("stress") or "0"),
            }
        )
    return results


def parse_bolt_force_lis(path: Path | str) -> list[dict]:
    path = Path(path)
    try:
        records = _records_from_table(path)
    except LisParseError:
        return _parse_headerless_force_rows(path, default_name="BOLT_FORCE_RAW", value_kind="bolt")
    results: list[dict] = []
    for record in records:
        results.append(
            {
                "name": record.get("bolt_group") or record.get("name") or record.get("component") or "BOLT",
                "load_case": record.get("load_case") or record.get("case") or "UNKNOWN",
                "tension_mpa": _float(record.get("tension_mpa") or record.get("tension") or 0),
                "shear_mpa": _float(record.get("shear_mpa") or record.get("shear") or 0),
                "allowable_tension_mpa": _float(record.get("allowable_tension_mpa") or record.get("allow_tension") or 0),
                "allowable_shear_mpa": _float(record.get("allowable_shear_mpa") or record.get("allow_shear") or 0),
                "source_ref": path.name,
                **_source_meta(path, record.get("tension_mpa") or record.get("tension") or "0"),
            }
        )
    return results


def parse_foundation_load_lis(path: Path | str) -> list[dict]:
    path = Path(path)
    records = _records_from_table(path)
    results: list[dict] = []
    for record in records:
        force_unit = record.get("force_unit") or "N"
        moment_unit = record.get("moment_unit") or "N*m"
        source_ref = path.name
        results.append(
            {
                "load_case": record.get("load_case") or record.get("case") or "UNKNOWN",
                "node": record.get("node") or record.get("节点") or "UNKNOWN",
                "fx": {"value": _float(record.get("fx") or 0), "unit": force_unit, "raw_value": record.get("fx"), "source_ref": source_ref},
                "fy": {"value": _float(record.get("fy") or 0), "unit": force_unit, "raw_value": record.get("fy"), "source_ref": source_ref},
                "fz": {"value": _float(record.get("fz") or 0), "unit": force_unit, "raw_value": record.get("fz"), "source_ref": source_ref},
                "mx": {"value": _float(record.get("mx") or 0), "unit": moment_unit, "raw_value": record.get("mx"), "source_ref": source_ref},
                "my": {"value": _float(record.get("my") or 0), "unit": moment_unit, "raw_value": record.get("my"), "source_ref": source_ref},
                "mz": {"value": _float(record.get("mz") or 0), "unit": moment_unit, "raw_value": record.get("mz"), "source_ref": source_ref},
                "source_ref": source_ref,
                **_source_meta(path, record.get("fx") or "0"),
            }
        )
    for item in results:
        if item.get("node") == "UNKNOWN":
            item["node"] = "ENVELOPE_OF_NKMS_SUPPORT_NODES"
    return results


def parse_connection_node_force_lis(path: Path | str) -> list[dict]:
    path = Path(path)
    rows = _numeric_rows(path)
    results: list[dict] = []
    for index, row in enumerate(rows):
        if len(row) < 8:
            continue
        keypoint = int(row[0])
        case_id = int(row[1])
        load_case = "UPSET" if case_id == 2 else "FAULTED" if case_id == 3 else f"CASE_{case_id}"
        fx, fy, fz, mx, my, mz = row[2:8]
        if max(abs(value) for value in (fx, fy, fz, mx, my, mz)) <= 1e-9:
            continue
        results.append(
            {
                "keypoint": keypoint,
                "load_case": load_case,
                "fx": {"value": fx, "unit": "N", "raw_value": str(fx), "source_ref": path.name},
                "fy": {"value": fy, "unit": "N", "raw_value": str(fy), "source_ref": path.name},
                "fz": {"value": fz, "unit": "N", "raw_value": str(fz), "source_ref": path.name},
                "mx": {"value": mx, "unit": "N*m", "raw_value": str(mx), "source_ref": path.name},
                "my": {"value": my, "unit": "N*m", "raw_value": str(my), "source_ref": path.name},
                "mz": {"value": mz, "unit": "N*m", "raw_value": str(mz), "source_ref": path.name},
                "source_ref": path.name,
                **_source_meta(path, str(max(abs(value) for value in row[1:7]))),
            }
        )
    return results


def _parse_headerless_force_rows(path: Path, *, default_name: str, value_kind: str) -> list[dict]:
    rows = _numeric_rows(path)
    if not rows:
        raise LisParseError(f"{path.name}: no numeric force rows parsed")
    case_names = ["UPSET", "FAULTED"]
    results: list[dict] = []
    for index, row in enumerate(rows):
        load_case = case_names[index] if index < len(case_names) else f"CASE_{index + 1}"
        raw_value = str(max((abs(value) for value in row), default=0.0))
        meta = _source_meta(path, raw_value)
        fx = row[0] if len(row) > 0 else 0.0
        fy = row[1] if len(row) > 1 else 0.0
        fz = row[2] if len(row) > 2 else 0.0
        mx = row[3] if len(row) > 3 else 0.0
        my = row[4] if len(row) > 4 else 0.0
        mz = row[5] if len(row) > 5 else 0.0
        if value_kind == "weld":
            results.append(
                {
                    "name": default_name,
                    "load_case": load_case,
                    "force_n": max((abs(value) for value in row[:3]), default=0.0),
                    "fx": fx,
                    "fy": fy,
                    "fz": fz,
                    "mx": mx,
                    "my": my,
                    "mz": mz,
                    "force_unit": "N",
                    "moment_unit": "N*m",
                    "stress_mpa": 0.0,
                    "allowable_mpa": 0.0,
                    "source_ref": path.name,
                    **meta,
                }
            )
        else:
            results.append(
                {
                    "name": default_name,
                    "load_case": load_case,
                    "fx": fx,
                    "fy": fy,
                    "fz": fz,
                    "mx": mx,
                    "my": my,
                    "mz": mz,
                    "force_unit": "N",
                    "moment_unit": "N*m",
                    "result_kind": "tray_arm_connection_load",
                    "source_ref": path.name,
                    **meta,
                }
            )
    return results


def parse_existing(paths: Iterable[Path]) -> dict[str, list[dict]]:
    parsed: dict[str, list[dict]] = {}
    for path in paths:
        if path.name in {"SQUAREBEAMSTRESS.LIS", "MAXBEAMSTRESS.LIS", "TMAXBEAMSTRESS.LIS"}:
            parsed[path.name] = parse_beam_stress_lis(path)
        elif path.name == "Mode.oup":
            parsed[path.name] = parse_modal_oup(path)
        elif path.name == "HF-FORCE.LIS":
            parsed[path.name] = parse_weld_force_lis(path)
        elif path.name == "LS-FORCE.LIS":
            parsed[path.name] = parse_bolt_force_lis(path)
        elif path.name == "JCZH.LIS":
            parsed[path.name] = parse_foundation_load_lis(path)
        elif path.name == "LS-FORCE-NODES.LIS":
            parsed[path.name] = parse_connection_node_force_lis(path)
    return parsed
