from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_DISCOVERY_PATH = Path("docs/ansys_discovery.json")
DEFAULT_CONFIG_PATH = Path("config/ansys.local.toml")


def _to_posix(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def default_workdir(project_root: Path | str | None = None) -> str:
    root = Path.cwd() if project_root is None else Path(project_root)
    return _to_posix((root / "jobs").resolve())


def default_output_import_dir(project_root: Path | str | None = None) -> str:
    root = Path.cwd() if project_root is None else Path(project_root)
    return _to_posix((root / "outputs").resolve())


DEFAULT_WORKDIR = default_workdir()
DEFAULT_OUTPUT_IMPORT_DIR = default_output_import_dir()


@dataclass(frozen=True)
class SelectionResult:
    index: int
    executable: str
    version: str | None
    source: str | None
    config_path: str
    did_not_execute_ansys: bool = True


def load_discovery_candidates(discovery_path: Path | str = DEFAULT_DISCOVERY_PATH) -> list[dict[str, Any]]:
    discovery_path = Path(discovery_path)
    payload = json.loads(discovery_path.read_text(encoding="utf-8-sig"))
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("docs/ansys_discovery.json does not contain a candidates list")
    return candidates


def candidate_rows(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, candidate in enumerate(candidates, start=1):
        executable = str(candidate.get("executable") or "")
        rows.append(
            {
                "index": number,
                "executable": executable,
                "version": candidate.get("version_hint") or candidate.get("version"),
                "source": candidate.get("source"),
                "path": str(Path(executable).parent) if executable else "",
            }
        )
    return rows


def select_candidate(candidates: list[dict[str, Any]], index: int) -> dict[str, Any]:
    if index < 1 or index > len(candidates):
        raise IndexError(f"Candidate index must be between 1 and {len(candidates)}")
    candidate = candidates[index - 1]
    if not candidate.get("executable"):
        raise ValueError(f"Candidate {index} does not include an executable path")
    return candidate


def _toml_string(value: str) -> str:
    return value.replace("\\", "/").replace('"', '\\"')


def candidate_version_number(candidate: dict[str, Any]) -> int:
    text = " ".join(str(candidate.get(key) or "") for key in ("version_hint", "version", "executable"))
    numbers = re.findall(r"\d+", text)
    return max((int(number) for number in numbers), default=0)


def is_mechanical_apdl_candidate(candidate: dict[str, Any]) -> bool:
    executable = str(candidate.get("executable") or "").replace("\\", "/").lower()
    return "/ansys/bin/winx64/" in executable and bool(re.search(r"/ansys\d*\.exe$", executable))


def is_preferred_version_candidate(candidate: dict[str, Any], preferred_version: str = "182") -> bool:
    text = " ".join(str(candidate.get(key) or "") for key in ("version_hint", "version", "executable")).lower()
    compact = preferred_version.lower().lstrip("v")
    return f"v{compact}" in text or f"ansys{compact}" in text


def choose_preferred_candidate(candidates: list[dict[str, Any]], preferred_version: str = "182") -> dict[str, Any] | None:
    valid = [candidate for candidate in candidates if candidate.get("executable")]
    if not valid:
        return None

    def score(candidate: dict[str, Any]) -> tuple[int, int, int, int, str]:
        executable = str(candidate.get("executable") or "").lower()
        return (
            1 if is_preferred_version_candidate(candidate, preferred_version) and is_mechanical_apdl_candidate(candidate) else 0,
            1 if is_preferred_version_candidate(candidate, preferred_version) else 0,
            1 if is_mechanical_apdl_candidate(candidate) else 0,
            candidate_version_number(candidate),
            executable,
        )

    return sorted(valid, key=score, reverse=True)[0]


def build_ansys_local_toml(
    candidate: dict[str, Any],
    *,
    project_root: Path | str | None = None,
    output_dir: str | None = None,
    mode: str = "dry_run",
) -> str:
    executable = _toml_string(str(candidate["executable"]))
    workdir = default_workdir(project_root)
    source_dir = output_dir or default_output_import_dir(project_root)
    return "\n".join(
        [
            "[ansys]",
            f'executable = "{executable}"',
            f'default_workdir = "{_toml_string(workdir)}"',
            "timeout_minutes = 120",
            "license_wait = true",
            'product = "ansys"',
            "nproc_percent = 0.35",
            "startup_no_output_timeout_seconds = 90",
            "output_stall_timeout_seconds = 300",
            'memory = "4096"',
            "extra_args = []",
            "",
            "[runner]",
            f'mode = "{mode}"',
            "",
            "[output_import]",
            f'default_source_dir = "{_toml_string(source_dir)}"',
            "",
        ]
    )


def write_selected_candidate_config(
    candidate: dict[str, Any],
    *,
    index: int,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    force: bool = False,
    project_root: Path | str | None = None,
    output_dir: str | None = None,
    mode: str = "dry_run",
) -> SelectionResult:
    config_path = Path(config_path)
    if config_path.exists() and not force:
        raise FileExistsError(f"{config_path} already exists; pass -Force to overwrite it")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        build_ansys_local_toml(candidate, project_root=project_root, output_dir=output_dir, mode=mode),
        encoding="utf-8",
        newline="\n",
    )
    return SelectionResult(
        index=index,
        executable=str(candidate["executable"]),
        version=candidate.get("version_hint") or candidate.get("version"),
        source=candidate.get("source"),
        config_path=str(config_path),
    )


def select_and_write_config(
    index: int,
    *,
    discovery_path: Path | str = DEFAULT_DISCOVERY_PATH,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    force: bool = False,
    project_root: Path | str | None = None,
    output_dir: str | None = None,
    mode: str = "dry_run",
) -> SelectionResult:
    candidates = load_discovery_candidates(discovery_path)
    candidate = select_candidate(candidates, index)
    return write_selected_candidate_config(
        candidate,
        index=index,
        config_path=config_path,
        force=force,
        project_root=project_root,
        output_dir=output_dir,
        mode=mode,
    )

