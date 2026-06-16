from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.optimizer.square_section_selector import parse_square_section_name


SUPPORTED_MIXED_SIDES = {"front", "back"}


def _section_stem(value: Any, default: str = "") -> str:
    text = str(value or default).strip()
    if not text:
        return default
    return Path(text).stem


def _width_mm(layer: dict[str, Any]) -> int:
    return int(round(float(layer.get("tray_width_m") or 0.0) * 1000.0))


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
    support_section_id = str(support.get("support_section_id") or "")
    sections = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    candidates: list[Any] = [support.get("square_tube_width_m")]
    section = sections.get(support_section_id)
    if section:
        candidates.extend([section.get("sect_file"), section.get("section_id")])
    for value in candidates:
        parsed = parse_square_section_name(str(value or ""))
        if parsed:
            return parsed.outer_mm
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if 0.01 <= numeric <= 1.0:
            return numeric * 1000.0
        if 10.0 <= numeric <= 1000.0:
            return numeric
    return 0.0


def _arm_section_family(payload: dict[str, Any]) -> tuple[str, str, str]:
    square_outer_mm = _square_outer_width_mm_from_payload(payload)
    if square_outer_mm > 120.0:
        return "YIXINGGANG150", "YIXINGGANG150DAN", "square_gt_120_yixing_arm_family"
    return "50-42", "CAOGANG42DAN", "square_le_120_standard_channel_family"


def _support_section(payload: dict[str, Any]) -> str:
    support = payload.get("support") or {}
    sections = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    support_section_id = str(support.get("support_section_id") or "")
    section = sections.get(support_section_id)
    return _section_stem((section or {}).get("sect_file") or support_section_id, "100-100-6")


def _tray_section(layer: dict[str, Any], payload: dict[str, Any]) -> str:
    sections = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    section_id = str(layer.get("tray_section_id") or "")
    section = sections.get(section_id)
    section_name = _section_stem((section or {}).get("sect_file"), "")
    if section_name:
        return section_name
    width = _width_mm(layer)
    return f"{width}-75-2mm"


