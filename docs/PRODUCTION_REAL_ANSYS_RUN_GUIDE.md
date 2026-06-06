# Production Real ANSYS Run Guide

Real ANSYS execution is intentionally gated.

Required before running:

- `config/ansys.local.toml` exists.
- `runner.mode = "real"`.
- `ansys.executable` exists.
- `run_all.mac` exists and calls model, solve, post macros in order.
- `ansys_preflight.json` has no fail checks.
- spectrum config is confirmed.
- user passes the explicit real-run confirmation flag.

Command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\production_real_run.ps1 -JobId <job_id> -IUnderstandThisWillRunANSYS
```

If ANSYS fails, the pipeline records the failure and does not switch to mock.
