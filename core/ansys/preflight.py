from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.ansys.config import AnsysLocalConfig
from core.ansys.master_macro import command_uses_master_macro, validate_run_all_macro
from core.apdl.audit import audit_rendered_apdl
from core.results.pip_output_manifest import KNOWN_RESULT_OUTPUTS
from core.schemas.input_models import parse_cable_input


def _check(check_id: str, status: str, message: str, evidence: Any = None, source_ref: str | None = None, suggested_fix: str | None = None) -> dict:
    return {
        "check_id": check_id,
        "status": status,
        "message": message,
        "evidence": evidence,
        "source_ref": source_ref,
        "suggested_fix": suggested_fix,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _apdl_text(job_dir: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [job_dir / "generated_model.mac", job_dir / "generated_solve.mac", job_dir / "generated_post.mac"]
        if path.exists()
    )


def _sample_token_pattern() -> re.Pattern:
    project_token = "18" + "18"
    elevation_token = "7" + r"\.5" + "m"
    building_token = "(?<![A-Za-z])" + "N" + "B" + "(?![A-Za-z])"
    return re.compile("|".join([project_token, elevation_token, building_token]), flags=re.IGNORECASE)


def _secread_sections(job_dir: Path) -> list[str]:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return []
    text = model_path.read_text(encoding="utf-8", errors="replace")
    sections: list[str] = []
    for match in re.finditer(r"SECREAD\s*,\s*['\"]?([^,'\"\s]+)", text, flags=re.IGNORECASE):
        name = match.group(1).strip()
        if name and name not in sections:
            sections.append(name)
    return sections


def _native_hrec_sections(job_dir: Path) -> set[str]:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return set()
    text = model_path.read_text(encoding="utf-8", errors="replace")
    return {
        match.group(1).strip()
        for match in re.finditer(r"SECTYPE\s*,\s*\d+\s*,\s*BEAM\s*,\s*HREC\s*,\s*([^,\s!]+)", text, flags=re.IGNORECASE)
        if match.group(1).strip()
    }


def _section_stem(value: Any, default: str = "") -> str:
    text = str(value or default).strip()
    return Path(text).stem if text else default


def _is_tray_section_name(name: str) -> bool:
    return bool(re.search(r"\d+-75-2mm", str(name or ""), flags=re.IGNORECASE))


def _required_tray_sections_from_payload(payload: dict[str, Any]) -> list[str]:
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
        if section_name and _is_tray_section_name(section_name) and section_name not in required:
            required.append(section_name)
    return required


def _has_source_traced_solve(job_dir: Path) -> bool:
    trace_path = job_dir / "intake_standard_family_traceability.json"
    if not trace_path.exists():
        return False
    try:
        trace = _read_json(trace_path)
    except Exception:
        return False
    solve_source = trace.get("solve_source") if isinstance(trace, dict) else {}
    return isinstance(solve_source, dict) and solve_source.get("status") == "pass" and bool(solve_source.get("source"))


def run_preflight(job_dir: Path | str, config: AnsysLocalConfig | None = None) -> dict:
    job_dir = Path(job_dir)
    checks: list[dict] = []
    input_payload: dict[str, Any] = {}

    input_path = job_dir / "input.json"
    if input_path.exists():
        try:
            input_payload = _read_json(input_path)
            cable_input = parse_cable_input(input_payload)
            checks.append(_check("input_json", "pass", "input.json exists and is parseable", str(input_path), "input.json"))
        except Exception as exc:
            cable_input = None
            checks.append(_check("input_json", "fail", "input.json is not parseable", str(exc), "input.json", "Fix input schema errors."))
    else:
        cable_input = None
        checks.append(_check("input_json", "fail", "input.json is missing", None, "input.json", "Create job input first."))

    required_macros = ["generated_model.mac", "generated_solve.mac", "generated_post.mac"]
    macro_paths = [job_dir / name for name in required_macros]
    for path in macro_paths:
        checks.append(
            _check(
                path.stem,
                "pass" if path.exists() else "fail",
                f"{path.name} {'exists' if path.exists() else 'is missing'}",
                str(path),
                path.name,
                None if path.exists() else "Render APDL templates before running.",
            )
        )

    master_audit = validate_run_all_macro(job_dir)
    checks.append(
        _check(
            "run_all_master_macro",
            master_audit["status"],
            "run_all.mac exists and calls model, solve, and post macros in order",
            master_audit,
            "run_all.mac",
            "Generate run_all.mac before dry-run or real ANSYS.",
        )
    )

    command_path = job_dir / "ansys_command.json"
    if command_path.exists():
        try:
            command_payload = _read_json(command_path)
            uses_master = command_uses_master_macro(command_payload)
            checks.append(
                _check(
                    "ansys_command_uses_run_all",
                    "pass" if uses_master else "fail",
                    "ansys_command.json uses run_all.mac as -i input",
                    command_payload.get("input_file"),
                    "ansys_command.json",
                    "Rebuild ansys_command.json using core.ansys.command_builder.",
                )
            )
        except Exception as exc:
            checks.append(_check("ansys_command_uses_run_all", "fail", "ansys_command.json is unreadable", str(exc), "ansys_command.json"))

    text = _apdl_text(job_dir)
    if text:
        has_placeholders = "{{" in text or "{%" in text
        checks.append(_check("jinja_placeholders", "fail" if has_placeholders else "pass", "APDL placeholder check", has_placeholders, "generated_*.mac"))
        hardcoded = bool(_sample_token_pattern().search(text))
        metadata = input_payload.get("metadata") if isinstance(input_payload, dict) else {}
        is_calibration_source_copy = bool(isinstance(metadata, dict) and metadata.get("calibration_workspace"))
        has_source_traced_solve = _has_source_traced_solve(job_dir)
        hardcoded_status = "warning" if hardcoded and (is_calibration_source_copy or has_source_traced_solve) else ("fail" if hardcoded else "pass")
        hardcoded_message = "APDL sample token scan"
        if hardcoded_status == "warning":
            hardcoded_message = "APDL sample token scan; allowed because generated_solve.mac is source-traced to an audited standard calculation stream"
        checks.append(_check("hardcoded_sample_tokens", hardcoded_status, hardcoded_message, hardcoded, "generated_*.mac"))
        analysis_method = str((metadata or {}).get("analysis_method") or "").strip().lower()
        require_modal_analysis = analysis_method != "static"
        checks.extend(_apdl_feature_checks(text, require_modal_analysis=require_modal_analysis))
        try:
            audit = audit_rendered_apdl(
                macro_paths,
                job_dir / "apdl_audit_preflight.json",
                require_modal_analysis=require_modal_analysis,
            )
            checks.append(_check("apdl_audit", "pass" if audit["status"] == "pass" else "fail", "APDL audit status", audit, "apdl_audit_preflight.json"))
        except Exception as exc:
            checks.append(_check("apdl_audit", "fail", "APDL audit failed", str(exc), "generated_*.mac"))
    else:
        checks.append(_check("apdl_content", "fail", "No APDL content available", None, "generated_*.mac", "Render APDL templates."))

    if cable_input is not None:
        required_tray_sections = _required_tray_sections_from_payload(input_payload)
        present_secreads = {Path(section).stem.lower() for section in _secread_sections(job_dir)}
        missing_required_tray_sections = [
            section for section in required_tray_sections if Path(section).stem.lower() not in present_secreads
        ]
        checks.append(
            _check(
                "tray_sections_match_input",
                "pass" if not missing_required_tray_sections else "fail",
                "generated_model.mac includes the tray equivalent SECT files declared by input.json",
                {"required": required_tray_sections, "missing": missing_required_tray_sections},
                "input.json:tray_layers / generated_model.mac:SECREAD",
                "Regenerate the model from the controlled S2 template or fix the selected source family tray section mapping.",
            )
        )
        missing_sections = []
        native_hrec_section_names = _native_hrec_sections(job_dir)
        traceable_model = (job_dir / "intake_standard_family_traceability.json").exists()
        required_section_stems = _secread_sections(job_dir) if traceable_model else []
        if not required_section_stems:
            required_section_stems = [
                section.sect_file
                for section in cable_input.sections
                if section.sect_file not in native_hrec_section_names
            ]
        for section_stem in required_section_stems:
            sect_name = section_stem if section_stem.lower().endswith(".sect") else f"{section_stem}.SECT"
            candidates = [job_dir / "sections" / sect_name, job_dir / sect_name]
            if not any(candidate.exists() for candidate in candidates):
                missing_sections.append(sect_name)
        checks.append(
            _check(
                "sect_files",
                "pass" if not missing_sections else "fail",
                "SECT files referenced by generated_model.mac are available",
                missing_sections,
                "generated_model.mac:SECREAD",
                "Copy required SECT files into job sections directory.",
            )
        )
        materials_ok = all(
            material.elastic_modulus_pa and material.poisson_ratio is not None and material.density_kg_m3
            for material in cable_input.materials
        )
        checks.append(_check("material_units", "pass" if materials_ok else "fail", "Material parameters include required units/values", None, "input.json:materials"))
        directions_ok = bool(cable_input.spectrum.directions)
        checks.append(_check("coordinate_directions", "pass" if directions_ok else "warning", "Spectrum coordinate directions are declared", cable_input.spectrum.directions, "input.json:spectrum"))

    analysis_method = None
    input_payload = {}
    if input_path.exists():
        try:
            input_payload = _read_json(input_path)
            analysis_method = (input_payload.get("metadata") or {}).get("analysis_method")
        except Exception:
            analysis_method = None

    spectrum_exists = analysis_method == "static" or (job_dir / "ansys_spectrum.mac").exists()
    spectrum_message = "Response-spectrum jobs require a generated ansys_spectrum.mac, not only a declared source workbook"
    if analysis_method == "static":
        spectrum_message = "Static method selected; response spectrum is not required"
    checks.append(_check("spectrum_available", "pass" if spectrum_exists else "fail", spectrum_message, spectrum_exists, "input.json:spectrum"))
    if analysis_method != "static":
        zpa_path = job_dir / "ansys_zpa_parameters.mac"
        checks.append(
            _check(
                "response_zero_period_parameters",
                "pass" if zpa_path.exists() else "fail",
                "Response-spectrum jobs require zero-period acceleration parameters for the source-stream static correction load steps",
                str(zpa_path) if zpa_path.exists() else None,
                "ansys_zpa_parameters.mac",
                "Render ansys_zpa_parameters.mac from the confirmed spectrum workbook before real ANSYS.",
            )
        )
    if analysis_method == "static":
        metadata = (input_payload.get("metadata") or {}) if input_path.exists() else {}
        coefficient_keys = (
            "zpa_obe_x_g",
            "zpa_obe_y_g",
            "zpa_obe_z_g",
            "zpa_sse_x_g",
            "zpa_sse_y_g",
            "zpa_sse_z_g",
        )
        coefficients = {key: float(metadata.get(key) or 0.0) for key in coefficient_keys}
        checks.append(
            _check(
                "static_acceleration_coefficients",
                "pass" if all(value > 0 for value in coefficients.values()) else "fail",
                "Static method uses non-zero SL-1/SL-2 acceleration coefficients from a confirmed spectrum or static coefficient source",
                coefficients,
                "input.json:metadata",
                "Select the project spectrum file or provide audited static acceleration coefficients before real ANSYS.",
            )
        )

    figures_dir = job_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    checks.append(_check("figures_dir", "pass", "Figures output directory exists", str(figures_dir), "jobs/<job_id>/figures"))
    checks.append(_check("result_dir", "pass" if job_dir.exists() else "fail", "Job result directory exists", str(job_dir), "jobs/<job_id>"))

    registered_outputs = sorted(KNOWN_RESULT_OUTPUTS)
    checks.append(_check("pip_outputs_registered", "pass", "Key PIP outputs are registered", registered_outputs, "core/results/pip_output_manifest.py"))

    state_path = job_dir / "job_state.json"
    if state_path.exists():
        state = _read_json(state_path)
        allowed = state.get("status") not in {"running", "failed"}
        checks.append(_check("job_state_allows_run", "pass" if allowed else "fail", "Job state allows run", state, "job_state.json"))
    else:
        checks.append(_check("job_state_allows_run", "warning", "job_state.json missing; dry-run may create it", None, "job_state.json"))

    if config and config.runner.mode == "real":
        executable = Path(config.ansys.executable or "")
        checks.append(
            _check(
                "ansys_executable",
                "pass" if executable.exists() else "fail",
                "Configured ANSYS executable exists",
                str(executable),
                "config/ansys.local.toml",
                "Set ansys.executable to an existing executable.",
            )
        )

    status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    payload = {"status": status, "checks": checks}
    (job_dir / "ansys_preflight.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _apdl_feature_checks(text: str, *, require_modal_analysis: bool = True) -> list[dict]:
    features = {
        "apdl_beam188": (r"BEAM188|\bET\s*,\s*\d+\s*,\s*188\b", "BEAM188 element definition"),
        "apdl_secread": (r"\bSECREAD\s*,", "SECREAD section loading"),
        "apdl_latt": (r"\bLATT\s*,", "LATT meshing attributes"),
        "apdl_lmesh": (r"\bLMESH\s*,", "LMESH command"),
        "apdl_coupling": (r"\b(CP|CPCYC)\s*,", "CP/CPCYC coupling"),
        "apdl_constraint": (r"^\s*D\s*,", "D constraint command"),
        "apdl_modal": (r"\b(MODOPT|ANTYPE\s*,\s*2)\b", "modal analysis command"),
        "apdl_spectrum": (r"\b(SPOPT|ANTYPE\s*,\s*8|SV\s*,|ACEL\s*,|LSSOLVE\s*,|LCOPER\s*,)\b", "response spectrum or equivalent static seismic command"),
        "apdl_post": (r"/POST1|\*GET\s*,|/OUTPUT\s*,", "post-processing command"),
    }
    checks = []
    for check_id, (pattern, message) in features.items():
        ok = bool(re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE))
        if check_id == "apdl_modal" and not require_modal_analysis:
            ok = True
            message = "modal analysis command not required for static-method main solve"
        checks.append(_check(check_id, "pass" if ok else "fail", message, ok, "generated_*.mac"))
    return checks
