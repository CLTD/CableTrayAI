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


def _secondary_arm_secoffset(secondary_arm: str) -> tuple[str, str]:
    if str(secondary_arm or "").upper() == "CAOGANG42DAN":
        return "SECOFFSET,user,,-0.03249", "channel_secondary_arm_offset_minus_0p03249"
    return "SECOFFSET,user", "non_channel_secondary_arm_no_offset"


def _tray_offset_m(width_mm: int, secondary_arm: str | None = None) -> float:
    if str(secondary_arm or "").upper() == "CAOGANG42DAN":
        return 0.074
    return 0.068 if width_mm >= 500 else 0.074


def _bolt_radius_m_for_widths(widths_mm: list[int]) -> tuple[float, str]:
    positive_widths = [int(width) for width in widths_mm if int(width) > 0]
    if positive_widths and max(positive_widths) <= 200:
        return 0.004, "tray_width_le_200_uses_m8_nominal_round_bar_radius"
    return 0.006, "tray_width_gt_200_uses_m12_nominal_round_bar_radius"


def _layer_geometry_audit(layer: dict[str, Any], *, side: str, h1: float, secondary_arm: str) -> dict[str, Any]:
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
        "tray_offset_m": _tray_offset_m(width, secondary_arm),
    }


def _append_layer_arrays(lines: list[str], *, prefix: str, layers: list[dict[str, Any]], secondary_arm: str) -> None:
    if not layers:
        return
    lines.extend(
        [
            f"*DIM,{prefix}W,ARRAY,{len(layers)}",
            f"*DIM,{prefix}A,ARRAY,{len(layers)}",
            f"*DIM,{prefix}B,ARRAY,{len(layers)}",
            f"*DIM,{prefix}ALEN,ARRAY,{len(layers)}",
            f"*DIM,{prefix}L3A,ARRAY,{len(layers)}",
            f"*DIM,{prefix}DENS,ARRAY,{len(layers)}",
            f"*DIM,{prefix}TOFF,ARRAY,{len(layers)}",
            f"*DIM,{prefix}CODE,ARRAY,{len(layers)}",
        ]
    )
    for index, layer in enumerate(layers, start=1):
        width = _width_mm(layer)
        arm_a = float(layer.get("arm_a_length_m") or 0.0)
        arm_b = float(layer.get("arm_b_length_m") or 0.0)
        lines.extend(
            [
                f"{prefix}W({index})={_num(width / 1000.0)}",
                f"{prefix}A({index})={_num(arm_a)}",
                f"{prefix}B({index})={_num(arm_b)}",
                f"{prefix}ALEN({index})={_num(arm_a + arm_b)}",
                f"{prefix}L3A({index})={_num(arm_b)}",
                f"{prefix}DENS({index})={_num(float(layer.get('tray_density_kg_m3') or 0.0))}",
                f"{prefix}TOFF({index})={_num(_tray_offset_m(width, secondary_arm))}",
                f"{prefix}CODE({index})={width}",
            ]
        )


