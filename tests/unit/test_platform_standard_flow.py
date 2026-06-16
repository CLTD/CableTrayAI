from __future__ import annotations

from pathlib import Path

from core.apdl.platform_standard_flow import (
    PLATFORM_STANDARD_AUDIT,
    PLATFORM_STANDARD_POST,
    PLATFORM_STANDARD_POST_NUMERIC,
    PLATFORM_STANDARD_POST_NUMERIC_AUDIT,
    PLATFORM_STANDARD_SOLVE,
    build_platform_standard_shadow_flow,
    classify_platform_standard_scope,
)


def _single_tray_payload() -> dict:
    return {
        "metadata": {"analysis_method": "response_spectrum"},
        "support": {
            "support_type": "S2",
            "layers_front": 2,
            "layers_back": 0,
            "layers_third": 0,
            "support_spacing_m": 2.0,
            "support_height_m": 2.0,
        },
        "tray_layers": [
            {"side": "front", "layer_index": 1, "tray_width_m": 0.3},
            {"side": "front", "layer_index": 2, "tray_width_m": 0.3},
        ],
    }


def test_platform_standard_scope_accepts_single_tray_width_s2() -> None:
    scope = classify_platform_standard_scope(_single_tray_payload())

    assert scope["status"] == "pass"
    assert scope["tray_width_mm"] == 300
    assert scope["scope"] == "single_tray_width_s2_shadow_v1"


def test_platform_standard_scope_skips_mixed_tray_widths() -> None:
    payload = _single_tray_payload()
    payload["tray_layers"][1]["tray_width_m"] = 0.6

    scope = classify_platform_standard_scope(payload)

    assert scope["status"] == "skipped"
    assert scope["reason"] == "mixed_or_unknown_tray_widths"
    assert scope["tray_widths_mm"] == [300, 600]


def test_platform_standard_shadow_flow_writes_review_files_without_touching_main_numeric_audit(tmp_path: Path) -> None:
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    (job_dir / "generated_solve.mac").write_text(
        "\n".join(
            [
                "! CableTrayAI generated_solve.mac",
                "! Response-spectrum method for non-steel-platform support.",
                "/INPUT,'ansys_spectrum_sl1','mac','','',0",
                "/INPUT,'ansys_zpa_parameters','mac','','',0",
                "FINISH",
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "generated_post.mac").write_text(
        "\n".join(
            [
                "! CableTrayAI generated_post.mac",
                "/IMAGE,SAVE,SHITI,BMP",
                "*CFOPEN,MAXBEAMSTRESS,LIS",
                "*CFCLOS",
                "*CFOPEN,TMAXBEAMSTRESS,LIS",
                "*CFCLOS",
                "*CFOPEN,JCZH,LIS",
                "*CFCLOS",
                "*CFOPEN,LS-FORCE,LIS",
                "*CFCLOS",
            ]
        ),
        encoding="utf-8",
    )

    audit = build_platform_standard_shadow_flow(job_dir, _single_tray_payload())

    assert audit["status"] == "pass"
    assert (job_dir / PLATFORM_STANDARD_AUDIT).exists()
    assert (job_dir / PLATFORM_STANDARD_SOLVE).read_text(encoding="utf-8").startswith(
        "! CableTrayAI platform standard solve command stream."
    )
    assert (job_dir / PLATFORM_STANDARD_POST).read_text(encoding="utf-8").startswith(
        "! CableTrayAI platform standard post command stream."
    )
    numeric_text = (job_dir / PLATFORM_STANDARD_POST_NUMERIC).read_text(encoding="utf-8")
    assert "CableTrayAI numeric-post skipped graphics command: /IMAGE,SAVE,SHITI,BMP" in numeric_text
    assert "*CFOPEN,MAXBEAMSTRESS,LIS" in numeric_text
    assert (job_dir / PLATFORM_STANDARD_POST_NUMERIC_AUDIT).exists()
    assert not (job_dir / "generated_post_numeric_audit.json").exists()
    assert "generated_post_numeric.mac" not in (job_dir / "run_all.mac").read_text(encoding="utf-8", errors="ignore") if (job_dir / "run_all.mac").exists() else True

