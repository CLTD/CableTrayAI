# Delivery Review 2026-05-20

## Scope

This delivery closes three review items:

1. Historical report/source conflict analysis for the 15 audited conflicts and the 24 remaining post-validation mismatches.
2. `CableTrayAI Job JSON v1` as the structured intake contract for future multi-department collaboration.
3. Template-preserving report injection sample for one verified job.

## Generated Review Artifacts

Desktop review files:

- `C:\Users\duxy\Desktop\duxyb\CableTrayAI_历史报告冲突原因分析.pptx`
- `C:\Users\duxy\Desktop\duxyb\18185NI-LXSJ4120_template_injected_report.docx`
- `C:\Users\duxy\Desktop\duxyb\18185NI-LXSJ4120_template_injected_report.pdf`
- `C:\Users\duxy\Desktop\duxyb\18185NI-LXSJ4120_template_report_audit.json`

Repository files:

- `docs/HISTORICAL_REPORT_CONFLICT_ANALYSIS.md`
- `data/schemas/cabletray_job_v1.schema.json`
- `data/schemas/cabletray_job_v1.example.json`
- `docs/CABLETRAYAI_JOB_JSON_V1.md`
- `scripts/build_validation_review_deck.py`
- `tests/unit/test_job_json_v1_schema.py`

## Validation

Commands run:

```powershell
python -m pytest -q tests\unit\test_job_json_v1_schema.py tests\unit\test_template_report_injector.py tests\unit\test_report_baseline.py
python -m pytest -q
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Results:

- Focused tests: passed.
- Full test suite: passed.
- Hardcode scan: no matches in `core`, `apps`, or `templates`.
- Template report audit: `pass`, 22 replacements, no warnings.
- Word COM PDF export: succeeded for the sample report.

## Engineering Position

The 15 audited conflicts are not part of the remaining 24 mismatches. They are retained as historical report/source conflicts with evidence and should be reviewed by the discipline owner.

The remaining 24 are not treated as passed. They remain post-validation review cases and must not be resolved by forcing generated results to match old reports. If a case is traced to software logic, the relevant parser, command renderer, evaluator, or template injector must be fixed; otherwise it remains a documented source/report conflict.

`CableTrayAI Job JSON v1` is the preferred long-term intake contract. Local ANSYS remains the calculation backend for the current release.
