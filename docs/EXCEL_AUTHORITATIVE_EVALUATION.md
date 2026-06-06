# Excel Authoritative Evaluation

Production evaluation can use job-local copies of existing Excel workbooks when Python formula replication is incomplete.

Rules:

- Original workbooks under `source_materials` are never modified.
- Each job uses `jobs/<job_id>/evaluation_workbooks/`.
- If Excel COM is unavailable, evaluation is blocked and cannot authorize final pass.
- Results are written to `excel_evaluation_results.json`.

This stage provides the safe wrapper and blocker reporting. Exact production cell mappings remain in `EXCEL_CELL_MAPPING_FOR_PRODUCTION.md`.
