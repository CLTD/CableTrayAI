# CableTrayAI 当前修复队列

## 2026-06-06 4210 MT/选型优化队列 closeout

本节为当前最新队列状态，覆盖旧的 4210 / 100x8 追查分支。

Resolved in source, package, local install, and real ANSYS18.2 evidence:

1. MT 阶数策略已智能化。成功 job 会写入 `data/calibration/modal_mode_count_cache.json`；4210 从成功 MT=80 学习出推荐 MT=70，正式验证中 MT=70 仍满足 50 Hz 截断门禁。
2. 4210 最新正式验证 job：`D:/CableTrayAI/jobs/verify_4210_optimized_20260606_173411/18185NI-LXSJ4210`。`modal_results.json` 记录 `mt_mode=70`，第 66 阶首次超过 50 Hz，第 70 阶频率 `51.14707600861 Hz`，`modal_cutoff_status=pass`。
3. 方钢自动选型已改为：只在提资允许截面内搜索，按经济顺序试算，允许基于失败真实比值做智能跳过，遇到第一个完整评定满足的真实 ANSYS 候选即停止，不再继续跑更大且不经济的候选。
4. 4210 最新候选结果：`100-100-6=1.1845095292843475 fail`，`100-100-8=1.0698821329670751 fail`，`120-120-6=1.2389187235994654 fail`，`120-120-10=1.089945134953613 fail`，`140-140-8=0.9052401909300667 pass selected`。`160-160-8` 未运行，因为 `140-140-8` 已是第一个满足截面。
5. 这次验证明确回答旧问题：在当前正确的 active-M/workbook-envelope 反应谱和 Q355 非钢平台评定下，4210 `100-100-8` 不满足，控制比 `1.0698821329670751 > 1.0`。
6. 审查命令流已补全。发布目录 `command_streams` 现在包括建模、计算、结果提取、SL-1/SL-2 实际求解反应谱、工作簿格式审查谱、ZPA/残余质量静力修正参数，共 8 个文件。
7. 当前输出目录 `E:/CODEX/tray_platform/ANSYS Output/18185NI-LXSJ4210/command_streams` 和最新验证输出目录 `E:/CODEX/tray_platform/ANSYS Output/verify_4210_optimized_20260606_173411/18185NI-LXSJ4210/command_streams` 均已刷新为 8 个审查命令流。
8. 部署包已重建并应用到 `D:/CableTrayAI`，备份 `D:/CableTrayAI/_update_backups/20260606_173008`；服务 PID `33516`，`/health` 返回 ok。安装目录核心文件 hash 与源码一致。
9. 验证通过：unit tests `71 passed`，目标测试 `23 passed`，py_compile 通过，部署包 gate 通过，硬编码扫描无核心运行时命中。

Open queue:

1. No blocking item remains for the current 4210 MT/section-selection/command-stream/deployment request.
2. If a future operator run uses a materially different intake/spectrum workbook, re-run the real ANSYS acceptance gate before release.

## 队列顺序

1. 检查 `core/intake/intake_excel_reader.py`：
   - 是否从提资 Excel 的“计算说明”提取允许方钢截面。
   - 是否能提取 `100*100*6、100*100*8、120*120*6、120*120*10、140*140*8、160*160*8` 这类列表。
   - 未出现的 `120*120*8` 不得进入候选。

2. 检查 `core/optimizer/square_section_workflow.py` 与 `core/optimizer/square_section_selector.py`：
   - 候选截面必须先按提资允许列表过滤。
   - 旧试算目录不得复用到新提资。
   - 选型完成后，候选控制比值必须与最终第六章评定来源一致。
   - 不允许用历史报告结果硬凑通过。

3. 检查 APDL 渲染：
   - 生成的 `generated_model.mac` 必须保留提资要求的托盘截面，例如 `500-75-2mm`。
   - `50-42` 只作为托臂/异形钢相关截面，不得替代托盘截面。

4. 检查前端恢复状态：
   - 打开网页时不得自动恢复已经不存在的 `uploads/intake` 或 `uploads/spectrum` 路径。
   - 不得在未选择文件前恢复旧 job，例如 `18185NI-LXSJ4210`。
   - 当前已修复：恢复会话前必须通过 `/files/exists` 验证提资和反应谱两个上传文件都存在，否则清除旧状态并要求重新选择。

