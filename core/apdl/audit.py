from __future__ import annotations

import json
import re
from pathlib import Path


PLACEHOLDER_PATTERN = re.compile(r"({{.*?}}|{%.*?%})")

AUDIT_CHECKS = {
    "has_beam188": ("BEAM188", "188"),
    "has_secread": ("SECREAD",),
    "has_material": ("MP,EX", "MP,DENS"),
    "has_constraints": ("D,",),
    "has_coupling": ("CP,", "CPCYC"),
    "has_modal_analysis": ("ANTYPE,2", "MODOPT"),
    "has_response_spectrum": ("ANTYPE,8", "SPOPT", "ACEL", "LSSOLVE"),
    "has_result_extraction": ("*GET", "/OUTPUT", "PRNSOL", "PLESOL", "/IMAGE"),
}


def audit_rendered_apdl(
    rendered_files: list[Path],
    output_path: Path | None = None,
    *,
    require_modal_analysis: bool = True,
) -> dict:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in rendered_files)
    checks: dict[str, bool] = {}
    for name, tokens in AUDIT_CHECKS.items():
        checks[name] = any(token.upper() in combined.upper() for token in tokens)
    if not require_modal_analysis:
        checks["has_modal_analysis"] = True

    unresolved = PLACEHOLDER_PATTERN.findall(combined)
    audit = {
        "status": "pass" if all(checks.values()) and not unresolved else "fail",
        "checks": checks,
        "unresolved_placeholders": unresolved,
        "files": [path.name for path in rendered_files],
    }
    if output_path:
        output_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
