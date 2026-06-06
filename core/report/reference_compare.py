from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docx import Document

from core.report.report_audit import REQUIRED_HEADINGS


REFERENCE_REPORT_PATTERN = "*LXSJ4120.docx"


def find_reference_report(source_root: Path | str = Path("source_materials")) -> Path | None:
    source_root = Path(source_root)
    if not source_root.exists():
        return None
    matches = sorted(source_root.rglob(REFERENCE_REPORT_PATTERN), key=lambda item: item.as_posix())
    return matches[0] if matches else None


def extract_docx_headings(path: Path | str) -> list[str]:
    document = Document(str(path))
    headings: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style_name = paragraph.style.name if paragraph.style else ""
        if style_name.startswith("Heading") or text in REQUIRED_HEADINGS or text[:1].isdigit() or text.startswith(("Appendix", "Reference")):
            headings.append(text)
    return headings


def compare_report_structure(
    generated_docx: Path | str,
    *,
    reference_docx: Path | str | None = None,
    source_root: Path | str = Path("source_materials"),
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    generated_docx = Path(generated_docx)
    reference_path = Path(reference_docx) if reference_docx else find_reference_report(source_root)
    generated_headings = extract_docx_headings(generated_docx) if generated_docx.exists() else []

    if reference_path is None or not reference_path.exists():
        payload = {
            "status": "warning",
            "generated_docx": str(generated_docx),
            "reference_docx": None,
            "generated_heading_count": len(generated_headings),
            "reference_heading_count": 0,
            "matched_reference_headings": [],
            "missing_reference_headings": [],
            "notes": ["Reference report was not found; generated report was only checked against the stage template headings."],
        }
    else:
        reference_headings = extract_docx_headings(reference_path)
        matched = [heading for heading in reference_headings if heading in generated_headings]
        missing = [heading for heading in reference_headings if heading not in generated_headings]
        payload = {
            "status": "pass" if matched else "warning",
            "generated_docx": str(generated_docx),
            "reference_docx": str(reference_path),
            "generated_heading_count": len(generated_headings),
            "reference_heading_count": len(reference_headings),
            "matched_reference_headings": matched,
            "missing_reference_headings": missing,
            "notes": ["This comparison is structural only; numeric values are audited through result.json mapping."],
        }

    if output_path:
        Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
