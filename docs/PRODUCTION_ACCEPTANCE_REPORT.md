# Production Acceptance Report

Acceptance conditions:

- pytest passes.
- collected test count is at least 120.
- hardcoded sample token scan has no matches.
- `source_materials` has no modifications.
- `run_all.mac` is used by ANSYS commands.
- real ANSYS is either attempted with guard approval or the blocker is explicitly recorded.
- formal conclusions are not based on mock or dry-run data.

Current run should be recorded by `scripts/production_final_self_check.ps1`.

## Current Acceptance Direction

The production gate now treats historical reports as calibration and conflict-discovery references, not as the sole authority. The authority order for new production jobs is:

1. audited standard command-flow generation,
2. deterministic specification formulas,
3. job-local Excel authoritative evaluation for formulas that are not fully locked in Python,
4. real ANSYS or real imported output,
5. historical report comparison for calibration, regression checks, and conflict discovery.

Audited historical report conflicts are recorded in `data/calibration/report_baseline_conflicts.json`. They are excluded from the historical numerical precision gate only after evidence is recorded, and they never change new-intake ANSYS output or evaluation results.

## Latest Guarded Smoke Result

On 2026-05-17, the representative intake-as-new report-level batch passed for:

- `18185NI-LXSJ4120`
- `18185NI-LXSJ4126`
- `18185NI-LXSJ4128`
- `18185NI-LXSJ4225`
- `18185NI-LXSJ4249`

Result: `5/5` passed, with max effective gate error `0.004990731571029472`.
