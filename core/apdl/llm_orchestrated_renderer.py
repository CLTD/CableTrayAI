from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.ai.engineering_intent import propose_intake_intent
from core.apdl.command_plan import audit_command_plan, build_command_plan, write_command_plan
from core.apdl.intake_standard_family_renderer import render_intake_standard_family_commands
from core.apdl.standard_command_renderer import render_standard_command_package


def render_llm_orchestrated_command_package(
    job_dir: Path | str,
    *,
    source_root: Path | str = Path("source_materials/model_commands"),
    jobs_dir: Path | str | None = None,
    template_dir: Path | str = Path("templates/apdl"),
    package_id: str | None = None,
    use_model: bool = True,
    solve_strategy: str = "template",
) -> dict[str, Any]:
    job_dir = Path(job_dir)
    input_path = job_dir / "input.json"
    if not input_path.exists():
        raise FileNotFoundError(f"Missing job input: {input_path}")

    intent = propose_intake_intent(input_path, job_dir=job_dir, use_model=use_model)
    plan = build_command_plan(input_path, llm_intent=intent, package_id=package_id)
    plan_audit = write_command_plan(job_dir, plan)
    if plan_audit["status"] != "pass":
        payload = {
            "status": "fail",
            "stage": "command_plan_audit",
            "llm_intake_intent": intent,
            "command_plan": plan,
            "command_plan_audit": plan_audit,
            "policy": "Rendering is blocked when the LLM-influenced command plan fails audit.",
        }
        (job_dir / "llm_generation_audit.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return payload

    if package_id:
        render_result = render_standard_command_package(
            job_dir,
            source_root=source_root,
            package_id=package_id,
        )
        compiler = "standard_command_package"
    else:
        render_result = render_intake_standard_family_commands(
            job_dir.name,
            input_path,
            jobs_dir=Path(jobs_dir) if jobs_dir else job_dir.parent,
            template_dir=template_dir,
            source_root=source_root,
            solve_strategy=solve_strategy,
        )
        compiler = "intake_standard_family"
    final_plan_audit = audit_command_plan(plan)
    status = "fail" if final_plan_audit["status"] != "pass" else render_result.get("status", "pass")
    payload = {
        "status": status,
        "stage": "rendered_standard_commands",
        "llm_intake_intent": {
            "schema_version": intent.get("schema_version"),
            "source_type": intent.get("source_type"),
            "llm_status": intent.get("llm_status"),
            "authority": intent.get("authority"),
            "model": intent.get("model"),
        },
        "command_plan_file": "command_plan.json",
        "command_plan_audit": final_plan_audit,
        "render_result": render_result,
        "compiler": compiler,
        "rendered_files": ["generated_model.mac", "generated_solve.mac", "generated_post.mac"],
        "policy": (
            "The model may propose intake intent and command-plan parameters. "
            "Executable APDL/PIP/MAC is still compiled from audited standard source streams."
        ),
    }
    (job_dir / "llm_generation_audit.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload
