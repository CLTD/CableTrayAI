import json
from pathlib import Path

from core.pipeline.one_click import _persist_spectrum_selection_features


def _write_input(job_dir: Path) -> None:
    job_dir.mkdir()
    (job_dir / "input.json").write_text(json.dumps({"metadata": {}}), encoding="utf-8")


def test_response_spectrum_features_capture_peak_and_workbook_identity(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    _write_input(job_dir)
    (job_dir / "spectrum_points.json").write_text(
        json.dumps(
            {
                "load_steps": [
                    {
                        "level": "SL-1",
                        "direction": "X",
                        "points": [
                            {"frequency_hz": 1.0, "acceleration_g": 0.25},
                            {"frequency_hz": 4.0, "acceleration_g": 0.72},
                        ],
                    },
                    {
                        "level": "SL-2",
                        "direction": "Z",
                        "points": [{"frequency_hz": 4.0, "acceleration_g": 1.15}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    features = _persist_spectrum_selection_features(
        job_dir,
        {
            "sheet": "reviewed-sheet",
            "requested_elevation": 8.5,
            "selected_elevation": 8.5,
            "static_acceleration_source": {
                "workbook_sha256": "abc123",
                "zpa_sse_x_g": 0.3,
                "zpa_sse_y_g": 0.4,
                "zpa_sse_z_g": 0.5,
            },
        },
        "response_spectrum",
    )

    assert features["peak_acceleration_g"] == 1.15
    assert features["peak_acceleration_g_by_level_direction"] == {"sl-1_x": 0.72, "sl-2_z": 1.15}
    assert features["workbook_sha256"] == "abc123"
    persisted = json.loads((job_dir / "input.json").read_text(encoding="utf-8"))
    assert persisted["metadata"]["spectrum_selection_features"] == features


def test_static_features_ignore_stale_response_spectrum_points(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    _write_input(job_dir)
    (job_dir / "spectrum_points.json").write_text(
        json.dumps(
            {
                "load_steps": [
                    {
                        "level": "SL-2",
                        "direction": "X",
                        "points": [{"frequency_hz": 4.0, "acceleration_g": 9.9}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    features = _persist_spectrum_selection_features(
        job_dir,
        {"status": "not_required"},
        "static",
    )

    assert features["peak_acceleration_g"] is None
    assert features["peak_acceleration_g_by_level_direction"] == {}
