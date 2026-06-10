from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from core.ansys.config import AnsysLocalConfig


OUTPUT_NAME = "LS-FORCE-NODES.LIS"
MACRO_NAME = "export_connection_nodes.mac"
REQUIREMENT_NAME = "connection_node_export_required.json"


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
        (job_dir / "connection_node_export_audit.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
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
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_handle, stderr_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as stderr_handle:
            completed = subprocess.run(
                command,
                cwd=str(job_dir),
                stdout=stdout_handle,
                stderr=stderr_handle,
                text=True,
                timeout=300,
                check=False,
            )
    except subprocess.TimeoutExpired:
        with stderr_path.open("a", encoding="utf-8", errors="replace") as stderr_handle:
            stderr_handle.write("\nconnection node export exceeded timeout_seconds=300\n")
        payload = {
            **macro,
            "status": "failed",
            "returncode": None,
            "reason": "connection node export exceeded timeout_seconds=300",
            "timeout_seconds": 300,
            "output_exists": (job_dir / OUTPUT_NAME).exists(),
            "stdout_path": stdout_path.name,
            "stderr_path": stderr_path.name,
            "output_log": output_log.name,
        }
        (job_dir / "connection_node_export_audit.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload
    payload = {
        **macro,
        "status": "success" if completed.returncode == 0 and (job_dir / OUTPUT_NAME).exists() else "failed",
        "returncode": completed.returncode,
        "output_exists": (job_dir / OUTPUT_NAME).exists(),
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "output_log": output_log.name,
    }
    (job_dir / "connection_node_export_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
