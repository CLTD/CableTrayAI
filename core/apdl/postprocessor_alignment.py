from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


POST_HEADER_MARKER = "! CableTrayAI postprocessor branch parameters"


def _load_input(job_dir: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload is not None:
        return payload
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return {}
    return json.loads(input_path.read_text(encoding="utf-8"))


def _square_outer_m(payload: dict[str, Any]) -> float | None:
    metadata = payload.get("metadata") or {}
    support = payload.get("support") or {}
    value = metadata.get("square_section_outer_mm")
    if value is not None:
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            pass
    value = support.get("square_tube_width_m")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    spec = str(metadata.get("square_section_spec") or support.get("support_section_id") or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-*xX]\s*\1", spec)
    if match:
        return float(match.group(1)) / 1000.0
    return None


def _square_thickness_m(payload: dict[str, Any]) -> float | None:
    metadata = payload.get("metadata") or {}
    value = metadata.get("square_section_thickness_mm")
    if value is not None:
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            pass
    spec = str(metadata.get("square_section_spec") or (payload.get("support") or {}).get("support_section_id") or "")
    match = re.search(r"\d+(?:\.\d+)?\s*[-*xX]\s*\d+(?:\.\d+)?\s*[-*xX]\s*(\d+(?:\.\d+)?)", spec)
    if match:
        return float(match.group(1)) / 1000.0
    return None


def _prepend_branch_parameters(text: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    outer_m = _square_outer_m(payload)
    thickness_m = _square_thickness_m(payload)
    if outer_m is None:
        return text, {"status": "skipped", "reason": "square section outer width not available"}
    if POST_HEADER_MARKER in text:
        updated = re.sub(r"(?m)^H1\s*=\s*[-+0-9.Ee]+", f"H1={outer_m:.6f}", text, count=1)
        if thickness_m is not None:
            if re.search(r"(?m)^H2\s*=", updated):
                updated = re.sub(r"(?m)^H2\s*=\s*[-+0-9.Ee]+", f"H2={thickness_m:.6f}", updated, count=1)
            else:
                updated = updated.replace(f"H1={outer_m:.6f}", f"H1={outer_m:.6f}\nH2={thickness_m:.6f}", 1)
        return updated, {
            "status": "updated_existing" if updated != text else "already_current",
            "H1_m": outer_m,
            "H2_m": thickness_m,
            "source_ref": "input.json:metadata.square_section_outer_mm/support.square_tube_width_m",
        }
    lines = [
        POST_HEADER_MARKER,
        "! H1 controls the Appendix C post branch: <=120 mm uses TB/TD cantilever clouds; >120 mm uses weld-principle force extraction.",
        "! The value is injected from input.json so new intakes do not inherit stale source-package dimensions.",
        f"H1={outer_m:.6f}",
    ]
    if thickness_m is not None:
        lines.extend(
            [
                "! H2 records square tube wall thickness in meters for downstream source traceability.",
                f"H2={thickness_m:.6f}",
            ]
        )
    lines.append("")
    return "\n".join(lines) + text, {
        "status": "applied",
        "H1_m": outer_m,
        "H2_m": thickness_m,
        "source_ref": "input.json:metadata.square_section_outer_mm/support.square_tube_width_m",
    }


def _align_appendix_c_threshold(text: str) -> tuple[str, dict[str, Any]]:
    pattern = re.compile(r"^\s*\*IF\s*,\s*H1\s*,\s*LT\s*,\s*0\.14\s*,\s*THEN\s*$", re.IGNORECASE | re.MULTILINE)
    replacement = (
        "! CableTrayAI Appendix C branch rule: square outer width <=120 mm exports TB/TD cantilever stress clouds; >120 mm uses weld-principle extraction.\n"
        "*IF,H1,LE,0.120001,THEN\n"
    )
    updated, count = pattern.subn(replacement, text, count=1)
    return updated, {
        "status": "applied" if count else "not_found",
        "replaced_count": count,
        "source_ref": "analysis_scope.square_outer_width_le_120_requires_cantilever_stress_clouds",
    }


def _parameterized_cantilever_selector() -> str:
    return "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI audited cantilever selector for parameterized S2 models.",
            "! 方钢 support is TYPE=1; tray arms are layer-specific BEAM188 types:",
            "!   front: 10*I+2 and 10*I+3",
            "!   back : 200*I+2 and 200*I+3",
            "! This replaces the shared-source TYPE=1/SEC!=1 selector, which becomes an empty set after parameterization.",
            "ESEL,NONE",
            "*DO,I,1,qiancengshu,1",
            "ESEL,A,TYPE,,10*I+2",
            "ESEL,A,TYPE,,10*I+3",
            "*ENDDO",
            "*DO,I,1,houcengshu,1",
            "ESEL,A,TYPE,,200*I+2",
            "ESEL,A,TYPE,,200*I+3",
            "*ENDDO",
        ]
    )