5. 验证：
   - 运行方钢选型、托盘截面、结果门禁相关单元测试。
   - 运行硬编码扫描。
   - 用真实 ANSYS 路径做受控验证。
   - 重新打包部署包并做启动检查。
   - 当前已完成：`pytest -q` 47 passed，硬编码扫描无命中；真实 ANSYS no-reuse 验证 `18185NI-LXSJ4212` 通过，选中 `120-120-6`，`result_validation.json` 15/15 pass；部署包已重新生成并确认包含最新前端恢复文件校验，且不包含根目录级 `jobs/uploads/outputs/logs` 历史运行目录。

## 当前重点

用户最担心的问题是：

1. 4210 同事用 `140*140*8` 才过，但软件选 `100*100*6` 也过，怀疑建模托盘截面或载荷没按提资进入模型。
2. 新版本安装后可能仍在用旧缓存或旧策略。
3. 部署包必须干净，不带历史 job、上传文件、输出文件和旧日志。

## 2026-06-05 输出缓冲修复状态

已完成，不在当前阻断队列中：

1. `Unable to allocate output buffer` 已定位为 ANSYS 后处理长输出被 `capture_output=True` 缓冲导致。
2. `figure_export.py` 与 `connection_export.py` 已改为 stdout/stderr 流式写入 job 日志文件。
3. 已新增回归测试防止长输出后处理入口重新使用 `capture_output=True`。
4. 已重建部署包，并刷新本机 `D:\CableTrayAI` 安装目录和服务进程。

后续若再次看到同一句失败，需要先确认是否是旧 job 历史状态；新计算应查看对应 job 目录下 `figure_export_stderr.log`、`connection_node_export_stderr.log`、`ansys_run_audit.json` 和 `job_state.json`。

## 2026-06-05 stale run restore status

Resolved for the current release package.

1. The old `18185NI-LXSJ4210: Unable to allocate output buffer` message was caused by stale persisted run state, not by a fresh calculation after the output-buffer streaming fix.
2. Backend now isolates current-service runs from old persisted runs.
3. Frontend now clears stale `activeRunId` / `latestRunId` state when the server reports `stale` or `not_started`.
4. Local installed smoke after login confirmed `/runs/latest` returns `not_started` on a clean service start instead of restoring the old failure.

If this exact message appears again, first verify the installed package version and clear stale browser state only if the server package is older than this fix.

## 2026-06-05 workspace cleanup status

Resolved for the current source workspace.

1. Project-root historical generated artifacts were removed: `jobs/`, `logs/`, PyInstaller build/dist/spec directories, `runtime/`, root-level exe/uninstall/manifest deployment files, `docs/web_runs/`, `docs/production_runs/`, and one-off validation logs.
2. Empty `jobs/` and `logs/` directories were recreated so future jobs have stable output roots.
3. `source_materials/`, source code, templates, tests, data, and handoff documents were preserved.
4. Verification after cleanup passed: `python -m pytest -q -p no:cacheprovider` returned `50 passed`; hardcode scan over `core apps templates` had no `1818`, `7.5m`, or standalone `NB` hits.
5. `.pytest_cache/` and `.pytest_tmp/` remain as 0 MB ACL-denied empty directories; they are not calculation state and pytest was run with cache provider disabled.

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


## 2026-06-05 final queue status after deployment refresh

Resolved in the current source tree, package, and local installation:

1. 4210 100-100-8 command streams and evidence were exported for manual coworker review:
   - `C:/Users/duxy/Desktop/4210_100x8_command_stream_for_review_20260605_134215`
   - `C:/Users/duxy/Desktop/4210_100x8_command_stream_for_review_20260605_134215.zip`
2. The deployment package was rebuilt at `C:/Users/duxy/Desktop/duxyb/CableTrayAI` and `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`.
3. The rebuilt package was applied to `D:/CableTrayAI`; the service was restarted and now runs from `D:/CableTrayAI/runtime/CableTrayAI_Server/CableTrayAI_Server.exe`.
4. Installed source hashes match the workspace for `core/optimizer/square_section_selector.py`, `core/validation/analysis_scope.py`, `core/ansys/runner.py`, `apps/web/index.html`, and `scripts/package_duxyb_intranet_release.ps1`.
5. The package excludes root historical run data and local secrets/config: `jobs/`, `uploads/`, `outputs/`, `logs/`, `runtime/auth_sessions.json`, `config/access_control.local.json`, and `config/ansys.local.toml`.
6. `command_stream_error` blocking was fixed for optional ANSYS WARNING-context selection messages. True ERROR/FATAL command stream messages still block.
7. Verification passed: full pytest, hardcode scan, terminology scan, service health check, and no-cache root page check.

