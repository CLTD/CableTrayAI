# Final Logic Audit Before Web UI

Date: 2026-05-17

## Conclusion

The current direction matches the operator intent after the latest adjustment:

- Production authority is the standard command stream, deterministic/spec formulas, and job-local Excel authoritative evaluation.
- Historical reports are calibration and conflict-discovery references.
- Audited historical report conflicts are not allowed to override ANSYS output or new-intake production logic.
- New intake jobs are created from uploaded/selected intake files, not from historical report command folders, unless a developer explicitly runs a source-regression workflow.

## No Material Deviation Found

The earlier risk was treating historical reports as absolute truth. That has been corrected.

Current policy:

1. Use the standard command-flow renderer to generate model, solve, and extraction commands.
2. Use real ANSYS or real imported output for formal results.
3. Use deterministic formulas and Excel authoritative evaluation for assessment.
4. Use report comparison to find mapping mistakes, source conflicts, and regression issues.
5. Record conflicted historical rows in `data/calibration/report_baseline_conflicts.json`; do not hide them and do not use them to tune production outputs.

## Modeling Logic

- Intake rows are parsed from uploaded Excel-like tabular files or key-value files.
- Formal report number/calculation batch is optional at initial calculation time.
- If no formal number exists, the job uses a provisional identity based on workbook, sheet, and row/serial.
- After the formal number is later added to the intake workbook, reconciliation can bind the existing job to the final output folder.
- Intake column I is treated as the square tube section. If blank, the workflow marks `auto_selection_required`; candidate `*.SECT` sections must be tried inside the intake allowed list, and the selected section must satisfy the deterministic ratio gate `<= 1.0`. Production economy target is `0.60 <= ratio <= 0.9999` with at most two normal candidate trials.
- Steel-platform rows use static method. Non-steel-platform rows use response-spectrum method.
- Static jobs still require the selected project spectrum workbook or audited static acceleration coefficients so equivalent-static acceleration is traceable.
- Generated engineering command streams are:
  - `generated_model.mac`
  - `generated_solve.mac`
  - `generated_post.mac`
- `run_all.mac` is only the real ANSYS entrypoint and calls the three generated command streams in order.

## Calculation Logic

- ANSYS path discovery is read-only and does not execute ANSYS.
- Real execution requires guarded mode, valid executable, passing preflight, confirmed spectrum/static coefficients, and explicit real-run approval.
- Real runs use `run_all.mac`, not `generated_solve.mac`.
- Failed real runs do not fall back to mock.
- CPU process count can be configured by percentage strategy or explicit override; representative calibration runs still use one process when the source command stream is sensitive to multi-worker behavior.

## Result Extraction Logic

- The result parser reads named source files instead of choosing whichever value is closest to a report:
  - `SQUAREBEAMSTRESS.LIS`
  - `MAXBEAMSTRESS.LIS`
  - `TMAXBEAMSTRESS.LIS`
  - `JCZH.LIS`
  - `HF-FORCE.LIS`
  - `LS-FORCE.LIS`
  - `LS-FORCE-NODES.LIS`
  - `Mode.oup`
- Parsed values include source file, source hash, source line/block when available, raw value, normalized value, unit, and parser version fields where supported.
- Report comparison maps by table caption, result source file, component scope, and section/topology rule. It must not use nearest-value matching.
- Figure export derives named PNG output by mechanically converting the audited `generated_post.mac` image-save points, so cloud plots follow the same source post-processing selections.
- Appendix C figure policy is based on square tube outer width:
  - outer width `<= 120 mm`: publish `TB*` / `TD*` cantilever cloud figures.
  - outer width `> 120 mm`: do not publish cantilever cloud figures; use weld-evaluation-principle mode.

## Evaluation Logic

- Q355 and Q235 allowables are locked from the evaluation workbook formula pattern and documented material policy.
- Current locked values include:
  - Q355 bending allowable: `234.30 MPa`
  - Q355 normal/tension allowable: `159.75 MPa`
  - Q355 shear allowable: `142.00 MPa`
  - Q235 bending allowable: `155.10 MPa`
  - Q235 normal/tension allowable: `105.75 MPa`
  - Q235 shear allowable: `94.00 MPa`
- Steel-platform square support uses the conservative Q235 square-support policy; other steel-platform parts use Q355.
- Support evaluation covers tension, compression, bending, shear, tension-bending combination, and compression-bending combination.
- Combination rows use allowable value `1.0`, matching the report table convention.
- Bolt and weld checks carry `source_ref` and formula status.
- If a formula is not confirmed and Excel authoritative evaluation is unavailable, the job cannot receive a final production pass.
- Original Excel workbooks under `source_materials` are never modified; Excel evaluation works on job-local copies.

## New Intake Readiness

The current workflow supports:

1. Upload/select intake workbook.
2. Parse all supported rows into job-local `input.json`.
3. Use provisional job identity if report number/calculation batch is not available yet.
4. Select project-specific spectrum workbook.
5. Confirm or derive spectrum/static acceleration configuration.
6. Auto-discover ANSYS path without executing it.
7. Render model, solve, and extraction command streams from templates/standard command family.
8. Run preflight.
9. Run real ANSYS only after guard checks pass.
10. Parse LIS/OUP outputs.
11. Export named PNG figures from source post-processing image commands.
12. Evaluate with deterministic formulas and Excel authoritative fallback.
13. Publish clean operator results to the selected output root and final report/calculation-batch folder when a formal number exists.

## Latest Verification

- Full pytest suite: passed with `281` collected tests.
- Hardcoded sample-token scan under `core`, `apps`, and `templates`: no matches.
- `source_materials`: no Git modifications.
- Representative real ANSYS report-level smoke batch passed:
  - `18185NI-LXSJ4120`
  - `18185NI-LXSJ4126`
  - `18185NI-LXSJ4128`
  - `18185NI-LXSJ4225`
  - `18185NI-LXSJ4249`
- Batch result: `5/5` passed.
- Max effective gate error: `0.004990731571029472`, below the `1%` gate.

## Known Boundaries Before Web UI

- This check did not rerun every historical report package. The latest representative smoke batch passed, and earlier train/hold-out artifacts remain recorded, but the production policy no longer requires every historical report row to be treated as absolute authority.
- Some historical rows are audited source/report conflicts and remain visible as conflicts.
- Raw job workspaces contain helper macro files for ANSYS output redirection and figure export. The operator-facing published result folder and web UI should expose only the three engineering review command streams: modeling, calculation, and extraction.
- Report generation remains outside the next UI focus. The next UI should prioritize intake upload, spectrum selection, ANSYS discovery, output-folder selection, calculation status, command review, result tables, precision/conflict dashboard, and figure review.
