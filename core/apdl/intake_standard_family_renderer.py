from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from core.ansys.master_macro import build_run_all_macro
from core.apdl.audit import audit_rendered_apdl
from core.apdl.command_aliases import write_command_aliases
from core.apdl.intake_template_context import build_standard_s2_template_context
from core.apdl.keypoint_guard import guard_undefined_keypoint_coordinate_refs
from core.apdl.modal_policy import (
    modal_mode_count_from_payload,
    modal_policy_audit,
    parse_source_modal_mode_count,
    rewrite_modal_mode_count,
)
from core.apdl.section_specific_export import augment_square_support_export
from core.apdl.source_diff import read_text_with_encoding
from core.apdl.postprocessor_alignment import align_postprocessor_to_intake
from core.apdl.standard_command_renderer import _copy_required_sections, _prepend_command_headers, _sha256
from core.intake.tray_load_parser import LOAD_KG_PER_M, TRAY_AREA_M2
from core.optimizer.square_section_selector import parse_square_section_name
from core.spectra.static_coefficients import describe_segmented_spectrum_workbook, derive_static_acceleration_coefficients


MODEL_PATTERNS = ("01*.PIP", "01*.pip", "01*.MAC", "01*.mac", "01*.TXT", "01*.txt")
SOLVE_PATTERNS = ("02*.mac", "02*.MAC", "02*.PIP", "02*.pip", "02*.TXT", "02*.txt")


@dataclass(frozen=True)
class CommandFamily:
    path: Path
    source_encoding: str
    text: str
    side_kind: str
    support_section: str
    width_family: tuple[int, ...]
    primary_arm_section: str
    secondary_arm_section: str
    has_mixed_widths: bool
    has_back_side: bool


def _section_stem(value: Any, default: str = "") -> str:
    text = str(value or default).strip()
    if not text:
        return default
    return Path(text).stem


def _secreads(text: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"SECREAD\s*,\s*['\"]?([^,'\"\s]+)", text, flags=re.IGNORECASE)
    ]


def _tray_widths_from_sections(sections: list[str]) -> tuple[int, ...]:
    widths: list[int] = []
    for section in sections:
        match = re.search(r"(\d+)-75-2mm", section, flags=re.IGNORECASE)
        if match:
            width = int(match.group(1))
            if width not in widths:
                widths.append(width)
    return tuple(widths)


def _is_tray_section(section_name: str) -> bool:
    return bool(re.search(r"\d+-75-2mm", str(section_name or ""), flags=re.IGNORECASE))


def _arm_sections_from_sections(sections: list[str]) -> tuple[str, str]:
    """Return reviewed cantilever arm sections without treating tray slots as arms."""

    primary = ""
    secondary = ""
    for section in sections:
        name = str(section or "").strip()
        upper = name.upper()
        if _is_tray_section(name):
            continue
        if upper in {"50-42", "YIXINGGANG150"} and not primary:
            primary = name
        elif upper in {"CAOGANG42DAN", "YIXINGGANG150DAN"} and not secondary:
            secondary = name
    return primary, secondary


def _classify_source_side(path: Path, text: str) -> tuple[str, bool]:
    name = path.name
    has_back = bool(re.search(r"K\s*,\s*15\d\d", text, flags=re.IGNORECASE))
    if "三侧" in name:
        return "three_side", has_back
    if "单侧" in name or not has_back:
        return "single", has_back
    if "不同" in name:
        return "double_different", has_back
    return "double_same", has_back


def _payload_side_count(payload: dict[str, Any]) -> int:
    support = payload.get("support") or {}
    metadata = payload.get("metadata") or {}
    raw = support.get("side_count") or metadata.get("topology_side_count")
    if raw is None:
        if int(support.get("layers_third") or metadata.get("layers_third") or 0) > 0:
            return 3
        if int(support.get("layers_back") or 0) > 0:
            return 2
        return 1
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


def _discover_families(source_root: Path) -> list[CommandFamily]:
    reports_root = source_root / "报告及模型命令流"
    roots = [reports_root] if reports_root.exists() else [source_root]
    families: list[CommandFamily] = []
    for root in roots:
        for pattern in MODEL_PATTERNS:
            for path in sorted(root.rglob(pattern), key=lambda item: item.as_posix()):
                if not path.is_file() or path.name.lower().endswith(".bak") or "副本" in path.name:
                    continue
                try:
                    text, encoding = read_text_with_encoding(path)
                except Exception:
                    continue
                sections = _secreads(text)
                if len(sections) < 4 or not any("75-2mm" in item for item in sections):
                    continue
                side_kind, has_back = _classify_source_side(path, text)
                tray_widths = _tray_widths_from_sections(sections)
                if not tray_widths:
                    continue
                primary_arm_section, secondary_arm_section = _arm_sections_from_sections(sections)
                has_mixed_widths = len(tray_widths) > 1 or "不同" in path.name
                if has_back and has_mixed_widths:
                    side_kind = "double_different"
                families.append(
                    CommandFamily(
                        path=path,
                        source_encoding=encoding,
                        text=text,
                        side_kind=side_kind,
                        support_section=sections[0],
                        width_family=tray_widths,
                        primary_arm_section=primary_arm_section,
                        secondary_arm_section=secondary_arm_section,
                        has_mixed_widths=has_mixed_widths,
                        has_back_side=has_back,
                    )
                )
    return families


def _input_widths(payload: dict[str, Any]) -> list[int]:
    widths = []
    for layer in payload.get("tray_layers") or []:
        width = int(round(float(layer.get("tray_width_m") or 0.0) * 1000))
        if width > 0:
            widths.append(width)
    return widths


def _square_outer_width_mm_from_payload(payload: dict[str, Any]) -> float:
    support = payload.get("support") or {}
    metadata = payload.get("metadata") or {}
    for value in (
        metadata.get("square_section_selected"),
        metadata.get("square_section_spec"),
        metadata.get("square_section_current_model_spec"),
    ):
        parsed = parse_square_section_name(str(value or ""))
        if parsed:
            return parsed.outer_mm
    try:
        if metadata.get("square_section_outer_mm") is not None:
            return float(metadata["square_section_outer_mm"])
    except (TypeError, ValueError):
        pass
    support_section_id = str(support.get("support_section_id") or "")
    sections = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    candidates: list[Any] = []
    if support_section_id:
        section = sections.get(support_section_id)
        if section:
            candidates.extend([section.get("sect_file"), section.get("section_id")])
    for section in payload.get("sections") or []:
        candidates.extend([section.get("sect_file"), section.get("section_id")])
    for value in candidates:
        parsed = parse_square_section_name(str(value or ""))
        if parsed:
            return parsed.outer_mm
    try:
        return float(support.get("square_tube_width_m") or 0.0) * 1000.0
    except (TypeError, ValueError):
        return 0.0


