from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SOURCE_FILENAMES = (
    "建模标准化命令流.txt",
    "01 双侧同类型电缆桥架-方钢托臂.PIP",
    "02 计算用命令流.mac",
    "导出数据-S2.PIP",
)


@dataclass(frozen=True)
class CommandBlock:
    key: str
    label: str
    patterns: tuple[str, ...]
    required: bool = True


COMMAND_BLOCKS = (
    CommandBlock("element_type", "ET / BEAM188", (r"\bET\s*,", r"BEAM188")),
    CommandBlock("keyopt", "KEYOPT", (r"\bKEYOPT\s*,",)),
    CommandBlock("material", "MP material properties", (r"\bMP\s*,\s*EX", r"\bMP\s*,\s*PRXY", r"\bMP\s*,\s*DENS")),
    CommandBlock("section", "SECTYPE / SECOFFSET / SECREAD", (r"\bSECTYPE\s*,", r"\bSECOFFSET\s*,", r"\bSECREAD\s*,")),
    CommandBlock("geometry", "K / L geometry", (r"^\s*K\s*,", r"^\s*L\s*,")),
    CommandBlock("mesh", "LATT / LESIZE / LMESH", (r"\bLATT\s*,", r"\bLESIZE\s*,", r"\bLMESH\s*,")),
    CommandBlock("coupling", "CP / CPCYC", (r"\bCP\s*,", r"\bCPCYC\s*,")),
    CommandBlock("selection", "NSEL / LSEL / CM / CMSEL", (r"\bNSEL\s*,", r"\bLSEL\s*,", r"\bCM\s*,", r"\bCMSEL\s*,")),
    CommandBlock("constraint", "D constraint command", (r"^\s*D\s*,",)),
    CommandBlock("modal", "Modal analysis", (r"\bANTYPE\s*,\s*(2|MODAL)", r"\bMODOPT\s*,")),
    CommandBlock("spectrum", "Response spectrum analysis", (r"\bANTYPE\s*,\s*(8|SPECTR)", r"\bSPOPT\s*,", r"\bSV\s*,")),
    CommandBlock("post", "POST1/POST26 extraction", (r"/POST1", r"/POST26", r"\*GET\s*,")),
    CommandBlock("lis_output", "LIS output", (r"/OUTPUT\s*,", r"\*CFOPEN\s*,.*LIS", r"\*VWRITE")),
    CommandBlock("image_output", "BMP/image output", (r"/IMAGE\s*,\s*SAVE", r"\bbmp\b")),
)


def read_text_with_encoding(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb2312", "latin1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def source_files(source_root: Path | str = Path("source_materials/model_commands")) -> list[Path]:
    root = Path(source_root)
    files: list[Path] = []
    for filename in SOURCE_FILENAMES:
        files.extend(path for path in root.rglob(filename) if path.is_file())
    files.extend(path for path in root.rglob("*.SECT") if path.is_file())
    return sorted(set(files), key=lambda item: item.as_posix())


def _matches_block(line: str, block: CommandBlock) -> bool:
    return any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in block.patterns)


def _scan_text(text: str, block: CommandBlock, source_name: str) -> list[dict]:
    matches: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _matches_block(line, block):
            matches.append(
                {
                    "source_ref": f"{source_name}:{line_no}",
                    "line_start": line_no,
                    "line_end": line_no,
                    "text": line.strip(),
                }
            )
    return matches


def _combined_template_text(template_dir: Path) -> str:
    parts: list[str] = []
    for path in sorted(template_dir.rglob("*")):
        if path.suffix in {".j2", ".mac", ".txt"}:
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def scan_apdl_source_diff(
    source_root: Path | str = Path("source_materials/model_commands"),
    template_dir: Path | str = Path("templates/apdl"),
) -> dict:
    source_root = Path(source_root)
    template_dir = Path(template_dir)
    templates = _combined_template_text(template_dir)
    files = source_files(source_root)

    blocks: list[dict] = []
    for block in COMMAND_BLOCKS:
        source_matches: list[dict] = []
        for path in files:
            if path.suffix.upper() == ".SECT" and block.key != "section":
                continue
            text, encoding = read_text_with_encoding(path)
            for match in _scan_text(text, block, path.relative_to(source_root).as_posix()):
                match["encoding"] = encoding
                source_matches.append(match)
        template_matches = _scan_text(templates, block, "templates/apdl")
        covered = bool(template_matches)
        blocks.append(
            {
                "key": block.key,
                "label": block.label,
                "required": block.required,
                "status": "covered" if covered else "missing",
                "source_matches": source_matches[:20],
                "source_match_count": len(source_matches),
                "template_matches": template_matches,
            }
        )

    required_missing = [item["key"] for item in blocks if item["required"] and item["status"] != "covered"]
    return {
        "status": "pass" if not required_missing else "needs_review",
        "required_missing": required_missing,
        "source_files": [path.relative_to(source_root).as_posix() for path in files],
        "blocks": blocks,
    }


def write_apdl_source_reports(
    source_root: Path | str = Path("source_materials/model_commands"),
    template_dir: Path | str = Path("templates/apdl"),
    docs_dir: Path | str = Path("docs"),
) -> dict:
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    report = scan_apdl_source_diff(source_root=source_root, template_dir=template_dir)
    (docs_dir / "apdl_source_diff.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# APDL Template Gap Report",
        "",
        f"Status: {report['status']}",
        "",
        "## Covered Command Blocks",
        "",
        "| Block | Template refs | Source refs sampled |",
        "| --- | --- | --- |",
    ]
    for block in report["blocks"]:
        if block["status"] == "covered":
            template_refs = ", ".join(match["source_ref"] for match in block["template_matches"]) or "-"
            source_refs = ", ".join(match["source_ref"] for match in block["source_matches"][:5]) or "-"
            lines.append(f"| {block['label']} | {template_refs} | {source_refs} |")

    lines.extend(["", "## Missing Or Manual Review Blocks", "", "| Block | Reason | Source refs sampled |", "| --- | --- | --- |"])
    for block in report["blocks"]:
        if block["status"] != "covered":
            source_refs = ", ".join(match["source_ref"] for match in block["source_matches"][:5]) or "not found in scanned sources"
            lines.append(f"| {block['label']} | Not represented in templates yet | {source_refs} |")

    (docs_dir / "APDL_TEMPLATE_GAP_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    trace_lines = [
        "# APDL Source Traceability",
        "",
        "This file records source APDL/PIP/MAC command evidence used by the Stage 2 template gap scan.",
        "",
        "| Block | Source match count | Sample source refs |",
        "| --- | ---: | --- |",
    ]
    for block in report["blocks"]:
        refs = ", ".join(match["source_ref"] for match in block["source_matches"][:10]) or "-"
        trace_lines.append(f"| {block['label']} | {block['source_match_count']} | {refs} |")
    (docs_dir / "APDL_SOURCE_TRACEABILITY.md").write_text("\n".join(trace_lines) + "\n", encoding="utf-8")
    return report


def assert_no_unrendered_jinja(paths: Iterable[Path]) -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    if "{{" in text or "{%" in text:
        raise AssertionError("Rendered APDL contains unrendered Jinja placeholders")
