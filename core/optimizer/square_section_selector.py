from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.apdl.section_offsets import normalize_yixing_arm_secoffset
from core.apdl.postprocessor_alignment import align_postprocessor_to_intake


# Candidate section trials are an optimization sub-step, not a publishable
# final result.  They must prove deterministic ratios, but they should not keep
# sweeping merely because the trial workspace did not export final report
# figures or because the trial modal order has not yet been tuned for the
# final selected section.  Final figure completeness and MT cutoff are checked
# again after the selected section is run as the formal job.
CANDIDATE_SELECTION_IGNORED_NON_RATIO_CHECKS = {
    "modal_mt_cutoff",
    "required_figures",
}

STATIC_CANDIDATE_SELECTION_IGNORED_NON_RATIO_CHECKS = {
    "modal_frequency_table",
    "required_file_Mode.oup",
}

FORMAL_VALIDATION_RETRYABLE_DOMAINS = {
    "JCZH",
    "LS-FORCE",
    "HF-FORCE",
    "TMAXBEAMSTRESS",
    "MAXBEAMSTRESS",
}

FORMAL_VALIDATION_RETRYABLE_CHECKS = {
    "required_file_Mode.oup",
    "modal_frequency_table",
}

ECONOMIC_RATIO_MIN = 0.60
ECONOMIC_DOWNSHIFT_RATIO_MAX = 0.75
ECONOMIC_RATIO_MAX = 0.9999
MAX_ECONOMIC_SECTION_TRIALS = 2
OVERLIMIT_RECOVERY_SECTION_TRIALS = 2
ECONOMY_DOWNSHIFT_SECTION_TRIALS = 1
SECTION_RATIO_POLICY = (
    "Square-section selection uses the fresh Chapter 6.1 structural member "
    "ratios only: square support, cantilever arm, and mixed beam/support rows. "
    "Weld and bolt ratios remain final-result gates, but they are not allowed "
    "to drive square-tube economy selection. Trial candidates are acceptable only "
    "when fresh 6.1 evaluation_summary ratios prove a section-selection ratio <= 1.0 "
    "and result_validation has no blocking non-ratio failures; "
    "history/cache/report numbers may order candidates but never decide the section. "
    "Production economy search targets 0.60 <= ratio <= 0.9999 and must normally "
    "finish within two fresh ANSYS candidate trials; if those two fresh trials are both "
    "deterministic over-limit, the search may run up to two larger intake-allowed sections "
    "before reporting failure. If a passed larger candidate lands at ratio <= 0.75, "
    "run one immediately lower intake-allowed section once to avoid an overly conservative selection; "
    "if that lower section fails, keep the already passing larger section."
)
SECTION_RATIO_BASIS = (
    "evaluation_summary.json:Chapter 6.1 structural member ratios + "
    "result_validation.json:non-ratio completeness checks"
)


def _section_ratio_audit_fields() -> dict[str, str]:
    return {
        "ratio_policy": SECTION_RATIO_POLICY,
        "ratio_basis": SECTION_RATIO_BASIS,
        "chapter6_ratio_basis": "same_source_as_final_chapter6_evaluation",
        "economic_ratio_range": f"{ECONOMIC_RATIO_MIN:.2f} <= ratio <= {ECONOMIC_RATIO_MAX:.4f}",
        "economic_downshift_ratio_range": f"ratio <= {ECONOMIC_DOWNSHIFT_RATIO_MAX:.2f}",
        "max_economic_section_trials": str(MAX_ECONOMIC_SECTION_TRIALS),
        "overlimit_recovery_section_trials": str(OVERLIMIT_RECOVERY_SECTION_TRIALS),
        "economy_downshift_section_trials": str(ECONOMY_DOWNSHIFT_SECTION_TRIALS),
    }


def _candidate_trial_analysis_method(trial_dir: Path) -> str:
    input_path = trial_dir / "input.json"
    if not input_path.exists():
        return ""
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}
    return str(metadata.get("analysis_method") or payload.get("analysis_method") or "").strip().lower()


def _candidate_ignored_non_ratio_checks(trial_dir: Path) -> set[str]:
    ignored = set(CANDIDATE_SELECTION_IGNORED_NON_RATIO_CHECKS)
    if _candidate_trial_analysis_method(trial_dir) == "static":
        ignored.update(STATIC_CANDIDATE_SELECTION_IGNORED_NON_RATIO_CHECKS)
    return ignored


TRIAL_RUNTIME_OUTPUT_FILE_NAMES = {
    "result.json",
    "result_raw.json",
    "evaluation_summary.json",
    "figures_manifest.json",
    "modal_results.json",
    "beam_stress_results.json",
    "weld_force_results.json",
    "bolt_force_results.json",
    "foundation_loads.json",
    "result_validation.json",
    "report_audit.json",
    "report_traceability.json",
    "ansys_run_audit.json",
    "ansys_command.json",
    "ansys_live_status.json",
    "ansys_preflight.json",
    "figure_export_live_status.json",
    "job_state.json",
    "run_ansys.ps1",
    "square_section_selection.json",
    "square_section_selection_summary.json",
    "square_section_selection_applied.json",
    "square_section_trial_summary.json",
    "analysis_scope.json",
    "result_requirements.json",
    "postprocess_ai_qc.json",
}

TRIAL_RUNTIME_OUTPUT_SUFFIXES = {
    ".lis",
    ".oup",
    ".out",
    ".err",
    ".rst",
    ".db",
    ".emat",
    ".esav",
    ".full",
    ".mntr",
    ".page",
    ".bmp",
    ".png",
    ".log",
}

TRIAL_RUNTIME_OUTPUT_DIR_NAMES = {
    "raw_results",
    "figures",
    "published",
    "report",
    "reports",
    "candidate_trials",
    "evaluation_workbooks",
}

TRIAL_RUNTIME_OUTPUT_PREFIXES = (
    "CableTrayAI_Run",
    "MOTAI-",
    "SQ",
    "TB",
    "TD",
)


def _is_trial_runtime_output_name(name: str) -> bool:
    path = Path(name)
    lower = name.lower()
    if name in TRIAL_RUNTIME_OUTPUT_FILE_NAMES or lower in {item.lower() for item in TRIAL_RUNTIME_OUTPUT_FILE_NAMES}:
        return True
    if path.suffix.lower() in TRIAL_RUNTIME_OUTPUT_SUFFIXES:
        return True
    return any(name.startswith(prefix) for prefix in TRIAL_RUNTIME_OUTPUT_PREFIXES)


def _trial_copy_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        if name in TRIAL_RUNTIME_OUTPUT_DIR_NAMES or name.lower() in {item.lower() for item in TRIAL_RUNTIME_OUTPUT_DIR_NAMES}:
            ignored.add(name)
            continue
        if _is_trial_runtime_output_name(name):
            ignored.add(name)
    return ignored


def _clean_trial_runtime_outputs(trial_dir: Path) -> dict[str, Any]:
    """Remove inherited solver/evaluation outputs before a candidate trial runs.

    Candidate jobs are allowed to reuse input and generated command files, but
    never previous ANSYS results.  If a trial cannot produce fresh LIS/OUP/BMP
    and evaluation files, it must fail instead of appearing economical from
    stale JSON.
    """

    removed_files: list[str] = []
    removed_dirs: list[str] = []
    for child in sorted(trial_dir.iterdir(), key=lambda item: item.name.lower()):
        if child.is_dir() and child.name.lower() in {item.lower() for item in TRIAL_RUNTIME_OUTPUT_DIR_NAMES}:
            shutil.rmtree(child, ignore_errors=True)
            removed_dirs.append(child.name)
        elif child.is_file() and _is_trial_runtime_output_name(child.name):
            child.unlink(missing_ok=True)
            removed_files.append(child.name)
    return {
        "status": "pass",
        "removed_file_count": len(removed_files),
        "removed_dir_count": len(removed_dirs),
        "removed_files": removed_files[:50],
        "removed_dirs": removed_dirs[:50],
        "policy": "candidate trials must generate fresh ANSYS/result/evaluation outputs; inherited runtime artifacts are ignored and deleted",
    }


@dataclass(frozen=True)
class SquareSectionCandidate:
    section_name: str
    outer_mm: float
    thickness_mm: float
    source_file: str
    source_kind: str = "local_sect"

    @property
    def estimated_area_mm2(self) -> float:
        inner = max(0.0, self.outer_mm - 2.0 * self.thickness_mm)
        return self.outer_mm * self.outer_mm - inner * inner

    @property
    def estimated_bending_section_modulus_mm3(self) -> float:
        inner = max(0.0, self.outer_mm - 2.0 * self.thickness_mm)
        if self.outer_mm <= 0:
            return 0.0
        inertia = (self.outer_mm**4 - inner**4) / 12.0
        return inertia / (self.outer_mm / 2.0)


def parse_square_section_name(path_or_name: Path | str) -> SquareSectionCandidate | None:
    path = Path(path_or_name)
    stem = path.stem if path.suffix else str(path_or_name)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)-\1-(\d+(?:\.\d+)?)", stem)
    if not match:
        return None
    return SquareSectionCandidate(
        section_name=stem,
        outer_mm=float(match.group(1)),
        thickness_mm=float(match.group(2)),
        source_file=str(path) if path.suffix else "",
    )


def generated_native_hrec_square_candidates(
    *,
    outer_values_mm: tuple[int, ...] = (200, 220, 240, 260, 280),
    thickness_values_mm: tuple[int, ...] = (8, 10, 12, 14, 16, 18, 20),
) -> list[SquareSectionCandidate]:
    """Generate auditable APDL HREC candidates when the local SECT catalog is too small."""

    candidates: list[SquareSectionCandidate] = []
    for outer in outer_values_mm:
        for thickness in thickness_values_mm:
            if thickness * 2 >= outer:
                continue
            name = f"{outer}-{outer}-{thickness}"
            candidates.append(
                SquareSectionCandidate(
                    section_name=name,
                    outer_mm=float(outer),
                    thickness_mm=float(thickness),
                    source_file="generated:ANSYS_APDL_HREC",
                    source_kind="native_hrec",
                )
            )
    return sorted(
        candidates,
        key=lambda item: (
            item.estimated_bending_section_modulus_mm3,
            item.estimated_area_mm2,
            item.outer_mm,
            item.thickness_mm,
        ),
    )


