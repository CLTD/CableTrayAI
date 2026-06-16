from __future__ import annotations

from pathlib import Path

from core.results.output_workspace import write_command_stream_manifest


def test_command_stream_manifest_includes_spectrum_and_residual_mass_streams(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    for filename in (
        "generated_model.mac",
        "generated_solve.mac",
        "generated_post.mac",
        "ansys_spectrum_sl1.mac",
        "ansys_spectrum_sl2.mac",
        "ansys_spectrum_workbook_format.mac",
        "ansys_zpa_parameters.mac",
        "platform_standard_solve.mac",
        "platform_standard_post.mac",
        "platform_standard_post_numeric.mac",
    ):
        (job_dir / filename).write_text("! test\n", encoding="utf-8")

    manifest = write_command_stream_manifest(job_dir)

    roles = {item["role"]: item for item in manifest["streams"]}
    assert manifest["status"] == "pass"
    assert roles["modeling"]["required"] is True
    assert roles["calculation"]["required"] is True
    assert roles["result_extraction"]["required"] is True
    assert roles["spectrum_sl1_solve"]["exists"] is True
    assert roles["spectrum_sl2_solve"]["exists"] is True
    assert roles["spectrum_workbook_format_review"]["exists"] is True
    assert roles["residual_mass_static_correction"]["exists"] is True
    assert roles["platform_standard_calculation_shadow"]["exists"] is True
    assert roles["platform_standard_calculation_shadow"]["required"] is False
    assert roles["platform_standard_result_extraction_shadow"]["exists"] is True
    assert roles["platform_standard_numeric_extraction_shadow"]["exists"] is True
