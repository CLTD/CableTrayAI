from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.ansys.command_builder import build_ansys_command, write_run_script
from core.ansys.config import AnsysLocalConfig, load_ansys_config
from core.ansys.connection_export import run_connection_node_export
from core.ansys.figure_export import run_figure_export
from core.ansys.lock_cleanup import cleanup_stale_ansys_locks
from core.ansys.preflight import run_preflight
from core.ansys.real_run_guard import evaluate_real_run_guard, write_rejected_real_run_audit
from core.apdl.numeric_post import NUMERIC_POST_MACRO, build_numeric_post_macro


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


_ANSYS_FATAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\*\*\*\s*FATAL\s*\*\*\*",
        r"\bfatal\s+error\b",
        r"\bworker process\b.*\berror\b",
        r"\bmemory\s*\(-m\)\s*size requested\b",
        r"\bnot currently available\b",
        r"\bterminated abnormally\b",
        r"\babort(?:ed|ing)\b",
    )
]

_ANSYS_BLOCKING_OUTPUT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "mapdl_error",
        re.compile(r"\*\*\*\s*ERROR\s*\*\*", re.IGNORECASE),
    ),
    (
        "command_stream_error",
        re.compile(
            r"\b(?:unknown|unrecognized|invalid|illegal)\s+(?:command|label|argument|parameter)\b|"
            r"\bcommand\s+(?:is\s+)?(?:ignored|not\s+recognized)\b|"
            r"\b(?:KSEL|NSEL|ESEL|CMSEL|LCFILE|LCASE|RESUME|ETABLE|PLNSOL|PLDISP|/SHOW|/IMAGE)\b.*\b(?:invalid|error|failed)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "file_or_permission_error",
        re.compile(
            r"\b(?:could\s+not|cannot|can't|unable\s+to)\s+(?:open|read|write|access|find)\b|"
            r"\b(?:access\s+is\s+denied|permission\s+denied|no\s+such\s+file|file\s+not\s+found|does\s+not\s+exist)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "post_export_error",
        re.compile(
            r"\b(?:connection_node_export|export_connection_nodes|LS-FORCE-NODES|figure_export|generated_post_figure_export)\b"
            r".*\b(?:failed|error|invalid|missing)\b",
            re.IGNORECASE,
        ),
    ),
]

_LIVE_OUTPUT_SUFFIXES = {".out", ".err", ".rst", ".db", ".lis", ".oup", ".bmp", ".png", ".log"}

MIN_REAL_RUN_TIMEOUT_MINUTES = 120
MIN_REAL_RUN_STARTUP_NO_OUTPUT_TIMEOUT_SECONDS = 90
MIN_REAL_RUN_OUTPUT_STALL_TIMEOUT_SECONDS = 300


def _positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _nonnegative_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 0 else default


def _effective_real_run_timeout_policy(config: AnsysLocalConfig) -> dict[str, Any]:
    """Return code-level minimum ANSYS watchdog settings for production runs.

    Update packages intentionally preserve unit-site ``ansys.local.toml`` files.
    That means stale local timeout settings can otherwise kill a valid ANSYS
    solve before APDL/PIP post-processing writes result JSON.  The configured
    values are still recorded for traceability, but real production runs use a
    hard minimum that matches the acceptance runs.
    """

    configured_timeout_minutes = _positive_int(
        getattr(config.ansys, "timeout_minutes", None),
        MIN_REAL_RUN_TIMEOUT_MINUTES,
    )
    configured_startup = _positive_int(
        getattr(config.ansys, "startup_no_output_timeout_seconds", None),
        MIN_REAL_RUN_STARTUP_NO_OUTPUT_TIMEOUT_SECONDS,
    )
    configured_stall = _nonnegative_int(
        getattr(config.ansys, "output_stall_timeout_seconds", None),
        MIN_REAL_RUN_OUTPUT_STALL_TIMEOUT_SECONDS,
    )
    effective_timeout_minutes = max(configured_timeout_minutes, MIN_REAL_RUN_TIMEOUT_MINUTES)
    effective_startup = max(configured_startup, MIN_REAL_RUN_STARTUP_NO_OUTPUT_TIMEOUT_SECONDS)
    effective_stall = 0 if configured_stall == 0 else max(configured_stall, MIN_REAL_RUN_OUTPUT_STALL_TIMEOUT_SECONDS)
    return {
        "status": "clamped" if (
            effective_timeout_minutes != configured_timeout_minutes
            or effective_startup != configured_startup
            or effective_stall != configured_stall
        ) else "unchanged",
        "configured_timeout_minutes": configured_timeout_minutes,
        "configured_timeout_seconds": configured_timeout_minutes * 60,
        "timeout_minutes": effective_timeout_minutes,
        "timeout_seconds": effective_timeout_minutes * 60,
        "minimum_timeout_minutes": MIN_REAL_RUN_TIMEOUT_MINUTES,
        "minimum_timeout_seconds": MIN_REAL_RUN_TIMEOUT_MINUTES * 60,
        "configured_startup_no_output_timeout_seconds": configured_startup,
        "startup_no_output_timeout_seconds": effective_startup,
        "minimum_startup_no_output_timeout_seconds": MIN_REAL_RUN_STARTUP_NO_OUTPUT_TIMEOUT_SECONDS,
        "configured_output_stall_timeout_seconds": configured_stall,
        "output_stall_timeout_seconds": effective_stall,
        "output_stall_hard_kill_enabled": effective_stall > 0,
        "minimum_output_stall_timeout_seconds": MIN_REAL_RUN_OUTPUT_STALL_TIMEOUT_SECONDS,
        "policy": (
            "Real ANSYS production runs use code-level minimum watchdogs so "
            "unit-site preserved local configs cannot terminate a valid solve before results are produced."
        ),
    }

_IGNORED_SELECTION_WARNING_RE = re.compile(
    r"\b(?:Entity\s+\d+\s+is\s+undefined\.\s+)?(?:The\s+)?"
    r"(?:KSEL|NSEL|ESEL|LSEL|CMSEL)\s+command\s+is\s+ignored\b",
    re.IGNORECASE,
)

_IGNORED_GRAPHICS_WARNING_RE = re.compile(
    r"/IMAGE\s+requires\s+/MENU,\s*(?:ON|GRPH)|\bCommand\s+ignored\b",
    re.IGNORECASE,
)

_MPI_CWD_IGNORED_RE = re.compile(
    r"/CWD\s+command\s+is\s+ignored\s+on\s+MPI\s+process\s+with\s+rank\b",
    re.IGNORECASE,
)


def _brief_output_file(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "size_bytes": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
    }


def _job_output_activity(job_dir: Path, command: dict[str, Any], started_monotonic: float) -> dict[str, Any]:
    candidates: dict[Path, None] = {}
    output_file = Path(command.get("output_file") or job_dir / "ansys.out")
    for path in [output_file, job_dir / "ansys_stdout.log", job_dir / "ansys_stderr.log"]:
        candidates[path] = None
    for child in job_dir.glob("*"):
        if child.is_file() and child.suffix.lower() in _LIVE_OUTPUT_SUFFIXES:
            candidates[child] = None

    total_bytes = 0
    nonzero_files = 0
    newest_mtime: float | None = None
    latest: list[dict[str, Any]] = []
    for path in candidates:
        try:
            if not path.exists() or not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        total_bytes += stat.st_size
        if stat.st_size > 0:
            nonzero_files += 1
        newest_mtime = stat.st_mtime if newest_mtime is None else max(newest_mtime, stat.st_mtime)
        latest.append(_brief_output_file(path))

    latest = sorted(latest, key=lambda item: item["updated_at"], reverse=True)[:12]
    now = time.time()
    no_output_seconds = round(time.monotonic() - started_monotonic, 1)
    if newest_mtime:
        no_output_seconds = max(0.0, round(now - newest_mtime, 1))
    return {
        "total_output_bytes": total_bytes,
        "total_output_mb": round(total_bytes / 1024 / 1024, 3),
        "nonzero_file_count": nonzero_files,
        "latest_files": latest,
        "latest_update": datetime.fromtimestamp(newest_mtime, timezone.utc).isoformat() if newest_mtime else None,
        "no_output_seconds": no_output_seconds,
        "output_file_bytes": output_file.stat().st_size if output_file.exists() else 0,
    }


def _read_text_tail(path: Path, max_chars: int = 12000) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_chars), os.SEEK_SET)
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _is_nonblocking_ansys_warning(category: str, message: str, context: str) -> bool:
    """Return true for MAPDL warnings that should not block parsing.

    Post-processing command streams sometimes probe optional entity or
    component ranges. MAPDL records a WARNING such as "Entity 52 is undefined.
    The ESEL command is ignored" when that optional selection is absent. That
    is not by itself a failed calculation; the later result gates still block
    missing LIS rows, UNKNOWN nodes, all-zero required tables, and missing
    figures. ERROR/FATAL contexts remain blocking.
    """

    if "*** ERROR ***" in context.upper() or "*** FATAL ***" in context.upper():
        return False
    if category == "file_or_permission_error":
        # MAPDL sometimes emits WARNING-level file probes while checking optional
        # scratch, graphics, or export targets.  Do not fail the real run at this
        # text-scan layer for warnings only; required files, blank tables, and
        # figures remain blocked by the deterministic result validation gate.
        return "*** WARNING ***" in context.upper()
    if category != "command_stream_error":
        return False
    if _MPI_CWD_IGNORED_RE.search(message) or _MPI_CWD_IGNORED_RE.search(context):
        return True
    if "*** WARNING ***" not in context.upper():
        return False
    return any(
        pattern.search(message) or pattern.search(context)
        for pattern in (
            _IGNORED_SELECTION_WARNING_RE,
            _IGNORED_GRAPHICS_WARNING_RE,
        )
    )


