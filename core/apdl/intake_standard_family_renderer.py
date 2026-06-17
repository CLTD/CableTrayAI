from __future__ import annotations

import json
import os
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
from core.apdl.mixed_tray_model import (
    render_mixed_tray_layer_model,
    should_use_mixed_tray_layer_renderer,
)
from core.apdl.section_specific_export import augment_square_support_export
from core.apdl.section_offsets import normalize_secondary_arm_secoffset
from core.apdl.source_diff import read_text_with_encoding
from core.apdl.postprocessor_alignment import align_postprocessor_to_intake
from core.apdl.platform_standard_flow import build_platform_standard_shadow_flow
from core.apdl.standard_command_renderer import _copy_required_sections, _prepend_command_headers, _sha256
from core.intake.tray_load_parser import LOAD_KG_PER_M, TRAY_AREA_M2
from core.optimizer.square_section_selector import parse_square_section_name
from core.spectra.static_coefficients import describe_segmented_spectrum_workbook, derive_static_acceleration_coefficients


MODEL_PATTERNS = ("01*.PIP", "01*.pip", "01*.MAC", "01*.mac", "01*.TXT", "01*.txt")
CURRENT_TYPE_MODEL_PATTERNS = ("*.PIP", "*.pip", "*.MAC", "*.mac", "*.TXT", "*.txt")
SOLVE_PATTERNS = ("02*.mac", "02*.MAC", "02*.PIP", "02*.pip", "02*.TXT", "02*.txt")


@dataclass(frozen=True)
class CommandFamily:
    path: Path
    source_library: str
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
    lower_name = name.lower()
    has_back = bool(re.search(r"K\s*,\s*15\d\d", text, flags=re.IGNORECASE))
    if "三侧" in name or "three" in lower_name:
        return "three_side", has_back
    if "单侧" in name or "single" in lower_name or not has_back:
        return "single", has_back
    if "不同" in name or "mixed" in lower_name or "different" in lower_name:
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


def _current_type_command_roots(source_root: Path) -> list[Path]:
    candidates: list[Path] = []
    env_root = str(os.environ.get("CABLETRAYAI_CURRENT_TYPE_COMMAND_ROOT") or "").strip()
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend(
        [
            Path.cwd() / "resources" / "current_type_command_flows",
            Path(__file__).resolve().parents[2] / "resources" / "current_type_command_flows",
            source_root.parent.parent / "resources" / "current_type_command_flows",
        ]
    )
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.exists():
            continue
        resolved = candidate.resolve()
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)
    return roots


def _discover_families(source_root: Path) -> list[CommandFamily]:
    reports_root = source_root / "报告及模型命令流"
    scan_roots: list[tuple[Path, str, tuple[str, ...]]] = [
        (root, "current_type_command_flows", CURRENT_TYPE_MODEL_PATTERNS)
        for root in _current_type_command_roots(source_root)
    ]
    scan_roots.append(
        (reports_root, "historical_source_materials", MODEL_PATTERNS)
        if reports_root.exists()
        else (source_root, "source_materials", MODEL_PATTERNS)
    )
    families: list[CommandFamily] = []
    for root, source_library, patterns in scan_roots:
        for pattern in patterns:
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
                        source_library=source_library,
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


def _single_width_family_l3_from_tray_and_square(primary_tray_width_mm: int, square_outer_mm: float) -> tuple[float, str]:
    if primary_tray_width_mm <= 300:
        return 0.15, "tray_width_le_300_l3_0p15m"
    if square_outer_mm > 120.0:
        return 0.15, "square_outer_width_gt_120_l3_0p15m"
    return 0.20, "square_outer_width_le_120_l3_0p20m"


def _width_compatibility(family: CommandFamily, widths: list[int]) -> dict[str, Any]:
    family_widths = sorted(set(int(width) for width in family.width_family if int(width) > 0))
    expected_widths = sorted(set(int(width) for width in widths if int(width) > 0))
    if not expected_widths:
        return {"status": "pass", "reason": "no_width_constraint", "value": family_widths, "expected": expected_widths}
    if not family_widths:
        return {"status": "fail", "reason": "source_has_no_tray_width", "value": family_widths, "expected": expected_widths}
    if family_widths == expected_widths:
        return {"status": "pass", "reason": "exact_width_family", "value": family_widths, "expected": expected_widths}

    if len(expected_widths) == 1:
        width = expected_widths[0]
        if width <= 200:
            if family_widths == [200]:
                return {"status": "pass", "reason": "reviewed_100_200_small_tray_family", "value": family_widths, "expected": expected_widths}
            if (
                not family.has_mixed_widths
                and len(family_widths) == 1
                and family_widths[0] > 300
            ):
                return {"status": "pass", "reason": "single_width_small_tray_rewrite_from_wide_family", "value": family_widths, "expected": expected_widths}
            return {"status": "fail", "reason": "small_tray_must_not_use_300_family", "value": family_widths, "expected": expected_widths}
        if width == 300:
            return {"status": "fail", "reason": "tray_300_requires_exact_physical_bolt_family", "value": family_widths, "expected": expected_widths}
        if width > 300 and not family.has_mixed_widths and len(family_widths) == 1 and family_widths[0] > 300:
            return {"status": "pass", "reason": "reviewed_wide_single_width_rewrite", "value": family_widths, "expected": expected_widths}

    if len(expected_widths) > 1 and family.has_mixed_widths:
        if set(expected_widths).issubset(set(family_widths)):
            return {"status": "pass", "reason": "mixed_width_family_covers_intake_widths", "value": family_widths, "expected": expected_widths}
        if max(expected_widths) in family_widths:
            return {"status": "pass", "reason": "mixed_width_family_covers_governing_width", "value": family_widths, "expected": expected_widths}

    return {"status": "fail", "reason": "incompatible_width_family", "value": family_widths, "expected": expected_widths}


