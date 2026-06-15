from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.optimizer.square_section_selector import (
    SquareSectionCandidate,
    discover_square_section_candidates,
    parse_square_section_name,
)

MIN_SUPPORT_SPACING_M = 0.5
SUPPORT_SPACING_STEP_M = 0.1
SUPPORT_SPACING_RECOVERY_TARGET_RATIOS = (0.85, 0.75, 0.65, 0.55)
MAX_SUPPORT_SPACING_RECOVERY_ATTEMPTS = len(SUPPORT_SPACING_RECOVERY_TARGET_RATIOS)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _normalise_square_section_ids(values: Any) -> list[str]:
    if values in (None, ""):
        return []
    if not isinstance(values, (list, tuple, set)):
        values = re.sub(r"\s+", ",", str(values).replace("，", ",").replace("；", ",").replace("、", ","))
    raw_items = list(values) if isinstance(values, (list, tuple, set)) else re.split(r"[,，;；、\s]+", str(values))
    normalised: list[str] = []
    for item in raw_items:
        item = str(item or "").strip().replace("×", "x")
        text = re.sub(r"[xX*×]", "-", str(item or "").strip())
        text = re.sub(r"\s+", "", text)
        shorthand = re.fullmatch(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)", text)
        if shorthand:
            text = f"{shorthand.group(1)}-{shorthand.group(1)}-{shorthand.group(2)}"
        parsed = parse_square_section_name(text)
        if not parsed:
            continue
        section_id = f"{parsed.outer_mm:g}-{parsed.outer_mm:g}-{parsed.thickness_mm:g}"
        if section_id not in normalised:
            normalised.append(section_id)
    return normalised


def _allowed_square_section_ids(payload: dict[str, Any]) -> list[str]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    return _normalise_square_section_ids(
        metadata.get("allowed_square_section_ids")
        or support.get("allowed_square_section_ids")
        or metadata.get("allowed_square_sections")
        or support.get("allowed_square_sections")
    )


def _candidate_map_for_allowed(
    payload: dict[str, Any],
    *,
    source_root: Path | str,
) -> dict[str, SquareSectionCandidate]:
    allowed_ids = _allowed_square_section_ids(payload)
    if not allowed_ids:
        return {}
    discovered = {
        candidate.section_name: candidate
        for candidate in discover_square_section_candidates(source_root)
    }
    candidates: dict[str, SquareSectionCandidate] = {}
    for section_id in allowed_ids:
        parsed = parse_square_section_name(section_id)
        if not parsed:
            continue
        candidates[section_id] = discovered.get(section_id) or parsed
    return candidates


def _max_allowed_candidate(
    payload: dict[str, Any],
    *,
    source_root: Path | str,
) -> SquareSectionCandidate | None:
    candidates = list(_candidate_map_for_allowed(payload, source_root=source_root).values())
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda item: (
            item.estimated_bending_section_modulus_mm3,
            item.estimated_area_mm2,
            item.outer_mm,
            item.thickness_mm,
        ),
    )


def _candidate_result_by_section(selection: dict[str, Any], section_name: str) -> dict[str, Any] | None:
    for item in selection.get("candidate_results") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("section_name") or item.get("candidate_section") or "") == section_name:
            return item
    return None


def _result_is_deterministic_overlimit(item: dict[str, Any]) -> bool:
    ratio = _as_float(item.get("section_selection_ratio") or item.get("controlling_ratio"))
    if ratio is None or ratio <= 1.0:
        return False
    if str(item.get("run_status") or "") not in {"success", "pass"}:
        return False
    if item.get("failed_non_ratio_checks"):
        return False
    diagnosis = item.get("diagnosis") if isinstance(item.get("diagnosis"), dict) else {}
    return bool(diagnosis.get("continue_square_section_search", True))


def _failed_ratio_from_validation(job_dir: Path) -> tuple[float | None, list[str], list[dict[str, Any]]]:
    path = job_dir / "result_validation.json"
    if not path.exists():
        return None, ["result_validation_missing"], []
    try:
        validation = _read_json(path)
    except json.JSONDecodeError:
        return None, ["result_validation_json_invalid"], []
    ratios: list[float] = []
    failed_non_ratio: list[str] = []
    ratio_evidence: list[dict[str, Any]] = []
    for check in validation.get("checks") or []:
        if not isinstance(check, dict) or check.get("status") != "fail":
            continue
        check_id = str(check.get("check_id") or "")
        if check_id != "evaluation_ratio_limit":
            failed_non_ratio.append(check_id)
            continue
        evidence = [item for item in check.get("evidence") or [] if isinstance(item, dict)]
        for item in evidence:
            ratio = _as_float(item.get("ratio"))
            if ratio is None:
                continue
            ratios.append(ratio)
            ratio_evidence.append(
                {
                    "check_id": item.get("check_id"),
                    "ratio": ratio,
                }
            )
    return (max(ratios) if ratios else None), failed_non_ratio, ratio_evidence


