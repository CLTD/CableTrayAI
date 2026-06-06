from __future__ import annotations

import re
from pathlib import Path
from typing import Any

MODAL_CUTOFF_HZ = 50.0
DEFAULT_MODAL_MODE_COUNT = 40
MIN_MODAL_MODE_COUNT = 1
MAX_INITIAL_MODAL_MODE_COUNT = 160
SAFE_SOURCE_MODAL_MODE_COUNT_LIMIT = 160
MODAL_RETRY_SEQUENCE = (20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 140, 160, 200, 240)
INITIAL_MODAL_MODE_COUNT_BY_LAYER_COUNT = {
    1: 40,
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
    """Infer tray layer count from normalized intake payload fields."""

    data = payload or {}
    support = data.get("support") if isinstance(data.get("support"), dict) else {}
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

    candidate_values: list[Any] = [
        support.get("total_layers"),
        metadata.get("total_layers"),
        metadata.get("tray_layer_count"),
        metadata.get("layer_count"),
    ]
    side_sum_values = [
        support.get("layers_front"),
        support.get("layers_back"),
        support.get("layers_third"),
        metadata.get("layers_front"),
        metadata.get("layers_back"),
        metadata.get("layers_third"),
    ]
    parsed_sides = [_as_positive_int(value) or 0 for value in side_sum_values]
    if any(parsed_sides):
        candidate_values.append(sum(parsed_sides))

    tray_layers = data.get("tray_layers")
    if isinstance(tray_layers, list) and tray_layers:
        candidate_values.append(len(tray_layers))

    tray_mapping = metadata.get("tray_load_mapping")
    if isinstance(tray_mapping, dict):
        layers = tray_mapping.get("layers")
        if isinstance(layers, list) and layers:
            candidate_values.append(len(layers))
        mapping_sides = [
            tray_mapping.get("front_layers"),
            tray_mapping.get("back_layers"),
            tray_mapping.get("third_layers"),
        ]
        parsed_mapping_sides = [_as_positive_int(value) or 0 for value in mapping_sides]
        if any(parsed_mapping_sides):
            candidate_values.append(sum(parsed_mapping_sides))

    parsed = [_as_positive_int(value) for value in candidate_values]
    parsed = [value for value in parsed if value is not None]
    return max(parsed) if parsed else None


def source_modal_count_is_safe_for_initial_solve(source_count: int | None) -> bool:
    return source_count is not None and MIN_MODAL_MODE_COUNT <= source_count <= SAFE_SOURCE_MODAL_MODE_COUNT_LIMIT


def modal_mode_count_from_payload(payload: dict[str, Any] | None, source_text: str | None = None) -> int:
    metadata = (payload or {}).get("metadata") or {}
    explicit = _as_positive_int(metadata.get("modal_mode_count"))
    source_count = parse_source_modal_mode_count(source_text)
    inferred_layers = _infer_layer_count_from_payload(payload)
    if explicit is not None:
        return coerce_initial_modal_mode_count(explicit)
    if source_modal_count_is_safe_for_initial_solve(source_count):
        return coerce_initial_modal_mode_count(source_count)
    if inferred_layers is not None:
        return modal_mode_count_from_layer_count(inferred_layers)
    return DEFAULT_MODAL_MODE_COUNT


def modal_policy_audit(payload: dict[str, Any] | None, source_text: str | None = None) -> dict[str, Any]:
    metadata = (payload or {}).get("metadata") or {}
    source_count = parse_source_modal_mode_count(source_text)
    requested_count = _as_positive_int(metadata.get("modal_mode_count"))
    inferred_layers = _infer_layer_count_from_payload(payload)
    assigned = modal_mode_count_from_payload(payload, source_text)
    source_count_used = (
        requested_count is None
        and source_modal_count_is_safe_for_initial_solve(source_count)
        and assigned == source_count
    )
    if requested_count is not None and assigned == coerce_initial_modal_mode_count(requested_count):
        assigned_source = "input_metadata"
    elif requested_count is None and source_count_used and assigned == source_count:
        assigned_source = "audited_source_safe_count"
    elif requested_count is None and inferred_layers is not None and assigned == modal_mode_count_from_layer_count(inferred_layers):
        assigned_source = "inferred_layer_count"
    else:
        assigned_source = "default_initial_count"
    return {
        "status": "pass",
        "requested_modal_mode_count": requested_count,
        "source_modal_mode_count": source_count,
        "inferred_layer_count": inferred_layers,
        "source_modal_mode_count_used_for_initial_solve": source_count_used,
        "source_modal_mode_count_limit": SAFE_SOURCE_MODAL_MODE_COUNT_LIMIT,
        "assigned_modal_mode_count": assigned,
        "assigned_modal_mode_count_source": assigned_source,
        "minimum_modal_mode_count": MIN_MODAL_MODE_COUNT,
        "max_initial_modal_mode_count": MAX_INITIAL_MODAL_MODE_COUNT,
        "retry_sequence": list(MODAL_RETRY_SEQUENCE),
        "cutoff_frequency_hz": MODAL_CUTOFF_HZ,
        "policy": (
            "MT is assigned before ANSYS solves. New-intake first solves use explicit intake metadata or "
            "audited source MT/literal MODOPT counts when the source count is within the safe initial range. "
            "Layer-count heuristics are only a fallback for new rows with no usable source count. Mode.oup is a "
            "post-run coverage check for frequencies above 50 Hz; if it fails, CableTrayAI retries with the next "
            "MT in the bounded retry sequence instead of starting every job with an over-conservative mode count."
        ),
    }


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
