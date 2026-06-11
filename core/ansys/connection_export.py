from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.ansys.config import AnsysLocalConfig


OUTPUT_NAME = "LS-FORCE-NODES.LIS"
MACRO_NAME = "export_connection_nodes.mac"
REQUIREMENT_NAME = "connection_node_export_required.json"
CONNECTION_EXPORT_SOFT_TIMEOUT_SECONDS = 300
CONNECTION_EXPORT_POST_COMPLETION_EXIT_GRACE_SECONDS = 10

_COMPLETION_MARKER_RE = re.compile(r"\*{5}\s+ROUTINE\s+COMPLETED\s+\*{5}", re.IGNORECASE)
_ERROR_COUNT_RE = re.compile(r"NUMBER\s+OF\s+ERROR\s+MESSAGES\s+ENCOUNTERED\s*=\s*(\d+)", re.IGNORECASE)
_WARNING_COUNT_RE = re.compile(r"NUMBER\s+OF\s+WARNING\s+MESSAGES\s+ENCOUNTERED\s*=\s*(\d+)", re.IGNORECASE)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_text_tail(path: Path, *, max_chars: int = 40000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text if len(text) <= max_chars else text[-max_chars:]


def _detect_export_completion(job_dir: Path, output_log: Path) -> dict[str, Any]:
    text = _read_text_tail(output_log)
    has_routine = bool(_COMPLETION_MARKER_RE.search(text))
    error_counts = [int(value) for value in _ERROR_COUNT_RE.findall(text)]
    warning_counts = [int(value) for value in _WARNING_COUNT_RE.findall(text)]
    output_path = job_dir / OUTPUT_NAME
    output_exists = output_path.exists() and output_path.stat().st_size > 0
    complete = has_routine and bool(error_counts) and error_counts[-1] == 0 and output_exists
    return {
        "status": "pass" if complete else "not_detected",
        "output_exists": output_exists,
        "output_size": output_path.stat().st_size if output_exists else 0,
        "output_log": output_log.name,
        "markers": ["ROUTINE_COMPLETED"] if has_routine else [],
        "error_count": error_counts[-1] if error_counts else None,
        "warning_count": warning_counts[-1] if warning_counts else None,
        "policy": (
            "Connection-node export is accepted only when LS-FORCE-NODES.LIS exists and the MAPDL output "
            "contains ROUTINE COMPLETED with zero MAPDL errors. Launcher return code alone is not authoritative."
        ),
    }


def _kill_process_tree(pid: int | None) -> dict[str, Any]:
    if not pid:
        return {"status": "skipped", "reason": "missing_pid"}
    try:
        completed = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # pragma: no cover - defensive for OS/process failures
        return {"status": "failed", "pid": pid, "reason": str(exc)}
    return {
        "status": "success" if completed.returncode == 0 else "failed",
        "pid": pid,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _cleanup_stale_connection_outputs(job_dir: Path, output_log: Path) -> dict[str, Any]:
    removed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for path in (job_dir / OUTPUT_NAME, output_log, job_dir / "connection_node_export.err"):
        if not path.exists() or not path.is_file():
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            removed.append({"file": path.name, "size": size})
        except OSError as exc:
            skipped.append({"file": path.name, "reason": str(exc)})
    return {
        "status": "pass" if not skipped else "warning",
        "removed_count": len(removed),
        "removed": removed,
        "skipped": skipped,
        "policy": (
            "Before connection-node export reruns, stale LS-FORCE-NODES and completion logs are removed "
            "so completion-marker acceptance can only use the current export."
        ),
    }


def _requirement_allows_export(job_dir: Path) -> tuple[bool, dict[str, Any] | None]:
    requirement_path = job_dir / REQUIREMENT_NAME
    if not requirement_path.exists():
        return True, None
    try:
        payload = json.loads(requirement_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return True, {"status": "warning", "reason": f"invalid {REQUIREMENT_NAME}: {exc}"}
    return bool(payload.get("required")), payload


def _keypoints_from_model(job_dir: Path) -> list[int]:
    model_path = job_dir / "generated_model.mac"
    if not model_path.exists():
        return []
    text = model_path.read_text(encoding="utf-8", errors="replace")
    keypoints: set[int] = set()
    for match in re.finditer(r"(?im)^\s*K\s*,\s*(\d+)\s*,", text):
        keypoint = int(match.group(1))
        if 1 <= keypoint % 10 <= 9:
            keypoints.add(keypoint)

    def _int_parameter(name: str, default: int = 0) -> int:
        match = re.search(rf"(?im)^\s*{re.escape(name)}\s*=\s*(-?\d+)\b", text)
        if not match:
            return default
        return int(match.group(1))

    qiancengshu = max(0, _int_parameter("qiancengshu"))
    houcengshu = max(0, _int_parameter("houcengshu"))
    senum = max(0, _int_parameter("senum"))
    senum1 = max(0, _int_parameter("senum1"))
    kp_offset = max(0, _int_parameter("KPOFF"))
    frame_step = max(1, _int_parameter("KPFSTEP", 100))
    back_base0 = max(1500, _int_parameter("KPBKBASE", 1500))
    # Template-rendered models define qiancengshu/houcengshu.  Standard-family
    # source models often keep their original senum1/senum3 naming, where
    # senum1 is the rendered front-side layer count.  If qiancengshu/houcengshu
    # are absent, treat senum1 as the front-side count; otherwise senum1 remains
    # the back-side alias used by the generic template.
    if qiancengshu or houcengshu:
        front_layers = max(qiancengshu, senum)
        back_layers = max(houcengshu, senum1 if houcengshu else 0)
    else:
        front_layers = max(senum, senum1)
        back_layers = 0
    max_layers = max(front_layers, back_layers)

    # The reviewed S2 standard macro defines tray-arm and tray/tray-arm
    # connection keypoints by APDL expressions such as
    # K,500+10*cengshu1+2.  Export only the keypoint families that can actually
    # exist for the rendered front/back layer counts; broad numeric guessing
    # creates thousands of "undefined keypoint" warnings and can mask topology
    # mistakes with all-zero rows.
    front_bases = [500 + frame_step * frame for frame in range(3)]
    back_bases = [back_base0 + frame_step * frame for frame in range(3)]
    for base in front_bases:
        for layer in range(0, max_layers + 2):
            keypoints.add(base + layer)
        for layer in range(1, front_layers + 1):
            for suffix in (1, 2, 3, 4, 6, 7, 8, 9):
                keypoints.add(base + kp_offset + layer * 10 + suffix)
    if back_layers:
        for base in back_bases:
            for layer in range(1, back_layers + 1):
                for suffix in (1, 2, 3, 4, 6, 7, 8, 9):
                    keypoints.add(base + kp_offset + layer * 10 + suffix)
    return sorted(keypoints)


def _database_stem(job_dir: Path) -> str | None:
    for preferred in ("djs.db", "CableTrayAI_Run.db"):
        if (job_dir / preferred).exists():
            return Path(preferred).stem
    matches = sorted(job_dir.glob("*.db"))
    return matches[0].stem if matches else None


def _lcfile_lines(job_dir: Path) -> list[str]:
    lines: list[str] = []
    for number in (39, 40, 41):
        matches = sorted(job_dir.glob(f"*.l{number}"))
        if matches:
            match = matches[0]
            lines.append(f"LCFILE,{number},'{match.stem}','{match.suffix.lstrip('.')}',")
    return lines


def write_connection_node_export_macro(job_dir: Path | str) -> dict[str, Any]:
    job_dir = Path(job_dir)
    db_stem = _database_stem(job_dir)
    keypoints = _keypoints_from_model(job_dir)
    macro_path = job_dir / MACRO_NAME
    if not db_stem or not keypoints:
        payload = {
            "status": "skipped",
            "reason": "missing database or connection keypoints",
            "database_stem": db_stem,
            "keypoint_count": len(keypoints),
            "macro": str(macro_path),
        }
        (job_dir / "connection_node_export_audit.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload

    lines = [
        f"RESUME,{db_stem},db",
        "/POST1",
        *_lcfile_lines(job_dir),
        f"*DIM,KPLIST,ARRAY,{len(keypoints)}",
    ]
    lines.extend(f"KPLIST({index})={keypoint}" for index, keypoint in enumerate(keypoints, start=1))
    lines.extend(
        [
            f"*CFOPEN,{Path(OUTPUT_NAME).stem},LIS",
            "*VWRITE,'KP','CASEID','FX','FY','FZ','MX','MY','MZ'",
            "(A10,2X,A10,2X,A15,2X,A15,2X,A15,2X,A15,2X,A15,2X,A15)",
            f"*DO,I,1,{len(keypoints)},1",
            "KPVAL=KPLIST(I)",
            "*DIM,FORCES,ARRAY,3,6",
            "*DO,K,1,3,1",
            "LCASE,38+K",
            "KSEL,S,KP,,KPVAL",
            "NSLK,S",
            "*GET,NODEID,NODE,0,NUM,MAX",
            "*IF,NODEID,LT,1,THEN",
            "*DO,J,1,6,1",
            "FORCES(K,J)=0",
            "*ENDDO",
            "*ELSE",
            "NSEL,S,,,NODEID",
            "ESLN,S",
            "*GET,EID,ELEM,,NUM,MAX",
            "*IF,EID,LT,1,THEN",
            "*DO,J,1,6,1",
            "FORCES(K,J)=0",
            "*ENDDO",
            "*ELSE",
            "*GET,FORCES(K,1),ELEM,EID,EFOR,NODEID,FX",
            "*GET,FORCES(K,2),ELEM,EID,EFOR,NODEID,FY",
            "*GET,FORCES(K,3),ELEM,EID,EFOR,NODEID,FZ",
            "*GET,FORCES(K,4),ELEM,EID,EFOR,NODEID,MX",
            "*GET,FORCES(K,5),ELEM,EID,EFOR,NODEID,MY",
            "*GET,FORCES(K,6),ELEM,EID,EFOR,NODEID,MZ",
            "*ENDIF",
            "*ENDIF",
            "*ENDDO",
            "*DO,J,1,6,1",
            "UPVAL=ABS(FORCES(1,J))+ABS(FORCES(2,J))",
            "FAVAL=ABS(FORCES(1,J))+ABS(FORCES(3,J))",
            "FORCES(2,J)=UPVAL",
            "FORCES(3,J)=FAVAL",
            "*ENDDO",
            "F1=FORCES(2,1)",
            "F2=FORCES(2,2)",
            "F3=FORCES(2,3)",
            "F4=FORCES(2,4)",
            "F5=FORCES(2,5)",
            "F6=FORCES(2,6)",
            "*VWRITE,KPVAL,2,F1,F2,F3,F4,F5,F6",
            "(F10.0,2X,F10.0,2X,F15.4,2X,F15.4,2X,F15.4,2X,F15.4,2X,F15.4,2X,F15.4)",
            "F1=FORCES(3,1)",
            "F2=FORCES(3,2)",
            "F3=FORCES(3,3)",
            "F4=FORCES(3,4)",
            "F5=FORCES(3,5)",
            "F6=FORCES(3,6)",
            "*VWRITE,KPVAL,3,F1,F2,F3,F4,F5,F6",
            "(F10.0,2X,F10.0,2X,F15.4,2X,F15.4,2X,F15.4,2X,F15.4,2X,F15.4,2X,F15.4)",
            "*ENDDO",
            "*CFCLOS",
            "FINISH",
            "/EXIT,NOSAV",
        ]
    )
    macro_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    payload = {
        "status": "macro_written",
        "macro": str(macro_path),
        "output": OUTPUT_NAME,
        "database_stem": db_stem,
        "keypoints": keypoints,
        "policy": "Node-level tray-arm connection export. It preserves keypoint identity so report table mapping can use topology rather than numeric closeness.",
    }
    (job_dir / "connection_node_export_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def run_connection_node_export(job_dir: Path | str, config: AnsysLocalConfig) -> dict[str, Any]:
    job_dir = Path(job_dir)
    allowed, requirement = _requirement_allows_export(job_dir)
    if not allowed:
        payload = {
            "status": "skipped",
            "reason": "connection node export not required by report/result mapping",
            "requirement": requirement,
            "output": OUTPUT_NAME,
            "policy": "Skip expensive node-level export unless the report mapping requires LS-FORCE-NODES.LIS or derived tray-arm bolt loads.",
        }
        _write_json(job_dir / "connection_node_export_audit.json", payload)
        return payload
    macro = write_connection_node_export_macro(job_dir)
    if macro.get("status") != "macro_written":
        return macro
    output_log = job_dir / "connection_node_export.out"
    command = [
        config.ansys.executable or "ANSYS_EXECUTABLE_NOT_CONFIGURED",
        "-b",
        "-j",
        "connection_node_export",
        "-dir",
        str(job_dir.resolve()),
        "-i",
        str((job_dir / MACRO_NAME).resolve()),
        "-o",
        str(output_log.resolve()),
        "-p",
        config.ansys.product or "ansys",
        "-np",
        "1",
    ]
    stdout_path = job_dir / "connection_node_export_stdout.log"
    stderr_path = job_dir / "connection_node_export_stderr.log"
    stale_cleanup = _cleanup_stale_connection_outputs(job_dir, output_log)
    started = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    soft_timeout_reported = False
    completion_detection: dict[str, Any] = {"status": "not_detected"}
    completion_seen_at: float | None = None
    completion_cleanup: dict[str, Any] | None = None
    completed_returncode: int | None = None
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=str(job_dir),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
            )
            while True:
                returncode = process.poll()
                if returncode is not None:
                    completed_returncode = int(returncode)
                    break
                elapsed = time.monotonic() - started_monotonic
                if elapsed > CONNECTION_EXPORT_SOFT_TIMEOUT_SECONDS and not soft_timeout_reported:
                    stderr_handle.write(
                        f"\nconnection node export exceeded soft_timeout_seconds={CONNECTION_EXPORT_SOFT_TIMEOUT_SECONDS}; "
                        "continuing until MAPDL completion or operator interruption.\n"
                    )
                    stderr_handle.flush()
                    soft_timeout_reported = True
                probe = _detect_export_completion(job_dir, output_log)
                if probe.get("status") == "pass":
                    completion_detection = probe
                    if completion_seen_at is None:
                        completion_seen_at = time.monotonic()
                    elif (
                        time.monotonic() - completion_seen_at
                        >= CONNECTION_EXPORT_POST_COMPLETION_EXIT_GRACE_SECONDS
                    ):
                        completion_cleanup = {
                            "status": "completed_marker_cleanup",
                            "reason": (
                                "Connection-node export completed with LS-FORCE-NODES.LIS and zero MAPDL errors, "
                                "but the launcher remained alive after the completion grace window."
                            ),
                            "grace_seconds": CONNECTION_EXPORT_POST_COMPLETION_EXIT_GRACE_SECONDS,
                            "process_tree_cleanup": _kill_process_tree(process.pid),
                        }
                        try:
                            process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            pass
                        completed_returncode = process.poll()
                        break
                else:
                    completion_detection = probe
                time.sleep(5.0)
    except Exception as exc:
        payload = {
            **macro,
            "status": "failed",
            "returncode": None,
            "reason": str(exc),
            "soft_timeout_seconds": CONNECTION_EXPORT_SOFT_TIMEOUT_SECONDS,
            "hard_timeout_policy": "disabled",
            "output_exists": (job_dir / OUTPUT_NAME).exists(),
            "stale_connection_output_cleanup": stale_cleanup,
            "stdout_path": stdout_path.name,
            "stderr_path": stderr_path.name,
            "output_log": output_log.name,
            "completion_marker_detection": _detect_export_completion(job_dir, output_log),
        }
        _write_json(job_dir / "connection_node_export_audit.json", payload)
        return payload
    finished = datetime.now(timezone.utc)
    if completion_detection.get("status") != "pass":
        completion_detection = _detect_export_completion(job_dir, output_log)
    returncode_success = completed_returncode == 0 or completion_detection.get("status") == "pass"
    payload = {
        **macro,
        "status": "success" if returncode_success and (job_dir / OUTPUT_NAME).exists() else "failed",
        "returncode": completed_returncode,
        "returncode_accepted_by_completion_marker": bool(
            completed_returncode not in (None, 0) and completion_detection.get("status") == "pass"
        ),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": (finished - started).total_seconds(),
        "soft_timeout_seconds": CONNECTION_EXPORT_SOFT_TIMEOUT_SECONDS,
        "hard_timeout_policy": "disabled",
        "soft_timeout_reported": soft_timeout_reported,
        "output_exists": (job_dir / OUTPUT_NAME).exists(),
        "completion_marker_detection": completion_detection,
        "completion_marker_cleanup": completion_cleanup,
        "stale_connection_output_cleanup": stale_cleanup,
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "output_log": output_log.name,
    }
    if payload["status"] != "success":
        payload["reason"] = "connection node export did not produce a valid LS-FORCE-NODES.LIS completion marker"
    _write_json(job_dir / "connection_node_export_audit.json", payload)
    return payload
