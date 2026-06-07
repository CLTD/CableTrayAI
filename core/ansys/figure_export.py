from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.ansys.config import AnsysLocalConfig, load_ansys_config
from core.ansys.command_builder import DEFAULT_HIGH_MODAL_NPROC_CAP_THRESHOLD
from core.ansys.master_macro import resolve_master_job_name
from core.ansys.resources import resolve_ansys_nproc
from core.apdl.modal_policy import modal_mode_count_from_job_dir, modal_policy_audit, rewrite_modal_mode_count
from core.results.figure_collector import collect_figures
from core.validation.result_requirements import classify_job_requirements


FIGURE_EXPORT_MACRO = "export_figures.mac"
FIGURE_EXPORT_AUDIT = "figure_export_audit.json"
FIGURE_POST_MACRO = "generated_post_figure_export.mac"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _quote_apdl(value: str) -> str:
    return value.replace("'", "''")


def _job_modal_requirements(job_dir: Path) -> tuple[bool, bool]:
    try:
        requirements = classify_job_requirements(job_dir)
    except Exception:
        return True, True
    requires = requirements.get("requires") or {}
    requires_modal_analysis = bool(requires.get("modal_analysis"))
    required_figures = {str(name).upper() for name in requirements.get("required_figures") or []}
    requires_modal_figures = bool(requires.get("modal_figures")) or any(name.startswith("MOTAI-") for name in required_figures)
    return requires_modal_figures, requires_modal_analysis


def _loadcase_lines(job_dir: Path) -> list[str]:
    lines: list[str] = []
    for path in sorted(job_dir.iterdir(), key=lambda item: item.name.upper()):
        match = path.is_file() and path.suffix.lower().startswith(".l") and path.suffix[2:].isdigit()
        if not match:
            continue
        loadcase_id = path.suffix[2:]
        stem = _quote_apdl(path.stem)
        ext = _quote_apdl(path.suffix[1:])
        lines.append(f"LCFILE,{loadcase_id},'{stem}','{ext}',''")
    return lines


def _modal_figure_export_lines(modal_mode_count: int, *, write_frequency_table: bool = False) -> list[str]:
    solve_lines = [
        "! Export Appendix A modal figures with a bounded graphics-only modal solve.",
        "! This bounded solve is only for MOTAI images and appendix-A frequency tables.",
        "FINISH",
        "/SOL",
        "LSCLEAR,ALL",
        "CMSEL,S,YUESHU,NODE",
        "*GET,_CTAI_YUESHU_COUNT,NODE,0,COUNT",
        "*IF,_CTAI_YUESHU_COUNT,LE,0,THEN",
        "  ALLSEL,ALL",
        "*ELSE",
        "  D,ALL,,,,,,ALL",
        "  ALLSEL,ALL",
        "*ENDIF",
        "ANTYPE,2",
        f"MODOPT,LANB,{int(modal_mode_count)}",
        f"MXPAND,{int(modal_mode_count)},,,YES",
    ]
    if write_frequency_table:
        solve_lines.append("/OUTPUT,'Mode','oup',")
    solve_lines.extend(
        [
            "SOLVE",
            *([] if not write_frequency_table else ["/OUTPUT,TERM"]),
            "FINISH",
            "/POST1",
            "FILE,CableTrayAI_Run,rst",
        ]
    )
    figure_lines = [
        "SET,1,1",
        "/SHOW,PNG",
        "*CFOPEN,figure_export_names,txt,,APPEND",
        "*VWRITE,'MOTAI-1'",
        "(A256)",
        "*CFCLOS",
        "PLDISP,0",
        "/SHOW,CLOSE",
        "SET,1,2",
        "/SHOW,PNG",
        "*CFOPEN,figure_export_names,txt,,APPEND",
        "*VWRITE,'MOTAI-2'",
        "(A256)",
        "*CFCLOS",
        "PLDISP,0",
        "/SHOW,CLOSE",
        "SET,1,3",
        "/SHOW,PNG",
        "*CFOPEN,figure_export_names,txt,,APPEND",
        "*VWRITE,'MOTAI-3'",
        "(A256)",
        "*CFCLOS",
        "PLDISP,0",
        "/SHOW,CLOSE",
        "SET,1,4",
        "/SHOW,PNG",
        "*CFOPEN,figure_export_names,txt,,APPEND",
        "*VWRITE,'MOTAI-4'",
        "(A256)",
        "*CFCLOS",
        "PLDISP,0",
        "/SHOW,CLOSE",
    ]
    return solve_lines + figure_lines


def _named_png_lines(image_name: str, plot_lines: list[str], *, note: str) -> list[str]:
    return [
        note,
        "*CFOPEN,figure_export_names,txt,,APPEND",
        f"*VWRITE,'{image_name}'",
        "(A256)",
        "*CFCLOS",
        "/SHOW,PNG",
        *plot_lines,
        "/SHOW,CLOSE",
    ]


def _named_model_png_lines(image_name: str, setup_lines: list[str], *, note: str) -> list[str]:
    """Write one report model PNG with a single plotting command.

    MAPDL batch graphics can emit a numbered PNG for every /REPLOT or /REP,FAST.
    Fig. 5.1/5.2 must map one recorded name to one real image, so all view,
    color and selection commands are applied before /SHOW,PNG and only EPLOT is
    executed while the PNG device is open.
    """

    return [
        note,
        *setup_lines,
        "*CFOPEN,figure_export_names,txt,,APPEND",
        f"*VWRITE,'{image_name}'",
        "(A256)",
        "*CFCLOS",
        "/SHOW,PNG",
        "EPLOT",
        "/SHOW,CLOSE",
    ]


def _model_figure_export_lines() -> list[str]:
    """Export report Fig. 5.1/5.2 before result contour commands run.

    The standard post command stream later creates many line-stress cloud plots.
    If Fig. 5.1/5.2 are saved from that contaminated graphics state, MAPDL can
    replay NODES or LINE STRESS instead of a finite-element model.  These two
    report figures are therefore rendered in PREP7 from the resumed database and
    the converted post macro skips their original /IMAGE,SAVE commands.
    """

    select_cantilever_types = [
        "ALLSEL,ALL",
        "ESEL,NONE",
        "! Fig. 5.2 is the tray-arm/cantilever model.  Select by section IDs",
        "! assigned in generated_model.mac (SEC 2/3 arm and SEC 10 auxiliary rods).",
        "! Do not include SEC 4 tray/cable elements here; report Fig. 5.2 is",
        "! the cantilever finite-element model, not a copy of the full tray model.",
        "ESEL,S,SEC,,2",
        "ESEL,A,SEC,,3",
        "ESEL,A,SEC,,10",
        "*GET,_CTAI_TB_ECOUNT,ELEM,0,COUNT",
        "*IF,_CTAI_TB_ECOUNT,LE,0,THEN",
        "  ! Fallback by coordinates: tray-arm elements are outside the square tube centerline.",
        "  ESEL,S,CENT,X,H1/2,H1/2+L1",
        "  ESEL,U,SEC,,1",
        "  ESEL,U,SEC,,4",
        "  *GET,_CTAI_TB_ECOUNT,ELEM,0,COUNT",
        "*ENDIF",
        "*IF,_CTAI_TB_ECOUNT,LE,0,THEN",
        "  ! Final fallback keeps Fig. 5.2 non-empty, and the audit flags SHITI/TBMODEL similarity.",
        "  ALLSEL,ALL",
        "*ELSE",
        "  NSLE,S",
        "*ENDIF",
    ]
    report_model_view = [
        "! Match the audited S2 post-PIP model figure style used in reports.",
        "! The original source exports SHITI after /VIEW + /ANG rotations and",
        "! indexed white/black plotting colors.  We intentionally suppress the",
        "! source /REPLOT and /REP,FAST intermediate frames here, then issue a",
        "! single EPLOT per figure so names map deterministically to PNG files.",
        "/ESHAPE,0",
        "/RGB,INDEX,100,100,100,0",
        "/RGB,INDEX,80,80,80,13",
        "/RGB,INDEX,60,60,60,14",
        "/RGB,INDEX,0,0,0,15",
        "/VIEW,1,,-1",
        "/ANG,1",
        "/AUTO,1",
        "/ANG,1,30,YS,1",
        "/ANG,1,30,XS,1",
        "/AUTO,1",
    ]
    return [
        "! Export report model figures in a clean PREP7 graphics context.",
        "FINISH",
        "/PREP7",
        "ALLSEL,ALL",
        "/GRAPHICS,POWER",
        "/DEVICE,VECTOR,0",
        "/PNGR,COLOR,2",
        "/PLOPTS,INFO,3",
        "/PLOPTS,LEG1,0",
        "/PLOPTS,LEG2,0",
        "/PLOPTS,LEG3,0",
        "/PLOPTS,FRAME,1",
        "/PLOPTS,TITLE,0",
        "/PLOPTS,MINM,0",
        "/PLOPTS,LOGO,0",
        *_named_model_png_lines(
            "SHITI",
            ["ALLSEL,ALL", *report_model_view],
            note="! Fig. 5.1: whole S2 finite-element model, source-PIP view/style.",
        ),
        *_named_model_png_lines(
            "TBMODEL",
            [*select_cantilever_types, *report_model_view],
            note="! Fig. 5.2: cantilever/tray-arm finite-element model from section IDs, source-PIP view/style.",
        ),
        "/PNGR,COLOR,2",
        "/COLOR,DEFA",
        "ALLSEL,ALL",
        "FINISH",
        "/POST1",
    ]


