from __future__ import annotations

import json
from pathlib import Path

from core.results.figure_collector import collect_figures


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04\x00\x01"
    b"\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _png(path: Path) -> None:
    path.write_bytes(PNG_1X1)


def test_appendix_b_collects_main_type1_stress_figures_not_square_audit_figures(tmp_path: Path) -> None:
    for name in ("SHITI.PNG", "TBMODEL.PNG", "B1SDIR1.PNG", "D1SDIR1.PNG", "SQ-B1SDIR1.PNG"):
        _png(tmp_path / name)

    manifest = collect_figures(tmp_path)

    by_name = {Path(item["target_file"]).name.upper(): item for item in manifest}
    assert "B1SDIR1.PNG" in by_name
    assert "D1SDIR1.PNG" in by_name
    assert "SQ-B1SDIR1.PNG" not in by_name
    assert by_name["B1SDIR1.PNG"]["appendix"] == "B"
    assert by_name["B1SDIR1.PNG"]["component_scope"] == "mixed_beam_type_1"


def test_required_figures_do_not_allow_sq_to_substitute_main_stress_figure(tmp_path: Path) -> None:
    _png(tmp_path / "SQ-B1SDIR1.PNG")
    (tmp_path / "result_requirements.json").write_text(
        json.dumps({"required_figures": ["B1SDIR1.PNG"]}),
        encoding="utf-8",
    )

    manifest = collect_figures(tmp_path)

    assert manifest == []
