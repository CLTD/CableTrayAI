from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


KNOWN_WIDTHS = (600, 500, 300, 200, 100, 50)
LOAD_KG_PER_M = {
    (600, "medium_low_voltage"): 117.5,
    (600, "control_measurement"): 90.0,
    (600, "all"): 117.5,
    (500, "medium_low_voltage"): 90.5,
    (500, "control_measurement"): 90.5,
    (500, "all"): 90.5,
    (300, "all"): 53.0,
    (200, "all"): 35.0,
    (100, "all"): 15.0,
    (50, "all"): 7.5,
}
TRAY_AREA_M2 = {
    600: 0.001796,
    500: 0.001596,
    300: 53.0 / 44315.0,
    200: 35.0 / 51095.0,
    100: 15.0 / 3896.1,
    50: 0.000400,
}
TRAY_ARM_LENGTHS_M = {
    600: (0.47, 0.20),
    500: (0.35, 0.20),
    300: (0.20, 0.15),
    200: (0.20, 0.15),
    100: (0.20, 0.15),
    50: (0.20, 0.15),
}
TRAY_SECTION_FILE = {
    600: "600-75-2mm",
    500: "500-75-2mm",
    300: "300-75-2mm",
    200: "200-75-2mm",
    100: "100-75-2mm",
    50: "100-75-2mm",
}


@dataclass(frozen=True)
class ParsedTrayLayer:
    side: str
    layer_index: int
    tray_width_mm: int
    cable_type: str
    load_kg_per_m: float
    arm_a_length_m: float
    arm_b_length_m: float
    tray_density_kg_m3: float
    tray_section_file: str


def _normalise(text: str) -> str:
    table = str.maketrans({"，": ",", "（": "(", "）": ")", "：": ":"})
    return re.sub(r"\s+", " ", str(text or "").strip().translate(table))


def _split_tray_slots(text: str) -> list[str]:
    normalised = _normalise(text)
    slots = [slot.strip() for slot in re.split(r"\s*(?:\+|,|、|;|；)\s*", normalised) if slot.strip()]
    if len(slots) > 1:
        return slots
    width_hits = re.findall(rf"(?<!\d)({'|'.join(str(width) for width in KNOWN_WIDTHS)})(?!\d)", normalised)
    if len(width_hits) <= 1:
        return slots
    marked = re.sub(
        rf"\s+(?=(?:\d+|一|二|两|三|四|五)?\s*层?\s*(?:中低压|低压|控制|测量|全部)?\s*(?:{'|'.join(str(width) for width in KNOWN_WIDTHS)})(?:\s*mm|\s*毫米)?)",
        "+",
        normalised,
    )
    return [slot.strip() for slot in marked.split("+") if slot.strip()]


def _side_count(word: str) -> int:
    if word in {"单侧"}:
        return 1
    if word in {"双侧", "两侧", "双", "两"}:
        return 2
    if word in {"三侧", "三"}:
        return 3
    raise ValueError(f"unsupported side word: {word}")


def _parse_header(raw: str) -> tuple[int, list[int], str]:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("empty tray load description")
    if not re.match(r"^\s*(单侧|双侧|两侧|三侧|双|两|三)", text):
        return 1, [1], text

    match_each = re.match(r"^\s*(?P<side>单侧|双侧|两侧|三侧)\s*各\s*(?P<n>\d+)\s*层\s*", text)
    if match_each:
        n_sides = _side_count(match_each.group("side"))
        return n_sides, [int(match_each.group("n"))] * n_sides, text[match_each.end() :].lstrip(" ，,;；:：")

    match_counts = re.match(
        r"^\s*(?P<side>单侧|双侧|两侧|三侧|双|两|三)\s*"
        r"(?P<counts>\d+\s*层?(?:\s*\+\s*\d+\s*层?){0,2})\s*",
        text,
    )
    if match_counts:
        n_sides = _side_count(match_counts.group("side"))
        counts = [int(item) for item in re.findall(r"\d+", match_counts.group("counts"))]
        if len(counts) == 1 and n_sides > 1:
            counts = counts * n_sides
        rest = text[match_counts.end() :].lstrip(" ，,;；:：")
        return n_sides, counts, rest

    match = re.match(
        r"^\s*(?P<side>单侧|双侧|两侧|三侧|双|两|三)\s*"
        r"(?:[:：])?\s*"
        r"(?:(?P<counts>\d+(?:\s*\+\s*\d+){1,2})\s*层?|(?P<single>\d+)\s*层\s*(?P<trailing>\d+(?:\s*\+\s*\d+){1,2})?)?"
        r"\s*(?:[:：])?\s*",
        text,
    )
    if not match:
        raise ValueError(f"cannot parse tray load header: {text[:40]}")
    n_sides = _side_count(match.group("side"))
    count_text = match.group("trailing") or match.group("counts")
    if count_text:
        counts = [int(item) for item in count_text.replace(" ", "").split("+")]
    elif match.group("single"):
        counts = [int(match.group("single"))] * n_sides
    else:
        counts = []
    rest = text[match.end() :].lstrip(" ，,;；:：")
    return n_sides, counts, rest