def _stress_figure_display_lines() -> list[str]:
    """Restore report-style line-stress legends before source PLLS plots.

    Fig. 5.1/5.2 model export deliberately suppresses most legends so the
    model pictures are clean.  The following PLLS cloud plots must not inherit
    that state: report appendix stress figures need the LINE STRESS block,
    min/max markers and color legend, while the ANSYS version/date stamp is
    unnecessary noise for comparing against Chapter 6 numbers.
    """

    return [
        "! Restore report-style line-stress figure display before source PLLS plots.",
        "! Keep multi-legend LINE STRESS/min/max/color scale; the collector removes the right version/date stamp.",
        "/PLOPTS,INFO,3",
        "/PLOPTS,LEG1,1",
        "/PLOPTS,LEG2,0",
        "/PLOPTS,LEG3,1",
        "/PLOPTS,FRAME,1",
        "/PLOPTS,TITLE,1",
        "/PLOPTS,MINM,1",
        "/PLOPTS,LOGO,0",
        "/UDOC,1,DATE,0",
        "/PNGR,COLOR,2",
    ]


def _build_named_figure_post_macro(source: Path, target: Path) -> dict[str, Any]:
    image_save_count = 0
    skipped_model_images: list[str] = []
    output_lines: list[str] = []
    pattern = re.compile(
        r"^\s*/image\s*,\s*save\s*,\s*([^,\s]+)\s*,\s*bmp\b.*$",
        flags=re.IGNORECASE,
    )
    plot_pattern = re.compile(r"^\s*(PLLS\b|PLDISP\b|EPLOT\b|NPLOT\b|/REPLOT\b)", flags=re.IGNORECASE)
    source_lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    model_image_names = {"SHITI", "TBMODEL", "TUOBI_MODEL", "TUOBI_MO"}

    def named_plot_block(image_name: str, source_line: str, plot_lines: list[str] | None = None) -> list[str]:
        lines = [
            f"! CableTrayAI named PNG export converted from source line: {source_line.strip()}",
            "*CFOPEN,figure_export_names,txt,,APPEND",
            f"*VWRITE,'{image_name}'",
            "(A256)",
            "*CFCLOS",
            "/SHOW,PNG",
        ]
        lines.extend(plot_lines or ["/REPLOT"])
        lines.append("/SHOW,CLOSE")
        return lines

    def model_plot_lines(image_name: str) -> list[str] | None:
        name = image_name.upper()
        if name == "SHITI":
            return [
                "! Fig. 5.1 must be a whole finite-element model plot, not a replayed node plot.",
                "ALLSEL,ALL",
                "/ESHAPE,1",
                "EPLOT",
            ]
        if name in {"TBMODEL", "TUOBI_MODEL", "TUOBI_MO"}:
            return [
                "! Fig. 5.2 must use the current cantilever/tray-arm element selection.",
                "/ESHAPE,1",
                "EPLOT",
            ]
        return None

    while index < len(source_lines):
        line = source_lines[index]
        match = pattern.match(line)
        if match:
            # If a source image-save line has no directly preceding plot command,
            # still record the name and flush the current plot buffer.
            image_name = match.group(1).strip()
            if image_name.upper() in model_image_names:
                skipped_model_images.append(image_name.upper())
                output_lines.append(
                    f"! CableTrayAI: skipped source {line.strip()} because Fig. 5 model images "
                    "are exported in PREP7 before result contour commands."
                )
                index += 1
                continue
            image_save_count += 1
            output_lines.extend(named_plot_block(image_name, line, model_plot_lines(image_name)))
            index += 1
            continue
        next_match = pattern.match(source_lines[index + 1]) if index + 1 < len(source_lines) else None
        if next_match and plot_pattern.match(line):
            image_name = next_match.group(1).strip()
            if image_name.upper() in model_image_names:
                skipped_model_images.append(image_name.upper())
                output_lines.append(line)
                output_lines.append(
                    f"! CableTrayAI: skipped source {source_lines[index + 1].strip()} because Fig. 5 "
                    "model images are exported in PREP7 before result contour commands."
                )
                index += 2
                continue
            image_save_count += 1
            plot_lines = model_plot_lines(image_name) or [line]
            output_lines.extend(named_plot_block(image_name, source_lines[index + 1], plot_lines))
            index += 2
            continue
        output_lines.append(line)
        index += 1
    target.write_text("\n".join(output_lines) + "\n", encoding="utf-8", newline="\n")
    return {
        "source": source.name,
        "target": target.name,
        "converted_image_save_commands": image_save_count,
        "skipped_model_image_saves": skipped_model_images,
        "policy": "Convert /IMAGE,SAVE,<name>,BMP from the standard post PIP into named /SHOW,<name>,PNG blocks for reliable batch export.",
    }


