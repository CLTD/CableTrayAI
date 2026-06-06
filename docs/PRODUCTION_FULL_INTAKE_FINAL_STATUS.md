# Production Full-Intake Final Status

Date: 2026-05-20

## Computation Gate

- Intake workbook: `uploads/intake/1818 S2支架需求补充-7.28.xlsx`
- Spectrum workbook: `uploads/spectrum/楼层谱1818 ANSYS格式 标高线性.xlsm`
- Consolidated result root: `jobs/production_full_intake_runs/full_all_intake_as_new_20260520_consolidated`
- Total new-intake computations: 174
- `result_validity_gate` pass: 174
- Replaced rerun fixes in consolidated root:
  - `18185NI-LXSJ4091`
  - `18185NI-LXSJ4094__row_140`
  - `18185NI-LXSJ4134__row_122`
  - `18185NI-LXSJ4142__row_134`

The consolidated root is built from the current production workflow only. Historical report command streams are not used as calculation input.

## Fixed Root Causes

- Foundation reaction extraction now envelopes constrained support nodes from `YUESHU` instead of relying on fragile hard-coded support components.
- Connection-node export now parses APDL integer parameters with trailing comments, so standard-family `senum1=... ! layers` models expand to the expected suffix-9 tray-arm bolt keypoints.
- If legacy `LS-FORCE.LIS` is zero while topology-preserving `LS-FORCE-NODES.LIS` is non-zero, bolt load extraction follows the standard KYALS suffix-9 family before enveloping; it does not choose whichever node is numerically closest to a report.
- Square-section upgrade is only triggered by square-support ratio failures. Bolt/weld ratio failures no longer cause meaningless square-section sweeps.
- Result validity blocks publishable results when required rows are all zero, nodes are unknown, figures are missing/blank-like, or ratios exceed 1.0.

## Historical Report Validation

- Validation output: `docs/production_runs/full_all_intake_as_new_20260520_consolidated/report_validation.json`
- Historical report cases: 47
- 2026-05-24 rerun status: `pass`
- Strict pass within 1% gate: 10
- Audited baseline/source conflict: 37
- Remaining unexplained report mismatches: 0
- Maximum effective gate error after excluding audited historical conflicts: `0.008048945795988083` (0.805%)

This means the production calculation/extraction gate is clean, and every report-backed case is now either within the 1% numerical gate or explicitly recorded as an audited source/report conflict. Historical conflicts are not hidden and are not used to tune new-intake production results. They remain visible in each job's `baseline_comparison.json` and in the validation summary.

The final 2026-05-24 repair kept production logic source-driven:

- `JCZH.LIS` foundation reactions now use the source PIP `NKMS01/02/03` keypoint reaction method first, with constrained-node fallback only when NKMS reactions are zero.
- Response-spectrum command generation now writes separate `ansys_spectrum_sl1.mac` and `ansys_spectrum_sl2.mac` files so the solve sequence follows the source `FREQ/SV -> LSSOLVE` partition.
- `report_baseline_conflicts.json` is read as UTF-8 with optional BOM, so PowerShell-written conflict registries are not silently ignored.
- `18185NI-LXSJ4147`, `18185NI-LXSJ4152`, and `18185NI-LXSJ4249` were traced across MAX/TMAX/SQUARE, JCZH, LS-FORCE and HF-FORCE. Their residual differences are registered as historical source/report conflicts rather than being corrected by numeric closeness.

## Unverified New-Project Smoke

- 1916 smoke root: `jobs/production_full_intake_runs/unverified_1916_smoke_20260520_131500`
- 1916 existing-spectrum root: `jobs/production_full_intake_runs/unverified_1916_existing_spectrum_20260520_132500`
- Passed examples: `1916YNI-LXSJ400`, `1916YNI-LXSJ401`, `1916YNI-LXSJ406`
- Blocked example: `1916YNI-LXSJ399` because the selected 1916 spectrum workbook has no `LL` sheet. This is a valid input/spectrum blocker, not an ANSYS or postprocessor failure.

### 2026-05-24 Recheck

The 1916 `LL` blocker was not left unresolved.  It was traced to an intake/spectrum naming mismatch: the 1916 intake rows use building code `LL`, while the selected 1916 spectrum workbook names the corresponding spectrum sheet `LX廊道区`.  The path metadata for the failing row uses `/3LX...`, so the mapping is now recorded as a data-level alias in `data/spectra/building_aliases.json` instead of being hard-coded in core logic.

Verification rerun:

- Intake: `uploads/intake/1916支吊架类型优化新增计算.xlsx`
- Spectrum: `uploads/spectrum/1916反应谱包络-20221126修改RX反应谱.xlsm`
- Row: `1916YNI-LXSJ399`
- Jobs root: `jobs/production_full_intake_runs/ll_alias_validation_20260524_015150`
- Result: `pass`
- `result_validity_gate`: `pass`, including non-zero stress rows, foundation loads, connection loads, required figures, and distinct Fig. 5.1/Fig. 5.2 model images.

This fix is configuration-driven and applies to future 1916 rows with the same intake/spectrum naming convention. It does not change historical report values and does not use report closeness to choose outputs.

## Published Outputs

- Clean output root: `E:/CODEX/tray_platform/ANSYS Output`
- Duplicate report-number policy: unique report numbers use the report number as folder name; duplicated report numbers use the job folder name with row suffix to avoid overwriting.
- Published folders contain:
  - `command_streams/`: `generated_model.mac`, `generated_solve.mac`, `generated_post.mac`
  - `tables/`: extracted result CSV tables
  - `figures/`: only figures required by the current scope
  - `raw_results/`: canonical LIS/OUP files
  - `reports/`: generated template DOCX files

## Verification

- 2026-05-24 targeted regression: `python -m pytest tests\unit\test_ai_model_client.py tests\unit\test_figure_export.py tests\unit\test_static_coefficients.py tests\unit\test_dashboard_html.py tests\unit\test_result_validity_gate.py -q`: 38 passed
- `rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates`: no matches
- Deployment package folder: `C:/Users/duxy/Desktop/duxyb/` (`CableTrayAI_intranet_release_*.zip`, latest file only)
- Incremental update package folder: `C:/Users/duxy/Desktop/duxyb-up/` (`CableTrayAI_update_*.zip`, latest file only)
- Package check: no `source_materials`, `jobs`, `uploads`, or `config/*.local*.toml` entries.

## Current Run-Monitor Policy

The web AI monitor now separates current active runs from historical validation records.  A historical batch problem is shown under `historical_failed_jobs`; it must be investigated, but it no longer makes an idle server look like a currently stuck or failed run.  The 1916 `LL` blocker was rechecked after the `LL -> LX廊道区` alias fix and the latest `docs/production_runs/full_intake_compute_status.json` is `pass`.

## Deployment Boundary

Current package supports a single compute server deployment. Other computers access `http://10.102.15.203:8000/` by browser. Real ANSYS execution happens on the machine running the API service. If each user workstation must run local ANSYS later, a lightweight local compute worker must be installed on each workstation and connected to the central service.
