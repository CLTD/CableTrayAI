from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


POST_HEADER_MARKER = "! CableTrayAI postprocessor branch parameters"


def _load_input(job_dir: Path, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload is not None:
        return payload
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return {}
    return json.loads(input_path.read_text(encoding="utf-8"))


def _square_outer_m(payload: dict[str, Any]) -> float | None:
    metadata = payload.get("metadata") or {}
    support = payload.get("support") or {}
    value = metadata.get("square_section_outer_mm")
    if value is not None:
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            pass
    value = support.get("square_tube_width_m")
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass
    spec = str(metadata.get("square_section_spec") or support.get("support_section_id") or "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*[-*xX]\s*\1", spec)
    if match:
        return float(match.group(1)) / 1000.0
    return None


def _square_thickness_m(payload: dict[str, Any]) -> float | None:
    metadata = payload.get("metadata") or {}
    value = metadata.get("square_section_thickness_mm")
    if value is not None:
        try:
            return float(value) / 1000.0
        except (TypeError, ValueError):
            pass
    spec = str(metadata.get("square_section_spec") or (payload.get("support") or {}).get("support_section_id") or "")
    match = re.search(r"\d+(?:\.\d+)?\s*[-*xX]\s*\d+(?:\.\d+)?\s*[-*xX]\s*(\d+(?:\.\d+)?)", spec)
    if match:
        return float(match.group(1)) / 1000.0
    return None


def _prepend_branch_parameters(text: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    outer_m = _square_outer_m(payload)
    thickness_m = _square_thickness_m(payload)
    if outer_m is None:
        return text, {"status": "skipped", "reason": "square section outer width not available"}
    if POST_HEADER_MARKER in text:
        updated = re.sub(r"(?m)^H1\s*=\s*[-+0-9.Ee]+", f"H1={outer_m:.6f}", text, count=1)
        if thickness_m is not None:
            if re.search(r"(?m)^H2\s*=", updated):
                updated = re.sub(r"(?m)^H2\s*=\s*[-+0-9.Ee]+", f"H2={thickness_m:.6f}", updated, count=1)
            else:
                updated = updated.replace(f"H1={outer_m:.6f}", f"H1={outer_m:.6f}\nH2={thickness_m:.6f}", 1)
        return updated, {
            "status": "updated_existing" if updated != text else "already_current",
            "H1_m": outer_m,
            "H2_m": thickness_m,
            "source_ref": "input.json:metadata.square_section_outer_mm/support.square_tube_width_m",
        }
    lines = [
        POST_HEADER_MARKER,
        "! H1 controls the Appendix C post branch: <=120 mm uses TB/TD cantilever clouds; >120 mm uses weld-principle force extraction.",
        "! The value is injected from input.json so new intakes do not inherit stale source-package dimensions.",
        f"H1={outer_m:.6f}",
    ]
    if thickness_m is not None:
        lines.extend(
            [
                "! H2 records square tube wall thickness in meters for downstream source traceability.",
                f"H2={thickness_m:.6f}",
            ]
        )
    lines.append("")
    return "\n".join(lines) + text, {
        "status": "applied",
        "H1_m": outer_m,
        "H2_m": thickness_m,
        "source_ref": "input.json:metadata.square_section_outer_mm/support.square_tube_width_m",
    }


def _align_appendix_c_threshold(text: str) -> tuple[str, dict[str, Any]]:
    pattern = re.compile(r"^\s*\*IF\s*,\s*H1\s*,\s*LT\s*,\s*0\.14\s*,\s*THEN\s*$", re.IGNORECASE | re.MULTILINE)
    replacement = (
        "! CableTrayAI Appendix C branch rule: square outer width <=120 mm exports TB/TD cantilever stress clouds; >120 mm uses weld-principle extraction.\n"
        "*IF,H1,LE,0.120001,THEN\n"
    )
    updated, count = pattern.subn(replacement, text, count=1)
    return updated, {
        "status": "applied" if count else "not_found",
        "replaced_count": count,
        "source_ref": "analysis_scope.square_outer_width_le_120_requires_cantilever_stress_clouds",
    }


def _parameterized_cantilever_selector() -> str:
    return "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI参数化S2模型托臂选择器。",
            "! 方钢支架为TYPE=1；托臂为按层生成的BEAM188类型：",
            "!   front: 10*I+2 and 10*I+3",
            "!   back : 200*I+2 and 200*I+3",
            "! 这里替代旧的TYPE=1且SEC不等于1选择方式，避免参数化建模后选空。",
            "ESEL,NONE",
            "*DO,I,1,qiancengshu,1",
            "ESEL,A,TYPE,,10*I+2",
            "ESEL,A,TYPE,,10*I+3",
            "*ENDDO",
            "*DO,I,1,houcengshu,1",
            "ESEL,A,TYPE,,200*I+2",
            "ESEL,A,TYPE,,200*I+3",
            "*ENDDO",
        ]
    )


