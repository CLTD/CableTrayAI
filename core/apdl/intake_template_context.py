from __future__ import annotations

from pathlib import Path
from typing import Any

from core.apdl.modal_policy import MODAL_CUTOFF_HZ, modal_mode_count_from_payload


def _section_name(value: str | None, default: str) -> str:
    text = str(value or default).strip()
    if not text:
        return default
    return Path(text).stem


def _default_layer() -> dict[str, Any]:
    return {
        "a": 0.0,
        "b": 0.0,
        "c": 0.0,
        "density": 7850.0,
        "cantilever1_sect": "50-42",
        "cantilever2_sect": "CAOGANG42DAN",
        "tray_sect": "500-75-2mm",
    }


def _layer_context(layer: dict[str, Any], tray_section: str, arm_section: str, arm_secondary_section: str) -> dict[str, Any]:
    return {
        "a": float(layer.get("arm_a_length_m") or 0.0),
        "b": float(layer.get("arm_b_length_m") or 0.0),
        "c": float(layer.get("tray_width_m") or 0.0),
        "density": float(layer.get("tray_density_kg_m3") or 7850.0),
        "cantilever1_sect": arm_section,
        "cantilever2_sect": arm_secondary_section,
        "tray_sect": tray_section,
    }


def build_standard_s2_template_context(payload: dict[str, Any]) -> dict[str, Any]:
    support = payload.get("support") or {}
    sections = {str(item.get("section_id")): item for item in payload.get("sections") or []}
    support_section = sections.get(str(support.get("support_section_id"))) or {}
    tray_layers = payload.get("tray_layers") or []
    qian = {index: _default_layer() for index in range(1, 11)}
    hou = {index: _default_layer() for index in range(1, 11)}
    explicit_back_indices: set[int] = set()
    for layer in tray_layers:
        index = int(layer.get("layer_index") or 0)
        if not (1 <= index <= 10):
            continue
        tray_section_entry = sections.get(str(layer.get("tray_section_id"))) or {}
        tray_section = _section_name(tray_section_entry.get("sect_file"), "500-75-2mm")
        arm_section_entry = sections.get(str(layer.get("arm_section_id"))) or sections.get("arm-main") or {}
        arm_secondary_entry = sections.get("arm-secondary") or {}
        arm_section = _section_name(arm_section_entry.get("sect_file"), "50-42")
        arm_secondary = _section_name(arm_secondary_entry.get("sect_file"), "CAOGANG42DAN")
        target = hou if str(layer.get("side") or "").lower() == "back" else qian
        target[index] = _layer_context(layer, tray_section, arm_section, arm_secondary)
        if target is hou:
            explicit_back_indices.add(index)
    front_count = int(support.get("layers_front") or max((int(item.get("layer_index") or 0) for item in tray_layers if str(item.get("side")).lower() != "back"), default=1))
    back_count = int(support.get("layers_back") or max((int(item.get("layer_index") or 0) for item in tray_layers if str(item.get("side")).lower() == "back"), default=0))
    if back_count > 0 and not explicit_back_indices:
        # The intake parser stores symmetric "double-side" tray descriptions once.
        # The source APDL template still builds a front and back branch, so mirror
        # front layer parameters into the back branch rather than emitting zero
        # geometry that MAPDL rejects as coincident keypoints.
        for index in range(1, min(back_count, 10) + 1):
            source_index = index if index <= max(front_count, 1) else max(front_count, 1)
            hou[index] = dict(qian[source_index])
    return {
        "steel_width_m": float(support.get("square_tube_width_m") or 0.1),
        "steel_length_m": float(support.get("support_height_m") or 1.0),
        "span_m": float(support.get("support_spacing_m") or 2.0),
        "steel_sect_file": _section_name(support_section.get("sect_file"), "100-100-6"),
        "qian_n_layers": max(front_count, 1),
        "hou_n_layers": max(back_count, 0),
        "qian": qian,
        "hou": hou,
        "modal_mode_count": modal_mode_count_from_payload(payload),
        "modal_frequency_cutoff_hz": MODAL_CUTOFF_HZ,
    }
