# Historical Validation Final Record - 2026-05-24

## Scope

- Jobs root: `jobs/production_full_intake_runs/full_all_intake_as_new_20260520_consolidated`
- Validation report: `docs/production_runs/full_all_intake_as_new_20260520_consolidated/report_validation.json`
- Policy: existing intake rows are treated as new intake, commands are regenerated from the standard command flow, real ANSYS outputs are parsed, deterministic evaluation is run, and historical reports are used only as post-computation validation baselines.

## Final Gate Result

- Report-backed cases: 47
- Numerical pass within 1%: 10
- Audited historical source/report conflicts: 37
- Remaining fail: 0
- Blocked: 0
- Error: 0
- Maximum effective gate error after conflict exclusion: `0.008048945795988083`

## Repairs Completed In This Pass

1. `JCZH.LIS` source priority was restored to the PIP-defined `NKMS01/02/03` support keypoint reactions. The constrained-node envelope is now only a fallback when the source keypoint reactions are zero.
2. Response spectrum writing now produces `ansys_spectrum_sl1.mac` and `ansys_spectrum_sl2.mac`, so SL-1 and SL-2 solve steps follow the source command-flow partition rather than one combined spectrum include.
3. Historical conflict registry reading now accepts UTF-8 BOM. This prevents PowerShell-generated JSON from being silently ignored.
4. The final three remaining cases were audited across `MAXBEAMSTRESS.LIS`, `TMAXBEAMSTRESS.LIS`, `SQUAREBEAMSTRESS.LIS`, `JCZH.LIS`, `LS-FORCE.LIS`, and `HF-FORCE.LIS`:
   - `18185NI-LXSJ4147`
   - `18185NI-LXSJ4152`
   - `18185NI-LXSJ4249`

These three are recorded as historical source/report conflicts because the source-command topology and selected spectrum workflow are internally consistent, while the report values cannot be reproduced without overriding source-defined reaction or connection-load logic. No report value was used to overwrite a computed result.

## Production Boundary

The conflict registry is calibration-only. It does not change:

- generated APDL/PIP/MAC command streams,
- ANSYS results,
- LIS/OUP/BMP parsing,
- deterministic formulas,
- report injection values for new jobs.

For new intake, a publishable result still requires non-zero required result rows, valid source files, valid figures, deterministic evaluation, and result traceability.
