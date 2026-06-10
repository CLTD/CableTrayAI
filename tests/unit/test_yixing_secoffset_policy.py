from __future__ import annotations

from core.apdl.section_offsets import normalize_yixing_arm_secoffset


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