def _has_reviewed_300_physical_bolt_modeling(text: str, *, has_back_side: bool) -> bool:
    def has(pattern: str) -> bool:
        return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None

    front_line_pairs = (
        has(r"^\s*L\s*,\s*506\s*\+\s*10\s*\*\s*I\b.*,\s*507\s*\+\s*10\s*\*\s*I\b")
        or has(r"^\s*L\s*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*6\b.*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*7\b")
    ) and (
        has(r"^\s*L\s*,\s*507\s*\+\s*10\s*\*\s*I\b.*,\s*508\s*\+\s*10\s*\*\s*I\b")
        or has(r"^\s*L\s*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*7\b.*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*8\b")
    )
    back_line_pairs = (not has_back_side) or (
        has(r"^\s*L\s*,\s*1506\s*\+\s*10\s*\*\s*I\b.*,\s*1507\s*\+\s*10\s*\*\s*I\b")
        and has(r"^\s*L\s*,\s*1507\s*\+\s*10\s*\*\s*I\b.*,\s*1508\s*\+\s*10\s*\*\s*I\b")
    )
    return all(
        [
            has(r"^\s*ET\s*,\s*4\s*,\s*(?:188|BEAM188)\b"),
            has(r"^\s*SECTYPE\s*,\s*10\s*,\s*BEAM\s*,\s*CSOLID\b"),
            has(r"^\s*SECDATA\s*,\s*0\.006\b"),
            has(r"^\s*LATT\s*,\s*1\s*,\s*,\s*4\s*,\s*,\s*,\s*,\s*10\b"),
            front_line_pairs,
            back_line_pairs,
        ]
    )


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

    width_compatibility = _width_compatibility(family, widths)
    add("side_kind", family.side_kind == side_kind, 120, family.side_kind, side_kind)
    if expected_support_section:
        add(
            "support_section",
            _section_stem(family.support_section).upper() == expected_support_section.upper(),
            24,
            family.support_section,
            expected_support_section,
        )
    add(
        "width_compatibility",
        width_compatibility["status"] == "pass",
        160,
        width_compatibility["value"],
        width_compatibility["expected"],
    )
    checks[-1]["reason"] = width_compatibility.get("reason")
    add("width_family", sorted(family.width_family) == widths, 25, list(family.width_family), widths)
    if widths:
        add("max_width_covered", max(widths) in family.width_family, 20, list(family.width_family), max(widths))
    if len(widths) == 1 and widths[0] > 300:
        add(
            "wide_single_width_source_family",
            bool(family.width_family) and min(family.width_family) > 300,
            90,
            list(family.width_family),
            "single-width source family above 300 mm",
        )
    add("primary_arm_section", family.primary_arm_section.upper() == primary.upper(), 20, family.primary_arm_section, primary)
    add("secondary_arm_section", family.secondary_arm_section.upper() == secondary.upper(), 10, family.secondary_arm_section, secondary)
    add("mixed_widths", family.has_mixed_widths == mixed, 8, family.has_mixed_widths, mixed)
    if widths == [300]:
        add(
            "tray_300_physical_bolt_modeling",
            _has_reviewed_300_physical_bolt_modeling(family.text, has_back_side=family.has_back_side),
            45,
            family.path.name,
            "ET,4 + SECTYPE,10 CSOLID + LATT,1,,4,,,,10 + 506/507/508 physical bolt lines",
        )
    if source_senum is not None and expected_primary_layers:
        add("primary_layer_count", int(source_senum) == int(expected_primary_layers), 16, int(source_senum), int(expected_primary_layers))
    if back and source_senum1 is not None and expected_secondary_layers is not None:
        add("secondary_layer_count", int(source_senum1) == int(expected_secondary_layers), 8, int(source_senum1), int(expected_secondary_layers))
    if expected_method in {"static", "spectrum"}:
        add("analysis_method", source_method == expected_method, 12, source_method, expected_method)
    if expected_method == "static":
        add(
            "static_adjacent_solve_available",
            source_method == "static",
            80,
            source_method,
            "static adjacent 02 calculation command stream",
        )
    else:
        add(
            "current_type_command_library",
            family.source_library == "current_type_command_flows",
            100,
            family.source_library,
            "current_type_command_flows",
        )
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
    width_rejected: list[dict[str, Any]] = []
    for family in families:
        width_check = _width_compatibility(family, sorted(set(_input_widths(payload))))
        if width_check["status"] != "pass":
            width_rejected.append(
                {
                    "source": str(family.path),
                    "source_library": family.source_library,
                    "reason": width_check.get("reason"),
                    "value": width_check.get("value"),
                    "expected": width_check.get("expected"),
                }
            )
            continue
        score, checks = _score_family(family, payload)
        scored.append((score, family, checks))
    if not scored:
        raise ValueError(
            "No width-compatible standard APDL/PIP model family matches the intake geometry. "
            f"Rejected candidates: {width_rejected[:8]}"
        )
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
        "source_library": best.source_library,
        "source_sha256": _sha256(best.path),
        "policy": (
            "Select a reusable standard command-flow family by intake geometry, side/topology, tray width, and "
            "arm-section family. The curated resources/current_type_command_flows library is preferred for "
            "modeling; historical source_materials remain read-only fallback and solve/post traceability sources. "
            "Report result values and numerical closeness are not used."
        ),
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


def _layer_width_counts(payload: dict[str, Any], side: str | None = None) -> dict[int, int]:
    counts: dict[int, int] = {}
    for layer in payload.get("tray_layers") or []:
        layer_side = str(layer.get("side") or "front").lower()
        if side is not None and layer_side != side:
            continue
        width = int(round(float(layer.get("tray_width_m") or 0.0) * 1000))
        if width > 0:
            counts[width] = counts.get(width, 0) + 1
    return counts


def _one_side_width(payload: dict[str, Any], side: str, default: int) -> int:
    counts = _layer_width_counts(payload, side)
    if not counts:
        return default
    # Standard double-different command streams have one tray-width family per
    # side.  If an intake side contains multiple widths, keep the governing
    # width for source-family parameterization and let the family-selection
    # gate decide whether this is acceptable.
    return max(counts)


def _source_mixed_family_shape(text: str, source_tray_widths: list[int]) -> str:
    has_back = re.search(r"(?im)^\s*K\s*,\s*1501\s*\+", text) is not None
    has_l11 = _assignment_number(text, "L11") is not None
    has_senum2 = _assignment_number(text, "senum2") is not None
    has_senum3 = _assignment_number(text, "senum3") is not None
    widths = set(source_tray_widths)
    if not has_back and has_l11 and has_senum2 and has_senum3 and {300, 500, 600}.issubset(widths):
        return "single_mixed_600_500_300_universal"
    if not has_back and has_senum3 and widths == {500, 600}:
        return "single_mixed_600_500_yixing"
    if has_back and len(widths) > 1:
        return "double_mixed_one_width_per_side"
    return "standard_or_single_width"


def _current_type_mixed_family_covers_payload(
    payload: dict[str, Any],
    *,
    source_text: str,
    source_path: Path,
) -> dict[str, Any]:
    widths = sorted(set(_input_widths(payload)))
    source_tray_widths = list(_tray_widths_from_sections(_secreads(source_text)))
    source_shape = _source_mixed_family_shape(source_text, source_tray_widths)
    source_name = source_path.name
    if not widths:
        return {"status": "not_mixed", "source_shape": source_shape, "source": source_name}
    if source_shape in {"single_mixed_600_500_300_universal", "single_mixed_600_500_yixing"}:
        side_count = _payload_side_count(payload)
        covered = (
            side_count == 1
            and len(widths) > 1
            and set(widths).issubset(set(source_tray_widths))
            and not any(width <= 200 for width in widths)
        )
        return {
            "status": "pass" if covered else "fail",
            "source_shape": source_shape,
            "source": source_name,
            "payload_widths": widths,
            "source_widths": source_tray_widths,
            "reason": "single_side_current_type_mixed_family_exact_cover"
            if covered
            else "single_side_mixed_family_does_not_exactly_cover_payload",
        }
    if source_shape == "double_mixed_one_width_per_side":
        front_widths = sorted(_layer_width_counts(payload, "front"))
        back_widths = sorted(_layer_width_counts(payload, "back"))
        covered = (
            len(widths) > 1
            and len(front_widths) == 1
            and len(back_widths) == 1
            and set(front_widths + back_widths).issubset(set(source_tray_widths))
        )
        return {
            "status": "pass" if covered else "fail",
            "source_shape": source_shape,
            "source": source_name,
            "payload_widths": widths,
            "source_widths": source_tray_widths,
            "front_widths": front_widths,
            "back_widths": back_widths,
            "reason": "double_side_one_width_per_side_current_type_cover"
            if covered
            else "double_side_payload_has_per_side_mixed_widths_or_uncovered_widths",
        }
    return {
        "status": "fail",
        "source_shape": source_shape,
        "source": source_name,
        "payload_widths": widths,
        "source_widths": source_tray_widths,
        "reason": "source_is_not_current_mixed_family_shape",
    }


def _wide_tray_tail_m(widths: list[int], square_outer_mm: float, default: float | None = None) -> float:
    if widths and max(widths) <= 300:
        return 0.15
    if square_outer_mm > 120.0:
        return 0.15
    return 0.20


def _bolt_radius_m_for_widths(widths: list[int]) -> tuple[float, str]:
    positive_widths = [int(width) for width in widths if int(width) > 0]
    if positive_widths and max(positive_widths) <= 200:
        return 0.004, "tray_width_le_200_uses_m8_nominal_round_bar_radius"
    return 0.006, "tray_width_gt_200_uses_m12_nominal_round_bar_radius"


def _rewrite_model_bolt_section_radius(text: str, widths: list[int]) -> tuple[str, dict[str, Any]]:
    radius, policy = _bolt_radius_m_for_widths(widths)
    pattern = re.compile(
        r"(?im)^(\s*SECTYPE\s*,\s*10\s*,\s*BEAM\s*,\s*CSOLID\s*\n\s*SECDATA\s*,)\s*[-+]?\d+(?:\.\d+)?(?:[Ee][-+]?\d+)?\b"
    )
    replacement = rf"\g<1>{radius:.3f}"
    updated, count = pattern.subn(replacement, text)
    return updated, {
        "status": "rewritten" if count else "not_present",
        "radius_m": radius,
        "widths_mm": sorted(set(int(width) for width in widths if int(width) > 0)),
        "replacement_count": count,
        "policy": policy,
        "source_ref": "standard tray-support installation manual bolt size rule: 100/200 trays use M8; 300/500/600 trays use M12",
    }


