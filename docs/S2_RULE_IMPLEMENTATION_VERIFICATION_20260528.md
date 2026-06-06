# S2 Rule Implementation Verification - 2026-05-28

## Purpose

This note records the current general S2 implementation after the latest rule
fixes. The changes are not limited to `18185NI-LXSJ4140`; they apply to all
new-intake S2 jobs rendered through the current standard command-family
pipeline.

Formal conclusions remain controlled by ANSYS outputs, authoritative Excel or
deterministic formulas, `result.json`, `figures_manifest.json`, and
`source_ref`. Historical reports are used for validation and conflict discovery,
not for hard-coding production values.

## Current General Rules

| Area | Current rule | Verification status |
|---|---|---|
| Modal solve count | MT is a solve input. New-intake first solves use the intake/geometry rule or the default bounded value. Audited source `MT` or literal `MODOPT,LANB,<n>` is allowed to raise the first solve only when it is within the safe initial range `<=120`; very large historical batch counts such as several hundred modes are kept for traceability but are not copied into the first production run. After ANSYS runs, `Mode.oup` verifies frequency coverage above 50 Hz. If it fails, the one-click flow rewrites `generated_solve.mac` to the next reviewed value in `40/60/80/90/100/120/160/200/240` and reruns, stopping at the first passing MT so the final frequency coverage is close to the 50 Hz requirement. | Locked by unit tests; prevents very slow first-run modal solves while still enforcing 50 Hz coverage. |
| Modal output parsing | `Mode.oup` may also be recovered from ANSYS text outputs such as `8TEG*.TXT` or `ansys.out`. Near-rigid zero-frequency rows are excluded from reportable modal rows, while the original ANSYS mode is retained as `source_mode`. | Fixed division-by-zero and false modal mismatch failures. |
| 50 Hz modal coverage | The validation gate checks that the real modal output covers frequencies above 50 Hz. If coverage is missing, the job remains invalid. | 4140 and the representative passing cases now pass this gate. |
| Modal figures | MOTAI figure export uses a bounded graphics-only modal solve for the first 4 figures. This does not change the production solve MT or modal result table. | Prevents huge figure-export runs while preserving result authority. |
| Static correction | Static correction uses 100 Hz spectrum acceleration values in the generated solve stream. | Covered by command rendering and validation tests. |
| Arm-section family branch | The cantilever arm section family is controlled by square-tube outer width only. `<=120 mm` uses the normal channel arm family `50-42/CAOGANG42DAN`; `>120 mm` uses the special-shaped steel arm family `YIXINGGANG150/YIXINGGANG150DAN`. Tray width or layer count must not force a special-shaped arm. | Covered by new-intake builder and standard-family renderer tests. |
| Small square tube branch | Square tube outer width `<= 120 mm` uses the equivalent-stress weld branch with coefficient 0.526 and requires TB/TD cantilever stress figures. | Covered by result requirement and display tests. |
| Large square tube branch | Square tube outer width `> 120 mm` uses cantilever root loads plus weld stress evaluation, and uses the weld-principle appendix branch. | Covered by result requirement and display tests. |
| Material policy | Steel-platform square support remains conservative Q235 where required; non-steel platform and other Q355-controlled members use Q355 allowables. | Covered by material policy tests. |
| Invalid result gate | All-zero required tables, `UNKNOWN` formal load nodes, missing source references, missing figures, and failed parser provenance block formal conclusions. | Included in the batch status through `result_validation`. |

## Representative 15-Case Run

Command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_intake_as_new_report_precision_batch.ps1 -ReportNumber 18185NI-LXSJ4115,18185NI-LXSJ4116,18185NI-LXSJ4119,18185NI-LXSJ4120,18185NI-LXSJ4123,18185NI-LXSJ4128,18185NI-LXSJ4135,18185NI-LXSJ4139,18185NI-LXSJ4140,18185NI-LXSJ4144,18185NI-LXSJ4147,18185NI-LXSJ4151,18185NI-LXSJ4152,18185NI-LXSJ4155,18185NI-LXSJ4249 -Nproc 10 -TimeoutMinutes 120 -NoPublish
```

Result file:

`docs/precision_gate/intake_as_new_report_precision_batch.json`

Summary:

| Metric | Value |
|---|---:|
| Total selected cases | 15 |
| Strict pass cases | 4 |
| Historical/source conflict cases | 11 |
| Failed cases | 0 |
| Max strict gate error | 0.805% |

Strictly comparable cases:

| Report | Status | Max gate error |
|---|---:|---:|
| 18185NI-LXSJ4115 | pass | 0.409% |
| 18185NI-LXSJ4120 | pass | 0.556% |
| 18185NI-LXSJ4123 | pass | 0.805% |
| 18185NI-LXSJ4140 | pass | 0.481% |

Historical/source conflict cases are kept visible instead of being tuned against:

| Report | Status | Reason category |
|---|---|---|
| 18185NI-LXSJ4116 | baseline_conflict | Intake/report design facts do not fully match. |
| 18185NI-LXSJ4119 | baseline_conflict | Intake/report design facts do not fully match. |
| 18185NI-LXSJ4128 | baseline_conflict | Intake/report design facts do not fully match. |
| 18185NI-LXSJ4135 | baseline_conflict | Audited baseline conflict rows; current result validation passes. |
| 18185NI-LXSJ4139 | baseline_conflict | Intake/report design facts do not fully match. |
| 18185NI-LXSJ4144 | baseline_conflict | Report narrative spectrum elevations conflict with package command-file spectrum elevations. |
| 18185NI-LXSJ4147 | baseline_conflict | Audited baseline conflict rows; current result validation passes. |
| 18185NI-LXSJ4151 | baseline_conflict | Intake/report design facts do not fully match. |
| 18185NI-LXSJ4152 | baseline_conflict | Audited baseline conflict rows; current result validation passes. |
| 18185NI-LXSJ4155 | baseline_conflict | Intake/report design facts do not fully match. |
| 18185NI-LXSJ4249 | baseline_conflict | Audited baseline conflict rows; current result validation passes. |

## Tests Run

```powershell
pytest -q tests\unit\test_lis_parser.py tests\unit\test_modal_output_normalization.py tests\unit\test_real_lis_variants.py tests\unit\test_ansys_command_builder.py tests\unit\test_figure_export.py tests\unit\test_intake_standard_family_renderer.py tests\unit\test_apdl_renderer.py tests\unit\test_result_validity_gate.py
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
git status --short source_materials
```

Results:

- Unit test subset: pass.
- Hard-code scan: no hits in `core`, `apps`, or `templates`.
- `source_materials`: no Git modifications.

## Engineering Boundary

The current implementation is suitable for the S2 production path where the
topology is covered by the audited standard command families. It does not claim
that every historical report is correct or that conflict samples should force
new production logic. Conflict samples are retained for department review and
future source reconciliation.