def _side_names(n_sides: int) -> list[str]:
    if n_sides == 1:
        return ["front"]
    if n_sides == 2:
        return ["front", "back"]
    if n_sides == 3:
        return ["front", "back", "third"]
    raise ValueError(f"unsupported side count: {n_sides}")


def _width(slot: str) -> int:
    for width in KNOWN_WIDTHS:
        if re.search(rf"(?<!\d){width}(?!\d)", slot):
            return width
    raise ValueError(f"cannot parse tray width from: {slot}")


def _cable_type(slot: str, width_mm: int) -> str:
    if "中低压" in slot or "低压" in slot:
        return "medium_low_voltage"
    if "控制" in slot or "测量" in slot:
        return "control_measurement"
    if "全部" in slot:
        return "all"
    return "medium_low_voltage" if width_mm in {500, 600} else "all"


def _load(width_mm: int, cable_type: str) -> float:
    return LOAD_KG_PER_M.get((width_mm, cable_type)) or LOAD_KG_PER_M[(width_mm, "all")]


def _count_and_slot(slot: str) -> tuple[int, str]:
    text = _normalise(slot)
    text = re.sub(r"^(?:一侧|另一侧|左侧|右侧|每侧|各侧)\s*", "", text)
    match = re.match(r"^(?P<count>\d+|一|二|两|三|四|五)\s*层\s*(?P<rest>.*)$", text)
    if not match:
        return 1, text
    word = match.group("count")
    numbers = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5}
    return numbers.get(word, int(word) if word.isdigit() else 1), match.group("rest").strip()


def _is_count_only_line(line: str) -> bool:
    return bool(re.match(r"^\s*\d+(?:\s*\+\s*\d+){0,3}\s*$", line))


def _append_slot_layers(parsed: list[ParsedTrayLayer], *, side: str, start_index: int, slot: str) -> int:
    count, slot_text = _count_and_slot(slot)
    if not slot_text or slot_text == "0":
        return start_index
    width = _width(slot_text)
    cable_type = _cable_type(slot_text, width)
    load = _load(width, cable_type)
    arm_a, arm_b = TRAY_ARM_LENGTHS_M[width]
    area = TRAY_AREA_M2[width]
    next_index = start_index
    for _ in range(count):
        next_index += 1
        parsed.append(
            ParsedTrayLayer(
                side=side,
                layer_index=next_index,
                tray_width_mm=width,
                cable_type=cable_type,
                load_kg_per_m=load,
                arm_a_length_m=arm_a,
                arm_b_length_m=arm_b,
                tray_density_kg_m3=load / area,
                tray_section_file=TRAY_SECTION_FILE[width],
            )
        )
    return next_index


def _has_width_token(slot: str) -> bool:
    return any(re.search(rf"(?<!\d){width}(?!\d)", str(slot or "")) for width in KNOWN_WIDTHS)


def _is_header_width_summary(line: str) -> bool:
    text = _normalise(line).lstrip("，,;； ")
    if not text or not _has_width_token(text):
        return False
    if "+" in text or re.search(r"\d+\s*层", text):
        return False
    return not any(token in text for token in ("中低压", "低压", "控制", "测量", "全部"))


