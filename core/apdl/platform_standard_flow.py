from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.apdl.numeric_post import build_numeric_post_macro


PLATFORM_STANDARD_AUDIT = "platform_standard_flow_audit.json"
PLATFORM_STANDARD_SOLVE = "platform_standard_solve.mac"
PLATFORM_STANDARD_POST = "platform_standard_post.mac"
PLATFORM_STANDARD_POST_NUMERIC = "platform_standard_post_numeric.mac"
PLATFORM_STANDARD_POST_NUMERIC_AUDIT = "platform_standard_post_numeric_audit.json"

SUPPORTED_STANDARD_ANALYSIS_METHODS = {"static", "response_spectrum", "spectrum"}
SUPPORTED_STANDARD_SIDES = {"front", "back"}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")


def _tray_width_mm(layer: dict[str, Any]) -> int | None:
    if layer.get("tray_width_mm") is not None:
        try:
            return int(round(float(layer["tray_width_mm"])))
        except (TypeError, ValueError):
            return None
    if layer.get("tray_width_m") is not None:
        try:
            return int(round(float(layer["tray_width_m"]) * 1000.0))
        except (TypeError, ValueError):
            return None
    return None


def classify_platform_standard_scope(payload: dict[str, Any]) -> dict[str, Any]:
    """Return whether this job is inside the initial platform-standard shadow scope.

    Scope is deliberately narrow for v1: S2 square-cantilever jobs with one tray
    width across supported front/back sides. Mixed-width layouts keep using the
    existing production flow until enough baseline comparisons are accumulated.
    """

    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    support_type = str(support.get("support_type") or metadata.get("support_type") or "S2").strip().upper()
    analysis_method = str(metadata.get("analysis_method") or "response_spectrum").strip().lower()
    if support_type and support_type != "S2":
        return {"status": "skipped", "reason": "unsupported_support_type", "support_type": support_type}
    if analysis_method not in SUPPORTED_STANDARD_ANALYSIS_METHODS:
        return {"status": "skipped", "reason": "unsupported_analysis_method", "analysis_method": analysis_method}

    layers = [item for item in payload.get("tray_layers") or [] if isinstance(item, dict)]
    if not layers:
        return {"status": "skipped", "reason": "missing_tray_layers"}
    sides = {str(item.get("side") or "front").strip().lower() for item in layers}
    unsupported_sides = sorted(side for side in sides if side not in SUPPORTED_STANDARD_SIDES)
    if unsupported_sides:
        return {"status": "skipped", "reason": "unsupported_sides", "unsupported_sides": unsupported_sides}
    if int(support.get("layers_third") or metadata.get("layers_third") or 0) > 0:
        return {"status": "skipped", "reason": "third_side_not_in_v1_scope"}

    widths = sorted({width for width in (_tray_width_mm(item) for item in layers) if width is not None})
    if len(widths) != 1:
        return {"status": "skipped", "reason": "mixed_or_unknown_tray_widths", "tray_widths_mm": widths}

    return {
        "status": "pass",
        "scope": "single_tray_width_s2_shadow_v1",
        "analysis_method": "response_spectrum" if analysis_method == "spectrum" else analysis_method,
        "support_type": support_type or "S2",
        "tray_width_mm": widths[0],
        "layer_count": len(layers),
        "sides": sorted(sides),
        "policy": (
            "Generate platform-owned solve/post command streams for review and baseline comparison. "
            "They are shadow files in v1; production run_all.mac still targets the validated generated_* streams."
        ),
    }


def _standard_header(kind: str, scope: dict[str, Any], source_name: str, source_hash: str) -> str:
    return "\n".join(
        [
            f"! CableTrayAI platform standard {kind} command stream.",
            "! Scope: S2 single tray-width shadow standard v1.",
            f"! source={source_name}",
            f"! source_sha256={source_hash}",
            f"! tray_width_mm={scope.get('tray_width_mm')}",
            f"! analysis_method={scope.get('analysis_method')}",
            "! Execution policy: review/baseline shadow only until precision acceptance is recorded.",
            "",
        ]
    )


def _uses_platform_solve_template(text: str) -> bool:
    markers = [
        "CableTrayAI generated_solve.mac",
        "Response-spectrum method for non-steel-platform support",
        "Static method for steel-platform support",
        "ansys_spectrum_sl1",
        "ansys_zpa_parameters",
    ]
    return any(marker.lower() in text.lower() for marker in markers)


