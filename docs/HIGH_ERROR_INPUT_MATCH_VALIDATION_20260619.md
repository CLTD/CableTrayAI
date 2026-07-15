# High-error input-matched validation - 2026-06-19

Scope: additional large-error cases from `C:/Users/duxy/Desktop/2`, using the same method as the NR `18185NI-LXSJ4249` diagnostic.

Method:

1. Keep the current software-generated model/post/evaluation pipeline.
2. Replace the solve stream with the matching desktop source `02` command stream where available.
3. Run real ANSYS18.2.
4. Compare the assembled software result against the historical report baseline at the existing baseline gate.
5. For remaining failures, compare generated model parameters with the desktop source `01` model to separate calculation-input mismatch from model/intake mismatch.

Batch root:

`jobs/input_matched_high_error_20260619_174851`

## Summary

| Report | Method | Main type | Before failed comparisons | After source-solve replay | Status | Interpretation |
|---|---|---|---:|---:|---|---|
| `18185NI-LXSJ4115` | response spectrum | double same-width 500 | 42 | 0 | pass | Large error resolved by input-matched solve stream. |
| `18185NI-LXSJ4118` | response spectrum | single 300 | 17 | 0 | pass | Large error resolved by input-matched solve stream. |
| `18185NI-LXSJ4156` | response spectrum | single 200 | 3 | 0 | pass | Large error resolved by input-matched solve stream. |
| `18185NI-LXSJ4126` | static | 200/300-class static sample | 79 | 76 | fail | Generated model is not the same as the historical source model. |
| `18185NI-LXSJ4151` | response spectrum | mixed 500/600 | 77 | 77 | fail | Generated model is not the same as the historical source model. |
| `18185NI-LXSJ4228` | static | double same-width 500 | 64 | 16 | fail | Mostly improved; residual comes from historical `L3=0.15` versus current locked rule `L3=0.20` for 500 mm tray with 120 square section. |

The three response-spectrum single/same-width cases now match the historical reports after the source solve stream is replayed. Their remaining `result_validation.json` failures are diagnostic artifacts from this numeric-only replay: figure export was intentionally skipped and some source post streams do not provide the full current publication figure set. The numeric baseline comparison is pass.

## Case notes

### 18185NI-LXSJ4115

- Diagnostic job: `jobs/input_matched_high_error_20260619_174851/18185NI-LXSJ4115_source_solve`
- Baseline failures before replay: `42`
- Failures after source-solve replay: `0`
- Baseline comparison status: `pass`
- Maximum gate error: `0.004160212688098852`

Conclusion: the large historical-report error was calculation-input mismatch, not a current model/evaluation mismatch.

### 18185NI-LXSJ4118

- Diagnostic job: `jobs/input_matched_high_error_20260619_174851/18185NI-LXSJ4118_source_solve`
- Baseline failures before replay: `17`
- Failures after source-solve replay: `0`
- Baseline comparison status: `pass`
- Maximum gate error: `0.004944469300914717`

Conclusion: the large historical-report error was calculation-input mismatch, not a current model/evaluation mismatch.

### 18185NI-LXSJ4156

- Diagnostic job: `jobs/input_matched_high_error_20260619_174851/18185NI-LXSJ4156_source_solve`
- Baseline failures before replay: `3`
- Failures after source-solve replay: `0`
- Baseline comparison status: `pass`
- Maximum gate error: `0.004862134016218517`

Conclusion: the large historical-report error was calculation-input mismatch, not a current model/evaluation mismatch.

### 18185NI-LXSJ4126

- Diagnostic job: `jobs/input_matched_high_error_20260619_174851/18185NI-LXSJ4126_source_solve`
- Baseline failures before replay: `79`
- Failures after source-solve replay: `76`
- Baseline comparison status: `fail`
- Representative remaining difference: square-support upset bending `98.5247 MPa` versus report `133.76 MPa`

Generated model versus desktop source model:

