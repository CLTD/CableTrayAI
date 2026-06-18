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


def _square_segment(text: str) -> tuple[str, dict[str, Any]]:
    lines = text.splitlines()
    start = _find_line(lines, r"^\s*/PREP7\s*$")
    create = _find_line(lines, r"^\s*\*CREATE\s*,\s*MAXBEAMSTRESS-WRITE\s*,\s*MAC\b")
    call = _find_line(lines[create:], r"^\s*MAXBEAMSTRESS-WRITE\s*$") + create
    segment_lines = lines[start : call + 1]
    segment = "\n".join(segment_lines)
    segment = re.sub(
        r"^\s*ESEL\s*,\s*S\s*,\s*TYPE\s*,\s*,\s*1\s*$",
        "ESEL,S,TYPE,,1\nESEL,R,SEC,,1",
        segment,
        count=1,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    segment = segment.replace("MAXBEAMSTRESS-WRITE", SQUARE_MACRO)
    segment = re.sub(r"\*CFOPEN\s*,\s*MAXBEAMSTRESS\s*,\s*LIS", "*CFOPEN,SQUAREBEAMSTRESS,LIS", segment, flags=re.IGNORECASE)
    segment = re.sub(r"(/image\s*,\s*save\s*,\s*)", r"\1SQ-", segment, flags=re.IGNORECASE)
    audit = {
        "source_start_line": start + 1,
        "source_end_line": call + 1,
        "base_macro": "MAXBEAMSTRESS-WRITE",
        "derived_macro": SQUARE_MACRO,
        "selector": ["ESEL,S,TYPE,,1", "ESEL,R,SEC,,1"],
        "output": SQUARE_OUTPUT,
        "source_policy": "从标准MAXBEAMSTRESS提取块派生，并按截面1收窄；建模命令流中方钢由LATT截面1定义。",
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