def build_figure_export_macro(job_dir: Path | str, *, output_name: str = FIGURE_EXPORT_MACRO) -> dict[str, Any]:
    """Create a post-only APDL macro that forces batch graphics output.

    The macro deliberately calls the job-local generated_post.mac instead of
    reimplementing plot selections.  That keeps the cloud plots tied to the
    audited standard PIP post-processing command stream.
    """

    job_dir = Path(job_dir)
    job_name = resolve_master_job_name(job_dir)
    generated_post = job_dir / "generated_post.mac"
    figure_post = job_dir / FIGURE_POST_MACRO
    names_path = job_dir / "figure_export_names.txt"
    if names_path.exists():
        names_path.unlink()
    requires_modal_figures, requires_modal_analysis = _job_modal_requirements(job_dir)
    modal_mode_count = modal_mode_count_from_job_dir(job_dir) if requires_modal_analysis else None
    db_file = job_dir / f"{job_name}.db"
    rst_file = job_dir / f"{job_name}.rst"
    missing = [
        name
        for name, path in {
            "generated_post.mac": generated_post,
            f"{job_name}.db": db_file,
            f"{job_name}.rst": rst_file,
        }.items()
        if not path.exists()
    ]

    loadcase_lines = _loadcase_lines(job_dir)
    converted_post = (
        _build_named_figure_post_macro(generated_post, figure_post)
        if generated_post.exists()
        else {"source": generated_post.name, "target": figure_post.name, "converted_image_save_commands": 0}
    )
    if figure_post.exists():
        figure_post_text = figure_post.read_text(encoding="utf-8", errors="replace")
        if requires_modal_analysis and re.search(r"(?im)^\s*(MT\s*=|MODOPT\s*,\s*LANB\s*,)", figure_post_text):
            figure_post.write_text(
                rewrite_modal_mode_count(figure_post_text, modal_mode_count),
                encoding="utf-8",
                newline="\n",
            )
    lines = [
        "! CableTrayAI post-only figure export macro",
        "! Reuses generated_post.mac so plots follow the audited source PIP logic.",
        "/BATCH",
        f"/FILNAME,{job_name},1",
        f"/CWD,'{_quote_apdl(str(job_dir.resolve()))}'",
        f"RESUME,{job_name},db",
        "/POST1",
        "ALLSEL,ALL",
        "/GRAPHICS,POWER",
        "/DEVICE,VECTOR,0",
        "/ESHAPE,1",
        "/PLOPTS,INFO,1",
        "/PLOPTS,LEG1,1",
        "/PLOPTS,LEG2,0",
        "/PLOPTS,LEG3,1",
        "/PLOPTS,FRAME,1",
        "/PLOPTS,TITLE,1",
        "/PLOPTS,MINM,1",
        "/PLOPTS,LOGO,0",
        "/UDOC,1,DATE,0",
        "/VIEW,1,1,1,1",
        "/AUTO,1",
        "/REPLOT",
        "! Register existing load-case files because this is a fresh post-only MAPDL session.",
        *loadcase_lines,
        *_model_figure_export_lines(),
        *_stress_figure_display_lines(),
        "! generated_post_figure_export.mac opens /SHOW,PNG only at each saved plot.",
        f"! Run the named-image copy of generated_post.mac; selections and plots remain source-derived.",
        f"/INPUT,{figure_post.stem},mac",
        *(
            _modal_figure_export_lines(4, write_frequency_table=not requires_modal_analysis)
            if requires_modal_figures
            else []
        ),
        "/SHOW,CLOSE",
        "FINISH",
        "",
    ]
    macro_path = job_dir / output_name
    macro_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    payload = {
        "status": "fail" if missing else "ready",
        "macro": macro_path.name,
        "job_dir": str(job_dir.resolve()),
        "ansys_job_name": job_name,
        "entrypoint": figure_post.name,
        "missing_inputs": missing,
        "graphics_device": "PNG per saved plot",
        "registered_load_cases": loadcase_lines,
        "converted_post_macro": converted_post,
        "modal_mode_policy": (
            modal_policy_audit({}, f"MT={modal_mode_count}")
            if requires_modal_analysis
            else {
                "status": "figure_only" if requires_modal_figures else "not_required",
                "analysis_method": "static" if requires_modal_figures else None,
                "modal_figure_mode_count": 4 if requires_modal_figures else None,
                "writes_frequency_table": bool(requires_modal_figures and not requires_modal_analysis),
                "policy": (
                    "Static-method jobs still export appendix-A MOTAI figures and the frequency table by running a fixed four-mode graphics-only modal solve during post-processing; this is not the main solve MT and has no 50 Hz cutoff gate."
                    if requires_modal_figures
                    else "This job does not require appendix-A modal figures."
                ),
            }
        ),
        "source_policy": "Cloud images are generated from a mechanically converted copy of generated_post.mac; each executed /IMAGE,SAVE point is replayed to the batch PNG device and then renamed to the standard PIP image name.",
    }
    _write_json(job_dir / "figure_export_macro_audit.json", payload)
    return payload