def _current_selected_square_section(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    candidates = [
        metadata.get("square_section_selected"),
        metadata.get("square_section_spec"),
        support.get("support_section_id"),
    ]
    for section in payload.get("sections") or []:
        if isinstance(section, dict):
            candidates.append(section.get("sect_file"))
            candidates.append(section.get("section_id"))
    for value in candidates:
        parsed = parse_square_section_name(str(value)) if value else None
        if parsed:
            return f"{parsed.outer_mm:g}-{parsed.outer_mm:g}-{parsed.thickness_mm:g}"
    return None


def _round_spacing_down(value: float) -> float:
    return math.floor((value + 1e-9) / SUPPORT_SPACING_STEP_M) * SUPPORT_SPACING_STEP_M


def _next_spacing(current_spacing_m: float, failed_ratio: float, attempt_index: int) -> float | None:
    if current_spacing_m <= MIN_SUPPORT_SPACING_M:
        return None
    target_index = min(max(1, attempt_index), MAX_SUPPORT_SPACING_RECOVERY_ATTEMPTS) - 1
    target_ratio = SUPPORT_SPACING_RECOVERY_TARGET_RATIOS[target_index]
    raw = current_spacing_m * math.sqrt(target_ratio / max(failed_ratio, 1e-9))
    reduced = _round_spacing_down(raw)
    reduced = min(reduced, current_spacing_m - SUPPORT_SPACING_STEP_M)
    reduced = max(MIN_SUPPORT_SPACING_M, reduced)
    reduced = round(reduced, 3)
    if reduced >= current_spacing_m - 1e-9:
        return None
    return reduced


def _base_plan(
    job_dir: Path,
    *,
    payload: dict[str, Any],
    failed_ratio: float | None,
    max_allowed: SquareSectionCandidate | None,
    trigger: str,
    attempt_index: int,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    current_spacing = _as_float(support.get("support_spacing_m"))
    if max_allowed is None:
        return {"status": "skipped", "reason": "allowed_square_sections_missing_or_invalid", "trigger": trigger}
    if failed_ratio is None or failed_ratio <= 1.0:
        return {
            "status": "skipped",
            "reason": "deterministic_ratio_is_not_overlimit",
            "trigger": trigger,
            "max_allowed_square_section": max_allowed.section_name,
            "failed_ratio": failed_ratio,
        }
    if current_spacing is None or current_spacing <= 0:
        return {"status": "skipped", "reason": "support_spacing_m_missing_or_invalid", "trigger": trigger}
    if attempt_index > MAX_SUPPORT_SPACING_RECOVERY_ATTEMPTS:
        return {
            "status": "skipped",
            "reason": "support_spacing_recovery_attempt_limit_reached",
            "trigger": trigger,
            "attempt_index": attempt_index,
            "max_attempts": MAX_SUPPORT_SPACING_RECOVERY_ATTEMPTS,
        }
    new_spacing = _next_spacing(current_spacing, failed_ratio, attempt_index)
    if new_spacing is None:
        return {
            "status": "skipped",
            "reason": "support_spacing_already_at_minimum_or_cannot_reduce",
            "trigger": trigger,
            "current_support_spacing_m": current_spacing,
            "minimum_support_spacing_m": MIN_SUPPORT_SPACING_M,
        }
    target_ratio = SUPPORT_SPACING_RECOVERY_TARGET_RATIOS[
        min(max(1, attempt_index), MAX_SUPPORT_SPACING_RECOVERY_ATTEMPTS) - 1
    ]
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "status": "pass",
        "trigger": trigger,
        "attempt_index": attempt_index,
        "max_attempts": MAX_SUPPORT_SPACING_RECOVERY_ATTEMPTS,
        "current_support_spacing_m": current_spacing,
        "new_support_spacing_m": new_spacing,
        "original_support_spacing_m": metadata.get("support_spacing_original_m") or current_spacing,
        "failed_ratio": failed_ratio,
        "target_ratio_for_spacing_estimate": target_ratio,
        "max_allowed_square_section": max_allowed.section_name,
        "max_allowed_estimated_bending_section_modulus_mm3": max_allowed.estimated_bending_section_modulus_mm3,
        "spacing_step_m": SUPPORT_SPACING_STEP_M,
        "minimum_support_spacing_m": MIN_SUPPORT_SPACING_M,
        "evidence": evidence,
        "policy": (
            "When the largest intake-allowed square tube is active and fresh deterministic ratio gates remain over "
            "1.0, the software does not add unlisted square sections or publish failure immediately. It reduces the "
            "support spacing as a design-parameter recovery, regenerates APDL, reruns square-section selection and "
            "then reruns the formal ANSYS calculation. This also applies when the square-support member itself passes "
            "but a weld or connection ratio still controls. The spacing estimate is only an ordering heuristic; the "
            "rerun result remains the only publishable engineering conclusion."
        ),
        "source_ref": "support_spacing_recovery:largest_allowed_square_section_active_and_ratio_overlimit",
        "job_dir": str(job_dir),
        "planned_at": datetime.now(timezone.utc).isoformat(),
    }


def plan_support_spacing_recovery_from_selection(
    job_dir: Path | str,
    selection: dict[str, Any],
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
    attempt_index: int = 1,
) -> dict[str, Any]:
    job_path = Path(job_dir)
    payload = _read_json(job_path / "input.json")
    max_allowed = _max_allowed_candidate(payload, source_root=source_root)
    if max_allowed is None:
        return {"status": "skipped", "reason": "allowed_square_sections_missing_or_invalid", "trigger": "selection_failure"}
    result = _candidate_result_by_section(selection, max_allowed.section_name)
    if not result:
        return {
            "status": "skipped",
            "reason": "maximum_allowed_square_section_was_not_evaluated",
            "trigger": "selection_failure",
            "max_allowed_square_section": max_allowed.section_name,
        }
    if not _result_is_deterministic_overlimit(result):
        return {
            "status": "skipped",
            "reason": "maximum_allowed_square_section_result_is_not_clean_overlimit",
            "trigger": "selection_failure",
            "max_allowed_square_section": max_allowed.section_name,
            "result": result,
        }
    ratio = _as_float(result.get("section_selection_ratio") or result.get("controlling_ratio"))
    return _base_plan(
        job_path,
        payload=payload,
        failed_ratio=ratio,
        max_allowed=max_allowed,
        trigger="square_section_selection_failure",
        attempt_index=attempt_index,
        evidence={
            "selection_status": selection.get("status"),
            "selection_reason": selection.get("reason"),
            "candidate_result": result,
        },
    )


def plan_support_spacing_recovery_from_final_ratio(
    job_dir: Path | str,
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
    attempt_index: int = 1,
) -> dict[str, Any]:
    job_path = Path(job_dir)
    payload = _read_json(job_path / "input.json")
    max_allowed = _max_allowed_candidate(payload, source_root=source_root)
    if max_allowed is None:
        return {"status": "skipped", "reason": "allowed_square_sections_missing_or_invalid", "trigger": "final_ratio_failure"}
    current_section = _current_selected_square_section(payload)
    if current_section != max_allowed.section_name and current_section != max_allowed.section_name.lower():
        return {
            "status": "skipped",
            "reason": "current_square_section_is_not_maximum_allowed",
            "trigger": "final_ratio_failure",
            "current_square_section": current_section,
            "max_allowed_square_section": max_allowed.section_name,
        }
    ratio, failed_non_ratio, ratio_evidence = _failed_ratio_from_validation(job_path)
    if failed_non_ratio:
        return {
            "status": "skipped",
            "reason": "final_result_has_non_ratio_failures",
            "trigger": "final_ratio_failure",
            "failed_non_ratio_checks": failed_non_ratio,
            "max_allowed_square_section": max_allowed.section_name,
        }
    return _base_plan(
        job_path,
        payload=payload,
        failed_ratio=ratio,
        max_allowed=max_allowed,
        trigger="final_result_ratio_failure",
        attempt_index=attempt_index,
        evidence={
            "current_square_section": current_section,
            "result_validation": str(job_path / "result_validation.json"),
            "ratio_evidence": ratio_evidence,
        },
    )


def apply_support_spacing_recovery(
    job_dir: Path | str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    if plan.get("status") != "pass":
        return {"status": "skipped", "reason": "plan_status_is_not_pass", "plan": plan}
    job_path = Path(job_dir)
    input_path = job_path / "input.json"
    payload = _read_json(input_path)
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    previous_spacing = _as_float(support.get("support_spacing_m"))
    new_spacing = float(plan["new_support_spacing_m"])
    reset_keys = {
        "square_section_selection_status",
        "square_section_selected",
        "square_section_selected_ratio",
        "square_section_selection_policy",
        "square_section_selection_source",
        "square_section_selection_validation_mode",
        "square_section_selection_requires_formal_validation",
        "square_section_outer_mm",
        "square_section_thickness_mm",
    }
    previous_selection = {key: metadata.get(key) for key in sorted(reset_keys) if key in metadata}
    for key in reset_keys:
        metadata.pop(key, None)
    support["support_spacing_m"] = new_spacing
    metadata.update(
        {
            "square_section_selection_status": "auto_selection_required",
            "support_spacing_adjustment_status": "auto_reduced_after_max_allowed_square_section_overlimit",
            "support_spacing_original_m": plan.get("original_support_spacing_m") or previous_spacing,
            "support_spacing_previous_m": previous_spacing,
            "support_spacing_current_m": new_spacing,
            "support_spacing_adjustment_attempt": plan.get("attempt_index"),
            "support_spacing_adjustment_source_ref": plan.get("source_ref"),
        }
    )
    payload["support"] = support
    payload["metadata"] = metadata
    _write_json(input_path, payload)

    history_path = job_path / "support_spacing_adjustments.json"
    history: list[dict[str, Any]] = []
    if history_path.exists():
        try:
            loaded = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                history = [item for item in loaded if isinstance(item, dict)]
        except json.JSONDecodeError:
            history = []
    applied = {
        "status": "pass",
        "previous_support_spacing_m": previous_spacing,
        "new_support_spacing_m": new_spacing,
        "previous_square_section_selection": previous_selection,
        "plan": plan,
        "updated_input": str(input_path),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    history.append(applied)
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_json(job_path / "support_spacing_adjustment.json", applied)
    return applied
