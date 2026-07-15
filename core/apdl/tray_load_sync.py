from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.intake.tray_load_parser import TRAY_AREA_M2


_NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?"
_TRACE_BLOCK = re.compile(
    r"(?ms)^! CTAI_TRAY_LOAD_AUDIT_BEGIN\s*$.*?^! CTAI_TRAY_LOAD_AUDIT_END\s*$\n?"
)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0.0 else None


def _width_mm(layer: dict[str, Any]) -> int:
    direct = _float(layer.get("tray_width_mm"))
    if direct is not None:
        return int(round(direct))
    metres = _float(layer.get("tray_width_m"))
    return int(round(metres * 1000.0)) if metres is not None else 0


def expected_tray_load_layers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    mapping = metadata.get("tray_load_mapping") if isinstance(metadata.get("tray_load_mapping"), dict) else {}
    raw_layers = mapping.get("layers") if isinstance(mapping.get("layers"), list) else payload.get("tray_layers")
    if not isinstance(raw_layers, list):
        return []

    layers: list[dict[str, Any]] = []
    for position, raw in enumerate(raw_layers):
        if not isinstance(raw, dict):
            continue
        width = _width_mm(raw)
        density = _float(raw.get("tray_density_kg_m3"))
        load = _float(raw.get("load_kg_per_m"))
        if load is None and density is not None and width in TRAY_AREA_M2:
            load = density * TRAY_AREA_M2[width]
        if density is None and load is not None and width in TRAY_AREA_M2:
            density = load / TRAY_AREA_M2[width]
        if width <= 0 or density is None:
            continue
        layers.append(
            {
                "source_index": position,
                "side": str(raw.get("side") or "front").strip().lower(),
                "layer_index": int(raw.get("layer_index") or position + 1),
                "tray_width_mm": width,
                "load_kg_per_m": load,
                "tray_density_kg_m3": density,
                "source_ref": raw.get("source_ref") or "input.json:tray_layers",
            }
        )
    return layers


