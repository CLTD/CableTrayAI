from __future__ import annotations

from pathlib import Path


def test_jczh_fallback_handles_nonzero_dw_fz_with_zero_moments() -> None:
    template = Path("templates/apdl/post_extract_s2.mac.j2").read_text(encoding="utf-8")

    assert "_CTAI_DW_FZ=ABS(FMS03(1,3))" in template
    assert "_CTAI_DW_OTHER=0" in template
    assert "_CTAI_USE_YUESHU_FALLBACK=1" in template
    assert "*IF,_CTAI_USE_YUESHU_FALLBACK,EQ,1,THEN" in template
    assert "CMSEL,S,YUESHU,NODE" in template


def test_ls_force_template_uses_standard_suffix9_without_nearby_keypoint_fallback() -> None:
    template = Path("templates/apdl/post_extract_s2.mac.j2").read_text(encoding="utf-8")
    ls_block = template.split("!===========================================================提取螺栓载荷", 1)[0]
    ls_block = ls_block.rsplit("*DO,I,1,NODENUM,1", 1)[-1]

    assert "KSEL,S,,,KYALS%I%" in ls_block
    assert "KYSEL" not in ls_block
    assert "KYALS%I%-3" not in ls_block
    assert "KYALS%I%-101" not in ls_block
    assert "509+I*10" in template
    assert "1509+J*10" in template
