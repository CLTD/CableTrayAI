from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.ansys.candidate_selection import (
    _toml_string,
    choose_preferred_candidate,
    default_output_import_dir,
    default_workdir,
)
from core.ansys.config import AnsysLocalConfig, load_ansys_config
from core.ansys.discovery import discover_ansys, write_discovery_report


DEFAULT_CONFIG_PATH = Path("config/ansys.local.toml")


@dataclass(frozen=True)
class AutoConfigResult:
    status: str
    executable: str | None
    config_path: str
    runner_mode: str
    did_not_execute_ansys: bool
    candidate_count: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "executable": self.executable,
            "config_path": self.config_path,
            "runner_mode": self.runner_mode,
            "did_not_execute_ansys": self.did_not_execute_ansys,
            "candidate_count": self.candidate_count,
            "message": self.message,
        }


def _version_score(value: str | None) -> int:
    if not value:
        return 0
    numbers = re.findall(r"\d+", value)
    return max((int(number) for number in numbers), default=0)


def _candidate_score(candidate: dict[str, Any]) -> tuple[int, int, int, int, str]:
    executable = str(candidate.get("executable") or "")
    lower = executable.lower().replace("\\", "/")
    exists = Path(executable).exists()
    mechanical_apdl = "/ansys/bin/winx64/" in lower and bool(re.search(r"/ansys\d*\.exe$", lower))
    not_solver_helper = "/aisol/" not in lower and "launcher" not in lower
    version = _version_score(candidate.get("version_hint") or candidate.get("version") or executable)
    return (1 if exists else 0, 1 if mechanical_apdl else 0, 1 if not_solver_helper else 0, version, lower)


def choose_best_ansys_candidate(candidates: list[dict[str, Any]], preferred_version: str = "182") -> dict[str, Any] | None:
    valid = [candidate for candidate in candidates if candidate.get("executable")]
    if not valid:
        return None
    preferred = choose_preferred_candidate(valid, preferred_version=preferred_version)
    if preferred:
        return preferred
    return sorted(valid, key=_candidate_score, reverse=True)[0]


def _build_toml(executable: str, *, mode: str, default_workdir: str, output_dir: str) -> str:
    return "\n".join(
        [
            "[ansys]",
            f'executable = "{_toml_string(executable)}"',
            f'default_workdir = "{_toml_string(default_workdir)}"',
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
            f'default_source_dir = "{_toml_string(output_dir)}"',
            "",
        ]
    )


def _write_config(config_path: Path, executable: str, *, mode: str, output_dir: str) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        _build_toml(
            executable,
            mode=mode,
            default_workdir=default_workdir(),
            output_dir=output_dir,
        ),
        encoding="utf-8",
        newline="\n",
    )


def ensure_ansys_config(
    *,
    config_path: Path | str = DEFAULT_CONFIG_PATH,
    preferred_executable: str | None = None,
    force: bool = False,
    real_mode: bool = True,
    output_dir: str | None = None,
) -> tuple[AnsysLocalConfig, dict[str, Any]]:
    config_path = Path(config_path)
    mode = "real" if real_mode else "dry_run"

    if config_path.exists() and not force:
        config = load_ansys_config(config_path)
        existing = config.ansys.executable
        if existing and Path(existing).exists():
            if real_mode:
                config.runner.mode = "real"
            result = AutoConfigResult(
                status="existing_config_used",
                executable=existing,
                config_path=str(config_path),
                runner_mode=config.runner.mode,
                did_not_execute_ansys=True,
                candidate_count=1,
                message="Existing config/ansys.local.toml points to an existing ANSYS executable.",
            )
            return config, result.to_dict()

    candidate: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = []
    if preferred_executable and Path(preferred_executable).exists():
        candidate = {"executable": preferred_executable, "source": "preferred", "version_hint": None}
    else:
        discovery = discover_ansys(project_root=Path.cwd())
        write_discovery_report(discovery)
        candidates = list(discovery.get("candidates", []))
        candidate = choose_best_ansys_candidate(candidates, preferred_version="182")
    if not candidate:
        config = AnsysLocalConfig()
        result = AutoConfigResult(
            status="not_found",
            executable=None,
            config_path=str(config_path),
            runner_mode=config.runner.mode,
            did_not_execute_ansys=True,
            candidate_count=len(candidates),
            message="No ANSYS executable candidate was found. Discovery did not execute ANSYS.",
        )
        return config, result.to_dict()

    executable = str(candidate["executable"])
    _write_config(config_path, executable, mode=mode, output_dir=output_dir or default_output_import_dir())
    config = load_ansys_config(config_path)
    result = AutoConfigResult(
        status="config_written",
        executable=executable,
        config_path=str(config_path),
        runner_mode=mode,
        did_not_execute_ansys=True,
        candidate_count=len(candidates),
        message="ANSYS config was written from automatic discovery. Discovery did not execute ANSYS.",
    )
    Path("docs/ansys_auto_config.json").parent.mkdir(parents=True, exist_ok=True)
    Path("docs/ansys_auto_config.json").write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return config, result.to_dict()