def _section_based_cantilever_selector() -> str:
    return "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI audited cantilever selector for grouped mixed S2 models.",
            "! Grouped mixed tray arms use TYPE=2 with arm sections 2 and 3.",
            "ESEL,S,SEC,,2",
            "ESEL,A,SEC,,3",
        ]
    )


def _component_based_cantilever_selector() -> str:
    return "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI混合托盘标准流：托臂应力按建模阶段声明的组件提取。",
            "! CTAI_ARM_ELEMS由generated_model.mac中的LS_ARM/ARM_SEC登记生成。",
            "CMSEL,S,CTAI_ARM_ELEMS,ELEM",
        ]
    )


def _parameterized_structural_selector() -> str:
    return "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI parameterized MAXBEAMSTRESS selector.",
            "! Match department TYPE=1 semantics: square support plus tray arms; trays and bolt connector types are excluded.",
            "ESEL,S,TYPE,,1",
            "*DO,I,1,qiancengshu,1",
            "ESEL,A,TYPE,,10*I+2",
            "ESEL,A,TYPE,,10*I+3",
            "*ENDDO",
            "*DO,I,1,houcengshu,1",
            "ESEL,A,TYPE,,200*I+2",
            "ESEL,A,TYPE,,200*I+3",
            "*ENDDO",
        ]
    )


def _section_based_structural_selector() -> str:
    return "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI grouped mixed MAXBEAMSTRESS selector.",
            "! Match department TYPE=1 semantics: square support SEC=1 plus tray arms SEC=2/3; tray SEC=4..9 and bolts are excluded.",
            "ESEL,S,SEC,,1",
            "ESEL,A,SEC,,2",
            "ESEL,A,SEC,,3",
        ]
    )


def _component_based_structural_selector() -> str:
    return "\n".join(
        [
            "ALLSEL",
            "! CableTrayAI mixed tray standard flow: MAXBEAMSTRESS selects the TYPE=1-equivalent component.",
            "! Equivalent to the department TYPE=1 selector: square support plus tray arms, no trays/bolts.",
            "CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM",
            "CMSEL,A,CTAI_ARM_ELEMS,ELEM",
        ]
    )


def _model_uses_component_topology(job_dir: Path) -> bool:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return False
    model_text = model_path.read_text(encoding="utf-8", errors="ignore")
    required = ("CTAI_SUPPORT_ELEMS", "CTAI_ARM_ELEMS", "CTAI_TRAY_ELEMS", "CTAI_BOLT_ELEMS")
    return all(name in model_text for name in required)


def _model_uses_source_type1_arm_topology(job_dir: Path) -> bool:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return False
    model_text = model_path.read_text(encoding="utf-8", errors="ignore")
    has_source_arm_latt = bool(re.search(r"LATT\s*,\s*1\s*,\s*,\s*1\s*,\s*,\s*,\s*,\s*[23]\b", model_text, re.IGNORECASE))
    has_parameterized_arm_type = bool(re.search(r"10\s*\*\s*I\s*\+\s*[23]|200\s*\*\s*I\s*\+\s*[23]", model_text, re.IGNORECASE))
    return has_source_arm_latt and not has_parameterized_arm_type


