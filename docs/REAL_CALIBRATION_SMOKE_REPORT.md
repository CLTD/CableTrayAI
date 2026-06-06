# Real Calibration Smoke Report

## 18185NI-LXSJ4120

- Command workspace: `jobs/calibration_workspaces/18185NI-LXSJ4120`
- Required command files generated:
  - `01_build_model.PIP`
  - `02_solve.mac`
  - `03_extract.mac`
  - `04_visualize.mac`
- Real ANSYS status: success
- Return code: 0
- Parsed results:
  - modal: 10
  - beam stress: 12
  - weld force: 2
  - bolt force: 2
  - foundation loads: 3
- Report comparison: 44/44 pass within 1%

## 18185NI-LXSJ4122

- Command workspace: `jobs/calibration_workspaces/18185NI-LXSJ4122`
- Real ANSYS status: success
- Initial parser issue: `HF-FORCE.LIS` may be absent for some command streams; result assembler now records missing files instead of crashing.
- Report comparison now uses deterministic table/source mapping and no longer chooses the nearest numeric value.
- `TMAXBEAMSTRESS.LIS` maps to 支架托臂应力评定 by command selector `ESEL,U,SEC,,1`.
- 托臂根部焊缝评定 maps to `TMAXBEAMSTRESS.LIS` and report coefficient `0.526`.
- 支架方钢 rows now use the new audited `SQUAREBEAMSTRESS.LIS` section-1-only output. The previous all-section `MAXBEAMSTRESS.LIS` is no longer accepted for those rows.
- Parser unit fix: wide PIP stress tables are Pa even when small values are below the old heuristic threshold.
- Current report comparison: pass, 84/84 fields within the gate; `max_gate_error = 0.00543`, below the 0.01 limit.
- Some rounded report ratios such as `0.01` naturally show high relative percentage error; the gate for ratio rows is absolute ratio error, while stress/load/modal values use relative error.

## Current Status

The 1% precision target is not yet met for the full selected batch. The system now exposes the real blockers instead of claiming reliability:

1. ANSYS command path bug fixed by using absolute `-i`, `-o`, and `-dir` paths.
2. Required legacy command files are generated.
3. Formula source audit is in place.
4. Real ANSYS smoke cases now pass for `18185NI-LXSJ4120` and `18185NI-LXSJ4122` under deterministic mapping.
5. Batch validation still needs the full 15 training and 20 hold-out run before UI release.
