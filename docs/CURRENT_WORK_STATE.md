# CableTrayAI ??????

## 2026-07-09 mixed five-layer wide-tray short-segment section fix

Current source state:

1. User reviewed the `160-160-8` mixed five-layer model and found the 500/600 tray short arm segment still appeared as about `300 mm` instead of the expected `150 mm`.
2. Root cause was a second-level segment-assignment error in `core/apdl/mixed_tray_model.py`: `QALEN` and `QL3A` were already correct, but for 500/600 trays the line segment from bolt point `502` to short-tail start `503` was also assigned the short-section element type (`YIXINGGANG150DAN` / `CAOGANG42DAN`). Therefore the visible short-section length became bolt-to-end instead of tail-start-to-end.
3. Fixed the segmented arm assignment so:
   - for 500/600 trays, `502 -> 503` remains the main arm section and only `503 -> 504` is the short tail;
   - for 100/200 trays, the existing short-tail split stays unchanged;
   - for 300 trays, the existing special two-segment path stays unchanged.

Verification:

1. Targeted mixed-tray tests passed: `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py -q`.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. Fresh generated review files were written to `C:/Users/duxy/Desktop/mixed_five_tray_code_review_20260709_segment_fix`.
4. Segment summary now shows:
   - `160-160-8`: 600 short tail `0.15 m`, 500 short tail `0.15 m`, 300/200/100 short tail `0.15 m`.
   - `120-120-10`: 600 short tail `0.20 m`, 500 short tail `0.20 m`, 300/200/100 short tail `0.15 m`.
5. Real ANSYS18.2 model-only validation passed for 10 representative cases under `jobs/model_only_matrix_20260709_2230`: single-side single-layer 200, single-side double-layer 300, 600 with 120 and 160 square branches, double-side same-width 500 and 300, single-side mixed 500+600, single-side mixed 100+200, single-side five-width mixed 600+500+300+200+100, and double-side five-width mixed 100+200+300+500+600. Each job ran only `generated_model.mac`; `generated_solve.mac` and `generated_post.mac` were intentionally not called. All 10 produced nodes/elements with ANSYS error count `0`.
6. Deployment package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `447F5F4D2A1BC4E41D22C6449D24F2B040E416EB665F78F0A0809DE3383E1A85`, size `79,411,267` bytes. Package gate passed, including forbidden-path scan, runtime XML support files, and no-expat spectrum smoke.
7. Local `D:/CableTrayAI` was refreshed from the rebuilt package. Installed service smoke passed with `/health` returning `ok` and `duxyb/cnpe123` login returning `pass`. Source, desktop package, and installed hashes match for `core/apdl/mixed_tray_model.py`.

## 2026-07-09 mixed five-layer tray total arm length fix

Current source state:

1. User reported that the unit-copied deployment still generated wrong distances for the single-side mixed five-layer tray model.
2. Root cause was found in `ctai_layered_mixed_tray_standard`: the previous fix corrected the dynamic tail/L3 rule, but `QALEN` was still computed as `arm_a + dynamic_tail`. For 160-class sections this incorrectly shortened the total arm length of 600 mm trays from `0.67 m` to `0.62 m`, and 500 mm trays from `0.55 m` to `0.50 m`.
3. Fixed `core/apdl/mixed_tray_model.py` so explicit source total length is preserved first, and the branch-specific tail only changes the split between `QA` and `QL3A`.
4. Fixed `core/optimizer/square_section_selector.py` so final square-section replacement also refreshes topology-manifest `x_tail_m` when `l3_tail_m` changes.
5. Added regression assertions in `tests/unit/test_intake_standard_family_tray_widths.py` for both `120-120-10` and `160-160-8` branches.

Verification:

1. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
2. Installed-directory render verification from `D:/CableTrayAI` passed:
   - `120-120-10`: 600 `QA=0.47`, `QALEN=0.67`, `QL3A=0.20`; 500 `QA=0.35`, `QALEN=0.55`, `QL3A=0.20`; 300/200/100 `QALEN=0.35`, `QL3A=0.15`.
   - `160-160-8`: 600 `QA=0.52`, `QALEN=0.67`, `QL3A=0.15`; 500 `QA=0.40`, `QALEN=0.55`, `QL3A=0.15`; 300/200/100 `QALEN=0.35`, `QL3A=0.15`.
3. Full deployment package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `A12F08B273C042368E7B4B0A78F99DFD9C9F2E36F1C8F30B067D8951289E294A`, size `75.73 MB`.
4. Package gate passed: forbidden generated paths absent, runtime XML support files present, and no-expat spectrum smoke passed.
5. Local `D:/CableTrayAI` was refreshed from the rebuilt package. Service smoke passed: `/health` returned `ok`, and `duxyb/cnpe123` login returned `pass`.
6. Source, desktop package, and installed hashes match for the touched business files.

## 2026-07-07 mixed tray 500/600 versus 100/200/300 tail rule fix

Current source state:

1. User clarified the active physical tail rule: for `500-75-2` and `600-75-2`, square sections up to and including `120-120-10` use `50-42 + CAOGANG42DAN` with tail `0.20 m`; square sections above that use `YIXINGGANG150 + YIXINGGANG150DAN` with tail `0.15 m`.
2. For `100-75-2`, `200-75-2`, and `300-75-2`, the reviewed short-tail behavior remains `0.15 m` for both arm families.
3. Root cause found in the grouped source-style mixed renderer for `600/500/300`: the 300 mm group was incorrectly bound to the shared wide-tray `L5` variable. When the square section was `<=120`, this could make the 300 mm mixed group follow `L5=0.20` instead of its required `0.15`.
4. Fixed `core/apdl/mixed_tray_model.py` so the `600/500/300` grouped source-style path keeps `L5` only for 600/500 groups and lets 300 mm use its own numeric `0.15` tail.
5. Added explicit mixed source tail audit in `core/apdl/intake_standard_family_renderer.py` so reviewed single-side mixed source families record that `L5` applies only to 500/600, while 100/200/300 keep 0.15 even when APDL variable names differ by source family.

Verification:

1. Targeted tests passed for single five-width source audit, yixing branch, grouped 600/500/300 120-branch, grouped 600/500/300 yixing branch, and QL3A sync.
2. Full unit tests passed: `tests/unit` all green with the existing Pillow deprecation warnings only.
3. `py_compile` passed for touched APDL modules.
4. Render smoke confirmed: single five-width 120 branch has `L5=0.2` only for 600/500 policy, 300/200/100 tails audit as 0.15; grouped 600/500/300 renders `H1/2+L3-0.15` and no longer renders `H1/2+L3-L5`.
5. `git diff --check` reported only pre-existing CRLF normalization warnings in already dirty files.

Deployment closeout:

1. Full deployment package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `EBEE944A440CCB433DA3CD2479F371811E973DA7CEBC9CF4CA7E3F78EF701D88`, size `75.73 MB`.
2. Package gate passed after rebuild: forbidden paths absent, runtime XML support files present, and no-expat spectrum smoke passed.
3. The desktop expanded package is clean after local install: no `jobs/uploads/outputs/logs`, no `docs/paper`, no runtime auth session, and no local ANSYS/access-control config.
4. Local installed software at `D:/CableTrayAI` was refreshed from the package. Installed service smoke passed: `/health` returned `ok`, root HTTP returned `200`, and `duxyb/cnpe123` login returned `pass`.
5. Source/package/installed hashes match for the touched APDL renderer modules and deployment scripts.

Follow-up matrix validation:

1. Created static generated-command validation jobs under `jobs/mixed_tray_matrix_20260707_170849`.
2. Covered 20 mixed tray cases: single-side 100+200, 300+600, 500+600, 600+500+300, 600+500+300+200+100; double mirrored 100+200, 500+600, 300+500+600, 100+200+300+500+600; and double unbalanced 300+600 versus 100+500. Each case was rendered with both `120-120-10` and `160-160-8`.
3. Validation gates checked tray `SECREAD`, arm family, `SECOFFSET`, topology-manifest tail values, `Q/H CODE-L3A` arrays, the `H1/2+L3-L5` contamination guard for 300 mm groups, connector radius, and nonblank generated models.
4. Result: 20/20 cases passed. Summary is in `jobs/mixed_tray_matrix_20260707_170849/summary.json`; human-readable audit is in `jobs/mixed_tray_matrix_20260707_170849/MIXED_TRAY_TAIL_RULE_MATRIX_20260707.md`.

## 2026-06-19 4126 LS-FORCE clarification after user correction

Current clarification:

1. The user correction is accepted: `18185NI-LXSJ4126` should be treated as using the same generic S2 result-extraction stream, not as a case with a separate missing `03` command stream.
2. Rechecked `C:/Users/duxy/Desktop/Desktopuxyb/03 导出数据-S2.PIP`: it is still byte-identical to the curated generic `resources/current_type_command_flows/single_mixed_600_500_300_200_100/03_extract_s2.PIP`.
3. Rechecked the saved desktop 4126 model sources:
   - `C:/Users/duxy/Desktop/2/18185NI-LXSJ4126/计算文件/01双侧同类型电缆桥架-方钢300.PIP`
   - `C:/Users/duxy/Desktop/2/18185NI-LXSJ4126/计算文件/01双侧同类型电缆桥架-方钢300.PIP.bak`
   Both define physical bolt/round-bar keypoints `506/507/508` and `1506/1507/1508`, but do not define the generic post stream's suffix-9 LS-FORCE interface `509/609/709` and `1509/1609/1709`.
4. Therefore the unresolved 4126 load-table issue is not "actual production uses one post stream while validation uses another". It is a saved-model versus generic-post topology mismatch for the historical 4126 evidence currently available.
5. With the strict generic suffix-9 selector, the 4126 diagnostic snapshot gives zero LS-FORCE rows. A diagnostic-only `*09 -> *07` patch gives nonzero rows but still does not match the report load table. So `507/1507` must not be adopted as a production rule.

Decision:

1. Current production behavior remains correct: if a generated model lacks the suffix-9 interface required by the generic S2 post stream, traceability/publication must be blocked.
2. Do not claim that historical 4126 tray-arm connection loads are reproduced. The report values are present in the Word report, but the original raw LIS/DB evidence that produced them is not available in `C:/Users/duxy/Desktop/2/18185NI-LXSJ4126`.
3. Existing current-production coverage for representative 500, 300, 200, 600 and mixed-width cases remains accepted; 4126 remains an unresolved historical load-table reproduction case only.

## 2026-06-19 generic S2 post-extraction topology validation

Current source state:

1. User provided `C:/Users/duxy/Desktop/Desktopuxyb/03 导出数据-S2.PIP` as the generic S2 result-extraction stream. Its SHA256 is `39FC214B136A101F104559173A33081112338D7D60C9E2335C019F04D6E6E24A`, byte-identical to `resources/current_type_command_flows/single_mixed_600_500_300_200_100/03_extract_s2.PIP`.
2. The generated post template now keeps LS-FORCE on the standard suffix-9 `KYALS%I%` selector only. The unsafe `KYSEL` fallback to `KYALS%I%-3` and `KYALS%I%-101` was removed.
3. `core/results/result_assembler.py` now treats `LS-FORCE-NODES.LIS` suffix-6/7/8 physical bolt rows and suffix-2 CP interface rows as diagnostic only. Only suffix-9 rows may form a published tray-arm connection-load envelope. If suffix-9 is absent, publication remains blocked by the result gate.
4. Static command-flow audit matrix was written to `jobs/type_mix_command_audit_20260619_200315/summary.json`. It covers double same 100/200/300/500/600, single mixed 300+600, single mixed 600+500+300+200+100, double grouped 500+600 with 120/160 square sections, and double grouped 100+200+300+500+600.
5. Matrix outcome: source-family same-width jobs preserve `TYPE=1` / `TYPE=1 minus SEC=1` extraction; mixed jobs use `CTAI_TYPE1_ELEMS`, `CTAI_ARM_ELEMS`, and `CTAI_TRAY_ELEMS` component extraction. All cases had `ls_force_selector.status=pass` and no `KYSEL` / `KYALS%I%-3` / `KYALS%I%-101` tokens.

Verification:

1. Targeted post/result/tray-width tests passed: `78 passed`.
2. Full unit tests passed: `269 passed`.
3. `py_compile` passed for touched APDL/result/validation modules.
4. `git diff --check` passed with only pre-existing CRLF/LF normalization warnings on already modified files.
5. Detailed evidence is in `docs/GENERAL_POST_EXTRACT_TOPOLOGY_VALIDATION_20260619.md`.
6. Final recheck at `2026-06-19T20:12:16+08:00` passed targeted topology tests, full `tests/unit`, JSON integrity checks for the audit summaries, and confirmed `source_materials` remains unchanged.

Decision:

1. Keep the strict suffix-9 LS-FORCE publication policy. Do not publish suffix-6/7/8 physical bolt points or suffix-2 CP interface rows as formal connection loads.
2. If a future model lacks the suffix-9 interface required by the generic S2 post stream, the correct production behavior is to fail traceability/publication and retain diagnostic outputs.

Deployment closeout:

1. Full package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `D0B3223213FC41DE1A6143648AA7E30AF9927A1B169B48E733C36A27C79C7022`, size `79361379` bytes.
2. Package gate passed: forbidden paths absent, runtime XML support files present, and no-expat spectrum smoke passed.
3. Zip content scan passed: no `jobs/uploads/outputs/logs`, no cache directories, no `.pyc/.pyo`, and no local auth/ANSYS config files.
4. Local `D:/CableTrayAI` was installed from the rebuilt package, service started from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`, `/health` returned ok, root page returned HTTP 200, and `duxyb/cnpe123` login passed.
5. Source/package/install hashes match for the touched APDL template, result assembler, post alignment, LS-FORCE topology audit, intake renderer, and result gate.

## 2026-06-19 LS-FORCE hardening coverage validation

Current validation state:

1. Rechecked the 4126 LS-FORCE hardening after implementation. Direct topology audit shows the historical `18185NI-LXSJ4126_full_input` source model fails the standard suffix-9 interface check because `509/1509` are missing while legacy `506/507/508` physical bolt geometry is present. Current generated models for `18185NI-LXSJ4120` and production `18185NI-LXSJ4153` pass the same check.
2. Important boundary: the current hardening is useful for preventing a model/post mismatch and for blocking all-zero selected bolt-force envelopes, but it does not prove the historical 4126 `LS-FORCE.LIS` report values. The diagnostic `*09 -> *07` selector produced nonzero values but still did not match the report, so `507` must not be adopted as a production rule without the original department `03` post stream.
3. Re-summarized non-recent input-matched real ANSYS replays at a 5% gate in `jobs/input_matched_coverage_summary_20260619.json`. Accepted coverage includes `4115` 500 mm, `4118` 300 mm, `4156` 200 mm, `4249` 600 mm, `4151` 500+600 mixed, and `4228` historical 500 mm replay. `4126_full_input` remains failed only on `LS-FORCE.LIS`.
4. Current-code reparse check was run under `jobs/reparse_validation_20260619`. It copied existing real-output LIS files for `4126_full_input`, `4156` 200 mm, and `4151` 500+600 mixed, then reassembled them with the current parser/gate. `connection_load_values` passed with nonzero published `bolt_force_results` in all three copies; total result gates can still fail in these numeric replay copies only because full report figures were not copied/exported.
5. Verification passed: targeted LS-FORCE/tray-width/post/result tests returned 75 passed, full `tests/unit` passed, py_compile passed for touched modules, and `git diff --check` reported only pre-existing CRLF/LF normalization warnings.
6. Detailed evidence is in `docs/LS_FORCE_TOPOLOGY_AND_COVERAGE_VALIDATION_20260619.md`.

Decision:

1. Keep the current LS-FORCE hardening because it prevents the class of mismatched extraction errors and does not show evidence of confusing 100/200, 300, 500/600 logic.
2. Do not mark 4126 historical LS-FORCE as fully reproduced until the exact department `03` result-extraction stream or equivalent authoritative extraction point is available.

## 2026-06-19 4126 LS-FORCE topology hardening

Current source state:

1. Investigated the remaining `18185NI-LXSJ4126` full-input replay discrepancy. Main stress, modal and `JCZH.LIS` foundation loads already match the historical report; the unresolved item is only `LS-FORCE.LIS` tray-arm connection loads.
2. Root cause is not RCC-M evaluation or the main ANSYS solve. It is the model/post-processing interface: the historical 300 tray source model has physical bolt geometry through `506/507/508` and `1506/1507/1508`, but it does not expose the standard suffix-9 `509/1509` keypoint connector interface used by the shared S2 `KYALS` LS-FORCE selector.
3. Added `core/apdl/ls_force_topology.py` to audit the standard `509/1509` LS-FORCE interface independently from physical bolt geometry.
4. The 300 tray family score and physical-bolt audit now require both the `506/507/508` physical bolt lines and the standard `509/1509` LS-FORCE connector topology.
5. `postprocessor_alignment` now writes an `ls_force_selector` audit. If `generated_post.mac` uses the standard suffix-9 `KYALS` selector and `generated_model.mac` lacks the matching `509/1509` topology, traceability is failed instead of silently publishing a mismatched extraction.
6. `result_assembler` now marks an all-zero selected connection-node keypoint family as `selected_all_zero`; it no longer lets unrelated nonzero raw diagnostic nodes prove the selected published envelope is valid.
7. `result_validity_gate` now requires the final `bolt_force_results` envelope itself to be nonzero. Nonzero `LS-FORCE-NODES.LIS` rows with zero published bolt rows are treated as a topology mismatch and block publication.

Verification:

1. Direct 4126 source-model topology audit returns `fail`: missing `front_ls_force_keypoint_509`, `front_ls_force_connector_to_509`, `back_ls_force_keypoint_1509`, and `back_ls_force_connector_to_1509`; `legacy_physical_bolt_506_508_present=true`.
2. Targeted tests passed for 300 tray physical-bolt topology, LS-FORCE post alignment, connection-node selection, and result validation.
3. Full unit suite passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
4. `py_compile` passed for touched APDL/result/validation modules.
5. `git diff --check` returned only pre-existing CRLF warnings on already modified docs/cache/script files.

Decision:

1. Do not patch production LS-FORCE extraction to `507` for 4126. That diagnostic produced nonzero values but still did not match the historical report.
2. Treat the old 4126 source model as a historical source/post mismatch until the exact historical `03` post stream is available.
3. Current production must use model and post streams as a matched pair; mismatched LS-FORCE topology is now blocked generically.

## 2026-06-19 full input-matched high-error replay

Current validation state:

1. User requested the remaining high-error cases to be rerun with calculation inputs fully consistent and judged against an approximate `5%` acceptance idea.
2. Diagnostic batch root is `jobs/full_input_matched_high_error_20260619_180420`.
3. The diagnostic used desktop historical `01` model sources as `generated_model.mac`, desktop historical `02` solve sources as `generated_solve.mac`, stripped embedded solve tails from source models when present, and used the current standard S2 post stream aligned to the source model topology.
4. Real ANSYS18.2 completed successfully for `18185NI-LXSJ4126`, `4151`, and `4228`.
5. `18185NI-LXSJ4151` passes both `5%` and `1%` report comparison after full input matching. The previous mismatch was caused by comparing a current `500-only` generated model with a historical `600+500` source model.
6. `18185NI-LXSJ4228` passes both `5%` and `1%` report comparison after full input matching. The previous residual was caused by the historical report model using `L3=0.15`, while current production policy uses `L3=0.20` for `500 mm` tray with `120-120-8`.
7. `18185NI-LXSJ4126` main stress/modal/foundation values match after full input matching: stress max relative error is about `0.0327%`, modal max relative error is about `0.00002%`. It still fails due to `LS-FORCE.LIS` tray-arm connection loads.
8. `4126` LS-FORCE root cause is selector mismatch. Generic S2 post selected `*09` keypoints that do not exist in the source `300` model, giving all-zero LS-FORCE. A diagnostic-only patch to `*07` keypoints produced nonzero LS-FORCE, but still did not match the report, so the exact historical extraction point remains unresolved without the source `03` post stream.
9. Summary written to `docs/FULL_INPUT_MATCH_VALIDATION_20260619.md`.

Decision:

1. Treat `4151` and `4228` as input-matched precision accepted for this diagnostic.
2. Do not mark `4126` fully accepted until the source-family-specific `LS-FORCE` selector is corrected or the exact historical `03` extraction stream is available.
3. No production-code change or deployment package refresh was performed for this diagnostic.

## 2026-06-19 high-error input-matched baseline replay

Current validation state:

1. User requested the same input-matched method to be applied to other large-error desktop-folder-2 cases.
2. Diagnostic batch root is `jobs/input_matched_high_error_20260619_174851`.
3. Real ANSYS18.2 source-solve replays were run for `18185NI-LXSJ4115`, `4118`, `4156`, `4126`, `4151`, and `4228`.
4. `4115`, `4118`, and `4156` now pass strict baseline comparison after replaying the desktop source solve stream. Their previous large differences were calculation-input mismatches, not current deterministic evaluation errors.
5. `4126` remains failed because the generated model includes mixed `300/200` tray sections and CTAI mixed topology, while the historical source model/report is a `300-75-2mm` source-style model.
6. `4151` remains failed because the generated model is `500-75-2mm` only, while the historical source model/report is a `600-75-2mm + 500-75-2mm` mixed model with different layer/geometry variables.
7. `4228` improved from `64` failed comparisons to `16`, but the remaining difference traces to a historical source-model conflict: the report model uses `L3=0.15` for `500-75-2mm` with `120-120-8`, while current production rules lock this case to `L3=0.20`.
8. Summary written to `docs/HIGH_ERROR_INPUT_MATCH_VALIDATION_20260619.md`.

Decision:

1. The response-spectrum subset `4115/4118/4156` plus NR `4249` supports the conclusion that large historical stress mismatches disappear when calculation input is made consistent.
2. Do not claim all desktop-folder-2 baselines are clean. `4126`, `4151`, and `4228` need either input/model reconciliation or a developer-only historical replay policy.
3. No deployment/package refresh was performed for this diagnostic-only run.

## 2026-06-19 NR input-matched baseline replay

Current validation state:

1. User requested an NR-only rerun with calculation inputs made consistent before judging the remaining baseline difference.
2. The NR baseline sample used for this narrowed check is `18185NI-LXSJ4249`, because it is the NR case in the current representative desktop-folder-2 validation set with a report and source calculation stream.
3. Diagnostic job: `jobs/nr_input_matched_20260619_170940/18185NI-LXSJ4249_source_solve`.
4. The model input was checked against `C:/Users/duxy/Desktop/2/18185NI-LXSJ4249/计算文件/01双侧同类型电缆桥架-方钢托臂.PIP`; governing values match: `H1=0.14`, `H2=1.4`, `L1=0.67`, `L2=0.6`, `L3=0.15`, `L4=2.0`, `140-140-8`, `YIXINGGANG150/YIXINGGANG150DAN`, and `600-75-2mm`.
5. The diagnostic replayed the desktop source solve stream `02计算用命令流AR  8.55 7-10.mac`, which uses `MT=60` and embedded simplified `NR_1818@26.2` spectrum blocks, while production had used the controlled solve template with full workbook spectrum and `MT=80`.
6. Real ANSYS18.2 completed successfully. Numeric post outputs were assembled; figure export was intentionally skipped for this numeric replay, so `result_validation.json` fails only the required-figures gate.
7. With the source solve replay, governing stress/ratio values align with the report: faulted bending `289.308 MPa` vs report `289.32 MPa`, faulted tension+bending ratio `0.8167` vs report `0.82`.
8. The remaining comparison failures are limited to several SL-1 load-table components at about `3%` to `4%`, e.g. JCZH FY/MX and HF/LS FY. The desktop 4249 folder has no historical LIS files or separate `03` post command stream, so this residual cannot yet be proven as a current post-processing bug.
9. A dedicated summary was written to `docs/NR_INPUT_MATCH_VALIDATION_20260619.md`.

Decision:

1. For NR 4249, the large historical-report stress difference is caused by calculation-input mismatch, not by model generation or RCC-M evaluation.
2. The earlier "spectrum file does not satisfy" blocker is not an NR 4249 issue; it applies to the NB sample whose requested elevation has no acceptable common spectrum elevation in the selected workbook under the current no-snap-down policy.
3. Do not publish the full desktop-folder-2 baseline as fully accepted until historical LIS/post streams are available or the residual SL-1 load-table deltas are explicitly accepted as historical export drift.

## 2026-06-19 Desktop folder 2 baseline validation

Current validation state:

1. Used `C:/Users/duxy/Desktop/2` as the manual/unit-run baseline source and selected representative rows covering response spectrum, static method, same-width trays, mixed trays, 200/300/500/600 widths, and multiple square sections.
2. The aligned validation workbook/spectrum inputs were recorded under `jobs/baseline_desktop2_20260619_151733`.
3. Real ANSYS ran for rows `18,96,173,131,156,123,125,154` with provided square sections frozen so baseline comparison would not be distorted by the current smart selector.
4. Production real-run status after fixes:
   - Initial pass: `18185NI-LXSJ4115`, `4118`, `4126`, `4249`, `4156`.
   - Re-run pass after fixes: `18185NI-LXSJ4151`, `4228` at `jobs/baseline_desktop2_fixverify_20260619_154504`.
   - Input blocked: `18185NI-LXSJ4227` because the selected spectrum workbook has no common NB elevation satisfying the configured `>= +19.50m` policy.
5. Fixed a Windows status-file race in `scripts/run_production_full_intake_compute.ps1`; status JSON writes now use PID-suffixed temporary files with retry/backoff.
6. Fixed a result-gate false positive for symmetric double-side self-weight cases. `core/validation/result_validity_gate.py` no longer treats front/back cable label text as part of the self-weight symmetry signature, so vertical-only DW foundation reactions are accepted when geometry/load stacks match.
7. Added regression coverage in `tests/unit/test_result_validity_square_section.py`; targeted test passed with `9 passed`.

Baseline comparison status:

1. Strict historical report numeric comparison is not clean yet. Summary files are:
   - `jobs/baseline_desktop2_20260619_151733/baseline_validation_summary.json`
   - `jobs/baseline_desktop2_20260619_151733/baseline_validation_summary.md`
2. The comparison status is `fail` at `1%` tolerance for the sampled report set. This should not be reported as "no error".
3. Root cause is not ANSYS crash or missing post files in the fixed samples. The main mismatch is that some historical reports/standard command streams do not use the same input policy as current production:
   - Static reports such as `4126` and `4228` contain audited `ACEL` coefficients in their standard solve command streams that differ from the current workbook/current-elevation equivalent-static selection.
   - Response-spectrum report `4151` used a historical `MT=90`, while current production retried to `MT=100` to satisfy the `>50 Hz` Mode.oup gate.
4. Do not rebuild or publish a "fully baseline-matched" package from this validation alone. The next decision is whether to add a developer-only historical-baseline replay mode that freezes standard command-stream `ACEL`/`MT`, or to keep current production policy and record these historical report comparisons as input-policy conflicts.

## 2026-06-19 4218 grouped mirrored 500/600 L5 sync closeout

Current source state:

1. Fixed the grouped mirrored 500/600 final square-section replacement path for `ctai_grouped_mirrored_mixed_standard` models.
2. For the reviewed 4218-class grouped source-style APDL, `L3=0.6` and `L4=0.5` are tray-width variables, while `L5` is the wide-tray short arm/tail length that must follow the selected square section.
3. The locked rule is unchanged: tray width `<=300 mm -> 0.15 m`; tray width `>300 mm` with square outer `<=120 mm -> 0.20 m`; tray width `>300 mm` with square outer `>120 mm -> 0.15 m`.
4. The final selected `160-160-8` branch now rewrites `L5=0.15` for grouped mirrored 500/600 jobs, while preserving `L3=0.6` and `L4=0.5`.
5. Web model preview height, projection scale and legend wrapping were adjusted so the ANSYS model/command review area is easier to inspect and the legend no longer overlaps.

Verification:

1. Targeted square-section replacement regression passed for grouped mirrored 500/600 final selection.
2. Full unit suite passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. Frontend inline JavaScript syntax check passed for `apps/web/index.html`.
4. Real ANSYS18.2 validation passed for row 10 / `18185NI-LXSJ4218` at `jobs/verify_4218_l5_fix_20260619_104624`.
5. Real run selected `160-160-8`, generated `H1=0.160000`, `L3=0.6`, `L4=0.5`, `L5=0.15`, ANSYS status `success`, result validation `pass`, and controlling ratio `0.963156436189633`.

Closeout:

1. Full server, desktop, and installer runtimes were rebuilt.
2. Full installer package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `C770DDD3DB13CE8EDA4BC923C294C7E4CFE456F6F3A13F4F7C63803DDADBE372`, size `79349643` bytes.
3. Package gate passed, including runtime XML support and no-expat spectrum smoke.
4. Local `D:/CableTrayAI` was installed from the rebuilt full package; old `_internal_update` and package-folder installer logs were removed.
5. Local smoke passed: active server PID `19240`, `/health` returned `ok`, root page returned HTTP `200`, and `duxyb/cnpe123` login returned `pass`.
6. Source/package/install hashes match for the touched optimizer, web, learning-cache and recovery-doc files, plus rebuilt server, desktop and installer runtimes.
7. Git commit and push completed at `01e31c0` on `origin/codex/unit-deployment-hardening-20260610`.

## 2026-06-18 result-extraction component mapping closeout

Current source state:

1. The standard post-processing relationship is now explicit and tested:
   - `MAXBEAMSTRESS.LIS` and appendix-B `B*/D*` figures select the department `TYPE=1` equivalent scope: square support + tray arms, excluding tray beams and bolt connector beams.
   - `SQUAREBEAMSTRESS.LIS` selects square support only and is numeric-only. It does not generate or publish `SQ-*` figures.
   - `TMAXBEAMSTRESS.LIS` selects tray arms only.
   - Fig. 5.2 / `TBMODEL.PNG` selects tray arms + tray beams for model review, not for main stress ratios.
2. Mixed component-topology models now declare and use `CTAI_TYPE1_ELEMS = CTAI_SUPPORT_ELEMS + CTAI_ARM_ELEMS`. `CTAI_STRUCTURAL_ELEMS` remains support + arm + tray for model review only and is not used for `MAXBEAMSTRESS`.
3. Final square-section replacement now synchronizes mixed component-topology `QL3A` arrays and `apdl_topology_manifest.json` after section selection. Rule is locked by tests: tray width `<=300 mm` always uses `0.15 m`; tray width `>300 mm` uses `0.20 m` only for square outer `<=120 mm`, otherwise `0.15 m`.
4. `section_specific_export.py` now derives `SQUAREBEAMSTRESS.LIS` from the numeric main-stress block only, strips all `PLLS` / `/IMAGE,SAVE` plot commands, and prevents stale `SQ-*` figures from substituting appendix-B figures.
5. `postprocessor_alignment.py` is idempotent for component TMAX selectors, so repeated square-section sync does not duplicate `CMSEL,S,CTAI_ARM_ELEMS,ELEM` blocks.

Verification:

1. Full test suite passed: `D:/miniconda3/python.exe -m pytest tests -q`.
2. Python compile passed for touched APDL/result modules.
3. Real ANSYS18.2 validation passed for row 2 / `18185NI-LXSJ4210` at `jobs/verify_mapping_real_cleanpost_20260618`.
4. Real run selected `160-160-8`; generated model has `H1=0.160000`, `SECREAD,'160-160-8'`, yixing secondary arms with plain `SECOFFSET,user`, and `QL3A(1..5)=0.15` for `600/500/300/200/100`.
5. `result_source_map.json` shows `MAXBEAMSTRESS.LIS -> ctai_type1_component`, `SQUAREBEAMSTRESS.LIS -> ctai_support_component`, and `TMAXBEAMSTRESS.LIS -> ctai_cantilever_arm_component`.
6. `result_validation.json` passed with `result_publishable=true`; required figures are `SHITI.PNG`, `TBMODEL.PNG`, `MOTAI-1..4.PNG`, and appendix-B `B1/B2/B3/B4/D1/D2/D3/D4` figures.

Deployment closeout:

1. Full installer package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `48427750AB6C42D593576926F36DBF206AD0F56CA3F872F0456742AE3845CE1B`.
2. Package gate passed, including runtime XML support and no-expat spectrum smoke.
3. Local `D:/CableTrayAI` was installed from the rebuilt package; server started as PID `32384`.
4. Local smoke passed: `/health` returned ok, root page HTTP 200, and `duxyb/cnpe123` login returned pass.
5. Source/package/install hashes match for the touched APDL/result modules and recovery state.

## 2026-06-18 CableTrayAI mixed tray component-topology standard flow

Current source state:

1. Mixed tray-width production modeling now uses CableTrayAI's own standardized APDL topology instead of reusing a department mixed-width model file as production geometry.
2. The selected department source family remains in the audit as the solve/post intent and manual review reference, but mixed geometry is generated by `core/apdl/mixed_tray_model.py`.
3. Generated mixed APDL now declares explicit topology components after meshing:
   - `CTAI_SUPPORT_ELEMS` for square-tube support elements.
   - `CTAI_ARM_ELEMS` for cantilever/arm elements.
   - `CTAI_TRAY_ELEMS` for tray elements.
   - `CTAI_BOLT_ELEMS` for connector/bolt elements.
   - `CTAI_STRUCTURAL_ELEMS` for support + arm + tray structural elements.
   - `CTAI_BOLT_NODES` for bolt connector nodes.
4. `generated_post.mac` alignment now detects those components and extracts mixed cantilever stress plus Fig. 5.2 model display by component selectors such as `CMSEL,S,CTAI_ARM_ELEMS,ELEM`, avoiding coordinate guesses and obsolete `10*_CTAI_LAYER` / `200*_CTAI_LAYER` TYPE formulas.
5. Mixed jobs emit `apdl_topology_manifest.json`, and published command-stream review includes this manifest as optional audit evidence.
6. The new generated APDL comments are Chinese UTF-8 comments; APDL variables and component names remain ASCII to avoid parser encoding risk.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/apdl/mixed_tray_model.py core/apdl/postprocessor_alignment.py core/apdl/intake_standard_family_renderer.py core/apdl/result_source_map.py core/apdl/section_specific_export.py core/results/output_workspace.py` passed.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. `git diff --check` passed.
4. Render smokes passed for grouped mirrored mixed `100/300/500` and single-side five-width `600/500/300/200/100`; both generated topology components and component-based post selectors.
5. UTF-8 token checks passed for Chinese comments in the new APDL-generation paths.
6. Real ANSYS18.2 validation passed for row 2 / `18185NI-LXSJ4210` at `jobs/verify_ctai_component_topology_real_20260618_211918`. The run selected `160-160-8`, `ansys_run_status=success`, `result_validation.status=pass`, maximum deterministic ratio `0.8526662509801224`, controlling check `weld_force_raw_faulted_weld_equivalent`, and `TMAXBEAMSTRESS.LIS` maps to `ctai_cantilever_arm_component`.
7. The published command stream directory at `E:/CODEX/tray_platform/ANSYS Output/verify_ctai_component_topology_real_20260618_211918/18185NI-LXSJ4210/command_streams` includes `apdl_topology_manifest.json`, `generated_model.mac`, `generated_post.mac`, and spectrum review streams.
8. The modal MT and square-section learning caches were refreshed by that real ANSYS run for the same normalized 4210 key, so the learned ratios/source job now match the component-topology result source instead of the older mixed-beam selector path.

