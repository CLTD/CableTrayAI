from __future__ import annotations

from pathlib import Path

from core.ansys.command_builder import build_ansys_command
from core.ansys.config import AnsysLocalConfig
from core.ansys.master_macro import build_run_all_macro, validate_run_all_macro
from core.apdl.numeric_post import build_numeric_post_macro


def _write_minimal_job(job_dir: Path) -> None:
    job_dir.mkdir()
    (job_dir / "generated_model.mac").write_text("FINISH\n", encoding="utf-8")
    (job_dir / "generated_solve.mac").write_text("FINISH\n", encoding="utf-8")
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "/POST1",
                "ETABLE,SDIR,SMISC,31",
                "PLLS,SDIR",
                "/IMAGE,SAVE,A1SDIR,BMP",
                "*CFOPEN,MAXBEAMSTRESS,LIS",
                "*VWRITE,1",
                "(F10.3)",
                "*CFCLOS",
                "FINISH",
            ]
        ),
        encoding="utf-8",
    )


def test_numeric_post_comments_graphics_but_keeps_numeric_writes(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    _write_minimal_job(job_dir)

    audit = build_numeric_post_macro(job_dir)
    text = (job_dir / "generated_post_numeric.mac").read_text(encoding="utf-8")

    assert audit["status"] == "pass"
    assert audit["commented_graphics_commands"] == 2
    assert "! CableTrayAI numeric-post skipped graphics command: PLLS,SDIR" in text
    assert "! CableTrayAI numeric-post skipped graphics command: /IMAGE,SAVE,A1SDIR,BMP" in text
    assert "*CFOPEN,MAXBEAMSTRESS,LIS" in text
    assert "ETABLE,SDIR,SMISC,31" in text


def test_run_all_validation_accepts_internal_numeric_post_macro(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    _write_minimal_job(job_dir)
    build_numeric_post_macro(job_dir)

    audit = build_run_all_macro(job_dir, post_macro_name="generated_post_numeric.mac")
    validation = validate_run_all_macro(job_dir)
    run_all = (job_dir / "run_all.mac").read_text(encoding="utf-8")

    assert audit["status"] == "pass"
    assert audit["post_macro_role"] == "numeric_main_run"
    assert "/INPUT,generated_post_numeric,mac" in run_all
    assert validation["status"] == "pass"


def test_ansys_command_can_target_numeric_post_macro(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    _write_minimal_job(job_dir)
    build_numeric_post_macro(job_dir)
    config = AnsysLocalConfig()
    config.ansys.executable = "ANSYS.exe"

    command = build_ansys_command(config, job_dir, post_macro_name="generated_post_numeric.mac")

    assert command["post_macro_name"] == "generated_post_numeric.mac"
    assert command["master_macro_audit"]["post_macro_role"] == "numeric_main_run"
    assert (job_dir / "run_all.mac").read_text(encoding="utf-8").find("generated_post_numeric") >= 0