def discover_square_section_candidates(
    source_root: Path | str = Path("source_materials/model_commands"),
    *,
    include_native_hrec_generated: bool = False,
) -> list[SquareSectionCandidate]:
    source_root = Path(source_root)
    candidates: list[SquareSectionCandidate] = []
    for path in sorted(source_root.rglob("*.SECT"), key=lambda item: item.as_posix().lower()):
        candidate = parse_square_section_name(path)
        if candidate:
            candidates.append(candidate)
    if include_native_hrec_generated:
        candidates.extend(generated_native_hrec_square_candidates())
    unique: dict[str, SquareSectionCandidate] = {}
    for candidate in candidates:
        unique.setdefault(candidate.section_name, candidate)
    return sorted(
        unique.values(),
        key=lambda item: (
            item.estimated_bending_section_modulus_mm3,
            item.estimated_area_mm2,
            item.outer_mm,
            item.thickness_mm,
        ),
    )


def controlling_square_ratio(evaluation_summary: list[dict[str, Any]]) -> float | None:
    ratios = [
        float(item["ratio"])
        for item in evaluation_summary
        if item.get("ratio") is not None and "square_support" in str(item.get("check_id") or item.get("component") or "")
    ]
    return max(ratios) if ratios else None


def controlling_evaluation_ratio(evaluation_summary: list[dict[str, Any]]) -> float | None:
    ratios: list[float] = []
    for item in evaluation_summary:
        if item.get("ratio") is None:
            continue
        try:
            ratios.append(float(item["ratio"]))
        except (TypeError, ValueError):
            continue
    return max(ratios) if ratios else None


SECTION_SELECTION_EXCLUDED_KEYWORDS = (
    "weld",
    "bolt",
    "焊",
    "螺栓",
)


def is_section_selection_evaluation_row(item: dict[str, Any]) -> bool:
    """Return True for Chapter 6.1 rows that should drive square-tube sizing.

    Square tube selection is a member sizing problem.  Root weld and tray-arm
    connection bolt checks can fail independently and must stay in the final
    deterministic gate, but increasing the square tube should not be used to
    chase those ratios.
    """

    check_id = str(item.get("check_id") or "").strip().lower()
    component = str(item.get("component") or "").strip().lower()
    category = str(item.get("category") or "").strip().lower()
    combined = " ".join([check_id, component, category])
    if any(keyword in combined for keyword in SECTION_SELECTION_EXCLUDED_KEYWORDS):
        return False
    if component:
        return (
            component in {"support", "square_support", "cantilever_arm"}
            or component.startswith("mixed_beam")
        )
    if check_id.startswith(("support.", "square_support.", "cantilever_arm.", "mixed_beam")):
        return True
    if ".support_" in check_id:
        return True
    return category.startswith("支架梁") or "托臂应力" in category


def controlling_section_selection_ratio(evaluation_summary: list[dict[str, Any]]) -> float | None:
    ratios: list[float] = []
    for item in evaluation_summary:
        if item.get("ratio") is None or not is_section_selection_evaluation_row(item):
            continue
        try:
            ratios.append(float(item["ratio"]))
        except (TypeError, ValueError):
            continue
    return max(ratios) if ratios else None


def _ratio_limit_from_validation(validation: dict[str, Any]) -> float | None:
    ratios: list[float] = []
    for check in validation.get("checks") or []:
        if check.get("check_id") != "evaluation_ratio_limit":
            continue
        for item in check.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            try:
                ratios.append(float(item.get("ratio")))
            except (TypeError, ValueError):
                continue
    return max(ratios) if ratios else None


def _dominant_ratio_limit_from_validation(validation: dict[str, Any]) -> dict[str, Any] | None:
    dominant: dict[str, Any] | None = None
    for check in validation.get("checks") or []:
        if check.get("check_id") != "evaluation_ratio_limit":
            continue
        for item in check.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            try:
                ratio = float(item.get("ratio"))
            except (TypeError, ValueError):
                continue
            if dominant is None or ratio > float(dominant["ratio"]):
                dominant = {"check_id": item.get("check_id"), "ratio": ratio}
    return dominant


def _dominant_ratio_from_evaluation_summary(evaluation_summary: list[dict[str, Any]]) -> dict[str, Any] | None:
    dominant: dict[str, Any] | None = None
    for item in evaluation_summary:
        try:
            ratio = float(item.get("ratio"))
        except (TypeError, ValueError):
            continue
        if dominant is None or ratio > float(dominant["ratio"]):
            dominant = {"check_id": item.get("check_id"), "ratio": ratio}
    return dominant


def _dominant_section_selection_ratio(evaluation_summary: list[dict[str, Any]]) -> dict[str, Any] | None:
    dominant: dict[str, Any] | None = None
    for item in evaluation_summary:
        if not is_section_selection_evaluation_row(item):
            continue
        try:
            ratio = float(item.get("ratio"))
        except (TypeError, ValueError):
            continue
        if dominant is None or ratio > float(dominant["ratio"]):
            dominant = {
                "check_id": item.get("check_id"),
                "ratio": ratio,
                "component": item.get("component"),
                "category": item.get("category"),
            }
    return dominant


def _first_square_section_from_model(job_dir: Path) -> str | None:
    model = job_dir / "generated_model.mac"
    if not model.exists():
        return None
    text = model.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(
        r"SECREAD\s*,\s*['\"]?([^,'\"\s]+)['\"]?\s*,\s*['\"]?SECT",
        text,
        flags=re.IGNORECASE,
    ):
        name = match.group(1)
        if parse_square_section_name(name):
            return name
    return None


def _current_square_section_hint(base_job_dir: Path, preferred_section: str | None = None) -> str | None:
    if preferred_section and parse_square_section_name(str(preferred_section)):
        return str(preferred_section)
    input_path = base_job_dir / "input.json"
    if input_path.exists():
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        metadata = payload.get("metadata") or {}
        for key in ("square_section_current_model_spec", "square_section_spec", "square_section_selected"):
            value = metadata.get(key)
            if value and parse_square_section_name(str(value)):
                return str(value)
    return _first_square_section_from_model(base_job_dir)


def prioritize_square_section_candidates(
    base_job_dir: Path | str,
    candidates: list[SquareSectionCandidate],
    *,
    lower_neighbor_count: int = 0,
    preferred_section: str | None = None,
    preferred_section_source: str | None = None,
) -> tuple[list[SquareSectionCandidate], dict[str, Any]]:
    """Start near the reviewed engineering anchor instead of sweeping the catalog.

    For new intake rows with blank column I, the template still contains a
    standard square tube. Running every smaller historical section first is
    slow and adds no engineering value. Run upward from the selected anchor by
    default; an explicit lower-side guard can still be requested by tests or
    manual engineering review.
    """

    base_job_dir = Path(base_job_dir)
    if not candidates:
        return [], {"status": "empty"}
    hint = _current_square_section_hint(base_job_dir, preferred_section=preferred_section)
    if not hint:
        return candidates, {"status": "no_current_section_hint", "candidate_count": len(candidates)}
    anchor_index = next((idx for idx, item in enumerate(candidates) if item.section_name == hint), None)
    if anchor_index is None:
        return candidates, {
            "status": "hint_not_in_candidate_catalog",
            "current_section_hint": hint,
            "candidate_count": len(candidates),
        }
    start_index = max(0, anchor_index - max(0, int(lower_neighbor_count)))
    # Do not wrap around to much smaller sections after the upward search.
    # The one lower-side economy guard is enough to prove that the selected
    # section is not obviously oversized; returning to the smallest sections
    # after a feasible larger candidate only burns ANSYS time and can select an
    # unrelated historical minimum by tie-break.
    ordered = candidates[start_index:]
    if preferred_section_source in {"engineering_estimate", "engineering_estimate_allowed_list"}:
        audit_status = "anchored_to_engineering_estimate"
    elif preferred_section:
        audit_status = "anchored_to_similar_intake_section"
    else:
        audit_status = "anchored_to_current_template_section"
    policy = (
        "A deterministic engineering estimate is used only to order candidate sections from the first plausible "
        "section upward; it never reuses a result or proves acceptability. The selected section must still pass "
        "a fresh ANSYS run and deterministic ratio gate for this job."
        if preferred_section_source in {"engineering_estimate", "engineering_estimate_allowed_list"}
        else (
        "A similar-intake cache hit is used only to order candidate sections; it never reuses a calculation result. "
        "The selected section must still pass a fresh ANSYS trial and deterministic ratio gate for this job."
        if preferred_section
        else (
            "Use the existing standard template square tube as the search anchor and move upward. This avoids "
            "wasting ANSYS runs on obviously unrelated small sections; lower-side economy checks must be requested "
            "explicitly."
        )
        )
    )
    return ordered, {
        "status": audit_status,
        "current_section_hint": hint,
        "preferred_section": preferred_section,
        "anchor_index": anchor_index,
        "start_index": start_index,
        "lower_neighbor_count": lower_neighbor_count,
        "candidate_count": len(candidates),
        "first_candidate": ordered[0].section_name if ordered else None,
        "policy": policy,
    }


