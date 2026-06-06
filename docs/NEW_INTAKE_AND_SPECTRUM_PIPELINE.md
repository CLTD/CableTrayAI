# New Intake And Spectrum Pipeline

Production jobs can be created from a key/value intake workbook, CSV, or a tabular intake workbook whose row/column layout varies by project.

Required intake fields:

- `project_code`
- `building`
- `area`
- `elevation`
- `damping_ratio`
- `material`

The builder writes `jobs/<job_id>/input.json` and `job_creation_audit.json`.

For tabular workbooks the parser no longer depends on a fixed row number. It scans every sheet for header aliases, then keeps only rows that look like calculation tasks:

- support type aliases: `支架形式`, `支架类型`, `类型`, `支架`
- report/batch aliases: `力学报告号`, `力学计算结果`, `计算批次`, `报告号`, `提资单号`
- location aliases: `厂房`, `区域`, `生根层`, `生根楼层`, `标高`, `楼层`
- geometry/load aliases: `间距`, `跨距`, `长度`, `托盘载荷`, `载荷`, `荷载`
- square section aliases: `埋件`, `埋板`, `建议计算方钢`, `抗震计算后方钢尺寸`

Note rows and calculation instruction blocks are ignored unless they also contain a recognizable support type and enough location/load fields to form a real task. Values such as `+8.5m&+4.8m` are stored as `elevation_raw` plus `elevation_candidates`; the first value is used by default, and the web page lets the operator choose another candidate or type an override before calculation.

Formal report number / calculation batch is optional for new intake. When it is absent, the platform uses a provisional intake identity based on source workbook, sheet, and row. Later, after the report number is manually assigned in the intake workbook, the reconciliation script re-reads the workbook, binds the formal number to the existing job, and can republish the clean result folder under the formal number.

Spectrum configuration must be confirmed before real ANSYS is allowed. Steel-platform rows use the static method, but the selected spectrum workbook is still required to derive the SL-1/SL-2 peak acceleration coefficients used by the static load steps.

The dashboard also previews segmented spectrum workbooks before calculation. It lists discovered spectrum sheets/buildings and elevations, so the selected intake row can auto-fill factory/elevation while still allowing manual correction when the project workbook uses a different naming convention.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\confirm_spectrum_config.ps1 -JobId <job_id>
```

Complex spectrum workbooks should first receive a draft config using `core.spectra.config_wizard.draft_spectrum_config`, then be reviewed by a human.

After a report number is added to the workbook:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\reconcile_report_numbers_from_intake.ps1 -JobsDir jobs -IntakePath <updated_intake.xlsx> -PublishResults
```
