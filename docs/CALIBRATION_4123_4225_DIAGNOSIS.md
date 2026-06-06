# Calibration Diagnosis 4123 / 4249 / 4225

Status: `pass with audited historical report/source conflicts separated from production logic`

## Material And Section Policy

- Intake column I / 埋板 is treated as the square steel section size.
- If column I is blank, the one-click workflow must run candidate square-tube `*.SECT` files through real ANSYS and select the feasible section with `controlling_ratio < 1.0` closest to `1.0`. A candidate at exactly `1.0` is not accepted.
- Non-steel-platform support members use Q355 allowables where applicable.
- Steel-platform square support remains conservative with Q235 allowables where the square tube contacts the steel platform.

## 18185NI-LXSJ4123

Original failure:

- SL-1 upset stress and load rows were high by about `2.5%` to `9.1%`.
- The failures followed the source command line:

```apdl
ACEL,1.5*9.81*0.378,1.5*9.81*0.378,1.5*9.81*0.409
```

Controlled diagnostic:

```apdl
ACEL,1.5*9.81*0.378,1.5*9.81*0.378,1.5*9.81*0.378
```

Diagnostic result:

- Real ANSYS status: `success`.
- Replacing the SL-1 static Z coefficient with the horizontal coefficient reproduced the historical report.
- This diagnostic is **not** used for production command generation.

Interpretation:

- This is not a parser nearest-value issue.
- This is not a material allowable issue.
- The report spectrum summary lists vertical SL-1 as `0.409`, but the report result tables were produced by a command equivalent to using `0.378` for the static Z acceleration.
- The old exact-match correction in `data/calibration/source_conflict_resolutions.json` is disabled for 4123.
- The affected report rows are recorded in `data/calibration/report_baseline_conflicts.json`, so calibration keeps the conflict visible without altering generated commands.
- Production/new-intake static-method runs use the selected spectrum workbook coefficients and source-traceable `ACEL` lines.

## 18185NI-LXSJ4249

Original failure:

- `JCZH.LIS` and `LS-FORCE.LIS` had three SL-1 load discrepancies, up to about `3.85%`.
- A diagnostic that removed `LCOPER,SRSS,92` made the result much worse, so over-including the response spectrum was ruled out.
- Per-node debug exports showed the report values did not exist as alternate selected nodes, so the issue was not max-selection or parser selection.

Source conflict found:

- Active source: `paoy=1*0.259*9.81`.
- Same-directory backup source: `paoy=1*0.231*9.81`.

Controlled diagnostic:

- Replacing only `paoy` with the backup source value reproduced the report.

Result:

- Real ANSYS status: `success`.
- Report comparison: `pass`.
- Compared fields: `32`.
- Failure count: `0`.
- Max gate error: `0.00012265856543387351`.

Interpretation:

- This is a source-command conflict between active and `.bak` solve commands.
- The calibration command copy applies the exact source-ref replacement and records it in `source_conflict_resolution_audit.json`.

## 18185NI-LXSJ4225

- Comparison status: `pass`.
- Compared fields after mapping expansion: `118`.
- Failure count: `0`.
- Max gate error: `0.004699500410017031`.

4225 is retained as a passing static-method reference case for the support stress, foundation load, tray-arm connection load, combination-ratio, and weld-equivalent-stress mapping.

## Current Gate

- Train set: `15/15` case-level real ANSYS runs passed.
- Hold-out set: `20/20` case-level real ANSYS runs passed.
- Report-table mapping now includes square support, cantilever arm, root weld, weld equivalent, tension-bending and compression-bending combinations, foundation loads, tray-arm connection loads, bolt stress ratios, modal frequencies, and figures where available.