def _layers_by_side(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {"front": [], "back": []}
    for layer in payload.get("tray_layers") or []:
        side = str(layer.get("side") or "front").lower()
        if side not in SUPPORTED_MIXED_SIDES:
            continue
        grouped.setdefault(side, []).append(dict(layer))
    for layers in grouped.values():
        layers.sort(key=lambda item: int(item.get("layer_index") or 0))
    return grouped


def should_use_mixed_tray_layer_renderer(payload: dict[str, Any]) -> bool:
    layers = [
        layer
        for layer in payload.get("tray_layers") or []
        if str(layer.get("side") or "front").lower() in SUPPORTED_MIXED_SIDES
    ]
    widths = {_width_mm(layer) for layer in layers if _width_mm(layer) > 0}
    unsupported = [
        str(layer.get("side") or "")
        for layer in payload.get("tray_layers") or []
        if str(layer.get("side") or "front").lower() not in SUPPORTED_MIXED_SIDES
    ]
    return len(widths) > 1 and not unsupported


def _num(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def _kp(front: bool, frame: int, layer: int, suffix: int, numbering: dict[str, int]) -> int:
    base = (500 if front else numbering["back_base"]) + frame * numbering["frame_step"]
    return base + numbering["keypoint_offset"] + 10 * layer + suffix


def _support_kp(frame: int, index: int, numbering: dict[str, int]) -> int:
    return 500 + frame * numbering["frame_step"] + index


def _line_between(k1: int, k2: int, lines: list[str]) -> None:
    if k1 == k2:
        return
    lines.append(f"L,{k1},{k2}")


def _mesh_selected(lines: list[str], *, material: int, etype: int, section: int, size: float) -> None:
    lines.extend(
        [
            f"LATT,{material},,{etype},,,,{section}",
            f"LESIZE,ALL,{_num(size)},,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
        ]
    )


def _select_layer_lines(
    lines: list[str],
    *,
    x1: float,
    x2: float,
    z1: float,
    z2: float | None = None,
) -> None:
    lo, hi = sorted((x1, x2))
    lines.extend(
        [
            "ALLSEL",
            f"LSEL,S,LOC,X,{_num(lo)},{_num(hi)}",
            f"LSEL,R,LOC,Z,{_num(z1)}" if z2 is None else f"LSEL,R,LOC,Z,{_num(z1)},{_num(z2)}",
        ]
    )


def _mesh_layer(lines: list[str], *, layer: dict[str, Any], side: str, et_base: int, sec_base: int, h1: float) -> dict[str, Any]:
    sign = 1.0 if side == "front" else -1.0
    width = _width_mm(layer)
    tray_width_m = width / 1000.0
    arm_total = float(layer.get("arm_a_length_m") or 0.0) + float(layer.get("arm_b_length_m") or 0.0)
    arm_tail = float(layer.get("arm_b_length_m") or 0.0)
    z = 0.1 + 0.2 * (int(layer.get("layer_index") or 1) - 1)
    x_root = sign * (h1 / 2.0)
    x_bolt = sign * (h1 / 2.0 + arm_total - tray_width_m / 2.0)
    x_tail = sign * (h1 / 2.0 + arm_total - arm_tail)
    x_end = sign * (h1 / 2.0 + arm_total)
    tray_offset = 0.068 if width >= 500 else 0.074
    z_tray = z + tray_offset
    z_bolt = z + 0.05
    primary_etype = et_base + 2
    secondary_etype = et_base + 3
    tray_etype = et_base + 4
    tray_material = tray_etype
    primary_section = sec_base + 2
    secondary_section = sec_base + 3
    tray_section = sec_base + 4
    bolt_section = 10
    audit = {
        "side": side,
        "layer_index": int(layer.get("layer_index") or 0),
        "width_mm": width,
        "arm_total_m": round(arm_total, 6),
        "l3_tail_m": round(arm_tail, 6),
        "x_root_m": round(x_root, 6),
        "x_bolt_m": round(x_bolt, 6),
        "x_tail_m": round(x_tail, 6),
        "x_end_m": round(x_end, 6),
        "tray_offset_m": tray_offset,
        "type_ids": {
            "primary_arm": primary_etype,
            "secondary_arm": secondary_etype,
            "tray": tray_etype,
            "bolt": 4,
        },
    }

    if width <= 200:
        primary_start, primary_end = x_root, x_tail
        secondary_start, secondary_end = x_tail, x_end
    else:
        primary_start, primary_end = x_root, x_tail
        secondary_start, secondary_end = x_tail, x_end
    _select_layer_lines(lines, x1=primary_start, x2=primary_end, z1=z)
    lines.append(f"LSEL,U,LOC,X,{_num(x_bolt)}")
    _mesh_selected(lines, material=1, etype=primary_etype, section=primary_section, size=0.02)

    _select_layer_lines(lines, x1=secondary_start, x2=secondary_end, z1=z)
    if abs(secondary_start - secondary_end) > 1e-9:
        _mesh_selected(lines, material=1, etype=secondary_etype, section=secondary_section, size=0.02)
    else:
        lines.extend(["LSEL,NONE", "ALLSEL"])

    lines.extend(
        [
            "ALLSEL",
            f"LSEL,S,LOC,X,{_num(x_bolt)}",
            f"LSEL,R,LOC,Z,{_num(z_tray)}",
        ]
    )
    _mesh_selected(lines, material=tray_material, etype=tray_etype, section=tray_section, size=0.05)

    _select_layer_lines(lines, x1=x_bolt, x2=x_bolt, z1=z, z2=z_bolt)
    _mesh_selected(lines, material=1, etype=4, section=bolt_section, size=0.05)

    lines.extend(
        [
            "ALLSEL",
            f"NSEL,S,LOC,X,{_num(x_bolt)}",
            f"NSEL,R,LOC,Z,{_num(z)},{_num(z_tray)}",
            f"CPCYC,UX,,,,,{_num(tray_offset - 0.05)}",
            f"CPCYC,UY,,,,,{_num(tray_offset - 0.05)}",
            f"CPCYC,UZ,,,,,{_num(tray_offset - 0.05)}",
            f"CPCYC,ROTY,,,,,{_num(tray_offset - 0.05)}",
            f"CPCYC,ROTZ,,,,,{_num(tray_offset - 0.05)}",
            "ALLSEL",
        ]
    )
    return audit


def _keypoint_layer(
    lines: list[str],
    *,
    layer: dict[str, Any],
    side: str,
    numbering: dict[str, int],
    span: float,
    h1: float,
) -> dict[str, Any]:
    front = side == "front"
    sign = 1.0 if front else -1.0
    width = _width_mm(layer)
    tray_width_m = width / 1000.0
    layer_index = int(layer.get("layer_index") or 1)
    arm_total = float(layer.get("arm_a_length_m") or 0.0) + float(layer.get("arm_b_length_m") or 0.0)
    arm_tail = float(layer.get("arm_b_length_m") or 0.0)
    z = 0.1 + 0.2 * (layer_index - 1)
    x_root = sign * (h1 / 2.0)
    x_bolt = sign * (h1 / 2.0 + arm_total - tray_width_m / 2.0)
    x_tail = sign * (h1 / 2.0 + arm_total - arm_tail)
    x_end = sign * (h1 / 2.0 + arm_total)
    tray_offset = 0.068 if width >= 500 else 0.074
    z_tray = z + tray_offset
    z_bolt = z + 0.05
    if width <= 200:
        k2_x, k3_x = x_tail, x_bolt
    else:
        k2_x, k3_x = x_bolt, x_tail
    for frame in range(3):
        y = frame * span
        y_minus = y - span / 2.0
        y_plus = y + span / 2.0
        k1 = _kp(front, frame, layer_index, 1, numbering)
        k2 = _kp(front, frame, layer_index, 2, numbering)
        k3 = _kp(front, frame, layer_index, 3, numbering)
        k4 = _kp(front, frame, layer_index, 4, numbering)
        k6 = _kp(front, frame, layer_index, 6, numbering)
        k7 = _kp(front, frame, layer_index, 7, numbering)
        k8 = _kp(front, frame, layer_index, 8, numbering)
        k9 = _kp(front, frame, layer_index, 9, numbering)
        lines.extend(
            [
                f"K,{k1},{_num(x_root)},{_num(y)},{_num(z)}",
                f"K,{k2},{_num(k2_x)},{_num(y)},{_num(z)}",
                f"K,{k3},{_num(k3_x)},{_num(y)},{_num(z)}",
                f"K,{k4},{_num(x_end)},{_num(y)},{_num(z)}",
                f"K,{k6},{_num(x_bolt)},{_num(y_minus)},{_num(z_tray)}",
                f"K,{k7},{_num(x_bolt)},{_num(y)},{_num(z_tray)}",
                f"K,{k8},{_num(x_bolt)},{_num(y_plus)},{_num(z_tray)}",
                f"K,{k9},{_num(x_bolt)},{_num(y)},{_num(z_bolt)}",
            ]
        )
        if width <= 200:
            _line_between(k1, k2, lines)
            _line_between(k2, k3, lines)
            _line_between(k3, k4, lines)
        else:
            _line_between(k1, k2, lines)
            if abs(k2_x - k3_x) > 1e-9:
                _line_between(k2, k3, lines)
            _line_between(k3, k4, lines)
        _line_between(k6, k7, lines)
        _line_between(k7, k8, lines)
        _line_between(k2, k9, lines)
    return {
        "side": side,
        "layer_index": layer_index,
        "width_mm": width,
        "arm_total_m": round(arm_total, 6),
        "l3_tail_m": round(arm_tail, 6),
    }


def render_mixed_tray_layer_model(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    grouped = _layers_by_side(payload)
    front_layers = grouped.get("front") or []
    back_layers = grouped.get("back") or []
    support = payload.get("support") or {}
    h1 = float(support.get("square_tube_width_m") or (_square_outer_width_mm_from_payload(payload) / 1000.0) or 0.1)
    h2 = float(support.get("support_height_m") or 2.0)
    span = float(support.get("support_spacing_m") or 2.0)
    max_layers = max(len(front_layers), len(back_layers), 1)
    numbering = {
        "keypoint_offset": 0 if max_layers <= 9 else max(20, ((max_layers + 10) // 10) * 10),
        "frame_step": 100 if max_layers <= 9 else 200,
        "back_base": 1500,
    }
    if max_layers > 9:
        frame_span = numbering["keypoint_offset"] + 10 * max_layers + 9
        numbering["frame_step"] = max(200, ((frame_span // 100) + 1) * 100)
        front_third_frame_max = 500 + 2 * numbering["frame_step"] + frame_span
        numbering["back_base"] = 1500 if front_third_frame_max < 1500 else ((front_third_frame_max // 100) + 2) * 100

    support_section = _support_section(payload)
    primary_arm, secondary_arm, arm_policy = _arm_section_family(payload)

    lines: list[str] = [
        "finish",
        "/clear",
        "/prep7",
        "! CableTrayAI generated mixed tray layer model.",
        "! Each tray layer keeps its own width, arm split, section, density, and bolt keypoints.",
        "ET,1,188",
        "KEYOPT,1,4,2",
        "KEYOPT,1,1,1",
        "ET,4,188",
        "KEYOPT,4,4,2",
        "KEYOPT,4,1,1",
        f"H1={_num(h1)}",
        f"H2={_num(h2)}",
        f"L4={_num(span)}",
        f"qiancengshu={len(front_layers)}",
        f"houcengshu={len(back_layers)}",
        f"senum={max_layers if back_layers else len(front_layers)}",
        f"senum1={len(back_layers)}",
        f"KPOFF={numbering['keypoint_offset']}",
        f"KPFSTEP={numbering['frame_step']}",
        f"KPBKBASE={numbering['back_base']}",
        "SECTYPE,1,BEAM,MESH",
        "SECOFFSET,cent,",
        f"SECREAD,'{support_section}','SECT',,MESH",
        "SECTYPE,10,BEAM,CSOLID",
        "SECDATA,0.006",
        "SECOFFSET,USER,",
        "MP,EX,1,2.04E11",
        "MP,PRXY,1,0.3",
        "MP,DENS,1,7850",
    ]

    layer_audits: list[dict[str, Any]] = []
    for side, layers in (("front", front_layers), ("back", back_layers)):
        side_base = 10 if side == "front" else 200
        for layer in layers:
            index = int(layer.get("layer_index") or 1)
            et_base = side_base * index
            tray_density = float(layer.get("tray_density_kg_m3") or 0.0)
            tray_section = _tray_section(layer, payload)
            lines.extend(
                [
                    f"ET,{et_base + 2},188",
                    f"KEYOPT,{et_base + 2},4,2",
                    f"KEYOPT,{et_base + 2},1,1",
                    f"MP,EX,{et_base + 2},2.04E11",
                    f"MP,PRXY,{et_base + 2},0.3",
                    f"MP,DENS,{et_base + 2},7850",
                    f"SECTYPE,{et_base + 2},BEAM,MESH",
                    "SECOFFSET,cent,",
                    f"SECREAD,'{primary_arm}','SECT',,MESH",
                    f"ET,{et_base + 3},188",
                    f"KEYOPT,{et_base + 3},4,2",
                    f"KEYOPT,{et_base + 3},1,1",
                    f"MP,EX,{et_base + 3},2.04E11",
                    f"MP,PRXY,{et_base + 3},0.3",
                    f"MP,DENS,{et_base + 3},7850",
                    f"SECTYPE,{et_base + 3},BEAM,MESH",
                    "SECOFFSET,user,",
                    f"SECREAD,'{secondary_arm}','SECT',,MESH",
                    f"ET,{et_base + 4},188",
                    f"KEYOPT,{et_base + 4},4,2",
                    f"KEYOPT,{et_base + 4},1,1",
                    f"MP,EX,{et_base + 4},2.04E11",
                    f"MP,PRXY,{et_base + 4},0.3",
                    f"MP,DENS,{et_base + 4},{_num(tray_density)}",
                    f"SECTYPE,{et_base + 4},BEAM,MESH",
                    "SECOFFSET,cent,",
                    f"SECREAD,'{tray_section}','SECT',,MESH",
                ]
            )

    for frame in range(3):
        base = 500 + frame * numbering["frame_step"]
        y = frame * span
        lines.append(f"K,{base},0,{_num(y)},0")
        for index in range(1, max_layers + 1):
            z = 0.1 + 0.2 * (index - 1)
            lines.append(f"K,{base + index},0,{_num(y)},{_num(z)}")
        lines.append(f"K,{base + max_layers + 1},0,{_num(y)},{_num(h2)}")
        for index in range(1, max_layers + 2):
            lines.append(f"L,{base + index - 1},{base + index}")

    for side, layers in (("front", front_layers), ("back", back_layers)):
        for layer in layers:
            layer_audits.append(_keypoint_layer(lines, layer=layer, side=side, numbering=numbering, span=span, h1=h1))

    lines.extend(
        [
            "NUMMRG,KP",
            "ALLSEL",
            "LSEL,S,LOC,X,0",
        ]
    )
    _mesh_selected(lines, material=1, etype=1, section=1, size=0.05)

    mesh_audits: list[dict[str, Any]] = []
    for side, layers in (("front", front_layers), ("back", back_layers)):
        side_base = 10 if side == "front" else 200
        for layer in layers:
            index = int(layer.get("layer_index") or 1)
            mesh_audits.append(_mesh_layer(lines, layer=layer, side=side, et_base=side_base * index, sec_base=side_base * index, h1=h1))

    for frame in range(3):
        y = frame * span
        for index in range(1, max_layers + 1):
            z = 0.1 + 0.2 * (index - 1)
            cp_nodes = [f"node(0,{_num(y)},{_num(z)})"]
            if index <= len(front_layers):
                cp_nodes.append(f"node({_num(h1 / 2.0)},{_num(y)},{_num(z)})")
            if index <= len(back_layers):
                cp_nodes.append(f"node({_num(-h1 / 2.0)},{_num(y)},{_num(z)})")
            if len(cp_nodes) > 1:
                lines.append(f"CP,NEXT,ALL,{','.join(cp_nodes)}")

    ls_names_front: list[str] = []
    ls_names_back: list[str] = []
    for side, layers in (("front", front_layers), ("back", back_layers)):
        sign = 1.0 if side == "front" else -1.0
        for layer in layers:
            index = int(layer.get("layer_index") or 1)
            width = _width_mm(layer)
            arm_total = float(layer.get("arm_a_length_m") or 0.0) + float(layer.get("arm_b_length_m") or 0.0)
            x_bolt = sign * (h1 / 2.0 + arm_total - width / 2000.0)
            z_bolt = 0.15 + 0.2 * (index - 1)
            name = f"LS{index if side == 'front' else index + 10}"
            if side == "front":
                ls_names_front.append(name)
            else:
                ls_names_back.append(name)
            lines.extend(
                [
                    "ALLSEL",
                    f"NSEL,S,LOC,X,{_num(x_bolt)}",
                    f"NSEL,R,LOC,Z,{_num(z_bolt)}",
                    f"CM,{name},NODE",
                ]
            )

    top_index = max_layers + 1
    lines.extend(
        [
            "ALLSEL",
            f"KSEL,S,KP,,{_support_kp(0, top_index, numbering)},{_support_kp(2, top_index, numbering)},{numbering['frame_step']}",
            "NSLK,S,1",
            "CM,YUESHU,NODE",
            "ALLSEL",
        ]
    )
    if ls_names_front:
        lines.append(f"NSEL,S,,,{ls_names_front[0]}")
        for name in ls_names_front[1:]:
            lines.append(f"NSEL,A,,,{name}")
        lines.append("CM,LS100,NODE")
    if ls_names_back:
        lines.append(f"NSEL,S,,,{ls_names_back[0]}")
        for name in ls_names_back[1:]:
            lines.append(f"NSEL,A,,,{name}")
        lines.append("CM,LS200,NODE")
    lines.append("ALLSEL")
    if ls_names_front or ls_names_back:
        first = "LS100" if ls_names_front else "LS200"
        lines.append(f"NSEL,S,,,{first}")
        if ls_names_front and ls_names_back:
            lines.append("NSEL,A,,,LS200")
        lines.append("CM,LS,NODE")
    lines.extend(["ALLSEL", "FINISH", ""])

    widths = sorted({_width_mm(layer) for layer in front_layers + back_layers})
    audit = {
        "status": "pass",
        "model_source": "deterministic_mixed_tray_layer_renderer",
        "support_section": support_section,
        "arm_primary_section": primary_arm,
        "arm_secondary_section": secondary_arm,
        "arm_section_policy": arm_policy,
        "tray_widths_mm": widths,
        "model_geometry_widths_mm": widths,
        "source_geometry_widths_mm": [],
        "shared_max_width_geometry": {
            "status": "not_used",
            "policy": "Mixed tray layers are modeled explicitly per layer; no shared maximum-width geometry fallback is used.",
        },
        "physical_bolt_modeling": {
            "status": "pass",
            "section_10": "BEAM CSOLID diameter 0.006 m",
            "keypoint_suffix": 9,
            "policy": "Every layer includes tray-arm connector keypoints and BEAM188 CSOLID bolt lines; coupling is supplemental only.",
        },
        "assigned": {
            "H1": round(h1, 6),
            "H2": round(h2, 6),
            "L4": round(span, 6),
            "senum": max_layers if back_layers else len(front_layers),
            "senum1": len(back_layers),
        },
        "keypoint_numbering": {
            "status": "expanded_for_high_layer_count" if max_layers > 9 else "legacy_source_numbering",
            "enabled": max_layers > 9,
            "max_layers": max_layers,
            "safe_legacy_layer_limit": 9,
            "keypoint_offset": numbering["keypoint_offset"],
            "frame_step": numbering["frame_step"],
            "back_base": numbering["back_base"],
        },
        "layer_geometry": mesh_audits,
        "policy": (
            "This renderer is used only for mixed tray widths. It preserves the reviewed S2 keypoint families "
            "while assigning each layer its own tray section, density, arm split and connector location."
        ),
    }
    return "\n".join(lines), audit
