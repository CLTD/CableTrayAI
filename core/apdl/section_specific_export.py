from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SQUARE_OUTPUT = "SQUAREBEAMSTRESS.LIS"
SQUARE_MACRO = "SQUAREBEAMSTRESS-WRITE"


DELETE_NAMES = [
    "SDIR",
    "SBEND1",
    "SBEND2",
    "SBEND3",
    "SBEND4",
    "SSHEAR",
    "NSDIR",
    "NSBEND1",
    "NSBEND2",
    "NSBEND3",
    "NSBEND4",
    "NSSHEAR",
    "YSDIR",
    "YSBEND1",
    "YSBEND2",
    "YSBEND3",
    "YSBEND4",
    "YSSHEAR",
    "YNSDIR",
    "YNSBEND1",
    "YNSBEND2",
    "YNSBEND3",
    "YNSBEND4",
    "YNSSHEAR",
    "SSDIR",
    "SSBEND1",
    "SSBEND2",
    "SSBEND3",
    "SSBEND4",
    "SSSHEAR",
    "SNSDIR",
    "SNSBEND1",
    "SNSBEND2",
    "SNSBEND3",
    "SNSBEND4",
    "SNSSHEAR",
    "ASDIR1",
    "ASDIR2",
    "ASBEND",
    "ASHEAR",
    "BSDIR1",
    "BSDIR2",
    "BSBEND",
    "BSHEAR",
    "DSDIR1",
    "DSDIR2",
    "DSBEND",
    "DSHEAR",
    "MAXSDIR1",
    "MAXSDIR2",
    "MAXSBEND",
    "MAXSHEAR",
    "MAXLSDIR1",
    "MAXLSDIR2",
    "MAXLSBEND",
    "MAXLSHEAR",
    "MAXCSDIR1",
    "MAXCSDIR2",
    "MAXCSBEND",
    "MAXCSHEAR",
]


def _cleanup_block() -> str:
    return "\n".join(f"*DEL,{name}" for name in DELETE_NAMES)


def _find_line(lines: list[str], pattern: str) -> int:
    compiled = re.compile(pattern, re.IGNORECASE)
    for index, line in enumerate(lines):
        if compiled.search(line):
            return index
    raise ValueError(f"Cannot find APDL line matching {pattern!r}")


