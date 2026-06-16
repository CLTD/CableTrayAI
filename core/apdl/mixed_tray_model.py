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
        layers.sort(key=lambda item: (-_width_mm(item), int(item.get("layer_index") or 0)))
        for model_index, item in enumerate(layers, start=1):
            item["original_layer_index"] = int(item.get("layer_index") or model_index)
            item["model_layer_index"] = model_index
            item["layer_index"] = model_index
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


def _mesh_selected(lines: list[str], *, material: int, etype: int, section: int, size: float) -> None:
    lines.extend(
        [
            f"LATT,{material},,{etype},,,,{section}",
            f"LESIZE,ALL,{_num(size)},,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
        ]
    )


def _secondary_arm_secoffset(secondary_arm: str) -> tuple[str, str]:
    if str(secondary_arm or "").upper() == "CAOGANG42DAN":
        return "SECOFFSET,user,,-0.03249", "channel_secondary_arm_offset_minus_0p03249"
    return "SECOFFSET,user", "non_channel_secondary_arm_no_offset"


def _tray_offset_m(width_mm: int) -> float:
    return 0.068 if width_mm >= 500 else 0.074


def _layer_geometry_audit(layer: dict[str, Any], *, side: str, h1: float) -> dict[str, Any]:
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
    return {
        "side": side,
        "model_layer_index": int(layer.get("model_layer_index") or layer.get("layer_index") or 0),
        "original_layer_index": int(layer.get("original_layer_index") or layer.get("layer_index") or 0),
        "layer_index": int(layer.get("layer_index") or 0),
        "width_mm": width,
        "arm_total_m": round(arm_total, 6),
        "l3_tail_m": round(arm_tail, 6),
        "x_root_m": round(x_root, 6),
        "x_bolt_m": round(x_bolt, 6),
        "x_tail_m": round(x_tail, 6),
        "x_end_m": round(x_end, 6),
        "tray_offset_m": _tray_offset_m(width),
    }


def _append_layer_arrays(lines: list[str], *, prefix: str, layers: list[dict[str, Any]]) -> None:
    if not layers:
        return
    lines.extend(
        [
            f"*DIM,{prefix}W,ARRAY,{len(layers)}",
            f"*DIM,{prefix}A,ARRAY,{len(layers)}",
            f"*DIM,{prefix}B,ARRAY,{len(layers)}",
            f"*DIM,{prefix}DENS,ARRAY,{len(layers)}",
            f"*DIM,{prefix}TOFF,ARRAY,{len(layers)}",
        ]
    )
    for index, layer in enumerate(layers, start=1):
        width = _width_mm(layer)
        lines.extend(
            [
                f"{prefix}W({index})={_num(width / 1000.0)}",
                f"{prefix}A({index})={_num(float(layer.get('arm_a_length_m') or 0.0))}",
                f"{prefix}B({index})={_num(float(layer.get('arm_b_length_m') or 0.0))}",
                f"{prefix}DENS({index})={_num(float(layer.get('tray_density_kg_m3') or 0.0))}",
                f"{prefix}TOFF({index})={_num(_tray_offset_m(width))}",
            ]
        )


def _append_side_keypoint_loop(lines: list[str], *, side: str, layer_count: int, prefix: str) -> None:
    if layer_count <= 0:
        return
    front = side == "front"
    base = "500" if front else "KPBKBASE"
    x_root = "H1/2" if front else "-H1/2"
    x_bolt = f"H1/2+{prefix}A(I)+{prefix}B(I)-{prefix}W(I)/2"
    x_tail = f"H1/2+{prefix}A(I)"
    x_end = f"H1/2+{prefix}A(I)+{prefix}B(I)"
    if not front:
        x_bolt = f"-({x_bolt})"
        x_tail = f"-({x_tail})"
        x_end = f"-({x_end})"

    def kid(suffix: int) -> str:
        if front:
            return f"{500 + suffix}+KPOFF+10*I+KPFSTEP*(J-1)"
        return f"{base}+{suffix}+KPOFF+10*I+KPFSTEP*(J-1)"

    lines.extend(
        [
            f"! {side} mixed tray layers: looped keypoints keep small trays above wider trays.",
            f"*DO,J,1,3",
            f"*DO,I,1,{layer_count}",
            "QZ=0.1+0.2*(I-1)",
            f"QTRAYZ=QZ+{prefix}TOFF(I)",
            "QBOLTZ=QZ+0.05",
            f"QXBOLT={x_bolt}",
            f"QXTAIL={x_tail}",
            f"QXEND={x_end}",
            f"*IF,{prefix}W(I),LE,0.2,THEN",
            "QX2=QXTAIL",
            "QX3=QXBOLT",
            "*ELSE",
            "QX2=QXBOLT",
            "QX3=QXTAIL",
            "*ENDIF",
            f"K,{kid(1)},{x_root},L4*(J-1),QZ",
            f"K,{kid(2)},QX2,L4*(J-1),QZ",
            f"K,{kid(3)},QX3,L4*(J-1),QZ",
            f"K,{kid(4)},QXEND,L4*(J-1),QZ",
            f"K,{kid(6)},QXBOLT,-L4/2+L4*(J-1),QTRAYZ",
            f"K,{kid(7)},QXBOLT,L4*(J-1),QTRAYZ",
            f"K,{kid(8)},QXBOLT,L4/2+L4*(J-1),QTRAYZ",
            f"K,{kid(9)},QXBOLT,L4*(J-1),QBOLTZ",
            f"L,{kid(1)},{kid(2)}",
            "*IF,ABS(QX2-QX3),GT,1E-8,THEN",
            f"L,{kid(2)},{kid(3)}",
            "*ENDIF",
            f"L,{kid(3)},{kid(4)}",
            f"L,{kid(6)},{kid(7)}",
            f"L,{kid(7)},{kid(8)}",
            f"*IF,{prefix}W(I),LE,0.2,THEN",
            f"L,{kid(3)},{kid(9)}",
            "*ELSE",
            f"L,{kid(2)},{kid(9)}",
            "*ENDIF",
            "*ENDDO",
            "*ENDDO",
        ]
    )


