from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


DEFAULT_COMMON_DIRS = [
    Path(r"C:\Program Files\ANSYS Inc"),
    Path(r"C:\Program Files (x86)\ANSYS Inc"),
    Path(r"D:\Program Files\ANSYS Inc"),
    Path(r"E:\Program Files\ANSYS Inc"),
    Path(r"D:\ANSYS Inc"),
    Path(r"E:\ANSYS Inc"),
]

DEFAULT_REGISTRY_KEYS = [
    r"SOFTWARE\ANSYS, Inc.",
    r"SOFTWARE\ANSYS Inc",
    r"SOFTWARE\WOW6432Node\ANSYS, Inc.",
    r"SOFTWARE\WOW6432Node\ANSYS Inc",
]


@dataclass(frozen=True)
class AnsysCandidate:
    executable: str
    source: str
    version_hint: str | None = None


def _version_hint(path: Path) -> str | None:
    for part in path.parts:
        upper = part.upper()
        if upper.startswith(("V", "ANSYS")) and any(char.isdigit() for char in upper):
            return part
    return None


def _candidate(path: Path, source: str) -> AnsysCandidate:
    return AnsysCandidate(executable=str(path), source=source, version_hint=_version_hint(path))


def _is_ansys_exe(path: Path) -> bool:
    name = path.name.lower()
    return path.is_file() and name.startswith("ansys") and name.endswith(".exe")


def _is_mechanical_apdl_exe(path: Path) -> bool:
    name = path.name.lower()
    if not path.is_file() or name not in {"ansys.exe"} and not (name.startswith("ansys") and name[5:-4].isdigit() and name.endswith(".exe")):
        return False
    normalized = path.as_posix().lower()
    return "/ansys/bin/winx64/" in normalized


def find_mechanical_apdl_executables(root: Path | str) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    patterns = [
        "ansys/bin/winx64/ANSYS*.exe",
        "ansys/bin/winx64/ansys*.exe",
        "v*/ansys/bin/winx64/ANSYS*.exe",
        "v*/ansys/bin/winx64/ansys*.exe",
    ]
    found: list[Path] = []
    for pattern in patterns:
        try:
            found.extend(path for path in root.glob(pattern) if _is_mechanical_apdl_exe(path))
        except OSError:
            continue
    return sorted(set(found), key=lambda item: item.as_posix().lower())


def find_ansys_executables(root: Path | str, *, max_depth: int = 6) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    found: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_file() and _is_ansys_exe(entry):
                found.append(entry)
            elif entry.is_dir() and depth < max_depth:
                stack.append((entry, depth + 1))
    return sorted(found, key=lambda item: item.as_posix().lower())


def _mechanical_from_root(root: Path | str) -> list[Path]:
    targeted = find_mechanical_apdl_executables(root)
    if targeted:
        return targeted
    return [path for path in find_ansys_executables(root) if _is_mechanical_apdl_exe(path)]


def candidates_from_awp_roots(env: dict[str, str] | None = None) -> list[AnsysCandidate]:
    env = dict(os.environ) if env is None else env
    candidates: list[AnsysCandidate] = []
    for key, value in sorted(env.items()):
        if key.upper().startswith("AWP_ROOT") and value:
            executables = _mechanical_from_root(value)
            for executable in executables:
                candidates.append(_candidate(executable, f"env:{key}"))
    return candidates


def candidates_from_path(path_value: str | None = None) -> list[AnsysCandidate]:
    path_value = path_value if path_value is not None else os.environ.get("PATH", "")
    candidates: list[AnsysCandidate] = []
    for item in path_value.split(os.pathsep):
        if not item:
            continue
        path = Path(item)
        if path.is_file() and _is_ansys_exe(path):
            if _is_mechanical_apdl_exe(path):
                candidates.append(_candidate(path, "PATH"))
            continue
        if path.is_dir():
            try:
                for executable in sorted(path.glob("ansys*.exe"), key=lambda entry: entry.name.lower()):
                    if _is_mechanical_apdl_exe(executable):
                        candidates.append(_candidate(executable, "PATH"))
            except OSError:
                continue
    return candidates


def candidates_from_common_dirs(common_dirs: Iterable[Path | str] = DEFAULT_COMMON_DIRS) -> list[AnsysCandidate]:
    candidates: list[AnsysCandidate] = []
    for root in common_dirs:
        executables = _mechanical_from_root(root)
        for executable in executables:
            candidates.append(_candidate(executable, f"common_dir:{root}"))
    return candidates


