# Real Output Import Guide

Stage 4 supports importing a directory that was already produced by ANSYS outside the platform.

This mode never launches ANSYS. It copies and validates existing output files, then uses the same parser, evaluator, and report builder as the normal job flow.

Expected parser inputs:

- `MAXBEAMSTRESS.LIS`
- `TMAXBEAMSTRESS.LIS`
- `JCZH.LIS`
- `HF-FORCE.LIS`
- `LS-FORCE.LIS`
- `Mode.oup`
- BMP/PNG figures such as modal plots and stress plots

Optional retained files:

- `.out`
- `.err`
- `.rst`

Command:

```powershell
scripts\import_real_outputs.ps1 -JobId <job_id> -BuildReport
```

Default source directory:

```text
outputs
```

Override the source directory when needed:

```powershell
scripts\import_real_outputs.ps1 -SourceDir <external_ansys_output_dir> -JobId <job_id> -BuildReport
```

Outputs written under `jobs/<job_id>/`:

- `real_output_validation.json`
- `imported_outputs_manifest.json`
- `real_output_import.json`, retained as a compatibility alias
- copied `.LIS`, `.oup`, image, `.out`, `.err`, `.rst` files
- `result_raw.json`
- `result.json`
- `figures_manifest.json`
- `evaluation_summary.json`
- `report.docx`, when `-BuildReport` is used
- `report_audit.json`, when `-BuildReport` is used

`result.json` includes `result_source.type = external_real_output_import` so imported outputs are not confused with runner output.

Mock protection:

- Import validation fails if parser input files contain CableTrayAI mock markers.
- The importer does not call `run_mock_ansys`.
- The importer does not call real ANSYS.