Still open:

1. Manual baseline conflict remains unresolved. Coworker/manual calculation says only 140x140x8 satisfies 4210, while current non-steel-platform Q355 real ANSYS deterministic evaluation gives 100-100-8 numeric pass but final selection chooses 140-140-8 because it is closer to ratio 1.0. Need coworker Excel cells, hand calculation, or LIS comparison for 100/120/140 before changing formulas or claiming baseline parity.

## 2026-06-05 spectrum elevation / row6 queue closeout

Resolved in source, package, and local install:

1. Spectrum elevation selection is exact-or-interpolated and never snaps a requested elevation down to a lower floor. 4210 NR +8.5 is interpolated from 8.45 and 12.95 with `selected_elevation=8.5`.
2. Single-side source-family APDL now writes `senum1=0`; this fixes the last-row real ANSYS `Unknown parameter name= SENUM1` command-stream blocker without weakening the generic ERROR/FATAL gate.
3. Last physical intake row real ANSYS rerun passed at `jobs/real_ansys_row6_senumfix_20260605_151201/1818_S2_20240711_S2_row_6`; final selected section is `160-160-8`, ratio `0.9131955968601544`.
4. Last-row `100-100-8` is correctly failing with ratio `1.4919176724914107`; the previous web failure was masking the real section inadequacy.
5. 4210 formal result remains `140-140-8` selected, ratio `0.9050741886218011`; 4210 diagnostic `100-100-8` remains Q355 numeric pass, ratio `0.8238551033866901`. This is still the manual-baseline conflict and must be reconciled against coworker Excel/LIS evidence before changing formulas.
6. Latest coworker package is `C:/Users/duxy/Desktop/4210_100x8_spectrumfix_review_20260605_145910.zip`.
7. Rebuilt deployment package `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` was applied to `D:/CableTrayAI`; service health and no-cache headers passed; package inspection and installed hash checks passed.
8. Verification passed: targeted pytest 21, full pytest 66, py_compile, frontend inline JS parse, hardcode scan, package inspection, installed hash checks, and service smoke.

Current queue:

1. No code blocker remains from the spectrum, last-row calculation, deployment, cache, or command-stream items covered here.
2. Keep the 4210 coworker/manual baseline discrepancy open as an evidence comparison task only.

## 2026-06-05 floorpolicy queue closeout

This section supersedes the earlier interpolation-based spectrum notes.

Resolved in source, package, local install, and latest real ANSYS evidence:

1. Spectrum floor selection now uses a no-interpolation policy: choose the lowest common workbook spectrum elevation where `selected_elevation >= intake_elevation - 0.1 m`.
2. 4210 NR +8.5 now selects `8.45`, mode `lower_floor_within_0p1m_tolerance`, minimum allowed elevation `8.4`. The generated `ansys_spectrum_sl1.mac` and `ansys_spectrum_sl2.mac` have no `elevation_interp` source.
3. The selector covers the user's NS ring example: if intake elevation is `8.0` and available floors are `7.5` and `13.5`, then `7.5` is too low and `13.5` is selected.
4. Latest real ANSYS 4210 formal run: `jobs/real_ansys_4210_floorpolicy_20260605_194143/18185NI-LXSJ4210`; selected `140-140-8`, controlling ratio `0.9030941184530311`, validation pass/publishable.
5. Latest 4210 candidate ratios: `100-100-6=1.08448973904665 fail`, `100-100-8=0.8226542680722521 numeric pass but not selected`, `120-120-6=1.1154633008050938 fail`, `120-120-10=1.0873576336575843 fail`, `140-140-8=0.9030941184530311 selected pass`, `160-160-8=0.5519631912112796 pass but not selected`.
6. Latest 4210 `100-100-8` diagnostic real ANSYS run: `jobs/diagnostic_4210_100x8_floorpolicy_20260605_200418/18185NI-LXSJ4210_100-100-8`; max ratio `0.8226542680722521`, material `q355`, validation pass/publishable.
7. Latest coworker package: `C:/Users/duxy/Desktop/4210_100x8_floorpolicy_review_simplified_20260605_2008.zip`. It supersedes older `spectrumfix` and command-stream packages, which were removed.
8. Deployment package rebuilt and applied: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` to `D:/CableTrayAI`; the exact backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`; `/health` ok, no-cache root headers.
9. `core/spectra/interpolation.py` is removed from source, package, and installed target. `scripts/apply_internal_update.ps1` now removes known stale installed files such as that module during future updates.
10. Verification passed: full pytest with cache disabled, py_compile for touched spectrum modules, hardcode scan, runtime interpolation scan, package inspection, installed hash comparison, and service smoke.

