from __future__ import annotations

import json
from pathlib import Path

from core.ansys.figure_export import build_figure_export_macro
from core.apdl.audit import audit_rendered_apdl
from core.apdl.modal_policy import record_modal_mode_count_learning
from core.intake.job_input_builder import _intake_modal_mode_count
from core.validation.analysis_scope import classify_scope_from_input


def _static_payload() -> dict:
    return {
        "metadata": {"analysis_method": "static"},
        "support": {
            "support_type": "S2",
            "layers_front": 4,
            "layers_back": 2,
            "square_tube_width_m": 0.14,
            "support_height_m": 2.0,
            "support_spacing_m": 2.0,
        },
        "project": {"elevation": 8.5},
        "tray_layers": [
            {"side": "front", "layer_index": 1, "tray_width_m": 0.5},
            {"side": "back", "layer_index": 1, "tray_width_m": 0.5},
        ],
    }


def test_static_scope_does_not_require_modal_analysis() -> None:
    scope = classify_scope_from_input(_static_payload())

    assert scope["analysis_method"] == "static"
    assert scope["requires"]["modal_analysis"] is False
    assert scope["requires"]["modal_figures"] is True
    assert scope["requires"]["modal_frequency_table"] is True
    assert any(str(name).upper().startswith("MOTAI") for name in scope["required_figures"])


def test_static_intake_does_not_assign_modal_mode_count() -> None:
    modal_count, source = _intake_modal_mode_count({"analysis_method": "static"}, None, _static_payload())

    assert modal_count is None
    assert source == "static_method_not_required"


def test_static_figure_export_macro_keeps_modal_images_without_main_mt(tmp_path: Path) -> None:
    job_dir = tmp_path / "static-job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(json.dumps(_static_payload(), ensure_ascii=False), encoding="utf-8")
    (job_dir / "generated_post.mac").write_text("FINISH\n", encoding="utf-8")

    audit = build_figure_export_macro(job_dir)
    macro_text = (job_dir / "export_figures.mac").read_text(encoding="utf-8")

    assert "MOTAI-1" in macro_text
    assert "MODOPT,LANB,4" in macro_text
    assert "/OUTPUT,'Mode','oup'," in macro_text
    assert audit["modal_mode_policy"]["status"] == "figure_only"
    assert audit["modal_mode_policy"]["modal_figure_mode_count"] == 4
    assert audit["modal_mode_policy"]["writes_frequency_table"] is True


def test_static_jobs_do_not_write_modal_learning_entries(tmp_path: Path) -> None:
    job_dir = tmp_path / "static-job"
    job_dir.mkdir()
    (job_dir / "input.json").write_text(json.dumps(_static_payload(), ensure_ascii=False), encoding="utf-8")

    result = record_modal_mode_count_learning(job_dir, cache_path=tmp_path / "modal_cache.json")

    assert result["status"] == "not_required"
    assert result["reason"] == "static_method_has_no_modal_mt_learning"


def test_static_apdl_audit_does_not_require_main_modal_block(tmp_path: Path) -> None:
    model = tmp_path / "generated_model.mac"
    solve = tmp_path / "generated_solve.mac"
    post = tmp_path / "generated_post.mac"
    model.write_text("ET,1,188\nSECREAD,'100-100-8'\nMP,EX,1,2e11\nD,1,ALL\nCP,1,UX,1,2\nLATT,1\nLMESH,ALL\n", encoding="utf-8")
    solve.write_text("/SOL\nANTYPE,0\nACEL,1,2,3\nLSSOLVE,1,2\nFINISH\n", encoding="utf-8")
    post.write_text("/POST1\n/OUTPUT,MAXBEAMSTRESS,LIS\n*GET,A,ELEM,0,COUNT\n", encoding="utf-8")

    static_audit = audit_rendered_apdl([model, solve, post], require_modal_analysis=False)
    spectrum_audit = audit_rendered_apdl([model, solve, post], require_modal_analysis=True)

    assert static_audit["status"] == "pass"
    assert spectrum_audit["status"] == "fail"
    assert spectrum_audit["checks"]["has_modal_analysis"] is False