def _append_side_keypoint_loop(lines: list[str], *, side: str, layer_count: int, prefix: str) -> None:
    if layer_count <= 0:
        return
    front = side == "front"
    base = "500" if front else "KPBKBASE"
    x_root = "H1/2" if front else "-H1/2"
    x_bolt = f"H1/2+{prefix}ALEN(I)-{prefix}W(I)/2"
    x_tail = f"H1/2+{prefix}ALEN(I)-{prefix}L3A(I)"
    x_end = f"H1/2+{prefix}ALEN(I)"
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
            f"QET={10 if front else 200}*I",
            f"QTCODE={prefix}CODE(I)",
            f"QXBOLT={x_bolt}",
            f"QXTAIL={x_tail}",
            f"QXEND={x_end}",
            f"*IF,{prefix}W(I),LE,0.2,THEN",
            "QX2=QXTAIL",
            "QX3=QXBOLT",
            "*ELSEIF,QTCODE,EQ,300,THEN",
            "QX2=QXBOLT",
            "QX3=QXEND",
            "*ELSE",
            "QX2=QXBOLT",
            "QX3=QXTAIL",
            "*ENDIF",
            f"K,{kid(1)},{x_root},L4*(J-1),QZ",
            f"K,{kid(2)},QX2,L4*(J-1),QZ",
            "*IF,QTCODE,EQ,300,THEN",
            f"K,{kid(4)},QXEND,L4*(J-1),QZ",
            f"L,{kid(1)},{kid(2)}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NARM=NARM+1",
            "LS_ARM(NARM)=_LNEW",
            "ARM_ET(NARM)=QET+2",
            "ARM_SEC(NARM)=QET+2",
            f"L,{kid(2)},{kid(4)}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NARM=NARM+1",
            "LS_ARM(NARM)=_LNEW",
            "ARM_ET(NARM)=QET+3",
            "ARM_SEC(NARM)=QET+3",
            "*ELSE",
            f"K,{kid(3)},QX3,L4*(J-1),QZ",
            f"K,{kid(4)},QXEND,L4*(J-1),QZ",
            f"K,{kid(6)},QXBOLT,-L4/2+L4*(J-1),QTRAYZ",
            f"K,{kid(7)},QXBOLT,L4*(J-1),QTRAYZ",
            f"K,{kid(8)},QXBOLT,L4/2+L4*(J-1),QTRAYZ",
            f"K,{kid(9)},QXBOLT,L4*(J-1),QBOLTZ",
            f"L,{kid(1)},{kid(2)}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NARM=NARM+1",
            "LS_ARM(NARM)=_LNEW",
            "ARM_ET(NARM)=QET+2",
            "ARM_SEC(NARM)=QET+2",
            "*IF,ABS(QX2-QX3),GT,1E-8,THEN",
            f"L,{kid(2)},{kid(3)}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NARM=NARM+1",
            "LS_ARM(NARM)=_LNEW",
            "ARM_ET(NARM)=QET+3",
            "ARM_SEC(NARM)=QET+3",
            "*ENDIF",
            "*IF,ABS(QX3-QXEND),GT,1E-8,THEN",
            f"L,{kid(3)},{kid(4)}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NARM=NARM+1",
            "LS_ARM(NARM)=_LNEW",
            "ARM_ET(NARM)=QET+3",
            "ARM_SEC(NARM)=QET+3",
            "*ENDIF",
            "*ENDIF",
            f"*IF,QTCODE,EQ,300,THEN",
            f"K,{kid(6)},QXBOLT,-L4/2+L4*(J-1),QTRAYZ",
            f"K,{kid(7)},QXBOLT,L4*(J-1),QTRAYZ",
            f"K,{kid(8)},QXBOLT,L4/2+L4*(J-1),QTRAYZ",
            f"K,{kid(9)},QXBOLT,L4*(J-1),QBOLTZ",
            "*ENDIF",
            f"L,{kid(6)},{kid(7)}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NTRAY=NTRAY+1",
            "LS_TRAY(NTRAY)=_LNEW",
            "TRAY_ET(NTRAY)=QET+4",
            "TRAY_SEC(NTRAY)=QET+4",
            "TRAY_MAT(NTRAY)=QET+4",
            f"L,{kid(7)},{kid(8)}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NTRAY=NTRAY+1",
            "LS_TRAY(NTRAY)=_LNEW",
            "TRAY_ET(NTRAY)=QET+4",
            "TRAY_SEC(NTRAY)=QET+4",
            "TRAY_MAT(NTRAY)=QET+4",
            f"*IF,{prefix}W(I),LE,0.2,THEN",
            f"L,{kid(3)},{kid(9)}",
            "*ELSE",
            f"L,{kid(2)},{kid(9)}",
            "*ENDIF",
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NBOLT=NBOLT+1",
            "LS_BOLT(NBOLT)=_LNEW",
            "*IF,QTCODE,LE,200,THEN",
            "BOLT_SEC(NBOLT)=11",
            "*ELSE",
            "BOLT_SEC(NBOLT)=10",
            "*ENDIF",
            "*ENDDO",
            "*ENDDO",
        ]
    )