| Item | Current generated model | Desktop source model |
|---|---|---|
| Source file | `generated_model.mac` | `C:/Users/duxy/Desktop/2/18185NI-LXSJ4126/.../01...300.PIP` |
| Square section | `100-100-6` | `100-100-6` |
| Tray sections | `300-75-2mm` plus repeated `200-75-2mm` | `300-75-2mm` only |
| Layer variables | `qiancengshu=3`, `houcengshu=2` | `senum=3`, `senum1=2` |
| Topology | CTAI mixed topology, 29 keypoints, 18 loops | source same-width topology, 15 keypoints, 10 loops |

Conclusion: this is not just solve-input mismatch. The intake/model used by the software is not equivalent to the historical source model/report. Before using this case as a numeric regression, the calculation input must be reconciled: either rerun the software with a true 300-only source-equivalent input, or mark the historical report as an input/model mismatch.

### 18185NI-LXSJ4151

- Diagnostic job: `jobs/input_matched_high_error_20260619_174851/18185NI-LXSJ4151_source_solve`
- Baseline failures before replay: `77`
- Failures after source-solve replay: `77`
- Baseline comparison status: `fail`
- Representative remaining difference: mode 1 `3.7386 Hz` versus report `2.808 Hz`; mode 68 `65.014 Hz` versus report `30.78 Hz`

Generated model versus desktop source model:

| Item | Current generated model | Desktop source model |
|---|---|---|
| Square section | `160-160-8` | `160-160-8` |
| Tray sections | `500-75-2mm` only | `600-75-2mm` and `500-75-2mm` |
| Geometry variables | `L1=0.55`, `L2=0.5`, `L3=0.15`, `senum=3`, `senum1=2` | `L1=0.67`, `L2=0.6`, `L3=0.2`, `L5=0.55`, `L6=0.5`, `senum=4`, `senum1=3` |

Conclusion: the model is not equivalent. The modal-frequency failures are expected when a 500-only generated model is compared against a historical 600+500 model. This case should not be treated as a calculation-command-only mismatch.

### 18185NI-LXSJ4228

- Diagnostic job: `jobs/input_matched_high_error_20260619_174851/18185NI-LXSJ4228_source_solve`
- Baseline failures before replay: `64`
- Failures after source-solve replay: `16`
- Baseline comparison status: `fail`
- Representative remaining difference: cantilever upset tension `0.4595 MPa` versus report `0.44 MPa`; weld equivalent `0.8736 MPa` versus report `0.83 MPa`

Generated model versus desktop source model:

| Item | Current generated model | Desktop source model |
|---|---|---|
| Square section | `120-120-8` | `120-120-8` |
| Tray section | `500-75-2mm` | `500-75-2mm` |
| `L3` | `0.20` | `0.15` |

Conclusion: the current software follows the locked rule currently in the codebase and tests: tray width `<=300 mm` uses `0.15 m`; tray width `>300 mm` with square outer `<=120 mm` uses `0.20 m`; tray width `>300 mm` with square outer `>120 mm` uses `0.15 m`. The historical 4228 source model uses `L3=0.15` for a 500 mm tray with `120-120-8`, so this is a historical-model-policy conflict. If this report must be reproduced exactly, it needs a historical replay mode or an explicit rule override, not a silent production-code change.

## Decision

1. For `4115`, `4118`, and `4156`, the large deviations disappear after calculation input is made consistent. This supports the same conclusion as NR `4249`: response-spectrum historical stress mismatches were primarily solve-input mismatches.
2. For `4126` and `4151`, the remaining large deviations are model/input mismatches. Replaying the source solve stream cannot fix a different generated model.
3. For `4228`, the comparison is sensitive to a known `L3` policy conflict between the historical source model and the current locked production rule.
4. Do not claim the full desktop-folder-2 baseline is clean. The accepted subset is now: NR `4249` governing stress/ratio, plus `4115`, `4118`, and `4156`.
5. Before package publication based on this baseline, decide how to handle historical reports that conflict with current production input policy: keep current rules and document conflicts, or add a developer-only historical replay mode that freezes the source model/solve/post streams for baseline reproduction only.
