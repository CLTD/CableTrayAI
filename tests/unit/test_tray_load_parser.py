from __future__ import annotations

from core.intake.tray_load_parser import parse_tray_load_description


def test_tray_load_parser_preserves_500_and_600_widths_from_intake_text() -> None:
    parsed_500 = parse_tray_load_description("双侧3+3层500")
    assert [layer["tray_section_file"] for layer in parsed_500["layers"]] == ["500-75-2mm"] * 6

    parsed_600 = parse_tray_load_description("单侧2层600")
    assert [layer["tray_section_file"] for layer in parsed_600["layers"]] == ["600-75-2mm"] * 2


def test_tray_load_parser_splits_mixed_500_and_600_slots_without_width_bleed() -> None:
    parsed = parse_tray_load_description("单侧，2层中低压500 1层控制600")

    assert [
        (layer["tray_width_mm"], layer["cable_type"], layer["tray_section_file"])
        for layer in parsed["layers"]
    ] == [
        (500, "medium_low_voltage", "500-75-2mm"),
        (500, "medium_low_voltage", "500-75-2mm"),
        (600, "control_measurement", "600-75-2mm"),
    ]
