# LS-FORCE topology and coverage validation - 2026-06-19

## Scope

The user asked to verify that the 4126 LS-FORCE/bolt-load hardening is useful, and then check non-recent validation cases with consistent calculation inputs so the 100/200, 300, 500, 600, and mixed-width logic is not confused.

## 4126 LS-FORCE conclusion

The code change is useful for the generic production failure mode:

- `core/apdl/ls_force_topology.py` audits whether the model exposes the standard suffix-9 LS-FORCE interface: `509/1509`.
- `postprocessor_alignment` records `ls_force_selector` when the post stream uses the standard suffix-9 `KYALS` selector.
- `result_assembler` marks selected all-zero connection-node families as `selected_all_zero`.
- `result_validity_gate` blocks a published result when final `bolt_force_results` are all zero even if unrelated raw connection-node rows are nonzero.

Direct audit evidence:

| Case | Model topology status | Meaning |
|---|---:|---|
| `18185NI-LXSJ4126_full_input` historical source model | fail | Missing `509/1509`; legacy `506/507/508` physical bolt geometry exists but is not enough for the standard suffix-9 LS-FORCE selector. |
| `18185NI-LXSJ4120` current generated model | pass | Standard suffix-9 interface exists. |
| `18185NI-LXSJ4153` current production model | pass | Standard suffix-9 interface exists. |

Important boundary:

`4126` is still not accepted as a fully matched historical baseline. The source-model replay proves main stress, modal, and `JCZH.LIS` foundation loads match the report, but `LS-FORCE.LIS` remains different. The diagnostic `*09 -> *07` selector produced nonzero loads but still did not match the report, so production must not adopt `507` as a rule without the original department `03` post stream.

## Input-matched coverage check

The following existing real ANSYS replays were re-summarized at the user-requested 5% gate. These are not the latest `4120/4123/4135/4152/4153/4154` batch; they are the separate desktop-folder-2 input-matched replay set.

Source summary file:

`jobs/input_matched_coverage_summary_20260619.json`

Current-code reparse check:

`jobs/reparse_validation_20260619/summary.json`

This reparse did not rerun ANSYS. It copied representative real-output LIS files and reassembled them with the current `result_assembler` and `result_validity_gate`. For `4126_full_input_reparse`, `4156_200_reparse`, and `4151_mixed_reparse`, the `connection_load_values` gate passed with nonzero published `bolt_force_results`. The copied diagnostic directories still fail their overall result gate where full report figures are absent; that is expected for numeric replay folders and is not an LS-FORCE extraction failure.

| Case | Coverage | Square section | 5% status | Notes |
|---|---|---|---:|---|
| `18185NI-LXSJ4115_source_solve` | 500 mm | `100-100-8` | pass | Source model and source solve replay; no metric over 5%. |
| `18185NI-LXSJ4118_source_solve` | 300 mm | `100-100-6` | pass | Source model and source solve replay; no metric over 5%. |
| `18185NI-LXSJ4156_source_solve` | 200 mm | `100-100-6` | pass | Source model and source solve replay; no metric over 5%. |
| `18185NI-LXSJ4249_source_solve` | 600 mm | `140-140-8` | pass | NR source solve replay; remaining report deltas are within 5%. |
| `18185NI-LXSJ4151_full_input` | 500+600 mm mixed | `160-160-8` | pass | Full input-matched source model plus source solve; no metric over 5%. |
| `18185NI-LXSJ4228_full_input` | 500 mm historical static | `120-120-8` | pass | Historical model uses `L3=0.15`; this is accepted only as historical replay evidence, not a change to current production L3 policy. |
| `18185NI-LXSJ4126_full_input` | 300 mm source-style historical model | `100-100-6` | fail | Only `LS-FORCE.LIS` remains over 5%; main stress/modal/foundation are aligned. |

## Gate results

Commands rerun after the LS-FORCE hardening:

```text
D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py tests/unit/test_postprocessor_alignment.py tests/unit/test_result_assembler_connection_nodes.py tests/unit/test_result_validity_square_section.py -q
```

Result: `75 passed`.

```text
D:/miniconda3/python.exe -m pytest tests/unit -q
```

Result: full unit suite passed.

```text
D:/miniconda3/python.exe -m py_compile core/apdl/ls_force_topology.py core/apdl/intake_standard_family_renderer.py core/apdl/postprocessor_alignment.py core/results/result_assembler.py core/validation/result_validity_gate.py
```

Result: passed.

```text
git diff --check
```

Result: no whitespace errors; only pre-existing CRLF/LF normalization warnings on already modified files.

## Decision

1. The current fix should be kept: it prevents the class of errors where model and LS-FORCE post topology are mismatched or a zero selected bolt-load envelope is published.
2. The fix does not show evidence of confusing 100/200, 300, 500, 600, or 500+600 mixed logic. The input-matched coverage examples above stay within 5% except the known 4126 LS-FORCE historical open item.
3. Do not claim 4126 LS-FORCE is fully reproduced until the exact department `03` extraction stream or equivalent authoritative extraction point is available.