def _normalize_physical_bolt_element_type_keyopts(text: str) -> tuple[str, dict[str, Any]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    updated: list[str] = []
    rewritten = 0
    inserted = 0
    saw_et4 = False
    found_keyopt4 = False
    found_keyopt1 = False
    in_et4_block = False

    for line in lines:
        if re.match(r"\s*ET\s*,\s*4\s*,\s*188\b", line, flags=re.IGNORECASE):
            if in_et4_block and saw_et4:
                if not found_keyopt4:
                    updated.append("KEYOPT,4,4,2")
                    inserted += 1
                if not found_keyopt1:
                    updated.append("KEYOPT,4,1,1")
                    inserted += 1
            updated.append(line)
            saw_et4 = True
            in_et4_block = True
            found_keyopt4 = False
            found_keyopt1 = False
            continue

        if in_et4_block:
            match = re.match(r"(\s*)KEYOPT\s*,\s*(\d+)\s*,\s*([14])\s*,\s*(\d+)\s*(.*)$", line, flags=re.IGNORECASE)
            if match:
                prefix, element_type, option, value, suffix = match.groups()
                if element_type == "2" and option in {"1", "4"}:
                    line = f"{prefix}KEYOPT,4,{option},{value}{suffix}"
                    rewritten += 1
                if re.match(r"\s*KEYOPT\s*,\s*4\s*,\s*4\s*,\s*2\b", line, flags=re.IGNORECASE):
                    found_keyopt4 = True
                if re.match(r"\s*KEYOPT\s*,\s*4\s*,\s*1\s*,\s*1\b", line, flags=re.IGNORECASE):
                    found_keyopt1 = True
                updated.append(line)
                continue

            if not re.match(r"\s*KEYOPT\s*,", line, flags=re.IGNORECASE):
                if not found_keyopt4:
                    updated.append("KEYOPT,4,4,2")
                    inserted += 1
                if not found_keyopt1:
                    updated.append("KEYOPT,4,1,1")
                    inserted += 1
                in_et4_block = False

        updated.append(line)

    if in_et4_block and saw_et4:
        if not found_keyopt4:
            updated.append("KEYOPT,4,4,2")
            inserted += 1
        if not found_keyopt1:
            updated.append("KEYOPT,4,1,1")
            inserted += 1

    return "\n".join(updated), {
        "status": "rewritten" if rewritten else "inserted" if inserted else "already_correct" if saw_et4 else "not_present",
        "rewritten_count": rewritten,
        "inserted_count": inserted,
        "source_ref": "current-type physical bolt BEAM188 element-type correction",
        "policy": (
            "Physical bolt/connector lines use element type 4 through LATT,1,,4,,,,10. "
            "Some reviewed command streams inherited KEYOPT,2 immediately after ET,4; generated APDL "
            "normalizes that block to KEYOPT,4 so the bolt element type owns the intended BEAM188 settings."
        ),
    }


def _has_physical_bolt_topology(text: str, *, has_back_side: bool) -> bool:
    checks = [
        r"(?im)^\s*ET\s*,\s*4\s*,\s*188\b",
        r"(?im)^\s*SECTYPE\s*,\s*10\s*,\s*BEAM\s*,\s*CSOLID\b",
        r"(?im)^\s*K\s*,\s*509\s*\+\s*10\s*\*\s*I\b",
        r"(?im)^\s*L\s*,\s*(?:502|503)\s*\+\s*10\s*\*\s*I\b.*,\s*509\s*\+\s*10\s*\*\s*I\b",
        r"(?im)^\s*LATT\s*,\s*1\s*,\s*,\s*4\s*,\s*,\s*,\s*,\s*10\b",
    ]
    if has_back_side:
        checks.extend(
            [
                r"(?im)^\s*K\s*,\s*1509\s*\+\s*10\s*\*\s*I\b",
                r"(?im)^\s*L\s*,\s*(?:1502|1503)\s*\+\s*10\s*\*\s*I\b.*,\s*1509\s*\+\s*10\s*\*\s*I\b",
            ]
        )
    return all(re.search(pattern, text) for pattern in checks)


def _ensure_small_tray_physical_bolt_elements(
    text: str,
    *,
    enabled: bool,
    has_back_side: bool,
) -> tuple[str, dict[str, Any]]:
    if not enabled:
        return text, {
            "status": "not_required",
            "reason": "not_tray_width_le_200_single_width_family",
        }
    if _has_physical_bolt_topology(text, has_back_side=has_back_side):
        return text, {
            "status": "already_present",
            "source_ref": "operator-confirmed physical bolt modeling requirement",
            "policy": (
                "100/200 mm S2 small-tray jobs retain physical bolt/connector BEAM188 lines. "
                "Subsequent normalization still verifies element type 4 KEYOPT settings and M8 section data."
            ),
        }

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    inserted = {
        "element_type_4_blocks": 0,
        "section_10_blocks": 0,
        "front_k509_and_connector": 0,
        "back_k1509_and_connector": 0,
        "tray_center_unselect_lines": 0,
        "section_10_mesh_blocks": 0,
    }

    if not re.search(r"(?im)^\s*ET\s*,\s*4\s*,\s*188\b", text):
        insert_at = None
        for index, line in enumerate(lines):
            if re.match(r"\s*KEYOPT\s*,\s*2\s*,\s*1\s*,\s*1\b", line, flags=re.IGNORECASE):
                insert_at = index + 1
                break
            if insert_at is None and re.match(r"\s*ET\s*,\s*2\s*,\s*188\b", line, flags=re.IGNORECASE):
                insert_at = index + 1
        if insert_at is not None:
            lines[insert_at:insert_at] = ["ET,4,188", "KEYOPT,4,4,2", "KEYOPT,4,1,1"]
            inserted["element_type_4_blocks"] = 1

    if not re.search(r"(?im)^\s*SECTYPE\s*,\s*10\s*,\s*BEAM\s*,\s*CSOLID\b", "\n".join(lines)):
        insert_at = next(
            (
                index
                for index, line in enumerate(lines)
                if re.match(r"\s*MP\s*,", line, flags=re.IGNORECASE)
            ),
            None,
        )
        if insert_at is not None:
            lines[insert_at:insert_at] = ["SECTYPE,10,BEAM,CSOLID", "SECDATA,0.004", "SECOFFSET,USER,"]
            inserted["section_10_blocks"] = 1

    text_after_header = "\n".join(lines)
    need_front_connector = not re.search(r"(?im)^\s*K\s*,\s*509\s*\+\s*10\s*\*\s*I\b", text_after_header)
    need_back_connector = has_back_side and not re.search(r"(?im)^\s*K\s*,\s*1509\s*\+\s*10\s*\*\s*I\b", text_after_header)
    rebuilt: list[str] = []
    for line in lines:
        rebuilt.append(line)
        if need_front_connector and re.match(
            r"\s*L\s*,\s*507\s*\+\s*10\s*\*\s*I\b.*,\s*508\s*\+\s*10\s*\*\s*I\b",
            line,
            flags=re.IGNORECASE,
        ):
            rebuilt.extend(
                [
                    "K,509+10*I+100*(J-1),H1/2+L1-L2/2,0+L4*(J-1),0.15+0.2*(I-1)",
                    "L,503+10*I+100*(J-1),509+10*I+100*(J-1)",
                ]
            )
            inserted["front_k509_and_connector"] += 1
        if need_back_connector and re.match(
            r"\s*L\s*,\s*1507\s*\+\s*10\s*\*\s*I\b.*,\s*1508\s*\+\s*10\s*\*\s*I\b",
            line,
            flags=re.IGNORECASE,
        ):
            rebuilt.extend(
                [
                    "K,1509+10*I+100*(J-1),-(H1/2+L1-L2/2),0+L4*(J-1),0.15+0.2*(I-1)",
                    "L,1503+10*I+100*(J-1),1509+10*I+100*(J-1)",
                ]
            )
            inserted["back_k1509_and_connector"] += 1

    compact = re.sub(r"\s+", "", "\n".join(rebuilt))
    need_section10_mesh = "LATT,1,,4,,,,10" not in compact
    rebuilt2: list[str] = []
    pending_section10_after_lmesh = False
    for line in rebuilt:
        if re.match(r"\s*LATT\s*,\s*2\s*,\s*,\s*2\s*,\s*,\s*,\s*,\s*4\b", line, flags=re.IGNORECASE):
            for keypoint in ("519", "619", "719"):
                unselect = f"LSEL,U,LOC,Y,KY({keypoint})"
                if unselect not in rebuilt2:
                    rebuilt2.append(unselect)
                    inserted["tray_center_unselect_lines"] += 1
            if has_back_side:
                for keypoint in ("1519", "1619", "1719"):
                    unselect = f"LSEL,U,LOC,Y,KY({keypoint})"
                    if unselect not in rebuilt2:
                        rebuilt2.append(unselect)
                        inserted["tray_center_unselect_lines"] += 1
            pending_section10_after_lmesh = need_section10_mesh
        rebuilt2.append(line)
        if pending_section10_after_lmesh and re.match(r"\s*LMESH\s*,\s*ALL\b", line, flags=re.IGNORECASE):
            bolt_mesh = [
                "",
                "ALLSEL",
                "LSEL,S,LOC,X,KX(516)",
            ]
            if has_back_side:
                bolt_mesh.append("LSEL,A,LOC,X,KX(1516)")
            bolt_mesh.extend(
                [
                    "LATT,1,,4,,,,10",
                    "LESIZE,ALL,0.05,,,,,,,1",
                    "LMESH,ALL",
                ]
            )
            rebuilt2.extend(bolt_mesh)
            inserted["section_10_mesh_blocks"] += 1
            pending_section10_after_lmesh = False
            need_section10_mesh = False

    return "\n".join(rebuilt2), {
        "status": "inserted" if any(inserted.values()) else "already_present",
        "inserted": inserted,
        "has_back_side": has_back_side,
        "source_ref": "operator-confirmed physical bolt modeling requirement",
        "policy": (
            "100/200 mm S2 small-tray jobs must model the physical bolt/connector beam. "
            "If the selected current-type source family lacks ET4/SECTYPE10/K509 connector lines, "
            "generated APDL inserts the missing physical-bolt topology before normalizing KEYOPT, section, "
            "and M8 radius."
        ),
    }


def _wrap_optional_block_once(text: str, start_regex: str, condition: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?ms)(ALLSEL\s*\n\s*{start_regex}.*?LMESH\s*,\s*ALL)", flags=re.IGNORECASE)

    def repl(match: re.Match[str]) -> str:
        block = match.group(1)
        if f"*IF,{condition},THEN" in block:
            return block
        return f"*IF,{condition},THEN\n{block}\n*ENDIF"

    return pattern.subn(repl, text, count=1)


def _guard_single_mixed_optional_mesh_blocks(text: str, source_mixed_shape: str) -> tuple[str, dict[str, Any]]:
    if source_mixed_shape not in {"single_mixed_600_500_300_universal", "single_mixed_600_500_yixing"}:
        return text, {"status": "not_required", "source_mixed_family_shape": source_mixed_shape}

    replacements: list[dict[str, str]] = []

    def apply(start_regex: str, condition: str, label: str) -> None:
        nonlocal text
        text, count = _wrap_optional_block_once(text, start_regex, condition)
        if count:
            replacements.append({"block": label, "condition": condition})

    apply(r"LSEL\s*,\s*S\s*,\s*LOC\s*,\s*X\s*,\s*KX\(\s*516\s*\)", "senum3,GT,0", "600_tray_mesh")
    if source_mixed_shape == "single_mixed_600_500_300_universal":
        apply(
            r"LSEL\s*,\s*S\s*,\s*LOC\s*,\s*X\s*,\s*KX\(\s*506\s*\+\s*\(\s*senum3\s*\+\s*1\s*\)\s*\*\s*10\s*\)",
            "senum2,GT,senum3",
            "500_tray_mesh",
        )
        apply(
            r"LSEL\s*,\s*S\s*,\s*LOC\s*,\s*X\s*,\s*KX\(\s*506\s*\+\s*\(\s*senum2\s*\+\s*1\s*\)\s*\*\s*10\s*\)",
            "senum1,GT,senum2",
            "300_tray_mesh",
        )
    else:
        apply(
            r"LSEL\s*,\s*S\s*,\s*LOC\s*,\s*X\s*,\s*KX\(\s*506\s*\+\s*\(\s*senum3\s*\+\s*1\s*\)\s*\*\s*10\s*\)",
            "senum1,GT,senum3",
            "500_tray_mesh",
        )

    return text, {
        "status": "guarded" if replacements else "unchanged",
        "source_mixed_family_shape": source_mixed_shape,
        "replacements": replacements,
        "policy": (
            "Current unit single-side mixed command streams contain fixed mesh-selection blocks for every "
            "reviewed width family. When an intake has zero layers for one width, CableTrayAI preserves the "
            "standard block but wraps it in an APDL *IF guard so KX(...) is not evaluated for undefined "
            "keypoints."
        ),
    }


def _standard_family_keypoint_numbering(front_layers: int, back_layers: int) -> dict[str, Any]:
    """Return keypoint-numbering expansion for source families above 9 layers.

    The reviewed standard command stream reserves keypoint IDs by a 10-per-layer
    tray-arm family inside a 100-ID frame.  That is safe through 9 layers only:
    at 10+ layers the arm keypoints overlap the support-column keypoints.  Keep
    the legacy numbering for calibrated low-layer jobs, and expand only when the
    current intake needs more room.
    """

    max_layers = max(int(front_layers or 0), int(back_layers or 0))
    if max_layers <= 9:
        return {
            "status": "legacy_source_numbering",
            "enabled": False,
            "max_layers": max_layers,
            "safe_legacy_layer_limit": 9,
            "keypoint_offset": 0,
            "frame_step": 100,
            "back_base": 1500,
        }

    # Preserve the standard suffix convention (*2, *6, *9, etc.) by shifting
    # tray-arm keypoints by a whole multiple of ten, then enlarge the inter-frame
    # spacing enough that frame 1/2/3 cannot collide.
    keypoint_offset = max(20, ((max_layers + 10) // 10) * 10)
    frame_span = keypoint_offset + 10 * max_layers + 9
    frame_step = max(200, ((frame_span // 100) + 1) * 100)
    front_third_frame_max = 500 + 2 * frame_step + frame_span
    back_base = 1500 if front_third_frame_max < 1500 else ((front_third_frame_max // 100) + 2) * 100
    return {
        "status": "expanded_for_high_layer_count",
        "enabled": True,
        "max_layers": max_layers,
        "safe_legacy_layer_limit": 9,
        "keypoint_offset": keypoint_offset,
        "frame_step": frame_step,
        "back_base": back_base,
        "front_third_frame_max_keypoint": front_third_frame_max,
        "policy": (
            "For >9 layer standard-family models, CableTrayAI preserves the reviewed APDL topology "
            "but expands tray-arm keypoint IDs by KPOFF and frame spacing by KPFSTEP so ANSYS does "
            "not reject duplicate keypoints such as 511."
        ),
    }


def _apdl_numbering_assignments(numbering: dict[str, Any]) -> str:
    return "\n".join(
        [
            "! CableTrayAI high-layer keypoint numbering parameters.",
            f"KPOFF={int(numbering['keypoint_offset'])}",
            f"KPFSTEP={int(numbering['frame_step'])}",
            f"KPBKBASE={int(numbering['back_base'])}",
        ]
    )


def _insert_keypoint_numbering_assignments(text: str, numbering: dict[str, Any]) -> str:
    if not numbering.get("enabled"):
        return text
    assignment_block = _apdl_numbering_assignments(numbering)
    if re.search(r"(?im)^\s*KPOFF\s*=", text):
        text = re.sub(r"(?im)^\s*KPOFF\s*=.*$", f"KPOFF={int(numbering['keypoint_offset'])}", text)
        text = re.sub(r"(?im)^\s*KPFSTEP\s*=.*$", f"KPFSTEP={int(numbering['frame_step'])}", text)
        text = re.sub(r"(?im)^\s*KPBKBASE\s*=.*$", f"KPBKBASE={int(numbering['back_base'])}", text)
        return text
    match = re.search(r"(?im)^\s*senum1\s*=.*$", text)
    if match:
        return text[: match.end()] + "\n" + assignment_block + text[match.end() :]
    return assignment_block + "\n" + text


def _kp_base_expr(side: str, frame_index: int) -> str:
    if side == "front":
        if frame_index == 0:
            return "500"
        if frame_index == 1:
            return "500+KPFSTEP"
        return f"500+{frame_index}*KPFSTEP"
    if frame_index == 0:
        return "KPBKBASE"
    if frame_index == 1:
        return "KPBKBASE+KPFSTEP"
    return f"KPBKBASE+{frame_index}*KPFSTEP"


def _join_apdl_terms(*terms: Any) -> str:
    result: list[str] = []
    for term in terms:
        text = str(term)
        if not text or text == "0":
            continue
        result.append(text)
    return "+".join(result) if result else "0"


def _renumber_literal_keypoint_expr(keypoint: int, numbering: dict[str, Any]) -> str | None:
    max_layers = int(numbering.get("max_layers") or 0)
    for side, base0 in (("front", 500), ("back", 1500)):
        for frame_index in range(3):
            old_base = base0 + 100 * frame_index
            remainder = keypoint - old_base
            if remainder < 0 or remainder >= 100:
                continue
            base_expr = _kp_base_expr(side, frame_index)
            if remainder == 0:
                return base_expr
            if side == "front" and 1 <= remainder <= max_layers + 1:
                return _join_apdl_terms(base_expr, remainder)
            layer = remainder // 10
            suffix = remainder % 10
            if layer >= 1 and 1 <= suffix <= 9:
                return _join_apdl_terms(base_expr, "KPOFF", f"{layer * 10}", suffix)
    return None


def _renumber_k_function_literals(text: str, numbering: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        expr = _renumber_literal_keypoint_expr(int(match.group(2)), numbering)
        if expr is None:
            return match.group(0)
        return f"{match.group(1)}({expr})"

    lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("!"):
            lines.append(line)
        else:
            lines.append(re.sub(r"\b(K[XYZ])\(\s*(\d+)\s*\)", repl, line, flags=re.IGNORECASE))
    return "".join(lines)


def _replace_support_root_expressions(text: str) -> str:
    replacements = {
        "601+senum": "500+KPFSTEP+1+senum",
        "701+senum": "500+2*KPFSTEP+1+senum",
        "1601+senum1": "KPBKBASE+KPFSTEP+1+senum1",
        "1701+senum1": "KPBKBASE+2*KPFSTEP+1+senum1",
    }
    lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("!"):
            lines.append(line)
            continue
        updated = line
        for old, new in replacements.items():
            updated = re.sub(re.escape(old), new, updated, flags=re.IGNORECASE)
        lines.append(updated)
    return "".join(lines)


def _apply_model_keypoint_numbering(text: str, numbering: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not numbering.get("enabled"):
        return text, numbering
    updated = _insert_keypoint_numbering_assignments(text, numbering)
    updated = re.sub(r"100\s*\*\s*\(\s*J\s*-\s*1\s*\)", "KPFSTEP*(J-1)", updated, flags=re.IGNORECASE)
    updated = re.sub(r"(?<![\w.])((?:50|150)[1-9])\s*\+\s*10\s*\*\s*I", r"\1+KPOFF+10*I", updated)
    updated = re.sub(r"(?<![\w.])150([1-9])\s*\+\s*KPOFF\s*\+\s*10\s*\*\s*I", r"KPBKBASE+\1+KPOFF+10*I", updated)
    updated = re.sub(
        r"KSEL\s*,\s*S\s*,\s*KP\s*,\s*,\s*500\s*\+\s*senum\s*\+\s*1\s*,\s*700\s*\+\s*senum\s*\+\s*1\s*,\s*100",
        "KSEL,S,KP,,500+senum+1,500+2*KPFSTEP+senum+1,KPFSTEP",
        updated,
        flags=re.IGNORECASE,
    )
    updated = _renumber_k_function_literals(updated, numbering)
    updated = _replace_support_root_expressions(updated)
    return updated, numbering


def _replace_post_keypoint_formula(text: str, old_base: int, new_expr: str) -> str:
    return re.sub(
        rf"(?<![\w.]){old_base}\s*\+\s*([IJ])\s*\*\s*10",
        rf"{new_expr}+KPOFF+\1*10",
        text,
        flags=re.IGNORECASE,
    )


def _apply_post_keypoint_numbering(text: str, numbering: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not numbering.get("enabled"):
        return text, {"status": "legacy_source_numbering", "enabled": False}
    updated = _insert_keypoint_numbering_assignments(text, numbering)
    for old_base, new_expr in (
        (501, "501"),
        (601, "500+KPFSTEP+1"),
        (701, "500+2*KPFSTEP+1"),
        (1501, "KPBKBASE+1"),
        (1601, "KPBKBASE+KPFSTEP+1"),
        (1701, "KPBKBASE+2*KPFSTEP+1"),
    ):
        updated = _replace_post_keypoint_formula(updated, old_base, new_expr)
    updated = _renumber_k_function_literals(updated, numbering)
    updated = _replace_support_root_expressions(updated)
    return updated, numbering


def _ensure_standard_beam188_warping_keyopts(text: str) -> tuple[str, dict[str, Any]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    target_types = (1, 2)
    existing = {
        element_type
        for element_type in target_types
        if re.search(rf"(?im)^\s*KEYOPT\s*,\s*{element_type}\s*,\s*1\s*,\s*1\b", text)
    }
    available = {
        element_type
        for element_type in target_types
        if re.search(rf"(?im)^\s*ET\s*,\s*{element_type}\s*,\s*188\b", text)
    }
    inserted: list[int] = []
    for element_type in target_types:
        if element_type in existing or element_type not in available:
            continue
        insert_after = None
        keyopt4_pattern = re.compile(rf"^\s*KEYOPT\s*,\s*{element_type}\s*,\s*4\s*,", re.IGNORECASE)
        et_pattern = re.compile(rf"^\s*ET\s*,\s*{element_type}\s*,\s*188\b", re.IGNORECASE)
        for index, line in enumerate(lines):
            if keyopt4_pattern.search(line):
                insert_after = index
                break
            if insert_after is None and et_pattern.search(line):
                insert_after = index
        if insert_after is None:
            continue
        lines.insert(insert_after + 1, f"KEYOPT,{element_type},1,1")
        inserted.append(element_type)
    return "\n".join(lines), {
        "status": "inserted" if inserted else "already_present" if existing else "not_required",
        "inserted_element_types": inserted,
        "existing_element_types": sorted(existing),
        "available_element_types": sorted(available),
        "source_ref": "standard_model_command_family:BEAM188_KEYOPT_1_1",
        "policy": (
            "Most reviewed S2 standard command streams define BEAM188 KEYOPT(1)=1 for "
            "element types 1 and 2. Some otherwise matching historical families omit it; "
            "generated APDL restores this standard setting instead of changing CP/CPCYC topology."
        ),
    }


def _rewrite_small_tray_arm_partition(text: str, *, enabled: bool) -> tuple[str, dict[str, Any]]:
    if not enabled:
        return text, {
            "status": "not_required",
            "reason": "not_tray_width_le_200_single_width_family",
        }

    positive_l2_half = re.compile(r"H1\s*/\s*2\s*\+\s*L1\s*-\s*L2\s*/\s*2", flags=re.IGNORECASE)
    positive_l3 = re.compile(r"H1\s*/\s*2\s*\+\s*L1\s*-\s*L3\b", flags=re.IGNORECASE)
    negative_l2_half = re.compile(r"-\(\s*H1\s*/\s*2\s*\+\s*L1\s*-\s*L2\s*/\s*2\s*\)", flags=re.IGNORECASE)
    negative_l3 = re.compile(r"-\(\s*H1\s*/\s*2\s*\+\s*L1\s*-\s*L3\s*\)", flags=re.IGNORECASE)

    def keypoint_base(line: str) -> int | None:
        match = re.match(r"\s*K\s*,\s*(\d+)", line, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def rewrite_keypoint(line: str, base: int) -> tuple[str, int]:
        if base == 502:
            return positive_l2_half.subn("H1/2+L1-L3", line)
        if base == 503:
            return positive_l3.subn("H1/2+L1-L2/2", line)
        if base == 1502:
            return negative_l2_half.subn("-(H1/2+L1-L3)", line)
        if base == 1503:
            return negative_l3.subn("-(H1/2+L1-L2/2)", line)
        return line, 0

    line_502_to_509 = re.compile(
        r"(?i)(L\s*,\s*)502(\s*\+\s*10\s*\*\s*I\s*\+\s*100\s*\*\s*\(\s*J\s*-\s*1\s*\)\s*,\s*509)",
    )
    line_1502_to_1509 = re.compile(
        r"(?i)(L\s*,\s*)1502(\s*\+\s*10\s*\*\s*I\s*\+\s*100\s*\*\s*\(\s*J\s*-\s*1\s*\)\s*,\s*1509)",
    )
    wide_source_tray_z_offset = re.compile(
        r"(?<![\w.])0\.168\s*\+\s*0\.2\s*\*\s*\(\s*I\s*-\s*1\s*\)",
        flags=re.IGNORECASE,
    )
    wide_source_coupling_offset = re.compile(
        r"(?<![\w.])0\.068\s*-\s*0\.05\b",
        flags=re.IGNORECASE,
    )

    updated_lines: list[str] = []
    keypoint_replacements = 0
    line_replacements = 0
    z_offset_replacements = 0
    coupling_offset_replacements = 0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        base = keypoint_base(line)
        if base in {502, 503, 1502, 1503}:
            line, count = rewrite_keypoint(line, base)
            keypoint_replacements += count
        line, count = line_502_to_509.subn(r"\g<1>503\g<2>", line)
        line_replacements += count
        line, count = line_1502_to_1509.subn(r"\g<1>1503\g<2>", line)
        line_replacements += count
        line, count = wide_source_tray_z_offset.subn("0.1+L5+0.2*(I-1)", line)
        z_offset_replacements += count
        line, count = wide_source_coupling_offset.subn("L5-0.05", line)
        coupling_offset_replacements += count
        updated_lines.append(line)

    replacement_count = keypoint_replacements + line_replacements + z_offset_replacements + coupling_offset_replacements
    return "\n".join(updated_lines), {
        "status": "rewritten" if replacement_count else "unchanged",
        "replacement_count": replacement_count,
        "keypoint_replacements": keypoint_replacements,
        "line_replacements": line_replacements,
        "z_offset_replacements": z_offset_replacements,
        "coupling_offset_replacements": coupling_offset_replacements,
        "source_ref": "small_tray_200_100_standard_family_partition",
        "policy": (
            "For single-width S2 tray widths <=200 mm, the reviewed 200/100 mm small-tray topology keeps "
            "L3 fixed at 0.15 m, places the first cantilever split keypoint 502/1502 at H1/2+L1-L3, and "
            "keeps the tray connection/CPCYC line at H1/2+L1-L2/2. If the reused wide-tray source hardcodes "
            "0.168 m tray offset or 0.068-0.05 coupling offset, it is normalized to the reviewed small-tray "
            "0.1+L5 and L5-0.05 expressions with L5=0.074. "
            "This applies only when a larger single-width family has to be reused for a small tray; 300 mm sources "
            "are left in their reviewed L2/2 bolt topology."
        ),
    }


def _audit_small_tray_physical_bolt_modeling(
    text: str,
    *,
    tray_width_mm: int,
    has_back_side: bool,
) -> dict[str, Any]:
    if tray_width_mm != 300:
        return {
            "status": "not_required",
            "tray_width_mm": tray_width_mm,
            "reason": "physical_bolt_gate_only_for_300_tray",
            "policy": (
                "The reviewed 300 mm tray command stream uses additional physical bolt/round-bar BEAM188 "
                "elements. Reviewed 200/100 mm small-tray command streams use the small-tray arm partition "
                "and coupling topology, so they are checked by small_tray_arm_partition instead of this gate."
            ),
        }

    def has(pattern: str) -> bool:
        return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None

    front_line_pairs = [
        (
            has(r"^\s*L\s*,\s*506\s*\+\s*10\s*\*\s*I\b.*,\s*507\s*\+\s*10\s*\*\s*I\b")
            or has(r"^\s*L\s*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*6\b.*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*7\b")
        ),
        (
            has(r"^\s*L\s*,\s*507\s*\+\s*10\s*\*\s*I\b.*,\s*508\s*\+\s*10\s*\*\s*I\b")
            or has(r"^\s*L\s*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*7\b.*,\s*500\s*\+\s*10\s*\*\s*cengshu1\s*\+\s*8\b")
        ),
    ]
    back_line_pairs = [
        has(r"^\s*L\s*,\s*1506\s*\+\s*10\s*\*\s*I\b.*,\s*1507\s*\+\s*10\s*\*\s*I\b"),
        has(r"^\s*L\s*,\s*1507\s*\+\s*10\s*\*\s*I\b.*,\s*1508\s*\+\s*10\s*\*\s*I\b"),
    ]
    checks = {
        "beam188_type_4": has(r"^\s*ET\s*,\s*4\s*,\s*(?:188|BEAM188)\b"),
        "round_bar_section_10": has(r"^\s*SECTYPE\s*,\s*10\s*,\s*BEAM\s*,\s*CSOLID\b"),
        "round_bar_diameter": has(r"^\s*SECDATA\s*,\s*0\.006\b"),
        "section_10_latt_meshing": has(r"^\s*LATT\s*,\s*1\s*,\s*,\s*4\s*,\s*,\s*,\s*,\s*10\b"),
        "front_physical_bolt_lines": all(front_line_pairs),
        "back_physical_bolt_lines": (not has_back_side) or all(back_line_pairs),
        "has_coupling_only_as_supplement": has(r"\b(?:CP|CPCYC)\s*,"),
    }
    required = [
        "beam188_type_4",
        "round_bar_section_10",
        "round_bar_diameter",
        "section_10_latt_meshing",
        "front_physical_bolt_lines",
        "back_physical_bolt_lines",
    ]
    missing = [name for name in required if not checks.get(name)]
    return {
        "status": "pass" if not missing else "fail",
        "tray_width_mm": tray_width_mm,
        "checks": checks,
        "missing": missing,
        "source_ref": "300 tray standard APDL family: ET,4 + SECTYPE,10 CSOLID + LATT,1,,4,,,,10",
        "policy": (
            "The 300 mm tray standard family must contain physical bolt/round-bar beam elements. CP/CPCYC "
            "coupling is only a supplementary node coupling and cannot by itself satisfy the 300 mm modeling gate."
        ),
    }


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
    source_mixed_shape = _source_mixed_family_shape(text, source_tray_widths)
    shared_max_width_geometry = bool(
        len(unique_widths) > 1
        and source_mixed_shape == "standard_or_single_width"
        and len(source_tray_widths) == 1
        and int(source_tray_widths[0]) == max(unique_widths)
    )
    if source_mixed_shape in {"single_mixed_600_500_300_universal", "single_mixed_600_500_yixing"}:
        material_slot_widths = source_tray_widths
        model_widths = [width for width in source_tray_widths if width in unique_widths] or unique_widths
    elif source_mixed_shape == "double_mixed_one_width_per_side":
        front_default = source_tray_widths[0] if source_tray_widths else (unique_widths[0] if unique_widths else 500)
        back_default = source_tray_widths[1] if len(source_tray_widths) > 1 else front_default
        front_width = _one_side_width(payload, "front", front_default)
        back_width = _one_side_width(payload, "back", back_default)
        material_slot_widths = [front_width, back_width]
        model_widths = []
        for width in material_slot_widths:
            if width not in model_widths:
                model_widths.append(width)
    elif shared_max_width_geometry:
        model_widths = [max(unique_widths)]
        material_widths_for_source = model_widths
        material_slot_widths = _expanded_tray_widths_for_source(source_tray_widths, material_widths_for_source)
    else:
        model_widths = unique_widths
        material_widths_for_source = unique_widths
        material_slot_widths = _expanded_tray_widths_for_source(source_tray_widths, material_widths_for_source)
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
    square_outer_mm = _square_outer_width_mm_from_payload(payload)
    section_l3_value, section_l3_policy = _single_width_family_l3_from_tray_and_square(primary_width, square_outer_mm)
    width_counts_all = _layer_width_counts(payload)
    width_counts_front = _layer_width_counts(payload, "front")
    width_counts_back = _layer_width_counts(payload, "back")

    rendered = text
    rendered = _replace_nth_secread(rendered, 0, support_section)
    rendered, tray_secread_replacements = _replace_tray_secreads_from_intake(rendered, material_slot_widths)
    rendered, primary_arm_replacements, secondary_arm_replacements = _replace_arm_secreads_by_name(rendered, primary_arm, secondary_arm)
    rendered, secondary_secoffset_audit = normalize_secondary_arm_secoffset(rendered)
    yixing_secoffset_replacements = secondary_secoffset_audit.get("yixing_replacements", 0)
    channel_secoffset_replacements = secondary_secoffset_audit.get("channel_replacements", 0)
    required_tray_sections = _required_tray_sections_from_payload(payload)
    missing_required_tray_sections = _missing_required_sections_in_text(rendered, required_tray_sections)
    selected_square_outer_m = _square_outer_width_mm_from_payload(payload) / 1000.0
    assigned_h1 = round(float(selected_square_outer_m or support.get("square_tube_width_m") or source_assignments.get("H1") or 0.1), 4)
    assigned_h2 = round(float(support.get("support_height_m") or source_assignments.get("H2") or 2.0), 4)
    assigned_l1 = round(
        float(primary_arm_total or source_assignments.get("L1") or 0.55),
        4,
    )
    extra_assignments: dict[str, float | int] = {}
    if source_mixed_shape == "single_mixed_600_500_300_universal":
        assigned_l1 = round(float(arm_total_for_width(600) or source_assignments.get("L1") or 0.67), 4)
        assigned_l2 = 0.6
        extra_assignments["L11"] = round(float(arm_total_for_width(500) or source_assignments.get("L11") or 0.55), 4)
        extra_assignments["L12"] = 0.5
        assigned_l3 = round(float(arm_total_for_width(300) or source_assignments.get("L3") or 0.35), 4)
        assigned_l4 = 0.3
        assigned_l5 = round(_wide_tray_tail_m(unique_widths, square_outer_mm, arm_tail_for_width(max(unique_widths)) or source_assignments.get("L5")), 4)
        assigned_l6 = round(float(support.get("support_spacing_m") or source_assignments.get("L6") or 2.0), 4)
        extra_assignments["senum1"] = sum(width_counts_all.values())
        extra_assignments["senum3"] = width_counts_all.get(600, 0)
        extra_assignments["senum2"] = width_counts_all.get(600, 0) + width_counts_all.get(500, 0)
        section_l3_policy = "single_mixed_600_500_300_standard_family"
    elif source_mixed_shape == "single_mixed_600_500_yixing":
        assigned_l1 = round(float(arm_total_for_width(600) or source_assignments.get("L1") or 0.67), 4)
        assigned_l2 = round(float(arm_total_for_width(500) or source_assignments.get("L2") or 0.55), 4)
        assigned_l3 = 0.6
        assigned_l4 = 0.5
        assigned_l5 = round(_wide_tray_tail_m(unique_widths, square_outer_mm, arm_tail_for_width(max(unique_widths)) or source_assignments.get("L5")), 4)
        assigned_l6 = round(float(support.get("support_spacing_m") or source_assignments.get("L6") or 2.0), 4)
        extra_assignments["senum1"] = sum(width_counts_all.values())
        extra_assignments["senum3"] = width_counts_all.get(600, 0)
        section_l3_policy = "single_mixed_600_500_yixing_standard_family"
    elif source_mixed_shape == "double_mixed_one_width_per_side":
        front_width = material_slot_widths[0]
        back_width = material_slot_widths[1] if len(material_slot_widths) > 1 else front_width
        assigned_l1 = round(float(arm_total_for_width(front_width) or source_assignments.get("L1") or front_width / 1000.0), 4)
        assigned_l2 = round(float(front_width) / 1000.0, 4)
        assigned_l3 = round(_wide_tray_tail_m(unique_widths, square_outer_mm, source_assignments.get("L3")), 4)
        assigned_l4 = round(float(support.get("support_spacing_m") or source_assignments.get("L4") or 2.0), 4)
        assigned_l5 = round(float(arm_total_for_width(back_width) or source_assignments.get("L5") or back_width / 1000.0), 4)
        assigned_l6 = round(float(back_width) / 1000.0, 4)
        extra_assignments["senum"] = sum(width_counts_front.values())
        extra_assignments["senum1"] = sum(width_counts_back.values())
        section_l3_policy = "double_mixed_one_width_per_side_standard_family"
    elif has_source_span_l6:
        assigned_l2 = round(float(secondary_arm_total or source_assignments.get("L2") or primary_arm_total or 0.55), 4)
        assigned_l3 = round(float(primary_width) / 1000.0, 4)
        assigned_l4 = round(float(secondary_width) / 1000.0, 4)
        assigned_l5 = round(_wide_tray_tail_m(unique_widths, square_outer_mm, primary_arm_tail or source_assignments.get("L5")), 4)
        assigned_l6 = round(float(support.get("support_spacing_m") or source_assignments.get("L6") or 2.0), 4)
    else:
        assigned_l2 = round(
            float(primary_width / 1000.0),
            4,
        )
        assigned_l3 = round(float(section_l3_value), 4)
        assigned_l4 = round(float(support.get("support_spacing_m") or source_assignments.get("L4") or 2.0), 4)
        assigned_l5 = source_assignments.get("L5")
        if primary_width <= 300 and assigned_l5 is None:
            assigned_l5 = 0.074
        assigned_l6 = source_assignments.get("L6")
    rendered = _replace_assignment(rendered, "H1", assigned_h1)
    rendered = _replace_assignment(rendered, "H2", assigned_h2)
    rendered = _replace_assignment(rendered, "L1", assigned_l1)
    rendered = _replace_assignment(rendered, "L2", assigned_l2)
    rendered = _replace_assignment(rendered, "L3", assigned_l3)
    rendered = _replace_assignment(rendered, "L4", assigned_l4)
    if assigned_l5 is not None:
        rendered = _replace_or_insert_assignment_after(rendered, "L5", assigned_l5, "L4")
    if assigned_l6 is not None:
        rendered = _replace_assignment(rendered, "L6", assigned_l6)
    front = int(support.get("layers_front") or 0)
    back = int(support.get("layers_back") or 0)
    assigned_senum = int(extra_assignments.get("senum", max(front, back) if back else front))
    assigned_senum1 = int(extra_assignments.get("senum1", min(front, back) if back else 0))
    if "L11" in extra_assignments:
        rendered = _replace_assignment(rendered, "L11", extra_assignments["L11"])
    if "L12" in extra_assignments:
        rendered = _replace_assignment(rendered, "L12", extra_assignments["L12"])
    if "senum" in extra_assignments:
        rendered = _replace_assignment(rendered, "senum", int(extra_assignments["senum"]))
    elif source_mixed_shape in {"single_mixed_600_500_300_universal", "single_mixed_600_500_yixing"}:
        rendered = _replace_or_insert_assignment_after(rendered, "senum", assigned_senum, "senum1")
    else:
        rendered = _replace_assignment(rendered, "senum", assigned_senum)
    rendered = _replace_or_insert_assignment_after(rendered, "senum1", assigned_senum1, "senum")
    if "senum2" in extra_assignments:
        rendered = _replace_or_insert_assignment_after(rendered, "senum2", int(extra_assignments["senum2"]), "senum1")
    if "senum3" in extra_assignments:
        rendered = _replace_or_insert_assignment_after(rendered, "senum3", int(extra_assignments["senum3"]), "senum2")
    for material_id, width in enumerate(material_slot_widths, start=2):
        if width in density_map:
            rendered = _replace_density(rendered, material_id, density_map[width])
    small_tray_partition_enabled = (
        not has_source_span_l6
        and assigned_senum > 0
        and primary_width <= 200
    )
    rendered, small_tray_partition_audit = _rewrite_small_tray_arm_partition(
        rendered,
        enabled=small_tray_partition_enabled,
    )
    rendered, small_tray_physical_bolt_policy = _ensure_small_tray_physical_bolt_elements(
        rendered,
        enabled=small_tray_partition_enabled,
        has_back_side=bool(back),
    )
    rendered, bolt_section_radius_audit = _rewrite_model_bolt_section_radius(rendered, unique_widths)
    rendered, physical_bolt_element_type_keyopts = _normalize_physical_bolt_element_type_keyopts(rendered)
    rendered, optional_mixed_mesh_guards = _guard_single_mixed_optional_mesh_blocks(rendered, source_mixed_shape)
    connection_offset_audit = {
        "status": "not_required",
        "source_ref": "reviewed_single_width_s2_keypoint_topology",
        "policy": (
            "L3 assignment remains width-policy controlled, but standard wide-tray 500/600 keypoints "
            "502 and 506-509 use the reviewed H1/2+L1-L2/2 connection line. Tray widths <=200 are handled "
            "by the small-tray partition rewrite, while reviewed 300 mm physical-bolt topology keeps its "
            "own split: 506-508 at L3 and 509/coupling at L2/2."
        ),
    }
    rendered, beam188_warping_keyopts = _ensure_standard_beam188_warping_keyopts(rendered)
    keypoint_numbering = _standard_family_keypoint_numbering(front, back)
    rendered, keypoint_numbering = _apply_model_keypoint_numbering(rendered, keypoint_numbering)
    physical_bolt_modeling = _audit_small_tray_physical_bolt_modeling(
        rendered,
        tray_width_mm=primary_width,
        has_back_side=bool(back),
    )

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
        "shared_max_width_geometry": {
            "status": "applied" if shared_max_width_geometry else "not_required",
            "input_widths_mm": unique_widths,
            "model_widths_mm": model_widths,
            "source_ref": "standard_family_selection:shared_max_width_geometry",
            "policy": (
                "When a mixed-width intake has no exact mixed-width source family and the selected reviewed "
                "single-width family already models the governing maximum tray width, geometry and material "
                "slots are rendered at that maximum width. This is a conservative reviewed-command fallback; "
                "it prevents the first listed smaller tray from shortening the shared APDL geometry."
            ),
        },
        "material_slot_widths_mm": material_slot_widths,
        "tray_density_by_width": density_map,
        "source_has_multi_width_geometry": source_has_multi_width_geometry,
        "source_mixed_family_shape": source_mixed_shape,
        "standard_mixed_layer_counts": {
            "all": width_counts_all,
            "front": width_counts_front,
            "back": width_counts_back,
            "senum2": int(extra_assignments["senum2"]) if "senum2" in extra_assignments else None,
            "senum3": int(extra_assignments["senum3"]) if "senum3" in extra_assignments else None,
            "policy": (
                "For current_type mixed command families, the reviewed source loop structure is preserved. "
                "Single-side 600/500/300 families use senum3 as the 600-layer cutoff and senum2 as the "
                "600+500 cutoff; double-different families keep one tray-width family per side."
            ),
        },
        "required_tray_sections": required_tray_sections,
        "missing_required_tray_sections": missing_required_tray_sections,
        "tray_section_status": "pass" if not missing_required_tray_sections else "fail",
        "source_tray_secread_count": len(source_tray_widths),
        "tray_secread_replacements": tray_secread_replacements,
        "primary_arm_secread_replacements": primary_arm_replacements,
        "secondary_arm_secread_replacements": secondary_arm_replacements,
        "yixing_secoffset_replacements": yixing_secoffset_replacements,
        "channel_secoffset_replacements": channel_secoffset_replacements,
        "small_tray_arm_partition": small_tray_partition_audit,
        "small_tray_physical_bolt_policy": small_tray_physical_bolt_policy,
        "bolt_section_radius": bolt_section_radius_audit,
        "physical_bolt_element_type_keyopts": physical_bolt_element_type_keyopts,
        "optional_mixed_mesh_guards": optional_mixed_mesh_guards,
        "single_width_connection_offset": connection_offset_audit,
        "physical_bolt_modeling": physical_bolt_modeling,
        "beam188_warping_keyopts": beam188_warping_keyopts,
        "assigned": {
            "H1": assigned_h1,
            "H2": assigned_h2,
            "L1": assigned_l1,
            "L2": assigned_l2,
            "L3": assigned_l3,
            "L4": assigned_l4,
            "L5": assigned_l5,
            "L6": assigned_l6,
            "L11": extra_assignments.get("L11"),
            "L12": extra_assignments.get("L12"),
            "senum": assigned_senum,
            "senum1": assigned_senum1,
            "senum2": extra_assignments.get("senum2"),
            "senum3": extra_assignments.get("senum3"),
        },
        "l3_policy": {
            "status": section_l3_policy if not has_source_span_l6 else "source_multi_width_l3_tracks_primary_tray_width",
            "square_outer_width_mm": square_outer_mm,
            "primary_tray_width_mm": primary_width,
            "applied_to": "L3" if not has_source_span_l6 else None,
            "policy": (
                "For single-width/no-L6 standard S2 model families, tray widths <=300 mm use reviewed small-tray "
                "geometry with L3=0.15 m independent of square-tube section. Wider trays keep the existing square "
                "tube outer-width policy: <=120 mm uses 0.20 m and >120 mm uses 0.15 m. Multi-width source "
                "families keep L3/L4 as tray-width parameters."
            ),
        },
        "keypoint_numbering": keypoint_numbering,
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
    family_source_path = Path(family["source"])
    source_text, encoding = read_text_with_encoding(family_source_path)
    metadata = payload.get("metadata") or {}
    allow_platform_mixed_renderer = bool(metadata.get("allow_platform_mixed_tray_renderer"))
    mixed_family_cover = _current_type_mixed_family_covers_payload(
        payload,
        source_text=source_text,
        source_path=family_source_path,
    )
    use_platform_mixed_renderer = should_use_mixed_tray_layer_renderer(payload) and (
        allow_platform_mixed_renderer or mixed_family_cover.get("status") != "pass"
    )
    if use_platform_mixed_renderer:
        rendered_model, parameter_audit = render_mixed_tray_layer_model(payload)
        parameter_audit["source_family_model_status"] = "bypassed_for_mixed_tray_layer_renderer"
        parameter_audit["current_type_mixed_family_cover"] = mixed_family_cover
        parameter_audit["source_family_reference"] = {
            "source": family["source"],
            "source_sha256": family.get("source_sha256"),
            "policy": (
                "Mixed tray layer geometry is generated per layer when no current unit standard mixed family "
                "exactly covers the payload. The selected source family remains the audited solve/post reference."
            ),
        }
    else:
        rendered_model, parameter_audit = _render_model_from_family(source_text, payload)
        parameter_audit["current_type_mixed_family_cover"] = mixed_family_cover
        if should_use_mixed_tray_layer_renderer(payload):
            parameter_audit["platform_mixed_tray_renderer"] = {
                "status": "disabled_for_production_standard_family_baseline",
                "allow_platform_mixed_tray_renderer": allow_platform_mixed_renderer,
                "source_ref": family["source"],
                "policy": (
                    "Production mixed tray-width jobs preserve the current unit standard command-flow family by "
                    "default. The platform-owned mixed renderer is retained only as an explicit experimental "
                    "fallback after separate review."
                ),
            }
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
        parameter_audit.setdefault("source_family_model_status", "pass")
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
    rendered_post, post_keypoint_numbering_audit = _apply_post_keypoint_numbering(
        rendered_post,
        parameter_audit.get("keypoint_numbering") or _standard_family_keypoint_numbering(
            int((render_context.get("support") or {}).get("layers_front") or 0),
            int((render_context.get("support") or {}).get("layers_back") or 0),
        ),
    )
    (job_dir / "generated_post.mac").write_text(rendered_post, encoding="utf-8", newline="\n")

    command_header_audit = _prepend_command_headers(job_dir)
    post_alignment_audit = align_postprocessor_to_intake(job_dir, render_context)
    section_export_audit = augment_square_support_export(job_dir / "generated_post.mac")
    platform_standard_flow_audit = build_platform_standard_shadow_flow(
        job_dir,
        render_context,
        solve_source_audit=solve_source_audit,
        solve_parameterization_audit=solve_parameterization_audit,
        post_alignment_audit=post_alignment_audit,
    )
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
    model_parameterization_failed = (parameter_audit.get("physical_bolt_modeling") or {}).get("status") == "fail"
    payload_out = {
        "status": "pass" if not section_failures and not solve_parameterization_failed and not model_parameterization_failed else "fail",
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
        "platform_standard_flow": platform_standard_flow_audit,
        "post_keypoint_numbering": post_keypoint_numbering_audit,
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
