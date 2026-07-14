import json
from pathlib import Path

from core.apdl.tray_load_sync import audit_tray_load_command_sync, prepend_tray_load_trace


def _payload(layers: list[dict]) -> dict:
    return {
        "tray_layers": [
            {
                "side": layer["side"],
                "layer_index": layer["layer_index"],
                "tray_width_m": layer["tray_width_mm"] / 1000.0,
                "tray_density_kg_m3": layer["tray_density_kg_m3"],
            }
            for layer in layers
        ],
        "metadata": {"tray_load_mapping": {"status": "pass", "layers": layers}},
    }


def test_mixed_layer_operator_loads_match_model_arrays(tmp_path: Path) -> None:
    layers = [
        {
            "side": "front",
            "layer_index": 1,
            "tray_width_mm": 100,
            "load_kg_per_m": 10.0,
            "tray_density_kg_m3": 2597.4,
            "source_ref": "dashboard_confirmed_line_weight",
        },
        {
            "side": "front",
            "layer_index": 2,
            "tray_width_mm": 600,
            "load_kg_per_m": 30.0,
            "tray_density_kg_m3": 16703.786191536747,
            "source_ref": "dashboard_confirmed_line_weight",
        },
    ]
    payload = _payload(layers)
    payload["metadata"].update(
        {
            "tray_load_override_status": "applied",
            "tray_load_override_count": 2,
            "tray_load_override_layers": [
                {
                    "side": item["side"],
                    "layer_index": item["layer_index"],
                    "new_tray_density_kg_m3": item["tray_density_kg_m3"],
                }
                for item in layers
            ],
            "tray_load_override_skipped": [],
        }
    )
    model = "QDENS(1)=16703.786192\nQDENS(2)=2597.4\n"
    (tmp_path / "generated_model.mac").write_text(prepend_tray_load_trace(model, payload), encoding="utf-8")
    (tmp_path / "apdl_topology_manifest.json").write_text(
        json.dumps(
            {
                "layers": [
                    {"side": "front", "model_layer_index": 1, "original_layer_index": 2},
                    {"side": "front", "model_layer_index": 2, "original_layer_index": 1},
                ]
            }
        ),
        encoding="utf-8",
    )

    audit = audit_tray_load_command_sync(tmp_path, payload)

    assert audit["status"] == "pass"
    assert audit["operator_override_count"] == 2
    assert all(item["status"] == "pass" for item in audit["command_checks"])


def test_density_mismatch_blocks_command_audit(tmp_path: Path) -> None:
    layers = [
        {
            "side": "front",
            "layer_index": 1,
            "tray_width_mm": 600,
            "load_kg_per_m": 30.0,
            "tray_density_kg_m3": 16703.786191536747,
        }
    ]
    payload = _payload(layers)
    model = "QDENS(1)=65423.162584\n"
    (tmp_path / "generated_model.mac").write_text(prepend_tray_load_trace(model, payload), encoding="utf-8")
    (tmp_path / "apdl_topology_manifest.json").write_text(
        json.dumps({"layers": [{"side": "front", "model_layer_index": 1, "original_layer_index": 1}]}),
        encoding="utf-8",
    )

    audit = audit_tray_load_command_sync(tmp_path, payload)

    assert audit["status"] == "fail"
    assert any(item["check"] == "layer_density_command_sync" for item in audit["failures"])


def test_standard_family_rejects_distinct_loads_for_one_material_slot(tmp_path: Path) -> None:
    layers = [
        {
            "side": "front",
            "layer_index": 1,
            "tray_width_mm": 600,
            "load_kg_per_m": 20.0,
            "tray_density_kg_m3": 11135.857461,
        },
        {
            "side": "front",
            "layer_index": 2,
            "tray_width_mm": 600,
            "load_kg_per_m": 30.0,
            "tray_density_kg_m3": 16703.786192,
        },
    ]
    payload = _payload(layers)
    model = "MP,DENS,2,16704\n"
    (tmp_path / "generated_model.mac").write_text(prepend_tray_load_trace(model, payload), encoding="utf-8")

    audit = audit_tray_load_command_sync(
        tmp_path,
        payload,
        parameterization={"material_slot_widths_mm": [600]},
    )

    assert audit["status"] == "fail"
    assert any(
        item["check"] == "same_width_distinct_layer_loads_not_representable"
        for item in audit["failures"]
    )
