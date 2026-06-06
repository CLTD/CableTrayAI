# Historical Report Conflict Analysis

Date: 2026-05-20

## Current Count

The 47 historical report-backed cases are split into three mutually exclusive groups:

| Group | Count | Meaning |
| --- | ---: | --- |
| Strict pass | 8 | The regenerated new-intake workflow agrees with the historical report within the 1% gate. |
| Audited historical report/source conflict | 15 | A specific report row or source command conflict has evidence. These rows are excluded from calibration only and do not change production ANSYS output. |
| Remaining mismatch | 24 | The generated result passes the production validity gate, but historical report comparison still exceeds 1% and needs discipline/source review. |

The 15 audited conflicts are **not** part of the remaining 24.

## Audited Conflict Cases

The detailed machine-readable record is `data/calibration/report_baseline_conflicts.json`.

### 18185NI-LXSJ4123

Conflict type: spectrum/static coefficient conflict.

Evidence summary:

- Active command source and selected spectrum workbook use the SL-1 vertical coefficient around `0.409`.
- Historical report rows align with using the lower horizontal coefficient around `0.378`.
- The affected rows include square-support stress, cantilever stress, weld-equivalent rows, foundation load, and tray-arm connection load.

Policy:

- Keep the selected spectrum workbook coefficient in production.
- Do not flatten the vertical coefficient merely to match this historical report.

### 18185NI-LXSJ4126

Conflict type: tray-arm bolt-load collection topology conflict.

Evidence summary:

- The compact historical source reproduces modal, square-support stress, foundation, cantilever-arm, and weld tables.
- The same source lacks the standard `*9` tray-arm bolt surrogate keypoint family expected by the shared `LS-FORCE` postprocessor.
- Injecting the standard `*9` block changes modal and support-stress behavior, so one single audited command source cannot reproduce all report rows at once.

Policy:

- Treat only those tray-arm connection load rows as historical source/report conflict.
- New-intake production extraction still follows the standard topology and validity gate.

### 18185NI-LXSJ4128

Conflict type: duplicate/suspect report baseline rows and isolated source-family conflict.

Evidence summary:

- Two tray-arm connection load rows in 4128 exactly duplicate rows from 4115 even though they are different report packages.
- One derived bolt-load FZ entry follows an alternate `.bak` source family while the active source matches other 4128 tables.

Policy:

- Exclude only these audited rows from numerical calibration.
- Do not use nearest-value substitution or copy report numbers back into production output.

## Remaining 24 Mismatch Cases

These are not automatically wrong reports and not automatically wrong software. They are unresolved comparison findings.

Dominant failed metric types across the 24:

| Metric type | Failed rows | Interpretation |
| --- | ---: | --- |
| `beam_calculation_value` | 226 | Stress extraction/source coefficient/material-section differences dominate. |
| `combination_ratio_value` | 90 | Mostly follows the beam stress differences because combination ratios are derived from stress rows. |
| `weld_equivalent_stress_value` | 83 | Mostly follows cantilever/root-force and stress source differences. |
| `evaluation_ratio` | 55 | Allowable/source or rounded ratio comparison mismatch. |
| `foundation_load` | 49 | Support reaction source/coefficient/envelope differences. |
| `tray_arm_connection_load` | 26 | Connection node set or source-family differences. |
| `cantilever_root_load` | 16 | Root force extraction differences. |
| `modal_frequency` | 12 | Model/source topology mismatch, especially where modal error is very large. |
| `derived_bolt_load_missing` | 2 | Historical report expects derived bolt rows not present in the current production extraction scope. |

Highest-risk remaining cases by max gate error:

- `18185NI-LXSJ4154`: max gate error about `99%`; broad beam/combination/weld mismatch.
- `18185NI-LXSJ4141` and `18185NI-LXSJ4145`: max gate error about `78%`; modal frequency mismatch indicates likely model/source topology mismatch.
- `18185NI-LXSJ4225` and `18185NI-LXSJ4227`: max gate error about `26%`; broad beam/combination/weld mismatch.
- `18185NI-LXSJ4144`: max gate error about `26%`; foundation/tray-arm connection load mismatch dominates.

## Engineering Judgment

The production gate is currently based on:

1. intake-derived JSON/input facts,
2. standard APDL/PIP/MAC command logic,
3. selected spectrum workbook coefficients,
4. real ANSYS or real imported output,
5. deterministic evaluator/Excel authoritative evaluation,
6. post-processing validity checks that block all-zero rows, `UNKNOWN` nodes, missing files, blank figures, and missing source maps.

Historical report comparison is used to find source conflicts and software defects. It is not allowed to silently override generated ANSYS results.

