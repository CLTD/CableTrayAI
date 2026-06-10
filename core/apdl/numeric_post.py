from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


NUMERIC_POST_MACRO = "generated_post_numeric.mac"
NUMERIC_POST_AUDIT = "generated_post_numeric_audit.json"

_GRAPHICS_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"/IMAGE\b|/SHOW\b|/REPLOT\b|/REP\b|/VIEW\b|/ANG\b|/AUTO\b|"
    r"/RGB\b|/ESHAPE\b|/PLOPTS\b|/PNGR\b|/COLOR\b|/UDOC\b|"
    r"/DEVICE\b|/GRAPHICS\b|EPLOT\b|NPLOT\b|PLLS\b|PLDISP\b|PLNSOL\b|PLESOL\b"
    r")",
    re.IGNORECASE,
)


def build_numeric_post_macro(
    job_dir: Path | str,
    *,
    source_name: str = "generated_post.mac",
    output_name: str = NUMERIC_POST_MACRO,
) -> dict[str, Any]:
    """Create a numeric-only post macro for the main real ANSYS run.

    The reviewed ``generated_post.mac`` is preserved for human audit and for
    post-only figure export.  The main run only needs LIS/OUP/load extraction,
    so graphics commands are commented out to avoid batch MAPDL stalls and
    repeated ``/IMAGE requires /MENU`` warnings during candidate selection.
    """

    job_dir = Path(job_dir)
    source_path = job_dir / source_name
    output_path = job_dir / output_name
    if not source_path.exists():
        audit = {
            "status": "missing_source",
            "source": source_name,
            "target": output_name,
            "commented_graphics_commands": 0,
        }
        (job_dir / NUMERIC_POST_AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        return audit

    output_lines: list[str] = [
        "! CableTrayAI numeric-only post macro.",
        "! generated_post.mac remains the reviewed source-derived post stream.",
        "! Graphics commands are skipped here; export_figures.mac handles images in a separate post-only ANSYS run.",
    ]
    commented = 0
    for line in source_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if _GRAPHICS_ONLY_RE.match(line):
            output_lines.append(f"! CableTrayAI numeric-post skipped graphics command: {line}")
            commented += 1
        else:
            output_lines.append(line)
    output_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8", newline="\n")
    audit = {
        "status": "pass",
        "source": source_name,
        "target": output_name,
        "commented_graphics_commands": commented,
        "policy": (
            "Main ANSYS runs use generated_post_numeric.mac for deterministic LIS/OUP/load extraction. "
            "Report figures are generated afterwards by export_figures.mac from the preserved generated_post.mac."
        ),
    }
    (job_dir / NUMERIC_POST_AUDIT).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