Current queue:

1. No code blocker remains from the spectrum floorpolicy, row6 calculation, deployment, cache, command-stream, or stale-file cleanup items.
2. Keep only the 4210 coworker/manual discrepancy open as an evidence comparison task. Current code says `100-100-8` is numeric pass under Q355 but not selected; final selected section is `140-140-8`.

## 2026-06-05 workbook-VBA spectrum queue addendum

Use this addendum first. It supersedes the earlier floorpolicy package note for spectrum-data comparison.

Resolved in source and latest real ANSYS evidence:

1. The remaining spectrum-data mismatch was caused by generating ANSYS spectrum commands from a legacy source-command frequency-guide/compression path instead of the workbook's own `ANSYS Format` VBA path.
2. The workbook VBA has been learned and mirrored for generation: `Module1` handles spectrum extraction/envelope inputs; `Module2` handles `Simplify`, `PrintPepsSysp`, and `StrAnsys`, which produce the workbook ANSYS-specific format.
3. Jobs now generate `ansys_spectrum_workbook_format.mac` for direct comparison with the Excel red-box `ANSYS Format` area. The actual MAPDL solve still uses `ansys_spectrum_sl1.mac` and `ansys_spectrum_sl2.mac`, whose FREQ/SV points now come from the same workbook-VBA path.
4. Latest formal real ANSYS 4210 run: `jobs/real_ansys_4210_vbaspectrum_20260605_205920/18185NI-LXSJ4210`; selected `140-140-8`, controlling ratio `0.9031454745084346`, validation publishable.
5. Latest 4210 `100-100-8` diagnostic run: `jobs/diagnostic_4210_100x8_vbaspectrum_20260605_212110/18185NI-LXSJ4210_100-100-8`; max deterministic ratio `0.8229657592534583`, material `q355`, validation publishable.
6. Latest clean Desktop package for coworker spectrum/code review: `C:/Users/duxy/Desktop/4210_100x8_vbaspectrum_code_clean_20260605_212801.zip`. It contains the workbook-format review spectrum macro, actual solve spectrum macros, model/solve/post commands, spectrum/evaluation/result JSON, and only the SECT files used by the 100x8 model.
7. Verification passed: full pytest 68 passed; targeted spectrum/ANSYS/intake tests 18 passed; py_compile passed for existing spectrum modules; hardcode scan and old spectrum logic scan had no hits.

Current queue:

1. Deployment refresh is complete: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` was rebuilt after the workbook-VBA spectrum fix, applied to `D:/CableTrayAI`, and the service was restarted. `/health` is ok and root HTML has no-cache headers.
2. Package inspection passed: no root jobs/uploads/outputs/logs, no local auth/config files, and no removed `core/spectra/interpolation.py`. Installed hashes match source for the spectrum writer and update script.
3. Keep only the manual-baseline discrepancy open as an evidence-comparison task: coworker says only 140x140x8 satisfies 4210, while current Q355 real ANSYS VBA-spectrum calculation gives 100-100-8 numeric pass but final selection 140-140-8. Compare coworker Excel cells or LIS values before changing formulas, allowables, materials, or selection policy.

## 2026-06-06 Excel 8.5 spectrum + MMASS queue addendum

Use this addendum before reopening spectrum-elevation debugging for 4210.

Resolved as a diagnostic verification:

1. The coworker workbook `C:/Users/duxy/Desktop/楼层谱1818 ANSYS格式 标高线性-8.5.xlsm` was read from the Excel `包络谱` active sheet `ANSYS Format` output area. The bottom segmented source table still has `8.45`, so using the production segmented parser alone would not test the coworker 8.5 output.
2. Diagnostic job `jobs/diagnostic_4210_100x8_excel85_mmass_20260606_011434/18185NI-LXSJ4210_100-100-8_excel85_mmass` uses the Excel output blocks `Envelop:(NR_1818,8.5)` and inserts `MMASS,ON,<ZPA>` per direction.
3. Parsed Excel 8.5 residual/missing-mass values: SL-1 XY `0.182`, SL-1 Z `0.253`, SL-2 XY `0.477`, SL-2 Z `0.425`.
4. Real ANSYS succeeded. Deterministic 100-100-8 controlling ratio was `0.8245120550433136`, still below 1.0. Current 8.45 VBA-spectrum ratio was `0.8229657592534583`; the increase is only about `0.00155`.
5. Conclusion: spectrum elevation 8.45 vs Excel-interpolated 8.5, even with corresponding MMASS/ZPA, is not the root cause of the coworker/manual `100-100-8 > 1.0` discrepancy.

Current queue:

1. Continue reconciliation on calculation command stream / manual command stream differences or coworker LIS values.
2. Do not change material policy, allowables, RCC-M formulas, or section-selection policy based only on the Excel 8.5 spectrum diagnostic.
3. Web tail parsing fix is applied: `core/results/result_assembler.py` reads `input.json` with `utf-8-sig`; targeted regression test passed.

## 2026-06-06 unit raw post queue stop

Resolved as a diagnostic verification, not as a baseline match:

1. Unit raw result-extraction command stream `source_materials/model_commands/导出数据-S2.PIP` was run with the Excel 8.5 + MMASS 4210 `100-100-8` model/solve setup in `jobs/diagnostic_4210_100x8_excel85_unit_raw_post_20260606_012423/18185NI-LXSJ4210_100-100-8_excel85_unit_raw_post`.
2. Real ANSYS succeeded. The raw unit post produced `MAXBEAMSTRESS.LIS` and `TMAXBEAMSTRESS.LIS`; it does not produce `SQUAREBEAMSTRESS.LIS`.
3. Under current 4210 `non_steel_platform` Q355 material policy, raw `MAXBEAMSTRESS.LIS` gives accident tension+bending ratio `0.8245120550433136`, still satisfying `< 1.0`.
4. The same stress values evaluated as Q235 give accident tension+bending ratio `1.1592838171512616`, which reproduces an over-limit result by material/evaluation policy, not by a different raw post output.
5. Job-local `baseline_comparison.json`, `baseline_comparison.md`, and `precision_acceptance_report.md` were written. They record that no coworker LIS/workbook cells were available, so this is not a manual-baseline precision acceptance.

Current queue:

1. Stop the active 4210 `100-100-8` root-cause chase per user instruction.
2. Resume only when the exact coworker-used solve/post command streams, LIS files, or evaluation workbook cells are provided.
3. Do not change material policy, allowables, RCC-M formulas, postprocessor mapping, or section-selection logic from this diagnostic alone.

## 2026-06-06 active M-column spectrum queue update

This supersedes the preceding stop note. The coworker command streams provided after that note were sufficient to find the root cause.

Resolved:

1. 4210 `100-100-8` over-limit is reproduced with real ANSYS18.2 using the Desktop generated model, department standard solve/post, and correct jobname `djs`.
2. MT=60 vs MT=80 was tested as a diagnostic only; it is not the root cause.
3. Root cause is spectrum command generation: platform solve macros were not using the exact Excel active-sheet column M `ANSYS Format` FREQ/SV block for `Envelop:(NR_1818,8.5)`.
4. `core/spectra/response_spectrum_writer.py` now requires matching active M-column ANSYS Format blocks and uses them verbatim for actual SL-1/SL-2 solve macros and static-correction ZPA tails.

## 2026-06-06 automatic workbook-envelope spectrum queue closeout

This supersedes the "active M required" implementation note.

Resolved in source and verified with real ANSYS18.2:

1. The XLSM VBA envelope workflow is now reproduced in `core/spectra/workbook_envelope.py`.
2. The formal spectrum writer auto-generates ANSYS Format blocks from the workbook source sheets and precision controls.
3. If an active column M block matches the requested sheet/elevation, the generated formal solve tokens are compared to it at ANSYS three-decimal precision.
4. Because the workbook resets precision-control spacing cells on open/close, a matching saved M block can represent previously generated simplified precision output. In that case the M block is used as calibrated solve output and the current-control mismatch is retained in the audit.
5. Real ANSYS18.2 validation for 4210 `100-100-8` passed as a software run at `jobs/real_4210_envelope_replicator_20260606/workspaces/18185NI-LXSJ4210_100-100-8_envelope_replicator_real_144103`.
6. Source M-column comparison status is `pass` with zero frequency/acceleration error; formal source mode is `active_column_m_calibrated_precision_output`.
7. ANSYS return code is 0. `MAXBEAMSTRESS.LIS` has FAULTED bending `377.470368 MPa`.
8. Deterministic result is correctly not satisfied for `100-100-8`: bending ratio `1.0427260296450254`, tension+bending accident ratio `1.0698836684959312`.
9. Full pytest passed: 70 tests.

Current queue:

1. Refresh `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`.
2. Apply the update to `D:/CableTrayAI`, preserving `jobs/uploads/outputs/logs` and local config.
3. Restart/smoke-test the installed service.

Deployment queue status: completed.

1. Desktop full package rebuilt: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, `79017928` bytes.
2. Installed update applied: `C:/Users/duxy/Desktop/duxyb-up/CableTrayAI_update_workbook_envelope_20260606_145004.zip`.
3. Backup: `D:/CableTrayAI/_update_backups/20260606_145004`.
4. Service restarted: PID `25316`, start time `2026-06-06 14:50:13`.
5. `/health` returned ok.
6. Hash/package checks passed for the updated spectrum files and handoff docs.

Open queue: no blocking item remains. Optional follow-up is a full 4210 section-selection rerun with the calibrated workbook-envelope spectrum.

## 2026-06-06 expat deployment hotfix queue closeout

Resolved in source, package, and local install:

1. Latest package failure `No module named expat; use SimpleXMLTreeBuilder instead` was caused by the new workbook-envelope precision-control reader using direct openpyxl instead of the existing no-expat workbook fallback.
2. `core/spectra/workbook_envelope.py` now reads precision-control cells through the shared workbook row reader and recognizes the real `精度控制` sheet title.
3. `core/intake/intake_excel_reader.py` no-expat XLSX parser now preserves sparse Excel row numbers, which is required for the precision-control bands.
4. Regression test added in `tests/unit/test_spectrum_elevation_resolution.py` to simulate the exact expat failure and require spectrum macro generation to pass.
5. `scripts/deployment_package_gate.py` was added and is now called by `scripts/package_duxyb_intranet_release.ps1`; package creation is blocked unless the copied package passes a no-expat spectrum smoke.
6. `scripts/build_portable_runtime.ps1` now verifies required XML support files after building the server runtime.
7. Rebuilt package `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` passed the package gate and was applied to `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260606_153433`.
8. Installed service restarted, `/health` is ok, root no-cache headers are ok, and installed no-expat smoke with the real uploaded spectrum workbook passed.

Follow-up only if seen again:

1. A fixed-section real ANSYS smoke reached ANSYS success but was blocked at `modal_mt_cutoff`; this is separate from the expat failure and should be investigated only if normal operator runs hit the same modal gate.
5. Real ANSYS18.2 platform validation with the fixed spectrum matches the department baseline. `100-100-8` now has Q355 accident bending ratio `1.042726` and tension+bending ratio `1.069884`; controlling rows are `不满足`.
6. Job-local manual baseline artifacts exist in `jobs/diagnostic_4210_100x8_activeM_platform_ansys182_20260606/18185NI-LXSJ4210_100-100-8_activeM_platform`.

Deployment/update state:

1. Full Desktop package refreshed at `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`.
2. Clean package inspection passed: no root historical run folders, no local config/auth state, and no old interpolation module.
3. Incremental update applied to `D:/CableTrayAI` from `C:/Users/duxy/Desktop/duxyb-up/CableTrayAI_update_activeM_20260606_135232.zip`.
4. Installed source hash for `core/spectra/response_spectrum_writer.py` matches the source tree.
5. The active service process could not be restarted from this session because PID `10616` denied termination. Installed files are updated; the running process should be restarted by an admin/original deployment session before relying on the web UI for a fresh calculation.

Latest policy correction:

1. Formal response-spectrum calculations do not use an M-column priority/fallback model.
2. The operator must generate the M-column `ANSYS Format` in the spectrum workbook for the corresponding intake elevation by clicking `包络谱`.
3. If that matching M-column block is missing, calculation blocks instead of using segmented table data as the solve spectrum.
4. Full pytest after this tightening passed: 70 tests.

Remaining queue:

1. Restart `D:/CableTrayAI` service and smoke-test `/health` plus root no-cache headers.
2. Optional fresh formal selection rerun for 4210 can be performed after deployment; the selection gate will reject 100-100-8 because the deterministic evaluation ratio is now greater than 1.