## 2026-05-20 Deep Review And Code Fixes

The latest review separated report-rendering defects from numerical calibration defects.

### Fixed software defects

1. **Figure 5.1 / Figure 5.2 source mapping**
   - Cause: `core/report/template_injector.py` previously allowed Figure 5.2 (`托臂有限元模型`) to fall back to `SHITI.PNG`, which is the whole S2 support model used by Figure 5.1.
   - Fix: Figure 5.2 now requires a distinct `TBMODEL` ANSYS output. If the image is absent, report injection writes a warning and refuses to reuse the whole-model image.
   - Command fix: `templates/apdl/post_extract_s2.mac.j2` now exports `TBMODEL.bmp` by selecting the tray-arm/tray element TYPE families (`10*layer+2/3/4` and `200*layer+2/3/4`) before plotting. The 8-character file stem avoids MAPDL graphics-name truncation.
   - Scope impact: report injection and figure-export gate only. It does not alter ANSYS stresses, loads, or evaluation ratios.

2. **Required model figures**
   - Cause: result requirements checked modal and stress figures, but did not require the two Chapter 5 finite-element model figures.
   - Fix: `core/validation/result_requirements.py` and `core/validation/analysis_scope.py` now include `SHITI.PNG` and `TBMODEL.PNG` in `required_figures`.
   - Scope impact: new jobs cannot pass the figure gate while Figure 5.1 or Figure 5.2 is missing.

3. **Weld evaluation table layout**
   - Cause: the non-steel template weld table is not a generic "one formula row per item" table. It is a two-row table by condition, with shear stress and equivalent stress in separate column groups. The old injector could put category text into numeric columns.
   - Fix: `core/report/template_injector.py` now detects the weld table layout. For the non-steel layout it fills:
     - `异常工况`: shear calculation / shear allowable / shear ratio / equivalent calculation / equivalent allowable / equivalent ratio;
     - `事故工况`: the same six values.
   - It also trims unused rows in variable weld tables so blank historical-template rows do not create blank pages.
   - Scope impact: report injection only. It does not change `result.json`.

### Still not treated as software fixes

The 15 audited conflict rows and the 24 remaining post-validation mismatches are not resolved by the above rendering fixes. Their current root causes remain in the following buckets:

| Bucket | Evidence pattern | Code responsibility boundary |
| --- | --- | --- |
| modal/source topology mismatch | very large modal-frequency deltas, usually with different active source family or compact historical model | do not force modal values; inspect model geometry and constraint/source command before changing renderer |
| beam stress family mismatch | broad stress and combination rows move together | check selected element/component set and spectrum/static coefficient family; do not choose nearest report row |
| weld equivalent mismatch | follows cantilever/root stress or HF-FORCE differences | formula path remains Excel-confirmed; inspect upstream force/stress extraction first |
| foundation load mismatch | JCZH rows differ while stress rows may match | inspect constrained support-node set and loadcase coefficient family |
| connection bolt load mismatch | LS-FORCE or node-family exports differ by topology | inspect standard `*9` surrogate keypoint family and connection-node map |

If one of these buckets is proven to come from our command generation, parser, evaluator, or report injector, it must be fixed in code with a test. If it is proven to come from mutually inconsistent historical report/source files, it stays in the conflict register and must not tune new-intake production results.

### Verification evidence after fixes

- Unit and integration regression suite: `python -m pytest -q` passed.
- Hardcode scan: `rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates` returned no matches.
- Real ANSYS post-only figure export was rerun on `18185NI-LXSJ4142`.
  - `figure_export_audit.json` status: `success`.
  - Figure mapping includes `CableTrayAI_Run060.png -> SHITI.PNG` and `CableTrayAI_Run061.png -> TBMODEL.PNG`.
- Template report injection was rerun on `18185NI-LXSJ4142`.
  - `template_report_audit.json` status: `pass`.
  - Replacements include `图5.1 -> SHITI.PNG`, `图5.2 -> TBMODEL.PNG`.
  - Weld evaluation table replacement status: `pass`, `filled_rows = 2`.

## Recommended Discipline Review

For the 15 audited conflicts:

- Review the evidence row by row.
- Decide whether the historical report is acceptable as-is, should be corrected, or should be marked as a legacy conflict.
- If the discipline owner confirms a conflict is truly a report/source defect, keep it excluded from calibration.

For the 24 remaining mismatches:

- Start with modal mismatches, because large modal error usually indicates a model/source topology mismatch rather than a simple formula issue.
- Then review beam stress families and spectrum coefficients.
- Then review foundation and tray-arm connection node sets.
- Only after the source logic is confirmed should report numbers be used as precision targets.