def registry_install_paths() -> list[Path]:
    try:
        import winreg
    except ImportError:
        return []

    roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
    paths: list[Path] = []
    for root in roots:
        for key_name in DEFAULT_REGISTRY_KEYS:
            try:
                with winreg.OpenKey(root, key_name) as key:
                    paths.extend(_registry_paths_from_key(winreg, key))
            except OSError:
                continue
    return paths


def _registry_paths_from_key(winreg_module, key) -> list[Path]:
    paths: list[Path] = []
    value_count = winreg_module.QueryInfoKey(key)[1]
    for index in range(value_count):
        try:
            _, value, _ = winreg_module.EnumValue(key, index)
        except OSError:
            continue
        if isinstance(value, str) and ("ANSYS" in value.upper() or Path(value).exists()):
            paths.append(Path(value))
    subkey_count = winreg_module.QueryInfoKey(key)[0]
    for index in range(subkey_count):
        try:
            subkey_name = winreg_module.EnumKey(key, index)
            with winreg_module.OpenKey(key, subkey_name) as subkey:
                paths.extend(_registry_paths_from_key(winreg_module, subkey))
        except OSError:
            continue
    return paths


def candidates_from_registry(path_reader: Callable[[], list[Path]] = registry_install_paths) -> list[AnsysCandidate]:
    candidates: list[AnsysCandidate] = []
    for root in path_reader():
        if _is_mechanical_apdl_exe(root):
            candidates.append(_candidate(root, "registry"))
        else:
            executables = _mechanical_from_root(root)
            for executable in executables:
                candidates.append(_candidate(executable, "registry"))
    return candidates


def dedupe_candidates(candidates: Iterable[AnsysCandidate]) -> list[AnsysCandidate]:
    seen: dict[str, AnsysCandidate] = {}
    for candidate in candidates:
        key = str(Path(candidate.executable)).lower()
        if key not in seen:
            seen[key] = candidate
    return sorted(seen.values(), key=lambda item: item.executable.lower())


def _default_workdir(project_root: Path | str | None = None) -> str:
    root = Path.cwd() if project_root is None else Path(project_root)
    return str((root / "jobs").resolve()).replace("\\", "/")


def _default_output_dir(project_root: Path | str | None = None) -> str:
    root = Path.cwd() if project_root is None else Path(project_root)
    return str((root / "outputs").resolve()).replace("\\", "/")


def write_discovered_config(
    candidate: AnsysCandidate,
    config_dir: Path | str = Path("config"),
    *,
    project_root: Path | str | None = None,
) -> Path:
    config_dir = Path(config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / "ansys.local.discovered.toml"
    content = "\n".join(
        [
            "[ansys]",
            f'executable = "{candidate.executable.replace(chr(92), "/")}"',
            f'default_workdir = "{_default_workdir(project_root)}"',
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
            'mode = "dry_run"',
            "",
            "[output_import]",
            f'default_source_dir = "{_default_output_dir(project_root)}"',
            "",
        ]
    )
    target.write_text(content, encoding="utf-8")
    return target


def discover_ansys(
    *,
    env: dict[str, str] | None = None,
    path_value: str | None = None,
    common_dirs: Iterable[Path | str] = DEFAULT_COMMON_DIRS,
    registry_reader: Callable[[], list[Path]] = registry_install_paths,
    config_dir: Path | str = Path("config"),
    project_root: Path | str | None = None,
) -> dict:
    candidates = dedupe_candidates(
        [
            *candidates_from_awp_roots(env),
            *candidates_from_path(path_value),
            *candidates_from_common_dirs(common_dirs),
            *candidates_from_registry(registry_reader),
        ]
    )
    config_dir = Path(config_dir)
    local_config = config_dir / "ansys.local.toml"
    generated_config: str | None = None
    if len(candidates) == 1:
        generated_config = str(write_discovered_config(candidates[0], config_dir, project_root=project_root))
    payload = {
        "status": "single_candidate" if len(candidates) == 1 else ("multiple_candidates" if candidates else "not_found"),
        "candidate_count": len(candidates),
        "candidates": [asdict(candidate) for candidate in candidates],
        "generated_config": generated_config,
        "existing_local_config": str(local_config) if local_config.exists() else None,
        "did_not_execute_ansys": True,
        "notes": [
            "Discovery only inspects environment variables, PATH, common directories, and registry hints.",
            "Existing config/ansys.local.toml is never overwritten.",
        ],
    }
    return payload


def write_discovery_report(payload: dict, output_path: Path | str = Path("docs/ansys_discovery.json")) -> dict:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload

