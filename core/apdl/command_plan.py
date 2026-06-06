from __future__ import annotations

import json
from pathlib import Path
from typing import Any


COMMAND_PLAN_SCHEMA_VERSION = "cabletrayai.command_plan.v1"
ALLOWED_ANALYSIS_METHODS = {"static", "response_spectrum"}
ALLOWED_TEMPLATE_FAMILIES = {
    "S2_square_cantilever_standard",
    "S2_square_cantilever_parametric_topology",
}
REQUIRED_SOURCE_REFS = {
    "model": "standard_model_source",
    "solve": "standard_solve_source",
    "post": "standard_post_source",
}
FORBIDDEN_FREE_COMMAND_KEYS = {
    "apdl",
    "raw_apdl",
    "free_apdl",
    "pip",
    "mac",
    "commands",
    "command_stream",
    "generated_model_mac",
    "generated_solve_mac",
    "generated_post_mac",
    "model_apdl",
    "solve_apdl",
    "post_apdl",
}


def _read_input(job_dir_or_input: Path | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(job_dir_or_input, dict):
        return job_dir_or_input
    path = Path(job_dir_or_input)
    if path.is_dir():
        path = path / "input.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}


def _project(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("project") if isinstance(payload.get("project"), dict) else {}


def _support(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("support") if isinstance(payload.get("support"), dict) else {}


def _spectrum(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("spectrum") if isinstance(payload.get("spectrum"), dict) else {}


def _sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    return [item for item in items if isinstance(item, dict)]


def build_command_plan(
    input_payload_or_path: Path | str | dict[str, Any],
    *,
    llm_intent: dict[str, Any] | None = None,
    package_id: str | None = None,
) -> dict[str, Any]:
    payload = _read_input(input_payload_or_path)
    metadata = _metadata(payload)
    project = _project(payload)
    support = _support(payload)
    spectrum = _spectrum(payload)
    analysis_method = str(metadata.get("analysis_method") or (llm_intent or {}).get("analysis_method") or "response_spectrum")
    if analysis_method not in ALLOWED_ANALYSIS_METHODS:
        analysis_method = "response_spectrum"
    source_refs = {
        "standard_model_source": "source_materials/model_commands/**/01*.PIP|MAC|TXT",
        "standard_solve_source": "source_materials/model_commands/**/02*.PIP|MAC|TXT",
        "standard_post_source": "source_materials/model_commands/导出数据-S2.PIP",
        "input": "input.json",
    }
    parameters = {
        "project_code": project.get("project_code"),
        "building": project.get("building"),
        "area": project.get("area"),
        "elevation": project.get("elevation"),
        "analysis_method": analysis_method,
        "spectrum_file": spectrum.get("spectrum_file"),
        "spectrum_level": spectrum.get("spectrum_level"),
        "damping_ratio": spectrum.get("damping_ratio"),
        "support_type": support.get("support_type"),
        "support_height_m": support.get("support_height_m"),
        "support_spacing_m": support.get("support_spacing_m"),
        "layers_front": support.get("layers_front"),
        "layers_back": support.get("layers_back"),
        "layers_third": support.get("layers_third") or metadata.get("layers_third"),
        "topology_side_count": support.get("side_count") or metadata.get("topology_side_count") or 1,
        "support_section_id": support.get("support_section_id"),
        "square_section_spec": metadata.get("square_section_spec"),
        "tray_load_mapping_status": metadata.get("tray_load_mapping_status"),
        "spectrum_config_confirmed": metadata.get("spectrum_config_confirmed"),
    }
    return {
        "schema_version": COMMAND_PLAN_SCHEMA_VERSION,
        "authority": "standard_template_compilation_only",
        "template_family": "S2_square_cantilever_parametric_topology"
        if int(parameters["topology_side_count"] or 1) > 2
        else "S2_square_cantilever_standard",
        "package_id": package_id or metadata.get("report_number") or metadata.get("calculation_batch"),
        "analysis_method": analysis_method,
        "forbidden_free_apdl": True,
        "llm_intent_status": (llm_intent or {}).get("llm_status") or "not_used",
        "llm_authority": (llm_intent or {}).get("authority") or "not_used",
        "source_refs": source_refs,
        "macros": [
            {
                "role": "modeling",
                "target": "generated_model.mac",
                "source_ref": "standard_model_source",
                "allowed_operations": [
                    "copy_standard_source",
                    "parameter_substitution",
                    "parametric_topology_expansion",
                    "safe_guard_patch",
                    "audit_header",
                ],
                "responsibility": "geometry, materials, sections, constraints, coupling, mesh",
            },
            {
                "role": "calculation",
                "target": "generated_solve.mac",
                "source_ref": "standard_solve_source",
                "allowed_operations": ["copy_standard_source", "spectrum_or_static_parameterization", "audit_header"],
                "responsibility": "static or response-spectrum calculation sequence",
            },
            {
                "role": "result_extraction",
                "target": "generated_post.mac",
                "source_ref": "standard_post_source",
                "allowed_operations": ["copy_standard_source", "selector_alignment", "figure_export", "audit_header"],
                "responsibility": "LIS/OUP/BMP result extraction and report-table source collections",
            },
        ],
        "parameters": parameters,
        "section_candidates": [
            {
                "section_id": item.get("section_id"),
                "sect_file": item.get("sect_file"),
                "source_ref": item.get("source_ref"),
            }
            for item in _sections(payload)
        ],
        "safety_gates": [
            "llm_intent_is_proposal_only",
            "no_free_apdl_from_model",
            "compile_only_from_standard_sources",
            "apdl_audit_required",
            "preflight_required_before_real_ansys",
            "postprocess_validity_required_before_report",
        ],
        "generalization_policy": (
            "S2 single/double/three-side supports are one approved S2 square-cantilever family. "
            "For untrained side/layer combinations, the executable APDL must be compiled by deterministic S2 topology rules "
            "derived from audited standard command streams; the LLM may classify intent and review the plan but may not emit free APDL."
        ),
    }


def _scan_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).lower() in FORBIDDEN_FREE_COMMAND_KEYS:
                hits.append(child_path)
            hits.extend(_scan_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_scan_forbidden_keys(child, f"{path}[{index}]"))
    return hits


def audit_command_plan(plan: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    def add(check_id: str, status: str, message: str, evidence: Any = None) -> None:
        checks.append({"check_id": check_id, "status": status, "message": message, "evidence": evidence})

    add(
        "schema_version",
        "pass" if plan.get("schema_version") == COMMAND_PLAN_SCHEMA_VERSION else "fail",
        "command plan schema must match CableTrayAI v1",
        plan.get("schema_version"),
    )
    add(
        "authority",
        "pass" if plan.get("authority") == "standard_template_compilation_only" else "fail",
        "command plan must compile from standard templates only",
        plan.get("authority"),
    )
    add(
        "template_family",
        "pass" if plan.get("template_family") in ALLOWED_TEMPLATE_FAMILIES else "fail",
        "template family must be approved",
        plan.get("template_family"),
    )
    add(
        "analysis_method",
        "pass" if plan.get("analysis_method") in ALLOWED_ANALYSIS_METHODS else "fail",
        "analysis method must be static or response_spectrum",
        plan.get("analysis_method"),
    )
    macros = plan.get("macros") if isinstance(plan.get("macros"), list) else []
    macro_targets = {item.get("target") for item in macros if isinstance(item, dict)}
    add(
        "three_macro_targets",
        "pass" if {"generated_model.mac", "generated_solve.mac", "generated_post.mac"} <= macro_targets else "fail",
        "plan must produce exactly the three auditable command files",
        sorted(str(item) for item in macro_targets),
    )
    source_refs = plan.get("source_refs") if isinstance(plan.get("source_refs"), dict) else {}
    for check_id, ref_key in REQUIRED_SOURCE_REFS.items():
        add(
            f"source_ref_{check_id}",
            "pass" if source_refs.get(ref_key) else "fail",
            "standard source reference is required",
            {ref_key: source_refs.get(ref_key)},
        )
    forbidden_hits = _scan_forbidden_keys(plan)
    add(
        "no_free_command_fields",
        "pass" if not forbidden_hits else "fail",
        "LLM/free APDL command fields are not permitted in the command plan",
        forbidden_hits,
    )
    add(
        "llm_authority",
        "pass" if plan.get("llm_authority") in {"proposal_only", "not_used", None} else "fail",
        "LLM authority must be proposal-only",
        plan.get("llm_authority"),
    )
    status = "fail" if any(item["status"] == "fail" for item in checks) else "pass"
    return {
        "schema_version": COMMAND_PLAN_SCHEMA_VERSION,
        "status": status,
        "checks": checks,
        "policy": "The plan may be influenced by LLM intent, but executable command files are compiled only from approved standard sources.",
    }


def write_command_plan(job_dir: Path | str, plan: dict[str, Any]) -> dict[str, Any]:
    job_dir = Path(job_dir)
    audit = audit_command_plan(plan)
    (job_dir / "command_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (job_dir / "command_plan_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
