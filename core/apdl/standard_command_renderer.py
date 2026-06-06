from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from core.ansys.master_macro import build_run_all_macro
from core.apdl.audit import audit_rendered_apdl
from core.apdl.command_aliases import write_command_aliases
from core.apdl.keypoint_guard import guard_undefined_keypoint_coordinate_refs
from core.apdl.postprocessor_alignment import align_postprocessor_to_intake
from core.apdl.section_specific_export import augment_square_support_export
from core.apdl.source_conflict_resolver import apply_source_conflict_resolutions
from core.apdl.source_diff import read_text_with_encoding


MODEL_PATTERNS = ("01*.PIP", "01*.pip", "01*.MAC", "01*.mac", "01*.TXT", "01*.txt")
SOLVE_PATTERNS = ("02*.PIP", "02*.pip", "02*.MAC", "02*.mac", "02*.TXT", "02*.txt")
POST_FILE_NAME = "\u5bfc\u51fa\u6570\u636e-S2.PIP"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_standard_command_package(source_root: Path | str, package_id: str) -> Path:
    source_root = Path(source_root)
    matches = [path for path in source_root.rglob("*") if path.is_dir() and package_id in path.name]
    if not matches:
        raise FileNotFoundError(f"No standard command package matched: {package_id}")
    return sorted(matches, key=lambda item: len(item.parts))[0]


def resolve_standard_command_package(source_root: Path | str, report_number: str | None = None) -> Path | None:
    source_root = Path(source_root)
    if report_number:
        try:
            return find_standard_command_package(source_root, report_number)
        except FileNotFoundError:
            return None
    package_roots = sorted(
        path
        for path in source_root.rglob("*")
        if path.is_dir() and any((path / child).is_dir() for child in ("calc", "计算文件"))
    )
    return package_roots[0] if len(package_roots) == 1 else None


def _first_file(root: Path, patterns: str | tuple[str, ...]) -> Path:
    pattern_list = (patterns,) if isinstance(patterns, str) else patterns
    for pattern in pattern_list:
        matches = sorted(
            path
            for path in root.rglob(pattern)
            if path.is_file() and not path.name.lower().endswith(".bak")
        )
        if matches:
            return matches[0]
    raise FileNotFoundError(f"Missing standard command file matching {pattern_list} under {root}")


def _write_decoded_copy(source: Path, target: Path) -> dict[str, Any]:
    text, encoding = read_text_with_encoding(source)
    target.write_text(text, encoding="utf-8", newline="\n")
    return {
        "source": str(source),
        "target": target.name,
        "source_sha256": _sha256(source),
        "source_encoding": encoding,
        "line_count": len(text.splitlines()),
    }


def _command_header(role: str) -> str:
    descriptions = {
        "model": [
            "Builds the S2 support geometry from the audited standard source command stream.",
            "Defines BEAM188 element types, materials, SECREAD sections, keypoints, lines, LATT attributes, mesh, coupling, and supports.",
            "CableTrayAI only parameterizes intake-controlled dimensions/sections/loads; source_materials remains read-only.",
        ],
        "solve": [
            "Runs the calculation sequence from the audited standard source command stream.",
            "Defines gravity/static or response-spectrum load cases, solves them, and writes load-case files for postprocessing.",
            "Spectrum/static acceleration coefficients come from the selected spectrum workbook and input.json, not hardcoded project data.",
        ],
        "post": [
            "Extracts engineering results from the solved S2 model.",
            "Writes MAXBEAMSTRESS/SQUAREBEAMSTRESS/TMAXBEAMSTRESS, foundation loads, weld/bolt loads, modal data, and ANSYS figures.",
            "Selector blocks are annotated because they define which model component maps to each report table.",
        ],
    }
    lines = [
        "! =====================================================================",
        f"! CableTrayAI generated_{role}.mac audit guide",
        "! Review purpose:",
        *[f"! - {item}" for item in descriptions[role]],
        "! =====================================================================",
        "",
    ]
    return "\n".join(lines)


def _prepend_command_headers(job_dir: Path) -> dict[str, Any]:
    mapping = {
        "generated_model.mac": "model",
        "generated_solve.mac": "solve",
        "generated_post.mac": "post",
    }
    updated: list[str] = []
    for filename, role in mapping.items():
        path = job_dir / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        marker = f"! CableTrayAI generated_{role}.mac audit guide"
        if marker in text:
            continue
        path.write_text(_command_header(role) + text, encoding="utf-8", newline="\n")
        updated.append(filename)
    return {"status": "applied" if updated else "unchanged", "updated_files": updated}


