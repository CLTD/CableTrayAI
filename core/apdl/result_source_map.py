from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


RESULT_MACROS = {
    "SQUAREBEAMSTRESS-WRITE": "SQUAREBEAMSTRESS.LIS",
    "MAXBEAMSTRESS-WRITE": "MAXBEAMSTRESS.LIS",
    "TMAXBEAMSTRESS-WRITE": "TMAXBEAMSTRESS.LIS",
}


def _read_lines(path: Path) -> list[str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312"):
        try:
            return raw.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").splitlines()


def _selector_window(lines: list[str], create_line_index: int) -> list[dict[str, Any]]:
    selectors: list[dict[str, Any]] = []
    for index in range(create_line_index - 1, -1, -1):
        stripped = lines[index].strip()
        upper = stripped.upper()
        if upper.startswith("*DEL,MAXSHEAR") or upper.startswith("ALLSEL"):
            if selectors:
                break
        if re.match(r"^(ESEL|NSEL|LSEL|CMSEL|CM|ESLN|ALLSEL)\b", upper):
            selectors.append({"line": index + 1, "command": stripped})
    return list(reversed(selectors))


def _component_scope(selectors: list[dict[str, Any]]) -> str:
    commands = "\n".join(item["command"].upper().replace(" ", "") for item in selectors)
    if "ESEL,A,TYPE,,10*I+2" in commands and "ESEL,A,TYPE,,10*I+3" in commands:
        return "parameterized_cantilever_arm_type_family"
    if "CMSEL,S,LS,NODE" in commands and "ESLN,S" in commands and "ESEL,U,SEC,,1" in commands:
        return "ls_component_attached_elements_except_section_1"
    if "ESEL,R,SEC,,1" in commands or "ESEL,S,SEC,,1" in commands:
        return "beam_type_1_section_1_only"
    if "ESEL,U,SEC,,1" in commands:
        return "beam_type_1_sections_except_section_1"
    if "ESEL,S,TYPE,,1" in commands:
        return "beam_type_1_all_sections"
    return "unknown"


def _report_component_hint(scope: str) -> str:
    if scope == "parameterized_cantilever_arm_type_family":
        return "cantilever_arm"
    if scope == "ls_component_attached_elements_except_section_1":
        return "cantilever_arm"
    if scope == "beam_type_1_sections_except_section_1":
        return "cantilever_arm"
    if scope == "beam_type_1_section_1_only":
        return "square_support"
    if scope == "beam_type_1_all_sections":
        return "mixed_beam_type_1"
    return "unknown"


def extract_result_source_map(apdl_path: Path | str) -> dict[str, Any]:
    apdl_path = Path(apdl_path)
    lines = _read_lines(apdl_path)
    outputs: dict[str, Any] = {}
    for macro_name, output_file in RESULT_MACROS.items():
        create_pattern = re.compile(rf"^\s*\*CREATE\s*,\s*{re.escape(macro_name)}\s*,\s*MAC\b", re.IGNORECASE)
        create_index = next((index for index, line in enumerate(lines) if create_pattern.search(line)), None)
        if create_index is None:
            outputs[output_file] = {
                "status": "missing",
                "output_file": output_file,
                "macro_name": macro_name,
                "source_ref": f"{apdl_path.name}:not found",
            }
            continue
        selectors = _selector_window(lines, create_index)
        scope = _component_scope(selectors)
        outputs[output_file] = {
            "status": "mapped",
            "output_file": output_file,
            "macro_name": macro_name,
            "source_ref": f"{apdl_path.name}:{create_index + 1}",
            "selector_commands": selectors,
            "component_scope": scope,
            "report_component_hint": _report_component_hint(scope),
        }
    return {
        "status": "pass" if all(item["status"] == "mapped" for item in outputs.values()) else "fail",
        "apdl_file": str(apdl_path),
        "outputs": outputs,
        "policy": "Result-to-report comparison must use this declared output source map, not nearest numeric matching.",
    }


def write_result_source_map(job_dir: Path | str, apdl_name: str = "generated_post.mac") -> dict[str, Any]:
    job_dir = Path(job_dir)
    apdl_path = job_dir / apdl_name
    payload = extract_result_source_map(apdl_path)
    (job_dir / "result_source_map.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
