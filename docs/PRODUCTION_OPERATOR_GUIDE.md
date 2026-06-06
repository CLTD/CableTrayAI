# Production Operator Guide

1. Create or choose a job.
2. Confirm spectrum configuration.
3. Render APDL and generate `run_all.mac`.
4. Run preflight.
5. Review `ansys_command.json` and `run_ansys.ps1`.
6. Run real ANSYS only with explicit confirmation.
7. Parse real outputs or import a real output directory.
8. Check `result_validation.json`; all-zero, missing figures, or unknown-node outputs block publication.
9. Run Excel authoritative evaluation if formulas remain unconfirmed.
10. Generate report and audit.
11. Compare against manual baseline when available.

## LLM-Assisted Orchestration

The large model may parse intake intent and propose a command plan, but it must not directly write executable APDL/PIP/MAC.
CableTrayAI now writes `llm_intake_intent.json`, `command_plan.json`, and `command_plan_audit.json` before rendering commands.
The final `generated_model.mac`, `generated_solve.mac`, and `generated_post.mac` are still compiled from audited standard sources.

For DeepSeek or Qwen intranet services, configure an OpenAI-compatible `/v1` endpoint in `config/ai.local.toml`.
Keep the API key in an environment variable such as `DEEPSEEK_API_KEY`; do not store keys in the repository or deployment package.

See `docs/POST_PROCESSING_VALIDITY_POLICY.md` for the current post-processing gate.

Production report injection is governed by `docs/REPORT_INJECTION_ACCEPTANCE_GATE.md`.

The initial unit intranet deployment plan is `docs/INTRANET_DEPLOYMENT_PLAN.md`.
For the first deployment, run the web/API service on `10.102.15.203` and open `http://10.102.15.203:8000/` from other computers.
