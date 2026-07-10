from pathlib import Path


INDEX = Path("apps/web/index.html")


def test_command_panel_fills_its_grid_track() -> None:
    text = INDEX.read_text(encoding="utf-8")

    assert ".command-panel > #commandText" in text
    assert "max-height: none;" in text
    assert "--review-panel-height:" in text


def test_model_preview_uses_component_registries_and_honest_geometry_terms() -> None:
    text = INDEX.read_text(encoding="utf-8")

    assert "LS_(SUP|ARM|TRAY|BOLT)" in text
    assert 'TRAY: "tray_rail"' in text
    assert 'BOLT: "bolt_rod"' in text
    assert "关键点 /" in text
    assert "几何线" in text
    assert "不是 ANSYS 实际节点/单元" in text


def test_unapproved_public_price_is_not_presented_as_nuclear_cost() -> None:
    text = INDEX.read_text(encoding="utf-8")

    assert "118.38" not in text
    assert "单位核定方钢材料参考" in text
    assert 'item.pricing_status === "approved_active"' in text
    assert "不代表核电工程综合造价" in text