def _declared_counts_by_side(n_sides: int, declared_counts: list[int]) -> list[int]:
    if not declared_counts:
        return []
    if n_sides == 1:
        return [int(declared_counts[0])]
    if len(declared_counts) >= n_sides:
        return [int(item) for item in declared_counts[:n_sides]]
    if len(declared_counts) == 1:
        return [int(declared_counts[0])] * n_sides
    return [int(item) for item in declared_counts] + [0] * (n_sides - len(declared_counts))


def _parse_compact_declared_width_layers(
    *,
    lines: list[str],
    n_sides: int,
    declared_counts: list[int],
    sides: list[str],
) -> dict[str, Any] | None:
    if len(lines) != 1 or not declared_counts:
        return None
    slot = _normalise(lines[0]).lstrip("，,;； ")
    if not slot or len(_split_tray_slots(slot)) != 1 or not _has_width_token(slot):
        return None
    counts_by_side = _declared_counts_by_side(n_sides, declared_counts)
    if not counts_by_side:
        return None
    parsed: list[ParsedTrayLayer] = []
    side_layer_indices = {side: 0 for side in sides}
    for side_index, count in enumerate(counts_by_side):
        side = sides[min(side_index, len(sides) - 1)]
        for _ in range(max(int(count), 0)):
            side_layer_indices[side] = _append_slot_layers(
                parsed,
                side=side,
                start_index=side_layer_indices[side],
                slot=slot,
            )
    if not parsed:
        return None
    return {
        "status": "pass",
        "side_count": n_sides,
        "front_layers": max((item.layer_index for item in parsed if item.side == "front"), default=0),
        "back_layers": max((item.layer_index for item in parsed if item.side == "back"), default=0),
        "third_layers": max((item.layer_index for item in parsed if item.side == "third"), default=0),
        "layers": [item.__dict__ for item in parsed],
        "declared_layers": declared_counts,
        "source_policy": "Deterministic parser expanded compact declared layer counts such as 单侧4层500 or 双侧3+4层600; no LLM guessing.",
    }


