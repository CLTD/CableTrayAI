from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.optimizer.square_section_selector import (
    controlling_evaluation_ratio,
    controlling_section_selection_ratio,
    controlling_square_ratio,
    parse_square_section_name,
)

TRIAL_FINAL_RATIO_TOLERANCE = 0.01


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _first_square_from_model(job_dir: Path) -> str | None:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return None
    text = model_path.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"SECREAD\s*,\s*['\"]?([^,'\"\s]+)", text, flags=re.IGNORECASE):
        section_name = Path(match.group(1)).stem
        if parse_square_section_name(section_name):
            return section_name
    return None


def _square_from_input(job_dir: Path) -> str | None:
    payload = _read_json(job_dir / "input.json", {})
    support = payload.get("support") or {}
    sections = payload.get("sections") or []
    support_section_id = str(support.get("support_section_id") or "").strip()
    for value in [support_section_id, *(str(item.get("sect_file") or item.get("section_id") or "") for item in sections)]:
        section_name = Path(value).stem
        if parse_square_section_name(section_name):
            return section_name
    return None


def write_square_section_selection_summary(job_dir: Path | str) -> dict[str, Any]:
    """Write the square tube section selected for this intake/job.

    The I column in first-version intake files may be empty, so the platform
    must leave an explicit audit record of the section it used or auto-selected.
    """

    job_dir = Path(job_dir)
    input_payload = _read_json(job_dir / "input.json", {})
    metadata = input_payload.get("metadata") or {}
    previous_selection = _read_json(job_dir / "square_section_selection.json", {})
    if not isinstance(previous_selection, dict):
        previous_selection = {}
    selected = previous_selection.get("selected") if isinstance(previous_selection, dict) else None
    if not isinstance(selected, dict) and previous_selection.get("section_name"):
        # Legacy deployments wrote the publish summary directly to
        # square_section_selection.json.  Treat that flat shape as the selected
        # trial record so the trial/final ratio gate cannot be bypassed.
        selected = previous_selection
    section_name = (
        (selected or {}).get("section_name")
        or metadata.get("square_section_selected")
        or _first_square_from_model(job_dir)
        or _square_from_input(job_dir)
    )
    candidate = parse_square_section_name(str(section_name)) if section_name else None
    evaluation_summary = _read_json(job_dir / "evaluation_summary.json", [])
    final_square_support_ratio = controlling_square_ratio(evaluation_summary if isinstance(evaluation_summary, list) else [])
    final_section_selection_ratio = controlling_section_selection_ratio(evaluation_summary if isinstance(evaluation_summary, list) else [])
    final_chapter6_controlling_ratio = controlling_evaluation_ratio(evaluation_summary if isinstance(evaluation_summary, list) else [])
    trial_controlling_ratio = (
        (selected or {}).get("trial_controlling_ratio")
        or (selected or {}).get("section_selection_ratio")
        or (selected or {}).get("controlling_ratio")
        or previous_selection.get("trial_controlling_ratio")
        or metadata.get("square_section_selected_ratio")
    )
    trial_square_support_ratio = (
        (selected or {}).get("trial_square_support_ratio")
        or (selected or {}).get("square_support_ratio")
        or previous_selection.get("trial_square_support_ratio")
    )
    controlling_ratio = (
        final_section_selection_ratio
        if final_section_selection_ratio is not None
        else final_square_support_ratio
        if final_square_support_ratio is not None
        else trial_controlling_ratio
    )
    ratio_consistency_status = "not_checked"
    ratio_consistency_message = "No formal Chapter 6.1 section-selection ratio was available."
    if final_section_selection_ratio is not None and trial_controlling_ratio is not None:
        delta = abs(float(final_section_selection_ratio) - float(trial_controlling_ratio))
        ratio_consistency_status = "pass" if delta <= TRIAL_FINAL_RATIO_TOLERANCE else "fail"
        ratio_consistency_message = (
            "Formal Chapter 6.1 section-selection ratio matches the section-search trial ratio."
            if ratio_consistency_status == "pass"
            else "Formal Chapter 6.1 section-selection ratio differs from the section-search trial ratio by more than 0.01; section economy is not reliable until clean trial workspaces are rerun."
        )
    status = "pass" if candidate else "warning"
    if controlling_ratio is None:
        acceptance = "unknown"
    else:
        acceptance = "pass" if float(controlling_ratio) <= 1.0 else "fail"
    if ratio_consistency_status == "fail":
        status = "fail"
        acceptance = "fail"
    payload = {
        "status": status,
        "job_dir": str(job_dir),
        "section_name": candidate.section_name if candidate else section_name,
        "outer_mm": candidate.outer_mm if candidate else None,
        "thickness_mm": candidate.thickness_mm if candidate else None,
        "estimated_area_mm2": candidate.estimated_area_mm2 if candidate else None,
        "controlling_ratio": controlling_ratio,
        "final_controlling_ratio": final_section_selection_ratio,
        "final_section_selection_ratio": final_section_selection_ratio,
        "final_chapter6_controlling_ratio": final_chapter6_controlling_ratio,
        "final_square_support_ratio": final_square_support_ratio,
        "trial_controlling_ratio": trial_controlling_ratio,
        "trial_square_support_ratio": trial_square_support_ratio,
        "ratio_source": "evaluation_summary.json:Chapter 6.1 structural member ratios" if final_section_selection_ratio is not None else "square_section_selection_trial",
        "ratio_consistency_status": ratio_consistency_status,
        "ratio_consistency_message": ratio_consistency_message,
        "ratio_consistency_tolerance": TRIAL_FINAL_RATIO_TOLERANCE,
        "selection_acceptance": acceptance,
        "is_design_acceptable": acceptance == "pass",
        "selection_status": metadata.get("square_section_selection_status") or previous_selection.get("status") or "reported_or_source_command",
        "selection_policy": (
            previous_selection.get("policy")
            or "If intake column I is empty, use no more than two fresh ANSYS candidate trials to target 0.60 <= ratio <= 0.9999 inside the allowed square SECT list."
        ),
        "source_ref": "generated_model.mac SECREAD / input.json metadata / square_section_selection.json",
    }
    (job_dir / "square_section_selection_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