def _sect_names_from_apdl(text: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"SECREAD\s*,\s*['\"]?([^,'\"\s]+)", text, flags=re.IGNORECASE):
        value = match.group(1).strip()
        if value and value not in names:
            names.append(value)
    return names


def _copy_required_sections(job_dir: Path, source_root: Path, generated_model: Path) -> list[dict[str, Any]]:
    text = generated_model.read_text(encoding="utf-8", errors="replace")
    section_dir = job_dir / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    for section_name in _sect_names_from_apdl(text):
        filename = section_name if section_name.lower().endswith(".sect") else f"{section_name}.SECT"
        matches = sorted(source_root.rglob(filename), key=lambda item: item.as_posix().upper())
        if not matches:
            copied.append({"section": filename, "status": "missing"})
            continue
        source = matches[0]
        for target in (section_dir / filename, job_dir / filename):
            shutil.copy2(source, target)
        copied.append({"section": filename, "status": "copied", "source": str(source), "sha256": _sha256(source)})
    return copied


def _sync_input_sections(job_dir: Path, sections: list[dict[str, Any]]) -> None:
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    copied = [item for item in sections if item.get("status") == "copied"]
    if not copied:
        return
    payload["sections"] = [
        {
            "section_id": Path(item["section"]).stem.lower(),
            "sect_file": Path(item["section"]).stem,
            "section_type": "BEAM_MESH",
            "source_ref": "command_source_traceability.json",
        }
        for item in copied
    ]
    support = payload.get("support") or {}
    support["support_section_id"] = Path(copied[0]["section"]).stem.lower()
    payload["support"] = support
    metadata = payload.get("metadata") or {}
    metadata["sections_synced_from_standard_commands"] = True
    payload["metadata"] = metadata
    input_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _remove_unsafe_post_layer_aliases(post_text: str) -> tuple[str, list[str]]:
    """Remove stale template aliases that can overwrite standard-source layer counts."""

    removed: list[str] = []
    keep: list[str] = []
    unsafe_comments = (
        "CableTrayAI topology aliases for the shared S2 post processor",
        "The parameterized model uses qiancengshu/houcengshu",
        "extraction blocks use senum/senum1",
        "Keep the bridge explicit for audit",
    )
    unsafe_assignments = (
        re.compile(r"^\s*senum\s*=\s*qiancengshu\s*$", re.IGNORECASE),
        re.compile(r"^\s*senum1\s*=\s*houcengshu\s*$", re.IGNORECASE),
    )
    for line in post_text.splitlines():
        stripped = line.strip()
        if any(text in stripped for text in unsafe_comments) or any(pattern.match(stripped) for pattern in unsafe_assignments):
            removed.append(line)
            continue
        keep.append(line)
    suffix = "\n" if post_text.endswith(("\n", "\r\n")) else ""
    return "\n".join(keep) + suffix, removed


