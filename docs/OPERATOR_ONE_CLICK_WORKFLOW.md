# CableTrayAI Operator One-Click Workflow

This page is for the normal operator workflow. Baseline comparison is a developer calibration gate, not a step that every operator should run.

## Entry

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_dashboard.ps1
```

Open:

```text
http://127.0.0.1:8000/dashboard
```

## Main Workflow

1. Upload the intake Excel file.
2. Select the spectrum workbook for the current project. Steel-platform rows use the static method, but the same project spectrum workbook is still required so the equivalent-static acceleration coefficients are traceable.
3. Select the result output root folder. The default is `outputs` under the selected deployment directory.
4. Let the platform auto-discover ANSYS. Discovery is read-only and never executes ANSYS.
5. Click one-click calculation.

## Automatic Rules

- Jobs are created from report number / calculation batch / intake order fields in the intake workbook.
- New intake workbooks do not have to contain a report number or calculation batch at calculation time.
- Before the formal number exists, jobs use a provisional identity based on the intake sheet and serial row, for example `<workbook>_<sheet>_row_<serial>`.
- After the report number/calculation batch is manually added to the intake workbook, run `scripts/reconcile_report_numbers_from_intake.ps1 -PublishResults` to bind existing jobs to the formal number and publish to `<output_root>/<report_number_or_calculation_batch>/`.
- Rows that explicitly mention steel platform use the static method, but still need the selected project spectrum workbook so the static SL-1/SL-2 peak acceleration coefficients can be derived and audited.
- A new intake does not need a formal report number or calculation batch at upload time. The job is created under a provisional intake identity. After the formal report number is added to the intake workbook, run the reconciliation step to bind that number to the existing job and output folder.
- Rows that do not mention steel platform use the response-spectrum method and must have a spectrum workbook selected.
- Intake column I is treated as the square-tube section. If it is blank, the platform runs candidate square sections inside the intake allowed list and chooses a section whose controlling ratio is `<= 1.0`; the normal economy target is `0.60 <= ratio <= 0.9999`, with at most two candidate trials.
- The selected section is written back to the job-local `input.json` and `generated_model.mac`; the original intake and `source_materials` are not modified.
- ANSYS must be run for formal results. If ANSYS discovery, preflight, spectrum confirmation, or section selection fails, the job fails instead of switching to mock.

## Hidden From The Operator Main Screen

These remain development or audit tools:

- manual report baseline comparison;
- real-output directory import;
- report.docx generation;
- row-number-only job creation;
- manual typing of intake sequence numbers.

## Reliability Gate

Developer calibration still requires comparison against existing reports within `1%` for the mapped result fields. The comparison must use report table captions, APDL/PIP extraction command selections, and output file names. It must not choose whichever LIS value is numerically closest.
