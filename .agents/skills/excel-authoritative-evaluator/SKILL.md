---
name: excel-authoritative-evaluator
description: Use job-local copies of authoritative Excel evaluation workbooks when Python formulas are incomplete.
---

# Requirements

- Never modify source workbooks.
- Copy evaluation workbooks into each job.
- Excel COM unavailable means blocked, not passed.
- Export `excel_evaluation_results.json`.