def candidate_publishable_ratio(
    trial_dir: Path,
    evaluation_summary: list[dict[str, Any]],
    *,
    require_result_validation: bool = True,
) -> dict[str, Any]:
    """Return the ratio used to accept a candidate square section.

    The candidate ratio is the Chapter 6.1 structural-member ratio for this
    trial.  Weld and bolt checks remain in the final deterministic
    result-validation gate, but they do not size the square tube.
    """

    summary_ratio = controlling_section_selection_ratio(evaluation_summary)
    final_chapter6_ratio = controlling_evaluation_ratio(evaluation_summary)
    square_ratio = controlling_square_ratio(evaluation_summary)
    validation_path = trial_dir / "result_validation.json"
    if not validation_path.exists():
        if require_result_validation:
            return {
                **_section_ratio_audit_fields(),
                "status": "missing_validation",
                "controlling_ratio": summary_ratio,
                "final_chapter6_controlling_ratio": final_chapter6_ratio,
                "square_support_ratio": square_ratio,
                "validation_status": "missing",
                "failed_non_ratio_checks": ["result_validation_missing"],
                "source_ref": "result_validation.json required for production square-section selection",
            }
        return {
            **_section_ratio_audit_fields(),
            "status": "pass" if summary_ratio is not None else "missing_ratio",
            "controlling_ratio": summary_ratio,
            "final_chapter6_controlling_ratio": final_chapter6_ratio,
            "square_support_ratio": square_ratio,
            "validation_status": "missing",
            "source_ref": "evaluation_summary.json:Chapter 6.1 structural member ratios",
        }
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            **_section_ratio_audit_fields(),
            "status": "fail",
            "controlling_ratio": summary_ratio,
            "final_chapter6_controlling_ratio": final_chapter6_ratio,
            "square_support_ratio": square_ratio,
            "validation_status": "invalid",
            "reason": str(exc),
            "source_ref": "result_validation.json",
        }
    dominant_over_limit = _dominant_ratio_limit_from_validation(validation)
    validation_over_limit_ratio = float(dominant_over_limit["ratio"]) if dominant_over_limit else None
    dominant_summary_ratio = _dominant_section_selection_ratio(evaluation_summary)
    summary_ratio = float(dominant_summary_ratio["ratio"]) if dominant_summary_ratio else summary_ratio
    raw_failed_non_ratio = [
        check.get("check_id")
        for check in validation.get("checks") or []
        if check.get("status") == "fail" and check.get("check_id") != "evaluation_ratio_limit"
    ]
    ignored_check_ids = _candidate_ignored_non_ratio_checks(trial_dir)
    failed_non_ratio = [
        check_id
        for check_id in raw_failed_non_ratio
        if str(check_id) not in ignored_check_ids
    ]
    ignored_non_ratio = [
        check_id
        for check_id in raw_failed_non_ratio
        if str(check_id) in ignored_check_ids
    ]
    # Candidate selection must be decided from the freshly generated Chapter 6
    # ratios for this trial.  result_validation.json remains the completeness
    # gate for missing/blank LIS/OUP/figures, but its evaluation_ratio_limit
    # evidence is deliberately not used as the controlling ratio because stale
    # validation evidence can otherwise make a fresh 0.99 trial look failed.
    ratio = summary_ratio
    if failed_non_ratio:
        return {
            **_section_ratio_audit_fields(),
            "status": "fail",
            "controlling_ratio": ratio,
            "final_chapter6_controlling_ratio": final_chapter6_ratio,
            "square_support_ratio": square_ratio,
            "validation_status": validation.get("status"),
            "dominant_check_id": dominant_summary_ratio.get("check_id") if dominant_summary_ratio else None,
            "dominant_component": dominant_summary_ratio.get("component") if dominant_summary_ratio else None,
            "failed_non_ratio_checks": failed_non_ratio,
            "ignored_non_ratio_checks": ignored_non_ratio,
            "validation_ratio_limit_ratio": validation_over_limit_ratio,
            "source_ref": "result_validation.json",
        }
    gate_status = "missing_ratio"
    if ratio is not None:
        gate_status = "fail" if ratio > 1.0 else "pass"
    return {
        **_section_ratio_audit_fields(),
        "status": gate_status,
        "controlling_ratio": ratio,
        "final_chapter6_controlling_ratio": final_chapter6_ratio,
        "square_support_ratio": square_ratio,
        "validation_status": validation.get("status"),
        "dominant_check_id": dominant_summary_ratio.get("check_id") if dominant_summary_ratio else None,
        "dominant_component": dominant_summary_ratio.get("component") if dominant_summary_ratio else None,
        "ignored_non_ratio_checks": ignored_non_ratio,
        "validation_ratio_limit_ratio": validation_over_limit_ratio,
        "validation_ratio_limit_status": "ignored_for_candidate_ratio_recomputed_from_evaluation_summary",
        "source_ref": "evaluation_summary.json:Chapter 6.1 structural member ratios + result_validation.json non-ratio checks",
    }


def _smart_jump_after_square_ratio_failure(
    candidate_list: list[SquareSectionCandidate],
    current_index: int,
    result: dict[str, Any],
    *,
    target_ratio: float = 0.98,
) -> dict[str, Any] | None:
    raw_ratio = result.get("section_selection_ratio") or result.get("controlling_ratio") or result.get("square_support_ratio")
    try:
        section_ratio = float(raw_ratio)
    except (TypeError, ValueError):
        return None
    if section_ratio <= 1.0:
        return None
    dominant = str(result.get("dominant_check_id") or "")
    if dominant and not is_section_selection_evaluation_row({"check_id": dominant, "component": result.get("dominant_component")}):
        return None
    current = candidate_list[current_index]
    current_modulus = current.estimated_bending_section_modulus_mm3
    if current_modulus <= 0:
        return None
    required_modulus = current_modulus * section_ratio / max(target_ratio, 1e-6)
    target_index = None
    for idx in range(current_index + 1, len(candidate_list)):
        if candidate_list[idx].estimated_bending_section_modulus_mm3 >= required_modulus:
            target_index = idx
            break
    if target_index is None:
        return None
    # Use the inverse section-modulus trend as an ordering hint, not as the
    # conclusion.  Run one candidate just below the estimated target when it
    # exists, then let the deterministic ANSYS trial prove the ratio.  This
    # avoids slow one-by-one enlargement while still keeping an audit trail.
    next_index = max(current_index + 1, target_index - 1)
    if next_index <= current_index + 1:
        return None
    skipped = candidate_list[current_index + 1 : next_index]
    return {
        "next_index": next_index,
        "after_section": current.section_name,
        "next_section": candidate_list[next_index].section_name,
        "skipped_sections": [item.section_name for item in skipped],
        "skipped_count": len(skipped),
        "section_selection_ratio": section_ratio,
        "square_support_ratio": result.get("square_support_ratio"),
        "current_modulus_mm3": current_modulus,
        "estimated_required_modulus_mm3": required_modulus,
        "target_ratio": target_ratio,
        "source_ref": "Chapter 6.1 section-selection ratio * section_modulus inverse trend; final acceptance still requires ANSYS trial ratio <= 1.0",
    }


def _economic_ratio_status(ratio: float | None) -> str:
    if ratio is None:
        return "missing"
    if ratio > 1.0:
        return "over_limit"
    if ratio < ECONOMIC_RATIO_MIN:
        return "below_economic_range"
    if ratio <= ECONOMIC_RATIO_MAX:
        return "economic"
    return "limit_pass"


def _candidate_index_by_name(candidates: list[SquareSectionCandidate], section_name: str) -> int | None:
    for index, candidate in enumerate(candidates):
        if candidate.section_name == section_name:
            return index
    return None


def _candidate_at_or_above_modulus(
    candidates: list[SquareSectionCandidate],
    required_modulus: float,
) -> SquareSectionCandidate | None:
    for candidate in candidates:
        if candidate.estimated_bending_section_modulus_mm3 >= required_modulus:
            return candidate
    return candidates[-1] if candidates else None


def _candidate_at_or_below_modulus(
    candidates: list[SquareSectionCandidate],
    required_modulus: float,
) -> SquareSectionCandidate | None:
    lower = [
        candidate
        for candidate in candidates
        if candidate.estimated_bending_section_modulus_mm3 <= required_modulus
    ]
    return lower[-1] if lower else (candidates[0] if candidates else None)


def _economic_correction_candidate(
    catalog_candidates: list[SquareSectionCandidate],
    current: SquareSectionCandidate,
    result: dict[str, Any],
    evaluated_names: set[str],
    *,
    target_ratio: float = 0.82,
) -> dict[str, Any] | None:
    """Pick the one allowed correction candidate for a two-trial economy search."""

    try:
        ratio = float(result.get("controlling_ratio"))
    except (TypeError, ValueError):
        return None
    if not catalog_candidates or current.estimated_bending_section_modulus_mm3 <= 0:
        return None
    status = _economic_ratio_status(ratio)
    if status == "economic":
        return None
    current_modulus = current.estimated_bending_section_modulus_mm3
    if status in {"over_limit", "limit_pass"}:
        required_modulus = current_modulus * max(ratio, ECONOMIC_RATIO_MAX) / max(target_ratio, 1e-6)
        candidate = _candidate_at_or_above_modulus(catalog_candidates, required_modulus)
        direction = "larger"
    elif status == "below_economic_range":
        required_modulus = current_modulus * ratio / max(target_ratio, 1e-6)
        candidate = _candidate_at_or_below_modulus(catalog_candidates, required_modulus)
        direction = "smaller"
    else:
        return None
    if candidate is None or candidate.section_name == current.section_name or candidate.section_name in evaluated_names:
        return None
    return {
        "status": "planned",
        "direction": direction,
        "after_section": current.section_name,
        "next_section": candidate.section_name,
        "current_ratio": ratio,
        "economic_ratio_min": ECONOMIC_RATIO_MIN,
        "economic_ratio_max": ECONOMIC_RATIO_MAX,
        "target_ratio": target_ratio,
        "current_modulus_mm3": current_modulus,
        "estimated_required_modulus_mm3": required_modulus,
        "source_ref": "two-trial economy correction from fresh ANSYS ratio and square-tube section modulus",
    }


def _economic_downshift_candidate(
    catalog_candidates: list[SquareSectionCandidate],
    current: SquareSectionCandidate,
    result: dict[str, Any],
    evaluated_names: set[str],
) -> dict[str, Any] | None:
    """Run one immediately lower allowed section when a passing section is still conservative."""

    try:
        ratio = float(result.get("controlling_ratio"))
    except (TypeError, ValueError):
        return None
    if ratio <= 0.0 or ratio > ECONOMIC_DOWNSHIFT_RATIO_MAX:
        return None
    current_index = _candidate_index_by_name(catalog_candidates, current.section_name)
    if current_index is None or current_index <= 0:
        return None
    candidate = catalog_candidates[current_index - 1]
    if candidate.section_name == current.section_name or candidate.section_name in evaluated_names:
        return None
    return {
        "status": "planned",
        "direction": "smaller",
        "after_section": current.section_name,
        "next_section": candidate.section_name,
        "current_ratio": ratio,
        "economic_downshift_ratio_min": ECONOMIC_RATIO_MIN,
        "economic_downshift_ratio_max": ECONOMIC_DOWNSHIFT_RATIO_MAX,
        "current_modulus_mm3": current.estimated_bending_section_modulus_mm3,
        "next_modulus_mm3": candidate.estimated_bending_section_modulus_mm3,
        "source_ref": (
            "passed candidate ratio is at or below the conservative 0.75 threshold; "
            "run exactly one immediately lower intake-allowed section before final selection"
        ),
    }