def build_figure_export_command(config: AnsysLocalConfig, job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir).resolve()
    macro_audit = build_figure_export_macro(job_dir)
    ansys = config.ansys
    executable = ansys.executable or "ANSYS_EXECUTABLE_NOT_CONFIGURED"
    job_name = resolve_master_job_name(job_dir)
    input_file = job_dir / FIGURE_EXPORT_MACRO
    output_file = job_dir / "export_figures.out"
    command: list[str] = [
        executable,
        "-b",
        "-j",
        job_name,
        "-i",
        str(input_file),
        "-o",
        str(output_file),
        "-dir",
        str(job_dir),
    ]
    if ansys.product:
        command.extend(["-p", ansys.product])
    resolved_nproc = resolve_ansys_nproc(ansys.nproc, ansys.nproc_percent)
    requested_nproc = resolved_nproc.nproc
    requires_modal_figures, requires_modal_analysis = _job_modal_requirements(job_dir)
    modal_mode_count = modal_mode_count_from_job_dir(job_dir) if requires_modal_analysis else None
    effective_nproc = requested_nproc
    nproc_source = resolved_nproc.source
    high_modal_cap_applied = False
    high_modal_cap = ansys.high_modal_nproc_cap
    high_modal_threshold = ansys.high_modal_nproc_cap_threshold or DEFAULT_HIGH_MODAL_NPROC_CAP_THRESHOLD
    if (
        high_modal_cap
        and high_modal_cap > 0
        and modal_mode_count is not None
        and modal_mode_count >= high_modal_threshold
        and (effective_nproc is None or effective_nproc > high_modal_cap)
    ):
        effective_nproc = high_modal_cap
        nproc_source = f"{nproc_source}+explicit_high_modal_cap"
        high_modal_cap_applied = True
    if effective_nproc:
        command.extend(["-np", str(effective_nproc)])
    if ansys.memory:
        command.extend(["-m", str(ansys.memory)])
    command.extend(ansys.extra_args)
    payload = {
        "mode": "figure_export",
        "command": command,
        "command_line": " ".join(f'"{part}"' if " " in part else part for part in command),
        "job_dir": str(job_dir),
        "ansys_job_name": job_name,
        "input_file": str(input_file),
        "output_file": str(output_file),
        "macro_audit": macro_audit,
        "resources": {
            "nproc": effective_nproc,
            "requested_nproc_before_modal_cap": requested_nproc,
            "nproc_source": nproc_source,
            "nproc_percent": resolved_nproc.nproc_percent,
            "logical_processors": resolved_nproc.logical_processors,
            "modal_mode_count": modal_mode_count,
            "modal_mode_count_status": "required" if requires_modal_analysis else ("figure_only_static_method" if requires_modal_figures else "not_required"),
            "high_modal_nproc_cap_threshold": high_modal_threshold,
            "high_modal_nproc_cap": high_modal_cap,
            "high_modal_nproc_cap_applied": high_modal_cap_applied,
        },
    }
    _write_json(job_dir / "figure_export_command.json", payload)
    return payload