def _model_uses_section_based_arm_topology(job_dir: Path) -> bool:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return False
    model_text = model_path.read_text(encoding="utf-8", errors="ignore")
    return (
        "current-type grouped mixed tray model" in model_text
        or re.search(r"(?im)^\s*ARM_ET\s*\(\s*NARM\s*\)\s*=\s*2\s*$", model_text) is not None
    ) and re.search(r"(?im)^\s*ARM_SEC\s*\(\s*NARM\s*\)\s*=\s*[23]\s*$", model_text) is not None


def _replace_last_regex(text: str, pattern: str, replacement: str, *, flags: int = 0) -> tuple[str, int]:
    matches = list(re.finditer(pattern, text, flags))
    if not matches:
        return text, 0
    match = matches[-1]
    return text[: match.start()] + replacement + text[match.end() :], 1


def _replace_or_inject_maxbeam_selector(prefix: str, selector: str) -> tuple[str, str]:
    def with_trailing_newline(value: str) -> str:
        return value if not value or value.endswith(("\n", "\r")) else value + "\n"

    compact_prefix = re.sub(r"\s+", "", prefix).upper()
    compact_selector = re.sub(r"\s+", "", selector).upper()
    if compact_selector in compact_prefix:
        return with_trailing_newline(prefix), "already_aligned"

    generated_patterns = [
        (
            r"(?ims)^\s*ALLSEL\s*\n"
            r"\s*! CableTrayAI mixed tray standard flow: MAXBEAMSTRESS selects declared structural elements\..*?"
            r"^\s*CMSEL\s*,\s*S\s*,\s*CTAI_STRUCTURAL_ELEMS\s*,\s*ELEM\s*$",
            "generated_structural_selector_replaced",
        ),
        (
            r"(?ims)^\s*ALLSEL\s*\n"
            r"\s*! CableTrayAI mixed tray standard flow: MAXBEAMSTRESS selects the TYPE=1-equivalent component\..*?"
            r"^\s*CMSEL\s*,\s*A\s*,\s*CTAI_ARM_ELEMS\s*,\s*ELEM\s*$",
            "generated_type1_selector_replaced",
        ),
        (
            r"(?ims)^\s*ALLSEL\s*\n"
            r"\s*! CableTrayAI grouped mixed MAXBEAMSTRESS selector\..*?"
            r"^\s*ESEL\s*,\s*A\s*,\s*SEC\s*,\s*,\s*3\s*$",
            "generated_section_selector_replaced",
        ),
        (
            r"(?ims)^\s*ALLSEL\s*\n"
            r"\s*! CableTrayAI parameterized MAXBEAMSTRESS selector\..*?"
            r"^\s*\*ENDDO\s*$",
            "generated_parameterized_selector_replaced",
        ),
    ]
    for pattern, mode in generated_patterns:
        updated, count = _replace_last_regex(prefix, pattern, selector)
        if count:
            return with_trailing_newline(updated), mode

    section_pattern = (
        r"(?ims)^\s*ESEL\s*,\s*S\s*,\s*SEC\s*,\s*,\s*1\s*$\n"
        r"\s*ESEL\s*,\s*A\s*,\s*SEC\s*,\s*,\s*2\s*$\n"
        r"\s*ESEL\s*,\s*A\s*,\s*SEC\s*,\s*,\s*3\s*$"
    )
    updated, count = _replace_last_regex(prefix, section_pattern, selector)
    if count:
        return with_trailing_newline(updated), "section_selector_replaced"

    updated, count = _replace_last_regex(
        prefix,
        r"(?im)^\s*ESEL\s*,\s*S\s*,\s*TYPE\s*,\s*,\s*1\s*$",
        selector,
    )
    if count:
        return with_trailing_newline(updated), "legacy_type1_replaced"

    return prefix + ("" if prefix.endswith("\n") or not prefix else "\n") + selector + "\n", "selector_injected_before_maxbeam"


