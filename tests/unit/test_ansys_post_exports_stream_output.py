from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_post_export_subprocesses_stream_ansys_output_to_logs() -> None:
    for rel_path in (
        "core/ansys/figure_export.py",
        "core/ansys/connection_export.py",
    ):
        source = (ROOT / rel_path).read_text(encoding="utf-8")
        assert "capture_output=True" not in source
        assert "stdout=stdout_handle" in source
        assert "stderr=stderr_handle" in source
