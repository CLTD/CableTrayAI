# Stage 4 Real Run Guard Policy

Stage 4 still defaults to no real ANSYS execution.

Real execution is allowed only when all guard checks pass:

1. `config/ansys.local.toml` exists.
2. `runner.mode = "real"`.
3. `ansys.executable` points to an existing executable.
4. `jobs/<job_id>/ansys_preflight.json` has no `fail` checks.
5. `jobs/<job_id>/job_state.json` is not `running` or `failed`.
6. `input.json` has `spectrum_config_confirmed = true` either at the root or under `metadata`.
7. The caller supplies an explicit confirmation flag.
8. The command hash is recorded before execution.

PowerShell confirmation flag:

```powershell
scripts\run_ansys_real_once.ps1 -JobId <job_id> -IUnderstandThisWillRunANSYS
```

API confirmation field:

```json
{
  "confirm_real_run": true,
  "confirm_user": "operator-name"
}
```

If any check fails, ANSYS is not started. The guard writes:

- `real_run_guard.json`
- `ansys_run_audit.json`

The rejected audit includes `executed = false` and the rejection reasons.
