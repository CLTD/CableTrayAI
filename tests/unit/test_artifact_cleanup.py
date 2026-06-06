from __future__ import annotations

from pathlib import Path

from core.ansys.artifact_cleanup import cleanup_heavy_solver_artifacts


def test_cleanup_removes_ansys_l_step_cache_but_keeps_lis_and_logs(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "Normal.l80").write_bytes(b"cache")
    (job_dir / "CableTrayAI_Run.db").write_bytes(b"db")
    (job_dir / "SQUAREBEAMSTRESS.LIS").write_text("lis", encoding="utf-8")
    (job_dir / "ansys_stdout.log").write_text("log", encoding="utf-8")

    audit = cleanup_heavy_solver_artifacts(job_dir)

    assert audit["status"] == "pass"
    assert not (job_dir / "Normal.l80").exists()
    assert not (job_dir / "CableTrayAI_Run.db").exists()
    assert (job_dir / "SQUAREBEAMSTRESS.LIS").exists()
    assert (job_dir / "ansys_stdout.log").exists()
