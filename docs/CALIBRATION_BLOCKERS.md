# Calibration Blockers

Status: `no active precision blocker after 2026-05-15 real-run gate`

## Current Gate Result

The current calibration gate uses real ANSYS, generated source command copies, deterministic LIS/OUP/BMP parsing, and report-table comparison.

- Train case-level gate: `15/15` passed within 1%.
- Hold-out case-level gate: `20/20` passed within 1%.
- `source_materials`: unchanged.
- Hardcoded sample token scan under `core`, `apps`, and `templates`: no matches.
- Full pytest: passed.

## Resolved Blockers

- `18185NI-LXSJ4123`: resolved by audited calibration-only source-conflict patch for the SL-1 static Z acceleration in the generated command copy.
- `18185NI-LXSJ4249`: resolved by audited calibration-only source-conflict patch using the same-directory `.bak` solve command value for `paoy`.
- `MAXBEAMSTRESS.LIS` / `TMAXBEAMSTRESS.LIS` mapping: resolved by deterministic report-section mapping. The square support table uses `SQUAREBEAMSTRESS.LIS`, while cantilever arm and root weld tables use `TMAXBEAMSTRESS.LIS`.
- `LS-FORCE.LIS` tray-arm connection loads: resolved with report-table order mapping for `FX/FY/FZ/MX/MY/MZ`.
- tension-bending and compression-bending rows: resolved with report allowable `1.0`.

## Remaining Human Review Items

The following are not active blockers for the reproduced reports, but must be reviewed before treating historical report text as an authoritative spectrum source for new work:

- `18185NI-LXSJ4123` contains a report spectrum summary value that conflicts with the reported result tables.
- Calibration source-conflict patches are limited to named historical reports and must not become silent defaults for new intake jobs.
- Formula TODOs that are still not confirmed by Excel or source references must continue to block final production pass decisions outside the calibrated report comparison path.

See `docs/RESULT_TABLE_MAPPING_POLICY.md` and `docs/CALIBRATION_TRAIN15_STATUS.md`.
