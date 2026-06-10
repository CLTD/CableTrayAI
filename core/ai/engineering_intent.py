from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

from core.ai.model_client import DEFAULT_CONFIG, _call_openai_compatible, _load_config


INTENT_SCHEMA_VERSION = "cabletrayai.llm_intent.v1"
ALLOWED_INTENT_FIELDS = {
    "schema_version",
    "authority",
    "source_type",
    "llm_status",
    "job_id",
    "project",
    "analysis_method",
    "support",
    "square_section_policy",
    "material_policy",
    "spectrum_requirements",
    "tray_load_summary",
    "source_refs",
    "warnings",
    "unknown_fields_from_model",
}
FORBIDDEN_MODEL_FIELDS = {
    "apdl",
    "raw_apdl",
    "generated_apdl",
    "pip",
    "mac",
    "generated_model_mac",
    "generated_solve_mac",
    "generated_post_mac",
    "commands",
    "command_stream",
}


def _read_payload(input_path_or_payload: Path | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(input_path_or_payload, dict):
        return input_path_or_payload
    path = Path(input_path_or_payload)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _first_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("model response did not contain a JSON object")


def _project(payload: dict[str, Any]) -> dict[str, Any]:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "project_code": str(project.get("project_code") or metadata.get("project_code") or ""),
        "building": str(project.get("building") or ""),
        "area": str(project.get("area") or project.get("building") or ""),
        "elevation": project.get("elevation"),
        "report_number": metadata.get("report_number") or metadata.get("calculation_batch"),
        "intake_order_id": metadata.get("intake_order_id") or metadata.get("provisional_intake_id"),
    }


def deterministic_intake_intent(input_path_or_payload: Path | str | dict[str, Any], *, job_id: str | None = None) -> dict[str, Any]:
    payload = _read_payload(input_path_or_payload)
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    support = payload.get("support") if isinstance(payload.get("support"), dict) else {}
    spectrum = payload.get("spectrum") if isinstance(payload.get("spectrum"), dict) else {}
    tray_layers = payload.get("tray_layers") if isinstance(payload.get("tray_layers"), list) else []
    analysis_method = str(metadata.get("analysis_method") or "response_spectrum")
    square_section = metadata.get("square_section_spec") or support.get("support_section_id")
    source_refs = [
        "input.json:project",
        "input.json:support",
        "input.json:spectrum",
        "input.json:tray_layers",
        "source_materials/model_commands:standard APDL/PIP/MAC/SECT package",
    ]
    if analysis_method == "static":
        source_refs.append("input.json:metadata.static_acceleration_source")
    return {
        "schema_version": INTENT_SCHEMA_VERSION,
        "authority": "proposal_only",
        "source_type": "deterministic_fallback",
        "llm_status": "not_used",
        "job_id": job_id,
        "project": _project(payload),
        "analysis_method": analysis_method if analysis_method in {"static", "response_spectrum"} else "response_spectrum",
        "support": {
            "support_type": support.get("support_type"),
            "support_height_m": support.get("support_height_m"),
            "support_spacing_m": support.get("support_spacing_m"),
            "layers_front": support.get("layers_front"),
            "layers_back": support.get("layers_back"),
        },
        "square_section_policy": {
            "status": "provided" if square_section else "auto_select_required",
            "selected_or_candidate": square_section,
            "selection_rule": metadata.get("square_section_selection_rule")
            or "Select a local SECT candidate within 0.60 <= controlling ratio <= 0.9999 when possible, using no more than two fresh ANSYS candidate trials.",
        },
        "material_policy": {
            "policy": metadata.get("material_policy") or metadata.get("material_strategy"),
            "support_material_id": support.get("material_id"),
            "source_ref": "input.json:metadata/materials",
        },
        "spectrum_requirements": {
            "spectrum_file": spectrum.get("spectrum_file"),
            "spectrum_level": spectrum.get("spectrum_level"),
            "damping_ratio": spectrum.get("damping_ratio"),
            "directions": spectrum.get("directions"),
            "confirmed": bool(metadata.get("spectrum_config_confirmed")),
            "source_ref": spectrum.get("source_ref") or "input.json:spectrum",
        },
        "tray_load_summary": {
            "layer_count": len(tray_layers),
            "description": metadata.get("tray_load_description"),
            "mapping_status": metadata.get("tray_load_mapping_status"),
        },
        "source_refs": source_refs,
        "warnings": [],
        "unknown_fields_from_model": [],
    }


