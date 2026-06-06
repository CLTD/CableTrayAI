from __future__ import annotations

from pathlib import Path


def test_jczh_fallback_handles_nonzero_dw_fz_with_zero_moments() -> None:
    template = Path("templates/apdl/post_extract_s2.mac.j2").read_text(encoding="utf-8")

    assert "_CTAI_DW_FZ=ABS(FMS03(1,3))" in template
    assert "_CTAI_DW_OTHER=0" in template
    assert "_CTAI_USE_YUESHU_FALLBACK=1" in template
    assert "*IF,_CTAI_USE_YUESHU_FALLBACK,EQ,1,THEN" in template
    assert "CMSEL,S,YUESHU,NODE" in template

