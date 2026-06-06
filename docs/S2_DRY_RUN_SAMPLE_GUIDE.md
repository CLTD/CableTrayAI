# S2 Dry-Run Sample Guide

Stage 3 creates a dry-run package at:

```text
jobs/s2_dry_run_sample/
```

The package contains:

- `input.json`
- `generated_model.mac`
- `generated_solve.mac`
- `generated_post.mac`
- `ansys_spectrum.mac`
- `sections/*.SECT`
- `ansys_command.json`
- `run_ansys.ps1`
- `ansys_preflight.json`
- `ansys_run_audit.json`

## Build

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_s2_sample_job.ps1
```

## Dry-Run Check

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_ansys_dry_run.ps1 -JobDir jobs/s2_dry_run_sample
```

This does not call ANSYS. It only builds the command, run script and preflight report.

## Switching To Real

Manual steps before real execution:

1. Create `config/ansys.local.toml` from `config/ansys.local.example.toml`.
2. Set `runner.mode = "real"`.
3. Set `ansys.executable` to the actual local executable.
4. Review `ansys_preflight.json` and fix all `fail` items.
5. Confirm spectrum source and formula TODO items.
6. Explicitly run `scripts/run_ansys_real.ps1`.

No code path calls real ANSYS by default.
