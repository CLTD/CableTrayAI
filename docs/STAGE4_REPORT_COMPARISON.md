# Stage 4 Report Comparison

Stage 4 adds structural comparison between generated reports and the existing reference report.

The comparison is intentionally limited to report structure:

- generated heading count
- reference heading count
- matched reference headings
- missing reference headings
- path to the reference report, when found

The comparison file is written as:

- `jobs/<job_id>/report_reference_comparison.json`

Numeric consistency is not checked in this file. Numeric traceability remains in:

- `report_audit.json`
- `REPORT_FIELD_MAPPING.md`
- `result.json`
- `figures_manifest.json`

This keeps report wording/structure review separate from deterministic data validation.
