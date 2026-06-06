# Stage 4 Test Report

Executed Stage 4 verification:

```powershell
pytest -q
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
powershell -ExecutionPolicy Bypass -File scripts\stage4_self_check.ps1
```

Observed result:

- `pytest -q`: passed on 2026-05-15.
- `pytest --collect-only`: 210 collected tests.
- `scripts/stage4_self_check.ps1`: passed with 91 collected tests after adding the ANSYS candidate selector.
- Hardcoded sample token scan under `core`, `apps`, and `templates`: no matches.
- `scripts/stage4_prepare_real_run.ps1`: generated `jobs/s2_real_run_candidate` in dry-run mode with `preflight_status = pass` and `executed = false`.
- `scripts/find_ansys.ps1`: generated `docs/ansys_discovery.json`, found 56 candidates, selected none automatically, and did not execute ANSYS.
- `scripts/select_ansys_candidate.ps1`: covered by unit tests and self-check using a temporary discovery file; it writes only a dry-run TOML config and does not execute ANSYS.
- Default real output directory `E:\CODEX\tray_platform\ANSYS Output` was checked; no files were listed at the time of this patch.

Covered checks:

- Test count is at least 60.
- Real-run guard rejects missing config, missing confirmation, non-real mode, missing executable, failed preflight, and blocked job states.
- Real output validator detects required `.LIS` / `.oup` files and figures.
- Real output importer writes validation/import manifests and can assemble `result.json`.
- Imported output report generation writes `report.docx`, `report_audit.json`, and `report_reference_comparison.json`.
- API rejects real-run requests without explicit confirmation.
- ANSYS discovery is read-only and writes a discovered dry-run config only for a single candidate.
- ANSYS candidate selection is explicit, 1-based, and refuses to overwrite `config/ansys.local.toml` without `-Force`.
- Real-run guard also requires `spectrum_config_confirmed = true`.
- Real output import defaults to `E:\CODEX\tray_platform\ANSYS Output` and writes `imported_outputs_manifest.json`.
- Real output validation rejects files containing CableTrayAI mock markers.
- Hardcoded sample token scan has no matches under `core`, `apps`, or `templates`.
- Square tube auto-selection is now covered by tests. A blank intake column I records `auto_selection_required`, and the one-click workflow blocks formal calculation until candidate square `*.SECT` sections are tried by real ANSYS and the selected candidate has controlling ratio `< 1.0` closest to `1.0`.
- Source-conflict resolution is covered by tests and writes `source_conflict_resolution_audit.json` for historical report reproduction patches.
- Real ANSYS train gate passed `15/15` case-level runs.
- Real ANSYS hold-out gate passed `20/20` case-level runs.
- ANSYS post-only figure export passed for the same calibrated batches:
  - train: `15/15` jobs exported named PNG figures, `29` to `41` figures per job.
  - hold-out: `20/20` jobs exported named PNG figures, `29` to `41` figures per job.
  - outputs are recorded in `docs/precision_gate/figure_export_batch_real_precision_batch_train.json` and `docs/precision_gate/figure_export_batch_real_precision_batch_validation.json`.
  - each job now has `figure_export_audit.json`, `figure_export_command.json`, `generated_post_figure_export.mac`, and updated `figures_manifest.json`.

Most recent local checks:

```powershell
python -m pytest -q
python -m pytest --collect-only
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Results:

- `python -m pytest -q`: passed.
- collected tests: 281.
- hardcoded sample token scan: no matches.

Additional figure-export check:

```powershell
python -m pytest tests/unit/test_figure_export.py tests/unit/test_ansys_runner_modes.py -q
powershell -ExecutionPolicy Bypass -File scripts\export_ansys_figures.ps1 -BatchJson docs\precision_gate\real_precision_batch_train.json -TimeoutMinutes 30
powershell -ExecutionPolicy Bypass -File scripts\export_ansys_figures.ps1 -BatchJson docs\precision_gate\real_precision_batch_validation.json -TimeoutMinutes 30
```

Results:

- targeted tests: passed.
- train figure export: `15/15` success.
- hold-out figure export: `20/20` success.

2026-05-17 guarded calibration-policy check:

```powershell
python -m pytest -q tests\unit\test_report_baseline.py
python -m pytest -q tests\unit\test_intake_as_new_runner.py tests\unit\test_report_baseline.py
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
powershell -ExecutionPolicy Bypass -File scripts\run_intake_as_new_report_precision_batch.ps1 -ReportNumber 18185NI-LXSJ4120,18185NI-LXSJ4126,18185NI-LXSJ4128,18185NI-LXSJ4225,18185NI-LXSJ4249 -Nproc 1 -TimeoutMinutes 120 -NoPublish
```

Results:

- report-baseline unit tests: passed, including `LS-FORCE.LIS` audited baseline-conflict exclusions.
- intake-as-new runner + baseline tests: passed.
- full pytest suite: passed with `281` collected tests.
- hardcoded sample token scan: no matches under `core`, `apps`, or `templates`.
- representative real ANSYS report-level smoke batch: `5/5` passed.
- batch max effective gate error: `0.004990731571029472`, below the `0.01` gate.
- historical report conflicts in `18185NI-LXSJ4126` and `18185NI-LXSJ4128` remain visible in comparison artifacts and are excluded only from the historical numerical gate. They do not alter ANSYS output, formulas, Excel evaluation, or new-intake production logic.

2026-05-18 post-processing validity hardening:

```powershell
python -m pytest -q tests\unit\test_postprocessor_alignment.py tests\unit\test_result_validity_gate.py tests\unit\test_result_source_map.py tests\unit\test_section_specific_export.py tests\unit\test_apdl_renderer.py tests\unit\test_intake_standard_family_renderer.py
python -m pytest -q tests\unit\test_dashboard_html.py tests\unit\test_result_requirements.py tests\integration\test_api_stage3.py tests\integration\test_api_stage4.py
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Results:

- post-processing and validity gate tests: `23/23` passed.
- dashboard/API focused tests: `19/19` passed.
- full `python -m pytest -q`: passed.
- hardcoded sample token scan: no matches under `core`, `apps`, or `templates`.
- `source_materials` git status: clean.
- real ANSYS regression on `18185NI-LXSJ4157` completed with `result_validation.status = pass`.
- `TMAXBEAMSTRESS.LIS` now contains non-zero cantilever rows; `postprocessor_alignment_audit.json` records the `H1` injection and the parameterized tray-arm selector.
- validity gate now fails rows that contain no parseable numeric values, the same as all-zero rows.
- required figure manifests carry `image_quality`; blank-like required figures fail publication.

2026-05-18 disk-capacity protection and report smoke repair:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\cleanup_solver_artifacts.ps1
python -m pytest -q tests\unit\test_solver_artifact_cleanup.py tests\unit\test_report_baseline.py tests\unit\test_analysis_scope.py tests\unit\test_result_validity_gate.py
python -m pytest -q tests\unit\test_figure_export.py tests\unit\test_template_report_injector.py tests\integration\test_report_consistency.py tests\integration\test_report_template_upgrade.py
python -m pytest -q
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Results:

- E: drive free space restored to about `806 GB`.
- no active `ANSYS252.exe` / `ANSYS.exe` batch process remains; only `ansyslmd.exe` license service and the dashboard server are running.
- `core.ansys.artifact_cleanup.cleanup_heavy_solver_artifacts` now removes only regenerable heavy solver caches (`.rst`, `.mode`, `.full`, `.emat`, `.esav`, `.db`, `.page`, `.mntr`, `.rdb`, `.ldhi`) after parsing/publishing.
- operator one-click, intake-as-new report validation, full-report validation, real precision batch, and square-section trial runs now record `solver_artifact_cleanup_status` / removed GB.
- required figure filtering now accepts BMP source files when the requirement names the published PNG target, preventing empty modal/stress figure manifests after mock/real export.
- template report injection falls back from `mixed_beam_type_1` to `square_support`/`support` when a legacy or unit-test result uses older component names.
- targeted tests passed: `34/34` and `9/9`.
- full `python -m pytest -q`: passed.
- hardcoded sample token scan: no matches under `core`, `apps`, or `templates`.
