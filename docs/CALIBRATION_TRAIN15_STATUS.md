# Train-15 and Hold-Out-20 Real ANSYS Calibration Status

Status: `pass`

Commands executed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_real_precision_batch.ps1 -Dataset train -Limit 15 -Nproc 1
powershell -ExecutionPolicy Bypass -File scripts\run_real_precision_batch.ps1 -Dataset validation -Limit 20 -Nproc 1
```

## Result

- Train set: `15/15` case-level runs passed the 1% report comparison gate.
- Hold-out set: `20/20` case-level runs passed the 1% report comparison gate.
- `docs/precision_gate/real_precision_batch_train.json`: `status = pass`, `case_count = 15`.
- `docs/precision_gate/real_precision_batch_validation.json`: `status = pass`, `case_count = 20`.
- Largest train gate error: `0.00952384167915095` on `18185NI-LXSJ4123`.
- Largest hold-out gate error: `0.0049659317969498445` on `18185NI-LXSJ4154`.

## Mapping Scope

The gate compares report table fields by deterministic source mapping, not by nearest value:

- support square steel stress table: `SQUAREBEAMSTRESS.LIS`, derived from the standard `MAXBEAMSTRESS` export and narrowed by section 1.
- support cantilever arm and cantilever root weld table: `TMAXBEAMSTRESS.LIS`.
- root weld equivalent stress: `TMAXBEAMSTRESS.LIS` with the report coefficient `0.526`.
- support foundation loads: `JCZH.LIS`, three cases, fields `FX/FY/FZ/MX/MY/MZ`.
- tray-arm connection bolt loads: `LS-FORCE.LIS`, two seismic cases, fields `FX/FY/FZ/MX/MY/MZ`.
- modal frequencies: `Mode.oup`.

Combination rows are now included:

- tension + bending and compression + bending use report allowable value `1.0`.
- weld combination rows compare the ratio-sum values shown in the report.

## Source Conflict Resolutions

Two historical source/report conflicts are resolved through `data/calibration/source_conflict_resolutions.json`.

- `18185NI-LXSJ4123`: the source static command used SL-1 Z coefficient `0.409`, while all mapped report result rows match a command using `0.378`. The calibration command copy is patched by exact match and the job writes `source_conflict_resolution_audit.json`.
- `18185NI-LXSJ4249`: the active solve command and its same-directory `.bak` disagree on `paoy`. The report result table matches `.bak` value `paoy=1*0.231*9.81`; the calibration command copy is patched by exact match and audited.

These patches are calibration-only report reproduction records. They do not modify `source_materials` and are not silent defaults for new intake jobs.

## Runtime Policy

- Calibration uses `-np 1` for repeatable MAPDL comparisons.
- Production runs may still use percentage-based core selection.
- Existing source commands that read `djs.mcom` run with ANSYS job name `djs`; other jobs use the CableTrayAI job name.
- Each case-level run writes its own job directory when the same report appears more than once, for example `18185NI-LXSJ4149__case_152`.
