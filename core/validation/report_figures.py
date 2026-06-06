from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


APPENDIX_TO_GENERATED = {
    "A-1": "MOTAI-1.PNG",
    "A-2": "MOTAI-2.PNG",
    "A-3": "MOTAI-3.PNG",
    "A-4": "MOTAI-4.PNG",
    "B-1": "SQ-B1SDIR1.PNG",
    "B-2": "SQ-B2SDIR2.PNG",
    "B-3": "SQ-B3SBEND.PNG",
    "B-4": "SQ-B4SHEAR.PNG",
    "B-5": "SQ-D1SDIR1.PNG",
    "B-6": "SQ-D2SDIR2.PNG",
    "B-7": "SQ-D3SBEND.PNG",
    "B-8": "SQ-D4SHEAR.PNG",
    "C-1": "TB1SDIR1.PNG",
    "C-2": "TB2SDIR2.PNG",
    "C-3": "TB3SBEND.PNG",
    "C-4": "TB4SHEAR.PNG",
    "C-5": "TD1SDIR1.PNG",
    "C-6": "TD2SDIR2.PNG",
    "C-7": "TD3SBEND.PNG",
    "C-8": "TD4SHEAR.PNG",
}


def _caption_key(text: str) -> str | None:
    match = re.search(r"图([ABC])-([1-8])\b", text)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"


def _iter_paragraph_images(document: Any):
    from docx.oxml.ns import qn

    rels = document.part.rels
    paragraphs = list(document.paragraphs)
    for index, paragraph in enumerate(paragraphs):
        images = []
        for blip in paragraph._element.xpath(".//a:blip"):
            rid = blip.get(qn("r:embed")) or blip.get(qn("r:link"))
            rel = rels.get(rid)
            if rel is None or "image" not in rel.reltype:
                continue
            images.append((rid, rel))
        if not images:
            continue
        next_caption = ""
        next_key = None
        for follow in paragraphs[index + 1 : index + 5]:
            text = " ".join(follow.text.split())
            key = _caption_key(text)
            if key:
                next_caption = text
                next_key = key
                break
            if text and not next_caption:
                next_caption = text
        for rid, rel in images:
            yield index + 1, rid, rel, next_key, next_caption


def extract_report_appendix_figures(report_path: Path | str, output_dir: Path | str) -> dict[str, Any]:
    """Extract only real appendix A/B/C images from a baseline report.

    The reports contain QA stamps, signatures, and model screenshots. Those are
    intentionally ignored here because they are not appendix verification plots.
    """

    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("python-docx is required to extract report appendix figures") from exc

    report_path = Path(report_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    document = Document(str(report_path))
    manifest: list[dict[str, Any]] = []
    for paragraph_index, rid, rel, appendix_key, caption in _iter_paragraph_images(document):
        if appendix_key not in APPENDIX_TO_GENERATED:
            continue
        ext = Path(rel.target_ref).suffix or ".png"
        target_name = f"report_{appendix_key.replace('-', '_')}{ext}"
        target = output_dir / target_name
        target.write_bytes(rel.target_part.blob)
        manifest.append(
            {
                "appendix_key": appendix_key,
                "appendix": appendix_key[0],
                "caption": caption,
                "report_file": target_name,
                "generated_file": APPENDIX_TO_GENERATED[appendix_key],
                "paragraph_index": paragraph_index,
                "relationship_id": rid,
                "source_ref": f"{report_path.name}: paragraph {paragraph_index + 1} caption {caption}",
            }
        )
    payload = {
        "status": "pass" if manifest else "blocked",
        "report_path": str(report_path),
        "output_dir": str(output_dir),
        "figures": manifest,
        "policy": "Only figures whose following caption is 图A/B/C-n are extracted. QA stamps and non-appendix images are excluded.",
    }
    (output_dir / "report_appendix_figures_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
