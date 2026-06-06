from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from core.results.pip_output_manifest import KNOWN_RESULT_OUTPUTS


TEXT_OUTPUTS = {name.upper(): name for name in KNOWN_RESULT_OUTPUTS}
IMPORT_SUFFIXES = {".lis", ".oup", ".bmp", ".png", ".out", ".err", ".rst"}
FIGURE_SUFFIXES = {".bmp", ".png"}
MOCK_MARKERS = (b"MOCK", b"CABLETRAYAI STAGE")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_real_output_files(output_dir: Path | str) -> dict[str, Path]:
    output_dir = Path(output_dir)
    discovered: dict[str, Path] = {}
    if not output_dir.exists():
        return discovered
    for path in sorted(output_dir.rglob("*"), key=lambda item: item.as_posix().upper()):
        if path.is_file() and path.suffix.lower() in IMPORT_SUFFIXES:
            discovered[path.name.upper()] = path
    return discovered


def validate_real_output_dir(output_dir: Path | str, *, require_figures: bool = True) -> dict[str, Any]:
    output_dir = Path(output_dir)
    checks: list[dict[str, Any]] = []
    discovered = discover_real_output_files(output_dir)
    checks.append(
        {
            "check_id": "output_dir_exists",
            "status": "pass" if output_dir.exists() and output_dir.is_dir() else "fail",
            "message": "Real output directory exists",
            "evidence": str(output_dir),
        }
    )

    checks.append(
        {
            "check_id": "importable_files_available",
            "status": "pass" if discovered else "fail",
            "message": "At least one importable ANSYS output file is present",
            "evidence": sorted(discovered),
        }
    )

    for expected_upper, expected_name in sorted(TEXT_OUTPUTS.items()):
        found = discovered.get(expected_upper)
        checks.append(
            {
                "check_id": f"required_{expected_name}",
                "status": "pass" if found else "fail",
                "message": f"Required parser input {expected_name}",
                "evidence": str(found) if found else None,
                "source_ref": "docs/PIP_OUTPUT_MANIFEST.md",
            }
        )

    figures = [path for path in discovered.values() if path.suffix.lower() in FIGURE_SUFFIXES]
    checks.append(
        {
            "check_id": "figures_available",
            "status": "pass" if figures or not require_figures else "fail",
            "message": "BMP/PNG figures are available",
            "evidence": [path.name for path in figures],
            "source_ref": "figures_manifest.json",
        }
    )

    mock_markers = _mock_marker_files(discovered.values())
    checks.append(
        {
            "check_id": "mock_output_marker",
            "status": "fail" if mock_markers else "pass",
            "message": "Imported real-output directory must not contain CableTrayAI mock output markers",
            "evidence": mock_markers,
        }
    )

    optional_suffixes = {".out": "solver_out", ".err": "solver_err", ".rst": "result_rst"}
    for suffix, check_id in optional_suffixes.items():
        matched = [path for path in discovered.values() if path.suffix.lower() == suffix]
        checks.append(
            {
                "check_id": check_id,
                "status": "pass" if matched else "warning",
                "message": f"Optional {suffix} files are present",
                "evidence": [path.name for path in matched],
            }
        )

    file_manifest = [
        {
            "name": path.name,
            "relative_path": path.relative_to(output_dir).as_posix() if output_dir.exists() else path.name,
            "size": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(discovered.values(), key=lambda item: item.name.upper())
    ]
    status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    return {
        "status": status,
        "output_dir": str(output_dir),
        "checks": checks,
        "files": file_manifest,
        "file_count": len(file_manifest),
    }


def _mock_marker_files(paths: Iterable[Path]) -> list[str]:
    marked: list[str] = []
    for path in paths:
        if path.suffix.lower() not in {".lis", ".oup", ".out", ".err"}:
            continue
        try:
            chunk = path.read_bytes()[:8192].upper()
        except OSError:
            continue
        if any(marker in chunk for marker in MOCK_MARKERS):
            marked.append(path.name)
    return marked


def write_real_output_validation(output_dir: Path | str, target_path: Path | str) -> dict[str, Any]:
    validation = validate_real_output_dir(output_dir)
    Path(target_path).write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding="utf-8")
    return validation
