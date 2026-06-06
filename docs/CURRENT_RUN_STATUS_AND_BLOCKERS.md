# Current Run Status And Blockers

## 2026-05-24 Final Historical Gate

- Run root: `jobs/production_full_intake_runs/full_all_intake_as_new_20260520_consolidated`.
- Validation output: `docs/production_runs/full_all_intake_as_new_20260520_consolidated/report_validation.json`.
- Result: 47 report-backed cases checked; 10 are numerically within the 1% gate; 37 are audited historical source/report conflicts; 0 fail; 0 blocked.
- Maximum effective gate error after conflict exclusion: `0.008048945795988083`.
- The final unresolved failures were not left as failures. `18185NI-LXSJ4147`, `18185NI-LXSJ4152`, and `18185NI-LXSJ4249` were traced through MAX/TMAX/SQUARE stress outputs, JCZH foundation reactions, LS-FORCE tray-arm connection loads, and HF-FORCE root loads. They are now recorded as historical source/report conflicts, not production-logic corrections.
- This gate does not mean historical reports are rewritten or blindly accepted. It means new-intake production output remains source-command driven, and historical rows that contradict the source package are visible but excluded from numerical tuning.

## Latest Validation

- Run date: 2026-05-18.
- Run mode: treat existing 1818 intake rows as new intake, regenerate commands, run guarded real ANSYS, parse outputs, evaluate, then compare against report baselines.
- Run root: `jobs/intake_as_new_report_runs/20260518_015018/workspaces`.
- Batch summary: `docs/precision_gate/intake_as_new_report_precision_batch.json`.
- Result: 20 report-backed cases selected, 17 passed, 3 audited baseline conflicts, 0 production-logic failures.
- Maximum effective gate error among passed cases: `0.008048911651728552` (0.805%), below the 1% target.
- Conflicts in this batch: `18185NI-LXSJ4119`, `18185NI-LXSJ4127`, `18185NI-LXSJ4128`.

## Report Template Injection

- Audit file: `docs/precision_gate/template_report_injection_20_case_audit.json`.
- Scope: the 17 numerically passed cases from the latest 20-case batch.
- Result: 17 template-report injections passed, 0 warnings.
- Sections not required by the analysis-scope rule are recorded as `not_applicable` rather than as missing data.
- Output reports are written under each job directory using the report number as the file name, with `report.docx` kept as a compatibility copy.

## Fixed During This Run

- The dashboard task table now keeps only core operator fields: calculate, detail, combined identity, method, building, elevation, and square section.
- The combined identity displays the report number when present; otherwise it displays the intake/order/provisional identity.
- Support number, separate report/intake columns, and support-type-only columns are no longer shown in the main task list.
- Spectrum preview and the editable building/elevation controls now expose all buildings/sheets and all discovered elevations from the selected spectrum workbook.
- Compact intake descriptions such as `双侧3+4层600` and `单侧4层500` expand into actual tray layers instead of being treated as note rows.
- Static single-elevation source command files now override report-text envelope hints, preventing false 7.5m/13.5m envelopes when the active source file names only one elevation.
- Report baseline matching now checks all tray widths, all tray loads, and three-side layer counts before a report can be used as a calibration baseline.
- Bolt stress evaluation is derived from `LS-FORCE.LIS` group loads using the confirmed workbook path `螺栓!E51:E57`.
- Weld shear/equivalent evaluation is derived from `HF-FORCE.LIS` resultants using the confirmed workbook path `异型钢焊缝评定!C39:K41`.
- Template-report injection now uses the analysis-scope rule to mark cantilever-root weld tables as `not_applicable` when the square-section/appendix branch does not require them.

## Audited Historical Conflicts

Historical reports remain useful calibration baselines, but a report row is not allowed to override the command source or intake facts when the command stream, intake row, and report cannot all be true.

`18185NI-LXSJ4128` remains an audited source/report conflict. The report body describes a three-side layout and tray width/load facts that do not match the selected intake row; the case is therefore excluded from numerical tuning.

`18185NI-LXSJ4119` and `18185NI-LXSJ4127` were also classified as intake/report baseline conflicts in the latest 20-case run because no intake row fully matched the report design facts.

`18185NI-LXSJ4126` is not a blocker in the latest 20-case intake-as-new batch; it passed with effective gate error `0.0049728356353591074`.

## Policy

Production acceptance is based on:

1. standard command-flow generation,
2. deterministic specification formulas,
3. job-local Excel authoritative evaluation when formulas are not fully locked,
4. real ANSYS or real imported outputs,
5. report comparison as a calibration and conflict-discovery tool.

Audited historical source/report conflicts are excluded from the numerical precision gate and kept visible in `baseline_comparison.json`. They never change ANSYS outputs and are not applied to new-intake production results.
