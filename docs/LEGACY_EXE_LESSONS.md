# Legacy EXE Lessons

Release directory: `C:\Users\duxy\Desktop\tray_platform_onefile_release`
Status: `pass`

## Required Command Files

- `01_build_model.PIP`
- `02_solve.mac`
- `03_extract.mac`
- `04_visualize.mac`

## Workflow To Preserve

- Build a case library from intake Excel and historical reports.
- Generate command streams per case instead of asking the operator to write rows manually.
- Run real ANSYS MAPDL through a master macro.
- Compare generated command streams, extracted results, and report values before releasing UI changes.
- Use train samples for calibration and hold-out samples for validation.

## Calibration Counts

- Training cases: 50
- Validation cases: 20
- Legacy threshold: 5% in the archived release; current CableTrayAI gate is stricter at 1%.

## Current Policy

The current project must treat 1% report/result comparison as the release gate. Values beyond 1% are blockers, not warnings.