def tray_load_baseline_sha256(payload: dict[str, Any]) -> str:
    canonical = [
        {
            "side": layer["side"],
            "layer_index": layer["layer_index"],
            "tray_width_mm": layer["tray_width_mm"],
            "load_kg_per_m": round(float(layer["load_kg_per_m"] or 0.0), 9),
            "tray_density_kg_m3": round(float(layer["tray_density_kg_m3"]), 9),
        }
        for layer in expected_tray_load_layers(payload)
    ]
    encoded = json.dumps(canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def prepend_tray_load_trace(model_text: str, payload: dict[str, Any]) -> str:
    layers = expected_tray_load_layers(payload)
    if not layers:
        return model_text
    cleaned = _TRACE_BLOCK.sub("", model_text)
    lines = [
        "! CTAI_TRAY_LOAD_AUDIT_BEGIN",
        f"! baseline_sha256={tray_load_baseline_sha256(payload)}",
        "! Operator line loads are converted to equivalent tray material density before ANSYS execution.",
    ]
    for layer in layers:
        load = layer.get("load_kg_per_m")
        load_text = f"{float(load):.9g}" if load is not None else "UNKNOWN"
        lines.append(
            "! side={side};layer={layer};width_mm={width};line_load_kg_m={load};density_kg_m3={density:.12g};source_ref={source}".format(
                side=layer["side"],
                layer=layer["layer_index"],
                width=layer["tray_width_mm"],
                load=load_text,
                density=float(layer["tray_density_kg_m3"]),
                source=str(layer.get("source_ref") or "input.json").replace("\n", " "),
            )
        )
    lines.extend(["! CTAI_TRAY_LOAD_AUDIT_END", ""])
    return "\n".join(lines) + cleaned.lstrip("\n")


def _parse_density_commands(model_text: str) -> tuple[dict[int, float], dict[str, float]]:
    materials: dict[int, float] = {}
    arrays: dict[str, float] = {}
    for match in re.finditer(rf"(?im)^\s*MP\s*,\s*DENS\s*,\s*(\d+)\s*,\s*({_NUMBER})\s*$", model_text):
        materials[int(match.group(1))] = float(match.group(2))
    for match in re.finditer(rf"(?im)^\s*([QH]DENS)\s*\(\s*(\d+)\s*\)\s*=\s*({_NUMBER})\s*$", model_text):
        arrays[f"{match.group(1).upper()}({int(match.group(2))})"] = float(match.group(3))
    return materials, arrays


def _close(actual: float | None, expected: float, *, rounded_source: bool) -> bool:
    if actual is None:
        return False
    absolute_tolerance = 0.51 if rounded_source else 1e-5
    return math.isclose(actual, expected, rel_tol=1e-8, abs_tol=absolute_tolerance)


def audit_tray_load_command_sync(
    job_dir: Path | str,
    payload: dict[str, Any],
    *,
    parameterization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    model_path = job_dir / "generated_model.mac"
    expected = expected_tray_load_layers(payload)
    if not expected:
        result = {
            "status": "not_applicable",
            "reason": "No tray layers were present in the normalized input.",
            "source_ref": "input.json",
        }
        (job_dir / "tray_load_command_audit.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    failures: list[dict[str, Any]] = []
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    override_layers = metadata.get("tray_load_override_layers") if isinstance(metadata.get("tray_load_override_layers"), list) else []
    skipped = metadata.get("tray_load_override_skipped") if isinstance(metadata.get("tray_load_override_skipped"), list) else []
    override_count = int(metadata.get("tray_load_override_count") or 0)
    if override_layers or override_count or skipped:
        if metadata.get("tray_load_override_status") != "applied":
            failures.append({"check": "operator_override_status", "actual": metadata.get("tray_load_override_status")})
        if override_count != len(override_layers):
            failures.append(
                {"check": "operator_override_count", "declared": override_count, "record_count": len(override_layers)}
            )
        if skipped:
            failures.append({"check": "operator_override_unmatched", "items": skipped})

    expected_by_key = {(item["side"], int(item["layer_index"])): item for item in expected}
    for override in override_layers:
        key = (str(override.get("side") or "front").lower(), int(override.get("layer_index") or 0))
        layer = expected_by_key.get(key)
        new_density = _float(override.get("new_tray_density_kg_m3"))
        if layer is None or new_density is None or not _close(
            float(layer["tray_density_kg_m3"]), new_density, rounded_source=False
        ):
            failures.append({"check": "operator_override_input_sync", "key": key, "override": override, "input": layer})

    if not model_path.exists():
        failures.append({"check": "generated_model_exists", "path": str(model_path)})
        model_text = ""
    else:
        model_text = model_path.read_text(encoding="utf-8", errors="replace")
    materials, arrays = _parse_density_commands(model_text)

    topology_path = job_dir / "apdl_topology_manifest.json"
    command_checks: list[dict[str, Any]] = []
    if topology_path.exists() and arrays:
        topology = json.loads(topology_path.read_text(encoding="utf-8"))
        for model_layer in topology.get("layers") or []:
            side = str(model_layer.get("side") or "front").lower()
            original_index = int(model_layer.get("original_layer_index") or model_layer.get("layer_index") or 0)
            model_index = int(model_layer.get("model_layer_index") or model_layer.get("layer_index") or 0)
            expected_layer = expected_by_key.get((side, original_index))
            variable = f"{'Q' if side == 'front' else 'H'}DENS({model_index})"
            actual = arrays.get(variable)
            passed = bool(
                expected_layer
                and _close(actual, float(expected_layer["tray_density_kg_m3"]), rounded_source=False)
            )
            check = {
                "side": side,
                "original_layer_index": original_index,
                "model_layer_index": model_index,
                "tray_width_mm": expected_layer.get("tray_width_mm") if expected_layer else None,
                "load_kg_per_m": expected_layer.get("load_kg_per_m") if expected_layer else None,
                "expected_density_kg_m3": expected_layer.get("tray_density_kg_m3") if expected_layer else None,
                "command_variable": variable,
                "command_density_kg_m3": actual,
                "status": "pass" if passed else "fail",
            }
            command_checks.append(check)
            if not passed:
                failures.append({"check": "layer_density_command_sync", **check})
        command_mapping = "topology_manifest_array_mapping"
    elif topology_path.exists():
        topology = json.loads(topology_path.read_text(encoding="utf-8"))
        topology_widths = sorted(
            {int(item.get("width_mm") or 0) for item in topology.get("layers") or [] if int(item.get("width_mm") or 0) > 0},
            reverse=True,
        )
        density_by_width: dict[int, list[float]] = defaultdict(list)
        for layer in expected:
            density_by_width[int(layer["tray_width_mm"])].append(float(layer["tray_density_kg_m3"]))
        for width, densities in density_by_width.items():
            if max(densities) - min(densities) > 1e-5:
                failures.append(
                    {
                        "check": "same_width_distinct_layer_loads_not_representable",
                        "tray_width_mm": width,
                        "densities_kg_m3": densities,
                        "reason": "The grouped topology uses one tray material slot per width.",
                    }
                )
        for material_id, width in enumerate(topology_widths, start=2):
            densities = density_by_width.get(width) or []
            if not densities:
                continue
            expected_density = max(densities)
            actual = materials.get(material_id)
            passed = _close(actual, expected_density, rounded_source=False)
            check = {
                "material_id": material_id,
                "tray_width_mm": width,
                "expected_density_kg_m3": expected_density,
                "command_density_kg_m3": actual,
                "status": "pass" if passed else "fail",
            }
            command_checks.append(check)
            if not passed:
                failures.append({"check": "grouped_material_density_command_sync", **check})
        command_mapping = "topology_manifest_grouped_material_mapping"
    else:
        parameterization = parameterization or {}
        slots = parameterization.get("material_slot_widths_mm")
        slots = [int(value) for value in slots] if isinstance(slots, list) else []
        density_by_width: dict[int, list[float]] = defaultdict(list)
        for layer in expected:
            density_by_width[int(layer["tray_width_mm"])].append(float(layer["tray_density_kg_m3"]))
        for width, densities in density_by_width.items():
            if max(densities) - min(densities) > 1e-5:
                failures.append(
                    {
                        "check": "same_width_distinct_layer_loads_not_representable",
                        "tray_width_mm": width,
                        "densities_kg_m3": densities,
                        "reason": "The selected department source family has one tray material slot per width.",
                    }
                )
        for material_id, width in enumerate(slots, start=2):
            densities = density_by_width.get(width) or []
            if not densities:
                continue
            expected_density = round(max(densities))
            actual = materials.get(material_id)
            passed = _close(actual, float(expected_density), rounded_source=True)
            check = {
                "material_id": material_id,
                "tray_width_mm": width,
                "expected_density_kg_m3": expected_density,
                "command_density_kg_m3": actual,
                "status": "pass" if passed else "fail",
            }
            command_checks.append(check)
            if not passed:
                failures.append({"check": "material_density_command_sync", **check})
        if not slots:
            command_values = list(materials.values())
            for layer in expected:
                density = float(layer["tray_density_kg_m3"])
                passed = any(_close(actual, density, rounded_source=True) for actual in command_values)
                if not passed:
                    failures.append(
                        {
                            "check": "density_present_in_model",
                            "side": layer["side"],
                            "layer_index": layer["layer_index"],
                            "expected_density_kg_m3": density,
                        }
                    )
        command_mapping = "standard_family_material_slot_mapping"

    baseline = tray_load_baseline_sha256(payload)
    header_hash_match = f"! baseline_sha256={baseline}" in model_text
    if not header_hash_match:
        failures.append({"check": "command_header_baseline_hash", "expected": baseline})
    result = {
        "status": "pass" if not failures else "fail",
        "baseline_sha256": baseline,
        "operator_override_status": metadata.get("tray_load_override_status") or "not_requested",
        "operator_override_count": override_count,
        "expected_layers": expected,
        "command_mapping": command_mapping,
        "command_checks": command_checks,
        "header_hash_match": header_hash_match,
        "failures": failures,
        "source_ref": "input.json metadata/tray_layers + generated_model.mac + apdl_topology_manifest.json",
        "policy": (
            "A production run is blocked unless every operator-confirmed line load is applied to input.json and the "
            "corresponding equivalent density is present in the generated ANSYS model command stream."
        ),
    }
    (job_dir / "tray_load_command_audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