def _is_valid_png(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def _read_exported_names(job_dir: Path) -> list[str]:
    path = job_dir / "figure_export_names.txt"
    if not path.exists():
        return []
    names: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        value = line.strip().strip("'").strip('"')
        if value and value not in names:
            names.append(value)
    return names


def _normalise_recorded_name(name: str) -> str:
    upper = name.upper().rstrip("+-")
    replacements = {
        "SQ-A1SDI": "SQ-A1SDIR1",
        "SQ-B1SDI": "SQ-B1SDIR1",
        "SQ-D1SDI": "SQ-D1SDIR1",
        "SQ-A2SDI": "SQ-A2SDIR2",
        "SQ-B2SDI": "SQ-B2SDIR2",
        "SQ-D2SDI": "SQ-D2SDIR2",
        "SQ-A3SBE": "SQ-A3SBEND",
        "SQ-B3SBE": "SQ-B3SBEND",
        "SQ-D3SBE": "SQ-D3SBEND",
        "SQ-A4SHE": "SQ-A4SHEAR",
        "SQ-B4SHE": "SQ-B4SHEAR",
        "SQ-D4SHE": "SQ-D4SHEAR",
    }
    if upper in replacements:
        return replacements[upper]
    match = re.match(r"^([ABD])([124])(SDIR|SHEAR)", upper)
    if match and match.group(2) == "1" and upper.startswith(f"{match.group(1)}1SDIR1"):
        return f"{match.group(1)}1SDIR1"
    if match and match.group(2) == "2" and upper.startswith(f"{match.group(1)}2SDIR2"):
        return f"{match.group(1)}2SDIR2"
    if match and match.group(2) == "4":
        return f"{match.group(1)}4SHEAR"
    if re.match(r"^[ABD]3SBEND", upper):
        return f"{upper[0]}3SBEND"
    return upper


def _normalise_named_pngs(job_dir: Path, job_name: str, started: datetime) -> dict[str, Any]:
    names = _read_exported_names(job_dir)
    timestamp_floor = started.timestamp() - 2
    generic_pattern = re.compile(rf"^{re.escape(job_name.upper())}\d{{3}}\.PNG$")
    generic_pngs = [
        path
        for path in job_dir.glob("*.png")
        if generic_pattern.match(path.name.upper())
        and path.stat().st_mtime >= timestamp_floor
        and _is_valid_png(path)
    ]
    generic_pngs.extend(
        path
        for path in job_dir.glob("*.PNG")
        if generic_pattern.match(path.name.upper())
        and path.stat().st_mtime >= timestamp_floor
        and _is_valid_png(path)
    )
    unique = {path.resolve().as_posix().lower(): path for path in generic_pngs}
    generic_pngs = sorted(unique.values(), key=lambda item: (item.stat().st_mtime, item.name.upper()))
    if len(generic_pngs) > len(names):
        # MAPDL may emit extra trailing PNG frames after the named plot blocks
        # have finished.  The recorded names are written immediately before
        # each intended /SHOW,PNG plot, so the first N fresh job-name PNGs are
        # the stable one-to-one mapping.  Taking the last N shifts Fig. 5.1/5.2
        # onto later SQ/cloud plots and makes report model images wrong.
        generic_pngs = generic_pngs[: len(names)] if names else []

    copied: list[dict[str, str]] = []
    for source, raw_name in zip(generic_pngs, names):
        safe_name = _normalise_recorded_name(raw_name).replace("\\", "-").replace("/", "-").replace(":", "-")
        target = job_dir / f"{safe_name}.PNG"
        shutil.copy2(source, target)
        copied.append({"source": source.name, "target": target.name})
    return {
        "recorded_names": len(names),
        "generic_pngs": len(generic_pngs),
        "copied_named_pngs": len(copied),
        "mappings": copied,
    }


def _cleanup_previous_generic_pngs(job_dir: Path, job_name: str) -> list[str]:
    """Remove stale MAPDL auto-numbered PNGs before a new figure export.

    Named output images such as SHITI.PNG and SQ-B1SDIR1.PNG are preserved and
    overwritten after export.  Only the transient CableTrayAI_Run###.png files
    are removed so the normaliser maps this run's images, not leftovers.
    """

    generic_pattern = re.compile(rf"^{re.escape(job_name.upper())}\d{{3}}\.PNG$")
    removed: list[str] = []
    for path in list(job_dir.glob("*.png")) + list(job_dir.glob("*.PNG")):
        if not generic_pattern.match(path.name.upper()):
            continue
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            continue
    return sorted(set(removed))


def run_figure_export(
    job_dir: Path | str,
    config: AnsysLocalConfig | None = None,
    *,
    timeout_minutes: int | None = None,
) -> dict[str, Any]:
    """Run ANSYS in post-only mode to generate BMP/PNG cloud figures."""

    job_dir = Path(job_dir)
    config = config or load_ansys_config()
    command = build_figure_export_command(config, job_dir)
    started = datetime.now(timezone.utc)
    executable = Path(command["command"][0])
    if not executable.exists():
        audit = {
            "status": "rejected",
            "mode": "figure_export",
            "executed": False,
            "reason": f"ANSYS executable does not exist: {executable}",
            "command_file": "figure_export_command.json",
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(job_dir / FIGURE_EXPORT_AUDIT, audit)
        return audit
    if command["macro_audit"]["missing_inputs"]:
        audit = {
            "status": "rejected",
            "mode": "figure_export",
            "executed": False,
            "reason": "Missing post-processing inputs.",
            "missing_inputs": command["macro_audit"]["missing_inputs"],
            "command_file": "figure_export_command.json",
            "started_at": started.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        _write_json(job_dir / FIGURE_EXPORT_AUDIT, audit)
        return audit

    removed_generic_pngs = _cleanup_previous_generic_pngs(job_dir, command["ansys_job_name"])
    timeout_seconds = max(1, int((timeout_minutes or config.ansys.timeout_minutes) * 60))
    stdout_path = job_dir / "figure_export_stdout.log"
    stderr_path = job_dir / "figure_export_stderr.log"
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as stderr_handle:
            completed = subprocess.run(
                command["command"],
                cwd=str(job_dir),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
    except subprocess.TimeoutExpired:
        finished = datetime.now(timezone.utc)
        with stderr_path.open("a", encoding="utf-8", errors="replace") as stderr_handle:
            stderr_handle.write(f"\nFigure export exceeded timeout_seconds={timeout_seconds}.\n")
        audit = {
            "status": "failed",
            "mode": "figure_export",
            "executed": True,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "duration_seconds": (finished - started).total_seconds(),
            "returncode": None,
            "reason": f"Figure export exceeded timeout_seconds={timeout_seconds}.",
            "timeout_seconds": timeout_seconds,
            "command_file": "figure_export_command.json",
            "stdout_path": stdout_path.name,
            "stderr_path": stderr_path.name,
            "figure_count": 0,
            "notes": [
                "Post-only ANSYS figure export timed out and was blocked.",
                "The main result must not be published with missing or stale cloud figures.",
            ],
        }
        _write_json(job_dir / FIGURE_EXPORT_AUDIT, audit)
        return audit
    finished = datetime.now(timezone.utc)
    naming = _normalise_named_pngs(job_dir, command["ansys_job_name"], started)
    figures = collect_figures(job_dir, output_manifest=True)
    requirements_path = job_dir / "result_requirements.json"
    requirements = json.loads(requirements_path.read_text(encoding="utf-8")) if requirements_path.exists() else {}
    required = {str(name).upper() for name in requirements.get("required_figures", [])}
    present = {str(item.get("source_file") or "").upper() for item in figures}
    missing_required = sorted(required - present)
    audit = {
        "status": "success" if completed.returncode == 0 and figures and not missing_required else "failed",
        "mode": "figure_export",
        "executed": True,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "returncode": completed.returncode,
        "naming": naming,
        "removed_stale_generic_pngs": removed_generic_pngs,
        "command_file": "figure_export_command.json",
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "figure_count": len(figures),
        "required_figure_count": len(required),
        "missing_required_figures": missing_required,
        "bmp_count": len(list(job_dir.glob("*.bmp"))) + len(list(job_dir.glob("*.BMP"))),
        "png_count": len(list(job_dir.glob("*.png"))) + len(list(job_dir.glob("*.PNG"))),
        "notes": [
            "This is a post-only ANSYS invocation for cloud image export.",
            "It does not switch to mock data and does not overwrite source_materials.",
        ],
    }
    _write_json(job_dir / FIGURE_EXPORT_AUDIT, audit)
    return audit
