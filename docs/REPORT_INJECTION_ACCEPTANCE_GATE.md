# Report Injection Acceptance Gate

## Purpose

Report injection is a production deliverable, not a display-only feature. A job can publish a formal Word report only when the injected report remains consistent with the approved template and every injected value is traceable to calculation output.

## Authority Order

1. `result.json` and `evaluation_summary.json` for numeric tables and conclusions.
2. `excel_evaluation_results.json` when the authoritative Excel evaluator is used.
3. `figures_manifest.json` for model, modal, and stress images.
4. Steel-platform and non-steel-platform Word templates under `templates/report`.
5. Historical reports only for validation, calibration, and conflict discovery.

Historical reports are not used to guess values for new intake rows.

## Mandatory Checks

The formal report gate must fail if any item below fails:

- `template_report_audit.json.status == pass`.
- `report_audit.json.status == pass`.
- `result_validation.json.status == pass`.
- table titles in the generated Word report match the selected template section intent.
- web result page table titles match the generated report titles.
- Chapter 6 tables are generated only when required by the current analysis scope.
- Appendix A modal images exist when modal figures are required.
- Appendix B square-tube stress figures exist when square-support stress figures are required.
- Figure 5.1 uses the whole-model ANSYS image `SHITI`; Figure 5.2 uses the dedicated cantilever/tray-arm image `TBMODEL`. Figure 5.2 must never reuse Figure 5.1.
- Appendix C shows exactly one branch:
  - cantilever stress-cloud figures for square tube outer width `<= 120 mm`;
  - weld evaluation principle for square tube outer width `> 120 mm`.
- weld evaluation tables must follow the selected template layout. Non-steel templates use one row per condition with shear and equivalent stress in separate column groups; generic row-per-formula filling is not allowed for that table.
- no required report table contains all-zero rows from missing LIS extraction.
- no required load table uses `UNKNOWN` node/key-point when a deterministic set name is required.
- no formal conclusion is based on mock or dry-run data.
- unconfirmed formulas cannot produce a formal pass unless Excel authoritative evaluation succeeds and records source cells.

## Full Historical Validation Target

Before calling a release production-ready, run every historical report that has enough intake/report evidence through the current software as if it were a new intake row.

The validation package must include:

- generated modeling, calculation, and extraction command streams;
- real ANSYS or real imported outputs;
- `result.json`;
- `evaluation_summary.json`;
- `figures_manifest.json`;
- generated template report;
- report-versus-report comparison for all Chapter 6 tables;
- Appendix A/B/C image presence and branch checks;
- maximum numeric error for every comparable table.

Acceptance target:

- comparable numerical fields: max gate error `<= 1%`;
- known historical source conflicts are listed separately and do not tune new-intake output;
- every exclusion includes evidence in the conflict register.

## Operator Rule

If the gate fails, the dashboard must show the blocking reason and must not expose the generated report as a formal deliverable. The job may still keep its files for engineering debugging.
