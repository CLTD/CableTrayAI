from __future__ import annotations

import json
import shutil
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.ansys.artifact_cleanup import cleanup_heavy_solver_artifacts
from core.ansys.config import AnsysLocalConfig
from core.ansys.lock_cleanup import cleanup_stale_ansys_locks
from core.ansys.runner import (
    MIN_REAL_RUN_OUTPUT_STALL_TIMEOUT_SECONDS,
    MIN_REAL_RUN_STARTUP_NO_OUTPUT_TIMEOUT_SECONDS,
    MIN_REAL_RUN_TIMEOUT_MINUTES,
    run_real_ansys,
)
from core.apdl.postprocessor_alignment import align_postprocessor_to_intake
from core.audit.job_state import update_job_state
from core.optimizer.square_section_selector import (
    SquareSectionCandidate,
    is_section_selection_evaluation_row,
    discover_square_section_candidates,
    parse_square_section_name,
    replace_square_and_arm_sections_in_model,
    run_square_section_search,
)
from core.results.result_assembler import assemble_result


SQUARE_SECTION_CACHE_VERSION = "square-section-cache-v7-section-6-1-ratio"
SECTION_LEARNING_ALLOWED_START_THRESHOLD = 0.82
SECTION_LEARNING_LOWER_GUARD_COUNT = 2
LEARNED_FORMAL_VALIDATION_THRESHOLD = 0.95