def _arm_section_family(payload: dict[str, Any]) -> tuple[str, str, str]:
    square_outer_mm = _square_outer_width_mm_from_payload(payload)
    if square_outer_mm > 120.0:
        return "YIXINGGANG150", "YIXINGGANG150DAN", "square_gt_120_yixing_arm_family"
    return "50-42", "CAOGANG42DAN", "square_le_120_standard_channel_family"


def _score_family(family: CommandFamily, payload: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    support = payload.get("support") or {}
    front = int(support.get("layers_front") or 0)
    back = int(support.get("layers_back") or 0)
    side_count = _payload_side_count(payload)
    side_kind = "three_side" if side_count > 2 else ("single" if back == 0 else "double_same")
    widths = sorted(set(_input_widths(payload)))
    mixed = len(widths) > 1
    if side_count <= 2 and back and mixed:
        side_kind = "double_different"
    shared_max_geometry = bool(
        back
        and mixed
        and family.side_kind == "double_same"
        and len(family.width_family) == 1
        and widths
        and int(family.width_family[0]) == max(widths)
    )
    primary, secondary, _ = _arm_section_family(payload)
    sections_by_id = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    support_section_id = str(support.get("support_section_id") or "")
    expected_support_section = _section_stem((sections_by_id.get(support_section_id) or {}).get("sect_file") or support_section_id)
    expected_method = str((payload.get("metadata") or {}).get("analysis_method") or "").lower()
    source_method = _family_solve_method(family.path)
    source_senum = _assignment_number(family.text, "senum")
    source_senum1 = _assignment_number(family.text, "senum1")
    expected_primary_layers = max(front, back) if back else front
    expected_secondary_layers = min(front, back) if back else None
    score = 0
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, weight: int, value: Any, expected: Any) -> None:
        nonlocal score
        if passed:
            score += weight
        checks.append({"check_id": check_id, "status": "pass" if passed else "fail", "weight": weight, "value": value, "expected": expected})

    add("side_kind", family.side_kind == side_kind, 30, family.side_kind, side_kind)
    if expected_support_section:
        add(
            "support_section",
            _section_stem(family.support_section).upper() == expected_support_section.upper(),
            24,
            family.support_section,
            expected_support_section,
        )
    add("width_family", sorted(family.width_family) == widths, 25, list(family.width_family), widths)
    if widths:
        add("max_width_covered", max(widths) in family.width_family, 20, list(family.width_family), max(widths))
    add("primary_arm_section", family.primary_arm_section.upper() == primary.upper(), 20, family.primary_arm_section, primary)
    add("secondary_arm_section", family.secondary_arm_section.upper() == secondary.upper(), 10, family.secondary_arm_section, secondary)
    add("mixed_widths", family.has_mixed_widths == mixed, 8, family.has_mixed_widths, mixed)
    if source_senum is not None and expected_primary_layers:
        add("primary_layer_count", int(source_senum) == int(expected_primary_layers), 16, int(source_senum), int(expected_primary_layers))
    if back and source_senum1 is not None and expected_secondary_layers is not None:
        add("secondary_layer_count", int(source_senum1) == int(expected_secondary_layers), 8, int(source_senum1), int(expected_secondary_layers))
    if expected_method in {"static", "spectrum"}:
        add("analysis_method", source_method == expected_method, 12, source_method, expected_method)
    if shared_max_geometry:
        score += 34
        checks.append(
            {
                "check_id": "shared_max_width_geometry",
                "status": "pass",
                "weight": 34,
                "value": list(family.width_family),
                "expected": f"single shared geometry at max intake width {max(widths)} mm",
                "policy": "Mixed tray-load text may still use a same-geometry source family when the audited command stream models both sides at the governing maximum tray width; this is selected from command topology, not report values.",
            }
        )
    # Prefer compact source families over historical one-off variants when all
    # engineering features tie.
    add("not_backup", not family.path.name.lower().endswith(".bak"), 1, family.path.name, "not .bak")
    return score, checks


def _classify_solve_command(candidate: Path, text: str | None = None) -> str:
    name = candidate.name.lower()
    if "静力" in candidate.name or "static" in name:
        return "static"
    if text is None:
        try:
            text, _ = read_text_with_encoding(candidate)
        except Exception:
            text = ""
    lowered = text.lower()
    has_spectrum_tokens = "spopt" in lowered or "srss" in lowered or "spectrum" in lowered or "antype,8" in lowered
    if has_spectrum_tokens:
        return "spectrum"
    if "静力" in text or (re.search(r"\bANTYPE\s*,\s*0\b", text, flags=re.IGNORECASE) and re.search(r"\bACEL\s*,", text, flags=re.IGNORECASE)):
        return "static"
    return "unknown"


def _family_solve_method(model_source: Path) -> str:
    for pattern in SOLVE_PATTERNS:
        for candidate in sorted(model_source.parent.glob(pattern), key=lambda item: item.name.lower()):
            if not candidate.is_file() or candidate.name.lower().endswith(".bak"):
                continue
            try:
                text, _ = read_text_with_encoding(candidate)
            except Exception:
                text = ""
            method = _classify_solve_command(candidate, text)
            if method != "unknown":
                return method
            return "unknown"
    return "unknown"


def select_standard_model_family(payload: dict[str, Any], source_root: Path | str = Path("source_materials/model_commands")) -> dict[str, Any]:
    source_root = Path(source_root)
    families = _discover_families(source_root)
    if not families:
        raise FileNotFoundError(f"No APDL/PIP model families found under {source_root}")
    side_count = _payload_side_count(payload)
    metadata = payload.get("metadata") or {}
    if side_count > 2 and not metadata.get("allow_unvalidated_three_side_calculation"):
        raise ValueError(
            "S2 three-side intake was parsed, but three-side production calculation is blocked until an audited "
            "three-side APDL/PIP model family and extraction mapping are explicitly confirmed. CableTrayAI will "
            "not silently map a three-side topology onto a single/double-side command stream."
        )
    scored = []
    for family in families:
        score, checks = _score_family(family, payload)
        scored.append((score, family, checks))
    scored.sort(key=lambda item: (-item[0], item[1].path.as_posix()))
    best_score, best, best_checks = scored[0]
    if best_score <= 0:
        raise ValueError("No standard APDL/PIP model family matches the intake geometry.")
    return {
        "status": "pass",
        "source": str(best.path),
        "source_encoding": best.source_encoding,
        "score": best_score,
        "checks": best_checks,
        "candidate_count": len(families),
        "source_sha256": _sha256(best.path),
        "policy": "Select a reusable standard command-flow family by intake geometry, side/topology, tray width, and arm-section family. Report result values and numerical closeness are not used.",
    }