def _compact_input_context(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return {
        "project": payload.get("project"),
        "spectrum": payload.get("spectrum"),
        "support": payload.get("support"),
        "tray_layers": payload.get("tray_layers"),
        "materials": payload.get("materials"),
        "sections": payload.get("sections"),
        "metadata": {
            key: metadata.get(key)
            for key in (
                "analysis_method",
                "report_number",
                "calculation_batch",
                "intake_order_id",
                "provisional_intake_id",
                "tray_load_description",
                "tray_load_mapping",
                "square_section_spec",
                "square_section_selection_rule",
                "material_policy",
                "spectrum_config_confirmed",
                "static_acceleration_source",
            )
            if key in metadata
        },
    }


def _normalise_model_intent(model_payload: dict[str, Any], fallback: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    checks: list[dict[str, str]] = []
    forbidden = sorted(set(model_payload) & FORBIDDEN_MODEL_FIELDS)
    if forbidden:
        checks.append(
            {
                "status": "fail",
                "check_id": "model_attempted_free_command_generation",
                "message": "Model returned APDL/PIP/MAC command fields; these are not accepted.",
                "evidence": ", ".join(forbidden),
            }
        )
    normalised = dict(fallback)
    normalised.update(
        {
            "source_type": "llm_proposal",
            "llm_status": "accepted_with_constraints" if not forbidden else "rejected_for_free_commands",
            "authority": "proposal_only",
        }
    )
    unknown = sorted(set(model_payload) - ALLOWED_INTENT_FIELDS - FORBIDDEN_MODEL_FIELDS)
    normalised["unknown_fields_from_model"] = unknown
    for key in (
        "analysis_method",
        "support",
        "square_section_policy",
        "material_policy",
        "spectrum_requirements",
        "tray_load_summary",
        "warnings",
    ):
        if key not in model_payload:
            continue
        value = model_payload[key]
        if key == "analysis_method" and value not in {"static", "response_spectrum"}:
            checks.append(
                {
                    "status": "warning",
                    "check_id": "unsupported_analysis_method",
                    "message": "Model proposed an unsupported analysis method; deterministic value retained.",
                    "evidence": str(value),
                }
            )
            continue
        if key in {"support", "square_section_policy", "material_policy", "spectrum_requirements", "tray_load_summary"} and not isinstance(value, dict):
            continue
        if key == "warnings" and not isinstance(value, list):
            continue
        normalised[key] = value
    if forbidden:
        normalised["warnings"] = list(normalised.get("warnings") or []) + [
            "LLM free command output was rejected; use standard command-plan compiler only."
        ]
    return normalised, checks


def propose_intake_intent(
    input_path_or_payload: Path | str | dict[str, Any],
    *,
    job_dir: Path | str | None = None,
    config_path: Path | str = DEFAULT_CONFIG,
    use_model: bool = True,
) -> dict[str, Any]:
    payload = _read_payload(input_path_or_payload)
    job_id = Path(job_dir).name if job_dir else None
    fallback = deterministic_intake_intent(payload, job_id=job_id)
    audit_checks: list[dict[str, str]] = []
    intent = dict(fallback)
    if use_model:
        config = _load_config(config_path)
        if config.get("enabled"):
            try:
                intent_config = dict(config)
                intent_config["timeout_seconds"] = min(int(intent_config.get("timeout_seconds") or 60), 15)
                model_result = _call_openai_compatible(
                    intent_config,
                    {
                        "mode": "llm_intake_intent",
                        "input_context": _compact_input_context(payload),
                        "schema_version": INTENT_SCHEMA_VERSION,
                        "authority_policy": "Return JSON intent only. Do not write APDL, PIP, MAC or any executable command.",
                    },
                    (
                        "Read the CableTrayAI intake context and return one JSON object that matches "
                        "cabletrayai.llm_intent.v1. Only propose engineering intent and warnings. "
                        "Do not include APDL/PIP/MAC commands or code."
                    ),
                    fast=True,
                    max_tokens=900,
                )
                model_payload = _first_json_object(str(model_result.get("answer") or ""))
                intent, audit_checks = _normalise_model_intent(model_payload, fallback)
                intent["model"] = model_result.get("model")
            except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                intent = dict(fallback)
                intent["llm_status"] = "fallback_after_model_error"
                audit_checks.append(
                    {
                        "status": "warning",
                        "check_id": "llm_intent_model_error",
                        "message": str(exc),
                        "evidence": "deterministic fallback used",
                    }
                )
        else:
            intent["llm_status"] = "disabled"
    audit = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "status": "fail" if any(item["status"] == "fail" for item in audit_checks) else "pass",
        "authority": "proposal_only",
        "checks": audit_checks,
        "policy": "LLM may parse and propose engineering intent; it cannot directly generate executable APDL/PIP/MAC.",
    }
    output = {**intent, "audit": audit}
    if job_dir:
        path = Path(job_dir) / "llm_intake_intent.json"
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return output