def _normalize_square_selector(segment: str) -> tuple[str, list[str]]:
    component_selector = "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI square-support selector for component-topology models.",
            "CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM",
        ]
    )
    updated, count = re.subn(
        r"(?ims)^\s*ALLSEL\s*\n"
        r"\s*! CableTrayAI mixed tray standard flow: MAXBEAMSTRESS selects declared structural elements\..*?"
        r"^\s*CMSEL\s*,\s*S\s*,\s*CTAI_STRUCTURAL_ELEMS\s*,\s*ELEM\s*$",
        component_selector,
        segment,
        count=1,
    )
    if count:
        return updated, ["CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM"]

    updated, count = re.subn(
        r"(?ims)^\s*ALLSEL\s*\n"
        r"\s*! CableTrayAI mixed tray standard flow: MAXBEAMSTRESS selects the TYPE=1-equivalent component\..*?"
        r"^\s*CMSEL\s*,\s*A\s*,\s*CTAI_ARM_ELEMS\s*,\s*ELEM\s*$",
        component_selector,
        segment,
        count=1,
    )
    if count:
        return updated, ["CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM"]

    section_selector = "ALLSEL\nESEL,S,TYPE,,1\nESEL,R,SEC,,1"
    updated, count = re.subn(
        r"(?ims)^\s*ALLSEL\s*\n"
        r"\s*! CableTrayAI grouped mixed MAXBEAMSTRESS selector\..*?"
        r"^\s*ESEL\s*,\s*A\s*,\s*SEC\s*,\s*,\s*3\s*$",
        section_selector,
        segment,
        count=1,
    )
    if count:
        return updated, ["ESEL,S,TYPE,,1", "ESEL,R,SEC,,1"]

    updated, count = re.subn(
        r"^\s*ESEL\s*,\s*S\s*,\s*TYPE\s*,\s*,\s*1\s*$",
        "ESEL,S,TYPE,,1\nESEL,R,SEC,,1",
        segment,
        count=1,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if count:
        return updated, ["ESEL,S,TYPE,,1", "ESEL,R,SEC,,1"]

    return segment, ["unknown"]


def _strip_square_audit_plots(segment: str) -> tuple[str, int]:
    """Keep square-support numeric extraction but suppress derived cloud figures."""

    kept: list[str] = []
    removed = 0
    for line in segment.splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("PLLS") or stripped.startswith("/IMAGE,SAVE"):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed


def _square_segment(text: str) -> tuple[str, dict[str, Any]]:
    lines = text.splitlines()
    create = _find_line(lines, r"^\s*\*CREATE\s*,\s*MAXBEAMSTRESS-WRITE\s*,\s*MAC\b")
    call = _find_line(lines[create:], r"^\s*MAXBEAMSTRESS-WRITE\s*$") + create
    elas_index = None
    for index in range(create - 1, -1, -1):
        if re.search(r"^\s*ElasM\s*=", lines[index], re.IGNORECASE):
            elas_index = index
            break
    if elas_index is None:
        start = _find_line(lines, r"^\s*/PREP7\s*$")
    else:
        start = elas_index
        for index in range(elas_index, -1, -1):
            if re.search(r"^\s*/PREP7\s*$", lines[index], re.IGNORECASE):
                start = index
                break
    segment_lines = lines[start : call + 1]
    segment = "\n".join(segment_lines)
    segment, selector = _normalize_square_selector(segment)
    segment = segment.replace("MAXBEAMSTRESS-WRITE", SQUARE_MACRO)
    segment = re.sub(r"\*CFOPEN\s*,\s*MAXBEAMSTRESS\s*,\s*LIS", "*CFOPEN,SQUAREBEAMSTRESS,LIS", segment, flags=re.IGNORECASE)
    segment, removed_plot_commands = _strip_square_audit_plots(segment)
    audit = {
        "source_start_line": start + 1,
        "source_end_line": call + 1,
        "base_macro": "MAXBEAMSTRESS-WRITE",
        "derived_macro": SQUARE_MACRO,
        "selector": selector,
        "output": SQUARE_OUTPUT,
        "removed_plot_commands": removed_plot_commands,
        "source_policy": "Derived from the reviewed MAXBEAMSTRESS numeric block and narrowed to square support only. It writes SQUAREBEAMSTRESS.LIS for deterministic evaluation and deliberately exports no SQ-* stress figures.",
    }
    return segment, audit


def augment_square_support_export(post_path: Path | str) -> dict[str, Any]:
    post_path = Path(post_path)
    text = post_path.read_text(encoding="utf-8", errors="replace")
    if SQUARE_MACRO in text:
        return {"status": "already_present", "post_path": str(post_path), "output": SQUARE_OUTPUT}
    if "MAXBEAMSTRESS-WRITE" not in text:
        return {
            "status": "skipped",
            "post_path": str(post_path),
            "reason": "standard MAXBEAMSTRESS-WRITE block not found",
        }

    lines = text.splitlines()
    try:
        insert_index = _find_line(lines, r"^\s*\*IF\s*,\s*H1\s*,\s*LT\s*,\s*0\.14\s*,\s*THEN\b")
    except ValueError:
        insert_index = _find_line(lines, r"^\s*MAXBEAMSTRESS-WRITE\s*$") + 1
    segment, audit = _square_segment(text)
    block = "\n".join(
        [
            "",
            "! CableTrayAI审查增强：方钢截面1专项应力导出。",
            "! 来源：复制MAXBEAMSTRESS块，并用ESEL,R,SEC,,1收窄到方钢截面。",
            _cleanup_block(),
            segment,
            _cleanup_block(),
            "! CableTrayAI方钢截面1专项应力导出结束。",
            "",
        ]
    )
    updated = "\n".join(lines[:insert_index] + block.splitlines() + lines[insert_index:]) + "\n"
    post_path.write_text(updated, encoding="utf-8", newline="\n")
    payload = {"status": "added", "post_path": str(post_path), **audit}
    (post_path.parent / "section_specific_export_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