Additional verification and deployment closeout:

1. Additional real ANSYS18.2 matrix validation passed for rows 5 and 7 at `jobs/verify_ctai_component_topology_matrix_20260618_214222`.
2. `18185NI-LXSJ4213` selected `100-100-6`, `ansys_run_status=success`, `result_validation.status=pass`, and final controlling ratio `0.8205337776189886`.
3. `18185NI-LXSJ4215` selected `100-100-8`, `ansys_run_status=success`, `result_validation.status=pass`, final controlling ratio `0.8284205670255151`, and published command streams include `apdl_topology_manifest.json`.
4. Full unit tests passed again after the real ANSYS matrix: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
5. Python compile, `git diff --check`, recovery JSON validation, and `source_materials` clean checks passed. `git diff --check` only reported expected CRLF normalization warnings for touched JSON/Markdown/cache files.
6. Accessible Python caches were removed from the source tree: `__pycache__` and bytecode files are gone. The two old root pytest cache directories `.pytest_cache` and `.pytest_tmp` have broken ACLs and cannot be read or removed by the current user, but they are ignored by Git and explicitly excluded by the package script.
7. Server, desktop, and installer runtimes were rebuilt before packaging, so the deployment package cannot fall back to an older bundled executable.
8. Full installer package was rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; package gate passed, including runtime XML support and no-expat spectrum smoke.
9. Local `D:/CableTrayAI` was installed from the rebuilt full package. Smoke passed: `/health` HTTP 200 with `{"status":"ok"}`, root page HTTP 200, and `duxyb/cnpe123` login pass.
10. Source/package/install hashes match for the touched APDL/result modules, learning caches, recovery docs, and rebuilt runtime executables. Package directory has no Python cache directories, and the installed tree has no legacy nested package directories.

## 2026-06-18 single-side five-width mixed tray source-flow closeout

Current source/validation state:

1. Learned the uploaded department single-side five-layer `600/500/300/200/100` command-flow set from `C:/Users/duxy/Desktop/Desktopuxyb`: model, solve reference, and S2 post extraction.
2. Curated the reviewed files under `resources/current_type_command_flows/single_mixed_600_500_300_200_100/`.
3. Production standard-family selection now routes exact single-side five-width mixed intakes with small `100/200` tray blocks to this reviewed source family. Compact `500+600` mixed jobs still prefer the smaller reviewed family, so the broader five-width source does not steal simpler cases.
4. The reviewed source post topology is preserved for this family: `MAXBEAMSTRESS`/`TMAX` source-style selection keeps `ESEL,S,TYPE,,1` and `ESEL,U,SEC,,1`. This fixes the root mismatch where a nonstandard mixed geometry plus source-style post stream could line up for NORMAL/UPSET but diverge in FAULTED `MAXBEAMSTRESS`.
5. Fixed the square-section replacement follow-up defect: after auto-selection, reviewed single-side mixed wide-tray `L5` now follows the selected square tube branch. Selected square outer `>120 mm` writes `L5=0.15`; selected square outer `<=120 mm` keeps `L5=0.20`. Other mixed-family `L5` meanings are explicitly skipped so double-different side spans are not rewritten.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/optimizer/square_section_selector.py core/apdl/intake_standard_family_renderer.py tests/unit/test_square_section_workflow_policy.py tests/unit/test_intake_standard_family_tray_widths.py` passed.
2. Targeted tests passed: `tests/unit/test_intake_standard_family_tray_widths.py`, `tests/unit/test_postprocessor_alignment.py`, and `tests/unit/test_square_section_workflow_policy.py`.
3. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
4. `git diff --check` passed, with only line-ending normalization warnings.
5. Real ANSYS18.2 validation passed for row 2 of `C:/Users/duxy/Desktop/1818 S2支架.xlsx` at `jobs/verify_single_five_l5sync_real_20260618/18185NI-LXSJ4210`. Final selected section is `160-160-8`, final model has `H1=0.160000` and `L5=0.15`, `ansys_run_audit.status=success`, `result_validation.status=pass`, and max deterministic ratio is `0.8483448948253757`.
6. The verified `MAXBEAMSTRESS.LIS` values are:
   - NORMAL: TENSION `1522859.1`, COMPRESS `-71109.2`, BEND `36690078.0`, SHEAR `5200814.5`.
   - UPSET: TENSION `2028500.2`, COMPRESS `-730027.1`, BEND `62403138.0`, SHEAR `8589881.5`.
   - FAULTED: TENSION `4645857.0`, COMPRESS `-4574748.0`, BEND `225734616.0`, SHEAR `22195337.4`.

Deployment closeout:

1. Full installer package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Use the adjacent `CableTrayAI.zip.sha256.txt` as the transfer hash authority.
3. Local `D:/CableTrayAI` installed from the refreshed full package.
4. Local smoke passed: `/health` returned `ok`, root page returned HTTP `200`, and `duxyb/cnpe123` login returned `pass`.
5. Installed tree has `resources/current_type_command_flows/single_mixed_600_500_300_200_100/`, no legacy nested package directories, and source/package/install hashes match for the touched runtime files and new resources.

## 2026-06-18 all-ratio square-section display and 4210 render verification

Current source state:

1. Square-section candidate acceptance now uses the same overall deterministic stress-ratio basis as the final published result: support/member rows, cantilever rows, weld rows, bolt rows and mixed-beam rows are all included. The separate Chapter 6.1 member-only ratio remains in `section_selection_ratio` for audit and smart section-modulus jumps, but it no longer lets a candidate pass when weld/bolt/final rows exceed 1.0.
2. Web candidate summaries already prefer `overall_controlling_ratio` / `final_chapter6_controlling_ratio`; the backend now writes those fields as the controlling candidate status, so the web display and final result gate cannot disagree.
3. The learned square-section cache version is now `square-section-cache-v8-final-all-ratio`, preventing old records based on Chapter 6.1-only candidate acceptance from directly anchoring formal validation.
4. Support-spacing recovery from selection failure also reads overall/final candidate ratio first, so a maximum allowed square section that is cleanly over-limit by weld/bolt/final ratio can trigger the existing spacing-recovery path after larger sections are exhausted.
5. Re-rendered the actual installed `D:/CableTrayAI/jobs/18185NI-LXSJ4210/input.json` with current source. The rendered model source is `current_type_grouped_mirrored_mixed_renderer`, has `senum1=5` through `senum5=1`, includes `100/200/300/500/600-75-2mm` tray SECREADs, has no legacy `QCODE` or `QW(` arrays, keeps plain `SECOFFSET,user` for `YIXINGGANG150DAN`, and uses grouped bolt sections for small and large tray families.

Verification:

1. `D:/miniconda3/python.exe -m pytest tests/unit/test_square_section_selector.py tests/unit/test_square_section_summary.py tests/unit/test_square_section_workflow_policy.py tests/unit/test_support_spacing_recovery.py -q` passed.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. `D:/miniconda3/python.exe -m py_compile core/optimizer/square_section_selector.py core/optimizer/square_section_workflow.py core/optimizer/square_section_summary.py core/optimizer/support_spacing_recovery.py` passed.
4. `git diff --check` passed.
5. Targeted 4210 render checks passed and the temporary render directory was deleted to keep generated artifacts out of the source tree.

Deployment closeout:

1. Full installer package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; use the adjacent `CableTrayAI.zip.sha256.txt` as the transfer hash authority.
2. Local `D:/CableTrayAI` was synced from the refreshed full package with runtime data and ANSYS-local configuration preserved.
3. Started `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe` as PID `23104`.
4. Smoke checks passed: `/health` returned `{"status":"ok"}`, root page returned HTTP 200, and `duxyb/cnpe123` login returned `{"status":"pass","user":"duxyb"}`.
5. Source and installed hashes match for `core/optimizer/square_section_selector.py`, `core/optimizer/square_section_workflow.py`, `core/optimizer/square_section_summary.py`, `core/optimizer/support_spacing_recovery.py`, and `docs/CODEX_RECOVERY_STATE.json`.
6. Temporary package-run `logs` folder created by the installer under the send directory was removed after local install; `C:/Users/duxy/Desktop/duxyb-cnpe` contains the clean package folder, `CableTrayAI.zip`, and `CableTrayAI.zip.sha256.txt`.

## 2026-06-18 final installer-only closeout

Current source/validation state:

1. 100/200 current-type physical connector modeling now follows the reviewed department 200 template: section-10 `BEAM,CSOLID` uses `SECDATA,0.006`, and short connector lines are isolated with `LSEL,U,LENG,,0.05` / `LSEL,S,LENG,,0.05` before assigning section 10. This supersedes the earlier M8-radius insertion attempt for this visual connector geometry.
2. Reviewed model sources are sanitized before production solve assembly: embedded `/SOL`, `ANTYPE`, `MODOPT`, `MXPAND`, `SOLVE` tails are stripped from `generated_model.mac`, so modeling, solving, and extraction stay separated.
3. Current-type source-family scoring now requires the arm family to match the selected square section policy: `<=120` uses `50-42 + CAOGANG42DAN` with `SECOFFSET,user,,-0.03249`; `>120` uses `YIXINGGANG150 + YIXINGGANG150DAN` with plain `SECOFFSET,user`.
4. Modal MT selection now trusts real-run learned MT and audited standard-source MT, while keeping plain layer-count estimates bounded. This prevents 4210-class mixed 5+5 jobs from starting at an insufficient 70 modes; the validated learned entry starts at `MT=110` and still verifies `Mode.oup > 50 Hz`.
5. The modal learning cache keeps a sanitized 4210 real-run entry with relative audit source, not a local desktop path. Square-section runtime cache changes from validation were not carried into the deployment package.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/apdl/intake_standard_family_renderer.py core/apdl/mixed_tray_model.py core/apdl/modal_policy.py` passed.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. `git diff --check` passed, with only CRLF normalization warnings.
4. Real ANSYS18.2 production validation passed for `18185NI-LXSJ4210`: selected `140-140-8`, generated `MT=110`, first mode above 50 Hz is mode `102`, last frequency `54.44315136499 Hz`, `result_validation.status=pass`, max deterministic ratio `0.9672628568313631`.
5. Real ANSYS18.2 production validation passed for `18185NI-LXSJ4215`: selected `120-120-6`, `result_validation.status=pass`, max deterministic ratio `0.7799357874652737`, and generated model uses the reviewed small-tray connector section `SECDATA,0.006`.
6. Real ANSYS18.2 production validation passed for `18185NI-LXSJ4218`: selected `160-160-8` after automatic support-spacing recovery, static method has no main modal MT, `result_validation.status=pass`, max deterministic ratio `0.963156436189633`.

Deployment closeout:

1. Only the full installer deployment package is refreshed for the unit reinstall: `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. No update package is part of this closeout.
3. The package must be transferred with the adjacent `CableTrayAI.zip.sha256.txt` sidecar as hash authority.

## 2026-06-18 100/200 small-tray bolt mesh-selection and candidate-summary closeout

Current source/validation state:

1. Fixed the user-reported single-200 physical bolt visual defect root cause. The generated 100/200 mm small-tray command stream no longer meshes section 10 through broad geometry selections such as `LSEL,S,LOC,X,KX(516)`, because that can also catch tray/cantilever lines at the same X coordinate.
2. 100/200 mm physical bolt meshing now builds `CTAI_SMALL_BOLT_LINES` from the K509/K1509 connector lines and applies `LATT,1,,4,,,,10` only to that component. This preserves M8 `SECTYPE,10,BEAM,CSOLID` / `SECDATA,0.004` and prevents assigning bolt sections to tray or arm lines.
3. The 100/200 mm modeling gate now validates ET4 KEYOPTs, M8 section radius, K509/K1509 connectors, `L5-0.05` coupling, component-based bolt meshing, and absence of the legacy `KX(516)/KX(1516) -> LATT,1,,4` pollution pattern.
4. Mixed 100/200 tray jobs remain on the line-id path with `LS_BOLT(I)` and `BOLT_SEC(I)`; regression coverage now blocks fallback to the legacy geometry-selection bolt mesh.
5. The web square-section candidate summary was changed back to show the overall controlling ratio from `evaluation_summary.json`, with the controlling check/component label, while preserving the section-selection ratio separately for the actual square-tube sizing decision.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/apdl/intake_standard_family_renderer.py core/optimizer/square_section_selector.py` passed.
2. `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py -q` passed.
3. `D:/miniconda3/python.exe -m pytest tests/unit/test_square_section_selector.py tests/unit/test_square_section_workflow_policy.py -q` passed.
4. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
5. Frontend inline script syntax passed for `apps/web/index.html`.
6. Real ANSYS18.2 production-path validation passed for rows 5 and 7 from `C:/Users/duxy/Desktop/1818 S2支架.xlsx` under `jobs/verify_small_tray_component_real_20260618_075550`. `18185NI-LXSJ4213` single 200 selected `100-100-6`, result validation `pass`, max evaluation ratio `0.9313729151561154`, and generated model has `CTAI_SMALL_BOLT_LINES`, M8 `SECDATA,0.004`, `L5-0.05`, and no legacy section-10 pollution. `18185NI-LXSJ4215` double 100+200 mixed selected `120-120-6`, result validation `pass`, max evaluation ratio `0.7488461481605604`, and generated model uses `LS_BOLT/BOLT_SEC` with no legacy pollution.

Deployment closeout:

1. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `167A4BECD82F9E22E8CF39302324A48109594CEC9CABDA8F2FB69AED6561F2C9`.
2. Existing-install update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`, SHA256 `2D5D7D15AB170FA8D8DD290877D8CE036F763E42CDCC461A9C7DDBDFD8456D90`.
3. Update applied to local `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260618_081041`.
4. Local smoke passed on the actual installed port `8000`: `/health` returned `ok`, root page returned `200`, and `duxyb/cnpe123` login returned `pass`.
5. Installed hashes match source for `apps/web/index.html`, `core/apdl/intake_standard_family_renderer.py`, and `core/optimizer/square_section_selector.py`.

## 2026-06-18 4219 mixed 500/600 TMAX and source-style modeling closeout

Current source/validation state:

1. Fixed `18185NI-LXSJ4219`-class mirrored double-side mixed `500+600` modeling so grouped mixed command streams keep source-style review variables: `L1/L2/L3/L4/L5` plus `senum1/senum2`, instead of expanding the same geometry to hard-coded constants such as `0.67-0.3`.
2. The grouped mixed renderer now takes `H1` from the final selected square section metadata before falling back to the original intake width. This prevents selected `120/140/160` sections from retaining stale `H1=0.1` in mixed generated models.
3. Fixed grouped mixed post-processing for both TMAX and TBMODEL selectors. `TMAXBEAMSTRESS.LIS` selects actual arm sections with `ESEL,S,SEC,,2` and `ESEL,A,SEC,,3`; TBMODEL/Fig. 5.2 selects `SEC=2/3/4..9` and excludes bolt sections `10/11`, eliminating undefined `10*_CTAI_LAYER` and `200*_CTAI_LAYER` TYPE warnings.
4. Verified the desktop `C:/Users/duxy/Desktop/类型` mixed command files match `resources/current_type_command_flows` by SHA256 for single `600+500+300`, single `500+600` yixing, double mixed square, and double mixed yixing baselines.

Verification:

1. Targeted tests passed: `D:/miniconda3/python.exe -m pytest tests/unit/test_postprocessor_alignment.py tests/unit/test_intake_standard_family_tray_widths.py -q`.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. Real ANSYS18.2 rerun for Excel physical row 11 / `18185NI-LXSJ4219` completed the solve successfully with return code `0`, no fatal output evidence and no command-stream warnings after the TBMODEL selector fix.
4. `TMAXBEAMSTRESS.LIS` is non-zero for `4219`: NORMAL/UPSET/FAULTED rows are present, so the previous publication blocker `cantilever_stress_rows` is fixed.
5. `4219` still correctly fails final deterministic publication because `cantilever_root_weld_equivalent.accident.bending` ratio is `1.6677249408688304`; automatic larger-section recovery tried `140-140-8` and `160-160-8`, with controlling ratios `1.3648178105509505` and `1.0221575043033666`. This is an engineering over-limit result, not a result-extraction failure.
6. Static row 10 / `18185NI-LXSJ4218` was also real-run verified during row-number calibration; it passed after automatic spacing/section recovery and confirmed selected-section `H1` synchronization in mixed modeling.

Deployment closeout:

1. Full deployment package and update package were refreshed under `C:/Users/duxy/Desktop/duxyb-cnpe`; use the adjacent `.sha256.txt` sidecars as the transfer hash authority.
2. The update package was applied to local `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
3. Local smoke passed: `/health` returned `ok`, `duxyb/cnpe123` login returned `pass`, and installed runtime hashes match source for the touched APDL/post-processing modules.
4. Packaging scripts now regenerate outer `.sha256.txt` sidecars automatically for both `CableTrayAI.zip` and `更新包.zip`, preventing stale transfer hashes after rebuilds.

## 2026-06-18 physical bolt element-type and grouped mixed TMAX closeout

Current source/validation state:

1. Physical bolt/connector geometry is retained for 100/200 mm small-tray jobs. The temporary idea of removing physical bolts is superseded and must not be reused.
2. Fixed current-family small-tray physical bolt BEAM188 definition: when generated APDL has `ET,4,188`, the following element options are normalized to `KEYOPT,4,4,2` and `KEYOPT,4,1,1`. Reviewed source files that accidentally put `KEYOPT,2,...` after `ET,4` are corrected at render time without modifying source materials.
3. If a reviewed 100/200 mm double-side source lacks physical bolt topology, generated APDL now inserts `ET,4,188`, `SECTYPE,10,BEAM,CSOLID`, M8 `SECDATA,0.004`, front/back `K509/K1509`, connector lines, and `LATT,1,,4,,,,10`.
4. Fixed grouped mixed 100/200 mm post-processing: models using `ARM_ET(NARM)=2` and `ARM_SEC(NARM)=2/3` now select TMAX cantilever arms with `ESEL,S,SEC,,2` plus `ESEL,A,SEC,,3`, preventing `TMAXBEAMSTRESS.LIS` from being all-zero.
5. Replaced the old DOTALL regex TMAX selector rewrite with a linear line-based replacement. This removes the 120-minute CPU hang seen before real ANSYS started on `18185NI-LXSJ4215`.

Verification:

1. `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
2. Targeted postprocessor and tray-width tests passed: `tests/unit/test_postprocessor_alignment.py` and `tests/unit/test_intake_standard_family_tray_widths.py`.
3. Real ANSYS18.2 passed for `jobs/verify_small_tray_bolt_matrix_real_20260618_rerun` rows 5, 7, and 20.
4. Real-run results: `18185NI-LXSJ4213` selected `100-100-6`, section ratio `0.6179154054744243`, final max ratio `0.9313729151561154`; `18185NI-LXSJ4215` selected `120-120-6`, section ratio `0.3986404089390689`, final max ratio `0.7488461481605604`; temporary double-side 200 row `18185NI-LXSJ9299` selected `100-100-6`, section ratio `0.19562670633692059`, final max ratio `0.43973493136852526`.
5. Published `TMAXBEAMSTRESS.LIS` for `4215` is non-zero; `result_validation.status=pass`.
6. Generated models for `4213`, `4215`, and `9299` contain `ET,4,188`, `KEYOPT,4,4,2`, `KEYOPT,4,1,1`, no bad `KEYOPT,2` near `ET,4`, `BEAM,CSOLID`, M8 `SECDATA,0.004`, and physical `LATT,1,,4`.

Deployment closeout:

1. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; use the adjacent `CableTrayAI.zip.sha256.txt` as transfer hash authority.
2. Existing-install update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the adjacent `更新包.zip.sha256.txt` as transfer hash authority.
3. Refreshed `CableTrayAI.zip.sha256.txt` and `更新包.zip.sha256.txt`.
4. Applied the update to local `D:/CableTrayAI`; the exact latest backup path is recorded in the installed update manifest; health check passed.
5. Package gate passed, including runtime XML/expat files and the no-expat spectrum smoke.

## 2026-06-17 4213 bolt-section and 4210 grouped mixed closeout

Current source/validation state:

1. Fixed `18185NI-LXSJ4213`-class 100/200 mm tray modeling so a reviewed source that contains `SECTYPE,10,BEAM,CSOLID` is rewritten to the small-tray M8 nominal round-bar radius: `SECDATA,0.004`. 300/500/600 mm trays still use the M12 nominal radius `0.006`.
2. Fixed mirrored double-side mixed tray modeling for `4210`-class jobs. When both sides have the same mixed width distribution, the renderer now emits grouped `senum` boundary loops for 2 to 5 tray-width groups. This covers the current uploaded `4210` row with 100/200/300/500/600 mm trays and no longer emits the old `QW/QCODE` per-layer array stream.
3. The grouped mixed renderer now records `ARM_ET`, `ARM_SEC`, `TRAY_ET`, `TRAY_SEC`, `TRAY_MAT`, and `BOLT_SEC` for every generated line before meshing. This fixed the real ANSYS18.2 `No dimensions set for parameter= ARM_ET` error found during validation.
4. Mixed jobs with small and large trays keep separate bolt section numbers: `SECTYPE,10` for large-tray/M12 bolt lines and `SECTYPE,11` for small-tray/M8 bolt lines; each bolt line records the correct `BOLT_SEC` before `LATT`.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/apdl/mixed_tray_model.py core/apdl/intake_standard_family_renderer.py` passed.
2. `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py -q` passed with 41 tests.
3. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
4. Real ANSYS18.2 validation passed for the formal intake workbook rows 2 and 5 under `jobs/verify_4210_4213_current_request_real_fixed_20260617`.
5. `18185NI-LXSJ4210` selected `140-140-8`, `ansys_run_status=success`, `result_validation.status=pass`, final section-selection ratio `0.9527713364018127`; generated model contains `senum1=5` through `senum5=1`, `ARM_ET/TRAY_ET/BOLT_SEC`, and no `QW(` or `QCODE`.
6. `18185NI-LXSJ4213` selected `100-100-6`, `ansys_run_status=success`, `result_validation.status=pass`, section-selection ratio `0.6179154054744243`; generated model contains `SECREAD,'200-75-2mm'` and `SECTYPE,10,BEAM,CSOLID` with `SECDATA,0.004`.

Deployment closeout:

1. Rebuilt server, desktop, and installer runtimes.
2. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; use the adjacent `.sha256.txt` sidecar as transfer hash authority.
3. Existing-install update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the adjacent `.sha256.txt` sidecar as transfer hash authority.
4. Applied the update to local `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
5. Local smoke passed: `/health` returned ok and `duxyb/cnpe123` login returned pass.
6. Installed hashes match source for `core/apdl/intake_standard_family_renderer.py`, `core/apdl/mixed_tray_model.py`, `data/calibration/modal_mode_count_cache.json`, and `data/calibration/square_section_selection_cache.json`.

## 2026-06-17 current-type mixed tray dispatch and coupling closeout

Current source/validation state:

1. The department clarification is now the active small-tray rule: for `100/200 mm` trays, `CPCYC ... L5-0.05` couples the bolt upper point to the tray. The temporary `CPCYC ... L5` interpretation is not used.
2. Mixed tray modeling is tied to the current unit standard command-flow library in `resources/current_type_command_flows/` only when that reviewed source family exactly covers the intake topology. This prevents a reviewed single-side mixed family from being forced onto a double-side per-side mixed intake.
3. `18185NI-LXSJ4514`-class single-side `500+600` mixed trays now use the current standard mixed source family shape with `senum1/senum2/senum3`, `L1/L2/L11/L12/L5`, `CPCYC ... M1-0.05`, and no platform-only `QTOFF/QCODE` line groups. Optional mesh blocks for unused source width families are preserved but wrapped in APDL `*IF` guards so ANSYS18.2 does not evaluate undefined keypoints.
4. `18185NI-LXSJ4210`-class double-side `100+300+500` per-side mixed trays do not have an exact current-type standard source family in the reviewed `类型` folder. They now explicitly bypass the current-family renderer and use the deterministic per-layer mixed renderer instead of silently reusing a mismatched source.
5. The selector audit records this distinction so code review can see whether a job used an exact current-type family or the deterministic mixed renderer fallback.

Verification:

1. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
2. Real ANSYS18.2 passed for `4210` at `jobs/verify_4210_after_mixed_dispatch_20260617/18185NI-LXSJ4210`: selected `140-140-8`, result validation `pass`, final section-selection and Chapter 6.1 ratio `0.9672676676517402`.
3. Real ANSYS18.2 passed for `4211` at `jobs/verify_4210_4211_after_standard_mixed_20260617/18185NI-LXSJ4211`: selected `100-100-6`, result validation `pass`, section-selection ratio `0.6179154054744243`, final Chapter 6.1 ratio `0.9313729151561154`, and generated model contains `CPCYC,UX,,,,,L5-0.05`.
4. Real ANSYS18.2 passed for `4514` at `jobs/verify_4514_standard_family_real_final_20260617/18185NI-LXSJ4514`: selected `100-100-6`, result validation `pass`, section-selection ratio `0.5635385466913663`, final Chapter 6.1 ratio `0.7162255419833204`, generated model contains `senum1/senum2/senum3`, `M1-0.05`, and no `QTOFF/QCODE`.

Deployment closeout:

1. Full package and existing-install update package were refreshed under `C:/Users/duxy/Desktop/duxyb-cnpe` from this source state. Use the adjacent `.sha256.txt` sidecars as the transfer hash authority.
2. The update was applied to local `D:/CableTrayAI` through the update package installer entrypoint, not by feeding the outer update zip directly to `apply_internal_update.ps1`.
3. Local smoke passed: `/health` returned ok and `duxyb/cnpe123` login returned pass.
4. Source/package/installed hashes match for `core/apdl/intake_standard_family_renderer.py`, the two learning caches, the three recovery docs, and `runtime/CableTrayAI_Server/CableTrayAI_Server.exe`.

## 2026-06-17 4211 small-tray coupling review correction

Current source/validation state:

1. Supersedes the temporary `CPCYC ... L5` interpretation made during image review. The department clarification is authoritative: for tray widths `100/200 mm`, `L5-0.05` is the coupling distance between the bolt upper point and the tray; without subtracting `0.05`, the coupling reaches the cantilever arm/tray instead.
2. `core/apdl/intake_standard_family_renderer.py` keeps the `100/200 mm` small-tray branch as: `L3=0.15m`, `L5=0.074m`, keypoints `502/1502` at `H1/2+L1-L3`, keypoints `503/1503` and tray keypoints `506/507/508` at `H1/2+L1-L2/2`, tray Z offset `0.1+L5+...`, connector line rewritten to `503/1503 -> 509/1509`, and `CPCYC` offset `L5-0.05`.
3. The 300 mm physical-bolt branch and the 500/600 mm L2/2 topology are unchanged.

Verification:

1. Targeted tests passed: `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py -q`.
2. Square-section workflow tests passed: `D:/miniconda3/python.exe -m pytest tests/unit/test_square_section_selector.py tests/unit/test_square_section_workflow_policy.py -q`.
3. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
4. Render smoke using the latest installed `D:/CableTrayAI/jobs/18185NI-LXSJ4211/input.json` confirmed `CPCYC,UX,,,,,L5-0.05`, `K509`, and `L,503 -> 509` are present; plain `CPCYC ... L5` and old `L,502 -> 509` are absent.
5. Real ANSYS18.2 validation passed under `jobs/verify_4211_l5_minus_coupling_real_20260617/18185NI-LXSJ4211`: generated model has `L2=0.2`, `L3=0.15`, `L5=0.074`, `K509`, `L,503 -> 509`, and `CPCYC ... L5-0.05`; selected `100-100-6`; result validation `pass`; final Chapter 6.1 controlling ratio `0.9313729151561154`; connection-load extraction has non-zero rows.

## 2026-06-17 small-tray/wide-tray command-flow correction closeout

Current source/validation state:

1. Fixed the current-type source-family selector so single 100/200 mm trays cannot select the reviewed 300 mm physical-bolt family. If no exact single 100/200 family exists, production may reuse a reviewed wide single-width family only after the small-tray rewrite gate normalizes the geometry.
2. Fixed the 100/200 small-tray rewrite to normalize all reviewed small-tray details inherited from wide sources: `L3=0.15m`, `L5=0.074m`, keypoints 502/1502 at `H1/2+L1-L3`, tray/bolt line at `H1/2+L1-L2/2`, tray Z offset from `0.168+...` to `0.1+L5+...`, and `CPCYC` offset from `0.068-0.05` to `L5-0.05`.
3. Fixed square-section replacement so single-width generated models synchronize `H1` and `L3` together. Final L3 policy is now: tray width `<=300 mm` uses `0.15m`; tray width `>300 mm` uses `0.15m` when square outer width is `>120 mm`, otherwise `0.20m`.
4. Fixed mixed tray offsets so CAOGANG42DAN mixed 500/600 layers use `QTOFF/HTOFF=0.074`, while YIXINGGANG150DAN wide mixed layers keep the reviewed `0.068` offset.
5. This preserves the earlier 500/600 rule that 502 and 506-509 stay on `H1/2+L1-L2/2`, and preserves the 300 mm physical-bolt topology instead of mixing it with 100/200 or 500/600 rules.

Verification:

1. Targeted tests passed: `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py tests/unit/test_square_section_selector.py tests/unit/test_square_section_workflow_policy.py -q`.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. Render smoke confirmed 4211/4311 no longer contain small-tray `0.168` or `0.068-0.05`; 4215 uses `H1=0.140000`, `L3=0.15`; 4514 mixed CAOGANG uses `QTOFF(1)=0.074`.
4. Real ANSYS18.2 validation passed for rows 9 and 10 under `jobs/validation_small_tray_coupling_real_20260617`: 4211 double 200 selected `100-100-6`, section-selection ratio `0.6179190587519203`, overall max `0.9314387883147078`; 4311 double 100 selected `100-100-6`, overall max `0.039109041001640685`.
5. Real ANSYS18.2 validation passed for rows 7 and 14 under `jobs/validation_wide_mixed_model_real_20260617`: 4215 double 600 selected `140-140-8`, overall max `0.8902034974335807`; 4514 mixed 500/600 selected `100-100-6`, overall max `0.7143462445371618`.

Deployment closeout:

1. Rebuilt the server runtime and refreshed `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; SHA256 `8C1A395EA8BE1701C38668F348005EFCDC9873B9CDFD883BFEEB54EB51EAD810`.
2. Refreshed existing-install update package `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; SHA256 `2D0489EE38878E492FA5CB96F4DA88A45FE9F186467588F0616904AD585F01B9`.
3. Update applied to local `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260617_192703`.
4. Local smoke passed: `/health` returned ok, `duxyb/cnpe123` login returned pass, and source/package/installed hashes match for `core/apdl/intake_standard_family_renderer.py`, `core/apdl/mixed_tray_model.py`, `core/optimizer/square_section_selector.py`, the two learning caches, and `runtime/CableTrayAI_Server/CableTrayAI_Server.exe`.

## 2026-06-17 department S2 rule alignment

Current source/validation state:

1. Compared the department S2 rule memo against the current implementation. Existing production logic already matches the four-component model boundary, tray-width topology split, square-section-to-arm-family mapping, channel/yixing `SECOFFSET` policy, <=120 mm equivalent weld coefficient `0.526`, steel-platform static method with `1.5*9.81*peak` ACEL, and static no-main-MT policy.
2. Per the user's correction, the broad "full text contains steel platform -> static method" recognition policy remains unchanged.
3. Fixed the only source mismatch found in the conversational-intake default square-section list: `120-120-8` is now included with `100-100-6`, `100-100-8`, `120-120-6`, `120-120-10`, `140-140-8`, and `160-160-8`. Explicit intake calculation-note candidate lists still remain authoritative and are not expanded by the default list.
4. Aligned new-intake fallback MT initialization with the department note that one-layer 600 mm tray cases generally use 20 modes. `modal_mode_count_from_layer_count(1)` now returns `20`; multi-layer existing verified fallback values and the Mode.oup >50 Hz retry gate remain unchanged.

Verification:

1. Targeted tests passed: `D:/miniconda3/python.exe -m pytest tests/unit/test_chat_intake.py tests/unit/test_modal_policy.py tests/unit/test_intake_row_selection.py -q`.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. `git diff --check` passed.
4. `source_materials` remains unchanged.

Deployment closeout:

1. Rebuilt server, desktop, and installer runtimes, then refreshed `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Refreshed existing-install update package `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
3. Regenerated transfer hash sidecars. `CableTrayAI.zip` SHA256 is `C9869E91836AEF02DED08EF2D1991737AEBF7DA6687AA173A672E010AA097124`; `更新包.zip` SHA256 is `BA45B05C3E53842D72E1664A360A7DE567FAB82C6E521505CA1310A569E876CC`.
4. Applied the update to local `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260617_164537`; `resources_applied=true` in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
5. Local smoke passed: `/health` returned ok, `duxyb/cnpe123` login returned pass, installed `core/intake/chat_intake.py` contains `120-120-8`, and installed `core/apdl/modal_policy.py` contains one-layer fallback `1: 20`.

## 2026-06-17 current-type command-flow baseline closeout

Current latest source/validation state:

1. The uploaded desktop folder `C:/Users/duxy/Desktop/类型` is now the curated production modeling baseline. Its ten reviewed PIP files were copied into `resources/current_type_command_flows/` with ASCII names so packaging, tests, and source control can track them.
2. Historical command streams in `source_materials` were not deleted. They remain read-only traceability and fallback references per `AGENTS.md`, but the production model-family selector now strongly prefers `resources/current_type_command_flows` before scanning historical material.
3. The selector now scores topology more strictly so single-side cases do not pick double-side sources, mixed cases pick mixed sources, and 500/600 wide-tray sources are not stolen by the 300 mm source family.
4. Mixed tray geometry now keeps the standardized looped APDL style. The 300 mm branch uses the latest 501-502-504 physical-bolt topology, while 500/600 keep the reviewed L2/2 bolt/connection line and small trays keep their independent 100/200 topology.
5. Fixed an ANSYS18.2 APDL variable collision found by real validation: `QCODE` remains the width-code array, and the loop scalar is now `QTCODE`, so MAPDL no longer raises `Parameter QCODE needs subscripts`.
6. Secondary-arm offsets are normalized by arm family: `CAOGANG42DAN` keeps `SECOFFSET,user,,-0.03249`; `YIXINGGANG150DAN` keeps plain `SECOFFSET,user`.
7. Explicit tray line-load fields are not added to equivalent density. Density is only back-calculated to kg/m when no explicit line-load field exists.
8. The full package script now includes `resources/`, so the curated current baseline library is present in unit deployments.

Verification:

1. Render matrix passed for single-side 100/200/300/500/600, double-side 200/500, single mixed 300+600, double mixed 300+500, and single seven-layer 300/500/600.
2. Full unit tests passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`.
3. `git diff --check` returned no whitespace errors, only existing CRLF normalization warnings.
4. Real ANSYS18.2 final validation passed for uploaded workbook rows 3, 4, 7, and 11 under `jobs/validation_current_type_baseline_final_real_20260617`.
5. Final real-run results: `18185NI-LXSJ4211` selected `120-120-6`, ratio `0.9905821165756017`; `18185NI-LXSJ4212` selected `100-100-6`, ratio `0.8499368255073432`; `18185NI-LXSJ4215` selected `140-140-8`, ratio `0.8335106438226824`; `18185NI-LXSJ4214` selected `100-100-8`, ratio `0.869901992449058`. All four have `ansys_run_status=success`.

Deployment closeout:

1. Rebuilt server/desktop/installer runtimes, then refreshed `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Refreshed existing-install update package `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
3. Regenerated external transfer hashes: `CableTrayAI.zip.sha256.txt` and `更新包.zip.sha256.txt`.
4. Applied the update package to local `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260617_161759`.
5. Local smoke passed: `/health` returned ok, `duxyb/cnpe123` login returned pass, installed hashes match source for the touched runtime files, and `D:/CableTrayAI/resources/current_type_command_flows` contains the ten curated baseline PIP files.
6. The previous recommendation still stands: do not delete historical `source_materials`; constrain production selection to the curated current baseline and keep old streams only for audit fallback.

## 2026-06-17 600-tray L2/2 topology and load-counting closeout

Current latest source/validation state:

1. Fixed the single-width 500/600 tray topology regression. Standard wide-tray S2 families now keep keypoints 502 and 506-509, plus the related coupling selector, on the reviewed `H1/2+L1-L2/2` line. They are no longer rewritten to `H1/2+L1-L3`.
2. Preserved the separate small-tray and 300 mm policies: tray widths `<=300 mm` still assign `L3=0.15m`; 300 mm keeps its physical-bolt topology with 506-508 at L3 and 509/coupling at L2/2; 100/200 mm still use the reviewed small-tray partition rewrite.
3. Wider trays above 300 mm keep the square-tube L3 rule: square outer width `<=120 mm` uses `L3=0.20m`; square outer width `>120 mm` uses `L3=0.15m`.
4. Hardened square-section anchoring for 600 mm trays so single-side two-layer 600 starts above the small 100x8 path, and mixed 500/600 density-only inputs are anchored from actual back-calculated line load instead of stale learned evidence.
5. Answered and guarded the double-counting risk: if a tray layer contains explicit `load_kg_m` / `line_load_kg_m` / equivalent line-load fields, that value is used directly. Equivalent density is back-calculated into kg/m only when no explicit line load exists, so line load and density are not added together.
6. Hardened `scripts/run_production_full_intake_compute.ps1` to choose a Python runtime that can import required project dependencies before running production intake calculations. This prevents command-line real-ANSYS validation from accidentally using a system Python without `pydantic/openpyxl`.

Verification:

1. Targeted tests passed: `tests/unit/test_intake_standard_family_tray_widths.py` and `tests/unit/test_square_section_workflow_policy.py`.
2. Full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
3. PowerShell syntax parse passed for `scripts/run_production_full_intake_compute.ps1`.
4. Render-regression checks on uploaded workbook rows 4/7/9/10/11 confirmed 300, 200, 100, single 600, and mixed 500/600 geometry policies.
5. Real ANSYS18.2 validation passed for uploaded workbook rows 7 and 11 under `jobs/validation_600_mixed_fix_real_20260617`.
6. Row 7 / `18185NI-LXSJ4215` single 600 selected `140-140-8`; generated model uses `600-75-2mm`, `H1=0.140000`, `L3=0.2`, and 506/509/NSEL on `H1/2+L1-L2/2`; final controlling ratio `0.8883527244537628`, pass.
7. Row 11 / `18185NI-LXSJ4214` mixed 500/600 selected `100-100-8` only after a fresh real ANSYS calculation; final Chapter 6.1 controlling ratio `0.869901992449058`, pass. The generated model preserves both `500-75-2mm` and `600-75-2mm` sections and per-layer mixed geometry.

Deployment closeout:

1. Packaging and local installed-service refresh are the remaining steps after this source/real-ANSYS validation. Use this section as the latest source truth until the package closeout entry is added.

## 2026-06-17 section-before-spacing recovery and line-load override closeout

Current latest source/validation state:

1. This supersedes the immediately preceding `4215 spacing-first economy recovery` note. The accepted production policy is now: try larger intake-allowed square sections first for final weld/bolt/connection over-limit cases; reduce support spacing only after the largest allowed square tube is active and the deterministic final gate still exceeds 1.0.
2. `core/pipeline/one_click.py` no longer runs the preserved-current-section spacing branch before `final_ratio_design_recovery`. A 120 section that passes Chapter 6.1 but fails a weld final gate now progresses to 140/160 before any spacing recovery is considered.
3. `core/optimizer/support_spacing_recovery.py` now enforces the same policy at the planner level. `plan_support_spacing_recovery_from_final_ratio` skips when the current selected square tube is not the maximum allowed section, preventing future accidental spacing-first calls.
4. The result gate no longer recognizes `preserved_after_spacing_recovery_pending_formal_validation`; support-spacing recovery resets square-section selection and requires fresh selection plus a fresh formal run.
5. Added operator-confirmed tray line-load override support. The dashboard can edit layer `kg/m` values and send `tray_layer_overrides` through row overrides. Backend job creation updates only the job-local `tray_layers`, recalculates equivalent density from the audited tray area table, and stores original/override audit metadata without modifying the source Excel intake.

Verification:

1. Targeted tests passed: `test_support_spacing_recovery.py`, `test_result_validity_square_section.py`, and `test_tray_load_overrides.py`.
2. Full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
3. Frontend inline script syntax check passed using Node/VM UTF-8 parsing.
4. Real ANSYS18.2 validation passed for uploaded workbook row 7 / `18185NI-LXSJ4215` at `jobs/validation_4215_section_before_spacing_20260617_130851/18185NI-LXSJ4215`. The run tried 100 and 120, then recovered final weld/connection over-limit by trying 140 and 160. Final selected section is `160-160-8`; support spacing stayed `2.0m`; no `support_spacing_adjustments.json` was written; `result_validation.status=pass`.
5. Final controlling ratios for the validation job: weld accident equivalent `0.9049054104654485`, upset weld equivalent `0.890287195518`, cantilever Chapter 6.1 compression+bending accident `0.8128428436491665`.

Deployment closeout:

1. Rebuilt server, desktop, and installer runtimes.
2. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; use the external `.sha256.txt` sidecar beside the zip as the transfer hash authority.
3. Existing-install update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecar beside the zip as the transfer hash authority.
4. Exact zip hashes are intentionally not embedded here to avoid self-referential package hash churn.
5. Update applied to local `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`; `/health` ok; login `duxyb/cnpe123` pass; installed hashes match source for `apps/web/index.html`, `core/pipeline/one_click.py`, `core/optimizer/support_spacing_recovery.py`, and `core/intake/job_input_builder.py`.

## 2026-06-17 4215 final-gate spacing-first economy recovery

Current latest source/validation state:

1. Implemented the user's economy preference for cases like `18185NI-LXSJ4215`: when the current square tube passes Chapter 6.1 member sizing but a weld/bolt/connection final gate is over 1.0, the workflow now keeps the current square tube and reduces support spacing before trying a larger square tube.
2. `core/optimizer/support_spacing_recovery.py` now supports two explicit planning modes:
   - largest allowed square section is active and still over limit;
   - current section is preserved because the over-limit item is a non-section final gate.
3. `core/pipeline/one_click.py` now runs the spacing-first branch before `final_ratio_design_recovery` section enlargement. The branch preserves the current square section, regenerates APDL, reruns real ANSYS, and only falls back to larger sections if spacing recovery cannot produce a publishable result.
4. `core/validation/result_validity_gate.py` now treats `preserved_after_spacing_recovery_pending_formal_validation` as a formal-validation mode. The old trial ratio is not comparable after spacing changes, so the current formal Chapter 6.1 ratio is used directly; weld/bolt/global over-limit rows still block through the normal final gate.
5. Real ANSYS18.2 validation used uploaded workbook `C:/Users/duxy/Desktop/1818 S2支架.xlsx`, selected row 7 / `18185NI-LXSJ4215`. The first formal run selected `120-120-10`, Chapter 6.1 ratio about `0.815`, but weld accident bending ratio was `1.496`.
6. The new branch reduced support spacing from `2.0m` to `1.5m` while preserving `120-120-10`; the rerun passed with `result_validation.status=pass`, final Chapter 6.1 section-selection ratio `0.5241137016938773`, and controlling final weld ratio `0.961668929223405`.
7. Verification passed: targeted result-validity/support-spacing/square-section policy tests, full `D:/miniconda3/python.exe -m pytest tests/unit -q`, py_compile for touched modules, source_materials clean, and `git diff --check` only reports the known CRLF normalization warning for the calibration JSON.

Deployment closeout:

1. Rebuilt server, desktop, and installer runtimes.
2. Refreshed full package `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; use the external `.sha256.txt` sidecar beside the zip as transfer authority.
3. Refreshed update package `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecar beside the zip as transfer authority.
4. Package gate and update self-verification passed, including runtime XML/expat and no-expat spectrum smoke.
5. Applied update to local `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`; `/health` returned ok and `duxyb/cnpe123` login passed.
6. Installed hashes match source for `core/optimizer/support_spacing_recovery.py`, `core/pipeline/one_click.py`, `core/validation/result_validity_gate.py`, and `data/calibration/modal_mode_count_cache.json`.

## 2026-06-17 uploaded-intake 4211/4215 row binding and final-gate recovery

Current latest source/validation state:

1. Fixed dashboard row override selection so a physical Excel row number wins over duplicate report/calculation ids. This prevents duplicate `18185NI-LXSJ4211` rows from bleeding between row 3 `single-side 2-layer 500` and later 100/200 variants.
2. `analysis_scope` now prefers structured `metadata.tray_load_mapping.layers` / `input.tray_layers` over free-text tray descriptions. This prevents scope/result gates from seeing a stale text width such as 100 when the generated input contains 500 or 600 mm tray layers.
3. Split final over-limit handling into two explicit paths:
   - Chapter 6.1 member ratio over 1.0: square-section upgrade.
   - Weld/bolt/global final gate over 1.0: final-ratio design recovery using larger reviewed sections or spacing recovery, but not labeled as square-section stress overlimit.
4. Uploaded workbook `C:/Users/duxy/Desktop/1818 S2支架.xlsx` was used directly. Row 3 generated `18185NI-LXSJ4211` as `single-side 2-layer 500` with `500-75-2mm`; row 7 generated `18185NI-LXSJ4215` as `single-side 2-layer 600` with `600-75-2mm`.
5. Real ANSYS18.2 validation passed:
   - `jobs/validation_uploaded_intake_real_20260617/18185NI-LXSJ4211`: selected `120-120-6`, final Chapter 6.1 controlling ratio `0.9727244369318827`, `result_validation.status=pass`.
   - `jobs/validation_uploaded_4215_recovery_20260617/18185NI-LXSJ4215`: learned/formal start `120-120-10` had Chapter 6.1 ratio about `0.815`; the real over-limit was weld/final gate (`cantilever_root_weld_equivalent.accident.bending` about `1.496` at 120). The workflow recovered via `final_ratio_design_recovery` to `160-160-8` and finished with `result_validation.status=pass`.
6. Square-section learning cache is now guarded against this exact 4215 class: a historical sample whose selected section passes Chapter 6.1 sizing but exceeds the final weld/bolt/global ratio gate cannot be recorded or reused as a successful direct learned validation sample. Existing unsafe final-gate-fail cache records were pruned.
7. Verification passed: `py_compile` for touched runtime modules, targeted policy tests, and full `D:/miniconda3/python.exe -m pytest tests/unit -q`.

Deployment closeout:

1. Rebuilt server, desktop, and installer runtimes.
2. Refreshed full package `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and update package `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; package gate and update self-verification passed.
3. Refreshed external SHA256 sidecars beside both zips.
4. Applied the update to local `D:/CableTrayAI`; latest backup `D:/CableTrayAI/_update_backups/20260617_095241`; `/health` returned `ok`, login `duxyb/cnpe123` returned `pass`, and installed hashes match source for the touched modules and pruned learning cache.
5. Installed-code smoke using the uploaded workbook row 3/7 generated `500-75-2mm` for 4211 and `600-75-2mm` for 4215.
## 2026-06-16 mixed tray line-id standardization closeout

Current latest source/validation state:

1. The mixed tray-width renderer now follows the reviewed seven-layer mixed-width APDL pattern more closely.
2. `core/apdl/mixed_tray_model.py` drives mixed geometry with per-layer arrays for tray width, total arm length, tail length, tray offset, and width code.
3. Every generated support, arm, tray, and bolt line is captured immediately with `*GET,_LNEW,LINE,0,NUM,MAX`.
4. Meshing now uses recorded `LS_SUP`, `LS_ARM`, `LS_TRAY`, and `LS_BOLT` line-id groups instead of geometry-location reselection. This avoids mixed-width ambiguity when 300/500/600 or other widths are combined.
5. The 300 mm topology branch remains explicit, and the small-tray and wide-tray branches remain separate.
6. The same mechanism applies to single-side and double-side mixed layouts; it is no longer tied to one hardcoded seven-layer example.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/apdl/mixed_tray_model.py` passed.
2. `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py -q` passed.
3. Full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
4. Hardcode scan over runtime core/apps/templates had no hits for the desktop review macro or validation-only job names; `source_materials` remains unchanged.
5. Real ANSYS18.2 validation passed under `jobs/validation_mixed_lineid_real_20260616`.
6. `18185NI-LXSJ4214` selected `100-100-8`, final Chapter 6.1 controlling ratio `0.8607844777148501`, `result_validation.status=pass`.
7. `18185NI-LXSJ4215` selected `120-120-10`, final Chapter 6.1 controlling ratio `0.9660705625785098`, `result_validation.status=pass`.

Deployment closeout:

1. Server, desktop, and installer runtimes were rebuilt.
2. Full package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
3. Update package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
4. External `.sha256.txt` sidecars were refreshed beside both zip files and are the transfer authority; exact zip hashes are intentionally not embedded in packaged docs to avoid self-referential hash churn.
5. The update was applied to local `D:/CableTrayAI`; the exact latest backup path is recorded by the installer in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
6. Local smoke passed: `/health` returned `ok`, `duxyb/cnpe123` login returned `pass`, and source/package/installed hashes match for the mixed renderer and recovery docs.

## 2026-06-16 seven-intake layer parsing and preview closeout

Current latest source/validation state:

1. Fixed unlabeled double-side layer-width parsing in `core/intake/tray_load_parser.py`.
2. Equal declared side counts now repeat the declared layer sequence on every side. For example, `double-side 3+3 layers, one 100, one 300, one 500` parses as front `[100,300,500]` plus back `[100,300,500]`.
3. The six `input.json` tray-layer rows for 4210 are therefore trace rows for both sides: three front rows plus three back rows. They are not a single-side six-layer model.
4. Unequal declared side counts still distribute the unlabeled layer sequence by count, and native side labels such as front/back/left/right remain authoritative.
5. Fixed the web APDL preview interpreter in `apps/web/index.html` so it understands APDL array variables and functions used by mixed-loop models, including `QW(I)`, `HW(I)`, `QTOFF(I)`, and `ABS(...)`.
6. This fixes the visual-only issue where 4213/4214/4210 command streams could contain the correct APDL loop model but the web 3D preview displayed only two layers.
7. The existing 4211 small controlling ratio `0.0530209796187918` was checked against the completed job. It belongs to a light double-side two-layer 100 mm tray case with section `100-100-6`; current raw/evaluation files indicate this is a real deterministic result, not a zero-extraction/table-mapping error.

Verification:

1. Targeted parser tests passed for equal-side repetition and unequal-side distribution.
2. Full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
3. Node syntax check for `apps/web/index.html` passed.
4. Real ANSYS18.2 validation passed for seven rows under `jobs/validation_layer_fix_real_20260616`.
5. Real validation summary: 4210 `120-120-6`, ratio `0.9123861426715882`; 4211 `100-100-6`, ratio `0.0530209796187918`; 4212 `100-100-6`, ratio `0.5616030578647903`; 4213 static `140-140-8`, ratio `0.779440071051453`; 4214 `100-100-8`, ratio `0.8629901759670398`; 4220 `100-100-6`, ratio `0.1465742343488118`.
6. 4215 was rerun after tightening the economy policy. Real ANSYS job `jobs/validation_economic_downshift_real_20260616/18185NI-LXSJ4215` first found `140-140-8` ratio `0.509069498978923`, treated it as too conservative, downshifted to `120-120-10`, and passed with ratio `0.9673673573968273`.
7. All seven validation jobs have `result_validation.status=pass`; the latest 4215 result also has `result_validation.status=pass`.

Deployment closeout:

1. Full package and update package were refreshed under `C:/Users/duxy/Desktop/duxyb-cnpe`.
2. Use the external `.sha256.txt` sidecars beside `CableTrayAI.zip` and `update package zip` as the transfer authority; exact zip hashes are not embedded in packaged docs to avoid self-referential hash churn.
3. The refreshed update package was applied to local `D:/CableTrayAI`. The exact latest backup path is recorded by the installer in `D:/CableTrayAI/docs/last_internal_update_apply.json` and `D:/CableTrayAI/docs/last_mail_update_apply.json`.
4. Local health/login/hash smoke passed after applying the update.

## 2026-06-16 platform-owned single-tray command-flow shadow v1

Current latest source/validation state:

1. Added `core/apdl/platform_standard_flow.py`.
2. For S2 single tray-width front/back jobs, the renderer now writes three platform-owned shadow command streams:
   - `platform_standard_solve.mac`
   - `platform_standard_post.mac`
   - `platform_standard_post_numeric.mac`
3. These files are review/baseline artifacts only. Production `run_all.mac` still uses the validated `generated_solve.mac` and `generated_post_numeric.mac` path.
4. The scope gate deliberately skips mixed tray widths, third-side jobs, unsupported support types, and unsupported analysis methods.
5. `platform_standard_flow_audit.json` records scope, source hashes, required numeric-output checks, numeric-post generation, execution policy, and promotion gates.
6. Published command-stream manifests now include the optional `platform_standard_*` files when present, clearly marked as shadow review streams.

Verification:

1. `D:/miniconda3/python.exe -m py_compile` passed for the touched modules.
2. Full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
3. Render smoke passed for a single-tray 300 mm S2 job; the three `platform_standard_*` files and audit were generated.
4. Real ANSYS18.2 validation passed at `jobs/validation_platform_standard_shadow_real_20260616_194924/PLATFORM-STANDARD-SINGLE-300`.
5. Real validation selected `100-100-6`, controlling ratio `0.24417413972723276`, `result_validation.status=pass`, `result_publishable=true`.
6. The published output folder contains `platform_standard_solve.mac`, `platform_standard_post.mac`, and `platform_standard_post_numeric.mac` under `command_streams`.

Deployment closeout:

1. Server, desktop, and installer runtimes were rebuilt.
2. Full package and update package were refreshed under `C:/Users/duxy/Desktop/duxyb-cnpe`.
3. Package gate and update self-verification passed, including runtime XML/expat and no-expat spectrum smoke.
4. Local `D:/CableTrayAI` was updated from the refreshed update package; the exact latest backup path is recorded by the installer in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
5. Local `/health` and `duxyb/cnpe123` login smoke passed; installed hashes match source/package for the touched platform-standard command-flow files.

## 2026-06-16 mixed tray loop/offset closeout

Current latest source/validation state:

1. Mixed front/back tray layers are now rendered with APDL arrays and `*DO` loops instead of explicit Python-generated keypoints and lines. This keeps the generated command stream standardizable for seven-layer and other mixed layouts.
2. Same-side mixed tray widths are modeled from wider lower layers to narrower upper layers. Example: input `300+600` becomes model layer 1 `600` and model layer 2 `300`, so the small tray is above the large tray while original layer indices remain in `layer_geometry`.
3. Secondary-arm offset policy is explicit: `CAOGANG42DAN` keeps `SECOFFSET,user,,-0.03249`; non-channel secondary arms such as `YIXINGGANG150DAN` keep `SECOFFSET,user`.
4. Double-side root coupling now uses one CP set per layer/frame (`NROOT,NFROOT,NBROOT`) so MAPDL does not put the same support node UX into two coupled sets.
5. Native side text parsing now preserves the first width after labels such as `前侧300+600` and `后侧300+500`; it no longer consumes `300` as a side count.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/apdl/mixed_tray_model.py core/intake/tray_load_parser.py` passed.
2. Targeted parser/mixed-render tests passed.
3. Full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
4. Render smoke passed for single-side `300+600`, single-side seven-layer `300/500/600`, double-side mixed, and `YIXINGGANG` no-channel-offset cases.
5. Real ANSYS18.2 passed for `jobs/validation_mixed_loop_real_single_20260616_183024/MIXLOOP-SINGLE-300600`: selected `100-100-6`, controlling ratio `0.44156708491319885`, `result_validation.status=pass`.
6. Real ANSYS18.2 passed for `jobs/validation_mixed_loop_real_double_20260616_183434/MIXLOOP-DOUBLE-300600-300500`: selected `100-100-6`, controlling ratio `0.7684645157108101`, `result_validation.status=pass`.

Deployment closeout:

1. Server, desktop, and installer runtimes were rebuilt.
2. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
3. Update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecars beside the zip files as transfer authority.
4. Package gate and update self-verification passed.
5. Local `D:/CableTrayAI` was updated; the exact latest backup path is recorded by the installer in `D:/CableTrayAI/docs/last_internal_update_apply.json`; `/health` ok; `duxyb/cnpe123` login pass; source/package/installed hashes match for the mixed renderer, parser, and learning caches.

## 2026-06-16 tray-300 physical bolt modeling and small-tray L3 closeout

Current latest source/validation state:

1. The user-provided 300 mm and 200 mm standard PIP command streams were reviewed against the renderer logic.
2. For single-width/no-L6 S2 families, tray widths `<=300 mm` now always render `L3=0.15 m`, independent of selected square tube size. Tray widths above 300 mm keep the existing square-section-controlled L3 policy.
3. The 300 mm tray path now requires a real physical bolt/round-bar model, not only coupled nodes. Selection strongly prefers reviewed APDL families containing `ET,4,188`, `SECTYPE,10,BEAM,CSOLID`, `SECDATA,0.006`, `LATT,1,,4,,,,10`, and 506/507/508 physical line pairs. `CP/CPCYC` remains a supplementary coupling and cannot alone satisfy the 300 mm modeling gate.
4. The 200/100 mm small-tray path is intentionally separate: it uses the reviewed small-tray arm partition where `K502/1502` are at `H1/2+L1-L3`, `K503/1503` and the tray/CPCYC connection stay at `H1/2+L1-L2/2`, and the connector line moves from `502-509` to `503-509` when a larger family is reused.
5. Mixed-width fallback is fixed at render time. If a mixed intake such as 300/500 has to reuse a reviewed single-width maximum-width family, the generated `L2`, tray `SECREAD`, and density replacement now use the governing maximum width instead of the first listed smaller tray.
6. Web command-stream preview now labels and draws bolt/round-bar line elements separately, so the operator can visually confirm that the 300 mm physical bolt/round-bar lines are present rather than seeing only coupled points.

Verification:

1. `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py -q` passed.
2. `D:/miniconda3/python.exe -m pytest tests/unit/test_intake_standard_family_tray_widths.py tests/unit/test_square_section_selector.py tests/unit/test_static_method_no_modal_policy.py tests/unit/test_bolt_width_policy.py -q` passed.
3. Full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.
4. Node inline syntax check for `apps/web/index.html` passed.
5. Full render-entry smoke passed for `verify_double_300_3_2`: selected `source_materials/model_commands/报告及模型命令流/18185NI-LXSJ4155/计算文件/01双侧同类型电缆桥架-方钢300.PIP`, `L3=0.15`, `physical_bolt_modeling=pass`.
6. Full render-entry smoke passed for `verify_single_200_2`: `L3=0.15`, `physical_bolt_modeling=not_required`, and the small-tray path is not blocked by the 300 mm physical-bolt gate.
7. Full render-entry smoke passed for `verify_mixed_300_500`: selected reviewed 500 mm shared geometry, `L2=0.5`, `model_geometry_widths_mm=[500]`, and `shared_max_width_geometry=applied`.

Deployment closeout:

1. Server, desktop, and installer runtimes were rebuilt.
2. Full package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `0DD63988F61B00BB5AB61C590C1613E7E0CA667B3A5898C2EE952CB3B4A8318C`.
3. Update package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`, SHA256 `1171B1FB97138FCD6F2762BF9EC469796435CEC8E69D9DA35044434967212ECB`.
4. Package gate passed, including runtime XML support and no-expat spectrum smoke. Update package `-VerifyOnly` passed.
5. Local `D:/CableTrayAI` was updated from the new update package; backup is `D:/CableTrayAI/_update_backups/20260616_153124`.
6. Local smoke passed: `/health` returned `ok`, `duxyb/cnpe123` login returned `pass`, and installed `core/apdl/intake_standard_family_renderer.py` plus `apps/web/index.html` hashes match source.

## 2026-06-16 4215 smart section-selection and deployment closeout

Current latest source/validation state:

1. Root cause for `18185NI-LXSJ4215` starting at `160-160-8` on a 300 mm tray was stale square-section learning. Old cache evidence did not include tray width/load and could order a new small-tray job from unrelated larger-tray history.
2. The learned square-section path now accepts only the current v7 cache for direct learned decisions, includes tray-width/load similarity, and still requires a fresh real ANSYS/formal deterministic gate before publication.
3. Real ANSYS18.2 validation used a job-local six-row workbook with deliberately changed intakes: response-spectrum 300 single-side, response-spectrum 300 double-side, response-spectrum mixed 300/500 double-side, response-spectrum 600, static 300, and static 600.
4. Representative results: 300 single-side selected `100-100-6` with ratio `0.6334551866714465`; 300 double-side tried `100-100-6` first, failed it, then selected `120-120-10`; mixed 300/500 selected `140-140-8` with ratio about `0.905`; 600 response/static variants completed after larger-section recovery.
5. Candidate-trial/formal ratio differences are now handled correctly. The formal ANSYS deterministic Chapter 6.1 section-selection ratio is authoritative. If formal ratio is `<= 1.0`, the mismatch is recorded as `formal_override`; if formal ratio is `> 1.0`, the larger-section or support-spacing recovery path still runs.
6. ANSYS license-manager transient failures now retry the same candidate/formal calculation instead of marking a section as failed. LATT/already-meshed warnings are nonblocking; true MAPDL errors, missing deterministic outputs, and formal over-limit gates still block.
7. Verification passed: full `D:/miniconda3/python.exe -m pytest tests/unit -q`, targeted square-section/result-validity/renderer/runner tests, real ANSYS validation under `jobs/validation_4215_smart_selection_real_fix3_20260615_234758` and `jobs/validation_4215_smart_selection_real_fix5_DF_20260616_002328`.

Deployment closeout:

1. Full package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Mail-safe update package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
3. Package gate passed, including runtime XML/expat files and no-expat spectrum smoke.
4. Local `D:/CableTrayAI` was updated from the new update package. The exact latest backup path is recorded by the installer in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
5. Local deployment smoke passed: `/health` returned `{"status":"ok"}`, initial password remains `cnpe123`, and source/package/installed hashes match for touched source and calibration files.

## 2026-06-15 support-spacing recovery and representative real-ANSYS closeout

Current latest source/validation state:

1. Final over-limit recovery now covers the case where the selected square tube is already the largest intake-allowed section. If deterministic final gates still fail, the workflow reduces `support_spacing_m`, rerenders APDL, reruns section selection, and reruns formal real ANSYS instead of stopping.
2. The recovery evidence is not limited to Section 6.1 square-support rows. Weld/connection final ratio failures also trigger spacing reduction when the square tube can no longer be enlarged, which covers the user-reported 600 mm static case.
3. Spacing recovery continues in 0.1 m steps. Therefore a 600 mm static job with `160-160-8` and 1.8 m spacing still over weld limit will try the next smaller spacing rather than fail as a software error.
4. The 300 mm single-side modeling root cause was fixed separately: single-width/no-L6 standard-family connection/CPCYC selectors now use `H1/2+L1-L3`, matching the square-section-controlled `L3` policy. Double-side and multi-width families keep the reviewed source `L2/2` topology.
5. BEAM188 warping KEYOPTs are restored when source-family snippets omit them, and empty line-mesh blocks are guarded so low-layer/new-intake variants do not abort on empty `LSEL` groups.
6. Real ANSYS18.2 regression passed on a job-local workbook covering 300/500/600 response spectrum and 300/500/600 static. All six rows reached `result_validation.status=pass`.
7. The 600 static representative case selected `160-160-8`, detected over-limit weld/structural evidence, reduced spacing `2.0 m -> 1.7 m`, and then passed with final max weld ratio about `0.9821` and square/support ratio about `0.8647`.
8. Verification passed: full `D:/miniconda3/python.exe -m pytest tests/unit -q` and real ANSYS result `jobs/validation_spacing_recovery_20260615_175157/real_ansys_result_full_regression2_20260615_185147.json`.

Deployment closeout:

1. Rebuilt `runtime/CableTrayAI_Server/CableTrayAI_Server.exe` and refreshed the full package `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Refreshed the mail-safe update package `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; update VerifyOnly passed.
3. Refreshed external SHA256 sidecars beside both zip files. Use those sidecars as transfer authority; do not embed zip hashes inside packaged docs because that is self-referential.
4. Applied the update to local `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
5. Local deployment smoke passed: `/health` returned `ok`, `duxyb/cnpe123` login returned `pass`, and source/package/installed hashes match for the touched source, docs, and calibration files.

## 2026-06-15 unit jobs square-section and bolt-width policy closeout

Current latest source/validation state:

1. Copied unit jobs under `C:/Users/duxy/Desktop/jobs` were reviewed. `18185NI-LXSJ4210` selected `140-140-8` with an old stored trial ratio `0.9052401909300667`, while the final Chapter 6.1 structural section ratio is `0.4466859099481754`. `18185NI-LXSJ4215` selected `160-160-8` with an old stored ratio `0.9131067176524903`, while final Chapter 6.1 structural section ratio is `0.09814480040795198` and full Chapter 6 max is weld ratio `0.17789216054697474`.
2. Root cause fixed: square-section sizing now uses only Chapter 6.1 structural member rows (square support, cantilever arm, mixed beam/support). Weld and bolt ratios remain final publication gates, but they cannot enlarge square tubes or drive economy decisions.
3. Learned square-section cache is now versioned as `square-section-cache-v7-section-6-1-ratio`; old entries cannot direct-skip fresh candidate trials. Learned formal validation also requires historical dominant 6.1 structural evidence.
4. Standard S2 single-width/no-L6 modeling now assigns `L3` from selected square-tube outer width: `<=120 mm -> 0.20 m`, `>120 mm -> 0.15 m`. Multi-width source families keep `L3/L4` as tray-width parameters.
5. Bolt evaluation now follows the manual/workbook formula family, not just area replacement. `<=200 mm` tray widths use M8 area `36.6 mm2`, force share `1`, no lever-arm division, and workbook `螺栓 200` formulas. `300/500/600 mm` use M12 area `84.3 mm2`, force share `2`, and lever arms `0.241/0.441/0.541 m`.
6. `18185NI-LXSJ4212` in the copied unit folder has no `evaluation_summary.json` because the latest run was cancelled by operator after ANSYS/connection export completion. It should be treated as incomplete runtime/post-processing evidence, not a section over-limit result.
7. Verification passed: `D:/miniconda3/python.exe -m py_compile core/evaluators/bolt.py core/evaluators/summary.py core/optimizer/square_section_selector.py core/optimizer/square_section_workflow.py core/optimizer/square_section_summary.py core/validation/result_validity_gate.py core/apdl/intake_standard_family_renderer.py`; targeted square-section/model/bolt tests passed; full `D:/miniconda3/python.exe -m pytest tests/unit -q` passed.

Deployment closeout:

1. Rebuilt `runtime/CableTrayAI_Server/CableTrayAI_Server.exe` at `2026-06-15T17:03:33+08:00` so the packaged web service contains the latest Section 6.1 square-section sizing, `L3`, and M8/M12 formula-family fixes.
2. Refreshed the full deployment package under `C:/Users/duxy/Desktop/duxyb-cnpe`: `CableTrayAI/` and `CableTrayAI.zip`.
3. Refreshed the mail-safe update package under `C:/Users/duxy/Desktop/duxyb-cnpe`: `更新包/` and `更新包.zip`; update self-verification passed.
4. Refreshed SHA256 sidecars: `CableTrayAI.zip.sha256.txt` and `更新包.zip.sha256.txt`.
5. Deployment package gate passed: protected runtime directories are absent, `pyexpat.pyd`/`_elementtree.pyd`/`libexpat.dll` are present, and the no-expat spectrum smoke test passed with `active_column_m_calibrated_precision_output`.
6. Package password remains `cnpe123` via `config/initial_password.txt`.
7. Applied the refreshed update package to local `D:/CableTrayAI`; `/health` returned `{"status":"ok"}`, `duxyb/cnpe123` login returned `pass`, and source/package/installed hashes match for the touched evaluator, selector, APDL renderer, and server runtime files.

## 2026-06-12 AI PPT专题交付复核 closeout

1. 已重新完成河北省军工杯汇报用 AI/智能化专题 PPT，桌面交付文件为 `C:/Users/duxy/Desktop/核电工艺所人工智能应用汇报-AI智能化专题.pptx`。
2. PPT 为 10 页，正文、表格、流程图和指标均为可编辑对象；第 7 页嵌入完整 16:9 真实软件演示视频，不再用遮挡画面的局部截图。
3. 独立视频备份已复制到 `C:/Users/duxy/Desktop/CableTrayAI_对话提资完整演示.mp4`，素材来自本机真实对话提资/结果核查页面和完成的真实 ANSYS 作业。
4. Visio 可编辑流程源文件已复制到 `C:/Users/duxy/Desktop/CableTrayAI_flow_source.vsdx`，包含 `AI数据闭环`、`可学习与自恢复`、`多科室协同` 3 个页面。
5. 交付验证通过：PowerPoint 打开桌面 PPT 成功，`slides=10`，`media_shapes=1`，`slide7_media=1`；PPT 包内包含 `ppt/media/media1.mp4`；占位符扫描通过；Visio 打开源文件页数为 3。

## 2026-06-12 PPT and real demo closeout

1. 河北省军工杯汇报材料已完成并复制到桌面：`C:/Users/duxy/Desktop/核电工艺所人工智能应用汇报-军工杯成稿.pptx`。
2. PPT 共 10 页，包含电缆桥架两页：一页原理与研发步骤，一页嵌入真实软件调用演示视频。
3. 演示视频源于本机真实运行：`CHAT-20260612-f2317f9b9b`，状态 `pass`，真实 ANSYS 成功，选定 `140-140-8`，控制比值 `0.9074547160463298`，`result_publishable=true`。
4. 发现并修复演示阻塞问题：`/ai/intake/start-run` 返回值和 run 状态现在会将 `Path` / datetime 等对象转换为 JSON-safe 值；对话提资启动真实计算时不再把 `source_package_id="chat_intake"` 传入标准命令包匹配器。
5. 验证：`tests/unit/test_ai_intake_api.py tests/unit/test_chat_intake.py tests/unit/test_run_progress_state.py` 通过；PPT 文本占位符扫描通过；PowerPoint 打开桌面 PPT 成功，`slides=10`，`media_shapes=1`。
6. 同步交付：`C:/Users/duxy/Desktop/CableTrayAI_对话提资演示.mp4` 和 `C:/Users/duxy/Desktop/CableTrayAI_flow_source.vsdx`。

## 2026-06-12 unit jobs self-recovery closeout

Current latest source/validation state:

1. Unit copied evidence under `C:/Users/duxy/Desktop/jobs` was reviewed. `18185NI-LXSJ4211` was already publishable (`result_validation.status=pass`, selected `160-160-8`, ratio about `0.6125`). `18185NI-LXSJ4212` had completed ANSYS but failed final deterministic ratio gates after an old learned `120-120-6` choice. `18185NI-LXSJ4215` completed the main MAPDL stream but failed only in post-only figure export because the ANSYS license manager was temporarily unavailable.
2. Root cause for the 4212 “over-limit stops” class: old v5 learned cache evidence could still direct-select a section, and the post-formal upgrade trigger only recognized square-support evidence. The failed 4212 controlling rows were weld/bolt/cantilever/mixed-beam ratios, so the job stopped instead of automatically trying the next larger allowed sections.
3. `core/optimizer/square_section_workflow.py` now permits direct learned-formal skip only from the current cache version, treats any final deterministic `evaluation_ratio_limit` failure as an upgrade trigger when the square section was auto-selected and larger intake-allowed sections exist, resets failed job state to `apdl_rendered` after a successful upgrade, and writes the upgraded choice back to `square_section_selection.json`.
4. `core/optimizer/square_section_selector.py` now keeps candidate trial directories clean by excluding inherited `job_state.json`, `ansys_live_status.json`, and `figure_export_live_status.json`. Candidate trials no longer inherit a previous failed parent state that would make ANSYS preflight reject the trial before it runs.
5. `core/ansys/runner.py` now handles relative trial job paths during stale completion cleanup, retries post-only figure export when ANSYS license-manager output indicates a transient license unavailable state, and records `post_export_license_unavailable` in the audit.
6. `core/pipeline/one_click.py` now assembles numeric LIS/OUP results for diagnosis when main ANSYS succeeds but post-only figure export fails, and preserves DB/RST artifacts for later figure retry instead of cleaning them immediately.
7. Real ANSYS18.2 validation using the copied unit `18185NI-LXSJ4212` failure reproduced and fixed the intended AI-like recovery path: before fix it needed upgrade; after fix it ran `120-120-10` (failed, ratio `1.4624074146092667`), then `160-160-8` (passed, ratio `0.8480306526316335`), rewrote `square_section_selection.json` to `160-160-8`, formal ANSYS rerun succeeded, and final `result_validation.status=pass` with no fail checks.
8. Verification passed: `D:/miniconda3/python.exe -m pytest tests/unit -q`, targeted square-section workflow/selector, ANSYS runtime, post-export retry, and one-click cleanup tests, plus `py_compile` for touched modules.
9. Temporary local validation job folders named `jobs/verify_unit_4212_self_recovery_*` were removed after recording the results, keeping the source tree/package clean.
10. The unit login failure class was also fixed during final package smoke: `config/initial_password.txt` is now written as UTF-8 without BOM, and the Python/PowerShell/native C# installers strip a BOM if they ever read an older password file. This prevents `cnpe123` from being hashed as `\ufeffcnpe123`.
11. Refreshed package outputs are under `C:/Users/duxy/Desktop/duxyb-cnpe`: `CableTrayAI.zip`, `更新包.zip`, and their external `.sha256.txt` sidecars. Use the sidecars as transfer authority; do not embed package hashes inside packaged docs.
12. Final package verification passed: deployment package gate, update package self verification, initial password hex check (`cnpe123\n`, no BOM), temporary installed-server `/health=ok`, temporary installed `duxyb/cnpe123` login `pass`, package cleanliness scan, and source/package hash checks for touched files.
13. Local `D:/CableTrayAI` is now refreshed and verified. The old locked PID `21532` could not be stopped with `Stop-Process` or `taskkill`, but `wmic process where processid=21532 call terminate` returned `0`; the update package then applied successfully with backup `D:/CableTrayAI/_update_backups/20260612_105433`. The fresh server is PID `25224` from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`; `/health` returns `ok`, `duxyb/cnpe123` login returns `pass`, package gate and update self-verification pass, initial password is UTF-8 without BOM, and key installed source hashes match the repository.

Deployment next step:

1. For the unit, use the refreshed `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip` for an existing deployment or `CableTrayAI.zip` for a fresh deployment; verify with the `.sha256.txt` sidecars.
2. Local machine follow-up is closed: port `8000` is now served by fresh PID `25224` from `D:/CableTrayAI`, so the existing local web service can be used as the latest-code smoke target.

## 2026-06-11 unit 4211 connection-node export timeout closeout

Current latest source/validation state:

1. Unit copied folder `C:/Users/duxy/Desktop/18185NI-LXSJ4211` failed with `ANSYS post-export failed: connection_node_export failed - connection node export exceeded timeout_seconds=300`.
2. The retained evidence proves this was not a model, spectrum, section, or evaluation failure: main MAPDL had `ROUTINE COMPLETED` and `ERROR=0`; `LS-FORCE-NODES.LIS` existed; `connection_node_export.out` also ended with `ROUTINE COMPLETED`, `ERROR=0`, and 141 warnings only. The old code still marked it failed because `subprocess.run(timeout=300)` fired first.
3. `core/ansys/connection_export.py` now uses a soft monitor instead of a hard 300s timeout, writes `/EXIT,NOSAV` into `export_connection_nodes.mac`, accepts completed MAPDL output only when `LS-FORCE-NODES.LIS` exists and `ROUTINE COMPLETED` plus zero MAPDL errors are present, and clears stale `LS-FORCE-NODES.LIS` / `connection_node_export.out` before reruns.
4. The copied failed unit output was reassembled without rerunning ANSYS at `jobs/verify_unit_4211_connection_export_outputs_20260611_174956/18185NI-LXSJ4211`: `result.json` generated, `result_validation.status=pass`, `result_publishable=true`, and `connection_node_force_results` has 262 rows.
5. Real ANSYS18.2 validation passed at `jobs/verify_unit_4211_connection_export_fix_20260611_175038/18185NI-LXSJ4211`: `ansys_run_audit.status=success`, main duration `119.420748s`, `connection_node_export_status=success`, `figure_export_status=success`, `figure_count=14`, `result_validation.status=pass`, `result_publishable=true`, and total wall time about `167.8s`.
6. Verification passed after the fix: `D:/miniconda3/python.exe -m pytest tests/unit -q`, plus targeted post-export stream/completion tests.
7. Deployment closeout after this fix: refresh `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`, apply the update locally to `D:/CableTrayAI`, verify `/health`, `duxyb/cnpe123` login, key source/package/installed hashes, and package cleanliness. Use the external `.sha256.txt` sidecars in that folder as transfer authority.

## 2026-06-11 unit 4211 50-minute stall root-cause closeout

Current latest source/validation state:

1. Unit copied evidence from `C:/Users/duxy/Desktop/18185NI-LXSJ4211` and `_square_section_trials-18185NI-LXSJ4211` shows two separate causes for the apparent stall: candidate selection re-ran expensive 160/140 trials even though the learned 4211 evidence already proved `160-160-8` passes and the immediately lower `140-140-8` fails, and the formal post-only figure export finished inside MAPDL but the old macro did not force a no-save exit, so ANSYS18.2 could linger at launcher/DB-save exit.
2. The economy rule is still active: when a fresh passing candidate has `0.60 <= ratio <= 0.75`, the selector normally runs exactly one immediately lower intake-allowed section. It skips that duplicate lower trial only when a high-similarity learned cache hit (`score >= 0.95`) already contains real ANSYS evidence that the immediately lower section completed and failed with ratio `> 1.0`.
3. Learned formal validation never publishes a historical result. It only chooses the current formal section and requires the current job's full ANSYS/result-validation run to pass. If the final deterministic ratio exceeds 1.0, the existing upgrade/reselection gates still block and recover.
4. `core/ansys/figure_export.py` now writes `/EXIT,NOSAV` in `export_figures.mac` and can accept a completed MAPDL graphics export with `ROUTINE COMPLETED` and `ERROR=0` even if the ANSYS launcher return is nonzero or lingers. Required named figures still gate success; missing figures still fail publication.
5. `core/ansys/runner.py` now removes stale completion-marker files before every new real ANSYS run, so old `8TEG009010.TXT` or `ansys.out` cannot validate a new calculation before fresh output is produced.
6. Real ANSYS18.2 validation passed at `jobs/verify_4211_unit_hang_fix_20260611_114124/18185NI-LXSJ4211`: `run_real_ansys` status `success`, main duration `116.635979s`, figure export status `success`, `figure_count=14`, `result_validation.status=pass`, `result_publishable=true`, total wall time about `162.2s`.
7. Verification passed after the fix: `D:/miniconda3/python.exe -m pytest tests/unit -q`, plus targeted tests for figure-export completion markers, stale completion cleanup, learned formal validation, and result-validity handling.
8. Deployment closeout after this fix: refresh `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`, apply the update locally to `D:/CableTrayAI`, verify `/health`, `duxyb/cnpe123` login, key source/package/installed hashes, and package cleanliness. Use the external `.sha256.txt` sidecars in that folder as transfer authority.

## 2026-06-11 ??4211/4212?????????????? closeout

Current latest source/validation state:

1. ????????? `C:/Users/duxy/Desktop/_square_section_trials` ????4211 ? `160-160-8` ? 4212 ? `120-120-6` ???? `MAXBEAMSTRESS.LIS`?`SQUAREBEAMSTRESS.LIS`?`JCZH.LIS`?`LS-FORCE.LIS`?`Mode.oup` ???????? `8TEG009010.TXT` ??? `ROUTINE COMPLETED`?`EXIT ANSYS WITHOUT SAVING DATABASE`?`NUMBER OF ERROR MESSAGES ENCOUNTERED=0`?
2. ??????????????????? numeric post ?????????? ANSYS18.2 ? APDL ?????? `4294967295`????? launcher returncode ?????????????? `failed`?????????????????
3. `core/ansys/runner.py` ?????????? `*.TXT`?????? MAPDL ???????????????? MAPDL ??? `0` ???? ANSYS launcher ???????????????? LIS/OUP?????????????????????
4. ??????????????????????????? ANSYS `15s` ??????????????? job ????? job ??????? `ansys_run_audit.json` ?? `completion_marker_cleanup`?????????????? APDL ?????? `ERROR=0` ????
5. ??????????????????`candidate_section`?`trial_dir`?`trial_status_file`?`elapsed_seconds`?`total_output_bytes`?`no_output_seconds`?`ansys_pid` ??????????????????????????????
6. ??????????????????????LIS/OUP?JSON????? live status ??? `_square_section_trials`??? DB/RST ????????????????????
7. ?????????4211 `160-160-8` ????? LIS/OUP ????????? `0.6125688698630086`????4212 `120-120-6` ????????????????????????????
8. ??????`py_compile`????? `tests/unit/test_ansys_runtime_timeout_policy.py tests/unit/test_square_section_workflow_policy.py -q`??? `D:/miniconda3/python.exe -m pytest tests/unit -q`??? 4211/4212 ???????????? `pass accept_4294967295=True`?
9. ?? ANSYS18.2 ????????? 4212 `120-120-6` ????? `jobs/verify_unit_completion_marker_real_20260611/18185NI-LXSJ4212_120-120-6` ????? `47.9s` ???`post_exports_enabled=false`???? `assemble_result`?
10. ???????`C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` ? `C:/Users/duxy/Desktop/duxyb-cnpe/???.zip` ?????? `.sha256.txt` ???????????????????????? zip hash???????? `D:/CableTrayAI`?`/health=ok`?`duxyb/cnpe123` ??????????? source/package/install hash ???

# CableTrayAI 当前工作状态
## 2026-06-10 单位4211/4212导图卡住与候选试算提速 closeout

Current latest source/runtime/package target:

1. 单位 4212 保留目录 `C:/Users/duxy/Desktop/18185NI-LXSJ4212/20260610T095741698491Z/120-120-6` 已复核。失败根因不是建模/计算/评定公式，而是方钢候选试算的主 `run_all.mac` 仍执行完整 `generated_post.mac` 中的 `/IMAGE,SAVE` 图形命令，ANSYS18.2 批处理下大量报 `/IMAGE requires /MENU,ON or /MENU,GRPH`，随后触发 `output_stall_timeout`，导致没有 `evaluation_summary.json`。
2. 新增内部数值后处理宏 `generated_post_numeric.mac`：真实 ANSYS 主流程只跑 LIS/OUP/载荷等数值提取，跳过 `/IMAGE`、`PLLS`、`EPLOT` 等图形命令；原始 `generated_post.mac` 仍保留用于人工审查和 post-only 导图宏转换。
3. `run_all.mac` 现在可调用内部 numeric post 宏；`generated_model.mac / generated_solve.mac / generated_post.mac` 三份审查命令仍按原规则保留和发布。
4. 方钢候选试算禁用“输出停滞硬杀” watchdog，避免再把单位慢机上的 ANSYS 后处理误判为截面失败；提速依靠跳过候选阶段图片命令，不靠缩短超时。
5. `run_figure_export` 已改为启动即写 `figure_export_audit.json` 和 `figure_export_live_status.json`，`timeout_minutes` 只作为软监控阈值，不再硬杀 MAPDL；正式导图仍由独立 `export_figures.mac` 完成。
6. 使用单位拷回的 4212 失败 job 真实 ANSYS18.2 重跑通过：`jobs/verify_4212_numeric_post_20260610_194331/18185NI-LXSJ4212_120-120-6`，主数值流程 `50.1s` 成功，`generated_post_numeric_audit.json` 记录跳过 `267` 条图形命令，`assemble_result` 得到 `36` 条梁应力和 `3` 条基础载荷。
7. 同一 job 的 post-only 导图验证通过：`figure_export_audit.json` 状态 `success`，耗时 `20.1s`，`figure_count=22`，`missing_required_figures=[]`，`hard_timeout_policy=disabled`。
8. 验证已通过：`D:/miniconda3/python.exe -m pytest tests/unit -q`，以及 targeted numeric-post/runtime/导图/截面选型测试。
9. 部署包已刷新到 `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`，SHA256 `1BDBF15E04942FF850E8C355C3B7B3AE143C1671DC772BCB4492E1AF9838D0C7`；更新包已刷新到 `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`，SHA256 `262273C60ABE0399F8FA06711BE92D920C3B40AA61C571437927E6F8824D38D3`。
10. 本机 `D:/CableTrayAI` 已用该更新包更新，`/health=ok`，`duxyb/cnpe123` 登录 `pass`，关键运行文件 source/package/installed SHA256 一致。

## 2026-06-10 异型钢 SECOFFSET 修正 closeout

Current latest source/package target:

1. 用户确认异型钢建模命令流中不能继续使用槽钢专用偏置 `SECOFFSET,user,,-0.03249`，异型钢分支应输出 `SECOFFSET,user`。
2. 新增 `core/apdl/section_offsets.py`：只在 `SECOFFSET,user,,-0.03249` 后续对应的 `SECREAD` 已经是 `YIXINGGANG*` 时归一化为 `SECOFFSET,user`；后续仍是 `CAOGANG42DAN` 的槽钢分支保持原命令不变。
3. 标准族建模渲染和方钢截面试算/正式替换入口均已接入该规则，并在审计字段 `yixing_secoffset_replacements` 中记录修正次数。
4. 验证已通过：`D:/miniconda3/python.exe -m pytest tests/unit/test_yixing_secoffset_policy.py tests/unit/test_square_section_workflow_policy.py tests/unit/test_intake_standard_family_tray_widths.py -q` 和 `D:/miniconda3/python.exe -m pytest tests/unit/test_square_section_selector.py tests/unit/test_square_section_workflow_policy.py tests/unit/test_yixing_secoffset_policy.py -q`。
5. `source_materials` 未修改，槽钢原始资料和槽钢分支输出仍保留 `-0.03249`。
6. 部署包已刷新到 `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`，更新包已刷新到 `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`；使用同目录 `.sha256.txt` 旁路文件作为传输校验依据。
7. 本机 `D:/CableTrayAI` 已用该更新包更新，`/health` 为 `ok`，`duxyb/cnpe123` 登录返回 `pass`，关键运行文件 source/package/installed SHA256 一致。

## 2026-06-09 4211 economy downshift strategy closeout

Current latest source/validation state:

1. User requested a less conservative square-section strategy: when a passing candidate lands in `0.60 <= ratio <= 0.75`, run the immediately lower intake-allowed square section once before final selection. Example intent: if `160-160-8` is around `0.61`, verify `140-140-8` instead of accepting the larger section immediately.
2. `core/optimizer/square_section_selector.py` now records `ECONOMIC_DOWNSHIFT_RATIO_MAX = 0.75` and `ECONOMY_DOWNSHIFT_SECTION_TRIALS = 1`. The normal two-candidate economy strategy remains; this is a single bounded economy check, not a full downward sweep.
3. The downshift is allowed only in production auto-stop mode. Manual/diagnostic searches with `stop_after_first_feasible=False` keep their original search trace.
4. If the lower candidate passes, the normal deterministic selector picks the more economical passing section. If the lower candidate fails, the already passing larger section remains selected. Already evaluated candidates are skipped so a downshift failure cannot rerun the same larger section again.
5. Regression tests were added for both branches: `160-160-8` low-ratio downshifts to passing `140-140-8`, and `160-160-8` remains selected when `140-140-8` fails.
6. Verification passed: `D:/miniconda3/python.exe -m pytest tests/unit/test_square_section_selector.py -q`, targeted workflow/postprocessor/result-validity tests, `py_compile`, and full `D:/miniconda3/python.exe -m pytest tests/unit -q`.
7. Real ANSYS18.2 validation passed at `jobs/verify_4211_economy_downshift_20260609_202204/18185NI-LXSJ4211`. The selector did the requested downshift: `160-160-8` ratio `0.6125191042609882`, then `140-140-8` ratio `1.1132861849732167`.
8. Because the fresh ANSYS result for `140-140-8` is still over limit, the formal selected section correctly remains `160-160-8`; `result_validation.json` status is `pass`, `result_publishable=true`, and `ansys_run_audit.json` status is `success` with `figure_count=14`.
9. Deployment/update closeout completed after this fix. Send-folder outputs are `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecars in that folder as transfer authority.
10. Package gates passed: deployment package gate, update package self verification, outer and nested zip forbidden-path scan, local `D:/CableTrayAI` update apply, `/health` ok, `duxyb/cnpe123` login pass, and source/package/installed hashes match for the touched selector/docs.

## 2026-06-09 unit 4211 overlimit recovery and H1 geometry closeout

Current latest source/validation state:

1. Unit 4211 copied evidence under `C:/Users/duxy/Desktop/18185NI-LXSJ4211/20260609T074104184351Z` was reviewed. The failure was a real two-candidate over-limit case, not missing-output or timeout evidence: `100-100-6` ratio was `1.3581785618588114`, and `120-120-10` ratio was `1.6479509969960606`.
2. The same evidence exposed a modeling defect in candidate trials: `120-120-10` had `input.json` support width `0.12` and post H1 `0.120000`, but `generated_model.mac` still had `H1=0.1`. That means the trial model geometry did not follow the square-tube outer side length.
3. `core/optimizer/square_section_selector.py` now synchronizes `generated_model.mac` H1 from the square section outer width for every trial and formal selected section. Thickness does not affect H1, so `120-120-6`, `120-120-8`, and `120-120-10` all write H1 as `0.120000`.
4. The normal economy policy is still two candidate trials. If both normal trials finish successfully and both are deterministic over-limit (`ratio > 1.0`), the selector now extends by at most two larger intake-allowed square sections instead of failing immediately.
5. The over-limit extension is audit-traceable in `square_section_selection.json` through `overlimit_recovery_extensions`, `effective_evaluated_candidate_budget`, and the preserved base `max_evaluated_candidates=2`.
6. Regression tests were added for H1 outer-width synchronization and the two-overlimit-plus-two-larger recovery policy.
7. Verification passed: `pytest tests/unit/test_square_section_selector.py -q`, targeted selector/workflow/postprocessor/result-validity tests, and full `pytest tests/unit -q`.
8. Real ANSYS18.2 validation passed at `jobs/verify_4211_h1_overlimit_recovery_20260609_172633/18185NI-LXSJ4211`: the selector evaluated `100-100-6`, `120-120-10`, then recovered to `160-160-8`; selected ratio was `0.6132882273722775`, formal `result_validation.json` status was `pass`, and `ansys_run_audit.json` recorded `figure_count=14`.
9. Deployment/update packages were refreshed after this fix. The transfer authority is the `.sha256.txt` sidecar files in `C:/Users/duxy/Desktop/duxyb-cnpe`, not an embedded hash inside this document.

## 2026-06-09 unit 4210 ANSYS timeout false section-failure closeout

Current latest source/runtime/package state:

1. Unit-copied evidence under `C:/Users/duxy/Desktop/_square_section_trials` was reviewed. The current 4210 failures were not deterministic section over-ratio failures: candidate `140-140-8` was killed by ANSYS total timeout before `evaluation_summary.json`/result outputs were produced.
2. The unit 4210 audit `C:/Users/duxy/Desktop/_square_section_trials/18185NI-LXSJ4210/20260609T032119173447Z/140-140-8/ansys_run_audit.json` recorded `status=timeout`, `duration_seconds=723.0`, `timeout_seconds=720`. The command-stream hashes for model/solve/post/spectrum matched the locally passing 4210 run, so this was runtime watchdog policy, not modeling/spectrum/solve logic.
3. Root cause fixed in `core/optimizer/square_section_workflow.py`: candidate trials no longer force `timeout_minutes <= 12`. They now use production-safe watchdogs, because a candidate trial still must produce deterministic APDL/PIP outputs before a section decision is valid.
4. Runtime hardening added in `core/ansys/runner.py`: every real ANSYS production run records configured watchdog values but applies code-level minimums of `timeout_minutes=120`, `startup_no_output_timeout_seconds=90`, and `output_stall_timeout_seconds=300`. This prevents unit-site preserved `config/ansys.local.toml` values from killing valid solves after an update package preserves local config.
5. `core/optimizer/square_section_selector.py` now reports ANSYS timeouts as runtime timeout failures, not square-section over-limit decisions. The old generic `missing/UNKNOWN/all-zero/stalled` line is no longer used for ANSYS timeout without a computed ratio.
6. Regression coverage added in `tests/unit/test_ansys_runtime_timeout_policy.py` for stale unit `timeout_minutes=12`, safer timeout preservation, and square-section trial config watchdogs.
7. Verification passed: targeted ANSYS/runtime and square-section tests passed; full `pytest tests/unit -q` passed with `115 passed`.
8. Real ANSYS18.2 validation reproduced the unit old-config condition by running 4210 with script `-TimeoutMinutes 12` at `jobs/verify_unit_4210_timeout_clamp_20260609_123539/18185NI-LXSJ4210`. The job passed, selected `140-140-8`, controlling ratio `0.9052401909300667`, `result_validation.json` status `pass`, `figure_count=14`.
9. The validation `ansys_run_audit.json` proves the clamp: `configured_timeout_seconds=720`, `configured_timeout_minutes=12`, effective `timeout_seconds=7200`, `timeout_policy.status=clamped`, ANSYS `status=success`, duration about `133.5s`.
10. Local `config/ansys.local.toml` was restored to `timeout_minutes = 120` after the deliberate 12-minute reproduction.

## 2026-06-09 unit 4210 candidate-output fallback closeout

Current latest source/runtime/package state:

1. Unit 4210 reported `140*8` candidate blocked as `required ansys/pip source outputs are missing ... all-zero or stalled`, even though `140-140-8` is the correct satisfying section.
2. Root cause class fixed in `core/optimizer/square_section_selector.py`: a candidate with fresh deterministic ratio `<= 1.0` is no longer reported as a section-capacity failure when the only blocker is candidate-trial source output completeness such as `Mode.oup`, `JCZH.LIS`, `LS-FORCE.LIS`, `HF-FORCE.LIS`, `MAXBEAMSTRESS.LIS`, or `TMAXBEAMSTRESS.LIS`.
3. New policy: do not keep enlarging the square tube for candidate-only source-output defects. Apply the feasible candidate to the formal job and run the full ANSYS/PIP calculation once; final publication still requires the formal `result_validation.json` to pass.
4. `core/pipeline/one_click.py` failure messages now include candidate section, ratio, run status, failed checks, domains, and `trial_dir`, so a unit-site failure can be diagnosed from the retained job directory instead of a generic `unknown/all-zero` line.
5. Formal validation mode is written to `input.json` metadata as `square_section_selection_validation_mode`; formal-fallback candidates are traceable through `square_section_selection_requires_formal_validation`.
6. Verification passed: full `tests/unit` (`112 passed`), targeted result-validity/package/auth tests, and `py_compile` for the touched modules.
7. Real ANSYS18.2 verification passed for the unit-uploaded 4210 intake row at `jobs/verify_unit_4210_candidate_fallback_20260609_091048/18185NI-LXSJ4210`: selected `140-140-8`, controlling ratio `0.9052401909300667`, formal `result_validation.json` status `pass`, 14/14 checks pass.
8. Runtime/package refreshed: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, size `78976672`, SHA256 `83E499A079FD148468A5E9BB4958F106751902CD63D2A86ECFBFAB29AAC9C6F3`; `C:/Users/duxy/Desktop/duxyb-update/更新包.zip`, size `78540520`, SHA256 `E00426429D18887ECD983D601A8653EC0426D6071E942CC35F418977FE661E50`.
9. Local installed deployment updated through the mail-safe update package; backup `D:/CableTrayAI/_update_backups/20260609_091931`, `/health` returned `{"status":"ok"}`, and source/package/installed hashes match for the selector, workflow, and one-click pipeline.
10. Latest full deployment zip was copied to `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` with `CableTrayAI.zip.sha256.txt`.

## 2026-06-08 two-trial square-section economy strategy closeout

Current latest source/runtime target:

1. 方钢自动选型生产策略已改为“最多两次候选试算”：第一次来自相似提资学习或确定性工程估算；若第一次不在经济区间，再按截面模量做一次修正候选。
2. 经济区间固定为 `0.60 <= ratio <= 0.9999`。候选控制比落入该区间即认为经济性满足并停止；`ratio > 1.0` 仍必须失败。
3. 提资“计算说明”允许截面仍是硬边界；学习和估算只能在允许列表内移动起算截面，不能新增未列截面，不能复用历史结果替代当前真实 ANSYS。
4. 网页进度候选总数已按本轮策略上限显示， bounded 选型显示 `0/2`、`1/2`，不再把全量允许列表显示成 `0/6` 造成误解；审查 JSON 仍保留 `available_candidate_count`。
5. 真实 ANSYS18.2 三行验证通过，且 `exact_result_reuse_enabled=false`：`4210 -> 140-140-8, ratio 0.9052401909300667`；`4213 static -> 120-120-10, ratio 0.8025890143573237`；`4215/raw-6 -> 160-160-8, ratio 0.9131067176524903`。
6. 三个正式 job 的 `result_validation.json` 均为 `pass`，选型实际候选次数分别为 `1/2`、`1/2`、`1/2`，输出目录为 `E:/CODEX/tray_platform/ANSYS Output/verify_two_trial_section_strategy_20260608_173006`。
7. 验证通过：`py_compile`、`tests/unit/test_square_section_selector.py tests/unit/test_square_section_workflow_policy.py`、全量 `tests/unit`。
8. 部署收尾完成：服务器运行时已重建，全量部署包和 `更新包.zip` 已重新生成，更新包已应用到 `D:/CableTrayAI`，`/health` 与 `duxyb/cnpe123` 登录通过，包洁净核查通过。

## 2026-06-08 raw-6 / 18185NI-LXSJ4215 unit-run hotfix closeout

Current latest runtime/package state:

1. Unit reported the last intake row (`raw-6`, `18185NI-LXSJ4215`) returned `Square section auto-selection failed...` even though the corresponding section should satisfy the check with a ratio around `0.99`.
2. Root cause class fixed: candidate section acceptance now uses the freshly generated `evaluation_summary.json` maximum deterministic Chapter 6 ratio as the controlling ratio. `result_validation.json:evaluation_ratio_limit` evidence is retained for audit only and cannot make a fresh `0.99` candidate fail because of stale validation evidence.
3. Candidate section pass/fail boundary is now consistent with the project rule: only ratios `> 1.0` fail; `<= 1.0` passes and stops the section search. The summary/report-side selection acceptance was aligned to the same rule.
4. The one-click failure message now includes candidate section, ratio, status, and non-ratio failed checks so a future site failure immediately shows whether the blocker is over-ratio or missing/blank source output.
5. ANSYS output scanning was tightened for the second unit error: WARNING-level `file_or_permission_error` file probes no longer block a real run at the text-scan layer, while ERROR/FATAL file/permission messages still block. Missing required LIS/OUP/figures remain blocked by deterministic result validation.
6. Verification passed: targeted square-section and ANSYS warning-gate tests; full `tests/unit`; row6 historical real result readback shows selected `160-160-8`, maximum ratio `0.9131955968601544`, `selection_status=pass`.
7. Runtime rebuilt: `runtime/CableTrayAI_Server/CableTrayAI_Server.exe` was rebuilt with PyInstaller, and desktop/installer runtimes were regenerated so the package is not missing startup/install files.
8. Full deployment package rebuilt and gated at `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`; use the generated package file and final closeout hash as the transfer authority.
9. Mail-safe update package rebuilt and verified at `C:/Users/duxy/Desktop/duxyb-update/更新包.zip`; the extracted `manifest/update_manifest.json` records the payload SHA256 and payload file count.
10. Local installed deployment updated from the new update package; `/health` returned `{"status":"ok"}`, package cleanliness scan passed, and source/package/installed hashes match for the selector, ANSYS runner, one-click pipeline, square-section summary/workflow, and server runtime exe.

## 2026-06-08 deployment package fixed-password closeout

Current latest deployment-package state:

1. User requested the deployment package to keep the login password as `cnpe123` and to be directly sendable to the unit.
2. `scripts/package_duxyb_intranet_release.ps1` now defaults `InitialPassword` to `cnpe123` and writes `config/initial_password.txt` into the deployment package.
3. `scripts/CableTrayAIInstaller.cs` reads `config/initial_password.txt` from the package. On install it writes local `config/auth.local.json` for users `duxyb`, `jianghl`, and `wanggangb` using that password.
4. If target `config/auth.local.json` already exists, the installer backs it up as `auth.local.json.bak_<timestamp>` and rewrites local auth to the deployment package password, so old random-password installs are corrected.
5. Fallback installers `scripts/install_desktop_app.py` and `scripts/install_desktop_app.ps1` follow the same packaged-password and auth-backup policy.
6. Installer cleanup now removes stale target-root `CableTrayAI_Installer.exe`, so old installer exes do not remain in the installed folder after an upgrade/install.
7. Final deployment package: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, size `78960185` bytes, SHA256 `CE94EACF784DD7C8F1F7151DDFA22E099D7165DF1A231C0B26FF5FDAA0CD5EEE`; package gate passed and zip contains no top-level `jobs/uploads/outputs/logs`, no local configs, no runtime auth sessions, no `__pycache__`, and no `*.pyc`.
8. Local installer smoke passed using the rebuilt package against `D:/CableTrayAI`: `install_manifest.json` records `initial_password=cnpe123`, `CableTrayAI_LOGIN_INFO.txt` shows `cnpe123`, old auth was backed up, root `D:/CableTrayAI/CableTrayAI_Installer.exe` is absent, and installed hashes match the final package for checked runtime/source files.
9. Web smoke passed after install: `/health` returned `{"status":"ok"}`, `duxyb/cnpe123` login returned pass, and a wrong password returned 401.
9. Verification passed: native installer/package auth policy tests, fallback installer py_compile, PowerShell parser checks, deployment package gate, and full unit tests.

## 2026-06-08 mail update package closeout

Current latest update-package state:

1. Future unit upgrades should use the mail-safe update package, not manual full-folder copy.
2. Output package is `C:/Users/duxy/Desktop/duxyb-update/更新包.zip`; the extracted folder is `C:/Users/duxy/Desktop/duxyb-update/更新包`.
3. `scripts/package_internal_update.ps1` builds the clean deployment payload, wraps it as `payload/CableTrayAI_payload.zip`, writes `manifest/update_manifest.json` and `manifest/payload_file_manifest.json`, and names the final outer zip `更新包.zip`.
4. `scripts/install_update_package.ps1` verifies the payload zip SHA256 and every expanded payload file before applying anything to the target install. It rejects payloads containing top-level `jobs/uploads/outputs/logs`, `config/*.local.*`, `runtime/auth_sessions.json`, `__pycache__`, or `*.pyc`.
5. Unit operator flow: unzip `更新包.zip`, double-click `Install_Update.cmd`, or run `powershell -NoProfile -ExecutionPolicy Bypass -File .\install_update.ps1`; use `-TargetRoot <install dir>` only if auto-detection does not find the installed folder.
6. Update policy preserves target-machine `jobs/uploads/outputs/logs`, `config/auth.local.json`, `config/ansys.local.toml`, and local sessions/configs. It backs up replaced files under `<install>/_update_backups/<timestamp>`.
7. Health policy: after applying, the updater starts `runtime/CableTrayAI_Server/CableTrayAI_Server.exe` and checks `http://127.0.0.1:8000/health`; if health fails it attempts a backup overlay rollback and restart.
8. Verification passed: full unit tests `103 passed`, package gate pass with runtime XML/no-expat spectrum smoke, update package `-VerifyOnly` pass, top-level forbidden-path scan pass, no `__pycache__`/`.pyc` in final zips, local `D:/CableTrayAI` update pass with `/health {"status":"ok"}`.
9. Final update package details: outer zip `C:/Users/duxy/Desktop/duxyb-update/更新包.zip`, size `78513666` bytes, SHA256 prefix `173D981DA479526508`; payload SHA256 `265dde3d6bb0d82192bdab1720f0e8959946b564743f804e6d9432cd9e4bd5d0`, payload file count `1774`.
10. Local installed final apply record: `D:/CableTrayAI/docs/last_mail_update_apply.json`, backup `D:/CableTrayAI/_update_backups/20260608_135840`, health `pass`.

## 2026-06-08 unit deployment login installer fix

Current latest deployment-login state:

1. Unit deployment reported that login `duxyb / cnpe123` failed after using `CableTrayAI_Installer.exe`.
2. Root cause found: the native WinForms installer copied the package but did not create local `config/auth.local.json` on first install, while `core/security/auth.py` intentionally has no committed default credentials.
3. `scripts/CableTrayAIInstaller.cs` now creates local `config/auth.local.json` during first install, preserving an existing local auth config if present.
4. Default first-install users are `duxyb`, `jianghl`, and `wanggangb`. The password is generated locally unless `CABLETRAYAI_INITIAL_PASSWORD` is set before running the installer.
5. The installer writes `auth_local_created`, `login_users`, `login_info_path`, and first-install `initial_password` to `install_manifest.json`; it also shows the initial password and creates `CableTrayAI_LOGIN_INFO.txt` in the target install folder when a new auth file is created.
6. The login info file records the local URL, users, first-install password, auth config path, and local ANSYS config path. Existing local auth configs are preserved on reinstall; if no login info file exists, reinstall writes a no-password-recovery notice instead of inventing a password.
7. Packaging hardening: `scripts/package_duxyb_intranet_release.ps1` now avoids LibreOffice's bundled Python when running `deployment_package_gate.py`, preferring `CABLETRAYAI_PACKAGE_PYTHON`, `.venv`, `D:/miniconda3/python.exe`, or a non-LibreOffice `python`.
8. Layer-count validation for leadership: per-side `12+12` is now parameterized and real-ANSYS verified. Root cause of the old >9 layer failure was source-family APDL keypoint-number collision such as `511`; `core/apdl/intake_standard_family_renderer.py` now expands `KPOFF/KPFSTEP/KPBKBASE` only when layer count exceeds 9, and the post/connection export follows the same numbering.
9. Real ANSYS18.2 validation job: `jobs/verify_12x12_high_layer_static_20260608_124204/S2_12x12_160x8_static_overload`. Main solve status `success`, connection-node export `success`, figure export `success` with 14 required figures, modal frequency rows parsed from `Mode.oup`.
10. Engineering conclusion for the 12+12 stress demo: it can be modeled and calculated, but the synthetic 12+12 high-load/160x8 case is not publishable because deterministic evaluation ratios exceed 1.0. Top ratios include bolt combined `527.778`, bolt combined upset `156.392`, and support tension+bending `4.312`.
11. Static-method modal appendix fix: `core/results/lis_parser.py` now parses ANSYS18.2 participation-factor modal frequency tables and keeps positive low-frequency rows when all rows are below 1 Hz, so static jobs can still output modal figures plus frequency table without a main MT gate.
12. Native installer safety fix: it no longer cleans a different registered install directory unless `CABLETRAYAI_CLEAN_PREVIOUS_REGISTERED_INSTALL=1`, and it preserves target-machine `jobs/uploads/outputs/logs` unless `CABLETRAYAI_RESET_RUNTIME_DATA=1`.
13. Final deployment package rebuilt at `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` (about `75.48 MB`). Package gate passed; package and zip contain no root `jobs/uploads/outputs/logs`, no `runtime/auth_sessions.json`, and no local `config/ansys.local.toml` or `config/auth.local.json`.
14. Local installed deployment `D:/CableTrayAI` was restored from the final package. Service is running from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`, PID `9256`; `/health` returns `{"status":"ok"}`, root page returns 200 with `no-store, no-cache`.
15. Installed/package/source hashes match for high-layer APDL, connection export, postprocessor alignment, modal parser, result validity gate, installer scripts, packaging script, and handoff docs. Installed `duxyb/cnpe123` login succeeds and wrong password is rejected.

## 2026-06-07 report-generation injection closeout

Current latest report-generation state:

1. `core/report/template_injector.py` now handles the <=120 mm square-tube cantilever-root weld branch correctly: the report no longer leaves the root-load table as `待确认` when `HF-FORCE.LIS` is not required; it removes that not-applicable table from the generated copy and fills `表6-2 托臂根部焊缝评定结果（应力比）` from `evaluation_summary.json`.
2. The equivalent weld table is normalized to six columns: `工况 / 应力类型 / 计算值(MPa) / 等效应力(MPa) / 许用值(MPa) / 应力比`; equivalent stress is calculated from the recorded TMAX value divided by coefficient `0.526`.
3. Generated reports mark only touched section titles, table titles and figure captions red. Body text and table values are not colored.
4. Appendix cleanup removes only empty page-break-only paragraphs inside real appendices and skips TOC paragraphs, preventing blank appendix pages without touching the source template file.
5. Verified sample report generated from installed real job `D:/CableTrayAI/jobs/18185NI-LXSJ4212`: `C:/Users/duxy/Desktop/report_review_18185NI-LXSJ4212_20260607_180115.docx`. Its `template_report_audit.json` status is `pass`; the equivalent weld table has 8 data rows and no warnings.
6. Verification passed: `python -m pytest tests/unit/test_template_report_injector.py -q`, `python -m pytest tests/integration/test_report_template_upgrade.py tests/unit/test_template_report_injector.py -q`, `python -m pytest tests/unit -q`, and `py_compile` for the touched report module/test.
7. Deployment completed: refreshed `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` (`79122877` bytes), package gate passed, applied to `D:/CableTrayAI` with backup `D:/CableTrayAI/_update_backups/20260607_180517`, service restarted as PID `21176`, `/health` ok, root no-cache headers ok, and installed/package/source hashes match for `core/report/template_injector.py`.

更新时间：2026-06-07 16:06

## 2026-06-07 ANSYS 模型与命令流核查面板生命周期修复

本节为当前最新状态。

1. 已修复网页端“ANSYS 模型与命令流核查”只在最终完成后加载、返回计算平台后丢失的问题。
2. `apps/web/index.html` 现在在新的 `/runs/start` 成功后才清空上一轮命令流核查；如果启动失败或已有任务占用，不会误删上一轮可审查命令流。
3. 运行中一旦后端暴露 `active_job_id`，前端会在 `render_commands`、`select_square_section`、`running_ansys`、重算、发布和终态阶段节流刷新 `/jobs/{job_id}/engineering-review`，所以截面选型完成前后能实时显示当前 job 的 `generated_model.mac`、`generated_solve.mac`、`generated_post.mac`。
4. 多行/多截面顺序运行时，如果 `active_job_id` 从上一 job 切到下一 job，前端会立即清空旧模型和旧命令文本，等下一 job 命令流生成后再显示，避免人工审查看串任务。
5. `restoreIntakeSession()` 不再把 `activeJobId` 强制置空；返回计算平台且不开始新计算时，会保留上一 job 的命令流核查面板，并通过 `engineering-review` 接口校验 job 是否仍存在。
6. 新增 `reviewGeneration/reviewJobId/reviewLoadJobId` 前端并发保护；旧 job 的延迟返回不会覆盖当前 job 面板。
7. 顺手补齐旧的前端缺口：`refreshEngineeringReview()` 已定义为 `loadEngineeringReview({ force: true })`，模板报告相关按钮不会再因该函数未定义报错。
8. 验证通过：Node 解析 `apps/web/index.html` 内联脚本通过；`python -m pytest tests/unit -q` 为 `89 passed`；`core/apps/templates` 硬编码扫描无命中。
9. 部署完成：`C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` 已重建，package gate 通过；已应用到 `D:/CableTrayAI`，`/health` ok，首页 no-cache 头 ok。精确最新备份路径以 `D:/CableTrayAI/docs/last_internal_update_apply.json` 为准。
10. 安装版 `D:/CableTrayAI/apps/web/index.html` 与源码 hash 一致；部署包没有顶层 `jobs/uploads/outputs/logs`，`runtime/auth_sessions.json` 未打包。

## 2026-06-07 4212 基础载荷 0 值核查与解析加固

本节为当前最新状态。

1. 最新网页完成 job：`D:/CableTrayAI/jobs/18185NI-LXSJ4212`，状态 `evaluated`，`result_validation.status=pass`。
2. 页面 6.3 表中的 DW `FY=0`、`MZ=0` 与 `foundation_loads.json` 和原始 `JCZH.LIS` 一致，不是网页展示或 JSON 解析把非零值写成 0。
3. 原始 `JCZH.LIS` DW 行为：`FX=104.1`、`FY=0.0`、`FZ=4211.7`、`MX=0.0`、`MY=1128.7`、`MZ=0.0`。其中 `FY/MZ` 是 ANSYS 导出的显式 `0.0`，`foundation_loads.json` 保留了 `raw_value: "0.0"`。
4. 这不是“只剩 FZ 的错提取”异常；DW 仍有非零 `FX` 和 `MY`，现有 `foundation_load_values` 门禁通过。
5. 已加固 `core/results/lis_parser.py`：`JCZH.LIS` 基础载荷行的 `FX/FY/FZ/MX/MY/MZ` 六列都必须真实存在，缺列或空值直接 `LisParseError`，不再用 `or 0` 静默补零。
6. 已新增 `tests/unit/test_lis_parser_foundation.py`，锁定“显式 0 可保留、缺列不能补 0”的规则。
7. 验证通过：目标测试通过、`python -m pytest tests/unit -q` 为 `89 passed`、`py_compile` 通过、`core/apps/templates` 硬编码扫描无命中。
8. 部署完成：`C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` 已重建并应用到 `D:/CableTrayAI`，package gate 通过（含 runtime XML 支持与 no-expat 谱 smoke），`/health` ok。精确最新备份路径以 `D:/CableTrayAI/docs/last_internal_update_apply.json` 为准。
9. 安装目录代码已复核：对 `D:/CableTrayAI/jobs/18185NI-LXSJ4212/JCZH.LIS` 的显式 `0.0` 保留原始值；对缺失 `JCZH` 分量的测试文件会抛 `LisParseError`，不再补 0。

## 2026-06-07 4213 网页端截面选型失败 hotfix

本节为当前最新状态。

1. `18185NI-LXSJ4213` 网页端报错 `Square section auto-selection failed; formal calculation is blocked until a section with ratio <= 1.0 is found.` 已定位为候选试算门禁误判，不是所有允许截面都不满足。
2. 已安装失败记录显示：`100-100-6 = 2.3374003257388036` 失败，`120-120-10 = 1.128459493680719` 失败，`140-140-8 = 0.9342488209446427`，应当作为第一个满足截面被选中。
3. 根因是静力法候选试算阶段没有运行正式报告图表导出，因此缺少报告附录用 `Mode.oup`/频率表；选型器错误地把 `required_file_Mode.oup` 和 `modal_frequency_table` 当成候选截面阻断项。
4. 源码修复：`core/optimizer/square_section_selector.py` 只在 `analysis_method=static` 的候选试算阶段忽略 `required_file_Mode.oup` 与 `modal_frequency_table`。反应谱候选不放宽；正式静力法报告仍要求 MOTAI 图和频率表。
5. 已用现有 4213 `140-140-8` 试算目录复核：修复后 `candidate_publishable_ratio.status=pass`，控制比 `0.9342488209446427`，诊断无阻断域。
6. 验证通过：`python -m pytest tests/unit/test_square_section_selector.py tests/unit/test_result_validity_square_section.py tests/unit/test_static_method_no_modal_policy.py -q` 通过；`python -m pytest tests/unit -q` 为 `87 passed`；`py_compile` 通过。
7. 部署完成：`C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` 已重建，package gate 通过（含 runtime XML 支持与 no-expat 谱 smoke），已应用到 `D:/CableTrayAI`，`/health` ok。精确最新备份路径以 `D:/CableTrayAI/docs/last_internal_update_apply.json` 为准。
8. 安装目录代码已复核 4213 历史试算：`140-140-8` 返回 `status=pass`，控制比 `0.9342488209446427`，无阻断诊断域。旧 job 记录仍会保留旧失败信息，需从网页重跑该行刷新结果。

## 当前总目标

发布前必须完成并验证这一版：

1. 提资内容必须驱动建模，不能用旧缓存或历史样例替代。
2. 托盘截面必须来自提资载荷/宽度，例如 500 mm 托盘应在模型中保留 `500-75-2mm`，不能误认为 `50-42`。
3. `50-42` 是托臂/异形钢相关截面，不是托盘截面；模型中允许同时出现 `50-42` 和 `500-75-2mm`，但两者用途必须明确。
4. 方钢候选截面必须来自提资 Excel 的“计算说明”；未列出的截面不得试算。
5. 方钢选型应使用完整评定后的控制应力比，满足 `<= 1.0`；经济区间为 `0.60 <= ratio <= 0.9999`，正常最多两次候选试算；若允许截面内无法满足，明确报“提资允许截面不足”或可审查的非截面阻断原因。
6. 旧 `jobs/uploads/outputs/logs` 和旧浏览器恢复状态不得污染新提资计算。
7. 用真实 ANSYS 路径做受控验证，不允许静默切换 mock。
8. 最终更新网页端和部署包：`C:\Users\duxy\Desktop\duxyb\CableTrayAI` 与 `C:\Users\duxy\Desktop\duxyb\CableTrayAI.zip`。

## 已验证结论

1. 对桌面提资 `1818 S2支架需求汇总20240711 - 副本.xlsx` 中 4210-4214 的调试渲染，模型中已同时出现：
   - 方钢截面，例如 `100-100-8`
   - 托臂截面 `50-42`
   - 槽钢/异形钢相关截面 `CAOGANG42DAN`
   - 托盘截面 `500-75-2mm`
2. `core/ansys/preflight.py` 已加入 `tray_sections_match_input` 检查，用来防止提资要求的托盘截面没有进入 APDL。
3. `core/optimizer/square_section_selector.py` 已加入托盘截面保护，替换方钢和托臂截面时不得误删托盘截面。
4. 已通过一次目标测试集：`25 passed`。
5. 已通过核心硬编码扫描：`rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates` 无命中。
6. 前端恢复逻辑已修复：只有提资和反应谱两个已上传文件都真实存在时才恢复旧会话；否则清除旧 `uploads`/job/session 状态，避免未选文件就报 `Job not found` 或 `uploads\...\No such file`。
7. 已用真实 ANSYS、禁用旧结果复用验证 `18185NI-LXSJ4212`：
   - 提资：`C:\Users\duxy\Desktop\1818 S2支架需求汇总20240711 - 副本.xlsx`
   - 反应谱：`C:\Users\duxy\Desktop\楼层谱1818 ANSYS格式 标高线性.xlsm`
   - 输出：`E:\CODEX\tray_platform\ANSYS Output\codex_release_validation_20260605_022255\18185NI-LXSJ4212`
   - 方钢候选：`100-100-6`、`100-100-8` 大于 1 失败，`120-120-6` 控制比 0.9828 通过并被选中。
   - `result_validation.json` 15 项全部通过，包含 MT 截断、基础载荷、连接螺栓、TMAX、22 张图片、图 5.1/5.2 区分和试算/第六章比值一致。
8. 最新代码已通过 `pytest -q`：47 passed；硬编码扫描无命中。

## 当前未完成

无。当前发布阻断项已完成，后续如继续改代码，需要重新执行同等验证。

## 2026-06-05 早间修复：输出缓冲失败

用户在已安装平台中看到 `18185NI-LXSJ4210: Unable to allocate output buffer`。排查确认原因不是提资或谱文件，而是旧安装版在 ANSYS 后处理导出图片/连接节点时使用 `subprocess capture_output=True`，当 ANSYS 输出较大时会在内存中申请输出缓冲并失败。

已完成：

1. `core/ansys/figure_export.py` 改为把 ANSYS stdout/stderr 流式写入 `figure_export_stdout.log` / `figure_export_stderr.log`。
2. `core/ansys/connection_export.py` 改为把 ANSYS stdout/stderr 流式写入 `connection_node_export_stdout.log` / `connection_node_export_stderr.log`。
3. 新增 `tests/unit/test_ansys_post_exports_stream_output.py`，防止这两个长输出后处理入口重新出现 `capture_output=True`。
4. `pytest -q` 已通过：48 passed。
5. 硬编码扫描 `rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates` 无命中。
6. 部署包已重新生成：
   - `C:\Users\duxy\Desktop\duxyb\CableTrayAI`
   - `C:\Users\duxy\Desktop\duxyb\CableTrayAI.zip`
7. 本机安装目录 `D:\CableTrayAI` 已用最新包刷新，保留已有 jobs/uploads/outputs/logs，替换源码和 runtime。
8. 新服务已启动：
   - `D:\CableTrayAI\runtime\CableTrayAI_Server\CableTrayAI_Server.exe`
   - PID 11684
   - 启动时间 2026/6/5 08:09:39
9. 本机接口检查：
   - `http://127.0.0.1:8000/` 返回 200
   - `http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`

注意：旧 job `D:\CableTrayAI\jobs\18185NI-LXSJ4210\job_state.json` 中仍保留昨晚旧版本失败记录，这是历史记录，不代表新代码仍在使用输出缓冲。需要刷新页面后重新计算该 job。

## 最终打包校验

1. 部署包已重新生成：
   - `C:\Users\duxy\Desktop\duxyb\CableTrayAI`
   - `C:\Users\duxy\Desktop\duxyb\CableTrayAI.zip`
2. 包内 `apps/web/index.html` 已确认包含恢复文件存在性校验：
   - 必须同时存在提资文件和反应谱文件。
   - 两个文件都通过 `/files/exists` 后才恢复旧会话。
   - 缺少任一文件时会清除旧 `uploads`、旧 job 和旧 session 状态，要求重新选择文件。
3. 包内未带入根目录级历史运行目录：
   - 未打入 `jobs/`
   - 未打入 `uploads/`
   - 未打入 `outputs/`
   - 未打入 `logs/`
   - `core/jobs` 是源码模块目录，不是历史计算结果。
4. PyInstaller 构建中间目录和 `.codex_tmp` 已清理。

## 压缩后恢复步骤

如果 Codex 上下文被压缩，先读取本文件，再继续执行 `docs/ACTIVE_FIX_QUEUE.md` 中的队列，不要重新猜测目标。

## 2026-06-06 4210 MT/选型智能化与审查命令流 closeout

本节覆盖旧的 4210 / 100x8 结论。当前可发布结论以本节为准。

1. 本地部署版已完成 4210 全流程真实 ANSYS18.2 验证。验证 job 为 `D:/CableTrayAI/jobs/verify_4210_optimized_20260606_173411/18185NI-LXSJ4210`，发布输出为 `E:/CODEX/tray_platform/ANSYS Output/verify_4210_optimized_20260606_173411/18185NI-LXSJ4210`。
2. MT 不再只按固定保守阶数。`core/apdl/modal_policy.py` 新增成功 job 的模态阶数学习缓存；4210 已由成功 MT=80 记录学习出推荐 MT=70。正式验证中 `generated_solve.mac` 使用 `MT=70`，`modal_results.json` 记录第 66 阶首次超过 50 Hz，第 70 阶频率 `51.14707600861 Hz`，`modal_cutoff_status=pass`。
3. 方钢截面选型改为“提资允许列表内、经济顺序、失败后可智能跳过、首次真实 ANSYS 完整评定满足即停止”。4210 本次验证候选结果为：`100-100-6=1.1845095292843475 fail`，`100-100-8=1.0698821329670751 fail`，`120-120-6=1.2389187235994654 fail`，`120-120-10=1.089945134953613 fail`，`140-140-8=0.9052401909300667 pass selected`。
4. 验证中没有继续运行 `160-160-8`，因为 `140-140-8` 已是第一个完整评定满足的候选截面；`square_section_selection.json` 记录 `stop_after_first_feasible=true`。
5. 发布审查命令流已扩展。`command_streams` 现在除 `generated_model.mac`、`generated_solve.mac`、`generated_post.mac` 外，还发布 `ansys_spectrum.mac`、`ansys_spectrum_sl1.mac`、`ansys_spectrum_sl2.mac`、`ansys_spectrum_workbook_format.mac`、`ansys_zpa_parameters.mac`，便于人工审查反应谱和残余质量/静力修正尾值。
6. 已刷新当前 4210 输出目录 `E:/CODEX/tray_platform/ANSYS Output/18185NI-LXSJ4210/command_streams`，其中 8 个命令流文件均已存在。`generated_solve.mac` 通过 `/INPUT` 引入 SL-1、SL-2 谱宏和 `ansys_zpa_parameters.mac`。
7. 部署包已重建并应用：`C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`，大小约 `75.43 MB`；安装备份为 `D:/CableTrayAI/_update_backups/20260606_173008`。服务已从 `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe` 重启，PID `33516`，`http://127.0.0.1:8000/health` 返回 `{"status":"ok"}`。
8. 验证通过：`python -m pytest tests/unit -q -p no:cacheprovider` 为 `71 passed`；目标测试集 `23 passed`；py_compile 通过；硬编码扫描在 `core/apps/templates` 无项目号、厂房/标高等核心运行时写死命中；部署包 gate 通过 no-expat 反应谱 smoke。
9. 代码树清理：已移除源目录 PyInstaller build/dist/spec 临时目录；`.pytest_cache` 与 `.pytest_tmp` 因 Windows ACL 拒绝删除，仍是本地测试缓存，不进入部署包，也不是计算状态。

当前未完成：无阻断项。后续若继续修改解析、计算、评定或打包逻辑，必须重新执行同等级真实 ANSYS 和部署验证。

## 2026-06-06 截面选型长期学习优化 closeout

本节是当前最新状态，覆盖上一节中“截面学习只记录 4210 初始样本”的限制说明。

1. 截面选型长期学习已升级为 `square-section-cache-v6-learned-allowed-start`。缓存文件为 `data/calibration/square_section_selection_cache.json`，所有成功的真实 ANSYS 方钢选型 job 都会写入，不限 4210。
2. 新提资命中相似历史样本时，只允许在当前提资“计算说明”允许截面列表内移动起算截面；不会新增未列截面，不会直接复用历史结果，不会跳过当前 job 的真实 ANSYS 和确定性评定。
3. 旧策略问题已修复：相似特征不再使用 `arm_section_family`，因为该字段由当前方钢截面派生，会让选型前的 100 分支错误偏向旧 100 样本。
4. 缓存命中 tie-break 已修复：相似度相同时优先当前 cache version，再优先更新的成功样本，避免旧缓存压过新验证样本。
5. 长期缓存已压缩清理，只保留选型学习需要的字段：候选截面、控制比、方钢比、门禁状态、控制项、run 状态、相似特征、来源 job 和时间；不再保存 trial 目录替换审计和复制文件列表。
6. 安装版已验证会命中最新 4210 `140-140-8` v6 样本，并从 `120-120-6` 起算，跳过 `100-100-6` 和 `100-100-8`，候选顺序为 `120-120-6`、`120-120-10`、`140-140-8`、`160-160-8`。
7. 真实 ANSYS18.2 验证：
   - `jobs/verify_4210_section_learning_20260606_190645/18185NI-LXSJ4210`：pass，最终 `140-140-8`，比值 `0.9052401909300667`。
   - `jobs/verify_4210_section_learning_applied_20260606_192140/18185NI-LXSJ4210`：pass，最终 `140-140-8`，比值 `0.9052401909300667`。
8. 第二次验证前的直接命中检查确认 v6 样本会从 `120-120-6` 起算；第二次真实 run 在修复 `arm_section_family` 前仍被旧 100 样本影响，修复后直接命中检查已确认安装版和源码均命中新 v6 140 样本。
9. 部署包已重建并应用：`C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`，大小约 `75.43 MB`；安装备份为 `D:/CableTrayAI/_update_backups/20260606_193731`。服务已从 `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe` 重启，PID `38056`，`/health` 返回 `{"status":"ok"}`。
10. 验证通过：目标截面测试 `20 passed`，全量 unit 测试通过，py_compile 通过，硬编码扫描在 `core/apps/templates` 无核心运行时命中，package gate 通过，安装目录关键文件 hash 与源码一致。

当前未完成：无阻断项。下一次相似提资会继续写入截面学习缓存；学习只优化起算/少跑候选，不替代真实 ANSYS 和第六章确定性评定。

## 2026-06-05 stale run restore fix

User saw the old `18185NI-LXSJ4210: Unable to allocate output buffer` message immediately after opening the platform. This was not a fresh ANSYS run. It was stale persisted run state from `docs/web_runs`, `jobs`, and browser localStorage being restored as the current calculation.

Completed fix:

1. `apps/api/app/main.py` records `SERVICE_STARTED_AT`.
2. Persisted runs older than the current service session are marked `stale`.
3. `/runs/latest` now returns only current-session runs. If there is no current run, it returns `not_started`.
4. `/ai/run-monitor` ignores stale runs and old job directories unless they belong to an active current-session job.
5. `apps/web/index.html` clears `activeRunId`, `latestRunId`, and related localStorage when it sees `stale` or `not_started`.

Verification:

1. `pytest -q` passed: 50 tests.
2. Targeted run-progress and ANSYS post-export tests passed.
3. Hardcode scan over `core apps templates` had no `1818`, `7.5m`, or standalone `NB` hits.
4. Deployment package rebuilt at `C:/Users/duxy/Desktop/duxyb/CableTrayAI` and `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`.
5. Local installed service smoke passed after login: `/runs/latest` returned `not_started`, not the old `4210` failure.

## 2026-06-05 工作区清理和复核

已按“代码树干净、不让历史生成物污染解析/计算/评定”的要求清理项目根目录生成物：

1. 已删除根目录历史 `jobs/`、`logs/` 内容，并重建为空目录。
2. 已删除 PyInstaller 中间产物与本地运行时：`_pyinstaller_desktop_build/`、`_pyinstaller_desktop_dist/`、`_pyinstaller_desktop_spec/`、`runtime/`。
3. 已删除根目录旧部署产物：`CableTrayAI.exe`、`CableTrayAI_Uninstall.exe`、`install_manifest.json`、`release_manifest.json`、`INTRANET_DEPLOY_README.txt`。
4. 已删除 `docs/web_runs/`、`docs/production_runs/` 及本次一次性真实 ANSYS 验证日志文件。
5. 未修改或删除 `source_materials/`、`core/`、`apps/`、`templates/`、`tests/`、`data/` 和交接文档。

清理后验证：

1. `python -m pytest -q -p no:cacheprovider` 通过：`50 passed`。
2. `rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates` 无命中。
3. `.pytest_cache/` 与 `.pytest_tmp/` 是 0 MB 空目录，但当前 Windows ACL 拒绝读取/删除；验证时已关闭 pytest cache provider，它们不应被视作计算状态或历史 job。

## 2026-06-05 4210 / 100x8 ????

?????? ANSYS ?? 4210???????????????????

1. ?????`100-100-8` ?????????????? ANSYS ? `SQUAREBEAMSTRESS.LIS` ?????????????????????????`6.655874 / 246.8205 + 288.4764 / 362.0034 = 0.8238551033866901`???????? Q355?
2. ??????????????????? `ratio < 1` ???????????? 1 ?????????? `140-140-8`???? `0.9050741886218011`?
3. ??????????????? `140` job ???????? `100/120` ???? `square_section_selected=140` ? `analysis_scope.json` ???????????????? `input.json`?`generated_post.mac`?????????????????? `analysis_scope.json`?
4. ????? no-reuse ?? ANSYS ?????`jobs/real_ansys_4210_scopefix_20260605_122100/18185NI-LXSJ4210`??????`E:/CODEX/tray_platform/ANSYS Output/codex_real_ansys_4210_scopefix_20260605_122100/18185NI-LXSJ4210`?`result_validation.json` ? 14/14 pass?
5. ????????`100-100-6=1.0860649507711804 fail`?`100-100-8=0.8238551033866901 numeric pass but not selected`?`120-120-6=1.1176208624928199 fail`?`120-120-10=1.0897604486587695 fail`?`140-140-8=0.9050741886218011 selected pass`?`160-160-8=0.5530764105162179 pass but not selected`?
6. ???????????????? 140 ?????? Q355 ?? ANSYS ?????? `100-100-8` ??????????????????????????? 100/120/140 ?????Excel ???? LIS ????????????????????????
7. ???????????????????????????????????? `100-100-8` ?? pass ????????
8. ??????? `real_ansys_4210_20260605_110744`?`real_ansys_4210_syncfix_20260605_114610` ??? `docs/production_runs` ? ANSYS ??????????????? 100/8 ?????ANSYS `.lNN` ???????????
9. ???`python -m pytest -q -p no:cacheprovider` ?? 56 tests????? `py_compile` ???`apps/web/index.html` ?? JS ?? `node --check`?`????` ??????`1818|7.5m|NB` ?????????

## 2026-06-05 4210 / 100x8 ASCII recovery note

1. Direct answer: 100-100-8 is reported as a numeric candidate pass because real ANSYS SQUAREBEAMSTRESS.LIS plus deterministic evaluation gives square_support accident tension+bending ratio 0.8238551033866901. Formula path: 6.655874 / 246.8205 + 288.4764 / 362.0034. Material policy is non-steel-platform Q355.
2. 100-100-8 is not the final accepted section. The final formal selection still chooses 140-140-8 because its ratio 0.9050741886218011 is closer to 1.0 while remaining below 1.0.
3. A real bug was fixed: copied final jobs could keep stale square_section_selected=140 and stale analysis_scope.json while trialing 100/120. Replacement now syncs input.json and generated_post.mac, clears stale selected metadata when it conflicts with the current trial section, rewrites analysis_scope.json, and trial copy ignores stale derived scope/selection files.
4. Formal no-reuse real ANSYS rerun after the fix passed at jobs/real_ansys_4210_scopefix_20260605_122100/18185NI-LXSJ4210. Published output is E:/CODEX/tray_platform/ANSYS Output/codex_real_ansys_4210_scopefix_20260605_122100/18185NI-LXSJ4210. result_validation.json is 14/14 pass.
5. Candidate ratios after the fix: 100-100-6=1.0860649507711804 fail; 100-100-8=0.8238551033866901 numeric pass, not selected; 120-120-6=1.1176208624928199 fail; 120-120-10=1.0897604486587695 fail; 140-140-8=0.9050741886218011 selected pass; 160-160-8=0.5530764105162179 pass, not selected.
6. Manual baseline conflict is still open. The coworker/manual statement says only 140x140x8 satisfies 4210, but current Q355 real-ANSYS deterministic calculation says 100-100-8 is a numeric pass. Do not claim the manual baseline is matched until the coworker 100/120/140 sheet, Excel cells, or LIS comparison is available.
7. Web/API wording now separates candidate numeric pass/fail from final acceptance so 100-100-8 is displayed as numeric pass but not selected, not as the publishable section.
8. Cleanup: superseded 4210 runs real_ansys_4210_20260605_110744 and real_ansys_4210_syncfix_20260605_114610 plus their docs/production_runs and ANSYS outputs were deleted. Latest scopefix run and the 100x8 diagnostic evidence were retained. ANSYS .lNN load-step caches are now removed by cleanup_heavy_solver_artifacts.
9. Verification: python -m pytest -q -p no:cacheprovider passed 56 tests; py_compile passed for touched modules; apps/web/index.html inline JS passed node --check; forbidden terminology scan for the old square-support phrase had no hits; hardcode scan for 1818, 7.5m, and standalone NB over core/apps/templates had no hits.


## 2026-06-05 deployment / command stream final note

This section records the state after the user asked for the 100x8 command streams to be sent to Desktop and asked whether the web deployment still used old code/cache.

1. Exported the 4210 100-100-8 command stream and evidence package to:
   - `C:/Users/duxy/Desktop/4210_100x8_command_stream_for_review_20260605_134215`
   - `C:/Users/duxy/Desktop/4210_100x8_command_stream_for_review_20260605_134215.zip`
2. The package includes `run_all.mac`, `generated_model.mac`, `generated_solve.mac`, `generated_post.mac`, `01_build_model.PIP`, `02_solve.mac`, `03_extract.mac`, spectrum macros, input/scope JSON, SECT support files, ANSYS LIS/OUP files, evaluation JSON, `ansys_run_audit.json`, and `README_100x8_review.txt`.
3. Rebuilt the deployment package:
   - `C:/Users/duxy/Desktop/duxyb/CableTrayAI`
   - `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`
4. Applied that package to `D:/CableTrayAI` and restarted the local service from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`.
5. Verified the installed source files match the workspace for the selection logic, analysis scope logic, ANSYS runner, frontend, and packaging script.
6. Verified `http://127.0.0.1:8000/health` returns `{"status":"ok"}` and the root page returns `no-store/no-cache` headers. An already-open browser tab can still hold old in-memory JavaScript until refreshed, but new loads come from the updated server package.
7. The Desktop deployment package excludes root-level `jobs/`, `uploads/`, `outputs/`, `logs/`, `runtime/auth_sessions.json`, and local config files such as `config/access_control.local.json` / `config/ansys.local.toml`.
8. The previous `ANSYS real run did not finish successfully: failed - ANSYS output contains blocking messages (command_stream_error); post-processing was blocked.` issue is fixed for optional MAPDL selection warnings. WARNING-context undefined entity / ignored ESEL messages are retained as warnings and no longer block post-processing. ERROR/FATAL command-stream contexts still block.
9. Added `tests/unit/test_ansys_command_stream_warning_gate.py` to lock this behavior.
10. Final verification after this update: `python -m pytest -q -p no:cacheprovider` passed, hardcode scan over `core apps templates` had no `1818`, `7.5m`, or standalone `NB` hits, and the old square-support Chinese phrase scan had no hits.

## 2026-06-05 spectrum elevation and row6 final status

Current release state after the latest real ANSYS reruns:

1. Spectrum elevation selection no longer snaps a requested elevation down to a lower floor. Exact matches are used directly; otherwise the code linearly interpolates between the nearest lower and nearest higher spectrum elevations. If the requested elevation is above the highest available floor, calculation fails instead of extrapolating.
2. For 4210 NR +8.5, the spectrum audit records `requested_elevation=8.5`, `selected_elevation=8.5`, `mode=linear_interpolation`, lower `8.45`, upper `12.95`. It does not use 8.45 directly.
3. For the last physical intake row, the old failure was caused by single-side source-family command streams not defining `senum1`; ANSYS then warned `Unknown parameter name= SENUM1` and post-processing was blocked. `core/apdl/intake_standard_family_renderer.py` now writes `senum1=0` for single-side rows.
4. Real no-reuse ANSYS rerun for that last row passed at `jobs/real_ansys_row6_senumfix_20260605_151201/1818_S2_20240711_S2_row_6`; published output is under `E:/CODEX/tray_platform/ANSYS Output/codex_real_ansys_row6_senumfix_20260605_151201`.
5. Last-row candidate ratios: `100-100-6=1.475624234262047 fail`, `100-100-8=1.4919176724914107 fail`, `120-120-6=1.5468087394032437 fail`, `120-120-10=1.5467520208216183 fail`, `140-140-8=0.888341903997755 pass`, `160-160-8=0.9131955968601544 selected pass`.
6. Current 4210 formal result remains `140-140-8` selected with ratio `0.9050741886218011`. The 4210 `100-100-8` diagnostic still validates as Q355 numeric pass with ratio `0.8238551033866901`; this is the remaining manual-baseline conflict, not stale 140-model contamination.
7. Latest Desktop review package for coworker checking is `C:/Users/duxy/Desktop/4210_100x8_spectrumfix_review_20260605_145910.zip`.
8. Deployment package was rebuilt at `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` and applied to `D:/CableTrayAI`. Installed hashes for touched files match source. Service health is ok at `http://127.0.0.1:8000/health`, and root HTML returns no-store/no-cache headers.
9. Verification passed: targeted pytest `21 passed`, full pytest `66 passed`, py_compile on touched modules, Node parse for `apps/web/index.html`, hardcode scan over `core apps templates`, package inspection, installed hash checks, and service smoke.
10. Source cleanup retained only the three current evidence job roots and removed the superseded failed row6 job plus generated PyInstaller/runtime artifacts. `.pytest_cache` and `.pytest_tmp` remain as local ACL-denied cache directories; they are not in the deployment package and are not calculation state.

## 2026-06-05 floorpolicy spectrum closeout

This section supersedes the earlier 15:40 interpolation notes.

1. Spectrum elevation selection no longer interpolates between floors. The active rule is: select the lowest common workbook spectrum elevation satisfying `selected_elevation >= intake_elevation - 0.1 m`.
2. For 4210 NR +8.5, the selected spectrum elevation is `8.45`, mode `lower_floor_within_0p1m_tolerance`, with minimum allowed elevation `8.4`. The generated SL-1/SL-2 spectrum macros contain no `elevation_interp` source.
3. For an NS ring intake elevation of `8.0` with only `7.5` and `13.5` available, `7.5` is below the 0.1 m tolerance and the selector must choose `13.5`.
4. Real no-reuse ANSYS for 4210 passed at `jobs/real_ansys_4210_floorpolicy_20260605_194143/18185NI-LXSJ4210`; published output is `E:/CODEX/tray_platform/ANSYS Output/codex_real_ansys_4210_floorpolicy_20260605_194143/18185NI-LXSJ4210`.
5. 4210 candidate ratios after the floorpolicy fix: `100-100-6=1.08448973904665 fail`, `100-100-8=0.8226542680722521 numeric pass but not selected`, `120-120-6=1.1154633008050938 fail`, `120-120-10=1.0873576336575843 fail`, `140-140-8=0.9030941184530311 selected pass`, `160-160-8=0.5519631912112796 pass but not selected`.
6. The latest 100-100-8 diagnostic real ANSYS run passed at `jobs/diagnostic_4210_100x8_floorpolicy_20260605_200418/18185NI-LXSJ4210_100-100-8`. Its max deterministic ratio is `0.8226542680722521`, material `q355`, and `result_validation.json` is publishable.
7. The coworker review package now to use is `C:/Users/duxy/Desktop/4210_100x8_floorpolicy_review_simplified_20260605_2008.zip`; older `spectrumfix`/command-stream packages were removed to avoid reviewing stale spectrum evidence.
8. Deployment package `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` was rebuilt and applied to `D:/CableTrayAI`; the exact backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`. Active service runs from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`, `/health` returns ok, and root HTML has no-store/no-cache headers.
9. `core/spectra/interpolation.py` has been deleted. `scripts/apply_internal_update.ps1` now removes known stale installed files after applying an update, so old deployments cannot keep the removed interpolation module.
10. Source cleanup retained only the latest floorpolicy 4210 formal job, latest floorpolicy 100x8 diagnostic job, and the row6 senumfix job. Runtime/PyInstaller directories and `__pycache__` were removed after packaging.
11. Final verification passed: full pytest with `-p no:cacheprovider`, py_compile for touched spectrum modules, hardcode scan for `1818|7.5m|NB`, runtime interpolation scan over `core apps templates scripts`, package inspection, installed hash comparison, and service smoke.

Current open item: coworker/manual baseline still says only `140x140x8` satisfies 4210, but current Q355 real ANSYS deterministic floorpolicy calculation gives `100-100-8` numeric pass and final selection `140-140-8`. Do not change material allowables, RCC-M formulas, or selection policy without coworker Excel cells, hand calculation, or LIS comparison evidence.

## 2026-06-05 VBA spectrum format closeout

This section supersedes the earlier floorpolicy package notes for spectrum command review.

1. The spectrum mismatch root cause was the old generated command path: it resampled/compressed curves with legacy source-command frequency guides instead of reproducing the workbook's `ANSYS Format` output.
2. The workbook VBA logic has now been learned and replicated for code generation. `Module1` supplies level lookup, spectrum extraction, interpolation helpers, and X/Y envelope logic. `Module2` supplies `Simplify`, `PrintPepsSysp`, and `StrAnsys`, which are the workbook path used to write the red-box `ANSYS Format` block.
3. Runtime spectrum selection still follows the user's elevation rule: choose the lowest common workbook elevation satisfying `selected_elevation >= intake_elevation - 0.1 m`. For 4210 NR +8.5 this selects `8.45`, mode `lower_floor_within_0p1m_tolerance`.
4. Spectrum generation now writes `ansys_spectrum_workbook_format.mac` in every job. This file is for direct review against the Excel `ANSYS Format` area and contains the SL-1/SL-2, XY/Z workbook-format blocks.
5. The actual solve inputs remain `ansys_spectrum_sl1.mac` and `ansys_spectrum_sl2.mac`; their FREQ/SV data now come from the same workbook-VBA path as `ansys_spectrum_workbook_format.mac`.
6. Real no-reuse ANSYS for 4210 after the VBA spectrum fix passed at `jobs/real_ansys_4210_vbaspectrum_20260605_205920/18185NI-LXSJ4210`; selected section is `140-140-8`, controlling ratio `0.9031454745084346`, validation publishable.
7. Latest 4210 candidate ratios after the VBA spectrum fix: `100-100-6=1.1023869580598782 fail`, `100-100-8=0.8229657592534583 numeric pass but not selected`, `120-120-6=1.1169614521115918 fail`, `120-120-10=1.0874272040907167 fail`, `140-140-8=0.9031454745084346 selected pass`, `160-160-8=0.5520012955679422 pass but not selected`.
8. Latest 4210 `100-100-8` diagnostic real ANSYS run passed at `jobs/diagnostic_4210_100x8_vbaspectrum_20260605_212110/18185NI-LXSJ4210_100-100-8`; it uses SECREAD `100-100-8`, `50-42`, `CAOGANG42DAN`, and `500-75-2mm`; max deterministic ratio is `0.8229657592534583`, material `q355`, validation pass/publishable.
9. Latest clean Desktop spectrum/code review package is `C:/Users/duxy/Desktop/4210_100x8_vbaspectrum_code_clean_20260605_212801.zip`. It includes modeling, solve, post, actual SL-1/SL-2 spectrum solve macros, workbook-format review spectrum macro, spectrum JSON, evaluation JSON, and only the SECT files used by the 100x8 model.
10. Verification passed before deployment refresh: `python -m pytest -q -p no:cacheprovider` returned 68 passed; targeted spectrum/ANSYS/intake tests returned 18 passed; `py_compile` passed for existing spectrum modules; hardcode scan over `core apps templates` had no `1818`, `7.5m`, or standalone `NB`; old spectrum logic scan had no `LEGACY_MAX`, `ansys_100_point_compression`, `source_command_frequency_guide`, `elevation_interp`, or `linear_interpolation` hits.

Current open item remains the same: coworker/manual baseline says only `140x140x8` satisfies 4210, while current Q355 real ANSYS VBA-spectrum calculation gives `100-100-8` numeric pass and final selection `140-140-8`. The next reconciliation should compare the clean Desktop package's `ansys_spectrum_workbook_format.mac`, actual SL-1/SL-2 solve spectrum macros, LIS values, and coworker Excel cells before changing material policy, allowables, RCC-M formulas, or section-selection policy.

## 2026-06-05 VBA spectrum deployment refresh

## 2026-06-06 automatic workbook-envelope spectrum closeout

This section supersedes the earlier "active M required" note.

1. `core/spectra/workbook_envelope.py` now reproduces the floor-spectrum XLSM VBA path in Python:
   level lookup, log-frequency interpolation, linear elevation interpolation, X/Y envelope, `Simplify` precision controls, and ANSYS Format block sequencing.
2. `core/spectra/response_spectrum_writer.py` now generates response-spectrum solve macros from that Python replicator. When a matching active-sheet column M block exists, the formal solve tokens are compared against it at ANSYS three-decimal precision.
3. The XLSM `Workbook_Open` / `Workbook_BeforeClose` macros reset precision-control spacing cells to fine mode. If current-control replication differs from a matching saved M block, the saved M block is used as calibrated ANSYS Format output and the mismatch is recorded in `spectrum_audit.json`.
4. Real ANSYS18.2 validation for 4210 `100-100-8` completed at `jobs/real_4210_envelope_replicator_20260606/workspaces/18185NI-LXSJ4210_100-100-8_envelope_replicator_real_144103`.
5. Spectrum comparison passed with zero error against source M-column ANSYS Format:
   `formal_spectrum_source_mode=active_column_m_calibrated_precision_output`,
   `spectrum_comparison_status=pass`,
   `precision_control_override_status=used`.
6. ANSYS return code was 0. Key values:
   `MAXBEAMSTRESS FAULTED BEND = 377.470368 MPa`,
   `JCZH SL-2 MX/MY = 15655.6 / 13543.7 Nm`.
7. Deterministic evaluation correctly rejects 4210 `100-100-8`:
   `support_bending_accident = 377.470368 / 362.0034 = 1.0427260296450254`,
   `support_tension_bending_combined_accident = 1.0698836684959312`.
8. `result_validation.json` fails only because `evaluation_ratio_limit` is over 1.0. This is expected design failure, not software/ANSYS failure.
9. Verification passed: `python -m pytest -q` returned 70 passed. Heavy ANSYS solver caches were cleaned; LIS/OUT/ERR/JSON/MAC evidence was retained.

Current remaining task: refresh the desktop package and `D:/CableTrayAI` installed copy, then smoke-test the installed service.

Deployment completed after this note:

1. Desktop full package rebuilt at `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, size `79017928` bytes.
2. Incremental update applied to `D:/CableTrayAI` from `C:/Users/duxy/Desktop/duxyb-up/CableTrayAI_update_workbook_envelope_20260606_145004.zip`.
3. Installed backup path: `D:/CableTrayAI/_update_backups/20260606_145004`.
4. Installed service restarted from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`, PID `25316`, start time `2026-06-06 14:50:13`.
5. `http://127.0.0.1:8000/health` returned `{"status":"ok"}`.
6. Installed hashes match source for the spectrum writer, new workbook-envelope module, and handoff docs.
7. Package inspection passed: no root `jobs/uploads/outputs/logs`, no `runtime/auth_sessions.json`, no local config, no removed `core/spectra/interpolation.py`; `core/spectra/workbook_envelope.py` is present.

## 2026-06-06 expat deployment hotfix

The latest installed package failed during the 4210 web calculation with:

`No module named expat; use SimpleXMLTreeBuilder instead`

Root cause:

1. `core/spectra/workbook_envelope.py` introduced a direct `openpyxl.load_workbook` call for precision-control cells.
2. The portable/PyInstaller runtime can enter an environment where openpyxl XML parsing reports the expat failure.
3. Existing intake/spectrum preview readers already had a no-expat XLSX fallback, but the new workbook-envelope precision-control path did not use it.
4. The no-expat fallback reader also collapsed sparse empty rows, which breaks the workbook precision-control layout because those cells are placed in separated row bands.

Fix:

1. `read_simplify_controls()` now reads workbook rows through the shared `_read_workbook_rows()` fallback path instead of direct openpyxl.
2. `_read_xlsx_rows_without_expat()` now preserves Excel row numbers by inserting empty rows from the sheet XML row `r=` attribute.
3. Precision-control sheet matching now recognizes the real Unicode title `精度控制`, plus `precision/control` English fallbacks.
4. Added regression coverage that monkeypatches openpyxl to raise `No module named expat; use SimpleXMLTreeBuilder instead` and still requires spectrum macro generation to pass.
5. Added `scripts/deployment_package_gate.py`; package generation now fails before zip creation unless the package passes a simulated no-expat spectrum smoke.
6. `scripts/build_portable_runtime.ps1` now checks `pyexpat.pyd`, `_elementtree.pyd`, and `libexpat.dll` after building the portable runtime.

Verification:

1. `python -m pytest -q -p no:cacheprovider` passed.
2. Hardcode scan over `core apps templates` for `1818`, `7.5m`, and standalone `NB` had no hits.
3. Real uploaded installed spectrum workbook passed the no-expat smoke with `formal_spectrum_source_mode=active_column_m_calibrated_precision_output` and M-column comparison `pass`.
4. Full package rebuild with portable, desktop, and installer runtimes passed `deployment_package_gate.py`.
5. New package: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, size `79071848` bytes.
6. Installed update applied to `D:/CableTrayAI`; backup is `D:/CableTrayAI/_update_backups/20260606_153433`.
7. Installed service restarted from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`, PID `24108`, start time `2026-06-06 15:34:55`.
8. `http://127.0.0.1:8000/health` returned `{"status":"ok"}` and root HTML returned no-store/no-cache headers.

Additional real ANSYS smoke:

1. A fixed-section installed smoke ran 4210 with `140-140-8` through real ANSYS18.2.
2. Spectrum generation passed and ANSYS execution returned `success`.
3. The smoke did not publish because `result_validation.json` blocked on `modal_mt_cutoff` after the bounded MT retry. This is not the expat package failure; treat it as a separate modal gate follow-up if it appears in normal operator runs.

Resolved after the workbook-VBA spectrum fix:

1. Deployment package rebuilt at `C:/Users/duxy/Desktop/duxyb/CableTrayAI` and `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`; zip size `79000638` bytes.
2. Package inspection passed: no root `jobs/`, `uploads/`, `outputs/`, `logs/`, no `runtime/auth_sessions.json`, no local config files, and no `core/spectra/interpolation.py`.
3. Package applied to `D:/CableTrayAI`; backup path is `D:/CableTrayAI/_update_backups/20260605_213341`.
4. Installed service restarted from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`, PID `4204`.
5. `http://127.0.0.1:8000/health` returned `{"status":"ok"}` and root HTML returned `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`, `Pragma: no-cache`, `Expires: 0`.
6. Installed hashes match source for `core/spectra/response_spectrum_writer.py` and `scripts/apply_internal_update.ps1`; installed `core/spectra/interpolation.py` is absent. Installed `runtime/auth_sessions.json` and local config files are preserved local runtime state, not packaged files.
7. Cleanup removed `docs/_tmp_vba_extract`, `jobs/_tmp_spectrum_vba_check`, superseded floorpolicy 4210 jobs, old Desktop review packages, `D:/CableTrayAI/_internal_update`, source `runtime/`, PyInstaller build/dist/spec directories, and non-cache `__pycache__` artifacts.
8. Source `jobs/` now retains only `real_ansys_4210_vbaspectrum_20260605_205920`, `diagnostic_4210_100x8_vbaspectrum_20260605_212110`, and `real_ansys_row6_senumfix_20260605_151201`.

## 2026-06-06 Excel 8.5 spectrum + MMASS diagnostic

The coworker workbook `C:/Users/duxy/Desktop/楼层谱1818 ANSYS格式 标高线性-8.5.xlsm` was verified directly from the Excel `包络谱` active sheet `ANSYS Format` output area, not from the segmented source table. The active output block is `Envelop:(NR_1818,8.5)`.

Diagnostic job:

- `jobs/diagnostic_4210_100x8_excel85_mmass_20260606_011434/18185NI-LXSJ4210_100-100-8_excel85_mmass`

The generated solve spectrum macros use the Excel 8.5 ANSYS Format blocks and explicitly insert missing mass:

- SL-1 XY: peak `0.561g`, 100 Hz/ZPA `0.182g`, `MMASS,ON,0.182`
- SL-1 Z: peak `0.609g`, 100 Hz/ZPA `0.253g`, `MMASS,ON,0.253`
- SL-2 XY: peak `1.737g`, 100 Hz/ZPA `0.477g`, `MMASS,ON,0.477`
- SL-2 Z: peak `1.523g`, 100 Hz/ZPA `0.425g`, `MMASS,ON,0.425`

Real ANSYS succeeded with return code `0` and duration about `157s`. Extra figure export was skipped for speed, so `result_status` is blocked only by diagnostic figure requirements; LIS/OUP and deterministic evaluation were produced.

Result:

- `square_support.support_tension_bending_combined_accident = 0.8245120550433136`
- Accident bending `288.639968 MPa / 362.0034 MPa = 0.7973404890672298`
- Compared with the current 8.45 VBA-spectrum 100x8 result `0.8229657592534583`, the Excel 8.5 + MMASS result increases only by about `0.00155`.

Conclusion: Excel-interpolated 8.5 spectrum elevation and corresponding missing mass are not the root cause of the coworker/manual `100-100-8 > 1.0` discrepancy. Continue the next reconciliation on calculation-command-flow or external manual/LIS differences, not on spectrum elevation alone.

Also fixed the web result assembly tail failure class where `input.json` with UTF-8 BOM could fail parsing. `core/results/result_assembler.py` now reads `input.json` as `utf-8-sig`; regression test `tests/unit/test_result_assembler_input_encoding.py` passed.

## 2026-06-06 unit raw post diagnostic

## 2026-06-06 active M-column ANSYS Format root-cause fix

This section supersedes the earlier "manual baseline conflict blocked" note for 4210 `100-100-8`.

Root cause:

1. The coworker standard solve uses the Excel active-sheet column M `ANSYS Format` output at `Envelop:(NR_1818,8.5)`.
2. The previous platform solve macros still used reconstructed segmented curves / workbook-like simplification, not the exact active M-column block.
3. For SL-2 XY, the active M-column block jumps from `3.927` to `5.482` to `5.715`, while the old platform path kept intermediate valley points such as `4.094`, `4.268`, and `4.450`. ANSYS interpolation through the M-column block is therefore much higher around the controlling modes.
4. Controlled MT comparison proved MT is not the root cause: MT=60 and MT=80 produce essentially identical stresses under the same department command stream.

Implemented fix:

1. `core/spectra/response_spectrum_writer.py` now requires a complete Excel active-sheet column M `ANSYS Format` block matching the requested sheet/elevation.
2. `ansys_spectrum_sl1.mac` and `ansys_spectrum_sl2.mac` use those FREQ/SV lines verbatim for solve input.
3. `ansys_zpa_parameters.mac` takes the 100 Hz static-correction tails from the same active M-column block.
4. If no matching active M-column block exists, calculation is blocked and tells the operator to input the intake elevation in the spectrum workbook, click `包络谱`, save, and rerun. There is no segmented-spectrum solve fallback.

Real ANSYS verification:

1. Department baseline job: `jobs/diagnostic_4210_100x8_ansys182_mtcompare_20260606_132427/mt80_djs`.
2. Platform fixed job: `jobs/diagnostic_4210_100x8_activeM_platform_ansys182_20260606/18185NI-LXSJ4210_100-100-8_activeM_platform`.
3. ANSYS18.2 exit code was `0`; `.err` has no ERROR/FATAL, missing input, or ETABLE/database blockers.
4. Platform active-M `MAXBEAMSTRESS.LIS` FAULTED values match the department baseline: tension `6703062 Pa`, compression `-1509265.8 Pa`, bending `377470368 Pa`, shear `11984864.5 Pa`.
5. Under non-steel-platform Q355, `100-100-8` is now correctly not satisfied: bending ratio `377.470368 / 362.0034 = 1.042726`, tension+bending ratio `1.069884`.
6. `evaluation_summary.json` contains `pass_fail = 不满足` for the controlling square-support accident rows.
7. `baseline_comparison.json`, `baseline_comparison.md`, and `precision_acceptance_report.md` were written in the fixed platform job; 42/42 metrics pass against the department baseline.

Verification:

1. `python -m py_compile core/spectra/response_spectrum_writer.py tests/unit/test_spectrum_elevation_resolution.py` passed.
2. `python -m pytest tests/unit/test_spectrum_elevation_resolution.py -q -p no:cacheprovider` passed: 7 tests.
3. `python -m pytest tests/unit/test_spectrum_elevation_resolution.py tests/unit/test_square_section_selector.py tests/unit/test_square_section_summary.py tests/unit/test_result_validity_square_section.py -q -p no:cacheprovider` passed: 20 tests.
4. `python -m pytest tests/unit/test_material_policy.py tests/unit/test_template_report_injector.py -q -p no:cacheprovider` passed: 4 tests.
5. Hardcode scan showed new diagnostic constants only in tests, not in core runtime logic.

User clarification after this fix:

1. The spectrum workbook can generate the required M-column `ANSYS Format` for the corresponding elevation by entering the elevation and clicking `包络谱`.
2. Therefore the formal strategy is not "prefer M column, otherwise use another spectrum." The formal strategy is: response-spectrum solve macro generation requires the matching M-column `ANSYS Format`.
3. Code was tightened to this rule, and the old segmented-spectrum solve fallback/dead simplification code was removed from `response_spectrum_writer.py`.
4. Full verification after tightening passed: `python -m pytest -q -p no:cacheprovider` returned 70 passed.

Deployment status:

1. Full Desktop package refreshed: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, size `79008955` bytes.
2. Package inspection passed: no root `jobs/`, `uploads/`, `outputs/`, `logs/`, no `runtime/auth_sessions.json`, no local config, and no removed `core/spectra/interpolation.py`.
3. Incremental installed update applied: `C:/Users/duxy/Desktop/duxyb-up/CableTrayAI_update_activeM_20260606_135232.zip`.
4. Installed backup: `D:/CableTrayAI/_update_backups/20260606_135239`.
5. Installed `D:/CableTrayAI/core/spectra/response_spectrum_writer.py` hash matches the source tree and Desktop package.
6. `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
7. The active service process was not restarted because PID `10616` is running from a higher-privilege session and `taskkill /F` returned access denied. Installed files are updated, but the running process may still have old imported modules until restarted by an admin/original deployment session.

Current next step:

1. Restart `D:/CableTrayAI` service from an elevated/admin or original deployment session.
2. After restart, smoke-test `/health` and root no-cache headers.

This diagnostic follows the user's stop boundary: try the unit result-extraction command stream once; if it still does not reproduce the coworker over-limit result, stop the active root-cause chase until the coworker-used command stream is available.

Diagnostic job:

- `jobs/diagnostic_4210_100x8_excel85_unit_raw_post_20260606_012423/18185NI-LXSJ4210_100-100-8_excel85_unit_raw_post`

Configuration:

- Model/solve reused the Excel 8.5 + MMASS diagnostic setup.
- `generated_post.mac` was the unit raw `source_materials/model_commands/导出数据-S2.PIP`, decoded from GBK to UTF-8 only for APDL audit/preflight.
- `unit_raw_post_source.PIP` is retained as the raw copied source.
- No postprocessor alignment and no `SQUAREBEAMSTRESS` augmentation were applied.

Real ANSYS result:

- `ansys_run_audit.json` status `success`, duration `165.216125s`.
- Raw unit post generated `MAXBEAMSTRESS.LIS` and `TMAXBEAMSTRESS.LIS`, but no `SQUAREBEAMSTRESS.LIS`.
- `MAXBEAMSTRESS.LIS` controlling values match the existing Excel 8.5 diagnostic MAX output.

Evaluation from raw unit `MAXBEAMSTRESS.LIS`:

- Q355 accident bending `288.639968 / 362.0034 = 0.7973404890672298`.
- Q355 accident tension+bending `0.8245120550433136`, satisfies.
- Q235 accident bending `288.639968 / 257.466 = 1.1210799406523582`.
- Q235 accident tension+bending `1.1592838171512616`, not satisfied.

Conclusion: the unit raw result-extraction command stream itself does not reproduce the coworker/manual over-limit result under the current 4210 `non_steel_platform` Q355 policy. The same ANSYS stresses do exceed 1.0 if evaluated as Q235, so the remaining reconciliation should focus on the coworker's exact material/evaluation workbook path or the exact command streams they used. Stop further root-cause chasing until those files are available.

## 2026-06-06 static modal gate fix for 18185NI-LXSJ4213

Superseded correction after reviewing the user's 4120 static command files:

1. The first quick fix was too loose. Static-method reports also need modal output to cover 50 Hz. The real issue was MT generation/retry, not the result gate.
2. The standard 4120 static calculation keeps modal solve in the `01` model command stream: `MODOPT,LANB,887`, `MXPAND,887,,,0`, then the `02` static command stream runs `ANTYPE,0` / `ACEL`.
3. `core/validation/result_validity_gate.py` was restored so every required modal result, including static-method jobs, must contain a `modal_cutoff_status=pass` row above 50 Hz.
4. `core/apdl/intake_standard_family_renderer.py` now inserts a standard modal solve block with `EQSLV,SPAR`, `MXPAND,MT,,,1`, `LUMPM,0`, `PSTRES,0`, second `MODOPT`, and `/OUTPUT,'Mode','oup'`.
5. If the currently selected `01` source family lacks a modal block, the renderer searches same-name model command files in the standard command library and records their literal `MODOPT` count. For `18185NI-LXSJ4213`, this recovers audited source MT `887`.
6. `core/pipeline/one_click.py` now uses that audited source count as a high-MT retry when normal smart retries hit the old 240 cap and Mode.oup still does not cover 50 Hz.
7. Real ANSYS18.2 validation job `jobs/verify_4213_static_modal887_20260606_221633` succeeded with `MT=887`: ANSYS return code `0`, result validation `pass`, first mode above 50 Hz is mode `493` at `50.00458560826 Hz`, mode `497` is `50.25466922999 Hz`, and the last mode `887` is `270.0014312982 Hz`.
8. `data/calibration/modal_mode_count_cache.json` learned a compact static 4213 recommendation: future similar jobs can start at `MT=497`; if that is still insufficient, the audited source retry remains `887`.
9. Final deployment package `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` size is `79098955` bytes. It was applied to `D:/CableTrayAI`, backup `D:/CableTrayAI/_update_backups/20260606_223517`; active service PID `47364`, `/health` ok.

## 2026-06-07 static method no-main-MT correction

This section supersedes the 2026-06-06 static modal gate note immediately above.

1. Corrected policy: static-method jobs do not use response-spectrum modal extraction and do not have a main-solve MT or 50 Hz Mode.oup cutoff gate.
2. Static-method S2 reports still require appendix-A modal content: `MOTAI-1.PNG` through `MOTAI-4.PNG` and the modal frequency table.
3. Code now separates `modal_analysis` from report modal content:
   - Static main solve: `requires.modal_analysis=false`, so no `modal_mt_cutoff`.
   - Static report content: `requires.modal_figures=true` and `requires.modal_frequency_table=true`, so MOTAI figures and Mode.oup rows remain required.
4. Static `generated_solve.mac` preserves the audited static calculation stream and rewrites equivalent-static `ACEL` coefficients only. It no longer inserts `ANTYPE,2`, `MODOPT`, `MXPAND`, or `MT`.
5. Static figure export runs a fixed four-mode post-only modal graphics solve, writes `Mode.oup` for the frequency table, and exports MOTAI figures. This post-only modal solve is not the main solve MT and has no 50 Hz cutoff gate.
6. Removed the stale static `recommended_modal_mode_count=497` cache entry; static jobs are skipped by modal MT learning.
7. Real ANSYS18.2 validation job `jobs/verify_4213_static_no_mt_20260607_140551` passed: main solve duration about `20.04s`, figure export success, `figure_count=14`, `result_validation.status=pass`, `fail_count=0`, `modal_rows=4`, `modal_frequency_table=pass`, `required_file_Mode.oup=pass`, `required_figures=pass`, and no `modal_mt_cutoff` check.
8. Deployment completed after this correction: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` rebuilt with package gate pass, applied to `D:/CableTrayAI`, backup `D:/CableTrayAI/_update_backups/20260607_141510`; service restarted as PID `14620`, `/health` ok. Installed static-policy smoke returns `modal_analysis=false`, `modal_figures=true`, `modal_frequency_table=true`, and `modal_mode_count=null`.

## 2026-06-07 report render QA and appendix caption fix

1. LibreOffice system install via winget left `C:/Program Files/LibreOffice/program/bootstrap.ini` missing `URE_BOOTSTRAP`; the current user cannot patch Program Files. A user-writable extracted copy was created at `C:/Users/duxy/AppData/Local/LibreOfficePortableExtracted`, its `bootstrap.ini` was fixed, the user PATH registry now starts with `C:/Users/duxy/AppData/Local/LibreOfficePortableExtracted/program`, and explicit `soffice.com --headless --version` plus DOCX/PDF conversion work for QA. Existing Codex shells may need restart to see bare `soffice` from PATH.
2. Visual QA found a real appendix layout defect in the generated sample report: the final stress figure caption `图C-8` was isolated on the last page while the image stayed on the previous page.
3. `core/report/template_injector.py` now sets inserted image paragraphs to `keep_together=true` and `keep_with_next=true`, and sets caption paragraphs to `keep_together=true`, so figure and caption paginate as a unit.
4. New verified sample report: `C:/Users/duxy/Desktop/report_review_18185NI-LXSJ4212_20260607_190600.docx`.
5. The sample converted to PDF with portable LibreOffice: `C:/Users/duxy/Desktop/report_review_18185NI-LXSJ4212_lo_render_20260607_190600/report_review_18185NI-LXSJ4212_20260607_190600.pdf`.
6. Selected pages were rendered to PNG for inspection. Verified pages include equivalent weld section pages 20-22, appendix A start page 25, appendix B start page 29, and final page 44. Final page now contains both Figure C-8 and its caption; PDF blank-page scan found no suspects.
7. Report verification passed: `python -m pytest tests/integration/test_report_template_upgrade.py tests/unit/test_template_report_injector.py -q` returned 6 passed.
8. Deployment completed: refreshed `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` (`79126078` bytes before final doc sync), applied to `D:/CableTrayAI`, backup `D:/CableTrayAI/_update_backups/20260607_191437`, service restarted as PID `18604`, `/health` ok, root no-cache headers ok, installed/package/source hashes matched for `core/report/template_injector.py` and updated handoff docs.

## 2026-06-07 pre-deployment known-issue audit

1. Rechecked all known deployment failure classes before unit deployment: no-expat workbook parsing, runtime XML files, package contents, old-code/cache risk, active-M spectrum path, static-method MT policy, square-section candidate gate, JCZH zero extraction, ANSYS output buffer streaming, command-stream warning gate, BOM input parsing, frontend stale-run restore, report title coloring, appendix blank pages, and figure-caption pagination.
2. Found and fixed one report-only issue during this audit: static-method reports were still trying to build table 3-1 from the intake elevation `7.5m`, while the equivalent-static spectrum selection had chosen `13.09m`. `core/report/template_injector.py` now uses `metadata.static_acceleration_source.selected_elevation/elevations` for static report spectrum curves.
3. Regression test added: `test_static_report_spectrum_uses_selected_static_elevation`.
4. Verification passed after the fix: full `tests/unit` passed, report integration/unit tests passed, targeted known-failure tests passed, hardcode scan over `core apps templates` had no hits, package gate passed, and recent installed real jobs `18185NI-LXSJ4211` through `18185NI-LXSJ4214` all regenerated template reports with audit `pass`.
5. Final deployment completed after this audit: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` size `79128372` bytes, applied to `D:/CableTrayAI`, backup `D:/CableTrayAI/_update_backups/20260607_202131`, service PID `20688`, `/health` ok, root no-cache headers ok, checked runtime hashes match source/package/install.

## 2026-06-12 real ANSYS variant validation and square-section exhaustion fix

1. Created a job-local validation workbook at `jobs/validation_intake_variants_20260612_165827/intake_variants_single_double_layers_width.xlsx` from the installed intake workbook. Source uploads and `source_materials` were not modified.
2. Added three validation rows for real ANSYS stress testing: `18185NI-LXSJ9101` double-side 2+2 layers at 600 mm, `18185NI-LXSJ9102` single-side 5 layers at 600 mm, and `18185NI-LXSJ9103` double-side 3+3 layers at 600 mm.
3. Real ANSYS18.2 batch `jobs/real_validation_variants_20260612_1659` completed all three rows. `9103` passed with `160-160-8` and controlling deterministic ratio `0.8582242170469485`. `9102` completed ANSYS and result extraction but failed deterministic evaluation because weld equivalent ratio was `1.2479863056049951`, which is an engineering capacity failure. Initial `9101` exposed a selector defect: smart two-trial search could report allowed sections insufficient after testing `120-120-6`, `120-120-10`, and `160-160-8` without testing all remaining allowed sections.
4. Fixed `core/optimizer/square_section_selector.py`: smart two-trial search remains the efficiency path, but before declaring all intake-allowed square sections insufficient it now enters failure-exhaustion mode and runs every untested allowed section with fresh ANSYS/deterministic ratios. Economic downshift and smart jumps are disabled during this final exhaustion pass.
5. Added regression tests in `tests/unit/test_square_section_selector.py` requiring the final failure path to test skipped allowed sections and requiring an actual pass to be selected if a skipped section satisfies.
6. Verification passed: full `pytest` returned `154 passed`. A real ANSYS rerun for `9101` at `jobs/real_validation_variants_9101_rerun_20260612_1740` then evaluated `120-120-6`, `120-120-10`, `160-160-8`, `100-100-6`, `100-100-8`, and `140-140-8`; all remained over 1.0, so the final failure is now proven by exhaustive allowed-section evidence instead of a skipped-section assumption.
7. `data/calibration/modal_mode_count_cache.json` learned a successful response-spectrum signature for the 600 mm double-side 3+3 layer case from `9103`, with recommended `MT=90`.
8. Rebuilt deployment package at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and update package at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`. Package gate passed, including no-expat spectrum smoke and runtime XML support checks.
9. Applied the update package to `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260612_175308`. Active service runs from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`, `/health` returns ok, login `duxyb/cnpe123` returns pass, and installed `core/optimizer/square_section_selector.py` hash matches the source tree.

## 2026-06-12 conversational intake calculation workflow

1. Added `core/intake/chat_intake.py` to parse operator conversation into an auditable single-row intake payload. It recognizes report/project identifiers, factory/area, elevation, single/double-side tray layout, layer count, tray width, support spacing, square-support height, analysis method, damping, and allowed square-section candidates.
2. The chat parser is intentionally conservative. Missing project, factory, elevation, tray layout, spacing, support height, allowed square sections, or response-spectrum file blocks ANSYS start and returns prompts. It does not infer a historical spectrum file or silently expand the allowed square-section range.
3. Added `/ai/intake/preview` and `/ai/intake/start-run`. Preview validates structured fields and spectrum-file existence; start writes a job-local workbook under `jobs/chat_intakes/` and then calls the existing `/runs/start` one-click path, so progress, command-stream review, ANSYS execution, post-processing, result validation, and publishing remain the same production workflow.
4. Added `apps/web/ai_intake.html` as the operator page for non-mechanics departments. The existing AI tools page now links to it. The page supports text input, spectrum upload/path, output folder, optional explicit confirmation of the standard chat square-section candidate list, preview, real-run start, and run polling.
5. Online reference policy updated with official OpenAI Structured Outputs and Function Calling references. Adopted idea is only the engineering boundary: structure unstructured conversation and invoke explicit backend tools. No online formula, APDL command authority, material allowable, or report mapping was introduced.
6. Verification passed: `pytest` returned `158 passed`; `py_compile` passed for `core/intake/chat_intake.py` and `apps/api/app/main.py`; inline JS syntax checks passed for `apps/web/ai_intake.html` and `apps/web/ai_tools.html`; temporary source service HTTP checks confirmed `/ai-intake` loads, complete chat intake previews as pass, and missing/nonexistent spectrum files block with `spectrum_file`.
7. Browser plugin and bundled Playwright runtime were attempted for screenshot-level validation, but this local Codex environment failed to load browser assets / `playwright-core`. HTTP and JS syntax checks were used instead; production deployment still needs normal browser smoke after packaging.
8. Deployment completed after this feature: rebuilt `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; applied to `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`; `/health` ok; `duxyb/cnpe123` login pass; `/ai-intake` returns 200; installed hashes match source for parser, API, and page.

## 2026-06-12 conversational intake UX cleanup

1. The chat intake workflow no longer treats a report-like number pasted by another discipline as a formal mechanics report number. It is kept only as `raw_intake_row.detected_reference_number` for traceability; the calculation job uses an internal `CHAT-...` request id unless a backend caller explicitly sets `allow_formal_report_number`.
2. The `/ai-intake` structured table now hides internal tracking fields such as `report_number`, `calculation_batch`, `intake_order_id`, `provisional_intake_id`, `raw_intake_row`, and square-section source-ref/status fields. The visible table uses user-facing Chinese labels.
3. The confusing `采用单位默认候选方钢清单` checkbox was removed from the normal form. Candidate square sections are read first from the user text, e.g. `允许100x8、120x10、140x8`; only when no candidate section is provided does the page show `使用单位候选库补截面` as an explicit fallback action.
4. Verification passed: `pytest` returned `158 passed`; `py_compile` passed for the chat parser and API module; Node/VM script syntax checks passed for `apps/web/ai_intake.html` and `apps/web/ai_tools.html`; Unicode parse smoke confirms a pasted `18185NI-LXSJ9001` becomes an internal `CHAT-...` job id instead of a formal report number.
5. Deployment package and update package are refreshed in `C:/Users/duxy/Desktop/duxyb-cnpe`; local `D:/CableTrayAI` update uses `D:/CableTrayAI/docs/last_internal_update_apply.json` for the exact latest backup path.

## 2026-06-16 mixed tray-width per-layer renderer and NX/-8.8 validation

1. Superseded the old mixed-width shared-maximum geometry fallback for front/back mixed tray layers. The new renderer builds every tray layer with its own width, arm split, tray section, density, LS keypoint family, CSOLID bolt connectors, CPCYC coupling, and post-processing-compatible components.
2. Corrected the 600 mm tray split used by intake parsing from `0.45+0.22` to `0.47+0.20`, matching the user-confirmed engineering intent that the 600 mm L3 tail is `0.20m`.
3. The mixed renderer is selected only for front/back layer mixes where at least two tray widths are present. Homogeneous layouts and unsupported side labels continue through the existing standard-family renderer.
4. Added regression coverage that renders a single-side 2-layer `300+600` model and checks both tray sections, both physical bolt connector groups, the 600 mm `0.20m` tail, and the audit flag that shared-maximum geometry is not used.
5. Verification passed with `D:/miniconda3/python.exe -m py_compile` for changed modules and targeted unit tests `tests/unit/test_tray_load_parser.py` plus `tests/unit/test_intake_standard_family_tray_widths.py`, returning `28 passed`.
6. Real ANSYS18.2 validation ran for a job-local intake: NX building, `-8.8m`, single-side 2 layers `300+600`, support spacing `2.0m`, square-support height `2.2m`, response-spectrum method, Q355, using `C:/Users/duxy/Desktop/楼层谱1818 ANSYS格式 标高线性.xlsm`. The run passed in about `136.8s`.
7. The real validation selected `100-100-6` with controlling deterministic ratio `0.418410665203697`. Since this is the minimum allowed square tube in the test list, the ratio below the economy band is retained as the smallest feasible section rather than downshifting.
8. Full deliverables were copied to `C:/Users/duxy/Desktop/NX_-8.8m_single_300_600_results_20260616_171205`, including the full job directory, published output directory, intake workbook, progress log, and run summary.
9. Deployment package and update package were refreshed in `C:/Users/duxy/Desktop/duxyb-cnpe`; update package self-verification passed, including runtime XML/no-expat spectrum smoke.
10. The refreshed update was applied to `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`, `/health` returned ok, login `duxyb/cnpe123` returned pass, and installed/package/source hashes matched for the changed runtime files.