def _align_maxbeam_selector(
    text: str,
    *,
    preserve_source_type1_arm_topology: bool = False,
    use_section_based_arm_topology: bool = False,
    use_component_topology: bool = False,
) -> tuple[str, dict[str, Any]]:
    create = re.search(r"^\s*\*CREATE\s*,\s*MAXBEAMSTRESS-WRITE\s*,\s*MAC\b", text, re.IGNORECASE | re.MULTILINE)
    if not create:
        return text, {"status": "not_found", "reason": "MAXBEAMSTRESS-WRITE not found"}
    if preserve_source_type1_arm_topology:
        return text, {
            "status": "source_topology_preserved",
            "source_ref": "generated_model.mac:LATT source-family topology assigns support and tray arms to TYPE=1",
            "selector": ["ESEL,S,TYPE,,1"],
            "policy": "Reviewed department source models keep TYPE=1 as the audited support-plus-arm selector for MAXBEAMSTRESS; tray elements are TYPE=2 and are not selected.",
        }

    prefix = text[: create.start()]
    suffix = text[create.start() :]
    if use_component_topology:
        selector = _component_based_structural_selector()
        selector_ref = "generated_model.mac:CTAI_TYPE1_ELEMS semantics via CTAI_SUPPORT_ELEMS + CTAI_ARM_ELEMS"
        new_selector = ["CMSEL,S,CTAI_SUPPORT_ELEMS,ELEM", "CMSEL,A,CTAI_ARM_ELEMS,ELEM"]
    elif use_section_based_arm_topology:
        selector = _section_based_structural_selector()
        selector_ref = "generated_model.mac:grouped mixed TYPE=1-equivalent sections 1/2/3"
        new_selector = ["ESEL,S,SEC,,1", "ESEL,A,SEC,,2", "ESEL,A,SEC,,3"]
    else:
        selector = _parameterized_structural_selector()
        selector_ref = "generated_model.mac:TYPE=1 support plus layer-specific arm types"
        new_selector = [
            "ESEL,S,TYPE,,1",
            "ESEL,A,TYPE,,10*I+2",
            "ESEL,A,TYPE,,10*I+3",
            "ESEL,A,TYPE,,200*I+2",
            "ESEL,A,TYPE,,200*I+3",
        ]

    updated_prefix, replacement_mode = _replace_or_inject_maxbeam_selector(prefix, selector)
    return updated_prefix + suffix, {
        "status": "already_aligned" if replacement_mode == "already_aligned" else "applied",
        "replacement_mode": replacement_mode,
        "source_ref": selector_ref,
        "old_selector": ["ESEL,S,TYPE,,1"],
        "new_selector": new_selector,
        "policy": "MAXBEAMSTRESS must follow the generated model topology and match the department TYPE=1 scope: square support plus tray arms, excluding trays and bolts.",
    }


def _replace_or_inject_tmax_selector(prefix: str, selector: str) -> tuple[str, str]:
    def compact(line: str) -> str:
        return re.sub(r"\s+", "", line).upper()

    def rebuild(lines: list[str]) -> str:
        return "\n".join(lines) + "\n"

    def replace_lines(lines: list[str], start: int, end: int) -> str:
        return rebuild(lines[:start] + selector.splitlines() + lines[end:])

    compact_prefix = re.sub(r"\s+", "", prefix).upper()
    compact_selector = re.sub(r"\s+", "", selector).upper()
    if compact_selector in compact_prefix:
        return prefix if prefix.endswith(("\n", "\r")) else prefix + "\n", "already_aligned"

    lines = prefix.splitlines()
    for index in range(len(lines) - 1, -1, -1):
        if "cabletrayai audited cantilever selector" not in lines[index].lower():
            continue
        start = index
        for probe in range(index, max(-1, index - 5), -1):
            if compact(lines[probe]) == "ALLSEL":
                start = probe
                break
        end = index + 1
        enddo_count = 0
        saw_parameterized_selector = False
        for probe in range(start, len(lines)):
            current = compact(lines[probe])
            if current == "ESEL,NONE":
                saw_parameterized_selector = True
            if saw_parameterized_selector and current == "*ENDDO":
                enddo_count += 1
                if enddo_count >= 2:
                    end = probe + 1
                    break
            if current == "ESEL,A,SEC,,3":
                end = probe + 1
                break
            if current == "CMSEL,S,CTAI_ARM_ELEMS,ELEM":
                end = probe + 1
                break
        else:
            end = min(len(lines), index + 1)
        return replace_lines(lines, start, end), "parameterized_selector_replaced"

    for index in range(len(lines) - 1, -1, -1):
        if compact(lines[index]) != "ESEL,U,SEC,,1":
            continue
        prev = index - 1
        while prev >= 0 and not lines[prev].strip():
            prev -= 1
        if prev < 0 or compact(lines[prev]) != "ESEL,S,TYPE,,1":
            continue
        allsel = prev - 1
        while allsel >= 0 and not lines[allsel].strip():
            allsel -= 1
        if allsel < 0 or compact(lines[allsel]) != "ALLSEL":
            continue
        return replace_lines(lines, allsel, index + 1), "legacy_type1_replaced"

    return prefix + ("" if prefix.endswith("\n") or not prefix else "\n") + selector + "\n", "selector_injected_before_tmax"