def _arm_sections_for_square_outer(square_outer_mm: float | None) -> tuple[str, str, str]:
    if square_outer_mm is not None and square_outer_mm > 120.0:
        return "YIXINGGANG150", "YIXINGGANG150DAN", "square_gt_120_yixing_arm_family"
    return "50-42", "CAOGANG42DAN", "square_le_120_standard_channel_family"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _selection_cache_path(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else Path("data/calibration/square_section_selection_cache.json")


def _selection_cache_key(payload: dict[str, Any]) -> str:
    support = dict(payload.get("support") or {})
    for key in ("square_tube_width_m", "support_section_id"):
        support.pop(key, None)
    metadata = payload.get("metadata") or {}
    comparable = {
        "cache_version": SQUARE_SECTION_CACHE_VERSION,
        "project": payload.get("project") or {},
        "spectrum": payload.get("spectrum") or {},
        "support_without_square_section": support,
        "tray_layers": payload.get("tray_layers") or [],
        "load_cases": payload.get("load_cases") or [],
        "analysis_method": metadata.get("analysis_method"),
        "tray_load_mapping": metadata.get("tray_load_mapping"),
        "allowed_square_section_ids": _allowed_square_section_ids_from_payload(payload),
        "static_acceleration": {
            key: metadata.get(key)
            for key in (
                "static_acceleration_factor",
                "zpa_obe_x_g",
                "zpa_obe_y_g",
                "zpa_obe_z_g",
                "zpa_sse_x_g",
                "zpa_sse_y_g",
                "zpa_sse_z_g",
            )
        },
    }
    blob = json.dumps(comparable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _load_selection_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _as_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _as_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _layer_width_mm(layer: dict[str, Any]) -> float | None:
    width = _as_float(layer.get("width_mm") or layer.get("tray_width_mm") or layer.get("width"))
    if width is not None:
        return width
    width_m = _as_float(layer.get("tray_width_m"))
    if width_m is not None:
        return width_m * 1000.0
    return None


def _layer_load_kg_m(layer: dict[str, Any]) -> float | None:
    return _as_float(
        layer.get("load_kg_m")
        or layer.get("load_kg_per_m")
        or layer.get("line_load_kg_m")
        or layer.get("mass_per_m_kg")
    )


def _payload_tray_design_layers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_layers = payload.get("tray_layers") if isinstance(payload.get("tray_layers"), list) else []
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    mapping = metadata.get("tray_load_mapping") if isinstance(metadata.get("tray_load_mapping"), dict) else {}
    mapped_layers = mapping.get("layers") if isinstance(mapping.get("layers"), list) else []
    mapped = [layer for layer in mapped_layers if isinstance(layer, dict)]
    if mapped:
        return mapped
    return [layer for layer in raw_layers if isinstance(layer, dict)]


def _normalised_section_id(value: Any) -> str | None:
    text = re.sub(r"[×xX*＊]", "-", str(value or "").strip())
    text = re.sub(r"\s+", "", text)
    parsed = parse_square_section_name(text)
    if not parsed:
        return None
    return f"{parsed.outer_mm:g}-{parsed.outer_mm:g}-{parsed.thickness_mm:g}"


def _split_allowed_section_values(raw: Any) -> list[Any]:
    if raw in (None, ""):
        return []
    if isinstance(raw, (list, tuple, set)):
        return list(raw)
    return [part for part in re.split(r"[,，;；、\s]+", str(raw)) if str(part).strip()]


def _allowed_square_section_ids_from_payload(payload: dict[str, Any]) -> list[str]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    raw = (
        metadata.get("allowed_square_section_ids")
        or support.get("allowed_square_section_ids")
        or metadata.get("allowed_square_sections")
        or support.get("allowed_square_sections")
    )
    values: list[str] = []
    for item in _split_allowed_section_values(raw):
        section_id = _normalised_section_id(item)
        if section_id and section_id not in values:
            values.append(section_id)
    return values


def _allowed_square_section_source_ref(payload: dict[str, Any]) -> str | None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    value = metadata.get("allowed_square_section_source_ref") or support.get("allowed_square_section_source_ref")
    return str(value) if value else None


def _section_allowed_by_payload(section_name: Any, payload: dict[str, Any]) -> bool:
    allowed = _allowed_square_section_ids_from_payload(payload)
    if not allowed:
        return False
    section_id = _normalised_section_id(section_name)
    return section_id in set(allowed)


def _filter_allowed_square_candidates(
    candidates: list[SquareSectionCandidate],
    payload: dict[str, Any],
) -> tuple[list[SquareSectionCandidate], dict[str, Any]]:
    allowed = _allowed_square_section_ids_from_payload(payload)
    if not allowed:
        return [], {
            "status": "missing_required",
            "allowed_square_section_ids": [],
            "source_ref": _allowed_square_section_source_ref(payload),
            "before_count": len(candidates),
            "after_count": 0,
            "policy": (
                "Automatic square-section selection requires the intake calculation-note allowed-section list. "
                "The local SECT catalog, similar-job cache and historical reports are not allowed to add candidates."
            ),
        }
    allowed_set = set(allowed)
    filtered = [candidate for candidate in candidates if candidate.section_name in allowed_set]
    present = {candidate.section_name for candidate in filtered}
    return filtered, {
        "status": "applied",
        "allowed_square_section_ids": allowed,
        "source_ref": _allowed_square_section_source_ref(payload),
        "before_count": len(candidates),
        "after_count": len(filtered),
        "missing_allowed_sections": [section for section in allowed if section not in present],
        "policy": (
            "Only square sections explicitly listed in the intake calculation notes are trialed. "
            "Cache/similar-history hits may only reorder those allowed candidates and cannot add unlisted sections."
        ),
    }


def _allowed_section_insufficient_reason(payload: dict[str, Any], *, no_catalog: bool = False) -> str:
    if _allowed_square_section_ids_from_payload(payload):
        if no_catalog:
            return "提资允许截面不足：计算说明列出的方钢截面没有可用的本地 SECT 截面文件。"
        return "提资允许截面不足：计算说明允许的方钢截面均未满足应力比 < 1。"
    return "缺少提资计算说明允许方钢截面：自动方钢选型已停止，不能回退本地 SECT 目录、相似 job 缓存或历史报告。"


def _selection_similarity_features(payload: dict[str, Any]) -> dict[str, Any]:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    design_layers = _payload_tray_design_layers(payload)
    widths: list[float] = []
    loads: list[float] = []
    for layer in design_layers:
        width = _layer_width_mm(layer)
        if width is not None:
            widths.append(width)
        load = _layer_load_kg_m(layer)
        if load is not None:
            loads.append(load)
    payload_layers = payload.get("tray_layers") if isinstance(payload.get("tray_layers"), list) else []
    return {
        "support_type": _as_text(support.get("support_type")),
        "analysis_method": _as_text(metadata.get("analysis_method")),
        "building": _as_text(project.get("building")),
        "area": _as_text(project.get("area")),
        "elevation_m": _as_float(project.get("elevation")),
        "support_spacing_m": _as_float(support.get("support_spacing_m")),
        "support_height_m": _as_float(support.get("support_height_m")),
        "layers_front": int(_as_float(support.get("layers_front")) or 0),
        "layers_back": int(_as_float(support.get("layers_back")) or 0),
        "layer_count": len(payload_layers) or len(design_layers),
        "tray_widths_mm": sorted(round(width, 3) for width in widths),
        "tray_load_sum_kg_m": round(sum(loads), 6) if loads else None,
    }


def _relative_close(a: float | None, b: float | None, *, tolerance: float) -> bool:
    if a is None or b is None:
        return False
    scale = max(abs(a), abs(b), 1.0)
    return abs(a - b) / scale <= tolerance


def _selection_similarity_score(current: dict[str, Any], cached: dict[str, Any]) -> dict[str, Any]:
    mandatory_pairs = ("support_type", "analysis_method")
    for key in mandatory_pairs:
        if current.get(key) and cached.get(key) and current.get(key) != cached.get(key):
            return {"score": 0.0, "matched": [], "mismatched": [key], "policy": "mandatory feature mismatch"}

    matched: list[str] = []
    mismatched: list[str] = []
    score = 0.0
    weight = 0.0

    def add_exact(key: str, points: float) -> None:
        nonlocal score, weight
        left = current.get(key)
        right = cached.get(key)
        if left in (None, "") or right in (None, ""):
            return
        weight += points
        if left == right:
            score += points
            matched.append(key)
        else:
            mismatched.append(key)

    def add_close(key: str, points: float, tolerance: float) -> None:
        nonlocal score, weight
        left = current.get(key)
        right = cached.get(key)
        if left is None or right is None:
            return
        weight += points
        if _relative_close(left, right, tolerance=tolerance):
            score += points
            matched.append(key)
        else:
            mismatched.append(key)

    for key, points in (
        ("support_type", 2.0),
        ("analysis_method", 2.0),
        ("building", 1.0),
        ("area", 1.0),
        ("layers_front", 1.0),
        ("layers_back", 1.0),
        ("layer_count", 1.0),
    ):
        add_exact(key, points)
    add_close("elevation_m", 1.0, 0.08)
    add_close("support_spacing_m", 1.0, 0.10)
    add_close("support_height_m", 1.0, 0.10)
    add_close("tray_load_sum_kg_m", 1.0, 0.12)
    if current.get("tray_widths_mm") and cached.get("tray_widths_mm"):
        weight += 1.0
        if current["tray_widths_mm"] == cached["tray_widths_mm"]:
            score += 1.0
            matched.append("tray_widths_mm")
        else:
            mismatched.append("tray_widths_mm")

    return {
        "score": round(score / weight, 6) if weight else 0.0,
        "matched": matched,
        "mismatched": mismatched,
        "policy": "similar intake can only reorder candidate sections; it never reuses a result",
    }


def _read_similar_cached_selection(job_dir: Path, *, cache_path: Path, threshold: float = 0.62) -> dict[str, Any] | None:
    payload = _read_json(job_dir / "input.json")
    current_features = _selection_similarity_features(payload)
    cache = _load_selection_cache(cache_path)
    best: dict[str, Any] | None = None
    best_rank: tuple[float, int, str] | None = None
    for cache_key, entry in (cache.get("entries") or {}).items():
        if not isinstance(entry, dict) or entry.get("status") != "pass":
            continue
        selected = entry.get("selected") if isinstance(entry.get("selected"), dict) else {}
        if not selected.get("section_name"):
            continue
        if not _section_allowed_by_payload(selected.get("section_name"), payload):
            continue
        cached_features = entry.get("similarity_features") if isinstance(entry.get("similarity_features"), dict) else {}
        if not cached_features:
            continue
        score = _selection_similarity_score(current_features, cached_features)
        if score["score"] < threshold:
            continue
        candidate = {
            "status": "hit",
            "cache_key": cache_key,
            "cache_path": str(cache_path),
            "source_job_dir": entry.get("source_job_dir"),
            "selected_section_hint": selected.get("section_name"),
            "entry_cache_version": entry.get("cache_version"),
            "entry_updated_at": entry.get("updated_at"),
            "historical_candidate_results": [
                {
                    key: item.get(key)
                    for key in (
                        "section_name",
                        "status",
                        "run_status",
                        "controlling_ratio",
                        "square_support_ratio",
                        "dominant_check_id",
                        "result_gate_status",
                    )
                }
                for item in entry.get("candidate_results", [])
                if isinstance(item, dict)
            ],
            "similarity": score,
            "source_ref": "square_section_selection_cache.json:similarity_features",
        }
        rank = (
            float(candidate["similarity"]["score"]),
            1 if entry.get("cache_version") == SQUARE_SECTION_CACHE_VERSION else 0,
            str(entry.get("updated_at") or ""),
        )
        if best is None or best_rank is None or rank > best_rank:
            best = candidate
            best_rank = rank
    return best


def _compact_candidate_result_for_cache(item: dict[str, Any]) -> dict[str, Any]:
    keep_keys = (
        "section_name",
        "estimated_area_mm2",
        "estimated_bending_section_modulus_mm3",
        "source_kind",
        "controlling_ratio",
        "section_selection_ratio",
        "final_chapter6_controlling_ratio",
        "square_support_ratio",
        "result_gate_status",
        "trial_validation_status",
        "effective_validation_status",
        "validation_status",
        "dominant_check_id",
        "dominant_component",
        "failed_non_ratio_checks",
        "status",
        "run_status",
    )
    return {key: item.get(key) for key in keep_keys if key in item}


def _write_cached_selection(job_dir: Path, selection: dict[str, Any], *, cache_path: Path) -> None:
    payload = _read_json(job_dir / "input.json")
    key = _selection_cache_key(payload)
    selected = selection.get("selected") or {}
    if selection.get("status") != "pass" or not selected.get("section_name"):
        return
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_selection_cache(cache_path)
    entries = cache.setdefault("entries", {})
    compact_selected = _compact_candidate_result_for_cache(selected)
    entries[key] = {
        "status": "pass",
        "selected": compact_selected,
        "candidate_results": [
            _compact_candidate_result_for_cache(item)
            for item in selection.get("candidate_results", [])
            if isinstance(item, dict)
        ],
        "policy": selection.get("policy"),
        "source_job_dir": str(job_dir),
        "source_ref": "real ANSYS square-section trial for identical normalized intake payload",
        "similarity_features": _selection_similarity_features(payload),
        "cache_version": SQUARE_SECTION_CACHE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    cache["cache_version"] = SQUARE_SECTION_CACHE_VERSION
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _learned_allowed_candidate_start(
    candidates: list[SquareSectionCandidate],
    similar_hint: dict[str, Any] | None,
    *,
    threshold: float = SECTION_LEARNING_ALLOWED_START_THRESHOLD,
    lower_guard_count: int = SECTION_LEARNING_LOWER_GUARD_COUNT,
) -> tuple[list[SquareSectionCandidate], dict[str, Any]]:
    if not candidates:
        return candidates, {"status": "skipped", "reason": "empty_candidate_list"}
    if not similar_hint:
        return candidates, {"status": "skipped", "reason": "no_similar_successful_selection"}
    similarity = similar_hint.get("similarity") if isinstance(similar_hint.get("similarity"), dict) else {}
    score = _as_float(similarity.get("score"))
    if score is None or score < threshold:
        return candidates, {
            "status": "skipped",
            "reason": "similarity_below_allowed_start_threshold",
            "similarity_score": score,
            "similarity_threshold": threshold,
        }
    section_name = str(similar_hint.get("selected_section_hint") or "")
    selected_index = next((idx for idx, item in enumerate(candidates) if item.section_name == section_name), None)
    if selected_index is None:
        return candidates, {
            "status": "skipped",
            "reason": "learned_selected_section_not_in_current_allowed_list",
            "selected_section_hint": section_name,
            "similarity_score": score,
            "similarity_threshold": threshold,
        }
    start_index = max(0, selected_index - max(0, int(lower_guard_count)))
    skipped = candidates[:start_index]
    ordered = candidates[start_index:]
    return ordered, {
        "status": "applied" if skipped else "not_needed",
        "selected_section_hint": section_name,
        "source_job_dir": similar_hint.get("source_job_dir"),
        "cache_key": similar_hint.get("cache_key"),
        "similarity_score": score,
        "similarity_threshold": threshold,
        "lower_guard_count": lower_guard_count,
        "selected_index": selected_index,
        "start_index": start_index,
        "skipped_lower_allowed_sections": [item.section_name for item in skipped],
        "candidate_sections": [item.section_name for item in ordered],
        "historical_candidate_results": similar_hint.get("historical_candidate_results", []),
        "policy": (
            "A high-similarity successful real-ANSYS selection can move the starting point inside the current "
            "intake-allowed section list, while keeping lower economic guard candidates before the learned section. "
            "It cannot add unlisted sections and cannot accept a section without a fresh ANSYS trial and deterministic "
            "ratio gate for the current job."
        ),
    }


def _historical_immediate_lower_failed(
    candidates: list[SquareSectionCandidate],
    selected_section: str,
    historical_results: list[dict[str, Any]],
) -> dict[str, Any]:
    selected_index = next((idx for idx, item in enumerate(candidates) if item.section_name == selected_section), None)
    if selected_index is None:
        return {"status": "not_applicable", "reason": "selected_section_not_in_allowed_list"}
    if selected_index <= 0:
        return {"status": "not_applicable", "reason": "selected_section_is_minimum_allowed"}
    lower = candidates[selected_index - 1]
    for item in historical_results:
        if not isinstance(item, dict) or str(item.get("section_name") or "") != lower.section_name:
            continue
        ratio = _as_float(item.get("section_selection_ratio") or item.get("controlling_ratio"))
        section_sensitive = is_section_selection_evaluation_row(
            {"check_id": item.get("dominant_check_id"), "component": item.get("dominant_component")}
        )
        if ratio is not None and ratio > 1.0 and str(item.get("run_status") or "") == "pass" and section_sensitive:
            return {
                "status": "pass",
                "lower_section": lower.section_name,
                "historical_ratio": ratio,
                "historical_status": item.get("status"),
                "historical_run_status": item.get("run_status"),
                "source_ref": "square_section_selection_cache.json:historical_candidate_results",
            }
        return {
            "status": "fail",
            "lower_section": lower.section_name,
            "historical_ratio": ratio,
            "historical_status": item.get("status"),
            "historical_run_status": item.get("run_status"),
            "reason": "immediate lower section was not proven over limit by a successful historical ANSYS Chapter 6.1 trial",
        }
    return {
        "status": "missing",
        "lower_section": lower.section_name,
        "reason": "no historical result for the immediate lower allowed section",
    }


def _learned_formal_validation_selection(
    *,
    candidates: list[SquareSectionCandidate],
    similar_hint: dict[str, Any] | None,
    allowed_square_section_filter: dict[str, Any],
) -> dict[str, Any] | None:
    """Use learned section ordering to skip duplicate candidate trials.

    This never reuses a result.  It only applies a high-confidence section hint
    to the formal job so the one real ANSYS run for the current intake becomes
    the deterministic validation.  If the formal result fails, the existing
    square-section upgrade/reselection gates still run.
    """

    if allowed_square_section_filter.get("status") != "applied" or not similar_hint:
        return None
    if str(similar_hint.get("entry_cache_version") or "") != SQUARE_SECTION_CACHE_VERSION:
        return None
    similarity = similar_hint.get("similarity") if isinstance(similar_hint.get("similarity"), dict) else {}
    score = _as_float(similarity.get("score"))
    if score is None or score < LEARNED_FORMAL_VALIDATION_THRESHOLD:
        return None
    selected_section = str(similar_hint.get("selected_section_hint") or "")
    selected_candidate = next((item for item in candidates if item.section_name == selected_section), None)
    if selected_candidate is None:
        return None
    historical_results = [
        item for item in (similar_hint.get("historical_candidate_results") or []) if isinstance(item, dict)
    ]
    selected_history = next((item for item in historical_results if item.get("section_name") == selected_section), {})
    if not is_section_selection_evaluation_row(
        {
            "check_id": selected_history.get("dominant_check_id"),
            "component": selected_history.get("dominant_component"),
        }
    ):
        return None
    selected_ratio = _as_float(selected_history.get("section_selection_ratio") or selected_history.get("controlling_ratio"))
    if selected_ratio is None or not (0.60 <= selected_ratio <= 0.9999):
        return None
    if str(selected_history.get("run_status") or "") != "pass":
        return None
    lower_failure_audit: dict[str, Any] = {"status": "not_required", "reason": "selected ratio is already above 0.75"}
    if selected_ratio <= 0.75:
        lower_failure_audit = _historical_immediate_lower_failed(candidates, selected_section, historical_results)
        if lower_failure_audit.get("status") != "pass":
            return None
    selected_payload = {
        "section_name": selected_candidate.section_name,
        "estimated_area_mm2": selected_candidate.estimated_area_mm2,
        "estimated_bending_section_modulus_mm3": selected_candidate.estimated_bending_section_modulus_mm3,
        "source_kind": selected_candidate.source_kind,
        "controlling_ratio": selected_ratio,
        "section_selection_ratio": selected_ratio,
        "ratio_basis": "evaluation_summary.json:Chapter 6.1 structural member ratios",
        "historical_controlling_ratio": selected_ratio,
        "status": "pass",
        "run_status": "formal_validation_pending",
        "result_gate_status": "formal_validation_pending",
        "validation_status": "formal_validation_pending",
        "failed_non_ratio_checks": [],
        "dominant_check_id": selected_history.get("dominant_check_id"),
        "dominant_component": selected_history.get("dominant_component"),
        "source_ref": "square_section_selection_cache.json:selected_section_hint",
        "formal_validation_required": True,
    }
    return {
        "status": "pass",
        "selected": selected_payload,
        "candidate_results": [selected_payload],
        "selection_validation_mode": "learned_formal_validation",
        "learned_formal_validation": {
            "status": "applied",
            "similarity_score": score,
            "similarity_threshold": LEARNED_FORMAL_VALIDATION_THRESHOLD,
            "selected_section_hint": selected_section,
            "historical_selected_ratio": selected_ratio,
            "lower_economy_check": lower_failure_audit,
            "source_job_dir": similar_hint.get("source_job_dir"),
            "cache_key": similar_hint.get("cache_key"),
            "policy": (
                "High-similarity learned evidence may apply the section directly to the formal job, but it never "
                "reuses historical results. The current formal ANSYS run and deterministic Chapter 6 evaluation "
                "remain the only publishable result. When the learned ratio is 0.60-0.75, the immediate lower "
                "allowed section must already have a successful historical ANSYS over-limit result; otherwise the "
                "normal one-step economy downshift trial is still run."
            ),
        },
        "policy": (
            "Use a high-similarity learned section only as the current formal validation section. "
            "No historical result is reused; if the formal run exceeds ratio 1.0, the normal upgrade/reselection "
            "workflow remains mandatory."
        ),
    }


def square_section_auto_selection_required(job_dir: Path | str) -> bool:
    job_dir = Path(job_dir)
    payload = _read_json(job_dir / "input.json")
    metadata = payload.get("metadata") or {}
    return metadata.get("square_section_selection_status") == "auto_selection_required"


def reset_square_section_selection_for_reselection(
    job_dir: Path | str,
    *,
    reason: str,
) -> dict[str, Any]:
    """Reset job-local selection state before an audited clean reselection.

    A final Chapter 6 ratio mismatch means the previous trial evidence is not
    traceable enough to publish. The next action is to rerun the same audited
    selection workflow from a clean state, not to let stale
    ``auto_selected_by_real_ansys`` metadata skip selection.
    """

    job_dir = Path(job_dir)
    input_path = job_dir / "input.json"
    payload = _read_json(input_path)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    reset_keys = {
        "square_section_selection_status",
        "square_section_selected",
        "square_section_selected_ratio",
        "square_section_selection_policy",
        "square_section_selection_source",
        "square_section_outer_mm",
        "square_section_thickness_mm",
    }
    previous = {
        "metadata": {key: metadata.get(key) for key in sorted(reset_keys) if key in metadata},
        "support": {
            key: support.get(key)
            for key in ("support_section_id", "square_tube_width_m")
            if key in support
        },
    }
    for key in reset_keys:
        metadata.pop(key, None)
    metadata["square_section_selection_status"] = "auto_selection_required"
    payload["metadata"] = metadata
    payload["support"] = support
    _write_json(input_path, payload)
    audit = {
        "status": "pass",
        "reason": reason,
        "previous": previous,
        "new_status": "auto_selection_required",
        "source_ref": "result_validation.square_section_trial_final_ratio_mismatch",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(job_dir / "square_section_reselection_reset.json", audit)
    return audit


def result_validation_needs_square_section_upgrade(job_dir: Path | str) -> bool:
    job_path = Path(job_dir)
    validation_path = job_path / "result_validation.json"
    if not validation_path.exists():
        return False
    try:
        validation = _read_json(validation_path)
    except json.JSONDecodeError:
        return False
    if validation.get("status") == "pass":
        return False
    for check in validation.get("checks") or []:
        if check.get("check_id") == "evaluation_ratio_limit" and check.get("status") == "fail":
            evidence = check.get("evidence") or []
            section_ratio_failed = any(
                is_section_selection_evaluation_row(item) for item in evidence if isinstance(item, dict)
            )
            if section_ratio_failed:
                return True
    return False


def result_validation_needs_square_section_clean_reselection(job_dir: Path | str) -> bool:
    """Return True when the selected-section trial is not traceable to Chapter 6.

    This is intentionally separate from an "upgrade" decision. A trial/final
    ratio mismatch usually means stale generated files, stale selection JSON, or
    a trial-vs-formal extraction mismatch. The correct response is a clean
    reselection and formal rerun, not blindly moving to a larger square tube.
    """

    validation_path = Path(job_dir) / "result_validation.json"
    if not validation_path.exists():
        return False
    try:
        validation = _read_json(validation_path)
    except json.JSONDecodeError:
        return False
    if validation.get("status") == "pass":
        return False
    clean_reselection_checks = {
        "square_section_trial_final_ratio_mismatch",
        "square_section_trial_ratio_missing",
        "square_section_final_ratio_missing",
    }
    for check in validation.get("checks") or []:
        if check.get("status") == "fail" and check.get("check_id") in clean_reselection_checks:
            return True
    return False


def _failed_evaluation_ratio(job_dir: Path | str, *, square_support_only: bool = False, section_selection_only: bool = False) -> float | None:
    validation_path = Path(job_dir) / "result_validation.json"
    if not validation_path.exists():
        return None
    try:
        validation = _read_json(validation_path)
    except json.JSONDecodeError:
        return None
    ratios: list[float] = []
    for check in validation.get("checks") or []:
        if check.get("check_id") != "evaluation_ratio_limit" or check.get("status") != "fail":
            continue
        for item in check.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            if square_support_only and "square_support" not in str(item.get("check_id") or ""):
                continue
            if section_selection_only and not is_section_selection_evaluation_row(item):
                continue
            try:
                ratios.append(float(item.get("ratio")))
            except (TypeError, ValueError):
                continue
    return max(ratios) if ratios else None


def _failed_square_support_ratio(job_dir: Path | str) -> float | None:
    return _failed_evaluation_ratio(job_dir, square_support_only=True)


def _failed_section_selection_ratio(job_dir: Path | str) -> float | None:
    return _failed_evaluation_ratio(job_dir, section_selection_only=True)


def _trial_root(job_dir: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return job_dir.parent / "_square_section_trials" / job_dir.name / stamp


def _section_trial_config(config: AnsysLocalConfig) -> AnsysLocalConfig:
    """Use production-safe ANSYS watchdogs for square-section trials.

    Candidate trials are not publishable results, but they still must run long
    enough to produce deterministic APDL/PIP outputs.  A too-short local
    timeout turns a valid section into a false "missing source outputs" failure
    on slower unit-site machines.
    """

    cloned = config.model_copy(deep=True) if hasattr(config, "model_copy") else config.copy(deep=True)
    cloned.ansys.timeout_minutes = max(
        int(cloned.ansys.timeout_minutes or MIN_REAL_RUN_TIMEOUT_MINUTES),
        MIN_REAL_RUN_TIMEOUT_MINUTES,
    )
    cloned.ansys.startup_no_output_timeout_seconds = max(
        int(cloned.ansys.startup_no_output_timeout_seconds or MIN_REAL_RUN_STARTUP_NO_OUTPUT_TIMEOUT_SECONDS),
        MIN_REAL_RUN_STARTUP_NO_OUTPUT_TIMEOUT_SECONDS,
    )
    cloned.ansys.output_stall_timeout_seconds = 0
    return cloned


def _candidate_window_around_preferred(
    candidates: list,
    preferred_section: str | None,
    *,
    lower_count: int = 0,
    upper_count: int = 2,
) -> tuple[list, dict[str, Any]]:
    if not preferred_section:
        return candidates, {"status": "skipped", "reason": "no preferred section"}
    index = next((idx for idx, item in enumerate(candidates) if item.section_name == preferred_section), None)
    if index is None:
        return candidates, {
            "status": "skipped",
            "reason": "preferred section not in candidate catalog",
            "preferred_section": preferred_section,
        }
    start = max(0, index - max(0, int(lower_count)))
    end = min(len(candidates), index + max(0, int(upper_count)) + 1)
    window = candidates[start:end]
    return window, {
        "status": "applied",
        "preferred_section": preferred_section,
        "start_index": start,
        "end_index_exclusive": end,
        "candidate_count_before": len(candidates),
        "candidate_count_after": len(window),
        "candidate_sections": [item.section_name for item in window],
        "policy": (
            "High-similarity historical intake is used only to narrow the first candidate window. "
            "Every candidate in the window still runs ANSYS and must pass deterministic ratio gates; "
            "a failed window falls back to the full reviewed section catalog unless the failure is a source/post-processing blocker."
        ),
    }


def _candidate_by_name(candidates: list[SquareSectionCandidate], section_name: str | None) -> SquareSectionCandidate | None:
    if not section_name:
        return None
    for candidate in candidates:
        if candidate.section_name == section_name:
            return candidate
    return None


def _first_candidate_at_or_above(
    candidates: list[SquareSectionCandidate],
    target: SquareSectionCandidate | None,
) -> SquareSectionCandidate | None:
    if not candidates:
        return None
    if target is None:
        return candidates[0]
    for candidate in candidates:
        if candidate.estimated_bending_section_modulus_mm3 >= target.estimated_bending_section_modulus_mm3:
            return candidate
    return candidates[-1]


def _tray_layer_design_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    tray_layers = _payload_tray_design_layers(payload)
    widths: list[float] = []
    loads: list[float] = []
    for layer in tray_layers:
        width = _layer_width_mm(layer)
        if width is not None:
            widths.append(width)
        load = _layer_load_kg_m(layer)
        if load is not None:
            loads.append(load)
    declared_layers = len(tray_layers) or int(_as_float(support.get("layers_front")) or 0) + int(_as_float(support.get("layers_back")) or 0)
    return {
        "layer_count": declared_layers,
        "max_width_mm": max(widths) if widths else None,
        "tray_load_sum_kg_m": sum(loads) if loads else None,
        "max_line_load_kg_m": max(loads) if loads else None,
        "support_height_m": _as_float(support.get("support_height_m")),
        "support_spacing_m": _as_float(support.get("support_spacing_m")),
    }


def _estimated_square_anchor_from_payload(
    payload: dict[str, Any],
    candidates: list[SquareSectionCandidate],
) -> dict[str, Any] | None:
    """Choose a first plausible section for blank-column-I jobs.

    This is not an acceptance rule.  It only prevents a 5-layer heavy S2 row
    from wasting ANSYS time on small historical sections before the real ratio
    gate is reached.
    """

    if not candidates:
        return None
    metrics = _tray_layer_design_metrics(payload)
    layer_count = int(metrics["layer_count"] or 0)
    max_width = float(metrics["max_width_mm"] or 0.0)
    load_sum = float(metrics["tray_load_sum_kg_m"] or 0.0)
    max_load = float(metrics["max_line_load_kg_m"] or 0.0)
    support_height = float(metrics["support_height_m"] or 0.0)
    score = 0.0
    score += max(0, layer_count - 2) * 0.9
    score += max(0.0, max_width - 400.0) / 140.0
    score += max(0.0, load_sum - 180.0) / 170.0
    score += max(0.0, max_load - 90.0) / 70.0
    score += max(0.0, support_height - 1.0) * 1.2

    if score >= 7.0 or layer_count >= 8 or load_sum >= 760:
        target_name = "140-140-8"
    elif score >= 5.2 or layer_count >= 6 or load_sum >= 560:
        target_name = "120-120-10"
    elif score >= 2.0 or layer_count >= 4 or load_sum >= 360 or max_width >= 500:
        target_name = "100-100-8"
    else:
        target_name = "100-100-6"

    target = _candidate_by_name(candidates, target_name) or parse_square_section_name(target_name)
    selected = _first_candidate_at_or_above(candidates, target)
    if selected is None:
        return None
    return {
        "status": "pass",
        "section_name": selected.section_name,
        "target_section_name": target_name,
        "score": round(score, 6),
        "metrics": metrics,
        "policy": (
            "Blank-column-I candidate search starts from a deterministic engineering anchor based on layer count, "
            "tray width, tray load and support height. This only orders candidates; final acceptability still comes "
            "from real ANSYS + deterministic ratio gates."
        ),
        "source_ref": "square_section_workflow._estimated_square_anchor_from_payload",
    }


def real_ansys_section_trial_runner(
    trial_dir: Path,
    *,
    config: AnsysLocalConfig,
    config_path: Path | str,
    confirm_user: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    cleanup_stale_ansys_locks(trial_dir)
    trial_config = _section_trial_config(config)

    def trial_progress(event: dict[str, Any]) -> None:
        if not progress_callback:
            return
        payload = dict(event)
        payload.setdefault("stage", "select_square_section")
        payload["candidate_section"] = trial_dir.name
        payload["trial_dir"] = str(trial_dir)
        payload["trial_status_file"] = str(trial_dir / "ansys_live_status.json")
        if "elapsed_seconds" in payload:
            payload["message"] = (
                f"Candidate {trial_dir.name} ANSYS running: "
                f"{float(payload.get('elapsed_seconds') or 0.0) / 60.0:.1f} min elapsed, "
                f"{float(payload.get('total_output_bytes') or 0.0) / (1024 * 1024):.1f} MB output."
            )
        progress_callback(payload)

    audit = run_real_ansys(
        trial_dir,
        config=trial_config,
        config_path=config_path,
        confirm_real_run=True,
        confirm_user=confirm_user,
        run_post_exports=False,
        progress_callback=trial_progress,
    )
    if audit.get("status") != "success":
        cleanup_heavy_solver_artifacts(trial_dir)
        return audit
    assemble_result(trial_dir)
    artifact_cleanup = cleanup_heavy_solver_artifacts(trial_dir)
    return {"status": "pass", "ansys_run_audit": audit, "solver_artifact_cleanup": artifact_cleanup}


def apply_selected_square_section(
    job_dir: Path | str,
    selection: dict[str, Any],
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    selected = selection.get("selected") or {}
    section_name = selected.get("section_name")
    if selection.get("status") != "pass" or not section_name:
        raise ValueError("Square section selection did not produce a selected section.")

    replace_audit = replace_square_and_arm_sections_in_model(job_dir, str(section_name), source_root=source_root)
    input_path = job_dir / "input.json"
    payload = _read_json(input_path)
    metadata = payload.get("metadata") or {}
    parsed_square = parse_square_section_name(str(section_name))
    arm_primary, arm_secondary, arm_policy = _arm_sections_for_square_outer(parsed_square.outer_mm if parsed_square else None)
    metadata.update(
        {
            "square_section_selection_status": "auto_selected_by_real_ansys",
            "square_section_selected": section_name,
            "square_section_selected_ratio": selected.get("controlling_ratio"),
            "square_section_selection_policy": selection.get("policy"),
            "square_section_selection_source": "real_ansys_trial_runs",
            "square_section_selection_validation_mode": selection.get("selection_validation_mode") or "candidate_trial_complete",
            "square_section_selection_requires_formal_validation": bool(selected.get("formal_validation_required")),
            "arm_section_family": arm_policy,
        }
    )
    if parsed_square:
        metadata["square_section_outer_mm"] = parsed_square.outer_mm
        metadata["square_section_thickness_mm"] = parsed_square.thickness_mm
    payload["metadata"] = metadata
    if payload.get("sections"):
        payload["sections"][0]["section_id"] = str(section_name).lower()
        payload["sections"][0]["sect_file"] = str(section_name)
        payload["sections"][0]["source_ref"] = "square_section_selection.json"
        sections_by_id = {str(section.get("section_id")): section for section in payload["sections"] if isinstance(section, dict)}
        sections_by_id["arm-main"] = {
            "section_id": "arm-main",
            "sect_file": arm_primary,
            "section_type": "BEAM_MESH",
            "source_ref": arm_policy,
        }
        sections_by_id["arm-secondary"] = {
            "section_id": "arm-secondary",
            "sect_file": arm_secondary,
            "section_type": "BEAM_MESH",
            "source_ref": arm_policy,
        }
        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for section in payload["sections"]:
            section_id = str(section.get("section_id"))
            if section_id in sections_by_id and section_id not in seen:
                ordered.append(sections_by_id[section_id])
                seen.add(section_id)
        for section_id, section in sections_by_id.items():
            if section_id not in seen:
                ordered.append(section)
        payload["sections"] = ordered
    support = payload.get("support") or {}
    support["support_section_id"] = str(section_name).lower()
    if parsed_square:
        support["square_tube_width_m"] = parsed_square.outer_mm / 1000.0
    payload["support"] = support
    _write_json(input_path, payload)
    post_alignment_audit = align_postprocessor_to_intake(job_dir, payload)
    audit = {
        "status": "pass",
        "selection": selection,
        "replace_audit": replace_audit,
        "arm_section_replace_audit": replace_audit.get("arm_section_replace_audit"),
        "postprocessor_alignment_after_section_selection": post_alignment_audit,
    }
    _write_json(job_dir / "square_section_selection_applied.json", audit)
    return audit


def _fallback_square_section_from_input(payload: dict[str, Any], source_root: Path | str) -> str | None:
    sections = payload.get("sections") or []
    for section in sections:
        value = str(section.get("sect_file") or section.get("section_id") or "").strip()
        if (
            parse_square_section_name(value)
            and _section_allowed_by_payload(value, payload)
            and next(Path(source_root).rglob(f"{value}.SECT"), None)
        ):
            return value
    for value in _allowed_square_section_ids_from_payload(payload):
        if _section_allowed_by_payload(value, payload) and next(Path(source_root).rglob(f"{value}.SECT"), None):
            return value
    return None


def _provisional_square_section_from_payload(
    payload: dict[str, Any],
    source_root: Path | str,
) -> dict[str, Any] | None:
    candidates = discover_square_section_candidates(source_root)
    candidates, allowed_filter = _filter_allowed_square_candidates(candidates, payload)
    estimated = _estimated_square_anchor_from_payload(payload, candidates)
    if estimated is not None:
        estimated["allowed_square_section_filter"] = allowed_filter
        return estimated
    fallback = _fallback_square_section_from_input(payload, source_root)
    if not fallback:
        return None
    return {
        "status": "pass",
        "section_name": fallback,
        "target_section_name": fallback,
        "score": None,
        "metrics": _tray_layer_design_metrics(payload),
        "policy": "Fallback to first reviewed input/local square section because no candidate catalog estimate was available.",
        "source_ref": "input.json sections[0].sect_file or local square SECT fallback list",
        "allowed_square_section_filter": allowed_filter,
    }


def select_and_apply_square_section(
    job_dir: Path | str,
    *,
    config: AnsysLocalConfig,
    config_path: Path | str,
    confirm_user: str,
    source_root: Path | str = Path("source_materials/model_commands"),
    limit: int | None = None,
    runner: Callable[[Path], dict[str, Any]] | None = None,
    cache_path: Path | str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    allow_native_hrec_generated: bool = False,
    force_reselect: bool = False,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    input_payload = _read_json(job_dir / "input.json")
    if not square_section_auto_selection_required(job_dir):
        if force_reselect:
            reset_square_section_selection_for_reselection(
                job_dir,
                reason="forced_clean_reselection_after_trial_final_ratio_mismatch",
            )
            input_payload = _read_json(job_dir / "input.json")
        else:
            payload = {
                "status": "skipped",
                "reason": "square_section_selection_status is not auto_selection_required",
            }
            _write_json(job_dir / "square_section_selection.json", payload)
            return payload

    using_default_runner = runner is None
    resolved_cache_path = _selection_cache_path(cache_path)
    if using_default_runner:
        runner = lambda trial_dir: real_ansys_section_trial_runner(  # noqa: E731
            trial_dir,
            config=config,
            config_path=config_path,
            confirm_user=confirm_user,
            progress_callback=progress_callback,
        )

    similar_hint = (
        _read_similar_cached_selection(job_dir, cache_path=resolved_cache_path)
        if using_default_runner or cache_path is not None
        else None
    )
    preferred_section = similar_hint.get("selected_section_hint") if similar_hint else None
    trials = _trial_root(job_dir)
    candidates = discover_square_section_candidates(
        source_root,
        include_native_hrec_generated=allow_native_hrec_generated,
    )
    candidates, allowed_square_section_filter = _filter_allowed_square_candidates(candidates, input_payload)
    if not candidates:
        selection = {
            "status": "fail",
            "selected": None,
            "reason": _allowed_section_insufficient_reason(input_payload, no_catalog=True),
            "candidate_results": [],
            "allowed_square_section_filter": allowed_square_section_filter,
            "production_policy": (
                "Square-section selection is restricted to the intake calculation-note section list. "
                "No unlisted section is allowed, even if a local cache or historical job contains it."
            ),
        }
        _write_json(job_dir / "square_section_selection.json", selection)
        _write_json(
            job_dir / "square_section_trial_summary.json",
            {
                "status": "fail",
                "selected": None,
                "allowed_square_section_filter": allowed_square_section_filter,
                "reason": selection["reason"],
                "trial_root_removed": True,
            },
        )
        return selection
    full_candidates = list(candidates)
    candidate_window_audit: dict[str, Any] = {"status": "skipped", "reason": "no high-similarity cache hit"}
    learned_allowed_start_audit: dict[str, Any] = {
        "status": "skipped",
        "reason": "allowed-list learning not evaluated",
    }
    learned_formal_selection = (
        _learned_formal_validation_selection(
            candidates=full_candidates,
            similar_hint=similar_hint,
            allowed_square_section_filter=allowed_square_section_filter,
        )
        if using_default_runner and not force_reselect
        else None
    )
    if learned_formal_selection is not None:
        learned_formal_selection["allowed_square_section_filter"] = allowed_square_section_filter
        learned_formal_selection["similar_cache_order_hint"] = similar_hint
        learned_formal_selection["trial_root"] = None
        learned_formal_selection["trial_root_removed"] = True
        learned_formal_selection["production_policy"] = (
            "High-similarity learned section hints can skip duplicate candidate trial ANSYS runs only when they stay "
            "inside the current intake allowed-section list. The current formal ANSYS run is still mandatory and is "
            "the only publishable result; final Chapter 6 ratios, figures and LIS/OUP gates remain unchanged."
        )
        apply_audit = apply_selected_square_section(job_dir, learned_formal_selection, source_root=source_root)
        final_payload = {**learned_formal_selection, "apply_audit": apply_audit}
        _write_json(job_dir / "square_section_selection.json", final_payload)
        _write_json(
            job_dir / "square_section_trial_summary.json",
            {
                "status": "pass",
                "selected": final_payload.get("selected"),
                "policy": final_payload.get("policy"),
                "production_policy": final_payload.get("production_policy"),
                "allowed_square_section_filter": allowed_square_section_filter,
                "similar_cache_order_hint": similar_hint,
                "learned_formal_validation": final_payload.get("learned_formal_validation"),
                "candidate_results": final_payload.get("candidate_results"),
                "trial_root_removed": True,
                "trial_root_retention_policy": (
                    "No candidate trial workspace was created because a high-similarity learned section was applied "
                    "only for the current formal ANSYS validation run."
                ),
            },
        )
        if progress_callback:
            progress_callback(
                {
                    "stage": "select_square_section",
                    "message": (
                        f"Using learned section {final_payload['selected']['section_name']} for formal ANSYS validation; "
                        "current formal run will still decide pass/fail."
                    ),
                    "candidate_section": final_payload["selected"]["section_name"],
                    "candidate_index": 1,
                    "candidate_count": 1,
                }
            )
        return final_payload
    similarity_score = None
    if similar_hint is not None:
        try:
            similarity_score = float((similar_hint.get("similarity") or {}).get("score"))
        except (TypeError, ValueError):
            similarity_score = None
    if preferred_section and similarity_score is not None and similarity_score >= 0.82:
        candidates, candidate_window_audit = _candidate_window_around_preferred(
            full_candidates,
            str(preferred_section),
        )
    engineering_anchor = None
    preferred_section_source = "similar_intake_cache" if preferred_section else None
    allowed_filter_applied = allowed_square_section_filter.get("status") == "applied"
    lower_neighbor_count = 0
    if allowed_filter_applied:
        # The calculation note is the governing candidate boundary.  Learning
        # and deterministic estimates may choose the first candidate inside
        # that hard boundary, but they never add unlisted sections and never
        # accept a section without a fresh ANSYS trial.
        _, learned_allowed_start_audit = _learned_allowed_candidate_start(full_candidates, similar_hint)
        if learned_allowed_start_audit.get("status") in {"applied", "not_needed"} and learned_allowed_start_audit.get("selected_section_hint"):
            preferred_section = str(learned_allowed_start_audit["selected_section_hint"])
            preferred_section_source = "learned_allowed_start"
        else:
            engineering_anchor = _estimated_square_anchor_from_payload(input_payload, full_candidates)
            if engineering_anchor:
                preferred_section = str(engineering_anchor["section_name"])
                preferred_section_source = "engineering_estimate_allowed_list"
        candidates = full_candidates
        candidate_window_audit = {
            "status": "skipped",
            "reason": "intake_allowed_sections_use_two_trial_economy_strategy",
            "policy": (
                "For intake calculation-note sections, only listed/reviewed candidates are allowed. "
                "A high-similarity learned cache or deterministic engineering estimate may choose the first trial "
                "inside the current allowed list. If the fresh ratio is outside the 0.60-0.9999 economy band, one "
                "section-modulus correction trial is allowed. The search normally stops within two fresh ANSYS "
                "candidate trials; larger listed sections are not swept after an economic pass."
            ),
        }
    elif preferred_section is None:
        engineering_anchor = _estimated_square_anchor_from_payload(input_payload, full_candidates)
        if engineering_anchor:
            preferred_section = str(engineering_anchor["section_name"])
            preferred_section_source = "engineering_estimate"
    effective_limit = limit
    if allowed_filter_applied:
        # The intake calculation note is the governing candidate boundary.  A
        # first passing section is the economical stop because allowed
        # candidates are sorted by section modulus/area.  After a real failed
        # square-support ratio, smart jumps may avoid obviously under-sized
        # allowed candidates while recording exactly what was skipped.
        effective_limit = None if effective_limit is None else max(int(effective_limit), len(candidates))
    elif effective_limit is None and using_default_runner:
        effective_limit = 4
    selection = run_square_section_search(
        job_dir,
        trials,
        candidates=candidates,
        runner=runner,
        source_root=source_root,
        limit=effective_limit,
        overwrite_trials=True,
        preferred_section=str(preferred_section) if preferred_section else None,
        preferred_section_source=preferred_section_source,
        stop_after_first_feasible=True,
        feasible_confirmation_count=1,
        smart_jumps_enabled=True,
        smart_order=True,
        lower_neighbor_count=lower_neighbor_count,
        max_evaluated_candidates=2,
        progress_callback=progress_callback,
    )
    if engineering_anchor is not None:
        selection["engineering_candidate_anchor"] = engineering_anchor
    selection["allowed_square_section_filter"] = allowed_square_section_filter
    selection["learned_allowed_section_start"] = learned_allowed_start_audit
    if candidate_window_audit.get("status") == "applied":
        selection["similar_cache_candidate_window"] = candidate_window_audit
        if selection.get("status") != "pass" and not selection.get("early_stop"):
            expanded_trials = trials.with_name(f"{trials.name}_expanded")
            expanded = run_square_section_search(
                job_dir,
                expanded_trials,
                candidates=full_candidates,
                runner=runner,
                source_root=source_root,
                limit=effective_limit,
                overwrite_trials=True,
                preferred_section=str(preferred_section),
                preferred_section_source=preferred_section_source,
                stop_after_first_feasible=True,
                feasible_confirmation_count=1,
                smart_jumps_enabled=True,
                smart_order=True,
                lower_neighbor_count=lower_neighbor_count,
                max_evaluated_candidates=2,
                progress_callback=progress_callback,
            )
            expanded["similar_cache_candidate_window"] = {
                **candidate_window_audit,
                "fallback_full_search": "used",
                "first_window_status": selection.get("status"),
                "expanded_trial_root": str(expanded_trials),
            }
            trials = expanded_trials
            selection = expanded
            selection["allowed_square_section_filter"] = allowed_square_section_filter
            selection["learned_allowed_section_start"] = learned_allowed_start_audit
    if similar_hint is not None:
        selection["similar_cache_order_hint"] = similar_hint
    timeout_statuses = {
        str(item.get("run_status"))
        for item in selection.get("candidate_results", [])
        if isinstance(item, dict)
        and str(item.get("run_status"))
        in {"timeout", "startup_no_output_timeout", "output_stall_timeout"}
    }
    if timeout_statuses and selection.get("status") != "pass":
        selection["timeout_policy"] = {
            "status": "blocked",
            "detected_run_statuses": sorted(timeout_statuses),
            "policy": (
                "Candidate ANSYS timeouts are runtime failures, not section-ratio failures. "
                "The row keeps the ANSYS evidence and must be rerun after fixing timeout/output-stall conditions; "
                "the production runner applies code-level minimum watchdogs to avoid stale unit-site local configs."
            ),
        }
    selection["trial_root"] = str(trials)
    selection["production_policy"] = (
        "Future intake rows may omit column I square tube size. In that case, square-section candidates must come "
        "from the intake calculation-note allowed list and are evaluated by fresh real ANSYS output and deterministic "
        "ratios; the selected section must have ratio <= 1.0 within that intake-allowed list. The production economy band is "
        "0.60 <= ratio <= 0.9999, and section selection normally completes within two fresh ANSYS candidate trials: "
        "one learned/estimated first trial plus one section-modulus correction if needed. Candidate order may not use "
        "local catalog fallback or historical results to add unlisted candidates or accept a section without current "
        "ANSYS evidence. Generated APDL HREC candidates are disabled by default and only allowed when "
        "allow_native_hrec_generated=true is explicitly set for a reviewed engineering run. No nearest-report-value "
        "substitution is allowed."
    )
    selection["allow_native_hrec_generated"] = allow_native_hrec_generated
    if (
        selection.get("status") != "pass"
        and allowed_square_section_filter.get("status") == "applied"
        and not selection.get("early_stop")
    ):
        selection["reason"] = _allowed_section_insufficient_reason(input_payload)
    trial_summary = {
        "status": selection.get("status"),
        "selected": selection.get("selected"),
        "policy": selection.get("policy"),
        "production_policy": selection["production_policy"],
        "allowed_square_section_filter": allowed_square_section_filter,
        "similar_cache_order_hint": selection.get("similar_cache_order_hint"),
        "learned_allowed_section_start": selection.get("learned_allowed_section_start"),
        "candidate_results": [
            {key: value for key, value in item.items() if key != "trial_dir"}
            for item in selection.get("candidate_results", [])
            if isinstance(item, dict)
        ],
        "trial_root_removed": False,
        "trial_refresh_policy": selection.get("trial_refresh_policy"),
        "overwrite_trials": selection.get("overwrite_trials"),
    }
    _write_json(job_dir / "square_section_selection.json", selection)
    if selection.get("status") != "pass":
        trial_summary["early_stop"] = selection.get("early_stop")
        _write_json(job_dir / "square_section_trial_summary.json", trial_summary)
        return selection

    apply_audit = apply_selected_square_section(job_dir, selection, source_root=source_root)
    final_payload = {**selection, "apply_audit": apply_audit}
    _write_json(job_dir / "square_section_selection.json", final_payload)
    if using_default_runner:
        _write_cached_selection(job_dir, final_payload, cache_path=resolved_cache_path)
    trial_summary["trial_root_removed"] = False
    trial_summary["trial_root_retention_policy"] = (
        "Candidate ANSYS workspaces are retained after selection so unit-site stalls or ratio decisions can be audited. "
        "Heavy solver artifacts are cleaned inside each trial, but command streams, live status, out/err logs, LIS/OUP, "
        "result JSON and evaluation summaries remain available under trial_root."
    )
    _write_json(job_dir / "square_section_trial_summary.json", trial_summary)
    return final_payload


def upgrade_square_section_after_ratio_fail(
    job_dir: Path | str,
    *,
    config: AnsysLocalConfig,
    config_path: Path | str,
    confirm_user: str,
    source_root: Path | str = Path("source_materials/model_commands"),
    limit: int | None = None,
    runner: Callable[[Path], dict[str, Any]] | None = None,
    allow_native_hrec_generated: bool = False,
) -> dict[str, Any]:
    """Select a larger square tube when the final deterministic ratio gate fails."""

    job_dir = Path(job_dir)
    if not result_validation_needs_square_section_upgrade(job_dir):
        payload = {"status": "skipped", "reason": "result_validation does not require square-section upgrade"}
        _write_json(job_dir / "square_section_upgrade_after_ratio_fail.json", payload)
        return payload

    input_payload = _read_json(job_dir / "input.json")
    metadata = input_payload.get("metadata") or {}
    current_name = (
        metadata.get("square_section_selected")
        or metadata.get("square_section_spec")
        or (input_payload.get("sections") or [{}])[0].get("sect_file")
        or (input_payload.get("sections") or [{}])[0].get("section_id")
    )
    current = parse_square_section_name(str(current_name or ""))
    current_modulus = current.estimated_bending_section_modulus_mm3 if current else -1.0
    candidates = [
        candidate
        for candidate in discover_square_section_candidates(
            source_root,
            include_native_hrec_generated=allow_native_hrec_generated,
        )
        if candidate.estimated_bending_section_modulus_mm3 > current_modulus
    ]
    candidates, allowed_square_section_filter = _filter_allowed_square_candidates(candidates, input_payload)
    allowed_filter_applied = allowed_square_section_filter.get("status") == "applied"
    failed_ratio = _failed_section_selection_ratio(job_dir) or _failed_square_support_ratio(job_dir)
    estimated_required_modulus = None
    skipped_by_estimate = 0
    if not allowed_filter_applied and failed_ratio and failed_ratio > 1.0 and current_modulus > 0:
        estimated_required_modulus = current_modulus * failed_ratio * 0.92
        lower_candidates = [
            candidate
            for candidate in candidates
            if candidate.estimated_bending_section_modulus_mm3 < estimated_required_modulus
        ]
        upper_candidates = [
            candidate
            for candidate in candidates
            if candidate.estimated_bending_section_modulus_mm3 >= estimated_required_modulus
        ]
        # Keep one below the estimate as a trend guard, then jump to plausible candidates.
        candidates = (lower_candidates[-1:] if lower_candidates else []) + upper_candidates
        skipped_by_estimate = max(0, len(lower_candidates) - (1 if lower_candidates else 0))
    if limit is not None and allowed_filter_applied:
        limit = max(int(limit), len(candidates))
    if limit is not None:
        candidates = candidates[:limit]
    if not candidates:
        if allowed_square_section_filter.get("status") == "applied":
            reason = _allowed_section_insufficient_reason(input_payload, no_catalog=True)
        elif allowed_square_section_filter.get("status") == "missing_required":
            reason = _allowed_section_insufficient_reason(input_payload)
        elif not allow_native_hrec_generated:
            reason = (
                "No reviewed square-tube SECT candidate satisfied ratio <= 1.0; "
                "generated APDL HREC candidates are disabled by default."
            )
        else:
            reason = _allowed_section_insufficient_reason(input_payload, no_catalog=True)
        payload = {
            "status": "fail",
            "reason": reason,
            "current_section": current_name,
            "current_estimated_bending_section_modulus_mm3": current_modulus,
            "allow_native_hrec_generated": allow_native_hrec_generated,
            "allowed_square_section_filter": allowed_square_section_filter,
        }
        _write_json(job_dir / "square_section_upgrade_after_ratio_fail.json", payload)
        return payload

    if runner is None:
        runner = lambda trial_dir: real_ansys_section_trial_runner(  # noqa: E731
            trial_dir,
            config=config,
            config_path=config_path,
            confirm_user=confirm_user,
            progress_callback=None,
        )
    trials = job_dir.parent / "_square_section_upgrade_trials" / job_dir.name / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    selection = run_square_section_search(
        job_dir,
        trials,
        candidates=candidates,
        runner=runner,
        source_root=source_root,
        overwrite_trials=True,
        stop_after_first_feasible=True,
        feasible_confirmation_count=1,
        smart_jumps_enabled=not bool(estimated_required_modulus),
        smart_order=allowed_square_section_filter.get("status") != "applied",
        max_evaluated_candidates=2,
    )
    selection["upgrade_reason"] = "Final deterministic evaluation ratio exceeded 1.0 for the current square tube."
    selection["current_section"] = current_name
    selection["allowed_square_section_filter"] = allowed_square_section_filter
    selection["candidate_prefilter"] = {
        "status": "applied" if estimated_required_modulus else "skipped",
        "failed_ratio": failed_ratio,
        "current_estimated_bending_section_modulus_mm3": current_modulus,
        "estimated_required_bending_section_modulus_mm3": estimated_required_modulus,
        "skipped_candidate_count": skipped_by_estimate,
        "policy": (
            "The filter only avoids candidates whose square-tube bending section modulus is far below the modulus "
            "implied by the failed real-ANSYS ratio. One lower trend candidate is still run; final acceptance remains "
            "a real-ANSYS deterministic ratio <= 1.0."
        ),
    }
    selection["production_policy"] = (
        "A provided or provisional square tube section is not accepted when final real-ANSYS deterministic ratios exceed 1.0. "
        "Only intake-allowed/reviewed local SECT candidates are tried by default. Generated job-local APDL HREC candidates are allowed "
        "only when allow_native_hrec_generated=true is set for a reviewed engineering run; selected section must still "
        "have ratio <= 1.0. Upgrade selection uses the same bounded economy policy: target 0.60 <= ratio <= 0.9999 "
        "within no more than two fresh ANSYS candidate trials, without sweeping larger sections after an economic pass."
    )
    if (
        selection.get("status") != "pass"
        and allowed_square_section_filter.get("status") == "applied"
        and not selection.get("early_stop")
    ):
        selection["reason"] = _allowed_section_insufficient_reason(input_payload)
    elif (
        selection.get("status") != "pass"
        and allowed_square_section_filter.get("status") == "missing_required"
        and not selection.get("early_stop")
    ):
        selection["reason"] = _allowed_section_insufficient_reason(input_payload)
    elif (
        selection.get("status") != "pass"
        and allowed_square_section_filter.get("status") != "applied"
        and not allow_native_hrec_generated
        and not selection.get("early_stop")
    ):
        selection["reason"] = (
            "No reviewed square-tube SECT candidate satisfied ratio <= 1.0; "
            "generated APDL HREC candidates are disabled by default."
        )
    if selection.get("status") != "pass":
        selection["trial_root_removed"] = False
        selection["trial_root_retention_policy"] = (
            "Failed square-section upgrade trial workspaces are retained so unit-site runtime failures can be diagnosed "
            "from command streams, live status, out/err logs and LIS/OUP files. Heavy solver artifacts are cleaned inside "
            "each trial by the ANSYS trial runner."
        )
        _write_json(job_dir / "square_section_upgrade_after_ratio_fail.json", selection)
        return selection

    apply_audit = apply_selected_square_section(job_dir, selection, source_root=source_root)
    final_payload = {**selection, "apply_audit": apply_audit}
    final_payload["trial_root_removed"] = False
    final_payload["trial_root_retention_policy"] = (
        "Successful square-section upgrade trial workspaces are retained as lightweight audit evidence. "
        "The formal selected job remains the publishable result, while trial logs explain the section decision."
    )
    final_payload["selection_validation_mode"] = "upgrade_after_final_ratio_fail"
    final_payload["job_state_after_upgrade"] = update_job_state(
        job_dir,
        "apdl_rendered",
        "square-section upgrade applied; formal ANSYS rerun is allowed",
    )
    _write_json(job_dir / "square_section_selection.json", final_payload)
    _write_json(job_dir / "square_section_upgrade_after_ratio_fail.json", final_payload)
    return final_payload


def copy_selected_trial_outputs(job_dir: Path | str, selection: dict[str, Any]) -> dict[str, Any]:
    job_dir = Path(job_dir)
    selected = selection.get("selected") or {}
    trial_value = selected.get("trial_dir")
    if not trial_value:
        return {"status": "skipped", "reason": "selected trial directory is not recorded"}
    trial_dir = Path(str(trial_value))
    if not trial_dir.exists():
        return {"status": "skipped", "reason": "selected trial directory does not exist"}
    copied: list[str] = []
    for name in ("evaluation_summary.json", "result.json", "result_raw.json"):
        source = trial_dir / name
        if source.exists():
            target = job_dir / f"selected_section_trial_{name}"
            shutil.copy2(source, target)
            copied.append(target.name)
    return {"status": "pass" if copied else "warning", "copied": copied}
