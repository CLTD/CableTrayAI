from __future__ import annotations

import json
from pathlib import Path

from core.ansys.config import AnsysLocalConfig, config_to_dict
from core.ansys.master_macro import MASTER_MACRO_NAME, build_run_all_macro, resolve_master_job_name
from core.ansys.resources import resolve_ansys_nproc
from core.apdl.modal_policy import modal_mode_count_from_job_dir


DEFAULT_HIGH_MODAL_NPROC_CAP_THRESHOLD = 300


def _static_method_job(job_dir: Path) -> bool:
    input_path = job_dir / "input.json"
    if not input_path.exists():
        return False
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    return str((metadata or {}).get("analysis_method") or "").strip().lower() == "static"


def build_ansys_command(config: AnsysLocalConfig, job_dir: Path | str) -> dict:
    job_dir = Path(job_dir).resolve()
    ansys = config.ansys
    executable = ansys.executable or "ANSYS_EXECUTABLE_NOT_CONFIGURED"
    build_run_all_macro(job_dir)
    job_name = resolve_master_job_name(job_dir)
    input_file = job_dir / MASTER_MACRO_NAME
    output_file = job_dir / "ansys.out"
    command: list[str] = [
        executable,
        "-b",
        "-j",
        job_name,
        "-i",
        str(input_file),
        "-o",
        str(output_file),
        "-dir",
        str(job_dir),
    ]
    if ansys.product:
        command.extend(["-p", ansys.product])
    resolved_nproc = resolve_ansys_nproc(ansys.nproc, ansys.nproc_percent)
    requested_nproc = resolved_nproc.nproc
    static_method = _static_method_job(job_dir)
    modal_mode_count = None if static_method else modal_mode_count_from_job_dir(job_dir)
    effective_nproc = requested_nproc
    nproc_source = resolved_nproc.source
    high_modal_cap_applied = False
    high_modal_cap = ansys.high_modal_nproc_cap
    high_modal_threshold = ansys.high_modal_nproc_cap_threshold or DEFAULT_HIGH_MODAL_NPROC_CAP_THRESHOLD
    if (
        high_modal_cap
        and high_modal_cap > 0
        and modal_mode_count is not None
        and modal_mode_count >= high_modal_threshold
        and (effective_nproc is None or effective_nproc > high_modal_cap)
    ):
        effective_nproc = high_modal_cap
        nproc_source = f"{nproc_source}+explicit_high_modal_cap"
        high_modal_cap_applied = True
    if effective_nproc:
        command.extend(["-np", str(effective_nproc)])
    if ansys.memory:
        command.extend(["-m", str(ansys.memory)])
    command.extend(ansys.extra_args)

    payload = {
        "mode": config.runner.mode,
        "command": command,
        "command_line": " ".join(f'"{part}"' if " " in part else part for part in command),
        "job_dir": str(job_dir),
        "ansys_job_name": job_name,
        "input_file": str(input_file),
        "output_file": str(output_file),
        "config": config_to_dict(config),
        "resources": {
            "nproc": effective_nproc,
            "requested_nproc_before_modal_cap": requested_nproc,
            "nproc_source": nproc_source,
            "nproc_percent": resolved_nproc.nproc_percent,
            "logical_processors": resolved_nproc.logical_processors,
            "modal_mode_count": modal_mode_count,
            "modal_mode_count_status": "not_required_static_method" if static_method else "required_for_modal_or_spectrum_method",
            "high_modal_nproc_cap_threshold": high_modal_threshold,
            "high_modal_nproc_cap": high_modal_cap,
            "high_modal_nproc_cap_applied": high_modal_cap_applied,
        },
    }
    (job_dir / "ansys_command.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def write_run_script(command_payload: dict, job_dir: Path | str) -> Path:
    job_dir = Path(job_dir)
    command_literal = "@(\n" + "\n".join(f"  {json.dumps(part)}" for part in command_payload["command"]) + "\n)"
    script = "\n".join(
        [
            '$ErrorActionPreference = "Stop"',
            "$Command = " + command_literal,
            "Write-Host 'ANSYS command:'",
            'Write-Host ($Command -join " ")',
            "& $Command[0] $Command[1..($Command.Count-1)]",
            "",
        ]
    )
    path = job_dir / "run_ansys.ps1"
    path.write_text(script, encoding="utf-8", newline="\n")
    return path
