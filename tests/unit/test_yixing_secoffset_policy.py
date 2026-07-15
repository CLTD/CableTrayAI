from __future__ import annotations

from core.apdl.section_offsets import normalize_secondary_arm_secoffset, normalize_yixing_arm_secoffset


def test_yixing_secondary_arm_drops_channel_only_offset() -> None:
    text = "\n".join(
        [
            "SECOFFSET,user,,-0.03249",
            "SECREAD,'YIXINGGANG150DAN','SECT',,MESH",
        ]
    )

    updated, count = normalize_yixing_arm_secoffset(text)

    assert count == 1
    assert updated == "SECOFFSET,user\nSECREAD,'YIXINGGANG150DAN','SECT',,MESH"


def test_channel_secondary_arm_keeps_channel_only_offset() -> None:
    text = "\n".join(
        [
            "SECOFFSET,user,,-0.03249",
            "SECREAD,'CAOGANG42DAN','SECT',,MESH",
        ]
    )

    updated, count = normalize_yixing_arm_secoffset(text)

    assert count == 0
    assert updated == text


def test_channel_secondary_arm_restores_channel_offset_after_section_swap() -> None:
    text = "\n".join(
        [
            "SECOFFSET,user",
            "SECREAD,'CAOGANG42DAN','SECT',,MESH",
        ]
    )

    updated, audit = normalize_secondary_arm_secoffset(text)

    assert audit["channel_replacements"] == 1
    assert audit["yixing_replacements"] == 0
    assert updated == "SECOFFSET,user,,-0.03249\nSECREAD,'CAOGANG42DAN','SECT',,MESH"


def test_yixing_secondary_arm_uses_plain_user_offset_after_section_swap() -> None:
    text = "\n".join(
        [
            "SECOFFSET,user,,-0.03249",
            "SECREAD,'YIXINGGANG150DAN','SECT',,MESH",
        ]
    )

    updated, audit = normalize_secondary_arm_secoffset(text)

    assert audit["channel_replacements"] == 0
    assert audit["yixing_replacements"] == 1
    assert updated == "SECOFFSET,user\nSECREAD,'YIXINGGANG150DAN','SECT',,MESH"