def _align_tmax_selector(
    text: str,
    *,
    preserve_source_type1_arm_topology: bool = False,
    use_section_based_arm_topology: bool = False,
    use_component_topology: bool = False,
) -> tuple[str, dict[str, Any]]:
    create = re.search(r"^\s*\*CREATE\s*,\s*TMAXBEAMSTRESS-WRITE\s*,\s*MAC\b", text, re.IGNORECASE | re.MULTILINE)
    if not create:
        return text, {"status": "not_found", "reason": "TMAXBEAMSTRESS-WRITE not found"}
    if preserve_source_type1_arm_topology:
        return text, {
            "status": "source_topology_preserved",
            "source_ref": "generated_model.mac:LATT assigns square support and tray arms to TYPE=1 with SEC filtering",
            "selector": ["ESEL,S,TYPE,,1", "ESEL,U,SEC,,1"],
            "policy": "Standard command-flow family models keep the audited source TMAX selector because tray arms are TYPE=1 and non-square sections.",
        }
    prefix = text[: create.start()]
    suffix = text[create.start() :]
    if use_component_topology:
        selector = _component_based_cantilever_selector()
    elif use_section_based_arm_topology:
        selector = _section_based_cantilever_selector()
    else:
        selector = _parameterized_cantilever_selector()
    updated_prefix, replacement_mode = _replace_or_inject_tmax_selector(prefix, selector)
    selector_ref = (
        "generated_model.mac:CTAI_ARM_ELEMS component"
        if use_component_topology
        else (
        "generated_model.mac:grouped mixed tray arms use TYPE=2 with ARM_SEC 2/3"
        if use_section_based_arm_topology
        else "generated_model.mac:LATT assigns tray arms to TYPE 10*I+2/10*I+3 and 200*I+2/200*I+3"
        )
    )
    new_selector = (
        ["CMSEL,S,CTAI_ARM_ELEMS,ELEM"]
        if use_component_topology
        else (
        ["ESEL,S,SEC,,2", "ESEL,A,SEC,,3"]
        if use_section_based_arm_topology
        else [
            "ESEL,NONE",
            "ESEL,A,TYPE,,10*I+2",
            "ESEL,A,TYPE,,10*I+3",
            "ESEL,A,TYPE,,200*I+2",
            "ESEL,A,TYPE,,200*I+3",
        ]
        )
    )
    return updated_prefix + suffix, {
        "status": "applied",
        "replacement_mode": replacement_mode,
        "source_ref": selector_ref,
        "old_selector": ["ESEL,S,TYPE,,1", "ESEL,U,SEC,,1"],
        "new_selector": new_selector,
    }


def _source_type1_tbmodel_selector() -> str:
    return "\n".join(
        [
            "! CableTrayAI source-family TBMODEL selector.",
            "! Source-family tray arms use TYPE=1 with non-square sections; do not select 10*layer TYPE IDs.",
            "ESEL,S,TYPE,,1",
            "ESEL,U,SEC,,1",
        ]
    )


def _section_based_tbmodel_selector() -> str:
    return "\n".join(
        [
            "! CableTrayAI grouped mixed TBMODEL selector.",
            "! Grouped mixed models use SEC=2/3 for tray arms and SEC=4..9 for tray beams; bolt sections 10/11 are excluded.",
            "ESEL,S,SEC,,2",
            "ESEL,A,SEC,,3",
            "ESEL,A,SEC,,4,9",
        ]
    )