def _replace_assignment(text: str, name: str, value: float | int) -> str:
    pattern = rf"(?m)^(\s*{re.escape(name)}\s*=\s*)([-+]?(?:\d+(?:\.\d*)?|\.\d+))(.*)$"
    replacement = rf"\g<1>{value}\g<3>"
    updated, count = re.subn(pattern, replacement, text, count=1)
    return updated if count else text


def _replace_or_insert_assignment_after(text: str, name: str, value: float | int, anchor_name: str) -> str:
    pattern = rf"(?m)^(\s*{re.escape(name)}\s*=\s*)([-+]?(?:\d+(?:\.\d*)?|\.\d+))(.*)$"
    replacement = rf"\g<1>{value}\g<3>"
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count:
        return updated

    line = f"{name}={value:g}" if isinstance(value, float) else f"{name}={value}"
    anchor = rf"(?m)^(\s*{re.escape(anchor_name)}\s*=\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+).*)$"

    def insert_after_anchor(match: re.Match[str]) -> str:
        return f"{match.group(1)}\n{line}"

    updated, count = re.subn(anchor, insert_after_anchor, text, count=1)
    if count:
        return updated
    return f"{line}\n{text}" if text else line


def _assignment_number(text: str, name: str) -> float | None:
    match = re.search(
        rf"(?m)^\s*{re.escape(name)}\s*=\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))",
        text,
    )
    return float(match.group(1)) if match else None


def _replace_nth_secread(text: str, index: int, section_name: str) -> str:
    pattern = r"(SECREAD\s*,\s*')([^']+)(')"
    seen = -1

    def repl(match: re.Match[str]) -> str:
        nonlocal seen
        seen += 1
        if seen == index:
            return f"{match.group(1)}{section_name}{match.group(3)}"
        return match.group(0)

    return re.sub(pattern, repl, text, flags=re.IGNORECASE)


def _replace_density(text: str, material_id: int, density: float) -> str:
    pattern = rf"(?m)^(\s*MP\s*,\s*DENS\s*,\s*{material_id}\s*,\s*)([-+]?(?:\d+(?:\.\d*)?|\.\d+))(.*)$"
    updated, count = re.subn(pattern, rf"\g<1>{density:g}\g<3>", text, count=1, flags=re.IGNORECASE)
    return updated if count else text


def _expanded_tray_widths_for_source(source_widths: list[int], intake_widths: list[int]) -> list[int]:
    """Map source tray material/section slots to current intake tray widths.

    Source command families are reused for their reviewed topology, not for
    historical tray dimensions.  If the source has two tray-width slots and the
    intake is a uniform 500 mm tray, both source slots must become 500 mm.
    """
    if not intake_widths:
        return source_widths or [500]
    slot_count = max(len(source_widths), 1)
    if len(intake_widths) == 1:
        return [intake_widths[0]] * slot_count
    if slot_count <= len(intake_widths):
        return intake_widths[:slot_count]
    return intake_widths + [intake_widths[-1]] * (slot_count - len(intake_widths))


def _replace_tray_secreads_from_intake(text: str, intake_widths: list[int]) -> tuple[str, int]:
    pattern = r"(SECREAD\s*,\s*')([^']+)(')"
    tray_index = 0
    replacement_count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal tray_index, replacement_count
        section_name = match.group(2).strip()
        if not re.search(r"\d+-75-2mm", section_name, flags=re.IGNORECASE):
            return match.group(0)
        if not intake_widths:
            width = int(re.search(r"(\d+)-75-2mm", section_name, flags=re.IGNORECASE).group(1))
        elif len(intake_widths) == 1:
            width = intake_widths[0]
        else:
            width = intake_widths[min(tray_index, len(intake_widths) - 1)]
        tray_index += 1
        replacement_count += 1
        return f"{match.group(1)}{width}-75-2mm{match.group(3)}"

    return re.sub(pattern, repl, text, flags=re.IGNORECASE), replacement_count


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
        if section_name and _is_tray_section(section_name) and section_name not in required:
            required.append(section_name)
    return required


def _missing_required_sections_in_text(text: str, required_sections: list[str]) -> list[str]:
    present = {Path(section).stem.lower() for section in _secreads(text)}
    return [section for section in required_sections if Path(section).stem.lower() not in present]


def _replace_arm_secreads_by_name(text: str, primary_arm_section: str, secondary_arm_section: str) -> tuple[str, int, int]:
    """Rewrite only known arm section names, never positional tray SECREAD slots.

    Historical command families can place tray SECREADs before the cantilever
    arm sections.  Replacing the second/third SECREAD by position corrupts a
    500 mm tray into 50-42, so this function maps by reviewed section names.
    """

    pattern = r"(SECREAD\s*,\s*')([^']+)(')"
    primary_count = 0
    secondary_count = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal primary_count, secondary_count
        section_name = match.group(2).strip()
        upper = section_name.upper()
        if upper in {"50-42", "YIXINGGANG150"}:
            primary_count += 1
            return f"{match.group(1)}{primary_arm_section}{match.group(3)}"
        if upper in {"CAOGANG42DAN", "YIXINGGANG150DAN"}:
            secondary_count += 1
            return f"{match.group(1)}{secondary_arm_section}{match.group(3)}"
        return match.group(0)

    return re.sub(pattern, repl, text, flags=re.IGNORECASE), primary_count, secondary_count


def _density_by_width(payload: dict[str, Any]) -> dict[int, float]:
    grouped: dict[int, list[float]] = {}
    for layer in payload.get("tray_layers") or []:
        width = int(round(float(layer.get("tray_width_m") or 0.0) * 1000))
        density = float(layer.get("tray_density_kg_m3") or 0.0)
        if width and density:
            grouped.setdefault(width, []).append(density)
    result: dict[int, float] = {}
    for width, values in grouped.items():
        result[width] = round(max(values))
    return result


