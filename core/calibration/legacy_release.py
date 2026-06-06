from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_LEGACY_RELEASE = Path(r"C:\Users\duxy\Desktop\tray_platform_onefile_release")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_legacy_alignment(release_dir: Path | str = DEFAULT_LEGACY_RELEASE) -> dict[str, Any]:
    release_dir = Path(release_dir)
    train_path = release_dir / "train50_alignment_v2.json"
    validation_path = release_dir / "untrained20_alignment_v2.json"
    selection_path = release_dir / "train50_untrained20_selection_v2.json"
    calibration_path = release_dir / "train50_alignment_v2_calibration.json"
    return {
        "release_dir": str(release_dir),
        "train": _read_json(train_path) if train_path.exists() else None,
        "validation": _read_json(validation_path) if validation_path.exists() else None,
        "selection": _read_json(selection_path) if selection_path.exists() else None,
        "calibration": _read_json(calibration_path) if calibration_path.exists() else None,
    }


def legacy_release_lessons(release_dir: Path | str = DEFAULT_LEGACY_RELEASE) -> dict[str, Any]:
    payload = load_legacy_alignment(release_dir)
    readme = Path(release_dir) / "项目README.md"
    text = readme.read_text(encoding="utf-8-sig", errors="replace") if readme.exists() else ""
    return {
        "status": "pass" if payload["train"] and payload["validation"] else "blocked",
        "release_dir": str(release_dir),
        "core_output_files": ["01_build_model.PIP", "02_solve.mac", "03_extract.mac", "04_visualize.mac"],
        "legacy_quality_method": [
            "Build a case library from intake Excel and historical reports.",
            "Generate command streams per case instead of asking the operator to write rows manually.",
            "Run real ANSYS MAPDL through a master macro.",
            "Compare generated command streams, extracted results, and report values before releasing UI changes.",
            "Use train samples for calibration and hold-out samples for validation.",
        ],
        "train_case_count": payload["train"].get("case_count") if payload["train"] else 0,
        "validation_case_count": payload["validation"].get("case_count") if payload["validation"] else 0,
        "legacy_validation_threshold": "5% in the archived release; current CableTrayAI gate is stricter at 1%.",
        "readme_mentions_gui": "图形界面" in text,
    }


def write_legacy_lessons_doc(
    output_path: Path | str = Path("docs/LEGACY_EXE_LESSONS.md"),
    release_dir: Path | str = DEFAULT_LEGACY_RELEASE,
) -> dict[str, Any]:
    lessons = legacy_release_lessons(release_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Legacy EXE Lessons",
        "",
        f"Release directory: `{lessons['release_dir']}`",
        f"Status: `{lessons['status']}`",
        "",
        "## Required Command Files",
        "",
        *[f"- `{name}`" for name in lessons["core_output_files"]],
        "",
        "## Workflow To Preserve",
        "",
        *[f"- {item}" for item in lessons["legacy_quality_method"]],
        "",
        "## Calibration Counts",
        "",
        f"- Training cases: {lessons['train_case_count']}",
        f"- Validation cases: {lessons['validation_case_count']}",
        f"- Legacy threshold: {lessons['legacy_validation_threshold']}",
        "",
        "## Current Policy",
        "",
        "The current project must treat 1% report/result comparison as the release gate. Values beyond 1% are blockers, not warnings.",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return lessons
