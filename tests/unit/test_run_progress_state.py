from __future__ import annotations

from pathlib import Path


def test_live_ansys_callback_cannot_regress_visible_stage(tmp_path, monkeypatch) -> None:
    from apps.api.app import main

    monkeypatch.chdir(tmp_path)
    main.RUNS.clear()

    run_id = "run-progress-regression"
    main._set_run(run_id, status="running", stage="parsing_results", progress=90, active_job_id="job-1")
    run = main._set_run(
        run_id,
        status="running",
        stage="running_ansys",
        progress=98,
        message="late live callback",
        active_job_id="job-1",
    )

    assert run["stage"] == "parsing_results"
    assert run["progress"] == 90
    assert run["last_live_stage"] == "running_ansys"
    assert run["last_live_message"] == "late live callback"


def test_export_stages_are_not_final_completion() -> None:
    from core.pipeline.one_click import _clamp_progress

    assert _clamp_progress("running_ansys", 100) == 82
    assert _clamp_progress("exporting_connection_nodes", 100) == 86
    assert _clamp_progress("exporting_figures", 100) == 88
    assert _clamp_progress("ansys_post_exports_done", 100) == 90
    assert _clamp_progress("publish_outputs", 100) == 96
    assert _clamp_progress("completed", 100) == 100


def test_index_does_not_restore_old_latest_run_without_intake_session() -> None:
    text = Path("apps/web/index.html").read_text(encoding="utf-8")

    assert 'requestJson("/runs/latest"' not in text
    assert "const storedLatest = localStorage.getItem(LATEST_RUN_STORAGE_KEY)" not in text
    assert "if (!storedActive) {" in text
    assert "localStorage.removeItem(LATEST_RUN_STORAGE_KEY);" in text
    assert "return;" in text


def test_index_requires_restored_intake_and_spectrum_files() -> None:
    text = Path("apps/web/index.html").read_text(encoding="utf-8")

    assert 'const requiredIds = ["intakeFile", "spectrumFile"];' in text
    assert "missingRequired.length" in text
    assert "缺少已上传文件" in text
    assert 'body: JSON.stringify({ paths: [path] })' in text
