import json
from pathlib import Path

from core.ansys.config import AnsysExecutableConfig, AnsysLocalConfig
from core.ansys import connection_export
from core.ansys import figure_export
from core.ansys import runner as ansys_runner


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


def test_figure_export_macro_exits_without_saving_database(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    for name in ("generated_post.mac", "CableTrayAI_Run.db", "CableTrayAI_Run.rst"):
        (job_dir / name).write_text("FINISH\n", encoding="utf-8")

    figure_export.build_figure_export_macro(job_dir)
    macro_text = (job_dir / "export_figures.mac").read_text(encoding="utf-8")

    assert "/EXIT,NOSAV" in macro_text


def test_connection_node_export_macro_exits_without_saving_database(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "CableTrayAI_Run.db").write_text("placeholder", encoding="utf-8")
    (job_dir / "generated_model.mac").write_text("K,500,0,0,0\n", encoding="utf-8")

    audit = connection_export.write_connection_node_export_macro(job_dir)
    macro_text = (job_dir / "export_connection_nodes.mac").read_text(encoding="utf-8")

    assert audit["status"] == "macro_written"
    assert "/EXIT,NOSAV" in macro_text


def test_connection_node_export_accepts_completion_marker_with_nonzero_launcher_return(
    tmp_path: Path, monkeypatch
) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    exe = tmp_path / "ANSYS182.exe"
    exe.write_text("placeholder", encoding="utf-8")
    (job_dir / "CableTrayAI_Run.db").write_text("placeholder", encoding="utf-8")
    (job_dir / "generated_model.mac").write_text("K,500,0,0,0\n", encoding="utf-8")
    (job_dir / "LS-FORCE-NODES.LIS").write_text("stale output must be removed\n", encoding="utf-8")
    (job_dir / "connection_node_export.out").write_text("stale completion marker must be removed\n", encoding="utf-8")

    class FakeProcess:
        pid = 12345
        returncode = 1

        def poll(self):
            return self.returncode

    def fake_popen(*args, **kwargs):
        (job_dir / "LS-FORCE-NODES.LIS").write_text(
            "KP CASEID FX FY FZ MX MY MZ\n500 2 1 2 3 4 5 6\n",
            encoding="utf-8",
        )
        (job_dir / "connection_node_export.out").write_text(
            "\n".join(
                [
                    "***** ROUTINE COMPLETED *****",
                    "NUMBER OF WARNING MESSAGES ENCOUNTERED=        141",
                    "NUMBER OF ERROR   MESSAGES ENCOUNTERED=          0",
                ]
            ),
            encoding="utf-8",
        )
        return FakeProcess()

    monkeypatch.setattr(connection_export.subprocess, "Popen", fake_popen)

    audit = connection_export.run_connection_node_export(
        job_dir,
        config=AnsysLocalConfig(ansys=AnsysExecutableConfig(executable=str(exe), timeout_minutes=1)),
    )

    assert audit["status"] == "success"
    assert audit["returncode"] == 1
    assert audit["returncode_accepted_by_completion_marker"] is True
    assert audit["completion_marker_detection"]["status"] == "pass"
    assert audit["stale_connection_output_cleanup"]["removed_count"] == 2


def test_figure_export_accepts_completion_marker_with_nonzero_launcher_return(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    exe = tmp_path / "ANSYS182.exe"
    exe.write_text("placeholder", encoding="utf-8")
    for name in ("generated_post.mac", "CableTrayAI_Run.db", "CableTrayAI_Run.rst"):
        (job_dir / name).write_text("FINISH\n", encoding="utf-8")
    (job_dir / "result_requirements.json").write_text(json.dumps({"required_figures": ["SHITI.PNG"]}), encoding="utf-8")
    (job_dir / "export_figures.out").write_text(
        "\n".join(
            [
                "***** ROUTINE COMPLETED *****",
                "***** END OF INPUT ENCOUNTERED *****",
                "NUMBER OF WARNING MESSAGES ENCOUNTERED=          7",
                "NUMBER OF ERROR   MESSAGES ENCOUNTERED=          0",
            ]
        ),
        encoding="utf-8",
    )

    class FakeProcess:
        pid = 12345
        returncode = 4294967295

        def poll(self):
            return self.returncode

    def fake_popen(*args, **kwargs):
        return FakeProcess()

    monkeypatch.setattr(
        figure_export,
        "classify_job_requirements",
        lambda _job_dir: {"requires": {}, "required_figures": ["SHITI.PNG"]},
    )
    monkeypatch.setattr(figure_export.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        figure_export,
        "_normalise_named_pngs",
        lambda *args, **kwargs: {"recorded_names": 1, "generic_pngs": 1, "copied_named_pngs": 1},
    )
    monkeypatch.setattr(
        figure_export,
        "collect_figures",
        lambda *args, **kwargs: [{"source_file": "SHITI.PNG", "target_file": "SHITI.PNG"}],
    )

    audit = figure_export.run_figure_export(
        job_dir,
        config=AnsysLocalConfig(ansys=AnsysExecutableConfig(executable=str(exe), timeout_minutes=1)),
        timeout_minutes=1,
    )

    assert audit["status"] == "success"
    assert audit["returncode"] == 4294967295
    assert audit["returncode_accepted_by_completion_marker"] is True
    assert audit["completion_marker_detection"]["status"] == "pass"


def test_figure_export_license_busy_is_retried(tmp_path: Path, monkeypatch) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    calls: list[int] = []

    def fake_run_figure_export(job_dir_arg, config, **kwargs):
        calls.append(len(calls) + 1)
        if len(calls) == 1:
            (job_dir / "export_figures.out").write_text(
                "\n".join(
                    [
                        "ANSYS LICENSE MANAGER ERROR:",
                        "ANSYSLI exited or could not read server port ANSYSLI_DEMO_PORT.",
                        "*** ERROR - ANSYS license not available.",
                    ]
                ),
                encoding="utf-8",
            )
            return {
                "status": "failed",
                "mode": "figure_export",
                "returncode": 7,
                "figure_count": 0,
                "missing_required_figures": ["SHITI.PNG"],
            }
        (job_dir / "export_figures.out").write_text(
            "\n".join(
                [
                    "***** ROUTINE COMPLETED *****",
                    "NUMBER OF ERROR   MESSAGES ENCOUNTERED=          0",
                ]
            ),
            encoding="utf-8",
        )
        return {
            "status": "success",
            "mode": "figure_export",
            "returncode": 0,
            "figure_count": 1,
            "missing_required_figures": [],
        }

    monkeypatch.setattr(ansys_runner, "run_figure_export", fake_run_figure_export)
    monkeypatch.setattr(ansys_runner, "FIGURE_EXPORT_LICENSE_RETRY_DELAYS_SECONDS", (0,))

    audit = ansys_runner._run_figure_export_with_license_retries(
        job_dir,
        AnsysLocalConfig(),
        timeout_minutes=1,
    )

    assert calls == [1, 2]
    assert audit["status"] == "success"
    assert audit["license_retry_attempts"][0]["license_unavailable"] is True
    assert audit["license_retry_attempts"][1]["status"] == "success"