def _model_uses_source_type1_arm_topology(job_dir: Path) -> bool:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return False
    model_text = model_path.read_text(encoding="utf-8", errors="ignore")
    has_source_arm_latt = bool(re.search(r"LATT\s*,\s*1\s*,\s*,\s*1\s*,\s*,\s*,\s*,\s*[23]\b", model_text, re.IGNORECASE))
    has_parameterized_arm_type = bool(re.search(r"10\s*\*\s*I\s*\+\s*[23]|200\s*\*\s*I\s*\+\s*[23]", model_text, re.IGNORECASE))
    return has_source_arm_latt and not has_parameterized_arm_type


def _align_tmax_selector(text: str, *, preserve_source_type1_arm_topology: bool = False) -> tuple[str, dict[str, Any]]:
    create = re.search(r"^\s*\*CREATE\s*,\s*TMAXBEAMSTRESS-WRITE\s*,\s*MAC\b", text, re.IGNORECASE | re.MULTILINE)
    if not create:
        return text, {"status": "not_found", "reason": "TMAXBEAMSTRESS-WRITE not found"}
    if preserve_source_type1_arm_topology:
        return text, {
            "status": "source_topology_preserved",
            "source_ref": "generated_model.mac:LATT assigns square support and tray arms to TYPE=1 with SEC filtering",
            "selector": ["ESEL,S,TYPE,,1", "ESEL,U,SEC,,1"],
            "policy": "Standard command-flow family models keep the audited source TMAX selector because tray arms are TYPE=1 and non-square sections.",
        }
    prefix = text[: create.start()]
    suffix = text[create.start() :]
    old_selector = re.compile(
        r"(?:!\s*CableTrayAI audited selection for cantilever/root weld stress\.\s*\n"
        r"!\s*Source:.*?\n"
        r"!\s*Section 1.*?\n)?"
        r"\s*ALLSEL\s*\n\s*ESEL\s*,\s*S\s*,\s*TYPE\s*,\s*,\s*1\s*\n\s*ESEL\s*,\s*U\s*,\s*SEC\s*,\s*,\s*1\s*",
        re.IGNORECASE | re.DOTALL,
    )
    matches = list(old_selector.finditer(prefix))
    if not matches:
        return text, {"status": "not_found", "reason": "legacy TYPE=1/SEC!=1 selector not found before TMAX"}
    match = matches[-1]
    updated_prefix = prefix[: match.start()] + _parameterized_cantilever_selector() + "\n" + prefix[match.end() :]
    return updated_prefix + suffix, {
        "status": "applied",
        "source_ref": "generated_model.mac:LATT assigns tray arms to TYPE 10*I+2/10*I+3 and 200*I+2/200*I+3",
        "old_selector": ["ESEL,S,TYPE,,1", "ESEL,U,SEC,,1"],
        "new_selector": [
            "ESEL,NONE",
            "ESEL,A,TYPE,,10*I+2",
            "ESEL,A,TYPE,,10*I+3",
            "ESEL,A,TYPE,,200*I+2",
            "ESEL,A,TYPE,,200*I+3",
        ],
    }


def align_postprocessor_to_intake(job_dir: Path | str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Patch generated post commands so the shared S2 extractor matches the parameterized model.

    The original PIP assumes a model where BEAM188 TYPE=1 plus section filtering can
    isolate support and tray-arm sets. The current parameterized model uses TYPE=1
    for the square support and per-layer types for tray arms. This function keeps
    the source block but aligns branch parameters and selectors with that topology.
    """

    job_dir = Path(job_dir)
    post_path = job_dir / "generated_post.mac"
    if not post_path.exists():
        return {"status": "skipped", "reason": "generated_post.mac missing"}
    payload = _load_input(job_dir, payload)
    original = post_path.read_text(encoding="utf-8", errors="replace")
    text, branch_audit = _prepend_branch_parameters(original, payload)
    text, threshold_audit = _align_appendix_c_threshold(text)
    preserve_source_topology = _model_uses_source_type1_arm_topology(job_dir)
    text, selector_audit = _align_tmax_selector(text, preserve_source_type1_arm_topology=preserve_source_topology)
    changed = text != original
    if changed:
        post_path.write_text(text, encoding="utf-8", newline="\n")
    audit = {
        "status": "applied" if changed else "unchanged",
        "post_path": str(post_path),
        "branch_parameters": branch_audit,
        "appendix_c_threshold": threshold_audit,
        "tmax_selector": selector_audit,
        "policy": "Do not hide all-zero TMAX output. Prevent it by selecting the actual parameterized tray-arm element types and by injecting the intake square-section branch parameter.",
    }
    (job_dir / "postprocessor_alignment_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return audit