def _component_based_tbmodel_selector() -> str:
    return "\n".join(
        [
            "! CableTrayAI混合托盘标准流：图5.2按组件显示托臂和托盘。",
            "! 该选择来自generated_model.mac的拓扑组件，不依赖TYPE/SEC猜测。",
            "CMSEL,S,CTAI_ARM_ELEMS,ELEM",
            "CMSEL,A,CTAI_TRAY_ELEMS,ELEM",
        ]
    )


def _align_tbmodel_selector(
    text: str,
    *,
    preserve_source_type1_arm_topology: bool = False,
    use_section_based_arm_topology: bool = False,
    use_component_topology: bool = False,
) -> tuple[str, dict[str, Any]]:
    pattern = re.compile(
        r"ESEL\s*,\s*NONE\s*\n"
        r"\s*\*DO\s*,\s*_CTAI_LAYER\s*,\s*1\s*,\s*10\s*,\s*1\s*\n"
        r"\s*ESEL\s*,\s*A\s*,\s*TYPE\s*,\s*,\s*10\s*\*\s*_CTAI_LAYER\s*\+\s*2\s*\n"
        r"\s*ESEL\s*,\s*A\s*,\s*TYPE\s*,\s*,\s*10\s*\*\s*_CTAI_LAYER\s*\+\s*3\s*\n"
        r"\s*ESEL\s*,\s*A\s*,\s*TYPE\s*,\s*,\s*10\s*\*\s*_CTAI_LAYER\s*\+\s*4\s*\n"
        r"\s*ESEL\s*,\s*A\s*,\s*TYPE\s*,\s*,\s*200\s*\*\s*_CTAI_LAYER\s*\+\s*2\s*\n"
        r"\s*ESEL\s*,\s*A\s*,\s*TYPE\s*,\s*,\s*200\s*\*\s*_CTAI_LAYER\s*\+\s*3\s*\n"
        r"\s*ESEL\s*,\s*A\s*,\s*TYPE\s*,\s*,\s*200\s*\*\s*_CTAI_LAYER\s*\+\s*4\s*\n"
        r"\s*\*ENDDO",
        re.IGNORECASE,
    )
    if use_component_topology or use_section_based_arm_topology:
        replacement = _component_based_tbmodel_selector() if use_component_topology else _section_based_tbmodel_selector()
        updated, count = pattern.subn(replacement, text)
        if use_component_topology and not count and "CMSEL,S,CTAI_ARM_ELEMS,ELEM" in text:
            return text, {
                "status": "already_component_topology",
                "replaced_count": 0,
                "selector": ["CMSEL,S,CTAI_ARM_ELEMS,ELEM", "CMSEL,A,CTAI_TRAY_ELEMS,ELEM"],
                "source_ref": "generated_post.mac:TBMODEL selector already matches CableTrayAI topology components",
                "policy": "图5.2按建模组件显示托臂和托盘，不使用旧的10*layer/200*layer TYPE猜选。",
            }
        if not count and "ESEL,S,SEC,,2" in text and "ESEL,A,SEC,,4,9" in text:
            return text, {
                "status": "already_section_topology",
                "replaced_count": 0,
                "selector": ["ESEL,S,SEC,,2", "ESEL,A,SEC,,3", "ESEL,A,SEC,,4,9"],
                "source_ref": "generated_post.mac:TBMODEL selector already matches grouped mixed section topology",
                "policy": "Fig. 5.2 TBMODEL selection follows grouped mixed topology so MAPDL does not warn about undefined 10*layer/200*layer TYPE IDs.",
            }
        if use_component_topology:
            return updated, {
                "status": "component_topology_applied" if count else "not_found",
                "replaced_count": count,
                "selector": ["CMSEL,S,CTAI_ARM_ELEMS,ELEM", "CMSEL,A,CTAI_TRAY_ELEMS,ELEM"],
                "source_ref": "generated_model.mac:CTAI_ARM_ELEMS/CTAI_TRAY_ELEMS",
                "policy": "图5.2按CableTrayAI混合托盘拓扑组件选择托臂和托盘，避免TYPE/SEC或坐标错选。",
            }
        return updated, {
            "status": "section_topology_applied" if count else "not_found",
            "replaced_count": count,
            "selector": ["ESEL,S,SEC,,2", "ESEL,A,SEC,,3", "ESEL,A,SEC,,4,9"],
            "source_ref": "generated_model.mac:grouped mixed tray arms/trays are selected by section numbers",
            "policy": "Fig. 5.2 TBMODEL selection follows grouped mixed topology so MAPDL does not warn about undefined 10*layer/200*layer TYPE IDs.",
        }
    if not preserve_source_type1_arm_topology:
        return text, {
            "status": "parameterized_type_selector_preserved",
            "source_ref": "templates/apdl/post_extract_s2.mac.j2:TBMODEL selector",
        }
    updated, count = pattern.subn(_source_type1_tbmodel_selector(), text)
    return updated, {
        "status": "source_topology_applied" if count else "not_found",
        "replaced_count": count,
        "selector": ["ESEL,S,TYPE,,1", "ESEL,U,SEC,,1"],
        "source_ref": "generated_model.mac:LATT assigns source-family tray arms to TYPE=1 and non-square sections",
        "policy": "Fig. 5.2 TBMODEL selection follows the same source topology as TMAX so MAPDL does not warn about undefined 10*layer/200*layer TYPE IDs.",
    }