def _stable_non_square_blocker(results: list[dict[str, Any]]) -> dict[str, Any] | None:
    useful = [
        item
        for item in results
        if item.get("run_status") in {"success", "pass"}
        and item.get("controlling_ratio") is not None
        and item.get("square_support_ratio") is not None
    ]
    if len(useful) < 5:
        return None
    recent = useful[-5:]
    if not all(float(item.get("square_support_ratio") or 9.0) <= 1.0 for item in recent[-3:]):
        return None
    dominant_ids = [str(item.get("dominant_check_id") or "") for item in recent[-3:]]
    if not dominant_ids or any(not item or "square_support" in item for item in dominant_ids):
        return None
    dominant_prefixes = [item.split(".", 1)[0] for item in dominant_ids]
    if len(set(dominant_prefixes)) != 1:
        return None
    ratios = [float(item["controlling_ratio"]) for item in recent[-3:]]
    if not all(ratio > 1.0 for ratio in ratios):
        return None
    span = max(ratios) - min(ratios)
    baseline = max(abs(sum(ratios) / len(ratios)), 1e-9)
    if span / baseline > 0.02:
        return None
    return {
        "status": "stopped",
        "reason": "Non-square weld/bolt controlling ratio stayed above 1.0 after multiple larger square-section candidates; larger square tube is not correcting the governing check.",
        "dominant_check_id": dominant_ids[-1],
        "recent_ratios": ratios,
        "policy": "Stop square-section sweeping when the governing failed check is stable and not a square-support item. The row remains blocked for connection/weld design or extraction-source review; no pass is forced.",
    }


CHECK_DOMAIN_PREFIXES: tuple[tuple[str, str], ...] = (
    ("modal_mt", "modal_mt"),
    ("response_zero_period", "spectrum"),
    ("spectrum", "spectrum"),
    ("required_file_JCZH", "JCZH"),
    ("foundation_", "JCZH"),
    ("required_file_LS-FORCE", "LS-FORCE"),
    ("connection_", "LS-FORCE"),
    ("required_file_HF-FORCE", "HF-FORCE"),
    ("cantilever_root_weld", "HF-FORCE"),
    ("required_file_TMAXBEAMSTRESS", "TMAXBEAMSTRESS"),
    ("cantilever_stress", "TMAXBEAMSTRESS"),
    ("required_file_MAXBEAMSTRESS", "MAXBEAMSTRESS"),
    ("beam_stress", "MAXBEAMSTRESS"),
    ("required_figures", "figures"),
    ("evaluation_zero_allowable", "evaluation"),
)


def _domain_for_failed_check(check_id: str) -> str:
    for prefix, domain in CHECK_DOMAIN_PREFIXES:
        if check_id.startswith(prefix):
            return domain
    return "result_validation"


def _failed_checks_from_result_validation(trial_dir: Path) -> list[str]:
    path = trial_dir / "result_validation.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ["result_validation_json_invalid"]
    failed: list[str] = []
    for check in payload.get("checks") or []:
        if not isinstance(check, dict) or check.get("status") != "fail":
            continue
        check_id = str(check.get("check_id") or "")
        if not check_id:
            continue
        if check_id == "evaluation_ratio_limit":
            # Ratio evidence is a deterministic evaluation outcome, not a
            # source-collection failure.  Ordinary weld/bolt over-ratio rows
            # must not be misclassified as JCZH/LS/HF/MAX/TMAX extraction
            # defects, otherwise section search stops before proving whether a
            # nearby candidate can satisfy the full ratio gate.
            continue
        failed.append(check_id)
    return list(dict.fromkeys(failed))


def _candidate_trial_diagnosis(
    trial_dir: Path,
    *,
    run_result: dict[str, Any],
    gate_status: str,
    failed_non_ratio_checks: list[str],
    ratio: float | None,
    square_ratio: float | None,
) -> dict[str, Any]:
    """Classify whether a failed trial should keep enlarging the square tube.

    Section search is only valid when the governing failure is a square-support
    ratio.  Missing/zero JCZH, LS-FORCE, HF-FORCE, MAX/TMAX rows, MT cutoff and
    figure-set problems are post-processing/model-output issues; increasing the
    square tube cannot make those sources trustworthy.
    """

    run_status = str(run_result.get("status") or "")
    raw_failed_checks = list(dict.fromkeys([*failed_non_ratio_checks, *_failed_checks_from_result_validation(trial_dir)]))
    ignored_check_ids = _candidate_ignored_non_ratio_checks(trial_dir)
    ignored_failed_checks = [
        check for check in raw_failed_checks if check in ignored_check_ids
    ]
    failed_checks = [
        check for check in raw_failed_checks if check not in ignored_check_ids
    ]
    domains = sorted({_domain_for_failed_check(check) for check in failed_checks})
    if gate_status == "missing_summary":
        domains.append("evaluation_summary")
    if gate_status == "missing_validation":
        domains.append("result_validation")
    if run_status in {"timeout", "startup_no_output_timeout", "output_stall_timeout"}:
        domains.append("ansys_timeout")
    if run_status and run_status not in {"success", "pass"} and not domains:
        domains.append("ansys_run")
    domains = sorted(set(domains))

    square_ratio_failure = square_ratio is not None and square_ratio > 1.0
    deterministic_ratio_failure = ratio is not None and ratio > 1.0
    retryable_failed_checks = [
        check
        for check in failed_checks
        if check in FORMAL_VALIDATION_RETRYABLE_CHECKS
        or _domain_for_failed_check(check) in FORMAL_VALIDATION_RETRYABLE_DOMAINS
    ]
    formal_validation_retryable = (
        run_status in {"success", "pass"}
        and ratio is not None
        and ratio <= 1.0
        and bool(failed_checks)
        and len(retryable_failed_checks) == len(failed_checks)
    )
    blocking_domains = {
        "modal_mt",
        "spectrum",
        "JCZH",
        "LS-FORCE",
        "HF-FORCE",
        "TMAXBEAMSTRESS",
        "MAXBEAMSTRESS",
        "figures",
        "evaluation",
        "evaluation_summary",
        "ansys_timeout",
        "ansys_run",
        "result_validation",
    }
    non_section_issue = bool(blocking_domains.intersection(domains)) and not square_ratio_failure
    continue_search = not non_section_issue
    if formal_validation_retryable:
        recommendation = (
            "Stop square-section sweeping and run this section once as the formal full ANSYS/PIP calculation. "
            "The candidate ratio is <= 1.0, but the trial workspace missed required source outputs; publication still "
            "depends on the formal result_validation.json passing."
        )
    elif non_section_issue:
        recommendation = (
            "Stop square-section enlargement and fix the source collection/post-processing issue first. "
            "Candidate section search is not allowed to hide missing, UNKNOWN or all-zero JCZH/LS/HF/MAX/TMAX/figure outputs."
        )
    elif square_ratio_failure:
        recommendation = "Continue with larger square-section candidates; the governing failure is still a square-support ratio."
    elif deterministic_ratio_failure:
        recommendation = "Continue only if the governing ratio is section-sensitive; otherwise review weld/bolt/source mapping."
    else:
        recommendation = "No blocking extraction issue was detected for this candidate."
    return {
        "status": "continue" if continue_search else "stop_and_fix_source",
        "continue_square_section_search": continue_search,
        "run_status": run_status,
        "domains": domains,
        "failed_checks": failed_checks,
        "ignored_trial_only_checks": ignored_failed_checks,
        "formal_validation_retryable": formal_validation_retryable,
        "formal_validation_retryable_failed_checks": retryable_failed_checks,
        "square_ratio_failure": square_ratio_failure,
        "deterministic_ratio_failure": deterministic_ratio_failure,
        "recommendation": recommendation,
    }