def _uses_platform_post_template(text: str) -> bool:
    markers = [
        "CableTrayAI",
        "MAXBEAMSTRESS",
        "TMAXBEAMSTRESS",
        "JCZH",
        "LS-FORCE",
    ]
    return all(marker.lower() in text.lower() for marker in markers if marker != "CableTrayAI") and (
        "cabletrayai" in text.lower() or "导出" in text
    )


def build_platform_standard_shadow_flow(
    job_dir: Path | str,
    payload: dict[str, Any],
    *,
    solve_source_audit: dict[str, Any] | None = None,
    solve_parameterization_audit: dict[str, Any] | None = None,
    post_alignment_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    scope = classify_platform_standard_scope(payload)
    if scope.get("status") != "pass":
        audit = {
            "status": "skipped",
            "scope": scope,
            "generated_files": [],
            "policy": "Platform standard shadow command streams are emitted only for the initial single-tray-width S2 scope.",
        }
        _write_json(job_dir / PLATFORM_STANDARD_AUDIT, audit)
        return audit

    solve_path = job_dir / "generated_solve.mac"
    post_path = job_dir / "generated_post.mac"
    missing = [path.name for path in (solve_path, post_path) if not path.exists()]
    if missing:
        audit = {
            "status": "missing_source",
            "scope": scope,
            "missing": missing,
            "generated_files": [],
        }
        _write_json(job_dir / PLATFORM_STANDARD_AUDIT, audit)
        return audit

    solve_text = _read_text(solve_path)
    post_text = _read_text(post_path)
    solve_hash = _sha256_text(solve_text)
    post_hash = _sha256_text(post_text)
    standard_solve = _standard_header("solve", scope, solve_path.name, solve_hash) + solve_text.lstrip()
    standard_post = _standard_header("post", scope, post_path.name, post_hash) + post_text.lstrip()
    (job_dir / PLATFORM_STANDARD_SOLVE).write_text(standard_solve, encoding="utf-8", newline="\n")
    (job_dir / PLATFORM_STANDARD_POST).write_text(standard_post, encoding="utf-8", newline="\n")
    numeric_audit = build_numeric_post_macro(
        job_dir,
        source_name=PLATFORM_STANDARD_POST,
        output_name=PLATFORM_STANDARD_POST_NUMERIC,
        audit_name=PLATFORM_STANDARD_POST_NUMERIC_AUDIT,
    )

    checks = [
        {
            "check_id": "scope_single_tray_width",
            "status": "pass",
            "evidence": scope,
        },
        {
            "check_id": "solve_stream_platform_controlled",
            "status": "pass" if _uses_platform_solve_template(solve_text) else "warning",
            "evidence": {
                "generated_solve_sha256": solve_hash,
                "solve_source": (solve_source_audit or {}).get("status"),
                "solve_parameterization": (solve_parameterization_audit or {}).get("status"),
            },
        },
        {
            "check_id": "post_stream_has_required_numeric_outputs",
            "status": "pass" if _uses_platform_post_template(post_text) else "warning",
            "evidence": {
                "generated_post_sha256": post_hash,
                "post_alignment": (post_alignment_audit or {}).get("status"),
                "required_tokens": ["MAXBEAMSTRESS", "TMAXBEAMSTRESS", "JCZH", "LS-FORCE"],
            },
        },
        {
            "check_id": "numeric_post_shadow_created",
            "status": "pass" if numeric_audit.get("status") == "pass" else "fail",
            "evidence": numeric_audit,
        },
    ]
    status = "fail" if any(item["status"] == "fail" for item in checks) else "pass"
    audit = {
        "schema_version": "cabletrayai.platform_standard_flow.v1",
        "status": status,
        "mode": "shadow_review_only",
        "scope": scope,
        "generated_files": [
            PLATFORM_STANDARD_SOLVE,
            PLATFORM_STANDARD_POST,
            PLATFORM_STANDARD_POST_NUMERIC,
        ],
        "checks": checks,
        "execution_policy": (
            "Do not point run_all.mac at platform_standard_* files yet. Use these files for review, "
            "manual baseline comparison, and future precision acceptance. Production results remain "
            "controlled by generated_solve.mac plus generated_post_numeric.mac."
        ),
        "promotion_gate": [
            "real_ansys_baseline_comparison_required",
            "solve_load_case_hash_and_LIS_numeric_tolerance_required",
            "post_numeric_outputs_must_match_required_result_files",
            "static_and_response_spectrum_single_tray_cases_required",
        ],
    }
    _write_json(job_dir / PLATFORM_STANDARD_AUDIT, audit)
    return audit