def align_postprocessor_to_intake(job_dir: Path | str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Patch generated post commands so the shared S2 extractor matches the parameterized model.

    The original PIP assumes a model where BEAM188 TYPE=1 plus section filtering can
    isolate support and tray-arm sets. The current parameterized model uses TYPE=1
    for the square support and per-layer types for tray arms. This function keeps
    the source block but aligns branch parameters and selectors with that topology.
    """

    job_dir = Path(job_dir)
    post_path = job_dir / "generated_post.mac"
    if not post_path.exists():
        return {"status": "skipped", "reason": "generated_post.mac missing"}
    payload = _load_input(job_dir, payload)
    original = post_path.read_text(encoding="utf-8", errors="replace")
    text, branch_audit = _prepend_branch_parameters(original, payload)
    text, threshold_audit = _align_appendix_c_threshold(text)
    use_component_topology = _model_uses_component_topology(job_dir)
    preserve_source_topology = _model_uses_source_type1_arm_topology(job_dir)
    use_section_based_topology = _model_uses_section_based_arm_topology(job_dir)
    text, tbmodel_audit = _align_tbmodel_selector(
        text,
        preserve_source_type1_arm_topology=preserve_source_topology,
        use_section_based_arm_topology=use_section_based_topology,
        use_component_topology=use_component_topology,
    )
    text, maxbeam_audit = _align_maxbeam_selector(
        text,
        preserve_source_type1_arm_topology=preserve_source_topology,
        use_section_based_arm_topology=use_section_based_topology,
        use_component_topology=use_component_topology,
    )
    text, selector_audit = _align_tmax_selector(
        text,
        preserve_source_type1_arm_topology=preserve_source_topology,
        use_section_based_arm_topology=use_section_based_topology,
        use_component_topology=use_component_topology,
    )
    changed = text != original
    if changed:
        post_path.write_text(text, encoding="utf-8", newline="\n")
    audit = {
        "status": "applied" if changed else "unchanged",
        "post_path": str(post_path),
        "branch_parameters": branch_audit,
        "appendix_c_threshold": threshold_audit,
        "component_topology": use_component_topology,
        "section_based_arm_topology": use_section_based_topology,
        "tbmodel_selector": tbmodel_audit,
        "maxbeam_selector": maxbeam_audit,
        "tmax_selector": selector_audit,
        "policy": "Result extraction selectors must follow the generated model topology: MAX equals the department TYPE=1 scope (square support plus tray arms, no trays/bolts), SQUARE is square support only, TMAX is cantilever arms only.",
    }
    (job_dir / "postprocessor_alignment_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return audit