def _render_model_from_family(text: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    support = payload.get("support") or {}
    sections = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    support_section = _section_stem((sections.get(str(support.get("support_section_id"))) or {}).get("sect_file"), "100-100-6")
    primary_arm, secondary_arm, arm_policy = _arm_section_family(payload)
    widths = _input_widths(payload)
    unique_widths = []
    for width in widths:
        if width not in unique_widths:
            unique_widths.append(width)
    if not unique_widths:
        unique_widths = [500]
    source_tray_widths = list(_tray_widths_from_sections(_secreads(text)))
    model_widths = unique_widths
    material_slot_widths = _expanded_tray_widths_for_source(source_tray_widths, unique_widths)
    primary_width = model_widths[0]
    secondary_width = model_widths[1] if len(model_widths) > 1 else primary_width
    layers_by_width = {
        int(round(float(layer.get("tray_width_m") or 0.0) * 1000)): layer
        for layer in payload.get("tray_layers") or []
        if int(round(float(layer.get("tray_width_m") or 0.0) * 1000)) > 0
    }

    def arm_total_for_width(width: int) -> float:
        layer = layers_by_width.get(width) or {}
        return float(layer.get("arm_a_length_m") or 0.0) + float(layer.get("arm_b_length_m") or 0.0)

    def arm_tail_for_width(width: int) -> float:
        layer = layers_by_width.get(width) or {}
        return float(layer.get("arm_b_length_m") or 0.0)

    primary_arm_total = arm_total_for_width(primary_width)
    secondary_arm_total = arm_total_for_width(secondary_width)
    primary_arm_tail = arm_tail_for_width(primary_width)
    density_map = _density_by_width(payload)
    source_assignments = {
        name: _assignment_number(text, name)
        for name in ("H1", "H2", "L1", "L2", "L3", "L4", "L5", "L6", "senum", "senum1")
    }
    has_source_span_l6 = source_assignments.get("L6") is not None
    source_has_multi_width_geometry = len(source_tray_widths) > 1

    rendered = text
    rendered = _replace_nth_secread(rendered, 0, support_section)
    rendered, tray_secread_replacements = _replace_tray_secreads_from_intake(rendered, material_slot_widths)
    rendered, primary_arm_replacements, secondary_arm_replacements = _replace_arm_secreads_by_name(rendered, primary_arm, secondary_arm)
    required_tray_sections = _required_tray_sections_from_payload(payload)
    missing_required_tray_sections = _missing_required_sections_in_text(rendered, required_tray_sections)
    assigned_h1 = round(float(support.get("square_tube_width_m") or source_assignments.get("H1") or 0.1), 4)
    assigned_h2 = round(float(support.get("support_height_m") or source_assignments.get("H2") or 2.0), 4)
    assigned_l1 = round(
        float(primary_arm_total or source_assignments.get("L1") or 0.55),
        4,
    )
    if has_source_span_l6:
        assigned_l2 = round(float(secondary_arm_total or source_assignments.get("L2") or primary_arm_total or 0.55), 4)
        assigned_l3 = round(float(primary_width) / 1000.0, 4)
        assigned_l4 = round(float(secondary_width) / 1000.0, 4)
        assigned_l5 = round(float(source_assignments.get("L5") or primary_arm_tail or 0.15), 4)
        assigned_l6 = round(float(support.get("support_spacing_m") or source_assignments.get("L6") or 2.0), 4)
    else:
        assigned_l2 = round(
            float(primary_width / 1000.0),
            4,
        )
        assigned_l3 = round(
            float(source_assignments["L3"] if source_assignments.get("L3") is not None else (primary_arm_tail or 0.2)),
            4,
        )
        assigned_l4 = round(float(support.get("support_spacing_m") or source_assignments.get("L4") or 2.0), 4)
        assigned_l5 = source_assignments.get("L5")
        assigned_l6 = source_assignments.get("L6")
    rendered = _replace_assignment(rendered, "H1", assigned_h1)
    rendered = _replace_assignment(rendered, "H2", assigned_h2)
    rendered = _replace_assignment(rendered, "L1", assigned_l1)
    rendered = _replace_assignment(rendered, "L2", assigned_l2)
    rendered = _replace_assignment(rendered, "L3", assigned_l3)
    rendered = _replace_assignment(rendered, "L4", assigned_l4)
    if assigned_l5 is not None:
        rendered = _replace_assignment(rendered, "L5", assigned_l5)
    if assigned_l6 is not None:
        rendered = _replace_assignment(rendered, "L6", assigned_l6)
    front = int(support.get("layers_front") or 0)
    back = int(support.get("layers_back") or 0)
    assigned_senum = max(front, back) if back else front
    assigned_senum1 = min(front, back) if back else 0
    if back:
        rendered = _replace_assignment(rendered, "senum", assigned_senum)
        rendered = _replace_or_insert_assignment_after(rendered, "senum1", assigned_senum1, "senum")
    else:
        rendered = _replace_assignment(rendered, "senum", assigned_senum)
        rendered = _replace_or_insert_assignment_after(rendered, "senum1", assigned_senum1, "senum")
    for material_id, width in enumerate(material_slot_widths, start=2):
        if width in density_map:
            rendered = _replace_density(rendered, material_id, density_map[width])

    audit = {
        "support_section": support_section,
        "arm_primary_section": primary_arm,
        "arm_secondary_section": secondary_arm,
        "arm_section_policy": arm_policy,
        "section_role_map": {
            "support_square": {
                "section": support_section,
                "meaning": "方钢立柱/矩形管/梁构件截面；方钢经济性选型只允许替换这一类 SECREAD。",
            },
            "primary_cantilever_arm": {
                "section": primary_arm,
                "meaning": "托臂主槽钢/异形钢截面，不是电缆托盘；不得用托盘宽度替换。",
            },
            "secondary_cantilever_arm": {
                "section": secondary_arm,
                "meaning": "托臂次槽钢/连接件截面，不是电缆托盘；随方钢外边长分支选择。",
            },
            "tray_equivalent_sections": [
                {
                    "width_mm": width,
                    "section": f"{width}-75-2mm",
                    "meaning": "电缆托盘等效截面；必须按当前提资托盘宽度改写。",
                }
                for width in unique_widths
            ],
        },
        "tray_widths_mm": unique_widths,
        "model_geometry_widths_mm": model_widths,
        "source_geometry_widths_mm": source_tray_widths,
        "material_slot_widths_mm": material_slot_widths,
        "tray_density_by_width": density_map,
        "source_has_multi_width_geometry": source_has_multi_width_geometry,
        "required_tray_sections": required_tray_sections,
        "missing_required_tray_sections": missing_required_tray_sections,
        "tray_section_status": "pass" if not missing_required_tray_sections else "fail",
        "source_tray_secread_count": len(source_tray_widths),
        "tray_secread_replacements": tray_secread_replacements,
        "primary_arm_secread_replacements": primary_arm_replacements,
        "secondary_arm_secread_replacements": secondary_arm_replacements,
        "assigned": {
            "H1": assigned_h1,
            "H2": assigned_h2,
            "L1": assigned_l1,
            "L2": assigned_l2,
            "L3": assigned_l3,
            "L4": assigned_l4,
            "L5": assigned_l5,
            "L6": assigned_l6,
            "senum": assigned_senum,
            "senum1": assigned_senum1,
        },
        "policy": "The reviewed source command family supplies topology and command structure only. Tray width, tray SECREAD names, tray material densities, span-width L parameters, and layer-count parameters are rewritten from the current intake so a 500 mm tray is modeled as the 500 tray section even when the historical source family used another width.",
    }
    return rendered, audit


def _find_adjacent_solve_command(model_source: Path, expected_method: str | None = None) -> tuple[Path | None, str | None, str | None]:
    """Return the standard solve command stream next to a selected model family.

    The historical packages keep the modeling PIP and calculation MAC in the
    same review folder.  Using that solve stream preserves the audited spectrum,
    ZPA, and load-case combination logic instead of regenerating those blocks
    from a simplified template.
    """
    for pattern in SOLVE_PATTERNS:
        for candidate in sorted(model_source.parent.glob(pattern), key=lambda item: item.name.lower()):
            if candidate.is_file() and not candidate.name.lower().endswith(".bak"):
                text, encoding = read_text_with_encoding(candidate)
                method = _classify_solve_command(candidate, text)
                if expected_method == "static" and method not in {"static", "unknown"}:
                    continue
                if expected_method in {"response_spectrum", "spectrum"} and method == "static":
                    continue
                return candidate, text, encoding
    return None, None, None


def find_adjacent_solve_command(model_source: Path | str) -> Path | None:
    source_path, _, _ = _find_adjacent_solve_command(Path(model_source))
    return source_path


def _fmt_apdl_number(value: float) -> str:
    return f"{float(value):.6g}"


def _is_gravity_acel(args_text: str) -> bool:
    tokens = [token.strip().lower() for token in args_text.split(",")]
    if len(tokens) != 3:
        return False
    try:
        values = [float(token) for token in tokens]
    except ValueError:
        return False
    return abs(values[0]) < 1e-12 and abs(values[1]) < 1e-12 and abs(values[2] - 9.81) < 1e-9


def _static_acel_coefficients(payload: dict[str, Any]) -> tuple[dict[str, float] | None, dict[str, Any]]:
    metadata = payload.get("metadata") or {}
    if str(metadata.get("analysis_method") or "").lower() != "static":
        return None, {"status": "not_required", "policy": "Response-spectrum jobs keep the audited source solve command unchanged."}
    source = metadata.get("static_acceleration_source") or {}
    required = {
        "obe_x": "zpa_obe_x_g",
        "obe_y": "zpa_obe_y_g",
        "obe_z": "zpa_obe_z_g",
        "sse_x": "zpa_sse_x_g",
        "sse_y": "zpa_sse_y_g",
        "sse_z": "zpa_sse_z_g",
    }
    missing = [source_key for source_key in required.values() if metadata.get(source_key) is None and source.get(source_key) is None]
    if missing:
        return None, {
            "status": "fail",
            "missing": missing,
            "message": "Static method solve commands require ZPA coefficients derived from the selected spectrum workbook and intake elevation.",
        }
    coefficients = {
        label: float(metadata.get(source_key) if metadata.get(source_key) is not None else source[source_key])
        for label, source_key in required.items()
    }
    coefficients["factor"] = float(metadata.get("static_acceleration_factor") or source.get("static_acceleration_factor") or 1.5)
    return coefficients, {
        "status": "ready",
        "coefficients": coefficients,
        "source_ref": source.get("source_ref") or metadata.get("static_acceleration_source"),
        "policy": "Static-method earthquake ACEL lines are rewritten from the current intake building/elevation spectrum coefficients while preserving the audited solve-command structure.",
    }


def _rewrite_static_acel_from_payload(source_text: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    coefficients, audit = _static_acel_coefficients(payload)
    if coefficients is None:
        return source_text, audit

    rewritten_lines: list[str] = []
    replaced: list[dict[str, Any]] = []
    earthquake_index = 0
    for line_no, line in enumerate(source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), start=1):
        match = re.match(r"^(\s*ACEL\s*,)([^!]*)(.*)$", line, flags=re.IGNORECASE)
        if not match or _is_gravity_acel(match.group(2)):
            rewritten_lines.append(line)
            continue
        earthquake_index += 1
        if earthquake_index == 1:
            values = (coefficients["obe_x"], coefficients["obe_y"], coefficients["obe_z"])
            case_id = "SL-1/OBE"
        elif earthquake_index == 2:
            values = (coefficients["sse_x"], coefficients["sse_y"], coefficients["sse_z"])
            case_id = "SL-2/SSE"
        else:
            rewritten_lines.append(line)
            continue
        factor = _fmt_apdl_number(coefficients["factor"])
        new_args = ",".join(f"{factor}*9.81*{_fmt_apdl_number(value)}" for value in values)
        rewritten_line = f"{match.group(1)}{new_args}{match.group(3)}"
        rewritten_lines.append(rewritten_line)
        replaced.append(
            {
                "line": line_no,
                "case": case_id,
                "original": line.strip(),
                "rewritten": rewritten_line.strip(),
            }
        )

    status = "pass" if len(replaced) >= 2 else "fail"
    return "\n".join(rewritten_lines), {
        **audit,
        "status": status,
        "replaced_count": len(replaced),
        "replacements": replaced,
        "message": "Static ACEL coefficients were rewritten from selected spectrum data."
        if status == "pass"
        else "Could not find both non-gravity earthquake ACEL lines to rewrite.",
    }


def _source_filename_elevations(source_path: Path) -> list[float]:
    values: list[float] = []
    stem = source_path.stem
    if "m" not in stem.lower():
        return values
    for match in re.finditer(r"(?:^|[\s_])([-+]?\d+(?:\.\d+)?)(?=\s*m|\s|$)", stem, flags=re.IGNORECASE):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if -100.0 <= value <= 300.0:
            values.append(value)
    return sorted(set(values))


def _coefficient_from_acel_arg(value: str) -> float | None:
    numbers = re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", value)
    if not numbers:
        return None
    try:
        return float(numbers[-1])
    except ValueError:
        return None


def _source_static_acel_coefficients(source_text: str) -> dict[str, float] | None:
    earthquake_rows: list[tuple[float, float, float]] = []
    for line in source_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        match = re.match(r"^\s*ACEL\s*,([^!]*)", line, flags=re.IGNORECASE)
        if not match or _is_gravity_acel(match.group(1)):
            continue
        parts = [part.strip() for part in match.group(1).split(",")]
        if len(parts) != 3:
            continue
        parsed = [_coefficient_from_acel_arg(part) for part in parts]
        if any(item is None for item in parsed):
            continue
        earthquake_rows.append((float(parsed[0]), float(parsed[1]), float(parsed[2])))
    if len(earthquake_rows) < 2:
        return None
    return {
        "zpa_obe_x_g": earthquake_rows[0][0],
        "zpa_obe_y_g": earthquake_rows[0][1],
        "zpa_obe_z_g": earthquake_rows[0][2],
        "zpa_sse_x_g": earthquake_rows[1][0],
        "zpa_sse_y_g": earthquake_rows[1][1],
        "zpa_sse_z_g": earthquake_rows[1][2],
    }


def _coefficients_match_source(candidate: dict[str, Any], source_coefficients: dict[str, float], tolerance: float = 0.006) -> bool:
    for key, expected in source_coefficients.items():
        actual = candidate.get(key)
        if actual is None or abs(float(actual) - float(expected)) > tolerance:
            return False
    return True


def _infer_static_elevations_from_source_acel(source_text: str, payload: dict[str, Any]) -> tuple[list[float], dict[str, Any] | None]:
    source_coefficients = _source_static_acel_coefficients(source_text)
    if not source_coefficients:
        return [], None
    spectrum_file = (payload.get("spectrum") or {}).get("spectrum_file")
    project = payload.get("project") or {}
    if not spectrum_file or not project.get("building") or not project.get("project_code"):
        return [], None
    try:
        preview = describe_segmented_spectrum_workbook(spectrum_file)
    except Exception as exc:
        return [], {
            "status": "warning",
            "message": f"Could not inspect spectrum elevations for static source-ACEL inference: {exc}",
            "source_coefficients": source_coefficients,
        }
    available = [float(item) for item in preview.get("available_elevations") or []]
    if not available:
        return [], None
    base_elevation = float(project.get("elevation") or available[0])
    candidate_sets: list[tuple[float, ...]] = []
    for size in range(1, min(4, len(available)) + 1):
        for item in combinations(available, size):
            if not any(abs(float(elevation) - base_elevation) < 1e-6 for elevation in item):
                continue
            candidate_sets.append(tuple(sorted(item)))
    for elevations in candidate_sets:
        try:
            coefficients = derive_static_acceleration_coefficients(
                spectrum_file,
                project_code=str(project.get("project_code") or ""),
                building=str(project.get("building") or ""),
                elevation=base_elevation,
                elevations=elevations,
            )
        except Exception:
            continue
        if _coefficients_match_source(coefficients, source_coefficients):
            return list(elevations), {
                "status": "pass",
                "elevations": list(elevations),
                "source_coefficients": source_coefficients,
                "matched_coefficients": {
                    key: coefficients.get(key)
                    for key in source_coefficients
                },
                "policy": (
                    "Static source filename did not declare elevations, so the elevation envelope was inferred by "
                    "matching the audited source ACEL coefficients to the selected spectrum workbook within source "
                    "rounding tolerance. Report result values are not used."
                ),
            }
    return [], {
        "status": "warning",
        "source_coefficients": source_coefficients,
        "message": "No spectrum elevation envelope reproduced the audited source ACEL coefficients within rounding tolerance.",
    }


def _payload_with_static_source_elevation_envelope(
    source_path: Path,
    source_text: str,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    metadata = payload.get("metadata") or {}
    if str(metadata.get("analysis_method") or "").lower() != "static":
        return payload, None
    project = payload.get("project") or {}
    return payload, {
        "status": "not_applied",
        "source_file": str(source_path),
        "elevations": [float(project.get("elevation") or 0.0)] if project.get("elevation") is not None else [],
        "elevation_source": "current_intake_elevation",
        "policy": (
            "Static-method jobs use the current intake elevation only. Historical report text, command filename "
            "tokens, and source ACEL matching are recorded for conflict review but are not used to create a "
            "multi-elevation envelope for new production calculations."
        ),
    }


def _has_modal_analysis(source_text: str) -> bool:
    return bool(re.search(r"\b(MODOPT|ANTYPE\s*,\s*2)\b", source_text, flags=re.IGNORECASE))


def _ensure_modal_analysis_block(source_text: str) -> tuple[str, dict[str, Any]]:
    if _has_modal_analysis(source_text):
        return source_text, {"status": "source_contains_modal_analysis"}
    modal_block = "\n".join(
        [
            "! CableTrayAI inserted modal coverage block: follows audited static/spectrum modal solve pattern.",
            "/SOL",
            "LSCLEAR,ALL",
            "ALLSEL,ALL",
            "D,YUESHU,ALL,0",
            "ALLSEL,ALL",
            "ANTYPE,2",
            "MSAVE,0",
            "MODOPT,LANB,MT",
            "EQSLV,SPAR",
            "MXPAND,MT,,,1",
            "LUMPM,0",
            "PSTRES,0",
            "MODOPT,LANB,MT,0,0,,OFF",
            "/OUTPUT,'Mode','oup',",
            "SOLVE",
            "FINISH",
            "/OUTPUT,TERM",
            "",
        ]
    )
    return modal_block + source_text.lstrip(), {
        "status": "inserted",
        "source_ref": "CableTrayAI:modal_coverage_block",
        "reason": "source solve stream did not contain MODOPT or ANTYPE,2; reports require Mode.oup and modal figures",
    }


def _render_solve_from_source(
    source_path: Path,
    source_text: str,
    payload: dict[str, Any],
    *,
    source_text_for_modal_policy: str | None = None,
) -> tuple[str, dict[str, Any]]:
    solve_payload, elevation_envelope_audit = _payload_with_static_source_elevation_envelope(source_path, source_text, payload)
    body, solve_parameterization = _rewrite_static_acel_from_payload(source_text, solve_payload)
    analysis_method = str((solve_payload.get("metadata") or {}).get("analysis_method") or "").lower()
    if analysis_method == "static":
        solve_parameterization["modal_mode_policy"] = {
            "status": "not_required",
            "analysis_method": "static",
            "policy": "Static-method calculations apply equivalent static acceleration loads directly; no MT, modal extraction, or 50 Hz Mode.oup gate is required.",
        }
        solve_parameterization["modal_analysis_block"] = {
            "status": "not_required",
            "analysis_method": "static",
        }
        modal_policy_line = "! Modal policy: not required for static-method calculation."
    else:
        modal_policy_source = source_text_for_modal_policy if source_text_for_modal_policy is not None else source_text
        modal_count = modal_mode_count_from_payload(solve_payload, modal_policy_source)
        body, modal_block_audit = _ensure_modal_analysis_block(body)
        body = rewrite_modal_mode_count(body, modal_count)
        solve_parameterization["modal_mode_policy"] = modal_policy_audit(solve_payload, modal_policy_source)
        solve_parameterization["modal_analysis_block"] = modal_block_audit
        modal_policy_line = f"! Modal policy: MT={modal_count}; verify Mode.oup last frequency exceeds 50 Hz after ANSYS run."
    if elevation_envelope_audit:
        solve_parameterization["static_elevation_envelope"] = elevation_envelope_audit
    header = "\n".join(
        [
            "! CableTrayAI generated_solve.mac",
            "! Source: audited standard calculation command stream.",
            f"! source_file={source_path.as_posix()}",
            "! Policy: preserve audited solve structure; static-method ACEL values are parameterized from the current intake static acceleration coefficients.",
            modal_policy_line,
            "",
        ]
    )
    return header + body.replace("\r\n", "\n").replace("\r", "\n"), solve_parameterization


def _render_solve_from_controlled_template(
    environment: Environment,
    payload: dict[str, Any],
    *,
    source_text_for_modal_policy: str | None = None,
) -> tuple[str, dict[str, Any]]:
    render_payload = dict(payload)
    modal_count = modal_mode_count_from_payload(render_payload, source_text_for_modal_policy)
    render_payload["modal_mode_count"] = modal_count
    rendered = environment.get_template("solve_spectrum.mac.j2").render(**render_payload)
    return rendered, {
        "status": "pass",
        "modal_mode_policy": modal_policy_audit(render_payload, source_text_for_modal_policy),
        "response_solve_policy": (
            "Response-spectrum jobs use the controlled solve template because it isolates SL-1, SL-2, "
            "and zero-period static correction with model reloads. The adjacent audited source solve "
            "stream is retained as a traceable reference and as an MT lower-bound source, but its "
            "inline spectrum blocks are not copied verbatim because MAPDL can stall in continuous "
            "in-memory spectrum state."
        ),
    }


def _same_name_library_modal_sources(family_source_path: Path) -> list[tuple[Path, str]]:
    calculation_dir = family_source_path.parent
    report_root = calculation_dir.parent.parent
    if not report_root.exists() or report_root == calculation_dir:
        return []
    candidates: list[tuple[Path, str]] = []
    pattern = f"*/{calculation_dir.name}/{family_source_path.name}"
    for candidate in sorted(report_root.glob(pattern)):
        if candidate == family_source_path or not candidate.is_file():
            continue
        try:
            text, _ = read_text_with_encoding(candidate)
        except Exception:
            continue
        if parse_source_modal_mode_count(text) is None:
            continue
        candidates.append((candidate, text))
    return candidates


def _modal_policy_source_bundle(
    family_source_path: Path,
    family_source_text: str,
    solve_source_text: str | None,
    *,
    include_family_literal_modopt: bool = False,
) -> str:
    texts: list[str] = []
    if include_family_literal_modopt or re.search(r"(?im)^\s*MT\s*=\s*\d+\b", family_source_text):
        texts.append(family_source_text)
    if solve_source_text:
        texts.append(solve_source_text)
    for sibling in sorted(family_source_path.parent.iterdir()):
        if sibling == family_source_path or not sibling.is_file():
            continue
        suffixes = "".join(sibling.suffixes).lower()
        if not any(token in suffixes for token in (".pip", ".mac", ".txt", ".bak")):
            continue
        try:
            sibling_text, _ = read_text_with_encoding(sibling)
        except Exception:
            continue
        has_explicit_mt = re.search(r"(?im)^\s*MT\s*=\s*\d+\b", sibling_text) is not None
        if not include_family_literal_modopt and not has_explicit_mt:
            continue
        if parse_source_modal_mode_count(sibling_text) is not None:
            texts.append(f"\n! sibling_modal_policy_source={sibling.as_posix()}\n{sibling_text}")
    if include_family_literal_modopt and parse_source_modal_mode_count("\n".join(texts)) is None:
        for candidate, candidate_text in _same_name_library_modal_sources(family_source_path):
            texts.append(f"\n! library_modal_policy_source={candidate.as_posix()}\n{candidate_text}")
    return "\n".join(texts)


def _allows_model_literal_modal_count(payload: dict[str, Any], analysis_method: str | None, solve_source_text: str | None) -> bool:
    if re.search(r"(?im)^\s*MT\s*=\s*\d+\b", solve_source_text or ""):
        return False
    if analysis_method != "static":
        return False
    support = payload.get("support") or {}
    layer_count = int(support.get("layers_front") or 0) + int(support.get("layers_back") or 0)
    if layer_count <= 0:
        layer_count = len(payload.get("tray_layers") or [])
    return layer_count >= 5


def render_intake_standard_family_commands(
    job_id: str,
    input_payload: dict[str, Any] | Path,
    *,
    jobs_dir: Path | str,
    template_dir: Path | str = Path("templates/apdl"),
    source_root: Path | str = Path("source_materials/model_commands"),
    solve_strategy: str = "adjacent_source",
) -> dict[str, Any]:
    if solve_strategy not in {"adjacent_source", "template"}:
        raise ValueError("solve_strategy must be 'adjacent_source' or 'template'")

    jobs_dir = Path(jobs_dir)
    job_dir = jobs_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(input_payload, Path):
        payload = json.loads(input_payload.read_text(encoding="utf-8"))
    else:
        payload = input_payload
        (job_dir / "input.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    render_context = dict(payload)
    render_context.update(build_standard_s2_template_context(render_context))

    environment = Environment(
        loader=FileSystemLoader(str(template_dir)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )
    source_root = Path(source_root)
    family = select_standard_model_family(payload, source_root)
    source_text, encoding = read_text_with_encoding(Path(family["source"]))
    rendered_model, parameter_audit = _render_model_from_family(source_text, payload)
    required_tray_sections = _required_tray_sections_from_payload(payload)
    missing_required_tray_sections = _missing_required_sections_in_text(rendered_model, required_tray_sections)
    if missing_required_tray_sections:
        fallback_model = environment.get_template("geometry_s2.mac.j2").render(**render_context)
        fallback_missing = _missing_required_sections_in_text(fallback_model, required_tray_sections)
        parameter_audit["source_family_model_status"] = "rejected_missing_tray_sections"
        parameter_audit["source_family_missing_required_tray_sections"] = missing_required_tray_sections
        parameter_audit["fallback_model_template"] = "templates/apdl/geometry_s2.mac.j2"
        parameter_audit["fallback_missing_required_tray_sections"] = fallback_missing
        parameter_audit["missing_required_tray_sections"] = fallback_missing
        parameter_audit["tray_section_status"] = "pass" if not fallback_missing else "fail"
        parameter_audit["status"] = "fallback_template" if not fallback_missing else "fail"
        rendered_model = fallback_model
    else:
        parameter_audit["source_family_model_status"] = "pass"
        parameter_audit["status"] = "pass"
    (job_dir / "generated_model.mac").write_text(rendered_model, encoding="utf-8", newline="\n")
    keypoint_guard_audit = guard_undefined_keypoint_coordinate_refs(job_dir / "generated_model.mac")

    expected_solve_method = str((render_context.get("metadata") or {}).get("analysis_method") or "").lower() or None
    solve_source_path, solve_source_text, solve_source_encoding = _find_adjacent_solve_command(
        Path(family["source"]),
        expected_solve_method,
    )
    solve_source_audit: dict[str, Any]
    solve_parameterization_audit: dict[str, Any] = {"status": "not_applicable"}
    solve_source_method = _classify_solve_command(solve_source_path, solve_source_text) if solve_source_path else "unknown"
    effective_analysis_method = expected_solve_method or ("static" if solve_source_method == "static" else None)
    if effective_analysis_method == "static":
        modal_policy_source_text = None
    else:
        include_model_literal_modal_count = _allows_model_literal_modal_count(
            render_context,
            effective_analysis_method,
            solve_source_text,
        )
        modal_policy_source_text = _modal_policy_source_bundle(
            Path(family["source"]),
            source_text,
            solve_source_text,
            include_family_literal_modopt=include_model_literal_modal_count,
        )
    response_spectrum_method = expected_solve_method in {"response_spectrum", "spectrum"} or (
        expected_solve_method is None and solve_source_method == "spectrum"
    )
    if solve_strategy == "adjacent_source" and response_spectrum_method:
        rendered_solve, solve_parameterization_audit = _render_solve_from_controlled_template(
            environment,
            render_context,
            source_text_for_modal_policy=modal_policy_source_text,
        )
        if solve_source_path and solve_source_text is not None:
            solve_source_audit = {
                "status": "template_with_source_reference",
                "source": str(solve_source_path),
                "source_encoding": solve_source_encoding,
                "source_sha256": _sha256(solve_source_path),
                "policy": (
                    "generated_solve.mac uses the controlled response-spectrum template with separate "
                    "ansys_spectrum_sl1/sl2 includes and model reloads. The adjacent audited 02 command "
                    "stream remains the review source for calculation sequence intent and modal MT lower "
                    "bound, but inline FREQ/SV blocks are not copied into generated_solve.mac."
                ),
            }
        else:
            solve_source_audit = {
                "status": "fallback_template",
                "source": None,
                "policy": "No adjacent response-spectrum 02 calculation stream was found; controlled spectrum template is used and must be reviewed before precision acceptance.",
            }
    elif solve_strategy == "adjacent_source" and solve_source_path and solve_source_text is not None:
        rendered_solve, solve_parameterization_audit = _render_solve_from_source(
            solve_source_path,
            solve_source_text,
            render_context,
            source_text_for_modal_policy=modal_policy_source_text,
        )
        solve_source_audit = {
            "status": "pass",
            "source": str(solve_source_path),
            "source_encoding": solve_source_encoding,
            "source_sha256": _sha256(solve_source_path),
            "policy": "generated_solve.mac is rendered from the adjacent audited 02 calculation command stream. Static earthquake ACEL coefficients are rewritten from current intake static acceleration coefficients; no response-spectrum modal extraction or MT is inserted for static-method jobs.",
        }
    else:
        rendered_solve, solve_parameterization_audit = _render_solve_from_controlled_template(
            environment,
            render_context,
            source_text_for_modal_policy=source_text,
        )
        fallback_reason = (
            "Production intake-as-new flow uses the selected spectrum workbook and the generic audited solve template "
            "while the model geometry remains rendered from the matched standard command-flow family."
            if solve_strategy == "template"
            else "No adjacent 02 calculation command stream was found; generated_solve.mac falls back to the generic spectrum template and must be reviewed before precision acceptance."
        )
        solve_source_audit = {
            "status": "template" if solve_strategy == "template" else "fallback_template",
            "source": None,
            "policy": fallback_reason,
        }
    (job_dir / "generated_solve.mac").write_text(rendered_solve, encoding="utf-8", newline="\n")

    rendered_post = environment.get_template("post_extract_s2.mac.j2").render(**render_context)
    (job_dir / "generated_post.mac").write_text(rendered_post, encoding="utf-8", newline="\n")

    command_header_audit = _prepend_command_headers(job_dir)
    post_alignment_audit = align_postprocessor_to_intake(job_dir, render_context)
    section_export_audit = augment_square_support_export(job_dir / "generated_post.mac")
    alias_audit = write_command_aliases(job_dir)
    sections = _copy_required_sections(job_dir, source_root, job_dir / "generated_model.mac")
    master_macro_audit = build_run_all_macro(job_dir)
    apdl_audit = audit_rendered_apdl(
        [job_dir / "generated_model.mac", job_dir / "generated_solve.mac", job_dir / "generated_post.mac"],
        job_dir / "apdl_audit.json",
        require_modal_analysis=expected_solve_method != "static",
    )
    section_failures = [item for item in sections if item.get("status") != "copied"]
    solve_parameterization_failed = solve_parameterization_audit.get("status") == "fail"
    payload_out = {
        "status": "pass" if not section_failures and not solve_parameterization_failed else "fail",
        "job_id": job_id,
        "job_dir": str(job_dir),
        "family": {**family, "source_encoding": encoding},
        "solve_strategy": solve_strategy,
        "parameterization": parameter_audit,
        "model_keypoint_guard": keypoint_guard_audit,
        "solve_source": solve_source_audit,
        "solve_parameterization": solve_parameterization_audit,
        "sections": sections,
        "command_headers": command_header_audit,
        "postprocessor_alignment": post_alignment_audit,
        "section_specific_export": section_export_audit,
        "command_aliases": alias_audit,
        "master_macro_audit": master_macro_audit,
        "apdl_audit": apdl_audit,
    }
    (job_dir / "intake_standard_family_traceability.json").write_text(
        json.dumps(payload_out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload_out
