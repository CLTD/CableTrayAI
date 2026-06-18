from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODAL_CUTOFF_HZ = 50.0
DEFAULT_MODAL_MODE_COUNT = 40
MIN_MODAL_MODE_COUNT = 1
MAX_INITIAL_MODAL_MODE_COUNT = 160
SAFE_SOURCE_MODAL_MODE_COUNT_LIMIT = 160
MAX_AUDITED_SOURCE_MODAL_MODE_COUNT = 1200
MODAL_RETRY_SEQUENCE = (20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 140, 160, 200, 240)
MODAL_MODE_COUNT_CACHE_VERSION = "modal-mode-count-cache-v1"
MODAL_MODE_COUNT_CACHE_PATH = Path("data/calibration/modal_mode_count_cache.json")
MODAL_LEARNING_SIMILARITY_THRESHOLD = 0.78
MODAL_LEARNING_MODE_MARGIN = 4
AUTO_MODAL_MODE_COUNT_SOURCES = {
    "intake_rule_layer_count_modal_count",
    "learned_similar_intake_modal_cache",
    "inferred_layer_count",
    "modal_policy",
    "default_initial_count",
}
LEARNED_MODAL_MODE_COUNT_SOURCES = {
    "learned_similar_intake_modal_cache",
}
INITIAL_MODAL_MODE_COUNT_BY_LAYER_COUNT = {
    1: 20,
    2: 40,
    3: 50,
    4: 60,
    5: 70,
    6: 80,
    7: 90,
}


def _as_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def parse_source_modal_mode_count(text: str | None) -> int | None:
    source_text = text or ""
    explicit_mt_counts = [
        int(match.group(1)) for match in re.finditer(r"(?im)^\s*MT\s*=\s*(\d+)\b", source_text)
    ]
    if explicit_mt_counts:
        return max(explicit_mt_counts)

    literal_modopt_counts = [
        int(match.group(1))
        for match in re.finditer(r"(?im)^\s*MODOPT\s*,\s*LANB\s*,\s*(\d+)\b", source_text)
    ]
    return max(literal_modopt_counts) if literal_modopt_counts else None


def coerce_modal_mode_count(value: Any, *, minimum: int = MIN_MODAL_MODE_COUNT) -> int:
    parsed = _as_positive_int(value)
    if parsed is None:
        return DEFAULT_MODAL_MODE_COUNT
    return max(parsed, minimum)


def coerce_initial_modal_mode_count(value: Any) -> int:
    return min(coerce_modal_mode_count(value), MAX_INITIAL_MODAL_MODE_COUNT)


def modal_mode_count_from_layer_count(layer_count: Any) -> int:
    """Estimate the first-run modal extraction count from explicit tray layers.

    The first run should be close to the 50 Hz coverage gate, not a broad
    production maximum.  Source command streams and explicit metadata are
    preferred when present; this layer rule is only the fallback for new rows
    without a usable MT/MODOPT count.  The post-run Mode.oup gate owns the final
    decision and retries upward only when the first solve is short.
    """
    try:
        count = int(float(str(layer_count).strip()))
    except (TypeError, ValueError):
        count = 0
    if count <= 0:
        return DEFAULT_MODAL_MODE_COUNT
    if count in INITIAL_MODAL_MODE_COUNT_BY_LAYER_COUNT:
        return coerce_initial_modal_mode_count(INITIAL_MODAL_MODE_COUNT_BY_LAYER_COUNT[count])
    estimate = 20 + 15 * count
    for value in MODAL_RETRY_SEQUENCE:
        if int(value) >= estimate:
            return coerce_initial_modal_mode_count(value)
    return MAX_INITIAL_MODAL_MODE_COUNT


