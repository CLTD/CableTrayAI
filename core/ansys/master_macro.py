from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MASTER_MACRO_NAME = "run_all.mac"
REQUIRED_MACROS = ["generated_model.mac", "generated_solve.mac", "generated_post.mac"]
DEFAULT_JOB_NAME = "CableTrayAI_Run"
LEGACY_MCOM_JOB_NAME = "djs"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def macro_call_line(macro_name: str) -> str:
    return f"/INPUT,{Path(macro_name).stem},mac"


def resolve_master_job_name(job_dir: Path | str) -> str:
    job_dir = Path(job_dir)
    solve_path = job_dir / "generated_solve.mac"
    if solve_path.exists():
        text = solve_path.read_text(encoding="utf-8", errors="replace").lower()
        if "djs" in text and "mcom" in text:
            return LEGACY_MCOM_JOB_NAME
    return DEFAULT_JOB_NAME


def build_run_all_macro(job_dir: Path | str, *, output_name: str = MASTER_MACRO_NAME) -> dict[str, Any]:
    job_dir = Path(job_dir)
    missing = [name for name in REQUIRED_MACROS if not (job_dir / name).exists()]
    job_name = resolve_master_job_name(job_dir)
    lines = [
        "! CableTrayAI production master macro",
        "! This file is the only supported real ANSYS batch entrypoint.",
        f"/FILNAME,{job_name},1",
    ]
    for macro_name in REQUIRED_MACROS:
        lines.append(f"! Begin {macro_name}")
        lines.append(macro_call_line(macro_name))
        lines.append(f"! End {macro_name}")
    lines.extend(["FINISH", "/EXIT,NOSAVE", ""])

    output_path = job_dir / output_name
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    audit = {
        "status": "fail" if missing else "pass",
        "master_macro": output_path.name,
        "ansys_job_name": job_name,
        "required_macros": REQUIRED_MACROS,
        "missing_macros": missing,
        "entrypoint_policy": "ANSYS batch input must be run_all.mac for real and dry-run command generation.",
        "job_name_policy": "Use the legacy djs job name when source solve commands request djs.mcom; otherwise use the CableTrayAI job name.",
    }
    _write_json(job_dir / "master_macro_audit.json", audit)
    return audit


def validate_run_all_macro(job_dir: Path | str, *, master_name: str = MASTER_MACRO_NAME) -> dict[str, Any]:
    job_dir = Path(job_dir)
    path = job_dir / master_name
    checks: list[dict[str, Any]] = []
    if not path.exists():
        checks.append({"check_id": "run_all_exists", "status": "fail", "message": f"{master_name} is missing"})
        return {"status": "fail", "checks": checks}

    text = path.read_text(encoding="utf-8", errors="replace")
    checks.append({"check_id": "run_all_exists", "status": "pass", "message": f"{master_name} exists"})
    positions: list[int] = []
    for macro_name in REQUIRED_MACROS:
        line = macro_call_line(macro_name)
        position = text.lower().find(line.lower())
        positions.append(position)
        checks.append(
            {
                "check_id": f"calls_{macro_name}",
                "status": "pass" if position >= 0 else "fail",
                "message": f"{master_name} calls {macro_name}",
                "evidence": line,
            }
        )
    ordered = all(position >= 0 for position in positions) and positions == sorted(positions)
    checks.append(
        {
            "check_id": "run_all_order",
            "status": "pass" if ordered else "fail",
            "message": "run_all.mac calls model, solve, and post macros in order",
            "evidence": positions,
        }
    )
    return {"status": "fail" if any(check["status"] == "fail" for check in checks) else "pass", "checks": checks}


def command_uses_master_macro(command_payload: dict[str, Any]) -> bool:
    input_file = str(command_payload.get("input_file") or "")
    if input_file.lower().endswith(MASTER_MACRO_NAME.lower()):
        return True
    command = [str(part) for part in command_payload.get("command", [])]
    for index, part in enumerate(command):
        if part.lower() == "-i" and index + 1 < len(command):
            return command[index + 1].lower().endswith(MASTER_MACRO_NAME.lower())
    return False
