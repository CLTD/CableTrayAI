from __future__ import annotations

import re


_CHANNEL_SECONDARY_OFFSET_RE = re.compile(
    r"^(?P<indent>\s*)SECOFFSET\s*,\s*USER\s*,\s*,\s*-?0\.03249"
    r"(?P<trailing>\s*(?:!.*)?)$",
    re.IGNORECASE,
)
_SECREAD_RE = re.compile(r"^\s*SECREAD\s*,\s*['\"]?(?P<section>[^,'\"\s]+)", re.IGNORECASE)
_SECTION_BOUNDARY_RE = re.compile(r"^\s*(SECOFFSET|SECTYPE)\b", re.IGNORECASE)


def normalize_yixing_arm_secoffset(text: str) -> tuple[str, int]:
    """Drop the channel-specific secondary offset when the arm is YIXINGGANG.

    Reviewed channel sources use ``SECOFFSET,user,,-0.03249`` before
    ``CAOGANG42DAN``.  When the square-section branch swaps that secondary arm
    to ``YIXINGGANG*``, the offset must become the plain shaped-steel command
    ``SECOFFSET,user``.  The channel branch is deliberately left unchanged.
    """

    lines = text.splitlines(keepends=True)
    changed = 0
    for index, line in enumerate(lines):
        body = line.rstrip("\r\n")
        newline = line[len(body) :]
        offset_match = _CHANNEL_SECONDARY_OFFSET_RE.match(body)
        if not offset_match:
            continue
        section = _next_secread_section(lines, index + 1)
        if section is None or not section.upper().startswith("YIXINGGANG"):
            continue
        trailing = offset_match.group("trailing") or ""
        if "!" not in trailing:
            trailing = ""
        lines[index] = f"{offset_match.group('indent')}SECOFFSET,user{trailing}{newline}"
        changed += 1
    return "".join(lines), changed


def _next_secread_section(lines: list[str], start_index: int) -> str | None:
    for line in lines[start_index : start_index + 6]:
        body = line.strip()
        if not body or body.startswith("!"):
            continue
        secread_match = _SECREAD_RE.match(line)
        if secread_match:
            return secread_match.group("section").strip()
        if _SECTION_BOUNDARY_RE.match(line):
            return None
    return None