def _detect_ansys_fatal_outputs(job_dir: Path, extra_paths: list[Path] | None = None) -> dict[str, Any]:
    """Detect MAPDL fatal messages even when the launcher return code is zero.

    Some parallel MAPDL failures leave a zero launcher code but write worker
    fatal messages to ``ansys.out`` or ``CableTrayAI_Run*.out``. Treat those as
    real run failures so downstream parsing never publishes missing/zero data.
    """

    candidate_paths: list[Path] = []
    for name in ("ansys.out", "ansys_stdout.log", "ansys_stderr.log"):
        candidate_paths.append(job_dir / name)
    candidate_paths.extend(sorted(job_dir.glob("*.out")))
    candidate_paths.extend(sorted(job_dir.glob("*.err")))
    if extra_paths:
        candidate_paths.extend(extra_paths)

    seen: set[Path] = set()
    evidence: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for raw_path in candidate_paths:
        path = raw_path.resolve()
        if path in seen:
            continue
        seen.add(path)
        text = _read_text_tail(path)
        if not text:
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            category = None
            message = line.strip()
            if any(pattern.search(line) for pattern in _ANSYS_FATAL_PATTERNS):
                category = "fatal"
            else:
                for candidate_category, pattern in _ANSYS_BLOCKING_OUTPUT_PATTERNS:
                    if pattern.search(line):
                        category = candidate_category
                        break
            if category:
                start = max(0, idx - 2)
                end = min(len(lines), idx + 3)
                if category == "mapdl_error":
                    for context_line in lines[start:end]:
                        for candidate_category, pattern in _ANSYS_BLOCKING_OUTPUT_PATTERNS:
                            if candidate_category == "mapdl_error":
                                continue
                            if pattern.search(context_line):
                                category = candidate_category
                                message = context_line.strip()
                                break
                        if category != "mapdl_error":
                            break
                context = "\n".join(lines[start:end])[-1200:]
                payload = {
                    "file": str(path),
                    "category": category,
                    "message": message,
                    "context": context,
                }
                if _is_nonblocking_ansys_warning(category, message, context):
                    if len(warnings) < 25:
                        warnings.append(payload)
                    continue
                evidence.append(
                    payload
                )
                break
    return {
        "status": "failed" if evidence else "pass",
        "evidence": evidence,
        "warnings": warnings,
        "categories": sorted({item["category"] for item in evidence}),
    }


