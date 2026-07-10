from pathlib import Path

from core.pipeline.one_click import AUTO_SUPPORT_GEOMETRY_RECOVERY_ENABLED


def test_production_pipeline_keeps_support_geometry_fixed() -> None:
    source = Path("core/pipeline/one_click.py").read_text(encoding="utf-8")

    assert AUTO_SUPPORT_GEOMETRY_RECOVERY_ENABLED is False
    assert "from core.optimizer.support_spacing_recovery import" not in source
    assert "apply_support_spacing_recovery(" not in source
    assert "plan_support_spacing_recovery_from_selection(" not in source
    assert "plan_support_spacing_recovery_from_final_ratio(" not in source
    assert "revise_confirmed_tray_line_load_and_rerun" in source