def _append_side_coupling_loop(lines: list[str], *, side: str, layer_count: int, prefix: str) -> None:
    if layer_count <= 0:
        return
    front = side == "front"
    x_bolt_unsigned = f"H1/2+{prefix}ALEN(I)-{prefix}W(I)/2"
    x_bolt = x_bolt_unsigned if front else f"-({x_bolt_unsigned})"

    lines.extend(
        [
            f"! {side} mixed tray layers: looped tray/bolt coupling by per-layer bolt position.",
            f"*DO,I,1,{layer_count}",
            "QZ=0.1+0.2*(I-1)",
            f"QTRAYZ=QZ+{prefix}TOFF(I)",
            f"QXBOLT={x_bolt}",
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


def _append_line_id_mesh_loops(lines: list[str]) -> None:
    lines.extend(
        [
            "! Mesh by recorded line ids. This avoids geometry-location reselection ambiguity in mixed-width models.",
            "ALLSEL",
            "LSEL,NONE",
            "*DO,I,1,NSUP",
            "LSEL,A,LINE,,LS_SUP(I)",
            "*ENDDO",
            "LATT,1,,1,,,,1",
            "LESIZE,ALL,0.05,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "*DO,I,1,NARM",
            "LSEL,S,LINE,,LS_ARM(I)",
            "_ET=ARM_ET(I)",
            "_SEC=ARM_SEC(I)",
            "LATT,1,,_ET,,,,_SEC",
            "LESIZE,ALL,0.02,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "*ENDDO",
            "*DO,I,1,NTRAY",
            "LSEL,S,LINE,,LS_TRAY(I)",
            "_MAT=TRAY_MAT(I)",
            "_ET=TRAY_ET(I)",
            "_SEC=TRAY_SEC(I)",
            "LATT,_MAT,,_ET,,,,_SEC",
            "LESIZE,ALL,0.05,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "*ENDDO",
            "*DO,I,1,NBOLT",
            "LSEL,S,LINE,,LS_BOLT(I)",
            "_BSEC=BOLT_SEC(I)",
            "LATT,1,,4,,,,_BSEC",
            "LESIZE,ALL,0.05,,,,,,,1",
            "LMESH,ALL",
            "ALLSEL",
            "*ENDDO",
        ]
    )


def _side_group_counts(layers: list[dict[str, Any]]) -> list[tuple[int, int]]:
    counts: dict[int, int] = {}
    for layer in layers:
        width = _width_mm(layer)
        if width > 0:
            counts[width] = counts.get(width, 0) + 1
    return [(width, counts[width]) for width in sorted(counts, reverse=True)]


def _mirrored_grouped_mixed_groups(front_layers: list[dict[str, Any]], back_layers: list[dict[str, Any]]) -> list[tuple[int, int]] | None:
    if not front_layers or not back_layers:
        return None
    front = _side_group_counts(front_layers)
    back = _side_group_counts(back_layers)
    if front != back or not (2 <= len(front) <= 5):
        return None
    return front


def _representative_layer_by_width(layers: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for layer in layers:
        width = _width_mm(layer)
        if width > 0 and width not in result:
            result[width] = layer
    return result


def _append_recorded_line(
    lines: list[str],
    start: str,
    end: str,
    bucket: str,
    *,
    arm_et: str | None = None,
    arm_sec: str | None = None,
    tray_et: str | None = None,
    tray_sec: str | None = None,
    tray_mat: str | None = None,
    bolt_sec: str | None = None,
) -> None:
    lines.extend(
        [
            f"L,{start},{end}",
            "*GET,_LNEW,LINE,0,NUM,MAX",
        ]
    )
    if bucket == "ARM":
        lines.extend(
            [
                "NARM=NARM+1",
                "LS_ARM(NARM)=_LNEW",
                "ARM_ET(NARM)=" + str(arm_et or "2"),
                "ARM_SEC(NARM)=" + str(arm_sec or "2"),
            ]
        )
    elif bucket == "TRAY":
        lines.extend(
            [
                "NTRAY=NTRAY+1",
                "LS_TRAY(NTRAY)=_LNEW",
                "TRAY_ET(NTRAY)=" + str(tray_et or "4"),
                "TRAY_SEC(NTRAY)=" + str(tray_sec or "4"),
                "TRAY_MAT(NTRAY)=" + str(tray_mat or "2"),
            ]
        )
    elif bucket == "BOLT":
        lines.extend(["NBOLT=NBOLT+1", "LS_BOLT(NBOLT)=_LNEW", "BOLT_SEC(NBOLT)=" + str(bolt_sec or "10")])
    elif bucket == "SUP":
        lines.extend(["NSUP=NSUP+1", "LS_SUP(NSUP)=_LNEW"])


def _expr_side(expr: str, *, front: bool) -> str:
    return expr if front else f"-({expr})"


def _append_grouped_width_loop(
    lines: list[str],
    *,
    side: str,
    start_expr: str,
    end_expr: str,
    width: int,
    arm_total: float,
    arm_tail: float,
    tray_sec: int,
    tray_mat: int,
) -> None:
    front = side == "front"
    base = 500 if front else 1500
    x_root = "H1/2" if front else "-H1/2"
    total = _num(arm_total)
    tray = _num(width / 1000.0)
    half = _num(width / 2000.0)
    tail = _num(arm_tail)
    x_bolt = _expr_side(f"H1/2+{total}-{half}", front=front)
    x_tail = _expr_side(f"H1/2+{total}-{tail}", front=front)
    x_end = _expr_side(f"H1/2+{total}", front=front)
    def kid(suffix: int) -> str:
        return f"{base + suffix}+10*I+100*(J-1)"

    section_10_or_11 = "11" if width <= 200 else "10"
    lines.extend(
        [
            f"! {side} grouped mixed tray width {width} mm.",
            f"*IF,{end_expr},GE,{start_expr},THEN",
            "*DO,J,1,3",
            f"*DO,I,{start_expr},{end_expr}",
            "QZ=0.1+0.2*(I-1)",
            f"K,{kid(1)},{x_root},L6*(J-1),QZ",
        ]
    )
    if width <= 200:
        lines.extend(
            [
                f"K,{kid(2)},{x_tail},L6*(J-1),QZ",
                f"K,{kid(3)},{x_bolt},L6*(J-1),QZ",
                f"K,{kid(4)},{x_end},L6*(J-1),QZ",
                f"K,{kid(6)},{x_bolt},-L6/2+L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(7)},{x_bolt},L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(8)},{x_bolt},L6/2+L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(9)},{x_bolt},L6*(J-1),0.15+0.2*(I-1)",
            ]
        )
        _append_recorded_line(lines, kid(1), kid(2), "ARM", arm_sec="2")
        _append_recorded_line(lines, kid(2), kid(3), "ARM", arm_sec="3")
        _append_recorded_line(lines, kid(3), kid(4), "ARM", arm_sec="3")
        _append_recorded_line(lines, kid(6), kid(7), "TRAY", tray_sec=str(tray_sec), tray_mat=str(tray_mat))
        _append_recorded_line(lines, kid(7), kid(8), "TRAY", tray_sec=str(tray_sec), tray_mat=str(tray_mat))
        _append_recorded_line(lines, kid(3), kid(9), "BOLT", bolt_sec=section_10_or_11)
    elif width == 300:
        lines.extend(
            [
                f"K,{kid(2)},{x_bolt},L6*(J-1),QZ",
                f"K,{kid(4)},{x_end},L6*(J-1),QZ",
                f"K,{kid(6)},{x_tail},-L6/2+L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(7)},{x_tail},L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(8)},{x_tail},L6/2+L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(9)},{x_bolt},L6*(J-1),0.15+0.2*(I-1)",
            ]
        )
        _append_recorded_line(lines, kid(1), kid(2), "ARM", arm_sec="2")
        _append_recorded_line(lines, kid(2), kid(4), "ARM", arm_sec="3")
        _append_recorded_line(lines, kid(6), kid(7), "TRAY", tray_sec=str(tray_sec), tray_mat=str(tray_mat))
        _append_recorded_line(lines, kid(7), kid(8), "TRAY", tray_sec=str(tray_sec), tray_mat=str(tray_mat))
        _append_recorded_line(lines, kid(2), kid(9), "BOLT", bolt_sec=section_10_or_11)
    else:
        lines.extend(
            [
                f"K,{kid(2)},{x_bolt},L6*(J-1),QZ",
                f"K,{kid(3)},{x_tail},L6*(J-1),QZ",
                f"K,{kid(4)},{x_end},L6*(J-1),QZ",
                f"K,{kid(6)},{x_bolt},-L6/2+L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(7)},{x_bolt},L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(8)},{x_bolt},L6/2+L6*(J-1),0.1+M1+0.2*(I-1)",
                f"K,{kid(9)},{x_bolt},L6*(J-1),0.15+0.2*(I-1)",
            ]
        )
        _append_recorded_line(lines, kid(1), kid(2), "ARM", arm_sec="2")
        _append_recorded_line(lines, kid(2), kid(3), "ARM", arm_sec="3")
        _append_recorded_line(lines, kid(3), kid(4), "ARM", arm_sec="3")
        _append_recorded_line(lines, kid(6), kid(7), "TRAY", tray_sec=str(tray_sec), tray_mat=str(tray_mat))
        _append_recorded_line(lines, kid(7), kid(8), "TRAY", tray_sec=str(tray_sec), tray_mat=str(tray_mat))
        _append_recorded_line(lines, kid(2), kid(9), "BOLT", bolt_sec=section_10_or_11)
    lines.extend(["*ENDDO", "*ENDDO", "*ENDIF"])


def _append_grouped_coupling_loop(lines: list[str], *, side: str, start_expr: str, end_expr: str, width: int, arm_total: float) -> None:
    front = side == "front"
    half = _num(width / 2000.0)
    total = _num(arm_total)
    x_bolt = _expr_side(f"H1/2+{total}-{half}", front=front)
    lines.extend(
        [
            f"*IF,{end_expr},GE,{start_expr},THEN",
            f"*DO,I,{start_expr},{end_expr}",
            "QZ=0.1+0.2*(I-1)",
            "ALLSEL",
            f"NSEL,S,LOC,X,{x_bolt}",
            "NSEL,R,LOC,Z,QZ,0.1+M1+0.2*(I-1)",
            "CPCYC,UX,,,,,M1-0.05",
            "CPCYC,UY,,,,,M1-0.05",
            "CPCYC,UZ,,,,,M1-0.05",
            "CPCYC,ROTY,,,,,M1-0.05",
            "CPCYC,ROTZ,,,,,M1-0.05",
            "ALLSEL",
            "*ENDDO",
            "*ENDIF",
        ]
    )


def _render_mirrored_grouped_mixed_model(payload: dict[str, Any], groups: list[tuple[int, int]], front_layers: list[dict[str, Any]], back_layers: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    support = payload.get("support") or {}
    h1 = float(support.get("square_tube_width_m") or (_square_outer_width_mm_from_payload(payload) / 1000.0) or 0.1)
    h2 = float(support.get("support_height_m") or 2.0)
    span = float(support.get("support_spacing_m") or 2.0)
    support_section = _support_section(payload)
    primary_arm, secondary_arm, arm_policy = _arm_section_family(payload)
    secondary_offset_line, secondary_offset_policy = _secondary_arm_secoffset(secondary_arm)
    representative = _representative_layer_by_width(front_layers + back_layers)
    widths = [width for width, _ in groups]
    bolt_radius_m, bolt_radius_policy = _bolt_radius_m_for_widths(widths)
    total_layers = sum(count for _, count in groups)
    cumulative_counts: list[int] = []
    running_count = 0
    for _, count in groups:
        running_count += count
        cumulative_counts.append(running_count)
    boundary_names = [
        "senum1" if index == len(groups) - 1 else f"senum{len(groups) - index}"
        for index in range(len(groups))
    ]
    boundary_values = dict(zip(boundary_names, cumulative_counts))
    tray_section_numbers = {width: 4 + index for index, (width, _) in enumerate(groups)}
    tray_material_numbers = {width: 2 + index for index, (width, _) in enumerate(groups)}
    line_capacity = max(1, 3 * total_layers * 12)

    lines: list[str] = [
        "finish",
        "/clear",
        "/prep7",
        "! CableTrayAI generated current-type grouped mixed tray model.",
        "! Mirrored double-side mixed widths use senum boundary grouped loops instead of the legacy per-layer renderer.",
        "ET,1,188",
        "KEYOPT,1,4,2",
        "KEYOPT,1,1,1",
        "ET,2,188",
        "KEYOPT,2,4,2",
        "KEYOPT,2,1,1",
        "ET,4,188",
        "KEYOPT,4,4,2",
        "KEYOPT,4,1,1",
        "SECTYPE,1,BEAM,MESH",
        "SECOFFSET,cent,",
        f"SECREAD,'{support_section}','SECT',,MESH",
        "SECTYPE,2,BEAM,MESH",
        "SECOFFSET,cent,",
        f"SECREAD,'{primary_arm}','SECT',,MESH",
        "SECTYPE,3,BEAM,MESH",
        secondary_offset_line,
        f"SECREAD,'{secondary_arm}','SECT',,MESH",
    ]
    for width, _ in groups:
        layer = representative.get(width) or {}
        section = _tray_section(layer, payload)
        mat = tray_material_numbers[width]
        sec = tray_section_numbers[width]
        density = float(layer.get("tray_density_kg_m3") or 0.0)
        lines.extend(
            [
                f"MP,EX,{mat},2.04E11",
                f"MP,PRXY,{mat},0.3",
                f"MP,DENS,{mat},{_num(density)}",
                f"SECTYPE,{sec},BEAM,MESH",
                "SECOFFSET,cent,",
                f"SECREAD,'{section}','SECT',,MESH",
            ]
        )
    lines.extend(
        [
            "SECTYPE,10,BEAM,CSOLID",
            f"SECDATA,{_num(bolt_radius_m)}",
            "SECOFFSET,USER,",
            "SECTYPE,11,BEAM,CSOLID",
            "SECDATA,0.004",
            "SECOFFSET,USER,",
            "MP,EX,1,2.04E11",
            "MP,PRXY,1,0.3",
            "MP,DENS,1,7850",
            f"H1={_num(h1)}",
            f"H2={_num(h2)}",
            f"L6={_num(span)}",
            f"M1={_num(_tray_offset_m(max(widths), secondary_arm))}",
        ]
    )
    for number in range(1, len(groups) + 1):
        name = f"senum{number}"
        lines.append(f"{name}={boundary_values[name]}")
    lines.extend(
        [
            "senum=senum1",
            "senum_back=senum1",
            f"*DIM,LS_SUP,ARRAY,{max(1, 3 * (total_layers + 1))}",
            f"*DIM,LS_ARM,ARRAY,{line_capacity}",
            f"*DIM,ARM_ET,ARRAY,{line_capacity}",
            f"*DIM,ARM_SEC,ARRAY,{line_capacity}",
            f"*DIM,LS_TRAY,ARRAY,{line_capacity}",
            f"*DIM,TRAY_MAT,ARRAY,{line_capacity}",
            f"*DIM,TRAY_ET,ARRAY,{line_capacity}",
            f"*DIM,TRAY_SEC,ARRAY,{line_capacity}",
            f"*DIM,LS_BOLT,ARRAY,{line_capacity}",
            f"*DIM,BOLT_SEC,ARRAY,{line_capacity}",
            "NSUP=0",
            "NARM=0",
            "NTRAY=0",
            "NBOLT=0",
            "*DO,J,1,3",
            "K,500+100*(J-1),0,L6*(J-1),0",
            "*DO,I,1,senum1",
            "K,500+I+100*(J-1),0,L6*(J-1),0.1+0.2*(I-1)",
            "*ENDDO",
            "K,500+senum1+1+100*(J-1),0,L6*(J-1),H2",
            "*DO,I,1,senum1+1",
        ]
    )
    _append_recorded_line(lines, "500+(I-1)+100*(J-1)", "500+I+100*(J-1)", "SUP")
    lines.extend(["*ENDDO", "*ENDDO"])

    starts = ["1"] + [f"{boundary_names[index - 1]}+1" for index in range(1, len(groups))]
    ends = boundary_names
    for index, (width, _) in enumerate(groups):
        layer = representative.get(width) or {}
        arm_total = float(layer.get("arm_a_length_m") or 0.0) + float(layer.get("arm_b_length_m") or 0.0)
        arm_tail = float(layer.get("arm_b_length_m") or 0.0)
        _append_grouped_width_loop(
            lines,
            side="front",
            start_expr=starts[index],
            end_expr=ends[index],
            width=width,
            arm_total=arm_total,
            arm_tail=arm_tail,
            tray_sec=tray_section_numbers[width],
            tray_mat=tray_material_numbers[width],
        )
        _append_grouped_width_loop(
            lines,
            side="back",
            start_expr=starts[index],
            end_expr=ends[index],
            width=width,
            arm_total=arm_total,
            arm_tail=arm_tail,
            tray_sec=tray_section_numbers[width],
            tray_mat=tray_material_numbers[width],
        )

    lines.extend(["NUMMRG,KP"])
    _append_line_id_mesh_loops(lines)
    lines.extend(
        [
            "*DO,J,1,3",
            "*DO,I,1,senum1",
            "QZ=0.1+0.2*(I-1)",
            "CP,NEXT,ALL,NODE(0,L6*(J-1),QZ),NODE(H1/2,L6*(J-1),QZ),NODE(-H1/2,L6*(J-1),QZ)",
            "*ENDDO",
            "*ENDDO",
        ]
    )
    for index, (width, _) in enumerate(groups):
        layer = representative.get(width) or {}
        arm_total = float(layer.get("arm_a_length_m") or 0.0) + float(layer.get("arm_b_length_m") or 0.0)
        _append_grouped_coupling_loop(lines, side="front", start_expr=starts[index], end_expr=ends[index], width=width, arm_total=arm_total)
        _append_grouped_coupling_loop(lines, side="back", start_expr=starts[index], end_expr=ends[index], width=width, arm_total=arm_total)

    lines.extend(
        [
            "ALLSEL",
            "KSEL,S,KP,,500+senum1+1,700+senum1+1,100",
            "NSLK,S,1",
            "CM,YUESHU,NODE",
            "ALLSEL",
            "FINISH",
            "",
        ]
    )
    layer_geometry = [
        _layer_geometry_audit(layer, side=side, h1=h1, secondary_arm=secondary_arm)
        for side, layers in (("front", front_layers), ("back", back_layers))
        for layer in layers
    ]
    return "\n".join(lines), {
        "status": "pass",
        "model_source": "current_type_grouped_mirrored_mixed_renderer",
        "support_section": support_section,
        "arm_primary_section": primary_arm,
        "arm_secondary_section": secondary_arm,
        "arm_section_policy": arm_policy,
        "secondary_arm_offset_policy": secondary_offset_policy,
        "tray_widths_mm": widths,
        "model_geometry_widths_mm": widths,
        "source_geometry_widths_mm": widths,
        "grouped_width_counts": [{"width_mm": width, "count_per_side": count} for width, count in groups],
        "command_style": {
            "status": "senum_grouped_current_type_loops",
            "policy": "Mirrored mixed trays are rendered as grouped width loops using senum1/senum2/senum3 cutoffs, matching the current-type mixed command-flow style and avoiding the old per-layer width-code stream.",
        },
        "physical_bolt_modeling": {
            "status": "pass",
            "section_10": f"M12/large-tray CSOLID radius {bolt_radius_m:g} m",
            "section_11": "M8/small-tray CSOLID radius 0.004 m",
            "bolt_radius_policy": bolt_radius_policy,
            "policy": "Mixed jobs with both small and large trays keep separate M8/M12 bolt section numbers; each bolt line records the correct section before meshing.",
        },
        "assigned": {
            "H1": round(h1, 6),
            "H2": round(h2, 6),
            "L6": round(span, 6),
            "M1": round(_tray_offset_m(max(widths), secondary_arm), 6),
            **{name: boundary_values[name] for name in sorted(boundary_values)},
        },
        "keypoint_numbering": {
            "status": "legacy_source_numbering",
            "enabled": False,
            "max_layers": total_layers,
            "safe_legacy_layer_limit": 9,
            "keypoint_offset": 0,
            "frame_step": 100,
            "back_base": 1500,
        },
        "layer_geometry": layer_geometry,
    }


def render_mixed_tray_layer_model(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    grouped = _layers_by_side(payload)
    front_layers = grouped.get("front") or []
    back_layers = grouped.get("back") or []
    mirrored_groups = _mirrored_grouped_mixed_groups(front_layers, back_layers)
    if mirrored_groups:
        return _render_mirrored_grouped_mixed_model(payload, mirrored_groups, front_layers, back_layers)
    widths = sorted({_width_mm(layer) for layer in front_layers + back_layers})
    bolt_radius_m, bolt_radius_policy = _bolt_radius_m_for_widths(widths)
    support = payload.get("support") or {}
    h1 = float(support.get("square_tube_width_m") or (_square_outer_width_mm_from_payload(payload) / 1000.0) or 0.1)
    h2 = float(support.get("support_height_m") or 2.0)
    span = float(support.get("support_spacing_m") or 2.0)
    max_layers = max(len(front_layers), len(back_layers), 1)
    total_side_layers = len(front_layers) + len(back_layers)
    support_line_capacity = max(1, 3 * (max_layers + 1))
    arm_line_capacity = max(1, 9 * total_side_layers)
    tray_line_capacity = max(1, 6 * total_side_layers)
    bolt_line_capacity = max(1, 3 * total_side_layers)
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
        f"SECDATA,{_num(bolt_radius_m)}",
        "SECOFFSET,USER,",
        "SECTYPE,11,BEAM,CSOLID",
        "SECDATA,0.004",
        "SECOFFSET,USER,",
        "MP,EX,1,2.04E11",
        "MP,PRXY,1,0.3",
        "MP,DENS,1,7850",
    ]

    _append_layer_arrays(lines, prefix="Q", layers=front_layers, secondary_arm=secondary_arm)
    _append_layer_arrays(lines, prefix="H", layers=back_layers, secondary_arm=secondary_arm)
    lines.extend(
        [
            f"*DIM,LS_SUP,ARRAY,{support_line_capacity}",
            f"*DIM,LS_ARM,ARRAY,{arm_line_capacity}",
            f"*DIM,ARM_ET,ARRAY,{arm_line_capacity}",
            f"*DIM,ARM_SEC,ARRAY,{arm_line_capacity}",
            f"*DIM,LS_TRAY,ARRAY,{tray_line_capacity}",
            f"*DIM,TRAY_MAT,ARRAY,{tray_line_capacity}",
            f"*DIM,TRAY_ET,ARRAY,{tray_line_capacity}",
            f"*DIM,TRAY_SEC,ARRAY,{tray_line_capacity}",
            f"*DIM,LS_BOLT,ARRAY,{bolt_line_capacity}",
            f"*DIM,BOLT_SEC,ARRAY,{bolt_line_capacity}",
            "NSUP=0",
            "NARM=0",
            "NTRAY=0",
            "NBOLT=0",
        ]
    )

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
            "*GET,_LNEW,LINE,0,NUM,MAX",
            "NSUP=NSUP+1",
            "LS_SUP(NSUP)=_LNEW",
            "*ENDDO",
            "*ENDDO",
        ]
    )
    _append_side_keypoint_loop(lines, side="front", layer_count=len(front_layers), prefix="Q")
    _append_side_keypoint_loop(lines, side="back", layer_count=len(back_layers), prefix="H")

    lines.extend(
        [
            "NUMMRG,KP",
        ]
    )
    _append_line_id_mesh_loops(lines)
    _append_side_coupling_loop(lines, side="front", layer_count=len(front_layers), prefix="Q")
    _append_side_coupling_loop(lines, side="back", layer_count=len(back_layers), prefix="H")

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

    layer_geometry = [
        _layer_geometry_audit(layer, side=side, h1=h1, secondary_arm=secondary_arm)
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
            "status": "loop_parameterized_line_id_grouped",
            "policy": "K/L geometry, support-column lines, line-id capture, meshing, root coupling and per-layer coordinates are generated with APDL arrays and *DO loops; line ids are recorded with *GET and meshed by recorded groups instead of geometry-location guesses.",
        },
        "shared_max_width_geometry": {
            "status": "not_used",
            "policy": "Mixed tray layers are modeled explicitly per layer; no shared maximum-width geometry fallback is used.",
        },
        "physical_bolt_modeling": {
            "status": "pass",
            "section_10": f"BEAM CSOLID radius {bolt_radius_m:g} m",
            "bolt_radius_policy": bolt_radius_policy,
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