def _infer_layer_count_from_payload(payload: dict[str, Any] | None) -> int | None:
    """Infer vertical tray level count from normalized intake payload fields.

    For double-sided supports, modal MT tracks the number of vertical levels,
    not the total number of tray runs.  A 5+5 double-sided row is therefore
    treated as five levels, not ten.
    """

    data = payload or {}
    support = data.get("support") if isinstance(data.get("support"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

    candidate_values: list[Any] = [
        support.get("total_layers"),
        metadata.get("total_layers"),
        metadata.get("tray_layer_count"),
        metadata.get("layer_count"),
    ]
    side_count_values = [
        support.get("layers_front"),
        support.get("layers_back"),
        support.get("layers_third"),
        metadata.get("layers_front"),
        metadata.get("layers_back"),
        metadata.get("layers_third"),
    ]
    parsed_sides = [_as_positive_int(value) or 0 for value in side_count_values]
    if any(parsed_sides):
        candidate_values.append(max(parsed_sides))

    tray_layers = data.get("tray_layers")
    if isinstance(tray_layers, list) and tray_layers:
        by_side = [
            _as_positive_int(item.get("layer_index"))
            for item in tray_layers
            if isinstance(item, dict)
        ]
        by_side = [value for value in by_side if value is not None]
        candidate_values.append(max(by_side) if by_side else len(tray_layers))

    tray_mapping = metadata.get("tray_load_mapping")
    if isinstance(tray_mapping, dict):
        layers = tray_mapping.get("layers")
        if isinstance(layers, list) and layers:
            by_side = [
                _as_positive_int(item.get("layer_index"))
                for item in layers
                if isinstance(item, dict)
            ]
            by_side = [value for value in by_side if value is not None]
            candidate_values.append(max(by_side) if by_side else len(layers))
        mapping_sides = [
            tray_mapping.get("front_layers"),
            tray_mapping.get("back_layers"),
            tray_mapping.get("third_layers"),
        ]
        parsed_mapping_sides = [_as_positive_int(value) or 0 for value in mapping_sides]
        if any(parsed_mapping_sides):
            candidate_values.append(max(parsed_mapping_sides))

    parsed = [_as_positive_int(value) for value in candidate_values]
    parsed = [value for value in parsed if value is not None]
    return max(parsed) if parsed else None


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _round_float(value: Any, digits: int = 3) -> float | None:
    parsed = _as_float(value)
    return round(parsed, digits) if parsed is not None else None


def _section_from_payload(payload: dict[str, Any] | None) -> dict[str, float | str | None]:
    data = payload or {}
    support = data.get("support") if isinstance(data.get("support"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    outer = _round_float(metadata.get("square_section_outer_mm"), 2)
    thickness = _round_float(metadata.get("square_section_thickness_mm"), 2)
    raw = (
        metadata.get("square_section_selected")
        or metadata.get("square_section_current_model_spec")
        or metadata.get("square_section_spec")
        or support.get("support_section_id")
        or ""
    )
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)[-xX*](?:\1)[-xX*](\d+(?:\.\d+)?)\s*", str(raw))
    if match:
        outer = outer if outer is not None else round(float(match.group(1)), 2)
        thickness = thickness if thickness is not None else round(float(match.group(2)), 2)
    return {"raw": str(raw) if raw else None, "outer_mm": outer, "thickness_mm": thickness}


def _tray_width_m_from_layer(layer: dict[str, Any]) -> float | None:
    width_m = _round_float(layer.get("tray_width_m"), 3)
    if width_m is not None:
        return width_m
    width_mm = _as_float(layer.get("tray_width_mm") or layer.get("width_mm"))
    return round(width_mm / 1000.0, 3) if width_mm is not None else None


def _modal_learning_features(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = payload or {}
    support = data.get("support") if isinstance(data.get("support"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    tray_layers = data.get("tray_layers") if isinstance(data.get("tray_layers"), list) else []
    section = _section_from_payload(data)
    return {
        "analysis_method": str(metadata.get("analysis_method") or "response_spectrum").lower(),
        "support_type": str(support.get("support_type") or "").upper(),
        "layer_count": _infer_layer_count_from_payload(data),
        "side_count": _as_positive_int(support.get("side_count") or metadata.get("topology_side_count")),
        "layers_front": _as_positive_int(support.get("layers_front") or metadata.get("layers_front")),
        "layers_back": _as_positive_int(support.get("layers_back") or metadata.get("layers_back")),
        "layers_third": _as_positive_int(support.get("layers_third") or metadata.get("layers_third")) or 0,
        "support_spacing_m": _round_float(support.get("support_spacing_m"), 3),
        "support_height_m": _round_float(support.get("support_height_m"), 3),
        "square_outer_mm": section["outer_mm"],
        "square_thickness_mm": section["thickness_mm"],
        "tray_widths_m": [
            _tray_width_m_from_layer(layer)
            for layer in tray_layers
            if isinstance(layer, dict)
        ],
        "tray_arm_lengths_m": [
            _round_float(layer.get("arm_a_length_m"), 3)
            for layer in tray_layers
            if isinstance(layer, dict)
        ],
    }


def _modal_feature_cache_key(features: dict[str, Any]) -> str:
    payload = json.dumps(features, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _numeric_similarity(left: Any, right: Any, tolerance: float) -> float:
    left_value = _as_float(left)
    right_value = _as_float(right)
    if left_value is None and right_value is None:
        return 0.5
    if left_value is None or right_value is None:
        return 0.0
    if tolerance <= 0:
        return 1.0 if left_value == right_value else 0.0
    return max(0.0, 1.0 - abs(left_value - right_value) / tolerance)


def _exact_similarity(left: Any, right: Any) -> float:
    if left in (None, "") and right in (None, ""):
        return 0.5
    return 1.0 if left == right else 0.0


def _sequence_similarity(left: Any, right: Any, tolerance: float) -> float:
    left_values = [_as_float(value) for value in (left or [])]
    right_values = [_as_float(value) for value in (right or [])]
    left_values = [value for value in left_values if value is not None]
    right_values = [value for value in right_values if value is not None]
    if not left_values and not right_values:
        return 0.5
    if not left_values or not right_values:
        return 0.0
    if len(left_values) != len(right_values):
        count_score = max(0.0, 1.0 - abs(len(left_values) - len(right_values)) / max(len(left_values), len(right_values)))
    else:
        count_score = 1.0
    pair_count = min(len(left_values), len(right_values))
    if pair_count == 0:
        return 0.0
    pair_scores = [
        _numeric_similarity(left_values[index], right_values[index], tolerance)
        for index in range(pair_count)
    ]
    return 0.35 * count_score + 0.65 * (sum(pair_scores) / len(pair_scores))


def _modal_feature_similarity(current: dict[str, Any], learned: dict[str, Any]) -> float:
    weighted_scores = [
        (0.10, _exact_similarity(current.get("analysis_method"), learned.get("analysis_method"))),
        (0.12, _exact_similarity(current.get("support_type"), learned.get("support_type"))),
        (0.16, _numeric_similarity(current.get("layer_count"), learned.get("layer_count"), 1.0)),
        (0.08, _numeric_similarity(current.get("side_count"), learned.get("side_count"), 1.0)),
        (0.07, _numeric_similarity(current.get("layers_front"), learned.get("layers_front"), 1.0)),
        (0.07, _numeric_similarity(current.get("layers_back"), learned.get("layers_back"), 1.0)),
        (0.08, _numeric_similarity(current.get("support_spacing_m"), learned.get("support_spacing_m"), 0.75)),
        (0.08, _numeric_similarity(current.get("support_height_m"), learned.get("support_height_m"), 0.75)),
        (0.08, _numeric_similarity(current.get("square_outer_mm"), learned.get("square_outer_mm"), 40.0)),
        (0.04, _numeric_similarity(current.get("square_thickness_mm"), learned.get("square_thickness_mm"), 4.0)),
        (0.15, _sequence_similarity(current.get("tray_widths_m"), learned.get("tray_widths_m"), 0.25)),
        (0.07, _sequence_similarity(current.get("tray_arm_lengths_m"), learned.get("tray_arm_lengths_m"), 0.25)),
    ]
    weight_sum = sum(weight for weight, _ in weighted_scores)
    return sum(weight * score for weight, score in weighted_scores) / weight_sum


def _read_modal_cache(cache_path: Path | str = MODAL_MODE_COUNT_CACHE_PATH) -> dict[str, Any]:
    path = Path(cache_path)
    if not path.exists():
        return {"cache_version": MODAL_MODE_COUNT_CACHE_VERSION, "entries": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"cache_version": MODAL_MODE_COUNT_CACHE_VERSION, "entries": []}
    if not isinstance(payload, dict):
        return {"cache_version": MODAL_MODE_COUNT_CACHE_VERSION, "entries": []}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        payload["entries"] = []
    payload.setdefault("cache_version", MODAL_MODE_COUNT_CACHE_VERSION)
    return payload


def _write_modal_cache(payload: dict[str, Any], cache_path: Path | str = MODAL_MODE_COUNT_CACHE_PATH) -> None:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["cache_version"] = MODAL_MODE_COUNT_CACHE_VERSION
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_modal_retry_value(minimum: int) -> int:
    for value in MODAL_RETRY_SEQUENCE:
        if int(value) >= minimum:
            return coerce_modal_mode_count(value)
    return coerce_modal_mode_count(minimum)


def learned_modal_mode_count_from_payload(
    payload: dict[str, Any] | None,
    *,
    cache_path: Path | str = MODAL_MODE_COUNT_CACHE_PATH,
    threshold: float = MODAL_LEARNING_SIMILARITY_THRESHOLD,
) -> dict[str, Any]:
    metadata = (payload or {}).get("metadata") if isinstance(payload, dict) else {}
    if str((metadata or {}).get("analysis_method") or "").strip().lower() == "static":
        return {
            "status": "not_required",
            "reason": "static_method_has_no_modal_mt_learning",
        }
    features = _modal_learning_features(payload)
    cache = _read_modal_cache(cache_path)
    best: dict[str, Any] | None = None
    best_score = -1.0
    for entry in cache.get("entries") or []:
        if not isinstance(entry, dict) or entry.get("status") != "pass":
            continue
        count = _as_positive_int(entry.get("recommended_modal_mode_count"))
        if count is None:
            continue
        entry_features = entry.get("similarity_features")
        if not isinstance(entry_features, dict):
            continue
        score = _modal_feature_similarity(features, entry_features)
        if score > best_score:
            best_score = score
            best = entry
    if best is None or best_score < threshold:
        return {
            "status": "miss",
            "reason": "no_similar_successful_modal_cache_entry",
            "similarity_threshold": threshold,
            "best_similarity": round(best_score, 4) if best_score >= 0 else None,
            "similarity_features": features,
        }
    recommended = min(
        coerce_modal_mode_count(best.get("recommended_modal_mode_count")),
        MAX_AUDITED_SOURCE_MODAL_MODE_COUNT,
    )
    return {
        "status": "hit",
        "recommended_modal_mode_count": recommended,
        "similarity": {
            "score": round(best_score, 4),
            "threshold": threshold,
        },
        "cache_key": best.get("cache_key"),
        "source_job_dir": best.get("source_job_dir"),
        "observed_modal_mode_count": best.get("observed_modal_mode_count"),
        "first_above_cutoff_mode": best.get("first_above_cutoff_mode"),
        "similarity_features": features,
    }


def source_modal_count_is_safe_for_initial_solve(source_count: int | None) -> bool:
    return source_count is not None and MIN_MODAL_MODE_COUNT <= source_count <= SAFE_SOURCE_MODAL_MODE_COUNT_LIMIT


def source_modal_count_is_allowed_for_retry(source_count: int | None) -> bool:
    return source_count is not None and MIN_MODAL_MODE_COUNT <= source_count <= MAX_AUDITED_SOURCE_MODAL_MODE_COUNT


def _source_modal_count_is_reasonable_initial(source_count: int | None, inferred_layers: int | None) -> bool:
    _ = inferred_layers
    return source_modal_count_is_safe_for_initial_solve(source_count)


def _estimated_modal_count_is_reasonable_initial(count: int | None, inferred_layers: int | None) -> bool:
    if not source_modal_count_is_safe_for_initial_solve(count):
        return False
    if inferred_layers is None:
        return True
    layer_count = modal_mode_count_from_layer_count(inferred_layers)
    return int(count) <= layer_count + 20


def _learned_modal_count_is_reasonable_initial(count: int | None) -> bool:
    return source_modal_count_is_safe_for_initial_solve(count)


def _auto_modal_count_is_reasonable_initial(count: int | None, inferred_layers: int | None) -> bool:
    return _estimated_modal_count_is_reasonable_initial(count, inferred_layers)


def modal_mode_count_from_payload(payload: dict[str, Any] | None, source_text: str | None = None) -> int:
    metadata = (payload or {}).get("metadata") or {}
    explicit = _as_positive_int(metadata.get("modal_mode_count"))
    explicit_source = str(metadata.get("modal_mode_count_source") or "").strip()
    explicit_is_auto = explicit_source in AUTO_MODAL_MODE_COUNT_SOURCES
    source_count = parse_source_modal_mode_count(source_text)
    inferred_layers = _infer_layer_count_from_payload(payload)
    learned = learned_modal_mode_count_from_payload(payload)
    if explicit is not None and not explicit_is_auto:
        return coerce_initial_modal_mode_count(explicit)
    if learned.get("status") == "hit" and _learned_modal_count_is_reasonable_initial(
        _as_positive_int(learned.get("recommended_modal_mode_count"))
    ):
        return min(
            coerce_modal_mode_count(learned.get("recommended_modal_mode_count")),
            MAX_AUDITED_SOURCE_MODAL_MODE_COUNT,
        )
    if explicit is not None:
        if explicit_source in LEARNED_MODAL_MODE_COUNT_SOURCES:
            if _learned_modal_count_is_reasonable_initial(explicit):
                return coerce_initial_modal_mode_count(explicit)
        elif explicit_is_auto:
            if _auto_modal_count_is_reasonable_initial(explicit, inferred_layers):
                return coerce_initial_modal_mode_count(explicit)
        else:
            return coerce_initial_modal_mode_count(explicit)
    if _source_modal_count_is_reasonable_initial(source_count, inferred_layers):
        return coerce_initial_modal_mode_count(source_count)
    if inferred_layers is not None:
        return modal_mode_count_from_layer_count(inferred_layers)
    return DEFAULT_MODAL_MODE_COUNT


def modal_policy_audit(payload: dict[str, Any] | None, source_text: str | None = None) -> dict[str, Any]:
    metadata = (payload or {}).get("metadata") or {}
    if str(metadata.get("analysis_method") or "").strip().lower() == "static":
        return {
            "status": "not_required",
            "analysis_method": "static",
            "assigned_modal_mode_count": None,
            "assigned_modal_mode_count_source": "static_method_not_required",
            "policy": "Static-method calculations apply equivalent static acceleration loads directly; MT and Mode.oup 50 Hz coverage are not part of the solve.",
        }
    source_count = parse_source_modal_mode_count(source_text)
    requested_count = _as_positive_int(metadata.get("modal_mode_count"))
    requested_source = str(metadata.get("modal_mode_count_source") or "").strip()
    requested_is_auto = requested_source in AUTO_MODAL_MODE_COUNT_SOURCES
    inferred_layers = _infer_layer_count_from_payload(payload)
    learned = learned_modal_mode_count_from_payload(payload)
    assigned = modal_mode_count_from_payload(payload, source_text)
    source_count_used = (
        requested_count is None
        and learned.get("status") != "hit"
        and _source_modal_count_is_reasonable_initial(source_count, inferred_layers)
        and assigned == source_count
    )
    if requested_count is not None and not requested_is_auto and assigned == coerce_initial_modal_mode_count(requested_count):
        assigned_source = "input_metadata"
    elif (
        learned.get("status") == "hit"
        and _learned_modal_count_is_reasonable_initial(_as_positive_int(learned.get("recommended_modal_mode_count")))
        and assigned == min(coerce_modal_mode_count(learned.get("recommended_modal_mode_count")), MAX_AUDITED_SOURCE_MODAL_MODE_COUNT)
    ):
        assigned_source = "learned_similar_intake_cache"
    elif (
        requested_count is not None
        and requested_source in LEARNED_MODAL_MODE_COUNT_SOURCES
        and _learned_modal_count_is_reasonable_initial(requested_count)
        and assigned == coerce_initial_modal_mode_count(requested_count)
    ):
        assigned_source = "learned_similar_intake_metadata"
    elif (
        requested_count is not None
        and requested_is_auto
        and _auto_modal_count_is_reasonable_initial(requested_count, inferred_layers)
        and assigned == coerce_initial_modal_mode_count(requested_count)
    ):
        assigned_source = "auto_metadata_fallback"
    elif requested_count is None and source_count_used and assigned == source_count:
        assigned_source = "audited_source_safe_count"
    elif inferred_layers is not None and assigned == modal_mode_count_from_layer_count(inferred_layers):
        assigned_source = "inferred_layer_count"
    else:
        assigned_source = "default_initial_count"
    return {
        "status": "pass",
        "requested_modal_mode_count": requested_count,
        "source_modal_mode_count": source_count,
        "source_modal_mode_count_retry_allowed": source_modal_count_is_allowed_for_retry(source_count),
        "inferred_layer_count": inferred_layers,
        "learned_modal_mode_count": learned,
        "source_modal_mode_count_used_for_initial_solve": source_count_used,
        "source_modal_mode_count_limit": SAFE_SOURCE_MODAL_MODE_COUNT_LIMIT,
        "source_modal_mode_count_retry_limit": MAX_AUDITED_SOURCE_MODAL_MODE_COUNT,
        "assigned_modal_mode_count": assigned,
        "assigned_modal_mode_count_source": assigned_source,
        "minimum_modal_mode_count": MIN_MODAL_MODE_COUNT,
        "max_initial_modal_mode_count": MAX_INITIAL_MODAL_MODE_COUNT,
        "retry_sequence": list(MODAL_RETRY_SEQUENCE),
        "cutoff_frequency_hz": MODAL_CUTOFF_HZ,
        "policy": (
            "MT is assigned before ANSYS solves. New-intake first solves use explicit intake metadata or "
            "a similar successful intake cache when available. Auto-generated layer-count metadata is only a "
            "fallback and can be superseded by learned real-run evidence. Audited source MT/literal MODOPT counts "
            "within the safe initial range may be used for first solves; higher audited source counts are retained "
            "as traceable retry targets when Mode.oup does not cover 50 Hz. Mode.oup is the post-run coverage "
            "authority, and successful real runs are recorded so future similar intakes can start closer to the "
            "minimum MT that still covers the 50 Hz gate."
        ),
    }


def audited_source_modal_mode_count_from_job(job_dir: Path | str) -> int | None:
    job_dir = Path(job_dir)
    for file_name in ("intake_standard_family_traceability.json", "modal_mt_policy.json"):
        path = job_dir / file_name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        candidates: list[Any] = []
        solve_parameterization = payload.get("solve_parameterization") if isinstance(payload, dict) else {}
        if isinstance(solve_parameterization, dict):
            modal_policy = solve_parameterization.get("modal_mode_policy")
            if isinstance(modal_policy, dict):
                candidates.append(modal_policy.get("source_modal_mode_count"))
        if isinstance(payload, dict):
            candidates.extend(
                [
                    payload.get("source_modal_mode_count"),
                    payload.get("audited_source_modal_mode_count"),
                ]
            )
        parsed = [_as_positive_int(value) for value in candidates]
        parsed = [value for value in parsed if source_modal_count_is_allowed_for_retry(value)]
        if parsed:
            return max(parsed)
    return None


def record_modal_mode_count_learning(
    job_dir: Path | str,
    *,
    cache_path: Path | str = MODAL_MODE_COUNT_CACHE_PATH,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    input_path = job_dir / "input.json"
    modal_path = job_dir / "modal_results.json"
    if not input_path.exists():
        payload = {
            "status": "skipped",
            "reason": "missing_input",
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    try:
        input_payload = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:
        payload = {
            "status": "skipped",
            "reason": "unreadable_input",
            "error": str(exc),
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    input_dict = input_payload if isinstance(input_payload, dict) else {}
    if str(((input_dict.get("metadata") or {}).get("analysis_method") or "")).lower() == "static":
        payload = {
            "status": "not_required",
            "reason": "static_method_has_no_modal_mt_learning",
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    if not modal_path.exists():
        payload = {
            "status": "skipped",
            "reason": "missing_modal_results",
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    try:
        rows = json.loads(modal_path.read_text(encoding="utf-8"))
    except Exception as exc:
        payload = {
            "status": "skipped",
            "reason": "unreadable_modal_results",
            "error": str(exc),
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    if not isinstance(rows, list) or not rows:
        payload = {
            "status": "skipped",
            "reason": "empty_modal_results",
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    pass_rows = [row for row in rows if isinstance(row, dict) and row.get("modal_cutoff_status") == "pass"]
    if not pass_rows:
        payload = {
            "status": "skipped",
            "reason": "modal_cutoff_not_pass",
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    observed_counts = [_as_positive_int(row.get("mt_mode")) for row in pass_rows]
    first_above_values = [_as_positive_int(row.get("mt_mode_first_above_cutoff_hz")) for row in pass_rows]
    last_above_values = [_as_positive_int(row.get("mt_mode_last_above_cutoff_hz")) for row in pass_rows]
    frequency_rows = [
        row for row in rows
        if isinstance(row, dict) and _as_float(row.get("frequency_hz")) is not None
    ]
    observed_count = max(value for value in observed_counts if value is not None) if any(observed_counts) else modal_mode_count_from_job_dir(job_dir)
    first_above = min(value for value in first_above_values if value is not None) if any(first_above_values) else None
    if first_above is None:
        above_rows = [
            row for row in frequency_rows
            if (_as_float(row.get("frequency_hz")) or 0.0) > MODAL_CUTOFF_HZ
        ]
        source_modes = [_as_positive_int(row.get("source_mode") or row.get("mode")) for row in above_rows]
        first_above = min(value for value in source_modes if value is not None) if any(source_modes) else None
    if first_above is None:
        payload = {
            "status": "skipped",
            "reason": "no_mode_above_cutoff_found",
            "job_dir": str(job_dir),
        }
        (job_dir / "modal_mode_learning.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload
    recommended = _next_modal_retry_value(first_above + MODAL_LEARNING_MODE_MARGIN)
    features = _modal_learning_features(input_dict)
    cache_key = _modal_feature_cache_key(features)
    entry = {
        "cache_key": cache_key,
        "status": "pass",
        "source_job_dir": str(job_dir),
        "learned_at": datetime.now(timezone.utc).isoformat(),
        "cutoff_frequency_hz": MODAL_CUTOFF_HZ,
        "observed_modal_mode_count": observed_count,
        "first_above_cutoff_mode": first_above,
        "last_above_cutoff_mode": max(value for value in last_above_values if value is not None) if any(last_above_values) else None,
        "last_frequency_hz": _as_float(frequency_rows[-1].get("frequency_hz")) if frequency_rows else None,
        "recommended_modal_mode_count": recommended,
        "modal_learning_mode_margin": MODAL_LEARNING_MODE_MARGIN,
        "similarity_features": features,
        "policy": (
            "Recommended MT is the next bounded retry value at least four modes above the first source mode "
            "that exceeded 50 Hz in a successful real ANSYS run. The next run still verifies Mode.oup and retries "
            "upward if this learned initial MT is insufficient."
        ),
    }
    cache = _read_modal_cache(cache_path)
    entries = [item for item in cache.get("entries") or [] if isinstance(item, dict) and item.get("cache_key") != cache_key]
    entries.append(entry)
    cache["entries"] = entries[-200:]
    _write_modal_cache(cache, cache_path)
    (job_dir / "modal_mode_learning.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def rewrite_modal_mode_count(text: str, count: int) -> str:
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")

    def replace_mt(match: re.Match[str]) -> str:
        return f"{match.group(1)}{count}{match.group(2)}"

    updated, replaced = re.subn(r"(?im)^(\s*MT\s*=\s*)\d+(\b.*)$", replace_mt, normalised)
    if replaced:
        return updated

    lines = updated.split("\n")
    for index, line in enumerate(lines):
        if re.search(r"\bMODOPT\s*,\s*LANB\s*,", line, flags=re.IGNORECASE):
            lines.insert(
                index,
                f"MT={count}         ! CableTrayAI modal extraction count; verify Mode.oup > {MODAL_CUTOFF_HZ:g} Hz",
            )
            return "\n".join(lines)

    insert_at = 0
    for index, line in enumerate(lines):
        if re.match(r"^\s*/SOL\b", line, flags=re.IGNORECASE):
            insert_at = index + 1
            break
    lines.insert(
        insert_at,
        f"MT={count}         ! CableTrayAI modal extraction count; verify Mode.oup > {MODAL_CUTOFF_HZ:g} Hz",
    )
    return "\n".join(lines)


def modal_mode_count_from_job_dir(job_dir: Path | str) -> int:
    job_dir = Path(job_dir)
    payload: dict[str, Any] = {}
    input_path = job_dir / "input.json"
    if input_path.exists():
        try:
            import json

            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
    solve_path = job_dir / "generated_solve.mac"
    source_text = solve_path.read_text(encoding="utf-8", errors="replace") if solve_path.exists() else None
    generated_count = parse_source_modal_mode_count(source_text)
    if generated_count is not None:
        return coerce_modal_mode_count(generated_count)
    return modal_mode_count_from_payload(payload, source_text)