def _harmonize_post_layer_variable(model_path: Path, post_path: Path, job_dir: Path) -> dict[str, Any]:
    """Keep the shared S2 post processor aligned with model-specific layer names."""

    model_text = model_path.read_text(encoding="utf-8", errors="replace")
    post_text = post_path.read_text(encoding="utf-8", errors="replace")
    post_text, removed_unsafe_aliases = _remove_unsafe_post_layer_aliases(post_text)
    model_has_senum = re.search(r"(?im)^\s*senum\s*=", model_text) is not None
    model_has_senum1 = re.search(r"(?im)^\s*senum1\s*=", model_text) is not None
    model_has_qiancengshu = re.search(r"(?im)^\s*qiancengshu\s*=", model_text) is not None
    model_has_houcengshu = re.search(r"(?im)^\s*houcengshu\s*=", model_text) is not None
    post_has_senum_assignment = re.search(r"(?im)^\s*senum\s*=", post_text) is not None
    marker = "NODENUM=3*senum"
    updated_text = post_text
    if post_has_senum_assignment or marker not in post_text:
        payload = {
            "status": "not_applicable",
            "model_has_senum": model_has_senum,
            "model_has_senum1": model_has_senum1,
            "model_has_qiancengshu": model_has_qiancengshu,
            "model_has_houcengshu": model_has_houcengshu,
            "post_has_senum_assignment": post_has_senum_assignment,
            "removed_unsafe_aliases": removed_unsafe_aliases,
            "policy": "Post processor already has a safe layer assignment or does not use senum.",
        }
    elif not model_has_senum and model_has_qiancengshu:
        assignments = ["senum=qiancengshu"]
        if model_has_houcengshu:
            assignments.append("senum1=houcengshu")
        updated_text = post_text.replace(marker, "\n".join(assignments) + f"\n{marker}", 1)
        payload = {
            "status": "applied",
            "assignment": assignments,
            "removed_unsafe_aliases": removed_unsafe_aliases,
            "source_ref": f"{model_path.name}: defines qiancengshu/houcengshu; {post_path.name}: uses senum/senum1",
            "policy": "The shared extraction macro uses senum/senum1 for layer loops; parameterized models expose front/back layer counts as qiancengshu/houcengshu.",
        }
    elif model_has_senum or not model_has_senum1:
        payload = {
            "status": "removed_unsafe_aliases" if removed_unsafe_aliases else "not_applicable",
            "model_has_senum": model_has_senum,
            "model_has_senum1": model_has_senum1,
            "model_has_qiancengshu": model_has_qiancengshu,
            "model_has_houcengshu": model_has_houcengshu,
            "post_has_senum_assignment": post_has_senum_assignment,
            "removed_unsafe_aliases": removed_unsafe_aliases,
            "policy": "Model does not need an additional layer-count alias.",
        }
    else:
        updated_text = post_text.replace(marker, f"senum=senum1\n{marker}", 1)
        payload = {
            "status": "applied",
            "assignment": "senum=senum1",
            "removed_unsafe_aliases": removed_unsafe_aliases,
            "source_ref": f"{model_path.name}: defines senum1 but not senum; {post_path.name}: uses NODENUM=3*senum",
            "policy": "The shared extraction macro uses senum for layer loops; single-side different-width command sources name the governing layer count senum1.",
        }
    if updated_text != post_path.read_text(encoding="utf-8", errors="replace"):
        post_path.write_text(updated_text, encoding="utf-8", newline="\n")
    (job_dir / "post_layer_variable_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def render_standard_command_package(
    job_dir: Path | str,
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
    package_id: str | None = None,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    source_root = Path(source_root)
    package_root = find_standard_command_package(source_root, package_id) if package_id else source_root
    model_source = _first_file(package_root, MODEL_PATTERNS)
    solve_source = _first_file(package_root, SOLVE_PATTERNS)
    post_source = _first_file(source_root, POST_FILE_NAME)

    mappings = [
        (model_source, job_dir / "generated_model.mac"),
        (solve_source, job_dir / "generated_solve.mac"),
        (post_source, job_dir / "generated_post.mac"),
    ]
    traces = [_write_decoded_copy(source, target) for source, target in mappings]
    source_conflict_audit = apply_source_conflict_resolutions(job_dir, package_id=package_id)
    keypoint_guard_audit = guard_undefined_keypoint_coordinate_refs(job_dir / "generated_model.mac")
    post_layer_audit = _harmonize_post_layer_variable(
        job_dir / "generated_model.mac", job_dir / "generated_post.mac", job_dir
    )
    command_header_audit = _prepend_command_headers(job_dir)
    post_alignment_audit = align_postprocessor_to_intake(job_dir)
    section_export_audit = augment_square_support_export(job_dir / "generated_post.mac")
    section_trace = _copy_required_sections(job_dir, source_root, job_dir / "generated_model.mac")
    _sync_input_sections(job_dir, section_trace)
    alias_audit = write_command_aliases(job_dir)
    master_audit = build_run_all_macro(job_dir)
    apdl_audit = audit_rendered_apdl([target for _, target in mappings], job_dir / "apdl_audit.json")
    missing_sections = [item for item in section_trace if item["status"] != "copied"]
    status = "fail" if missing_sections else "pass"
    if status == "pass" and apdl_audit["status"] != "pass":
        status = "needs_review"
    payload = {
        "status": status,
        "package_id": package_id,
        "package_root": str(package_root),
        "rendered_files": [target.name for _, target in mappings],
        "source_traces": traces,
        "source_conflict_resolutions": source_conflict_audit,
        "model_keypoint_guard": keypoint_guard_audit,
        "post_layer_variable": post_layer_audit,
        "command_headers": command_header_audit,
        "postprocessor_alignment": post_alignment_audit,
        "section_specific_export": section_export_audit,
        "sections": section_trace,
        "command_aliases": alias_audit,
        "master_macro_audit": master_audit,
        "apdl_audit": apdl_audit,
        "audit_policy": "Generated command streams are decoded copies of existing standard PIP/MAC sources for auditability; APDL audit findings are kept visible instead of being hidden.",
    }
    (job_dir / "command_source_traceability.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