def _formal_validation_candidates(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for item in results:
        diagnosis = item.get("diagnosis") if isinstance(item.get("diagnosis"), dict) else {}
        if not diagnosis.get("formal_validation_retryable"):
            continue
        try:
            ratio = float(item.get("controlling_ratio"))
        except (TypeError, ValueError):
            continue
        if ratio <= 1.0:
            candidates.append(item)
    return candidates


def select_best_square_section(results: list[dict[str, Any]]) -> dict[str, Any]:
    feasible = [
        item
        for item in results
        if item.get("status") == "pass"
        and item.get("controlling_ratio") is not None
        and float(item["controlling_ratio"]) <= 1.0
    ]
    if not feasible:
        formal_validation = _formal_validation_candidates(results)
        if formal_validation:
            economic = [
                item
                for item in formal_validation
                if ECONOMIC_RATIO_MIN <= float(item["controlling_ratio"]) <= ECONOMIC_RATIO_MAX
            ]
            pool = economic or formal_validation
            selected = sorted(
                pool,
                key=lambda item: (
                    0 if ECONOMIC_RATIO_MIN <= float(item["controlling_ratio"]) <= ECONOMIC_RATIO_MAX else 1,
                    abs(ECONOMIC_RATIO_MAX - float(item["controlling_ratio"])),
                    float(item.get("estimated_bending_section_modulus_mm3") or 0.0),
                    float(item.get("estimated_area_mm2") or 0.0),
                ),
            )[0]
            selected_payload = {
                **selected,
                "formal_validation_required": True,
                "selection_basis_status": "candidate_ratio_passed_but_trial_source_outputs_incomplete",
                "trial_non_ratio_failed_checks": selected.get("failed_non_ratio_checks") or [],
                "trial_diagnosis": selected.get("diagnosis"),
            }
            return {
                **_section_ratio_audit_fields(),
                "status": "pass",
                "selected": selected_payload,
                "selection_validation_mode": "formal_full_run_required",
                "reason": (
                    "Candidate ratio is <= 1.0 but the candidate trial missed required ANSYS/PIP source outputs. "
                    "The section is applied only to run the formal full calculation; final publication still requires "
                    "result_validation.json to pass."
                ),
                "policy": (
                    "Do not keep enlarging the square tube for candidate-only source-output defects. "
                    "Use the feasible candidate as a formal full-run validation candidate, then accept or block solely "
                    "from the formal result_validation gate."
                ),
                "selected_ratio_source": selected.get("source_ref"),
                "economic_ratio_min": ECONOMIC_RATIO_MIN,
                "economic_ratio_max": ECONOMIC_RATIO_MAX,
                "selected_economic_status": _economic_ratio_status(float(selected["controlling_ratio"])),
                "candidate_results": results,
            }
        return {
            **_section_ratio_audit_fields(),
            "status": "fail",
            "selected": None,
            "reason": (
                "没有候选方钢截面取得完整确定性评定比值 <= 1.0。若提资计算说明限定了候选截面，"
                "则不能扩大到未列截面，也不能用历史报告数值硬凑。"
            ),
            "candidate_results": results,
        }
    economic = [
        item
        for item in feasible
        if ECONOMIC_RATIO_MIN <= float(item["controlling_ratio"]) <= ECONOMIC_RATIO_MAX
    ]
    if economic:
        selected = sorted(
            economic,
            key=lambda item: (
                abs(ECONOMIC_RATIO_MAX - float(item["controlling_ratio"])),
                float(item.get("estimated_bending_section_modulus_mm3") or 0.0),
                float(item.get("estimated_area_mm2") or 0.0),
            ),
        )[0]
        policy = (
            "Select the candidate inside the production economy band "
            f"{ECONOMIC_RATIO_MIN:.2f} <= ratio <= {ECONOMIC_RATIO_MAX:.4f}, closest to the upper economic limit. "
            "Area is only a tie-breaker."
        )
    elif max(float(item["controlling_ratio"]) for item in feasible) < ECONOMIC_RATIO_MIN:
        selected = sorted(
            feasible,
            key=lambda item: (
                float(item.get("estimated_bending_section_modulus_mm3") or 0.0),
                float(item.get("estimated_area_mm2") or 0.0),
                str(item.get("section_name") or ""),
            ),
        )[0]
        policy = (
            f"All feasible reviewed/intake-allowed sections tried within the two-trial economy search have ratio < {ECONOMIC_RATIO_MIN:.2f}. "
            "This is treated as a light-duty row or lower-bound candidate limit, so select the minimum feasible section rather than "
            "running more oversized sections."
        )
    else:
        selected = sorted(
            feasible,
            key=lambda item: (
                abs(1.0 - float(item["controlling_ratio"])),
                float(item.get("estimated_bending_section_modulus_mm3") or 0.0),
                float(item.get("estimated_area_mm2") or 0.0),
            ),
        )[0]
        policy = (
            "No candidate landed inside the preferred economy band within the bounded search. "
            "Select the acceptable candidate closest to the upper limit without running extra sections."
        )
    return {
        **_section_ratio_audit_fields(),
        "status": "pass",
        "selected": selected,
        "candidate_results": results,
        "policy": policy,
        "selected_ratio_source": selected.get("source_ref"),
        "economic_ratio_min": ECONOMIC_RATIO_MIN,
        "economic_ratio_max": ECONOMIC_RATIO_MAX,
        "selected_economic_status": _economic_ratio_status(float(selected["controlling_ratio"])),
    }


def _replace_first_square_section_with_native_hrec(job_dir: Path, candidate: SquareSectionCandidate) -> dict[str, Any]:
    model = job_dir / "generated_model.mac"
    text = model.read_text(encoding="utf-8", errors="replace")
    outer_m = candidate.outer_mm / 1000.0
    thickness_m = candidate.thickness_mm / 1000.0
    replacement = (
        f"SECTYPE,1,BEAM,HREC,{candidate.section_name}   ! generated square tube: APDL HREC\n"
        "SECOFFSET,cent,\n"
        f"SECDATA,{outer_m:.6f},{outer_m:.6f},{thickness_m:.6f},{thickness_m:.6f},{thickness_m:.6f},{thickness_m:.6f}   "
        "! W1,W2,t1,t2,t3,t4 from ANSYS SECDATA HREC"
    )
    pattern = (
        r"SECTYPE\s*,\s*1\s*,\s*BEAM\s*,\s*MESH[^\r\n]*\r?\n"
        r"\s*SECOFFSET\s*,[^\r\n]*\r?\n"
        r"\s*SECREAD\s*,\s*['\"]?[^,'\"\s]+['\"]?\s*,\s*['\"]?SECT['\"]?\s*,\s*,\s*MESH[^\r\n]*"
    )
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.IGNORECASE)
    if count != 1:
        raise ValueError("Could not replace the first square section block in generated_model.mac with native HREC.")
    model.write_text(new_text, encoding="utf-8", newline="\n")
    audit = {
        "status": "pass",
        "section_name": candidate.section_name,
        "source_kind": "native_hrec",
        "source_ref": "ANSYS Mechanical APDL Command Reference: SECTYPE BEAM HREC + SECDATA W1,W2,t1,t2,t3,t4",
        "outer_mm": candidate.outer_mm,
        "thickness_mm": candidate.thickness_mm,
        "estimated_area_mm2": candidate.estimated_area_mm2,
        "estimated_bending_section_modulus_mm3": candidate.estimated_bending_section_modulus_mm3,
    }
    (job_dir / "generated_square_section_apdl.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def replace_square_section_in_model(job_dir: Path | str, section_name: str, source_root: Path | str = Path("source_materials/model_commands")) -> dict[str, Any]:
    job_dir = Path(job_dir)
    parsed = parse_square_section_name(section_name)
    source = next(Path(source_root).rglob(f"{section_name}.SECT"), None)
    if source is None and parsed is not None:
        candidate = SquareSectionCandidate(
            section_name=parsed.section_name,
            outer_mm=parsed.outer_mm,
            thickness_mm=parsed.thickness_mm,
            source_file="generated:ANSYS_APDL_HREC",
            source_kind="native_hrec",
        )
        return _replace_first_square_section_with_native_hrec(job_dir, candidate)

    model = job_dir / "generated_model.mac"
    text = model.read_text(encoding="utf-8", errors="replace")
    new_text, count = re.subn(
        r"(SECREAD\s*,\s*['\"]?)([^,'\"\s]+)(['\"]?\s*,\s*['\"]?SECT)",
        rf"\g<1>{section_name}\g<3>",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    if count != 1:
        raise ValueError("Could not replace the first square section SECREAD in generated_model.mac")
    model.write_text(new_text, encoding="utf-8", newline="\n")
    if source is None:
        raise FileNotFoundError(f"Missing SECT file for square section: {section_name}.SECT")
    for target in (job_dir / f"{section_name}.SECT", job_dir / "sections" / f"{section_name}.SECT"):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return {
        "status": "pass",
        "section_name": section_name,
        "source_kind": "local_sect",
        "source_file": str(source),
        "estimated_bending_section_modulus_mm3": parsed.estimated_bending_section_modulus_mm3 if parsed else None,
    }


def _replace_nth_secread(text: str, index: int, section_name: str) -> tuple[str, int]:
    pattern = r"(SECREAD\s*,\s*['\"]?)([^,'\"\s]+)(['\"]?\s*,\s*['\"]?SECT)"
    seen = -1
    replaced = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal seen, replaced
        seen += 1
        if seen == index:
            replaced += 1
            return f"{match.group(1)}{section_name}{match.group(3)}"
        return match.group(0)

    return re.sub(pattern, repl, text, count=0, flags=re.IGNORECASE), replaced


def _is_tray_secread_section(section_name: str) -> bool:
    return bool(re.search(r"\d+-75-2mm", str(section_name or ""), flags=re.IGNORECASE))


def _secread_sections_from_text(text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"SECREAD\s*,\s*['\"]?([^,'\"\s]+)", text, flags=re.IGNORECASE)
    ]


def _section_stem(value: Any, default: str = "") -> str:
    text = str(value or default).strip()
    return Path(text).stem if text else default


def _required_tray_sections_from_job(job_dir: Path) -> list[str]:
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return []
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except Exception:
        return []
    sections_by_id = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    required: list[str] = []
    for layer in payload.get("tray_layers") or []:
        section_id = str(layer.get("tray_section_id") or "")
        section = sections_by_id.get(section_id) if section_id else None
        section_name = _section_stem((section or {}).get("sect_file"), "")
        if not section_name:
            try:
                width = int(round(float(layer.get("tray_width_m") or 0.0) * 1000))
            except (TypeError, ValueError):
                width = 0
            if width > 0:
                section_name = f"{width}-75-2mm"
        if section_name and _is_tray_secread_section(section_name) and section_name not in required:
            required.append(section_name)
    return required


def _assert_required_tray_sections_preserved(job_dir: Path) -> dict[str, Any]:
    required = _required_tray_sections_from_job(job_dir)
    if not required:
        return {"status": "skipped", "required_tray_sections": []}
    model_path = job_dir / "generated_model.mac"
    text = model_path.read_text(encoding="utf-8", errors="replace")
    present = {Path(section).stem.lower() for section in _secread_sections_from_text(text)}
    missing = [section for section in required if Path(section).stem.lower() not in present]
    if missing:
        raise ValueError(
            "generated_model.mac lost required tray sections from input.json: "
            + ", ".join(missing)
        )
    return {"status": "pass", "required_tray_sections": required}


def _replace_last_two_secreads(text: str, primary_arm_section: str, secondary_arm_section: str) -> tuple[str, int, int]:
    pattern = re.compile(r"(SECREAD\s*,\s*['\"]?)([^,'\"\s]+)(['\"]?\s*,\s*['\"]?SECT)", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    if len(matches) < 2:
        return text, 0, 0

    replacements: list[tuple[re.Match[str], str, str]] = []
    known_primary = {"50-42", "YIXINGGANG150"}
    known_secondary = {"CAOGANG42DAN", "YIXINGGANG150DAN"}
    for match in matches:
        section_name = match.group(2).strip()
        upper = section_name.upper()
        if upper in known_primary:
            replacements.append((match, primary_arm_section, "primary"))
        elif upper in known_secondary:
            replacements.append((match, secondary_arm_section, "secondary"))

    if not replacements:
        arm_like_matches = [match for match in matches[1:] if not _is_tray_secread_section(match.group(2))]
        if len(arm_like_matches) < 2:
            return text, 0, 0
        replacements = [
            (arm_like_matches[-2], primary_arm_section, "primary"),
            (arm_like_matches[-1], secondary_arm_section, "secondary"),
        ]

    new_text = text
    primary_count = 0
    secondary_count = 0
    for match, section_name, role in sorted(replacements, key=lambda item: item[0].start(), reverse=True):
        replacement = f"{match.group(1)}{section_name}{match.group(3)}"
        new_text = new_text[: match.start()] + replacement + new_text[match.end() :]
        if role == "primary":
            primary_count += 1
        else:
            secondary_count += 1
    return new_text, primary_count, secondary_count


def replace_arm_sections_in_model(
    job_dir: Path | str,
    primary_arm_section: str,
    secondary_arm_section: str,
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
) -> dict[str, Any]:
    """Keep generated_model.mac arm SECREADs aligned with the selected square tube branch."""

    job_dir = Path(job_dir)
    model = job_dir / "generated_model.mac"
    text = model.read_text(encoding="utf-8", errors="replace")
    new_text, primary_count, secondary_count = _replace_last_two_secreads(text, primary_arm_section, secondary_arm_section)
    new_text, yixing_secoffset_count = normalize_yixing_arm_secoffset(new_text)
    if primary_count + secondary_count < 1:
        raise ValueError("Could not replace arm section SECREADs in generated_model.mac")
    model.write_text(new_text, encoding="utf-8", newline="\n")
    copied: list[str] = []
    for section_name in (primary_arm_section, secondary_arm_section):
        source = next(Path(source_root).rglob(f"{section_name}.SECT"), None)
        if source is None:
            raise FileNotFoundError(f"Missing SECT file for arm section: {section_name}.SECT")
        for target in (job_dir / f"{section_name}.SECT", job_dir / "sections" / f"{section_name}.SECT"):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(target))
    return {
        "status": "pass",
        "primary_arm_section": primary_arm_section,
        "secondary_arm_section": secondary_arm_section,
        "primary_replacement_count": primary_count,
        "secondary_replacement_count": secondary_count,
        "yixing_secoffset_replacements": yixing_secoffset_count,
        "copied": copied,
        "source_ref": "square_section_outer_width_branch: <=120 uses 50-42/CAOGANG42DAN; >120 uses YIXINGGANG150/YIXINGGANG150DAN",
    }


def _arm_sections_for_square_outer(square_outer_mm: float | None) -> tuple[str, str, str]:
    if square_outer_mm is not None and square_outer_mm > 120.0:
        return "YIXINGGANG150", "YIXINGGANG150DAN", "square_gt_120_yixing_arm_family"
    return "50-42", "CAOGANG42DAN", "square_le_120_standard_channel_family"


def _read_trial_input_payload(job_dir: Path) -> dict[str, Any]:
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return {}
    try:
        return json.loads(input_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}


def _write_trial_input_payload(job_dir: Path, payload: dict[str, Any]) -> None:
    (job_dir / "input.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _section_record_is_square(section: dict[str, Any]) -> bool:
    return bool(
        parse_square_section_name(str(section.get("sect_file") or ""))
        or parse_square_section_name(str(section.get("section_id") or ""))
    )


def _upsert_section(payload: dict[str, Any], section_id: str, sect_file: str, source_ref: str) -> None:
    sections = payload.setdefault("sections", [])
    if not isinstance(sections, list):
        payload["sections"] = sections = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        if str(section.get("section_id") or "") == section_id:
            section.update(
                {
                    "section_id": section_id,
                    "sect_file": sect_file,
                    "section_type": section.get("section_type") or "BEAM_MESH",
                    "source_ref": source_ref,
                }
            )
            return
    sections.append(
        {
            "section_id": section_id,
            "sect_file": sect_file,
            "section_type": "BEAM_MESH",
            "source_ref": source_ref,
        }
    )


def _sync_trial_input_to_square_section(job_dir: Path, section_name: str, arm_policy: str) -> dict[str, Any]:
    """Keep a candidate trial's input/scope aligned with its generated APDL.

    The APDL, post-processing branch, analysis-scope gate and Chapter 6
    evaluator all read from job-local files.  A candidate trial that only
    replaces ``generated_model.mac`` can run one section but validate another.
    """

    parsed = parse_square_section_name(section_name)
    if parsed is None:
        return {"status": "skipped", "reason": "section_name is not a parsed square tube"}
    payload = _read_trial_input_payload(job_dir)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    metadata.update(
        {
            "square_section_current_model_spec": section_name,
            "square_section_spec": section_name,
            "square_section_outer_mm": parsed.outer_mm,
            "square_section_thickness_mm": parsed.thickness_mm,
            "arm_section_family": arm_policy,
            "square_section_trial_scope_status": "candidate_input_synced",
        }
    )
    stale_selected = metadata.get("square_section_selected") and str(metadata.get("square_section_selected")) != section_name
    if stale_selected:
        for key in (
            "square_section_selected",
            "square_section_selected_ratio",
            "square_section_selection_policy",
            "square_section_selection_source",
        ):
            metadata.pop(key, None)
        metadata["square_section_selection_status"] = "candidate_input_synced"
    payload["metadata"] = metadata

    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    support["support_section_id"] = section_name
    support["square_tube_width_m"] = parsed.outer_mm / 1000.0
    payload["support"] = support

    sections = payload.setdefault("sections", [])
    if not isinstance(sections, list):
        payload["sections"] = sections = []
    square_updated = False
    for section in sections:
        if not isinstance(section, dict) or not _section_record_is_square(section):
            continue
        section.update(
            {
                "section_id": section_name,
                "sect_file": section_name,
                "section_type": section.get("section_type") or "BEAM_MESH",
                "source_ref": "square_section_trial_candidate",
            }
        )
        square_updated = True
        break
    if not square_updated:
        sections.insert(
            0,
            {
                "section_id": section_name,
                "sect_file": section_name,
                "section_type": "BEAM_MESH",
                "source_ref": "square_section_trial_candidate",
            },
        )

    arm_primary, arm_secondary, _ = _arm_sections_for_square_outer(parsed.outer_mm)
    _upsert_section(payload, "arm-main", arm_primary, arm_policy)
    _upsert_section(payload, "arm-secondary", arm_secondary, arm_policy)

    _write_trial_input_payload(job_dir, payload)
    post_alignment_audit = align_postprocessor_to_intake(job_dir, payload)
    from core.validation.analysis_scope import classify_scope_from_job

    scope_audit = classify_scope_from_job(job_dir)
    return {
        "status": "pass",
        "section_name": section_name,
        "square_outer_mm": parsed.outer_mm,
        "square_thickness_mm": parsed.thickness_mm,
        "arm_section_family": arm_policy,
        "postprocessor_alignment": post_alignment_audit,
        "analysis_scope": {
            "status": scope_audit.get("status"),
            "appendix_c_mode": scope_audit.get("appendix_c_mode"),
            "square_outer_width_mm": scope_audit.get("square_outer_width_mm"),
            "square_thickness_mm": scope_audit.get("square_thickness_mm"),
        },
        "source_ref": "square_section_selector._sync_trial_input_to_square_section",
        "policy": "Candidate trial input.json and generated_post.mac must match the same square-tube section as generated_model.mac before ANSYS runs.",
    }


def _sync_model_h1_to_square_section(job_dir: Path, section_name: str) -> dict[str, Any]:
    """Keep generated model geometry width H1 aligned with the square tube.

    The first SECREAD controls the square-tube cross-section properties, but
    the source-family APDL also uses ``H1`` as the physical square-tube outside
    width in coordinates such as ``H1/2``.  Candidate trials must update both.
    """

    parsed = parse_square_section_name(section_name)
    model_path = job_dir / "generated_model.mac"
    if parsed is None:
        return {"status": "skipped", "reason": "section_name is not a parsed square tube"}
    if not model_path.exists():
        return {"status": "skipped", "reason": "generated_model.mac missing"}
    text = model_path.read_text(encoding="utf-8", errors="replace")
    h1_value = parsed.outer_mm / 1000.0
    updated, count = re.subn(
        r"(?m)^(\s*H1\s*=\s*)[-+0-9.Ee]+",
        rf"\g<1>{h1_value:.6f}",
        text,
        count=1,
    )
    if count == 0:
        lines = text.splitlines()
        insert_at = 0
        for index, line in enumerate(lines[:40]):
            if re.match(r"\s*(H2|L1|L2|L3|L4|L5|L6|senum|senum1)\s*=", line, re.IGNORECASE):
                insert_at = index
                break
        else:
            insert_at = 0
        lines.insert(insert_at, f"H1={h1_value:.6f}")
        updated = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    if updated != text:
        model_path.write_text(updated, encoding="utf-8", newline="\n")
    return {
        "status": "updated" if updated != text else "already_current",
        "section_name": section_name,
        "H1_m": h1_value,
        "replaced_count": count,
        "source_ref": "square_section_name outer width -> generated_model.mac H1",
        "policy": "For square tubes 100/120/140/160, model H1 equals the outer side length in meters; thickness does not affect H1.",
    }


def replace_square_and_arm_sections_in_model(
    job_dir: Path | str,
    section_name: str,
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
) -> dict[str, Any]:
    """Apply the exact section branch that the formal job will use.

    Candidate trials must not evaluate a different model than the final
    selected job.  The square tube and the cantilever/arm SECT family are a
    coupled S2 rule: outer width <=120 uses the standard channel arm family;
    outer width >120 uses the shaped-steel arm family.
    """

    job_dir = Path(job_dir)
    parsed = parse_square_section_name(section_name)
    replace_audit = replace_square_section_in_model(job_dir, section_name, source_root=source_root)
    model_h1_sync_audit = _sync_model_h1_to_square_section(job_dir, section_name)
    arm_primary, arm_secondary, arm_policy = _arm_sections_for_square_outer(parsed.outer_mm if parsed else None)
    arm_replace_audit = replace_arm_sections_in_model(
        job_dir,
        arm_primary,
        arm_secondary,
        source_root=source_root,
    )
    tray_section_preservation_audit = _assert_required_tray_sections_preserved(job_dir)
    trial_input_sync_audit = _sync_trial_input_to_square_section(job_dir, section_name, arm_policy)
    return {
        "status": "pass",
        "section_name": section_name,
        "replace_audit": replace_audit,
        "model_h1_sync_audit": model_h1_sync_audit,
        "arm_section_replace_audit": arm_replace_audit,
        "tray_section_preservation_audit": tray_section_preservation_audit,
        "trial_input_sync_audit": trial_input_sync_audit,
        "arm_section_family": arm_policy,
        "source_ref": "square_section_selector.replace_square_and_arm_sections_in_model",
    }


def run_square_section_search(
    base_job_dir: Path | str,
    trial_root: Path | str,
    *,
    candidates: list[SquareSectionCandidate] | None = None,
    runner: Callable[[Path], dict[str, Any]],
    source_root: Path | str = Path("source_materials/model_commands"),
    limit: int | None = None,
    overwrite_trials: bool = True,
    stop_after_first_feasible: bool = True,
    feasible_confirmation_count: int = 1,
    require_result_validation: bool = True,
    smart_order: bool = True,
    smart_jumps_enabled: bool = True,
    preferred_section: str | None = None,
    preferred_section_source: str | None = None,
    lower_neighbor_count: int = 0,
    max_evaluated_candidates: int | None = None,
    overlimit_recovery_candidate_count: int = OVERLIMIT_RECOVERY_SECTION_TRIALS,
    economic_ratio_min: float = ECONOMIC_RATIO_MIN,
    economic_ratio_max: float = ECONOMIC_RATIO_MAX,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    base_job_dir = Path(base_job_dir)
    trial_root = Path(trial_root)
    trial_root.mkdir(parents=True, exist_ok=True)
    catalog_candidate_list = candidates or discover_square_section_candidates(source_root)
    candidate_list = list(catalog_candidate_list)
    order_audit: dict[str, Any] = {"status": "disabled"}
    if smart_order:
        candidate_list, order_audit = prioritize_square_section_candidates(
            base_job_dir,
            candidate_list,
            preferred_section=preferred_section,
            preferred_section_source=preferred_section_source,
            lower_neighbor_count=lower_neighbor_count,
        )
    if limit is not None:
        candidate_list = candidate_list[:limit]
    results: list[dict[str, Any]] = []
    smart_jumps: list[dict[str, Any]] = []
    economy_corrections: list[dict[str, Any]] = []
    overlimit_recovery_extensions: list[dict[str, Any]] = []
    economic_downshift_extensions: list[dict[str, Any]] = []
    failure_exhaustion_extensions: list[dict[str, Any]] = []
    feasible_confirmation_hits = 0
    diagnostic_stop: dict[str, Any] | None = None
    base_candidate_budget = max(1, int(max_evaluated_candidates)) if max_evaluated_candidates is not None else None
    overlimit_recovery_budget = 0
    economic_downshift_budget = 0
    failure_exhaustion_active = False

    def _effective_candidate_budget() -> int | None:
        if failure_exhaustion_active:
            return None
        if base_candidate_budget is None:
            return None
        return base_candidate_budget + overlimit_recovery_budget + economic_downshift_budget

    def _deterministic_overlimit_result(item: dict[str, Any]) -> bool:
        try:
            ratio_value = float(item.get("controlling_ratio"))
        except (TypeError, ValueError):
            return False
        diagnosis = item.get("diagnosis") if isinstance(item.get("diagnosis"), dict) else {}
        return (
            ratio_value > 1.0
            and str(item.get("run_status") or "") in {"success", "pass"}
            and bool(diagnosis.get("continue_square_section_search", True))
            and not item.get("failed_non_ratio_checks")
        )

    def _has_feasible_result() -> bool:
        return any(
            isinstance(item, dict)
            and item.get("status") == "pass"
            and item.get("controlling_ratio") is not None
            and float(item.get("controlling_ratio")) <= 1.0
            for item in results
        )

    def _maybe_extend_overlimit_budget(reason: str, candidate: SquareSectionCandidate | None = None) -> bool:
        nonlocal overlimit_recovery_budget
        if base_candidate_budget is None or overlimit_recovery_candidate_count <= 0:
            return False
        if overlimit_recovery_budget >= overlimit_recovery_candidate_count:
            return False
        if len(results) < base_candidate_budget + overlimit_recovery_budget:
            return False
        if _has_feasible_result():
            return False
        overlimit_failures = [item for item in results if isinstance(item, dict) and _deterministic_overlimit_result(item)]
        if len(overlimit_failures) < base_candidate_budget:
            return False
        added = min(
            int(overlimit_recovery_candidate_count) - overlimit_recovery_budget,
            int(overlimit_recovery_candidate_count),
        )
        if added <= 0:
            return False
        overlimit_recovery_budget += added
        overlimit_recovery_extensions.append(
            {
                "status": "applied",
                "reason": reason,
                "after_candidate": candidate.section_name if candidate else None,
                "base_candidate_budget": base_candidate_budget,
                "added_candidate_budget": added,
                "effective_candidate_budget": base_candidate_budget + overlimit_recovery_budget,
                "overlimit_sections": [str(item.get("section_name")) for item in overlimit_failures],
                "overlimit_ratios": [item.get("controlling_ratio") for item in overlimit_failures],
                "policy": (
                    "The normal economy search is two candidates. When both are deterministic over-limit, "
                    "run up to two larger intake-allowed candidates before reporting section insufficiency."
                ),
            }
        )
        return True

    def _maybe_enable_failure_exhaustion(reason: str) -> bool:
        nonlocal failure_exhaustion_active
        if failure_exhaustion_active:
            return False
        if limit is not None:
            return False
        if diagnostic_stop or _has_feasible_result() or not results:
            return False
        if any(not _deterministic_overlimit_result(item) for item in results if isinstance(item, dict)):
            return False
        evaluated_names = {str(item.get("section_name")) for item in results if isinstance(item, dict)}
        remaining = [
            candidate
            for candidate in catalog_candidate_list
            if candidate.section_name not in evaluated_names
        ]
        if not remaining:
            return False
        candidate_list.extend(remaining)
        failure_exhaustion_active = True
        failure_exhaustion_extensions.append(
            {
                "status": "applied",
                "reason": reason,
                "added_candidate_count": len(remaining),
                "added_sections": [candidate.section_name for candidate in remaining],
                "evaluated_sections_before_exhaustion": sorted(evaluated_names),
                "policy": (
                    "The two-trial smart search is an efficiency path only. Before reporting that the intake-allowed "
                    "square sections are insufficient, run every remaining allowed section that has not been proven by "
                    "a fresh ANSYS deterministic ratio. This avoids declaring all allowed sections failed after a "
                    "non-monotonic dynamic response skips an intermediate section."
                ),
            }
        )
        return True

    def _maybe_extend_economic_downshift_budget(
        candidate: SquareSectionCandidate,
        correction: dict[str, Any],
    ) -> bool:
        nonlocal economic_downshift_budget
        if base_candidate_budget is None:
            return True
        effective_budget = _effective_candidate_budget()
        if effective_budget is None or len(results) < effective_budget:
            return True
        if economic_downshift_budget >= ECONOMY_DOWNSHIFT_SECTION_TRIALS:
            return False
        economic_downshift_budget += 1
        economic_downshift_extensions.append(
            {
                "status": "applied",
                "reason": "economic_low_ratio_downshift",
                "after_candidate": candidate.section_name,
                "next_section": correction.get("next_section"),
                "base_candidate_budget": base_candidate_budget,
                "added_candidate_budget": 1,
                "effective_candidate_budget": base_candidate_budget + overlimit_recovery_budget + economic_downshift_budget,
                "current_ratio": correction.get("current_ratio"),
                "economic_downshift_ratio_min": ECONOMIC_RATIO_MIN,
                "economic_downshift_ratio_max": ECONOMIC_DOWNSHIFT_RATIO_MAX,
                "policy": (
                    "A passing candidate at ratio <= 0.75 may be oversized. "
                    "Run exactly one immediately lower intake-allowed section; if that lower section fails, "
                    "keep the already passing larger section."
                ),
            }
        )
        return True

    def _progress_candidate_count() -> int:
        effective_budget = _effective_candidate_budget()
        if effective_budget is None:
            return max(1, len(candidate_list))
        return max(1, min(len(candidate_list), max(1, effective_budget)))

    index = 0
    while True:
        if index >= len(candidate_list):
            if _maybe_enable_failure_exhaustion("candidate_list_exhausted_without_feasible"):
                continue
            break
        effective_budget = _effective_candidate_budget()
        if effective_budget is not None and len(results) >= effective_budget:
            if _maybe_extend_overlimit_budget("base_budget_exhausted_before_next_candidate"):
                effective_budget = _effective_candidate_budget()
            elif _maybe_enable_failure_exhaustion("candidate_budget_exhausted_without_feasible"):
                continue
            else:
                break
        if effective_budget is not None and len(results) >= effective_budget:
            break
        candidate = candidate_list[index]
        if candidate.section_name in {str(item.get("section_name")) for item in results}:
            index += 1
            continue
        progress_candidate_count = _progress_candidate_count()
        if progress_callback:
            progress_callback(
                {
                    "stage": "select_square_section",
                    "candidate_index": len(results) + 1,
                    "candidate_count": progress_candidate_count,
                    "candidate_section": candidate.section_name,
                    "completed_candidate_count": len(results),
                    "message": f"正在计算候选方钢截面 {candidate.section_name}（已完成 {len(results)}/{progress_candidate_count}）",
                }
            )
        trial_dir = trial_root / candidate.section_name
        if trial_dir.exists():
            if not overwrite_trials:
                results.append(
                    {
                        "section_name": candidate.section_name,
                        "estimated_area_mm2": candidate.estimated_area_mm2,
                        "estimated_bending_section_modulus_mm3": candidate.estimated_bending_section_modulus_mm3,
                        "source_kind": candidate.source_kind,
                        "controlling_ratio": None,
                        "trial_dir": str(trial_dir),
                        "status": "fail",
                        "run_status": "skipped_existing_trial",
                    }
                )
                index += 1
                continue
            shutil.rmtree(trial_dir)
        shutil.copytree(base_job_dir, trial_dir, ignore=_trial_copy_ignore)
        stale_output_cleanup = _clean_trial_runtime_outputs(trial_dir)
        trial_section_replace_audit = replace_square_and_arm_sections_in_model(
            trial_dir,
            candidate.section_name,
            source_root=source_root,
        )
        run_result = runner(trial_dir)
        summary_path = trial_dir / "evaluation_summary.json"
        ratio = None
        final_chapter6_ratio = None
        square_ratio = None
        gate_status = "missing_summary"
        validation_status = None
        dominant_check_id = None
        dominant_component = None
        failed_non_ratio_checks: list[str] = []
        if summary_path.exists():
            evaluation_summary = json.loads(summary_path.read_text(encoding="utf-8"))
            ratio_payload = candidate_publishable_ratio(
                trial_dir,
                evaluation_summary,
                require_result_validation=require_result_validation,
            )
            ratio = ratio_payload.get("controlling_ratio")
            final_chapter6_ratio = ratio_payload.get("final_chapter6_controlling_ratio")
            square_ratio = ratio_payload.get("square_support_ratio")
            gate_status = str(ratio_payload.get("status") or "")
            validation_status = ratio_payload.get("validation_status")
            dominant_check_id = ratio_payload.get("dominant_check_id")
            dominant_component = ratio_payload.get("dominant_component")
            failed_non_ratio_checks = list(ratio_payload.get("failed_non_ratio_checks") or [])
        run_ok = run_result.get("status") in {"success", "pass"}
        candidate_status = "pass" if run_ok and ratio is not None and gate_status == "pass" else "fail"
        effective_validation_status = validation_status
        if candidate_status == "pass" and not failed_non_ratio_checks:
            effective_validation_status = "pass"
        diagnosis = _candidate_trial_diagnosis(
            trial_dir,
            run_result=run_result,
            gate_status=gate_status,
            failed_non_ratio_checks=failed_non_ratio_checks,
            ratio=ratio,
            square_ratio=square_ratio,
        )
        result_item = {
            "section_name": candidate.section_name,
            "estimated_area_mm2": candidate.estimated_area_mm2,
            "estimated_bending_section_modulus_mm3": candidate.estimated_bending_section_modulus_mm3,
            "source_kind": candidate.source_kind,
            "controlling_ratio": ratio,
            "section_selection_ratio": ratio,
            "final_chapter6_controlling_ratio": final_chapter6_ratio,
            "square_support_ratio": square_ratio,
            "result_gate_status": gate_status,
            "trial_validation_status": validation_status,
            "effective_validation_status": effective_validation_status,
            "validation_status": effective_validation_status,
            "dominant_check_id": dominant_check_id,
            "dominant_component": dominant_component,
            "failed_non_ratio_checks": failed_non_ratio_checks,
            "trial_dir": str(trial_dir),
            "status": candidate_status,
            "economic_ratio_status": _economic_ratio_status(float(ratio) if ratio is not None else None),
            "economic_ratio_min": economic_ratio_min,
            "economic_ratio_max": economic_ratio_max,
            "run_status": run_result.get("status"),
            "diagnosis": diagnosis,
            "trial_stale_output_cleanup": stale_output_cleanup,
            "trial_section_replace_audit": trial_section_replace_audit,
        }
        results.append(result_item)
        progress_candidate_count = _progress_candidate_count()
        if progress_callback:
            progress_callback(
                {
                    "stage": "select_square_section",
                    "candidate_index": len(results),
                    "candidate_count": progress_candidate_count,
                    "candidate_section": candidate.section_name,
                    "completed_candidate_count": len(results),
                    "message": (
                        f"候选方钢截面 {candidate.section_name} 完成："
                        f"控制比值 {ratio if ratio is not None else '未取得'}"
                    ),
                }
            )
        if not diagnosis.get("continue_square_section_search", True):
            reason = (
                "Candidate failed because required ANSYS/PIP source outputs are missing, UNKNOWN, all-zero or stalled; "
                "do not keep enlarging the square tube."
            )
            if "ansys_timeout" in set(diagnosis.get("domains") or []):
                reason = (
                    "Candidate ANSYS run timed out before complete result extraction, so no deterministic section ratio "
                    "was produced. Treat this as a runtime timeout, not as a square-section over-limit decision."
                )
            if diagnosis.get("formal_validation_retryable"):
                reason = (
                    "Candidate ratio is <= 1.0, but this trial missed required ANSYS/PIP source outputs; "
                    "stop section sweeping and run the same section through the formal full calculation."
                )
            diagnostic_stop = {
                "status": "stopped",
                "reason": reason,
                "candidate_section": candidate.section_name,
                "domains": diagnosis.get("domains", []),
                "failed_checks": diagnosis.get("failed_checks", []),
                "trial_dir": str(trial_dir),
                "run_status": run_result.get("status"),
                "formal_validation_retryable": diagnosis.get("formal_validation_retryable", False),
                "policy": (
                    "Run the feasible candidate as a formal full calculation and let the formal result_validation gate decide."
                    if diagnosis.get("formal_validation_retryable")
                    else (
                        "Rerun with production ANSYS watchdog settings before making any section decision."
                        if "ansys_timeout" in set(diagnosis.get("domains") or [])
                        else "Fix model/load/spectrum/post-processing source collections before section optimization continues."
                    )
                ),
            }
            break
        if ratio is not None and run_ok and gate_status == "pass" and ratio <= 1.0:
            feasible_confirmation_hits += 1
            required_confirmations = max(1, int(feasible_confirmation_count))
            downshift = (
                _economic_downshift_candidate(
                    catalog_candidate_list,
                    candidate,
                    result_item,
                    {str(item.get("section_name")) for item in results},
                )
                if stop_after_first_feasible and not failure_exhaustion_active
                else None
            )
            if downshift and _maybe_extend_economic_downshift_budget(candidate, downshift):
                next_section = str(downshift["next_section"])
                next_index = _candidate_index_by_name(candidate_list, next_section)
                if next_index is None:
                    catalog_index = _candidate_index_by_name(catalog_candidate_list, next_section)
                    next_candidate = catalog_candidate_list[catalog_index] if catalog_index is not None else None
                    if next_candidate is not None:
                        candidate_list.append(next_candidate)
                        next_index = len(candidate_list) - 1
                if next_index is not None:
                    downshift["next_index"] = next_index
                    economy_corrections.append(downshift)
                    index = next_index
                    continue
            if (
                economic_ratio_min <= float(ratio) <= economic_ratio_max
                and stop_after_first_feasible
                and feasible_confirmation_hits >= required_confirmations
            ):
                break
            correction = (
                _economic_correction_candidate(
                    catalog_candidate_list,
                    candidate,
                    result_item,
                    {str(item.get("section_name")) for item in results},
                )
                if not failure_exhaustion_active
                and (_effective_candidate_budget() is None or len(results) < int(_effective_candidate_budget() or 0))
                else None
            )
            if correction:
                next_section = str(correction["next_section"])
                next_index = _candidate_index_by_name(candidate_list, next_section)
                if next_index is None:
                    catalog_index = _candidate_index_by_name(catalog_candidate_list, next_section)
                    next_candidate = catalog_candidate_list[catalog_index] if catalog_index is not None else None
                    if next_candidate is not None:
                        candidate_list.append(next_candidate)
                        next_index = len(candidate_list) - 1
                if next_index is not None:
                    correction["next_index"] = next_index
                    economy_corrections.append(correction)
                    index = next_index
                    continue
            if stop_after_first_feasible and feasible_confirmation_hits >= required_confirmations:
                break
        elif ratio is not None and run_ok and ratio > 1.0:
            if _effective_candidate_budget() is not None and len(results) >= int(_effective_candidate_budget() or 0):
                _maybe_extend_overlimit_budget("two_candidate_overlimit_recovery", candidate)
            correction = (
                _economic_correction_candidate(
                    catalog_candidate_list,
                    candidate,
                    result_item,
                    {str(item.get("section_name")) for item in results},
                )
                if not failure_exhaustion_active
                and (_effective_candidate_budget() is None or len(results) < int(_effective_candidate_budget() or 0))
                else None
            )
            if correction:
                next_section = str(correction["next_section"])
                next_index = _candidate_index_by_name(candidate_list, next_section)
                if next_index is None:
                    catalog_index = _candidate_index_by_name(catalog_candidate_list, next_section)
                    next_candidate = catalog_candidate_list[catalog_index] if catalog_index is not None else None
                    if next_candidate is not None:
                        candidate_list.append(next_candidate)
                        next_index = len(candidate_list) - 1
                if next_index is not None:
                    correction["next_index"] = next_index
                    economy_corrections.append(correction)
                    index = next_index
                    continue
        stable_blocker = _stable_non_square_blocker(results)
        if stable_blocker:
            break
        jump = (
            _smart_jump_after_square_ratio_failure(candidate_list, index, results[-1])
            if smart_jumps_enabled and not failure_exhaustion_active
            else None
        )
        if jump:
            smart_jumps.append(jump)
            index = int(jump["next_index"])
            continue
        index += 1
    selection = select_best_square_section(results)
    stable_blocker = _stable_non_square_blocker(results)
    if stable_blocker:
        selection["early_stop"] = stable_blocker
        if selection.get("status") != "pass":
            selection["reason"] = stable_blocker["reason"]
    if diagnostic_stop:
        selection["early_stop"] = diagnostic_stop
        if selection.get("status") != "pass":
            selection["reason"] = diagnostic_stop["reason"]
    selection["search_policy"] = (
        "Candidates are prioritized from the current standard template section, or from a similar-intake cache hit "
        "used only as an ordering hint, or from a deterministic engineering estimate for blank-section new intake. "
        "When the intake calculation note lists allowed square sections, that reviewed list remains the hard boundary; "
        "engineering estimates cannot skip or add candidates, and high-similarity learned history may only move the "
        "starting point inside that allowed list. Production economy target is 0.60 <= ratio <= 0.9999 and the "
        "search normally runs at most two fresh ANSYS candidate trials: one first candidate and one section-modulus "
        "correction if the first ratio is outside the economy band. If both normal trials are deterministic over-limit, "
        "the search may run up to two larger intake-allowed recovery candidates. If a passing larger section lands in "
        "ratio <= 0.75, the search may run exactly one immediately lower intake-allowed section as an economy "
        "downshift check. If JCZH/LS-FORCE/HF-FORCE/MAX/TMAX/Mode or runtime output-growth checks fail, "
        "section sweeping stops and the source/post-processing issue must be fixed first. Feasibility is based on "
        "deterministic ratios; final report-figure checks are applied only after the selected formal run."
    )
    selection["candidate_order_audit"] = order_audit
    selection["smart_jumps"] = smart_jumps
    selection["economy_corrections"] = economy_corrections
    selection["overlimit_recovery_extensions"] = overlimit_recovery_extensions
    selection["economic_downshift_extensions"] = economic_downshift_extensions
    selection["failure_exhaustion_extensions"] = failure_exhaustion_extensions
    selection["overlimit_recovery_candidate_count"] = overlimit_recovery_candidate_count
    selection["economic_downshift_candidate_count"] = ECONOMY_DOWNSHIFT_SECTION_TRIALS
    selection["failure_exhaustion_active"] = failure_exhaustion_active
    selection["smart_jumps_enabled"] = smart_jumps_enabled
    selection["smart_skipped_candidate_count"] = sum(int(item.get("skipped_count") or 0) for item in smart_jumps)
    selection["stop_after_first_feasible"] = stop_after_first_feasible
    selection["feasible_confirmation_count"] = feasible_confirmation_count
    selection["lower_neighbor_count"] = lower_neighbor_count
    selection["evaluated_candidate_count"] = len(results)
    selection["available_candidate_count"] = len(candidate_list)
    selection["catalog_candidate_count"] = len(catalog_candidate_list)
    selection["max_evaluated_candidates"] = max_evaluated_candidates
    selection["effective_evaluated_candidate_budget"] = _effective_candidate_budget()
    selection["economic_ratio_min"] = economic_ratio_min
    selection["economic_ratio_max"] = economic_ratio_max
    selection["trial_refresh_policy"] = (
        "Candidate trial directories are regenerated for every section run. "
        "An existing trial directory is deleted when overwrite_trials=True, so stale ANSYS/result JSON cannot decide selection."
    )
    selection["overwrite_trials"] = overwrite_trials
    (trial_root / "square_section_selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    return selection
