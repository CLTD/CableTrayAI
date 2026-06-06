from __future__ import annotations

import json
import re
from pathlib import Path


def _is_valid_png(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(8) == b"\x89PNG\r\n\x1a\n"
    except OSError:
        return False


def _figure_metadata(path: Path) -> dict:
    raw_stem = path.stem.upper()
    stem = re.sub(r"\d{3}$", "", raw_stem)
    if stem == "SHITI":
        return {
            "figure_type": "model",
            "category": "model",
            "case": None,
            "stress_type": None,
            "component_scope": "whole_model",
            "appendix": None,
        }
    if stem in {"TBMODEL", "TUOBI_MODEL", "TUOBI_MO"}:
        return {
            "figure_type": "model",
            "category": "model",
            "case": None,
            "stress_type": None,
            "component_scope": "cantilever_model",
            "appendix": None,
        }
    if stem.startswith("MOTAI-"):
        return {
            "figure_type": "modal",
            "category": "modal",
            "case": None,
            "stress_type": None,
            "component_scope": "modal",
            "appendix": "A",
        }
    square_match = re.match(r"^SQ[-_]?([ABD])[-_]?(\d?)(SDIR[12]?|SBEND\d?|SHEAR)", stem)
    if square_match:
        return {
            "figure_type": "stress",
            "category": "stress",
            "case": square_match.group(1),
            "stress_type": square_match.group(3),
            "component_scope": "square_support",
            "appendix": "B",
        }
    match = re.match(r"^T?([ABD])[-_]?(\d?)(SDIR[12]?|SBEND\d?|SHEAR)", stem)
    if match:
        component_scope = "cantilever_arm" if stem.startswith("T") else "source_beam_selection"
        return {
            "figure_type": "stress",
            "category": "stress",
            "case": match.group(1),
            "stress_type": match.group(3),
            "component_scope": component_scope,
            "appendix": "C" if component_scope == "cantilever_arm" else None,
        }
    if stem.startswith(("A-", "B-", "D-", "A_", "B_", "D_")):
        parts = re.split(r"[-_]", stem, maxsplit=1)
        return {
            "figure_type": "stress",
            "category": "stress",
            "case": stem[0],
            "stress_type": parts[1] if len(parts) > 1 else None,
            "component_scope": "source_beam_selection",
            "appendix": None,
        }
    return {
        "figure_type": "figure",
        "category": "figure",
        "case": None,
        "stress_type": None,
        "component_scope": None,
        "appendix": None,
    }


def _convert_bmp_to_png(source: Path, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{source.stem}.png"
    try:
        from PIL import Image

        with Image.open(source) as image:
            image.save(target)
        return target
    except Exception:
        return source


def _image_quality(path: Path) -> dict:
    try:
        from PIL import Image

        with Image.open(path) as image:
            rgb = image.convert("RGB")
            pixels = list(rgb.getdata())
            if not pixels:
                return {"quality_status": "invalid", "non_background_percent": 0.0}
            non_background = sum(
                1
                for red, green, blue in pixels
                if not (red > 248 and green > 248 and blue > 248)
            )
            percent = round(non_background * 100.0 / len(pixels), 4)
            return {
                "quality_status": "blank_like" if percent < 0.2 else "usable",
                "non_background_percent": percent,
                "width_px": rgb.width,
                "height_px": rgb.height,
            }
    except Exception as exc:
        return {"quality_status": "unknown", "quality_error": str(exc)}


def _strip_ansys_version_stamp(path: Path, metadata: dict) -> dict:
    """Remove the right-side ANSYS version/date stamp from stress cloud figures.

    MAPDL's `PLLS` legend that contains LINE STRESS, STEP/SUB, MIN/MAX and
    ELEM depends on keeping an information legend enabled.  Turning INFO off
    removes the useful engineering legend as well as the noisy version stamp.
    We therefore keep the native engineering legend during export and only
    paint over the software-version area in the copied report PNG.
    """

    if metadata.get("figure_type") != "stress":
        return {"status": "skipped", "reason": "not_stress_figure"}
    try:
        from PIL import Image, ImageDraw

        with Image.open(path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            if width < 240 or height < 120:
                return {"status": "skipped", "reason": "image_too_small"}
            x0 = max(int(width * 0.74), width - 280)
            y1 = min(height, max(130, int(height * 0.18)))
            draw = ImageDraw.Draw(rgb)
            draw.rectangle((x0, 0, width, y1), fill=(255, 255, 255))
            rgb.save(path)
            return {
                "status": "pass",
                "operation": "strip_ansys_version_stamp",
                "removed_box": [x0, 0, width, y1],
                "legend_policy": "Keep native LINE STRESS/min/max legend; remove ANSYS version/date stamp only.",
            }
    except Exception as exc:
        return {"status": "warning", "operation": "strip_ansys_version_stamp", "error": str(exc)}


def collect_figures(job_dir: Path | str, output_manifest: bool = True) -> list[dict]:
    job_dir = Path(job_dir)
    requirements_path = job_dir / "result_requirements.json"
    required_figure_names: set[str] | None = None
    forbidden_figure_names: set[str] = set()
    if requirements_path.exists():
        try:
            requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
            required_figure_names = {str(name).upper() for name in requirements.get("required_figures", [])}
            forbidden_figure_names = {str(name).upper() for name in requirements.get("forbidden_figures", [])}
        except Exception:
            required_figure_names = None
    discovered = [
        *job_dir.glob("*.bmp"),
        *job_dir.glob("*.BMP"),
        *job_dir.glob("*.png"),
        *job_dir.glob("*.PNG"),
    ]
    discovered = [
        path
        for path in discovered
        if path.suffix.lower() != ".png" or _is_valid_png(path)
    ]
    unique_paths = {path.resolve().as_posix().lower(): path for path in discovered}
    figure_paths = sorted(unique_paths.values(), key=lambda item: item.name.upper())
    has_named_exports = any(not re.match(r"^(CABLETRAYAI_RUN|DJS)\d{3}\.PNG$", path.name.upper()) for path in figure_paths)
    if has_named_exports:
        figure_paths = [
            path
            for path in figure_paths
            if not re.match(r"^(CABLETRAYAI_RUN|DJS)\d{3}\.PNG$", path.name.upper())
        ]
    canonical_stems = {path.stem.upper() for path in figure_paths}
    filtered_paths: list[Path] = []
    for path in figure_paths:
        stem = path.stem.upper()
        if re.match(r"^SQ[-_][ABD][1234](SDI|SBE|SHE)$", stem):
            continue
        if stem[-1:] in "+-" and re.match(r"^[ABD][12]SDIR[12][+-]?$", stem) and stem.rstrip("+-") in canonical_stems:
            continue
        if stem[-1:] in "+-" and re.match(r"^[ABD]4SHEAR[+-]?$", stem) and stem.rstrip("+-") in canonical_stems:
            continue
        bend_match = re.match(r"^([ABD])3SBEND\d", stem)
        if bend_match and f"{bend_match.group(1)}3SBEND" in canonical_stems:
            continue
        filtered_paths.append(path)
    figure_paths = filtered_paths
    if required_figure_names is not None:
        figure_paths = [
            path
            for path in figure_paths
            if path.name.upper() in required_figure_names or f"{path.stem}.PNG".upper() in required_figure_names
        ]
    elif forbidden_figure_names:
        figure_paths = [path for path in figure_paths if path.name.upper() not in forbidden_figure_names]
    else:
        report_required_paths: list[Path] = []
        for path in figure_paths:
            metadata = _figure_metadata(path)
            if metadata["figure_type"] in {"model", "modal"}:
                report_required_paths.append(path)
                continue
            if metadata["figure_type"] == "stress" and metadata["component_scope"] in {"square_support", "cantilever_arm"} and metadata["case"] in {"B", "D"}:
                report_required_paths.append(path)
        if report_required_paths:
            figure_paths = report_required_paths
    manifest: list[dict] = []
    for index, source in enumerate(figure_paths, start=1):
        metadata = _figure_metadata(source)
        target = _convert_bmp_to_png(source, job_dir / "figures") if source.suffix.lower() == ".bmp" else source
        display_postprocess = _strip_ansys_version_stamp(target, metadata)
        relative_target = target.relative_to(job_dir).as_posix() if target.is_relative_to(job_dir) else target.name
        relative_source = source.relative_to(job_dir).as_posix() if source.is_relative_to(job_dir) else source.name
        caption_parts = [metadata["figure_type"]]
        if metadata["case"]:
            caption_parts.append(f"case {metadata['case']}")
        if metadata["stress_type"]:
            caption_parts.append(metadata["stress_type"])
        manifest.append(
            {
                "figure_id": f"FIG-{index:03d}",
                "path": relative_target,
                "source_file": relative_source,
                "target_file": relative_target,
                "category": metadata["category"],
                "figure_type": metadata["figure_type"],
                "load_case": metadata["case"],
                "case": metadata["case"],
                "stress_type": metadata["stress_type"],
                "component_scope": metadata["component_scope"],
                "appendix": metadata["appendix"],
                "caption": " ".join(caption_parts),
                "source_ref": source.name,
                "display_postprocess": display_postprocess,
                "image_quality": _image_quality(target),
            }
        )
    if output_manifest:
        (job_dir / "figures_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return manifest
