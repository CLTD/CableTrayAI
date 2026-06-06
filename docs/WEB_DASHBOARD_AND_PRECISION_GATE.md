# Web Dashboard And Precision Gate

- current_reference_batch: `docs\precision_gate\intake_as_new_report_precision_batch.json`
- status: pass
- case_count: 5
- passed_case_count: 5
- failed_case_count: 0
- max_gate_error_percent: 0.4990731571029472
- tolerance_percent: 1.0

## Gate Policy

- Standard command streams, deterministic/spec formulas, and job-local Excel authoritative evaluation are the production authority.
- Historical reports are calibration and conflict-discovery references, not the sole authority.
- Audited historical report conflicts remain visible in comparison data but are excluded from the historical numerical gate only after evidence is recorded.
- Conflict exclusions never alter ANSYS output, formulas, Excel evaluation, or new-intake production logic.

## Output Policy

- The dashboard reads `docs/precision_gate/precision_dashboard_data.json` through the API endpoint `/dashboard-data`.
- Published result folders use a clean review layout: `command_streams`, `tables`, `figures`, and `raw_results`.
- Published result folders do not contain workflow JSON, Markdown, ANSYS `.out` logs, or `.err` logs.
- The only `.mac` files in each published result folder are the three engineering review command streams: modeling, calculation, and result extraction.
- Figure publishing follows `figures_manifest.json`; unrelated QA/signature or extra cloud images are not copied.
- Square tube outer width `<= 120 mm` publishes TB/TD cantilever cloud figures. Width `> 120 mm` does not publish TB/TD and uses weld-evaluation-principle appendix mode.

## Web UI Contest Position

- The dashboard presents CableTrayAI as an AI-assisted engineering design and quality-control platform for the `人工智能工程设计应用` competition direction.
- AI features are framed as intake parsing, rule audit, source traceability, anomaly diagnosis, economical-section suggestion, and source/report conflict review.
- AI does not replace ANSYS, APDL, Excel, or confirmed formulas.
