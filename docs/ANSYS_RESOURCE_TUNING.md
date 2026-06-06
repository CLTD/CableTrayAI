# ANSYS Resource Tuning

The workstation currently has enough CPU resources to run MAPDL with more than the single-core/default setting.

Policy:

- Detect logical processors from Windows.
- Store a percentage in configuration, not a machine-specific fixed core count.
- Default to `nproc_percent = 0.5`, so each deployment machine computes its own `-np` from 50% of logical processors.
- Current response-spectrum jobs should not be forced to one core by default. The command builder uses the configured percentage first, records the actual `-np`, and only applies a high-modal cap when `high_modal_nproc_cap` is explicitly set in local config.
- If MAPDL starts with no output, or writes a small amount and then stops updating files, the one-click flow terminates that attempt and retries with safer core counts from `startup_retry_nproc`.
- Modal solve count is separately bounded for the first production solve: very large historical source counts are not copied into new-intake first runs, so slow runs should not be caused by accidental `MT=887` style commands.
- MT coverage is adaptive during one-click calculation: run with the current bounded MT, parse `Mode.oup`, and only if the 50 Hz coverage gate fails, rewrite `generated_solve.mac` to the next reviewed value in `40 -> 60 -> 80 -> 100 -> 120` and rerun. The first passing value is kept so the last modal frequency stays close to the 50 Hz requirement instead of blindly over-solving.
- Keep `nproc = <fixed>` as an explicit local override only when the ANSYS license or workstation requires it.
- Do not run multiple real ANSYS jobs concurrently unless the operator explicitly chooses that later.

For the current workstation, `scripts/tune_ansys_resources.ps1` recommends:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tune_ansys_resources.ps1
```

This updates only `config/ansys.local.toml`:

- `nproc_percent = 0.5`,
- effective `-np` is computed at run time from the current machine,
- `memory = "8192"`,
- `startup_no_output_timeout_seconds = 180`,
- `output_stall_timeout_seconds = 600`,
- `startup_retry_nproc = [4, 2, 1]`,
- ANSYS is not executed by the tuning script.

For a proven workstation/license combination, raise the percentage in small steps only after validation:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tune_ansys_resources.ps1 -NprocPercent 0.10
```

