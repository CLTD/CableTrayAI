# Demo Real ANSYS Validation - 2026-06-04

## Scope

This validation was run before the department demo using real ANSYS, not mock output.

- Intake: `C:\Users\duxy\Desktop\duxyb\1818 S2支架需求汇总20240711 - 副本.xlsx`
- Spectrum: `source_materials/model_commands/上游专业提资/楼层谱1818 ANSYS格式 标高线性.xlsm`
- Run root: `jobs/demo_real_validation_20260604_003152`
- Status file: `docs/production_runs/full_intake_compute_status.json`
- Result file: `docs/production_runs/full_intake_compute_result.json`

## Representative Rows

| Job | Status | Selected section | Chapter 6 controlling ratio | Figures | Appendix C stress figures | Model figure mixed into Appendix C | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 18185NI-LXSJ4210 | pass | 100-100-6 | 0.688072 | 22 | 8 | 0 | DW lateral/moment zero is accepted only under symmetric self-weight check. |
| 18185NI-LXSJ4211 | pass | 100-100-6 | 0.826207 | 22 | 8 | 0 | Square-section trial ratio matches final Chapter 6 ratio. |
| 18185NI-LXSJ4212 | pass | 100-100-6 | 0.311342 | 22 | 8 | 0 | Minimum allowed section selected for light load. |
| 18185NI-LXSJ4213 | pass | 100-100-6 | 0.708817 | 22 | 8 | 0 | Six-layer MT policy passed; `modal_mt_cutoff` recorded `mt_mode=160`. |
| 18185NI-LXSJ4214 | pass | 100-100-6 | 0.367813 | 22 | 8 | 0 | Static steel-platform case passed output and report gates. |

## Gates Confirmed

- `required_file_JCZH.LIS`, `LS-FORCE.LIS`, `MAXBEAMSTRESS.LIS`, `TMAXBEAMSTRESS.LIS`, and `Mode.oup` exist for each run.
- Beam stress, foundation loads, connection loads, and cantilever stress rows are non-zero where the section branch requires them.
- MT cutoff is checked from `Mode.oup` after the command-flow selected mode count; it is not back-filled from the report.
- For square tube outer width `<= 120 mm`, Appendix C uses cantilever stress cloud output and the equivalent weld-stress table branch with coefficient `0.526`.
- Fig. 5.1 and Fig. 5.2 are checked as distinct model images.
- Square-section trial controlling ratio must match the final Chapter 6 controlling ratio within the gate tolerance.

## Current Release Notes

- Progress/status/result JSON writes are atomic to avoid blank pages or half-written status files during long ANSYS runs.
- Live ANSYS monitor callbacks cannot move a finished parse/publish stage back to `running_ansys`.
- Section selection uses the intake-approved section list and engineering estimate only for candidate ordering; it does not invent unavailable sections.
- The deployment package excludes old `jobs`, `uploads`, `outputs`, logs, caches, and local machine config to prevent stale results from affecting new intakes.