def _post_export_failure(
    connection_export_audit: dict[str, Any] | None,
    figure_export_audit: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a blocking post-export failure if downstream exports are unusable."""

    checks = [
        ("connection_node_export", connection_export_audit),
        ("figure_export", figure_export_audit),
    ]
    for name, audit in checks:
        if not audit:
            continue
        status = audit.get("status")
        reason = str(audit.get("reason") or "")
        if status in {"failed", "rejected"}:
            return {
                "name": name,
                "status": status,
                "reason": reason or f"{name} returned {status}",
                "audit": audit,
            }
        if name == "connection_node_export" and status == "skipped" and "not required" not in reason:
            return {
                "name": name,
                "status": status,
                "reason": reason or "connection node export was skipped before required topology data could be written",
                "audit": audit,
            }
    return None


def _failed_post_export_audit(name: str, exc: BaseException) -> dict[str, Any]:
    return {
        "status": "failed",
        "mode": name,
        "executed": True,
        "reason": f"{type(exc).__name__}: {exc}",
        "exception_type": type(exc).__name__,
    }


def _write_final_live_status(
    job_dir: Path,
    *,
    command: dict[str, Any],
    started_monotonic: float,
    process_pid: int | None,
    status: str,
    returncode: int | None,
    failure_reason: str | None,
    failure_category: str | None,
    figure_count: int | None,
    timeout_policy: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    stage = "ansys_finished" if status == "success" else "ansys_failed"
    live_status = {
        "stage": stage,
        "status": status,
        "process_running": False,
        "ansys_pid": process_pid,
        "returncode": returncode,
        "failure_reason": failure_reason,
        "failure_category": failure_category,
        "figure_count": figure_count,
        "timeout_seconds": (timeout_policy or {}).get("timeout_seconds"),
        "configured_timeout_seconds": (timeout_policy or {}).get("configured_timeout_seconds"),
        "timeout_policy": timeout_policy,
        "nproc": command.get("resources", {}).get("nproc"),
        "nproc_source": command.get("resources", {}).get("nproc_source"),
        "command_line": command.get("command_line"),
        **_job_output_activity(job_dir, command, started_monotonic),
    }
    _write_json(job_dir / "ansys_live_status.json", live_status)
    if progress_callback:
        progress_callback(live_status)
    return live_status


def _kill_process_tree(pid: int) -> dict[str, Any]:
    if pid <= 0:
        return {"status": "skipped", "reason": "invalid pid"}
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "status": "success" if completed.returncode in {0, 128} else "failed",
            "pid": pid,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-2000:],
            "stderr": completed.stderr[-2000:],
        }
    try:
        import signal

        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return {"status": "success", "pid": pid}
    except Exception as exc:  # pragma: no cover - platform dependent
        return {"status": "failed", "pid": pid, "error": str(exc)}


def _kill_ansys_processes_for_job(job_dir: Path) -> dict[str, Any]:
    """Terminate ANSYS children that still reference this job directory.

    MAPDL can leave worker processes alive when the launcher is killed on
    Windows. Matching the absolute job path keeps cleanup scoped to this job.
    """

    if os.name != "nt":
        return {"status": "skipped", "reason": "windows_process_query_only"}
    job_text = str(job_dir.resolve()).replace("'", "''")
    script = (
        "$job = '"
        + job_text
        + "'; "
        + "Get-CimInstance Win32_Process | "
        + "Where-Object { $_.CommandLine -and $_.CommandLine.Contains($job) -and $_.Name -match '^(ANSYS\\d*|ansys\\d*|MAPDL|mapdl|mpiexec)\\.exe$' } | "
        + "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    killed = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    return {
        "status": "success" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "killed_pids": killed,
        "stderr": completed.stderr[-2000:],
    }


def _write_placeholder_bmp(path: Path, label: str) -> None:
    try:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (640, 420), color=(245, 247, 250))
        draw = ImageDraw.Draw(image)
        draw.rectangle((24, 24, 616, 396), outline=(60, 72, 88), width=3)
        draw.text((48, 56), "CableTrayAI Stage 2 Mock Figure", fill=(30, 41, 59))
        draw.text((48, 92), label, fill=(15, 23, 42))
        draw.line((80, 300, 560, 140), fill=(37, 99, 235), width=8)
        draw.line((80, 300, 560, 300), fill=(22, 163, 74), width=6)
        image.save(path)
    except Exception:
        path.write_bytes(b"BM")


def _mock_lis_files(job_dir: Path) -> list[str]:
    files: dict[str, str] = {
        "MAXBEAMSTRESS.LIS": "\n".join(
            [
                "# CableTrayAI MOCK_LIS_V2 realistic comma table",
                "case,value_type,element,value,unit",
                "A,SDIR_TENSION,101,82.5,MPa",
                "A,SDIR_COMPRESSION,102,76.0,MPa",
                "A,SBEND,103,64.0,MPa",
                "A,SHEAR,104,28.0,MPa",
                "B,SDIR_TENSION,201,95.0,MPa",
                "B,SBEND,203,72.0,MPa",
                "D,SDIR_TENSION,301,118.0,MPa",
                "D,SBEND,303,84.0,MPa",
            ]
        ),
        "TMAXBEAMSTRESS.LIS": "\n".join(
            [
                "# CableTrayAI MOCK_LIS_V2 realistic comma table",
                "case,value_type,element,value,unit",
                "A,TRAY_EQV,401,38.0,MPa",
                "B,TRAY_EQV,402,45.0,MPa",
                "D,TRAY_EQV,403,58.0,MPa",
            ]
        ),
        "JCZH.LIS": "\n".join(
            [
                "# CableTrayAI MOCK_LIS_V2 realistic comma table",
                "load_case,node,fx,fy,fz,mx,my,mz,force_unit,moment_unit",
                "A,N1,1.20,0.35,5.40,0.18,0.22,0.04,kN,kN*m",
                "B,N1,1.85,0.52,6.10,0.26,0.31,0.05,kN,kN*m",
                "D,N1,2.30,0.70,7.80,0.33,0.41,0.07,kN,kN*m",
            ]
        ),
        "HF-FORCE.LIS": "\n".join(
            [
                "# CableTrayAI MOCK_LIS_V2 realistic comma table",
                "component,load_case,force_n,stress_mpa,allowable_mpa",
                "WELD_MAIN,A,12800,86.0,140.0",
                "WELD_MAIN,B,15400,101.0,140.0",
                "WELD_MAIN,D,18800,119.0,140.0",
            ]
        ),
        "LS-FORCE.LIS": "\n".join(
            [
                "# CableTrayAI MOCK_LIS_V2 realistic comma table",
                "bolt_group,load_case,tension_mpa,shear_mpa,allowable_tension_mpa,allowable_shear_mpa",
                "ANCHOR_MAIN,A,62.0,34.0,160.0,100.0",
                "ANCHOR_MAIN,B,75.0,41.0,160.0,100.0",
                "ANCHOR_MAIN,D,92.0,55.0,160.0,100.0",
            ]
        ),
        "Mode.oup": "\n".join(
            [
                "# CableTrayAI MOCK_MODAL_V2 realistic comma table",
                "mode,frequency_hz,period_s,mass_x,mass_y,mass_z",
                "1,8.125,0.1231,0.42,0.12,0.03",
                "2,14.800,0.0676,0.18,0.37,0.05",
                "3,23.450,0.0426,0.05,0.21,0.29",
                "4,31.200,0.0321,0.03,0.08,0.34",
            ]
        ),
    }
    written: list[str] = []
    for name, content in files.items():
        path = job_dir / name
        path.write_text(content + "\n", encoding="utf-8", newline="\n")
        written.append(name)
    return written


def run_mock_ansys(job_dir: Path | str) -> dict:
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)

    lis_files = _mock_lis_files(job_dir)
    figure_names = [
        "MOTAI-1.bmp",
        "MOTAI-2.bmp",
        "MOTAI-3.bmp",
        "MOTAI-4.bmp",
        "SHITI.bmp",
        "A1SDIR1-101.bmp",
        "A2SDIR2-102.bmp",
        "A3SBEND1+103.bmp",
        "A4SHEAR+104.bmp",
        "B1SDIR1-201.bmp",
        "B3SBEND1+203.bmp",
        "D1SDIR1-301.bmp",
        "D3SBEND1+303.bmp",
        "D4SHEAR+304.bmp",
        "A-SDIR1.bmp",
        "B-SDIR1.bmp",
        "D-SDIR1.bmp",
        "A-SBEND.bmp",
        "B-SBEND.bmp",
        "D-SBEND.bmp",
        "SQ-B1SDIR1.bmp",
        "SQ-B2SDIR2.bmp",
        "SQ-B3SBEND.bmp",
        "SQ-B4SHEAR.bmp",
        "SQ-D1SDIR1.bmp",
        "SQ-D2SDIR2.bmp",
        "SQ-D3SBEND.bmp",
        "SQ-D4SHEAR.bmp",
    ]
    for figure_name in figure_names:
        _write_placeholder_bmp(job_dir / figure_name, figure_name)

    audit = {
        "status": "success",
        "mode": "mock",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "lis_files": lis_files,
        "figure_files": figure_names,
        "kept_job_directory": True,
        "notes": [
            "Stage 2 mock runner generated deterministic LIS, Mode.oup, and realistic placeholder figure names.",
            "No external ANSYS executable was invoked.",
        ],
    }
    _write_json(job_dir / "ansys_run_audit.json", audit)
    return audit


def run_ansys(
    job_dir: Path | str,
    mode: str = "mock",
    config: dict | None = None,
    *,
    confirm_real_run: bool = False,
    confirm_user: str | None = None,
) -> dict:
    job_dir = Path(job_dir)
    loaded_config = _coerce_config(mode=mode, config=config)
    effective_mode = mode or loaded_config.runner.mode
    loaded_config.runner.mode = effective_mode
    if effective_mode == "mock":
        return run_mock_ansys(job_dir)
    if effective_mode == "dry_run":
        return run_dry_ansys(job_dir, loaded_config)
    if effective_mode == "real":
        return run_real_ansys(
            job_dir,
            loaded_config,
            confirm_real_run=confirm_real_run,
            confirm_user=confirm_user,
        )
    audit = {
        "status": "rejected",
        "mode": effective_mode,
        "kept_job_directory": True,
        "notes": [f"Unsupported ANSYS runner mode: {effective_mode}"],
    }
    _write_json(job_dir / "ansys_run_audit.json", audit)
    return audit


def _coerce_config(mode: str | None = None, config: dict | AnsysLocalConfig | None = None) -> AnsysLocalConfig:
    if isinstance(config, AnsysLocalConfig):
        loaded = config
    elif isinstance(config, dict):
        loaded = AnsysLocalConfig(**config)
    else:
        loaded = load_ansys_config()
    if mode:
        loaded.runner.mode = mode
    return loaded


def run_dry_ansys(job_dir: Path | str, config: AnsysLocalConfig | None = None) -> dict:
    job_dir = Path(job_dir)
    job_dir.mkdir(parents=True, exist_ok=True)
    config = config or load_ansys_config()
    config.runner.mode = "dry_run"
    command = build_ansys_command(config, job_dir)
    script_path = write_run_script(command, job_dir)
    preflight = run_preflight(job_dir, config=config)
    audit = {
        "status": "dry_run",
        "mode": "dry_run",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "command_file": "ansys_command.json",
        "run_script": script_path.name,
        "preflight_status": preflight["status"],
        "executed": False,
        "kept_job_directory": True,
        "notes": ["Dry-run generated command files and did not invoke ANSYS."],
    }
    _write_json(job_dir / "ansys_run_audit.json", audit)
    return audit


def run_real_ansys(
    job_dir: Path | str,
    config: AnsysLocalConfig | None = None,
    *,
    config_path: Path | str = Path("config/ansys.local.toml"),
    confirm_real_run: bool = False,
    confirm_user: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    run_post_exports: bool = True,
) -> dict:
    job_dir = Path(job_dir)
    config = config or load_ansys_config()
    numeric_post_audit = build_numeric_post_macro(job_dir)
    post_macro_name = (
        str(numeric_post_audit.get("target") or NUMERIC_POST_MACRO)
        if numeric_post_audit.get("status") == "pass"
        else "generated_post.mac"
    )
    command = build_ansys_command(config, job_dir, post_macro_name=post_macro_name)
    write_run_script(command, job_dir)
    preflight = run_preflight(job_dir, config=config)
    guard = evaluate_real_run_guard(
        job_dir,
        config_path=config_path,
        config=config,
        preflight=preflight,
        confirm_real_run=confirm_real_run,
        confirm_user=confirm_user,
    )
    if not guard["accepted"]:
        return write_rejected_real_run_audit(job_dir, guard, preflight_status=preflight["status"])

    lock_cleanup = cleanup_stale_ansys_locks(job_dir)
    started = datetime.now(timezone.utc)
    timeout_policy = _effective_real_run_timeout_policy(config)
    timeout_seconds = int(timeout_policy["timeout_seconds"])
    startup_timeout = int(timeout_policy["startup_no_output_timeout_seconds"])
    stall_timeout = int(timeout_policy["output_stall_timeout_seconds"])
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    stdout_path = job_dir / "ansys_stdout.log"
    stderr_path = job_dir / "ansys_stderr.log"
    timed_out = False
    startup_no_output_timeout = False
    output_stall_timeout = False
    timeout_cleanup: dict[str, Any] | None = None
    job_cleanup: dict[str, Any] | None = None
    started_monotonic = time.monotonic()
    last_progress = 0.0
    with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8", errors="replace"
    ) as stderr_handle:
        process = subprocess.Popen(
            command["command"],
            cwd=str(job_dir),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            creationflags=creationflags,
        )
        while True:
            returncode = process.poll()
            elapsed = time.monotonic() - started_monotonic
            if elapsed - last_progress >= 5.0 or last_progress == 0.0:
                activity = _job_output_activity(job_dir, command, started_monotonic)
                live_status = {
                    "stage": "running_ansys",
                    "process_running": returncode is None,
                    "ansys_pid": process.pid,
                    "elapsed_seconds": round(elapsed, 1),
                    "timeout_seconds": timeout_seconds,
                    "configured_timeout_seconds": timeout_policy["configured_timeout_seconds"],
                    "timeout_policy": timeout_policy,
                    "nproc": command.get("resources", {}).get("nproc"),
                    "nproc_source": command.get("resources", {}).get("nproc_source"),
                    "command_line": command.get("command_line"),
                    **activity,
                }
                _write_json(job_dir / "ansys_live_status.json", live_status)
                if progress_callback:
                    progress_callback(live_status)
                last_progress = elapsed
            if returncode is not None:
                break
            if startup_timeout > 0 and elapsed > startup_timeout:
                activity = _job_output_activity(job_dir, command, started_monotonic)
                if int(activity.get("total_output_bytes") or 0) <= 0:
                    startup_no_output_timeout = True
                    timeout_cleanup = _kill_process_tree(process.pid)
                    job_cleanup = _kill_ansys_processes_for_job(job_dir)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        pass
                    live_status = {
                        "stage": "startup_no_output_timeout",
                        "process_running": False,
                        "ansys_pid": process.pid,
                        "elapsed_seconds": round(elapsed, 1),
                        "timeout_seconds": timeout_seconds,
                        "startup_no_output_timeout_seconds": startup_timeout,
                        "configured_timeout_seconds": timeout_policy["configured_timeout_seconds"],
                        "timeout_policy": timeout_policy,
                        "nproc": command.get("resources", {}).get("nproc"),
                        "nproc_source": command.get("resources", {}).get("nproc_source"),
                        "message": "ANSYS process produced no output bytes during startup window and was stopped for safe retry.",
                        **activity,
                    }
                    _write_json(job_dir / "ansys_live_status.json", live_status)
                    if progress_callback:
                        progress_callback(live_status)
                    break
            if stall_timeout > 0:
                activity = _job_output_activity(job_dir, command, started_monotonic)
                quiet_seconds = float(activity.get("no_output_seconds") or 0.0)
                total_bytes = int(activity.get("total_output_bytes") or 0)
                if total_bytes > 0 and quiet_seconds > stall_timeout:
                    output_stall_timeout = True
                    timeout_cleanup = _kill_process_tree(process.pid)
                    job_cleanup = _kill_ansys_processes_for_job(job_dir)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        pass
                    live_status = {
                        "stage": "output_stall_timeout",
                        "process_running": False,
                        "ansys_pid": process.pid,
                        "elapsed_seconds": round(elapsed, 1),
                        "timeout_seconds": timeout_seconds,
                        "output_stall_timeout_seconds": stall_timeout,
                        "configured_timeout_seconds": timeout_policy["configured_timeout_seconds"],
                        "timeout_policy": timeout_policy,
                        "nproc": command.get("resources", {}).get("nproc"),
                        "nproc_source": command.get("resources", {}).get("nproc_source"),
                        "message": "ANSYS output files stopped changing during the stall window and the process was stopped for safe retry.",
                        **activity,
                    }
                    _write_json(job_dir / "ansys_live_status.json", live_status)
                    if progress_callback:
                        progress_callback(live_status)
                    break
            if elapsed > timeout_seconds:
                timed_out = True
                timeout_cleanup = _kill_process_tree(process.pid)
                job_cleanup = _kill_ansys_processes_for_job(job_dir)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
                break
            time.sleep(2.5)
    finished = datetime.now(timezone.utc)
    figure_export_audit = None
    connection_export_audit = None
    post_export_failure = None
    returncode = process.returncode
    fatal_detection = _detect_ansys_fatal_outputs(job_dir, [stdout_path, stderr_path])
    fatal_found = fatal_detection["status"] == "failed"
    if not timed_out and returncode == 0 and not fatal_found and run_post_exports:
        if progress_callback:
            progress_callback(
                {
                    "stage": "exporting_connection_nodes",
                    "message": "ANSYS 主求解完成，正在导出连接/基础节点结果。",
                    "nproc": command.get("resources", {}).get("nproc"),
                }
            )
        try:
            connection_export_audit = run_connection_node_export(job_dir, config)
        except Exception as exc:  # pragma: no cover - defensive guard for external ANSYS subprocess failures
            connection_export_audit = _failed_post_export_audit("connection_node_export", exc)
            _write_json(job_dir / "connection_node_export_audit.json", connection_export_audit)
        if progress_callback:
            progress_callback(
                {
                    "stage": "exporting_figures",
                    "message": "正在从 ANSYS 数据库导出模态图和应力云图。",
                    "nproc": command.get("resources", {}).get("nproc"),
                }
            )
        try:
            post_timeout_minutes = max(1, min(int(config.ansys.timeout_minutes or 120), 20))
            figure_export_audit = run_figure_export(
                job_dir,
                config,
                timeout_minutes=post_timeout_minutes,
                progress_callback=progress_callback,
            )
        except Exception as exc:  # pragma: no cover - defensive guard for external ANSYS subprocess failures
            figure_export_audit = _failed_post_export_audit("figure_export", exc)
            _write_json(job_dir / "figure_export_audit.json", figure_export_audit)
        post_export_failure = _post_export_failure(connection_export_audit, figure_export_audit)
        post_export_paths = [
            job_dir / "connection_node_export.out",
            job_dir / "connection_node_export_stdout.log",
            job_dir / "connection_node_export_stderr.log",
            job_dir / "figure_export_stdout.log",
            job_dir / "figure_export_stderr.log",
            job_dir / "export_figures.out",
        ]
        post_export_detection = _detect_ansys_fatal_outputs(job_dir, post_export_paths)
        if post_export_detection["status"] == "failed":
            fatal_detection = post_export_detection
            fatal_found = True
        if progress_callback:
            progress_callback(
                {
                    "stage": "ansys_post_exports_done",
                    "message": "ANSYS 后处理导出完成，准备解析 LIS/OUP/PNG。",
                    "nproc": command.get("resources", {}).get("nproc"),
                    "figure_count": (figure_export_audit or {}).get("figure_count"),
                }
            )
    if startup_no_output_timeout:
        status = "startup_no_output_timeout"
        failure_reason = "ANSYS process produced no output bytes during startup window; it was stopped so the operator flow can retry with safer resource settings."
    elif output_stall_timeout:
        status = "output_stall_timeout"
        failure_reason = "ANSYS output files stopped changing during the stall window; it was stopped so the operator flow can retry with safer resource settings."
    elif timed_out:
        status = "timeout"
        failure_reason = "ANSYS exceeded timeout and was terminated."
    elif fatal_found:
        status = "failed"
        categories = ", ".join(fatal_detection.get("categories") or ["fatal"])
        failure_reason = f"ANSYS output contains blocking messages ({categories}); post-processing was blocked."
    elif post_export_failure:
        status = "failed"
        failure_reason = f"ANSYS post-export failed: {post_export_failure['name']} {post_export_failure['status']} - {post_export_failure['reason']}"
    elif returncode == 0:
        status = "success"
        failure_reason = None
    else:
        status = "failed"
        failure_reason = f"ANSYS exited with return code {returncode}."
    failure_category = (
        "startup_no_output_timeout"
        if startup_no_output_timeout
        else "output_stall_timeout"
        if output_stall_timeout
        else "timeout"
        if timed_out
        else ",".join(fatal_detection.get("categories") or [])
        if fatal_found
        else (post_export_failure or {}).get("name")
        if post_export_failure
        else None
    )
    audit = {
        "status": status,
        "mode": "real",
        "executed": True,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "returncode": returncode,
        "timeout_seconds": timeout_seconds,
        "configured_timeout_seconds": timeout_policy["configured_timeout_seconds"],
        "configured_timeout_minutes": timeout_policy["configured_timeout_minutes"],
        "startup_no_output_timeout_seconds": startup_timeout,
        "configured_startup_no_output_timeout_seconds": timeout_policy[
            "configured_startup_no_output_timeout_seconds"
        ],
        "output_stall_timeout_seconds": stall_timeout,
        "configured_output_stall_timeout_seconds": timeout_policy["configured_output_stall_timeout_seconds"],
        "timeout_policy": timeout_policy,
        "failure_reason": failure_reason,
        "failure_category": failure_category,
        "fatal_output_detection": fatal_detection,
        "numeric_post_macro_audit": numeric_post_audit,
        "post_export_failure": post_export_failure,
        "command_file": "ansys_command.json",
        "command_line": command.get("command_line"),
        "resources": command.get("resources", {}),
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "figure_export_status": (figure_export_audit or {}).get("status"),
        "figure_count": (figure_export_audit or {}).get("figure_count"),
        "connection_node_export_status": (connection_export_audit or {}).get("status"),
        "connection_node_export_output": (connection_export_audit or {}).get("output"),
        "figure_export_audit": figure_export_audit,
        "connection_node_export_audit": connection_export_audit,
        "post_exports_enabled": run_post_exports,
        "timeout_cleanup": timeout_cleanup,
        "job_process_cleanup": job_cleanup,
        "preflight_status": preflight["status"],
        "guard_status": guard["status"],
        "lock_cleanup_status": lock_cleanup.get("status"),
        "lock_cleanup_removed": lock_cleanup.get("removed", []),
        "confirm_user": guard["confirm_user"],
        "confirm_time": guard["confirm_time"],
        "command_hash": guard["command_hash"],
        "kept_job_directory": True,
    }
    _write_json(job_dir / "ansys_run_audit.json", audit)
    _write_final_live_status(
        job_dir,
        command=command,
        started_monotonic=started_monotonic,
        process_pid=getattr(process, "pid", None),
        status=status,
        returncode=returncode,
        failure_reason=failure_reason,
        failure_category=failure_category,
        figure_count=(figure_export_audit or {}).get("figure_count"),
        timeout_policy=timeout_policy,
        progress_callback=progress_callback,
    )
    return audit
