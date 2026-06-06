from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from core.ansys.master_macro import build_run_all_macro
from core.apdl.audit import audit_rendered_apdl
from core.apdl.command_aliases import write_command_aliases
from core.apdl.intake_template_context import build_standard_s2_template_context
from core.apdl.postprocessor_alignment import align_postprocessor_to_intake
from core.apdl.section_specific_export import augment_square_support_export
from core.apdl.standard_command_renderer import _prepend_command_headers
from core.schemas.input_models import CableTrayInput, model_to_dict, parse_cable_input


TEMPLATE_MAP = {
    "generated_model.mac": "geometry_s2.mac.j2",
    "generated_solve.mac": "solve_spectrum.mac.j2",
    "generated_post.mac": "post_extract_s2.mac.j2",
}


_TRAY_SEGMENT_TRIPLET = """L,I+10*cengshu1+1,I+10*cengshu1+2
L,I+10*cengshu1+2,I+10*cengshu1+3
L,I+10*cengshu1+3,I+10*cengshu1+4"""

_TRAY_SEGMENT_GUARD = """L,I+10*cengshu1+1,I+10*cengshu1+2
! Guard: when B equals half tray width C, keypoints 2 and 3 coincide.
! Skip the zero-length middle line and connect keypoint 2 directly to 4.
_ctai_mid_delta=B%cengshu1%-0.5*C%cengshu1%
*IF,_ctai_mid_delta,GT,0.000001,THEN
L,I+10*cengshu1+2,I+10*cengshu1+3
L,I+10*cengshu1+3,I+10*cengshu1+4
*ELSEIF,_ctai_mid_delta,LT,-0.000001,THEN
L,I+10*cengshu1+2,I+10*cengshu1+3
L,I+10*cengshu1+3,I+10*cengshu1+4
*ELSE
L,I+10*cengshu1+2,I+10*cengshu1+4
*ENDIF"""


def _load_input(input_payload: CableTrayInput | dict | Path) -> CableTrayInput:
    if isinstance(input_payload, CableTrayInput):
        return input_payload
    if isinstance(input_payload, Path):
        return parse_cable_input(json.loads(input_payload.read_text(encoding="utf-8")))
    return parse_cable_input(input_payload)


def _guard_zero_length_tray_segments(path: Path) -> dict:
    """Prevent APDL failures from coincident tray-arm keypoints.

    Some valid intake geometries, especially narrow single-side tray layouts,
    make the source formula `A + B - C/2` equal to `A`. MAPDL refuses to create
    the resulting zero-length middle line. The guard preserves the two physical
    end segments by directly connecting keypoint 2 to 4 only in that degenerate
    case; normal source-command topology is unchanged.
    """

    text = path.read_text(encoding="utf-8")
    count = text.count(_TRAY_SEGMENT_TRIPLET)
    if not count:
        return {"status": "not_applicable", "replacements": 0}
    path.write_text(text.replace(_TRAY_SEGMENT_TRIPLET, _TRAY_SEGMENT_GUARD), encoding="utf-8", newline="\n")
    return {
        "status": "pass",
        "replacements": count,
        "policy": "Only zero-length tray-arm middle segments are bypassed; dimensions, loads, and sections are not changed.",
    }


def render_apdl_templates(
    job_id: str,
    input_payload: CableTrayInput | dict | Path,
    jobs_dir: Path | str = Path("jobs"),
    template_dir: Path | str = Path("templates/apdl"),
    source_root: Path | str = Path("source_materials/model_commands"),
) -> dict:
    job_dir = Path(jobs_dir) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    cable_input = _load_input(input_payload)
    input_path = job_dir / "input.json"
    if not input_path.exists():
        input_path.write_text(
            json.dumps(model_to_dict(cable_input), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    context = model_to_dict(cable_input)
    context.update(build_standard_s2_template_context(context))
    rendered_paths: list[Path] = []
    zero_length_guard_audit = {"status": "not_run", "replacements": 0}
    for output_name, template_name in TEMPLATE_MAP.items():
        rendered = environment.get_template(template_name).render(**context)
        output_path = job_dir / output_name
        output_path.write_text(rendered, encoding="utf-8", newline="\n")
        if output_name == "generated_model.mac":
            zero_length_guard_audit = _guard_zero_length_tray_segments(output_path)
        rendered_paths.append(output_path)

    command_header_audit = _prepend_command_headers(job_dir)
    post_alignment_audit = align_postprocessor_to_intake(job_dir, context)
    section_export_audit = augment_square_support_export(job_dir / "generated_post.mac")
    alias_audit = write_command_aliases(job_dir)
    section_copy_audit = _copy_input_sections(job_dir, cable_input, Path(source_root))
    master_macro_audit = build_run_all_macro(job_dir)
    audit = audit_rendered_apdl(rendered_paths, job_dir / "apdl_audit.json")
    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "rendered_files": [str(path) for path in rendered_paths],
        "section_specific_export": section_export_audit,
        "postprocessor_alignment": post_alignment_audit,
        "command_headers": command_header_audit,
        "command_aliases": alias_audit,
        "sections": section_copy_audit,
        "master_macro_audit": master_macro_audit,
        "zero_length_tray_segment_guard": zero_length_guard_audit,
        "audit": audit,
    }


def _copy_input_sections(job_dir: Path, cable_input: CableTrayInput, source_root: Path) -> list[dict]:
    section_dir = job_dir / "sections"
    section_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict] = []
    required_sections: dict[str, str] = {}
    for section in cable_input.sections:
        name = section.sect_file if section.sect_file.lower().endswith(".sect") else f"{section.sect_file}.SECT"
        required_sections[name] = "input.json:sections"

    generated_model = job_dir / "generated_model.mac"
    if generated_model.exists():
        text = generated_model.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"SECREAD\s*,\s*['\"]?([^,'\"\s]+)", text, flags=re.IGNORECASE):
            stem = match.group(1).strip()
            if not stem:
                continue
            name = stem if stem.lower().endswith(".sect") else f"{stem}.SECT"
            required_sections.setdefault(name, "generated_model.mac:SECREAD")

    for name, source_ref in required_sections.items():
        matches = sorted(source_root.rglob(name), key=lambda item: item.as_posix().upper())
        if not matches:
            copied.append({"section": name, "status": "missing", "source_ref": source_ref})
            continue
        source = matches[0]
        shutil.copy2(source, section_dir / name)
        shutil.copy2(source, job_dir / name)
        copied.append({"section": name, "status": "copied", "source": str(source), "source_ref": source_ref})
    return copied
