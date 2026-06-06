# CableTrayAI 当前工作状态

更新时间：2026-06-05 10:58

## 当前总目标

发布前必须完成并验证这一版：

1. 提资内容必须驱动建模，不能用旧缓存或历史样例替代。
2. 托盘截面必须来自提资载荷/宽度，例如 500 mm 托盘应在模型中保留 `500-75-2mm`，不能误认为 `50-42`。
3. `50-42` 是托臂/异形钢相关截面，不是托盘截面；模型中允许同时出现 `50-42` 和 `500-75-2mm`，但两者用途必须明确。
4. 方钢候选截面必须来自提资 Excel 的“计算说明”；未列出的截面不得试算。
5. 方钢选型应使用完整评定后的控制应力比，满足 `< 1` 并尽量接近 1；若最小截面已远小于 1，则选最小可用截面；若全部不满足，明确报“提资允许截面不足”。
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
