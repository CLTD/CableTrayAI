# Full input-matched validation - 2026-06-19

Scope: follow-up to `docs/HIGH_ERROR_INPUT_MATCH_VALIDATION_20260619.md`.

User acceptance note: inspect the remaining high-error cases after making calculation input consistent; differences within about `5%` are acceptable for this diagnostic.

Batch root:

`jobs/full_input_matched_high_error_20260619_180420`

Method:

1. Use the desktop historical `01` model source as `generated_model.mac`.
2. Use the desktop historical `02` calculation source as `generated_solve.mac`.
3. Strip embedded analysis tails from `01` model sources when present, so `run_all.mac` still calls model, solve and post in order.
4. Use the current standard S2 post-processing stream from `source_materials/model_commands/*S2.PIP`, then align selectors to the source model topology and generate `generated_post_numeric.mac`.
5. Run real ANSYS18.2 with figure export disabled for numeric comparison speed.
6. Compare against the historical report baseline at `5%`, while also keeping `1%` snapshots.

## Summary

| Report | Full input-matched status at 5% | Strict 1% status | Main conclusion |
|---|---|---|---|
| `18185NI-LXSJ4151` | pass | pass | Source model + source solve removes the previous modal/stress mismatch. |
| `18185NI-LXSJ4228` | pass | pass | Source model with historical `L3=0.15` removes the previous residual mismatch. |
| `18185NI-LXSJ4126` | fail | fail | Main stress/modal/foundation values match; only `LS-FORCE` tray-arm connection loads remain unresolved. |

## 18185NI-LXSJ4151

- Diagnostic job: `jobs/full_input_matched_high_error_20260619_180420/18185NI-LXSJ4151_full_input`
- Input used: desktop `01` source model with `600-75-2mm + 500-75-2mm`, source `02` response-spectrum solve.
- Real ANSYS status: success.
- 5% comparison: pass, `0` failed metrics.
- 1% comparison: pass, `0` failed metrics.
- Maximum gate error: `0.004367791435481383`.
- Governing gate item: upset tension+bending ratio `0.8043677914354814` versus report `0.80`.
- Modal max relative error is about `0.011%`.

Interpretation: this case was not a calculation-command-only issue. Once the source model and source solve are both used, the previous `500-only` versus `600+500` mismatch disappears.

## 18185NI-LXSJ4228

- Diagnostic job: `jobs/full_input_matched_high_error_20260619_180420/18185NI-LXSJ4228_full_input`
- Input used: desktop `01` source model with historical `L3=0.15`, source `02` static solve.
- Real ANSYS status: success.
- 5% comparison: pass, `0` failed metrics.
- 1% comparison: pass, `0` failed metrics.
- Maximum gate error: `0.004821440344644972`.
- Governing gate item: cantilever-root weld upset equivalent ratio `0.005178559655355028` versus report `0.01`.
- Stress values are effectively identical for the engineering-significant rows; large relative percentages only occur on near-zero ratio rows.

Interpretation: the previous residual difference was the historical `L3=0.15` model policy versus the current production rule that uses `L3=0.20` for `500 mm` tray with `120-120-8`. Exact historical reproduction requires freezing that historical model input.

## 18185NI-LXSJ4126

- Diagnostic job: `jobs/full_input_matched_high_error_20260619_180420/18185NI-LXSJ4126_full_input`
- Input used: desktop `01` source model, forced input payload to the source-model interpretation: double side `3+2`, pure `300-75-2mm`, source `02` static solve.
- Real ANSYS status: success.
- Main stress/modal/foundation comparison: pass within 5%.
- Stress maximum relative error: `0.0327%` on square-support upset tension; gate error `0`.
- Modal maximum relative error: about `0.00002%`.
- 5% comparison still fails due to `LS-FORCE.LIS` tray-arm connection loads.

Two `LS-FORCE` diagnostics were run:

1. Generic standard S2 post selector selected the `*09` keypoint family. The source `4126` model does not define these keypoints, so `LS-FORCE.LIS` became all zero.
2. A diagnostic-only selector patch changed `*09` to the source model's existing `*07` keypoint family. This produced non-zero values, but they still did not match the report; for example upset `FY` differed by about `26.5%`, upset `FZ` by about `44.1%`, and the small `MZ` row was not meaningful by relative percent.

Interpretation: for `4126`, structural stress and modal values are aligned after full input matching. The remaining mismatch is a source-family-specific connection-load extraction problem. The historical folder has no separate `03` post stream, so the exact department extraction point for that report cannot yet be proven from the desktop evidence alone.

## Decision

1. `4151` and `4228` are now clean under the user's `5%` acceptance idea, and even pass the stricter `1%` comparison gate.
2. `4126` should not be marked fully accepted yet because `LS-FORCE` connection-load extraction is not aligned, even though the main stress/ratio values match.
3. The next targeted fix should be a source-family-aware `LS-FORCE` selector for `300` source-style models, or acquisition of the exact historical `03` extraction stream for `4126`.
4. No deployment package was rebuilt for this diagnostic; it only produced validation evidence.
