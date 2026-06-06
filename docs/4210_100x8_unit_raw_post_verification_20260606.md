# 4210 100x8 Unit Raw Post Verification

Date: 2026-06-06

Purpose: verify whether the unit standard result-extraction command stream `source_materials/model_commands/导出数据-S2.PIP` makes 4210 `100-100-8` exceed ratio 1.0 when used with the Excel 8.5 spectrum plus MMASS calculation.

## Diagnostic Job

- Job: `jobs/diagnostic_4210_100x8_excel85_unit_raw_post_20260606_012423/18185NI-LXSJ4210_100-100-8_excel85_unit_raw_post`
- Model and solve source: `jobs/diagnostic_4210_100x8_excel85_mmass_20260606_011434/18185NI-LXSJ4210_100-100-8_excel85_mmass`
- Post source: raw unit `source_materials/model_commands/导出数据-S2.PIP`
- Encoding handling: `unit_raw_post_source.PIP` is preserved as a raw copy; `generated_post.mac` is only decoded from GBK to UTF-8 so the APDL preflight audit can read it.
- No CableTrayAI postprocessor alignment and no `SQUAREBEAMSTRESS` augmentation were applied.

Real ANSYS completed successfully:

- `ansys_run_audit.json`: status `success`
- Duration: `165.216125s`
- Extra figure/connection export: disabled for this diagnostic

## Raw LIS Output

The raw unit post command stream produced:

- `MAXBEAMSTRESS.LIS`
- `TMAXBEAMSTRESS.LIS`
- No `SQUAREBEAMSTRESS.LIS`

`MAXBEAMSTRESS.LIS` from the unit raw post is numerically the same as the existing Excel 8.5 diagnostic `MAXBEAMSTRESS.LIS`. The section-1-only platform `SQUAREBEAMSTRESS.LIS` has the same controlling bending/tension values for this case but removes mixed-section ambiguity for production traceability.

## Ratio Check

Using the raw unit `MAXBEAMSTRESS.LIS` as the square-support stress source:

- Q355 accident bending: `288.639968 / 362.0034 = 0.7973404890672298`
- Q355 accident tension+bending: `0.8245120550433136`, satisfies
- Q235 accident bending: `288.639968 / 257.466 = 1.1210799406523582`
- Q235 accident tension+bending: `1.1592838171512616`, not satisfied

The current input is classified as `non_steel_platform`, and `component_material_id("square_support", metadata)` resolves to `q355`. Therefore this diagnostic does not reproduce the coworker/manual over-limit result under the current 4210 material rule. It does reproduce over-limit if the same stresses are evaluated as Q235.

## Conclusion

The unit raw result-extraction command stream itself is not the root cause of the `100-100-8 > 1.0` discrepancy. The remaining reconciliation needs the exact coworker-used command stream and/or evaluation workbook cells, with special attention to whether the coworker evaluated 4210 square support as Q235 instead of the current non-steel-platform Q355 rule.
