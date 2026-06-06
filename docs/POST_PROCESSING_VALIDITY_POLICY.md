# Post-Processing Validity Policy

The operator page must never treat a parsed file as an engineering result by itself. A result is publishable only after the validity gate passes.

Current gate rules:

1. Required LIS/OUP files are chosen from the intake-derived scope, not from a future report.
2. `MAXBEAMSTRESS.LIS`, `JCZH.LIS`, and the required connection-load files must exist.
3. If square tube outer width is `<= 120 mm`, `TMAXBEAMSTRESS.LIS` and TB/TD cantilever cloud figures are required.
4. If square tube outer width is `> 120 mm`, weld-principle extraction is required and TB/TD cantilever cloud figures are not required.
5. Stress and force rows must not be all zero.
6. Rows with no parseable numeric values are treated as invalid, the same as all-zero rows.
7. Foundation load rows must not show `UNKNOWN`; standard JCZH envelope rows are labelled `ENVELOPE_OF_NKMS_SUPPORT_NODES`.
8. Zero topology rows from `LS-FORCE-NODES.LIS` are filtered and are not displayed as bolt loads.
9. Required ANSYS figures must be present before the result can be published as complete.
10. Required ANSYS figures must not be blank-like. The collector records `image_quality`; required figures with near-empty pixels fail the gate.

The S2 post macro is still sourced from the standard PIP/MAC stream, but the generated parameterized model changes the element type topology. The old shared-source selector for `TMAXBEAMSTRESS.LIS` was:

- `ESEL,S,TYPE,,1`
- `ESEL,U,SEC,,1`

That selector is recorded in the source PIP, but in the parameterized CableTrayAI model `TYPE=1` is the square support. After `ESEL,U,SEC,,1`, the set can become empty, which produced all-zero `TMAXBEAMSTRESS.LIS`.

The renderer now writes `postprocessor_alignment_audit.json` and replaces only this selector with the actual tray-arm type family:

- `ESEL,NONE`
- front tray arms: `ESEL,A,TYPE,,10*I+2` and `ESEL,A,TYPE,,10*I+3`
- back tray arms: `ESEL,A,TYPE,,200*I+2` and `ESEL,A,TYPE,,200*I+3`

This is not nearest-value matching. It is topology alignment between `generated_model.mac` `LATT` type assignments and the result extraction block. `result_source_map.json` records the selector and labels `TMAXBEAMSTRESS.LIS` as `parameterized_cantilever_arm_type_family`.

Square-support stress is exported separately by the augmented `SQUAREBEAMSTRESS.LIS` block, which narrows the square support to `SEC=1`.

The generated post macro also injects `H1` from `input.json` before the Appendix C branch. The user-confirmed branch rule is:

- square tube outer width `<= 120 mm`: export TB/TD cantilever stress cloud figures;
- square tube outer width `> 120 mm`: use weld-evaluation-principle extraction and do not publish TB/TD figures.

Layer-count aliases are owned by the model command stream. Parameterized geometry defines `senum=qiancengshu` and `senum1=houcengshu` in `generated_model.mac`; standard copied model files that already define `senum/senum1` must not be overwritten by the post macro. The renderer removes stale post aliases before ANSYS execution so that `JCZH.LIS` and `LS-FORCE.LIS` loops use the model-declared topology.
