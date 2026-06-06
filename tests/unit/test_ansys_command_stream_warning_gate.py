from __future__ import annotations

from pathlib import Path

from core.ansys.runner import _detect_ansys_fatal_outputs


def test_optional_selection_warning_does_not_block_real_run(tmp_path: Path) -> None:
    (tmp_path / "CableTrayAI_Run0.err").write_text(
        "\n".join(
            [
                " *** WARNING ***                         CP =      70.266   TIME= 12:14:16",
                " Entity 53 is undefined.  The ESEL command is ignored.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    detection = _detect_ansys_fatal_outputs(tmp_path)

    assert detection["status"] == "pass"
    assert detection["evidence"] == []
    assert detection["warnings"]
    assert detection["warnings"][0]["category"] == "command_stream_error"


def test_parallel_mpi_cwd_warning_does_not_block_real_run(tmp_path: Path) -> None:
    (tmp_path / "CableTrayAI_Run1.err").write_text(
        "\n".join(
            [
                " The working directory specified (D:\\CableTrayAI\\jobs\\row_6) is not a directory on machine",
                " duxyb.  The /CWD command is ignored on MPI process with rank 1.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    detection = _detect_ansys_fatal_outputs(tmp_path)

    assert detection["status"] == "pass"
    assert detection["evidence"] == []
    assert detection["warnings"]


def test_mapdl_error_context_still_blocks_real_run(tmp_path: Path) -> None:
    (tmp_path / "ansys.out").write_text(
        "\n".join(
            [
                " *** ERROR ***",
                " ESEL command failed because of an invalid argument.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    detection = _detect_ansys_fatal_outputs(tmp_path)

    assert detection["status"] == "failed"
    assert detection["evidence"]


def test_unclassified_command_warning_still_blocks_real_run(tmp_path: Path) -> None:
    (tmp_path / "ansys.out").write_text(
        "\n".join(
            [
                " *** WARNING ***                         CP =      10.000   TIME= 12:14:16",
                " The command is ignored because the command stream state is invalid.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    detection = _detect_ansys_fatal_outputs(tmp_path)

    assert detection["status"] == "failed"
    assert detection["evidence"]