def _append_side_mesh_loop(lines: list[str], *, side: str, layer_count: int, prefix: str) -> None:
    if layer_count <= 0:
        return
    front = side == "front"
    et_expr = "10*I" if front else "200*I"
    x_root = "H1/2" if front else "-H1/2"
    x_bolt_unsigned = f"H1/2+{prefix}A(I)+{prefix}B(I)-{prefix}W(I)/2"
    x_tail_unsigned = f"H1/2+{prefix}A(I)"
    x_end_unsigned = f"H1/2+{prefix}A(I)+{prefix}B(I)"
    x_bolt = x_bolt_unsigned if front else f"-({x_bolt_unsigned})"
    x_tail = x_tail_unsigned if front else f"-({x_tail_unsigned})"
    x_end = x_end_unsigned if front else f"-({x_end_unsigned})"

    lines.extend(
        [
            f"! {side} mixed tray layers: looped meshing by per-layer section/material ids.",
            f"*DO,I,1,{layer_count}",
            f"QET={et_expr}",
            "QZ=0.1+0.2*(I-1)",
            f"QTRAYZ=QZ+{prefix}TOFF(I)",
            "QBOLTZ=QZ+0.05",
            f"QXBOLT={x_bolt}",
            f"QXTAIL={x_tail}",
            f"QXEND={x_end}",
            "QXLO=MIN(QXTAIL,H1/2)",
            "QXHI=MAX(QXTAIL,H1/2)",
        ]
    )
    if not front:
        lines[-2] = "QXLO=MIN(QXTAIL,-H1/2)"
        lines[-1] = "QXHI=MAX(QXTAIL,-H1/2)"
    lines.extend(
        [
            "ALLSEL",
            "LSEL,S,LOC,X,QXLO,QXHI",
            "LSEL,R,LOC,Z,QZ",
            "LSEL,U,LOC,X,QXBOLT",
            "LATT,1,,QET+2,,,,QET+2",
            "LESIZE,ALL,0.02,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "QXLO=MIN(QXTAIL,QXEND)",
            "QXHI=MAX(QXTAIL,QXEND)",
            "*IF,ABS(QXTAIL-QXEND),GT,1E-8,THEN",
            "LSEL,S,LOC,X,QXLO,QXHI",
            "LSEL,R,LOC,Z,QZ",
            "LATT,1,,QET+3,,,,QET+3",
            "LESIZE,ALL,0.02,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "*ENDIF",
            "LSEL,S,LOC,X,QXBOLT",
            "LSEL,R,LOC,Z,QTRAYZ",
            "LATT,QET+4,,QET+4,,,,QET+4",
            "LESIZE,ALL,0.05,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "LSEL,S,LOC,X,QXBOLT,QXBOLT",
            "LSEL,R,LOC,Z,QZ,QBOLTZ",
            "LATT,1,,4,,,,10",
            "LESIZE,ALL,0.05,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "NSEL,S,LOC,X,QXBOLT",
            "NSEL,R,LOC,Z,QZ,QTRAYZ",
            f"CPCYC,UX,,,,,{prefix}TOFF(I)-0.05",
            f"CPCYC,UY,,,,,{prefix}TOFF(I)-0.05",
            f"CPCYC,UZ,,,,,{prefix}TOFF(I)-0.05",
            f"CPCYC,ROTY,,,,,{prefix}TOFF(I)-0.05",
            f"CPCYC,ROTZ,,,,,{prefix}TOFF(I)-0.05",
            "ALLSEL",
            "*ENDDO",
        ]
    )


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

    _append_layer_arrays(lines, prefix="Q", layers=front_layers)
    _append_layer_arrays(lines, prefix="H", layers=back_layers)

    secondary_offset_line, secondary_offset_policy = _secondary_arm_secoffset(secondary_arm)
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
                    secondary_offset_line,
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

    lines.extend(
        [
            "! Standardized support-column loop.",
            "*DO,J,1,3",
            "K,500+KPFSTEP*(J-1),0,L4*(J-1),0",
            "*DO,I,1,senum",
            "K,500+I+KPFSTEP*(J-1),0,L4*(J-1),0.1+0.2*(I-1)",
            "*ENDDO",
            "K,500+senum+1+KPFSTEP*(J-1),0,L4*(J-1),H2",
            "*DO,I,1,senum+1",
            "L,500+(I-1)+KPFSTEP*(J-1),500+I+KPFSTEP*(J-1)",
            "*ENDDO",
            "*ENDDO",
        ]
    )
    _append_side_keypoint_loop(lines, side="front", layer_count=len(front_layers), prefix="Q")
    _append_side_keypoint_loop(lines, side="back", layer_count=len(back_layers), prefix="H")

    lines.extend(
        [
            "NUMMRG,KP",
            "ALLSEL",
            "LSEL,S,LOC,X,0",
        ]
    )
    _mesh_selected(lines, material=1, etype=1, section=1, size=0.05)

    _append_side_mesh_loop(lines, side="front", layer_count=len(front_layers), prefix="Q")
    _append_side_mesh_loop(lines, side="back", layer_count=len(back_layers), prefix="H")

    lines.extend(
        [
            "! Couple support-column nodes to same-elevation tray-arm root nodes.",
            "*DO,J,1,3",
            "*DO,I,1,senum",
            "QZ=0.1+0.2*(I-1)",
            "NROOT=NODE(0,L4*(J-1),QZ)",
            "*IF,I,LE,qiancengshu,THEN",
            "NFROOT=NODE(H1/2,L4*(J-1),QZ)",
            "*IF,I,LE,houcengshu,THEN",
            "NBROOT=NODE(-H1/2,L4*(J-1),QZ)",
            "CP,NEXT,ALL,NROOT,NFROOT,NBROOT",
            "*ELSE",
            "CP,NEXT,ALL,NROOT,NFROOT",
            "*ENDIF",
            "*ELSE",
            "*IF,I,LE,houcengshu,THEN",
            "NBROOT=NODE(-H1/2,L4*(J-1),QZ)",
            "CP,NEXT,ALL,NROOT,NBROOT",
            "*ENDIF",
            "*ENDIF",
            "*ENDDO",
            "*ENDDO",
        ]
    )

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

    lines.extend(
        [
            "ALLSEL",
            "KSEL,S,KP,,500+senum+1,500+2*KPFSTEP+senum+1,KPFSTEP",
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
    layer_geometry = [
        _layer_geometry_audit(layer, side=side, h1=h1)
        for side, layers in (("front", front_layers), ("back", back_layers))
        for layer in layers
    ]
    audit = {
        "status": "pass",
        "model_source": "deterministic_mixed_tray_layer_renderer",
        "support_section": support_section,
        "arm_primary_section": primary_arm,
        "arm_secondary_section": secondary_arm,
        "arm_section_policy": arm_policy,
        "secondary_arm_offset_policy": secondary_offset_policy,
        "tray_widths_mm": widths,
        "model_geometry_widths_mm": widths,
        "source_geometry_widths_mm": [],
        "layer_order_policy": {
            "status": "width_descending_small_trays_above",
            "policy": "For each side, mixed tray widths are modeled from wider lower layers to narrower upper layers; original layer indices are retained in layer_geometry.",
        },
        "command_style": {
            "status": "loop_parameterized",
            "policy": "K/L geometry, support-column lines, meshing selections, root coupling and per-layer coordinates are generated with APDL arrays and *DO loops; section/material definitions remain explicit for review.",
        },
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
        "layer_geometry": layer_geometry,
        "policy": (
            "This renderer is used only for mixed tray widths. It preserves the reviewed S2 keypoint families "
            "while assigning each layer its own tray section, density, arm split and connector location."
        ),
    }
    return "\n".join(lines), audit