def parse_tray_load_description(raw_text: Any) -> dict[str, Any]:
    n_sides, declared_counts, rest = _parse_header(str(raw_text or ""))
    lines = [line.strip() for line in str(rest).splitlines() if line.strip() and not _is_count_only_line(line)]
    if declared_counts and len(lines) > 1 and _is_header_width_summary(lines[0]):
        lines = lines[1:]
    if not lines and rest.strip():
        lines = [rest.strip()]
    if not lines:
        raise ValueError("tray load description has no layer rows")
    sides = _side_names(n_sides)
    parsed: list[ParsedTrayLayer] = []

    compact = _parse_compact_declared_width_layers(
        lines=lines,
        n_sides=n_sides,
        declared_counts=declared_counts,
        sides=sides,
    )
    if compact:
        return compact

    native_side_descriptor_lines: list[tuple[str, str]] = []
    native_side_patterns = [
        ("front", r"^\s*(?:前侧|左侧)\s*\d*\s*[:：、]?\s*(?P<rest>.*)$"),
        ("back", r"^\s*(?:后侧|右侧|另一侧)\s*\d*\s*[:：、]?\s*(?P<rest>.*)$"),
        ("third", r"^\s*(?:第三侧|中间侧)\s*\d*\s*[:：、]?\s*(?P<rest>.*)$"),
    ]
    for line in lines:
        normalised = _normalise(line)
        for side, pattern in native_side_patterns:
            match = re.match(pattern, normalised)
            if match and match.group("rest").strip():
                native_side_descriptor_lines.append((side, match.group("rest").strip()))
                break
    if native_side_descriptor_lines:
        side_layer_indices = {side: 0 for side in sides}
        for side, cleaned in native_side_descriptor_lines:
            if side not in side_layer_indices:
                continue
            for slot in _split_tray_slots(cleaned):
                side_layer_indices[side] = _append_slot_layers(
                    parsed,
                    side=side,
                    start_index=side_layer_indices[side],
                    slot=slot,
                )
        if not parsed:
            raise ValueError("tray load native side descriptors did not produce any tray layer")
        return {
            "status": "pass",
            "side_count": n_sides,
            "front_layers": max((item.layer_index for item in parsed if item.side == "front"), default=0),
            "back_layers": max((item.layer_index for item in parsed if item.side == "back"), default=0),
            "third_layers": max((item.layer_index for item in parsed if item.side == "third"), default=0),
            "layers": [item.__dict__ for item in parsed],
            "declared_layers": declared_counts,
            "source_policy": "Deterministic parser based on native Chinese side-descriptor intake tray-load text; no LLM guessing.",
        }

    side_descriptor_lines = [
        line for line in lines if re.match(r"^\s*(?:一侧|另一侧|左侧|右侧|每侧|各侧)\s*", _normalise(line))
    ]
    if side_descriptor_lines:
        side_layer_indices = {side: 0 for side in sides}
        for descriptor_index, line in enumerate(side_descriptor_lines):
            side = sides[min(descriptor_index, len(sides) - 1)]
            cleaned = re.sub(r"^\s*(?:一侧|另一侧|左侧|右侧|每侧|各侧)\s*", "", _normalise(line))
            slots = _split_tray_slots(cleaned)
            for slot in slots:
                side_layer_indices[side] = _append_slot_layers(
                    parsed,
                    side=side,
                    start_index=side_layer_indices[side],
                    slot=slot,
                )
        if not parsed:
            raise ValueError("tray load side descriptors did not produce any tray layer")
        front_layers = max((item.layer_index for item in parsed if item.side == "front"), default=0)
        back_layers = max((item.layer_index for item in parsed if item.side == "back"), default=0)
        third_layers = max((item.layer_index for item in parsed if item.side == "third"), default=0)
        return {
            "status": "pass",
            "side_count": n_sides,
            "front_layers": front_layers,
            "back_layers": back_layers,
            "third_layers": third_layers,
            "layers": [item.__dict__ for item in parsed],
            "declared_layers": declared_counts,
            "source_policy": "Deterministic parser based on side-descriptor intake tray-load text; no LLM guessing.",
        }

    side_layer_indices = {side: 0 for side in sides}
    for line in lines:
        slots = _split_tray_slots(line)
        if n_sides == 1:
            for slot in slots:
                slot_text = _normalise(slot)
                if not slot_text or slot_text == "0":
                    continue
                side_layer_indices[sides[0]] = _append_slot_layers(
                    parsed,
                    side=sides[0],
                    start_index=side_layer_indices[sides[0]],
                    slot=slot_text,
                )
            continue
        if len(slots) < n_sides:
            slots.extend(["0"] * (n_sides - len(slots)))
        if len(slots) > n_sides:
            slots = slots[: n_sides - 1] + ["+".join(slots[n_sides - 1 :])]
        for side_index, slot in enumerate(slots):
            for slot_text in _split_tray_slots(slot):
                slot_text = _normalise(slot_text)
                if not slot_text or slot_text == "0":
                    continue
                side_layer_indices[sides[side_index]] = _append_slot_layers(
                    parsed,
                    side=sides[side_index],
                    start_index=side_layer_indices[sides[side_index]],
                    slot=slot_text,
                )
    if not parsed:
        raise ValueError("tray load description did not produce any tray layer")
    front_layers = max((item.layer_index for item in parsed if item.side == "front"), default=declared_counts[0] if declared_counts else 0)
    back_layers = max((item.layer_index for item in parsed if item.side == "back"), default=declared_counts[1] if len(declared_counts) > 1 else 0)
    third_layers = max((item.layer_index for item in parsed if item.side == "third"), default=declared_counts[2] if len(declared_counts) > 2 else 0)
    return {
        "status": "pass",
        "side_count": n_sides,
        "front_layers": front_layers,
        "back_layers": back_layers,
        "third_layers": third_layers,
        "layers": [item.__dict__ for item in parsed],
        "declared_layers": declared_counts,
        "source_policy": "Deterministic parser based on intake tray-load text; no LLM guessing.",
    }
