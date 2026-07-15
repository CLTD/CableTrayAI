from __future__ import annotations

from core.intake.tray_load_parser import parse_tray_load_description


def test_tray_load_parser_preserves_500_and_600_widths_from_intake_text() -> None:
    parsed_500 = parse_tray_load_description("双侧3+3层500")
    assert [layer["tray_section_file"] for layer in parsed_500["layers"]] == ["500-75-2mm"] * 6

    parsed_600 = parse_tray_load_description("单侧2层600")
    assert [layer["tray_section_file"] for layer in parsed_600["layers"]] == ["600-75-2mm"] * 2
    assert [(layer["arm_a_length_m"], layer["arm_b_length_m"]) for layer in parsed_600["layers"]] == [
        (0.47, 0.20),
        (0.47, 0.20),
    ]


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


def test_tray_load_parser_keeps_first_width_after_native_side_label() -> None:
    parsed = parse_tray_load_description(
        "\u53cc\u4fa72+2\u5c42\n"
        "\u524d\u4fa7300+600\n"
        "\u540e\u4fa7300+500"
    )

    assert parsed["side_count"] == 2
    assert [
        (layer["side"], layer["layer_index"], layer["tray_width_mm"])
        for layer in parsed["layers"]
    ] == [
        ("front", 1, 300),
        ("front", 2, 600),
        ("back", 1, 300),
        ("back", 2, 500),
    ]


def test_tray_load_parser_repeats_unlabeled_equal_side_layer_pattern() -> None:
    parsed = parse_tray_load_description(
        "\u53cc\u4fa73+3\u5c42 "
        "\u4e00\u5c42100 \u4e00\u5c42300 \u4e00\u5c42500"
    )

    assert parsed["front_layers"] == 3
    assert parsed["back_layers"] == 3
    assert [
        (layer["side"], layer["layer_index"], layer["tray_width_mm"])
        for layer in parsed["layers"]
    ] == [
        ("front", 1, 100),
        ("front", 2, 300),
        ("front", 3, 500),
        ("back", 1, 100),
        ("back", 2, 300),
        ("back", 3, 500),
    ]


def test_tray_load_parser_repeats_unlabeled_double_side_two_width_pattern() -> None:
    parsed = parse_tray_load_description(
        "\u53cc\u4fa72\u5c42 \u4e00\u5c42300 \u4e00\u5c42500"
    )

    assert parsed["front_layers"] == 2
    assert parsed["back_layers"] == 2
    assert [
        (layer["side"], layer["layer_index"], layer["tray_width_mm"])
        for layer in parsed["layers"]
    ] == [
        ("front", 1, 300),
        ("front", 2, 500),
        ("back", 1, 300),
        ("back", 2, 500),
    ]


def test_tray_load_parser_distributes_unlabeled_unequal_side_layer_sequence() -> None:
    parsed = parse_tray_load_description(
        "\u53cc\u4fa74+2\u5c42\n"
        "\u4e2d\u4f4e\u538b500\n"
        "\u4e2d\u4f4e\u538b600\n"
        "\u63a7\u5236\u6d4b\u91cf500+\u63a7\u5236\u6d4b\u91cf500\n"
        "\u63a7\u5236\u6d4b\u91cf500+\u63a7\u5236\u6d4b\u91cf500"
    )

    assert parsed["front_layers"] == 4
    assert parsed["back_layers"] == 2
    assert [
        (layer["side"], layer["layer_index"], layer["tray_width_mm"], layer["cable_type"])
        for layer in parsed["layers"]
    ] == [
        ("front", 1, 500, "medium_low_voltage"),
        ("front", 2, 600, "medium_low_voltage"),
        ("front", 3, 500, "control_measurement"),
        ("front", 4, 500, "control_measurement"),
        ("back", 1, 500, "control_measurement"),
        ("back", 2, 500, "control_measurement"),
    ]
