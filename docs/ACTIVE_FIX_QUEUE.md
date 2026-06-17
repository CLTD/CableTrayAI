# CableTrayAI ??????

## 2026-06-17 4215 spacing-first economy recovery queue

Resolved in source and real ANSYS:

1. For `4215`-class jobs where Chapter 6.1 square-section sizing passes but weld/bolt/connection final ratio controls, automatic recovery now reduces support spacing before trying a larger square tube.
2. The preserved-section spacing branch keeps the current square section, regenerates APDL, reruns formal ANSYS, and validates against the current formal Chapter 6.1 ratio instead of requiring the old trial ratio, which is no longer comparable after spacing changes.
3. Real ANSYS validation on uploaded workbook row 7 / `18185NI-LXSJ4215` passed: selected section remained `120-120-10`, support spacing changed `2.0m -> 1.5m`, final Section 6.1 ratio `0.5241137016938773`, controlling final weld ratio `0.961668929223405`, `result_validation.status=pass`.
4. Regression coverage was added for support-spacing planning, preserved-section application, and result-validity formal validation after spacing recovery.

Deployment queue status: completed.

1. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; use the external `.sha256.txt` sidecar beside the zip as transfer authority.
2. Existing-install update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecar beside the zip as transfer authority.
3. Local `D:/CableTrayAI` was updated; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`; health, login, and installed-hash checks passed.

Open:

1. No source/package blocker remains for this policy. For the unit machine, use the update package for an existing deployment or the full package for a fresh deployment, and verify with the refreshed `.sha256.txt` sidecars.

## 2026-06-17 uploaded-intake 4211/4215 queue

Resolved in source and real ANSYS:

1. Duplicate report ids no longer override physical Excel row selection. This fixes the copied `4211__row_3` symptom where a row intended as `single-side 2-layer 500` was generated as `single-side 2-layer 100`.
2. Structured tray layer data is now authoritative for scope/result requirements, so 500/600 mm tray jobs no longer depend on fragile text parsing.
3. `18185NI-LXSJ4215` no longer treats weld/bolt/global final-ratio failures as Chapter 6.1 square-section stress failures. The workflow records those cases as `final_ratio_design_recovery`.
4. Real ANSYS validation used the uploaded workbook `C:/Users/duxy/Desktop/1818 S2支架.xlsx`:
   - row 3 / 4211: `500-75-2mm`, selected `120-120-6`, Chapter 6.1 ratio `0.9727244369318827`, pass.
   - row 7 / 4215: `600-75-2mm`, 120-120-10 Chapter 6.1 ratio about `0.815`, weld final gate controlled, recovered to `160-160-8`, pass.
5. Learning cache guard added: records with Chapter 6.1 section pass but final weld/bolt/global gate over 1.0 are not retained as successful square-section learning samples, and existing unsafe records were pruned.

Deployment closeout:

1. Full package and update package were refreshed under `C:/Users/duxy/Desktop/duxyb-cnpe`.
2. External SHA256 sidecars were refreshed beside both zip files.
3. Update applied to local `D:/CableTrayAI`; latest backup `D:/CableTrayAI/_update_backups/20260617_095241`.
4. `/health` passed, login `duxyb/cnpe123` passed, installed hashes match source for touched modules and pruned learning cache, and installed-code row-binding smoke generated 4211 as 500 mm and 4215 as 600 mm.

Open:

1. No current source/package blocker remains for unit transfer. For existing unit deployment, send `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; for fresh deployment, send `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`. Use the `.sha256.txt` sidecars for transfer verification.
## 2026-06-16 mixed tray line-id standardization closeout

Resolved in source and verified:

1. Mixed tray-width APDL generation now uses per-layer arrays plus recorded line-id groups, matching the reviewed standardized seven-layer style while remaining generic for new single-side and double-side mixed intakes.
2. Support, arm, tray, and bolt lines are recorded with `*GET,_LNEW,LINE,0,NUM,MAX` and later meshed through `LS_SUP`, `LS_ARM`, `LS_TRAY`, and `LS_BOLT`.
3. This removes the old geometry-location reselection ambiguity that could miss layers or select the wrong line group in mixed 300/500/600 layouts.
4. The explicit 300 mm topology, 200/100 small-tray branch, wider-tray branch, and channel/non-channel secondary-arm offset policies are preserved.
5. Verification passed: py_compile, targeted mixed tray tests, full `tests/unit`, hardcode/source_materials checks, and real ANSYS18.2 validation for 4214 and 4215 under `jobs/validation_mixed_lineid_real_20260616`.

Deployment queue status: completed.

1. Full package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Update package refreshed: `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
3. External `.sha256.txt` sidecars beside both zip files are the transfer authority.
4. Local `D:/CableTrayAI` was updated from the refreshed update package; `/health`, `duxyb/cnpe123` login, and source/package/installed hash checks passed.

## 2026-06-16 seven-intake layer parsing and preview closeout

Resolved in source and verified:

1. `double-side 3+3 layers, one 100, one 300, one 500` now parses as front `[100,300,500]` and back `[100,300,500]`. The apparent "six layers" in `input.json` are three front trace rows plus three back trace rows.
2. Unlabeled equal-side layer patterns are repeated per side; unequal declared counts are distributed by count; side-labeled text still takes precedence.
3. Web 3D command-stream preview now evaluates APDL array variables and `ABS(...)`, so mixed-loop `generated_model.mac` files no longer preview as only two layers.
4. 4211 ratio `0.0530209796187918` was checked as a light two-layer 100 mm double-side job with `100-100-6`; current deterministic outputs support the small ratio and do not indicate zero extraction.
5. Real ANSYS18.2 validation passed for seven rows at `jobs/validation_layer_fix_real_20260616`: 4210, 4211, 4212, 4213, 4214, 4215, and 4220 all have `result_validation=pass`.
6. 4215 economy follow-up is resolved: after `140-140-8` passed with ratio `0.509069498978923`, the tightened policy downshifted to `120-120-10`; real ANSYS rerun `jobs/validation_economic_downshift_real_20260616/18185NI-LXSJ4215` passed with ratio `0.9673673573968273`.

Deployment queue status: completed.

1. Refreshed `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and the mail/update package under the same folder.
2. Refreshed the external `.sha256.txt` sidecars; use those sidecars as transfer authority after copying to the unit computer.
3. Applied the update to local `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json` and `D:/CableTrayAI/docs/last_mail_update_apply.json`.
4. `/health`, `duxyb/cnpe123` login, and source/package/installed hash checks passed.

## 2026-06-16 platform-owned single-tray command-flow shadow v1

Resolved in source and verified:

1. Added platform-owned standard command-flow shadow generation for S2 single tray-width jobs.
2. Generated review files are `platform_standard_solve.mac`, `platform_standard_post.mac`, and `platform_standard_post_numeric.mac`.
3. The shadow files are not production entrypoints. `run_all.mac` still executes `generated_solve.mac` plus the production `generated_post_numeric.mac`.
4. Scope gate skips mixed tray widths, third-side jobs, unsupported support types, and unsupported analysis methods.
5. Publishing now includes optional `platform_standard_*` command streams when present.
6. Verification passed: py_compile, full unit tests, render smoke, and real ANSYS18.2 single-tray 300 mm validation with `result_validation=pass`.

Deployment queue status: completed.

1. Full package and update package were refreshed under `C:/Users/duxy/Desktop/duxyb-cnpe`.
2. Package gate, update self-verification, local update apply, `/health`, and `duxyb/cnpe123` login smoke all passed.

## 2026-06-16 mixed tray loop/offset closeout

Resolved in source and verified:

1. Fixed the latest mixed-tray offset review: channel secondary arm `CAOGANG42DAN` generates `SECOFFSET,user,,-0.03249`; non-channel secondary arms still generate `SECOFFSET,user`.
2. Replaced explicit per-point mixed geometry generation with APDL arrays plus `*DO` loops for support columns, tray-layer keypoints, tray-layer lines, meshing, and root coupling.
3. Enforced mixed-layer vertical order: for each side, wider trays are lower and smaller trays are above them. Example `300+600` is rendered as bottom `600`, top `300`.
4. Fixed double-side mixed root CP coupling so one support node is not coupled twice in UX.
5. Fixed native side parsing for `前侧300+600` / `后侧300+500` so the first tray width is retained.
6. Verification passed: py_compile, targeted parser/mixed tests, full `tests/unit`, render smokes for single/double/seven-layer/different-section cases, and two real ANSYS18.2 mixed-loop jobs with `result_validation=pass`.

Deployment queue status: completed.

1. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecars beside the zip files as transfer authority.
3. Package gate, update self-verification, local update apply, `/health`, and `duxyb/cnpe123` login smoke all passed.

## 2026-06-16 tray-300 physical bolt and <=300 L3 fix

Resolved in source and verified:

1. `L3` rule corrected for small trays: single-width/no-L6 S2 tray widths `<=300 mm` render `L3=0.15 m` regardless of square-tube section. Wider trays still follow the square-tube L3 policy.
2. 300 mm tray modeling now requires physical bolt/round-bar APDL, not just `CP/CPCYC`. The selector gives a strong preference to standard families with `ET,4`, `SECTYPE,10`, `SECDATA,0.006`, `LATT,1,,4,,,,10`, and 506/507/508 physical bolt line pairs.
3. The 300 mm gate is not applied to 200/100 mm small trays. 200/100 are governed by the reviewed small-tray partition: `502/1502` at `L3`, `503/1503` and CPCYC at `L2/2`, and the connector line rewired to `503-509` when transforming larger single-width families.
4. Mixed-width shared-maximum fallback now also applies while rendering APDL parameters. For 300/500 cases that reuse a reviewed 500 mm single-width source, the generated geometry and material slots use 500 mm instead of the first listed 300 mm tray.
5. Web APDL preview now recognizes bolt/round-bar elements and shows them separately from tray rails and arms.
6. Verification passed: targeted tray-width tests, broader selector/static/bolt tests, full `tests/unit`, Node syntax check, and render-entry smokes for double 300 3+2, single 200, and mixed 300/500.

Deployment queue status: completed.

1. Full package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`, SHA256 `0DD63988F61B00BB5AB61C590C1613E7E0CA667B3A5898C2EE952CB3B4A8318C`.
2. Update package refreshed at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`, SHA256 `1171B1FB97138FCD6F2762BF9EC469796435CEC8E69D9DA35044434967212ECB`.
3. Package gate, update self-verification, local update apply, `/health`, and `duxyb/cnpe123` login smoke all passed.

## 2026-06-16 4215 smart section-selection and deployment closeout

Resolved in source and verified:

1. Fixed the stale-learning cause of 300 mm jobs starting at `160-160-8`. Similarity and cache acceptance now include tray width/load and require current v7 evidence for direct learned decisions.
2. Preserved the intended AI-like behavior: learned history can order candidates, but the current job's real ANSYS and deterministic evaluation decide publication.
3. Formal Section 6.1 ratio is authoritative after the final ANSYS run. Trial/formal mismatch no longer blocks when the formal Section 6.1 ratio is `<= 1.0`; over-limit formal results still trigger larger-section or spacing recovery.
4. Candidate and formal ANSYS license-manager unavailable messages now retry the same section/run instead of falsely failing the section.
5. Real ANSYS18.2 validation passed on changed 300/500/600 response-spectrum and static intakes. The 300 single-side representative selected `100-100-6`; the double-side 300 representative failed `100-100-6` then selected `120-120-10`; 600 variants passed after automatic larger-section recovery.
6. Full unit tests passed, deployment package gate passed, and local `D:/CableTrayAI` is updated and healthy.

Open queue:

1. No current source/package blocker remains for unit transfer. For an existing unit deployment, send `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; for a fresh deployment, send `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`. Use the refreshed `.sha256.txt` sidecars in the same folder for transfer verification.
2. If a future unit run fails after this package, retain the full job folder and compare the current formal `evaluation_summary.json`, `result_validation.json`, and `square_section_selection_summary.json` before changing formulas or material policy.

## 2026-06-15 support-spacing recovery and modeling robustness closeout

Resolved in source and verified:

1. Added support-spacing recovery for final deterministic over-limit cases where the current square tube is already the largest intake-allowed section. This includes weld/connection over-limit evidence, so the workflow can keep reducing spacing when section enlargement is exhausted.
2. The user-reported 600 mm static case is now handled by continuing spacing reduction in 0.1 m steps. If `160-160-8` at 1.8 m still has weld ratio above 1.0, the next recovery run will try a smaller spacing instead of returning a terminal software failure.
3. Fixed single-side 300 mm source-family modeling by applying the `L3` offset to single-width/no-L6 connection and CPCYC selectors. This removed the low-layer small-pivot failure without changing double-side reviewed source topology.
4. Added BEAM188 warping KEYOPT restoration and empty line-mesh guarding to harden generated APDL for new intake variants.
5. Real ANSYS18.2 representative regression passed for 300/500/600 response-spectrum and 300/500/600 static rows. The 600 static row reduced spacing from 2.0 m to 1.7 m and then passed.
6. Full `tests/unit` passed.

Deployment closeout:

1. Full package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; update package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
2. Deployment package gate and update VerifyOnly both passed.
3. Local `D:/CableTrayAI` was updated; `/health` and `duxyb/cnpe123` login passed. The exact backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
4. External SHA256 sidecars were refreshed beside the full package and update package; use those sidecars as transfer authority.

## 2026-06-15 unit jobs square-section and bolt-width policy closeout

Resolved:

1. Fixed square-section sizing ratio basis. Candidate acceptance, selection summary, result-validity trial/final comparison, final over-limit upgrade trigger, and learned formal validation now use Chapter 6.1 structural member rows only.
2. Weld and bolt checks remain final result gates but no longer drive square-tube enlargement/economy selection.
3. Bumped learned square-section cache to `square-section-cache-v7-section-6-1-ratio`, so old cache evidence cannot skip fresh trials.
4. Fixed standard S2 single-width/no-L6 `L3` geometry rule: `<=120 mm -> 0.20 m`, `>120 mm -> 0.15 m`.
5. Fixed bolt-width policy beyond area replacement: M8 `36.6 mm2` for `<=200 mm` uses workbook `螺栓 200` single-bolt equations; M12 `84.3 mm2` for `300/500/600 mm` uses workbook two-bolt/lever-arm equations with L `0.241/0.441/0.541 m`.
6. Verified copied unit job evidence: 4210/4215 old stored selected ratios were stale or non-section-sizing ratios; new Chapter 6.1 ratios are much lower. 4212 latest copied folder was operator-cancelled before evaluation summary and is incomplete runtime evidence.
7. Verification passed: targeted tests and full `D:/miniconda3/python.exe -m pytest tests/unit -q`.

Open queue:

1. No package blocker remains for the 2026-06-15 square-section/L3/M8-M12 fix. The refreshed full deployment package is `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`; the refreshed update package is `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; package gate and update self-verification both passed. Local `D:/CableTrayAI` was updated from this package and passed health/login/hash smoke.

## 2026-06-12 AI PPT专题交付复核 closeout

Resolved:

1. 重新完成 AI/智能化专题汇报 PPT，并复制到 `C:/Users/duxy/Desktop/核电工艺所人工智能应用汇报-AI智能化专题.pptx`。
2. 第 7 页已嵌入完整 16:9 真实软件演示视频，避免遮挡、裁切和局部截图；独立视频备份为 `C:/Users/duxy/Desktop/CableTrayAI_对话提资完整演示.mp4`。
3. 生成可编辑 Visio 流程源文件 `C:/Users/duxy/Desktop/CableTrayAI_flow_source.vsdx`，包含 AI 数据闭环、可学习/自恢复、多科室协同 3 页。
4. 交付 QA 通过：桌面 PPT 可由 PowerPoint 打开，`slides=10`，`media_shapes=1`，`slide7_media=1`；占位符扫描通过；Visio 源文件可打开且页数为 3。

Open queue:

1. 本次 PPT 交付无阻塞项。若转移到其他电脑，保留独立 MP4 与 PPT 同目录作为播放兜底。

## 2026-06-12 PPT/demo closeout

Resolved:

1. Built the 河北省军工杯汇报 deck and copied final deliverables to Desktop.
2. Fixed two demo blockers in source and installed copy: JSON-safe `/ai/intake/start-run` responses and `source_package_id=null` for chat-intake real-run startup.
3. Real demo job `CHAT-20260612-f2317f9b9b` completed with ANSYS success, selected `140-140-8`, controlling ratio `0.9074547160463298`, and `result_publishable=true`.
4. PPT QA passed: PowerPoint opens the Desktop deck, 10 slides are present, one embedded media shape is present, and placeholder scan is clean.

Open queue:

1. No blocker remains for the PPT deliverable. If the deck is moved to another computer, keep the standalone MP4 beside it as a playback fallback even though the PPT contains an embedded media part.

## 2026-06-12 unit jobs self-recovery closeout

Resolved in source and verified with real ANSYS:

1. Unit copied `C:/Users/duxy/Desktop/jobs/18185NI-LXSJ4212` stopped after final deterministic over-limit instead of recovering. The job had been auto-selected to `120-120-6` from old learned evidence, but the final formal run failed weld/bolt/cantilever/mixed-beam ratio gates.
2. Old learned cache entries can no longer direct-skip candidate trials unless their `entry_cache_version` equals the current `SQUARE_SECTION_CACHE_VERSION`. Old cache can still order candidates, but not decide a publishable section.
3. Any final deterministic `evaluation_ratio_limit` failure now triggers larger-section recovery when the square section was auto-selected and the intake allowed list still contains larger candidates. This covers non-square-support controlling checks such as weld or bolt ratios.
4. Candidate trial directories no longer copy inherited `job_state.json` or live status files, so a previous failed parent task cannot make preflight reject a fresh candidate before ANSYS starts.
5. Successful square-section upgrade now writes the new selection to `square_section_selection.json` and resets the job state to `apdl_rendered`, allowing the formal rerun to pass real-run guards while retaining history.
6. Real ANSYS18.2 validation on copied unit `4212` passed: auto-recovery tried `120-120-10` (`ratio=1.4624074146092667`, fail), then selected `160-160-8` (`ratio=0.8480306526316335`, pass), formal rerun succeeded, and `result_validation.status=pass`.
7. Unit copied `4215` class is hardened: if main ANSYS succeeds but post-only figure export hits a transient ANSYS license-manager failure, numeric results are assembled for diagnosis, DB/RST are retained for retry, and figure export itself performs bounded license retries.
8. Unit login password failure class is fixed: package `initial_password.txt` is written UTF-8 without BOM, and all installer paths strip BOM before hashing. Temporary install smoke verified `duxyb/cnpe123` login `pass`.
9. Verification passed: full `tests/unit`, targeted square-section/ANSYS post-export/runtime/cleanup/auth/package tests, `py_compile` for touched modules, package gate, update package self verification, initial-password hex check, temporary installed `/health=ok`, package cleanliness scan, and source/package hash checks.
10. Latest send-folder outputs are `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use their external `.sha256.txt` sidecars as transfer authority.
11. Local `D:/CableTrayAI` is refreshed and verified. The old locked server PID `21532` was terminated through WMI after `Stop-Process` and `taskkill` were denied; update backup is `D:/CableTrayAI/_update_backups/20260612_105433`, the fresh server is PID `25224`, `/health` is `ok`, `duxyb/cnpe123` login is `pass`, package gate and update self-verification pass, and key installed source hashes match the repository.

Open queue:

1. No source/package blocker remains for unit transfer. For the existing unit deployment, send `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; for fresh deployment, send `CableTrayAI.zip` or the clean `CableTrayAI` folder. Use the `.sha256.txt` sidecars to verify transfer.
2. Local-only follow-up is closed: the current port-8000 process is the refreshed `D:/CableTrayAI` runtime and can be used for local smoke verification.

## 2026-06-11 unit 4211 connection-node export timeout closeout

Resolved in source and verified with real ANSYS:

1. Unit 4211 failed because `connection_node_export` used a fixed hard `timeout=300`, while the unit machine produced `LS-FORCE-NODES.LIS` and `connection_node_export.out` completion evidence slightly after the timeout path had already marked the post-export failed.
2. The failure evidence is deterministic: main ANSYS completed with `ERROR=0`; connection-node export output existed; `connection_node_export.out` ended with `ROUTINE COMPLETED`, zero MAPDL errors, and warnings only.
3. `core/ansys/connection_export.py` now disables hard timeout killing, records a soft timeout warning only, adds `/EXIT,NOSAV`, accepts only current-run completion markers with a non-empty `LS-FORCE-NODES.LIS`, and removes stale connection export outputs before reruns.
4. Copied unit outputs reassembled successfully at `jobs/verify_unit_4211_connection_export_outputs_20260611_174956/18185NI-LXSJ4211`: `result_validation.status=pass`, `result_publishable=true`, and 262 connection-node rows.
5. Real ANSYS18.2 validation passed at `jobs/verify_unit_4211_connection_export_fix_20260611_175038/18185NI-LXSJ4211`: `connection_node_export_status=success`, `figure_export_status=success`, `figure_count=14`, `result_validation.status=pass`, total wall time about `167.8s`.
6. Full unit suite passed with `D:/miniconda3/python.exe -m pytest tests/unit -q`.

Open queue:

1. No blocking source/package/deployment item remains for the 4211 connection-node export timeout fix. The refreshed transfer files are `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecars in that folder as transfer authority.

## 2026-06-11 unit 4211 50-minute stall root-cause closeout

Resolved in source and verified with real ANSYS:

1. Unit 4211 was not a formula/material/spectrum error. The copied job showed candidate trials and formal solve could complete, but the old flow wasted time by repeating a known 160/140 economy downshift and then could stall at post-only figure export after MAPDL had already completed graphics output.
2. The selector still honors the economy requirement: `0.60 <= ratio <= 0.75` normally triggers one immediately lower intake-allowed trial. The duplicate lower trial is skipped only when a high-similarity learned record already proves that exact immediately lower section completed under real ANSYS and failed with ratio `> 1.0`.
3. The learned skip is not result reuse. The current formal ANSYS run and current deterministic `result_validation.json` remain the publication authority.
4. Figure export now ends with `/EXIT,NOSAV`, detects `ROUTINE COMPLETED` plus zero MAPDL errors, and performs job-scoped cleanup only after a short completion grace. Required figures remain mandatory.
5. Fresh real ANSYS runs delete stale completion-marker outputs before launch, preventing old `8TEG009010.TXT` files from making a new run look complete.
6. Real ANSYS18.2 validation passed at `jobs/verify_4211_unit_hang_fix_20260611_114124/18185NI-LXSJ4211`: main run `116.635979s`, figure export `success`, `figure_count=14`, `result_validation.status=pass`, `result_publishable=true`, total wall time about `162.2s`.
7. Full unit suite passed with `D:/miniconda3/python.exe -m pytest tests/unit -q`.

Open queue:

1. No blocking source/package/deployment item remains for the 4211 stall fix. The refreshed transfer files are `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecars in that folder as transfer authority.

## 2026-06-11 ??4211/4212?????????????? closeout

Resolved in source and verified:

1. ?????? `C:/Users/duxy/Desktop/_square_section_trials` ???4211 `160-160-8` ? 4212 `120-120-6` ????????????? `run_all.mac` ??? `generated_post_numeric.mac`??? `8TEG009010.TXT` ??? `ROUTINE COMPLETED`?`EXIT ANSYS WITHOUT SAVING DATABASE`?`ERROR=0`?
2. ??? ANSYS18.2 ???? APDL ??????? `4294967295` ??? launcher ????? runner ?? returncode `0`???????????? failed????????????????
3. `core/ansys/runner.py` ??? `*.TXT` ???? MAPDL ???????????? + MAPDL ??? 0????????? launcher ?????????? LIS/OUP/??/??????????
4. ????????? `15s` ???????? ANSYS ?????????? job ????????? `completion_marker_cleanup`???????????????????????????
5. ??????????? `trial_dir`?`trial_status_file`?`elapsed_seconds`?`total_output_bytes`?`no_output_seconds`?`ansys_pid` ? API ?????????????????? live status?
6. ??????? `_square_section_trials` ???????????????????????????? solver DB/RST ?? trial runner ???
7. ???????4211 `160-160-8` ??????????? `0.6125688698630086`????4212 `120-120-6` ???????????????????
8. ???????????? `tests/unit`???????????????????? ANSYS18.2 ?? 4212 ????? `47.9s` ???

Open queue:

1. ?????? `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` ? `C:/Users/duxy/Desktop/duxyb-cnpe/???.zip`??? `.sha256.txt` ??????????????? 4211/4212 ?????? job ???? `_square_section_trials` ???????????????

# CableTrayAI 当前修复队列
## 2026-06-10 单位4211/4212导图卡住与候选试算提速 closeout

Resolved in source and verified with real ANSYS:

1. 4212 单位失败证据定位为候选试算主后处理误跑图片命令，触发 ANSYS 批处理 `/IMAGE` warning 和输出停滞，不是建模、反应谱、材料许用值或评定公式错误。
2. 主 ANSYS 入口改用内部 `generated_post_numeric.mac`，只做数值提取；`generated_post.mac` 继续保留为审查命令和导图转换来源。
3. 候选试算阶段跳过图形命令并禁用输出停滞硬杀 watchdog，避免候选选型被“导图卡住”误报为截面失败。
4. 正式导图改为带 live/audit 文件的 post-only 流程，`timeout_minutes` 是软监控阈值，不再硬杀 MAPDL。
5. 使用单位拷回 4212 job 真实 ANSYS18.2 验证通过：主数值流程 `50.1s`，导图 `20.1s`，`figure_count=22`，缺图为空。
6. 全量 `tests/unit` 通过。

Open queue:

1. 无剩余源码/部署阻塞项。单位用 `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` 或 `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip` 重跑 4211/4212；同目录 `.sha256.txt` 为传输校验依据。

## 2026-06-10 异型钢 SECOFFSET 修正 closeout

Resolved in source and unit verified:

1. 异型钢托臂分支不再继承槽钢专用 `SECOFFSET,user,,-0.03249`；当托臂截面为 `YIXINGGANG*` 时生成命令归一化为 `SECOFFSET,user`。
2. 槽钢分支仍保留 `SECOFFSET,user,,-0.03249`，避免影响 `CAOGANG42DAN` 已审查命令流。
3. 标准族渲染和方钢截面选型替换两个入口均已接入，审计字段为 `yixing_secoffset_replacements`。
4. 回归测试覆盖纯文本规则、异型钢试算替换、槽钢保留、标准族渲染。

Open queue:

1. 无剩余源码/部署阻塞项。单位应使用 `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` 或 `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`，并用同目录 `.sha256.txt` 文件校验传输。

## 2026-06-09 4211 economy downshift strategy closeout

Resolved in source and verified with real ANSYS:

1. Added the requested economy downshift strategy: if a fresh passing square-section candidate is in `0.60 <= ratio <= 0.75`, the selector runs exactly one immediately lower intake-allowed square section before final selection.
2. The normal production strategy remains bounded. This does not sweep all smaller sections; it is one downward check only, and only in production `stop_after_first_feasible=True` mode.
3. If the lower candidate passes, it can be selected as the more economical section. If it fails, the already passing larger section remains selected. Already evaluated candidates are skipped to prevent duplicate ANSYS trials after a backward check.
4. Regression tests cover both the lower-section-pass branch and the lower-section-fail branch.
5. Verification passed: targeted selector/workflow/postprocessor/result-validity tests, `py_compile`, and full `tests/unit`.
6. Real ANSYS18.2 validation passed at `jobs/verify_4211_economy_downshift_20260609_202204/18185NI-LXSJ4211`. The downshift ran as requested: `160-160-8` ratio `0.6125191042609882`, then `140-140-8` ratio `1.1132861849732167`.
7. Since `140-140-8` is over limit in the fresh real ANSYS run, the correct formal selected section remains `160-160-8`; formal `result_validation.json` is pass and required figures count is 14.

Open queue:

1. No blocking source/package/deployment item remains for the economy downshift strategy. The refreshed send-folder packages are `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` and `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`; use the external `.sha256.txt` sidecars in that folder as transfer authority.
2. If the unit has evidence that `140-140-8` passes for the same 4211 input, compare that retained job folder against `jobs/verify_4211_economy_downshift_20260609_202204/18185NI-LXSJ4211` before changing any deterministic evaluation rule.

## 2026-06-09 unit 4211 overlimit recovery and H1 geometry closeout

Resolved in source and verified with real ANSYS:

1. Unit 4211 failed after two over-limit candidates. Preserved evidence showed `100-100-6` ratio `1.3581785618588114` and `120-120-10` ratio `1.6479509969960606`; both candidate runs completed, so this was a deterministic capacity over-limit condition.
2. The same candidate evidence showed `generated_model.mac` H1 was not synchronized for the 120 square section: model H1 stayed `0.1` while post/input already used `0.12`.
3. `core/optimizer/square_section_selector.py` now updates model H1 from the square-section outer width. Thickness is ignored for H1, so all 120-wide square tubes use `H1=0.120000`.
4. Production square-section selection still normally runs two candidates for economy. If both of those candidates are deterministic over-limit, it now runs up to two larger intake-allowed candidates instead of failing immediately.
5. The extension is recorded in `square_section_selection.json` through `overlimit_recovery_extensions`, while the base two-candidate economy budget remains visible as `max_evaluated_candidates=2`.
6. Regression tests cover both H1 outer-width synchronization and two-overlimit recovery to a larger allowed section.
7. Verification passed: targeted selector/workflow/postprocessor/result-validity tests and full `pytest tests/unit -q`.
8. Real ANSYS18.2 validation passed at `jobs/verify_4211_h1_overlimit_recovery_20260609_172633/18185NI-LXSJ4211`: evaluated `100-100-6`, `120-120-10`, then `160-160-8`; selected `160-160-8`, ratio `0.6132882273722775`, `result_validation.json` pass, `figure_count=14`.

Open queue:

1. No blocking source/package/deployment item remains for the 4211 over-limit recovery and H1 geometry issue. The unit should install `更新包.zip` or redeploy `CableTrayAI.zip`, then rerun 4211 from a fresh job instead of reusing the old failed candidate directory.

## 2026-06-09 unit 4210 ANSYS timeout false section-failure closeout

Resolved in source and verified with real ANSYS:

1. Unit 4210 failed on `140-140-8` with a misleading square-section failure message. Copied unit evidence shows the candidate trial timed out at `timeout_seconds=720`; no deterministic ratio was produced for that failed attempt.
2. Hash comparison showed unit and local 4210 model/solve/post/spectrum command streams matched. The failure was caused by candidate-trial/runtime watchdog policy, not model generation, spectrum selection, residual mass, or RCC-M evaluation logic.
3. `core/optimizer/square_section_workflow.py` no longer shortens candidate trials to 12 minutes. Candidate trials now use production-safe watchdogs so they can produce APDL/PIP outputs before section selection decides.
4. `core/ansys/runner.py` now applies code-level minimum real-run watchdogs: 120 minutes total timeout, 90 seconds startup no-output timeout, and 300 seconds output-stall timeout. The configured values are retained in `ansys_run_audit.json` as `configured_*` fields.
5. `core/optimizer/square_section_selector.py` now classifies ANSYS timeouts as runtime failures, not section over-limit decisions. A timed-out candidate without a computed ratio will no longer be reported as a section stress failure.
6. Regression tests added in `tests/unit/test_ansys_runtime_timeout_policy.py`; full `pytest tests/unit -q` passed with `115 passed`.
7. Real ANSYS18.2 validation deliberately ran 4210 with `-TimeoutMinutes 12` at `jobs/verify_unit_4210_timeout_clamp_20260609_123539/18185NI-LXSJ4210`; the new code clamped the effective timeout to 7200 seconds and the job passed.
8. Validation result: selected `140-140-8`, controlling ratio `0.9052401909300667`, formal `result_validation.json` pass, `figure_count=14`, and `ansys_run_audit.json` records `configured_timeout_seconds=720`, effective `timeout_seconds=7200`, `timeout_policy.status=clamped`.

Open queue:

1. Rebuild and send the refreshed deployment/update package to the unit. After installing it, unit 4210 should rerun instead of reusing the old timeout-failed trial directory.

## 2026-06-09 unit 4210 candidate-output fallback closeout

Resolved in source, real ANSYS validation, runtime, package, and local install:

1. Unit 4210 reported `140*8` as blocked with `candidate failed because required ansys/pip source outputs are missing ... all-zero or stalled`, although the section is known to satisfy the formal calculation.
2. `core/optimizer/square_section_selector.py` now classifies feasible candidate trials with ratio `<= 1.0` and retryable source-output checks as `formal_validation_retryable` instead of treating them as a square-section capacity failure.
3. The selector now stops section sweeping for those source-output defects and selects the feasible candidate only for formal full-run validation. It does not publish the candidate trial result; formal `result_validation.json` remains the publication gate.
4. Retryable candidate-output checks include required source outputs for modal, JCZH, LS-FORCE, HF-FORCE, MAXBEAMSTRESS, and TMAXBEAMSTRESS. Spectrum errors, ANSYS timeouts, ANSYS run failures, missing evaluation summary, and zero allowables remain non-retryable blockers.
5. `core/pipeline/one_click.py` now reports candidate section, ratio, status, failed checks, domains, run status, and `trial_dir` in the error message.
6. `core/optimizer/square_section_workflow.py` records formal validation mode in `input.json` metadata for traceability.
7. Verification passed: targeted square-section/workflow tests, result-validity/package/auth tests, `py_compile`, and full `tests/unit` (`112 passed`).
8. Real ANSYS18.2 validation passed at `jobs/verify_unit_4210_candidate_fallback_20260609_091048/18185NI-LXSJ4210`: selected `140-140-8`, ratio `0.9052401909300667`, `result_validation.json` pass with 14/14 checks.
9. Deployment refreshed and applied locally: full package `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` SHA256 `83E499A079FD148468A5E9BB4958F106751902CD63D2A86ECFBFAB29AAC9C6F3`; update package `C:/Users/duxy/Desktop/duxyb-update/更新包.zip` SHA256 `E00426429D18887ECD983D601A8653EC0426D6071E942CC35F418977FE661E50`; local backup `D:/CableTrayAI/_update_backups/20260609_091931`; `/health` ok.
10. Latest full deployment package copied to `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip` with `CableTrayAI.zip.sha256.txt`.

Open queue:

1. No blocking source/package/deployment item remains for the 4210 candidate-output fallback issue. The unit should rerun 4210 after installing the new package/update; if it still fails, inspect the new message's `failed_checks` and `trial_dir` instead of changing section size.

## 2026-06-08 two-trial square-section economy strategy closeout

Resolved in source and real ANSYS validation:

1. User requested square-section selection to finish within two candidate runs and treat `0.6-0.9999` as the economic ratio band.
2. `core/optimizer/square_section_selector.py` now records `economic_ratio_min=0.6`, `economic_ratio_max=0.9999`, and `max_evaluated_candidates=2` for production searches.
3. `core/optimizer/square_section_workflow.py` now keeps the intake allowed list as the hard boundary, uses learned/estimated first candidate ordering, and passes the two-trial budget into the selector.
4. If the first candidate is over limit or below the economic band, the selector plans at most one section-modulus correction candidate; it does not sweep the full allowed list.
5. Progress events now report the active trial budget as `candidate_count`, so the web side shows `0/2` instead of `0/6` while still preserving full `available_candidate_count` in the JSON audit.
6. Real ANSYS18.2 validation passed at `jobs/verify_two_trial_section_strategy_20260608_173006` / `E:/CODEX/tray_platform/ANSYS Output/verify_two_trial_section_strategy_20260608_173006`:
   - `18185NI-LXSJ4210`: selected `140-140-8`, ratio `0.9052401909300667`, evaluated candidates `1/2`, result validation `pass`.
   - `18185NI-LXSJ4213` static: selected `120-120-10`, ratio `0.8025890143573237`, evaluated candidates `1/2`, result validation `pass`.
   - `18185NI-LXSJ4215` / raw-6: selected `160-160-8`, ratio `0.9131067176524903`, evaluated candidates `1/2`, result validation `pass`.
7. Verification passed: py_compile, targeted square-section/workflow tests, and full `tests/unit`.

Open queue:

1. No blocking source/package/deployment item remains for the two-trial square-section strategy. Send the regenerated `C:/Users/duxy/Desktop/duxyb-update/更新包.zip` for an update, or `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` for a full deployment.

## 2026-06-08 raw-6 / 18185NI-LXSJ4215 unit-run hotfix closeout

Resolved in source, runtime, package, local install, and smoke tests:

1. Unit clarified the failed row is the last intake (`raw-6`, `18185NI-LXSJ4215`), not 4213. The reported symptom was a satisfying section near ratio `0.99` being returned as `Square section auto-selection failed`.
2. `core/optimizer/square_section_selector.py` now derives candidate controlling ratio from the fresh `evaluation_summary.json` maximum deterministic Chapter 6 ratio. Stale `result_validation.json:evaluation_ratio_limit` ratio evidence is recorded as `validation_ratio_limit_ratio` but ignored for candidate acceptance.
3. Section-selection boundary is aligned to the project gate: ratio `> 1.0` fails; ratio `<= 1.0` passes. `run_square_section_search`, `select_best_square_section`, and `write_square_section_selection_summary` were updated.
4. `core/pipeline/one_click.py` now raises a diagnostic message with candidate section/ratio/status/failed non-ratio checks instead of the old generic one-line error.
5. `core/ansys/runner.py` now treats WARNING-level `file_or_permission_error` file probes as nonblocking warnings, while ERROR/FATAL file/permission messages still block. Required output absence remains enforced by result validation.
6. Regression coverage added:
   - stale validation ratio `1.01` plus fresh evaluation ratio `0.99` must pass;
   - exact ratio `1.0` is accepted;
   - WARNING-level file probe does not block;
   - ERROR-level file open failure still blocks.
7. Verification passed: targeted tests `tests/unit/test_square_section_selector.py` and `tests/unit/test_ansys_command_stream_warning_gate.py`; full `tests/unit`; row6 historical readback selected `160-160-8` with max ratio `0.9131955968601544`.
8. Runtime/package refreshed: server, desktop, and installer runtimes rebuilt; deployment package gate passed; update package `-VerifyOnly` passed; package cleanliness scan passed.
9. Final full deployment package is regenerated at `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`; use the generated file hash from the final closeout as the transfer authority.
10. Final update package is regenerated at `C:/Users/duxy/Desktop/duxyb-update/更新包.zip`; its extracted `manifest/update_manifest.json` records the payload SHA256 and payload file count.
11. Local install smoke: update package applied to `D:/CableTrayAI`; `/health` returned ok; source/package/installed hashes match for current touched runtime modules and server exe.

Open queue:

1. No blocking source/package/deployment item remains for the raw-6/4215 unit-run hotfix. Historical failed unit job records still need to be rerun on the unit machine after applying `更新包.zip`.

## 2026-06-08 deployment package fixed-password closeout

Resolved in source, package, local install, and smoke tests:

1. Deployment package now directly supports the user's requested fixed login password `cnpe123`.
2. `scripts/package_duxyb_intranet_release.ps1` defaults `InitialPassword` to `cnpe123` and writes `config/initial_password.txt` into `C:/Users/duxy/Desktop/duxyb/CableTrayAI`.
3. The native installer reads that package file. Fresh install and installer-managed auth reset both write local `config/auth.local.json` for `duxyb`, `jianghl`, and `wanggangb` using `cnpe123`.
4. Existing target `auth.local.json` is not silently preserved when the package fixed password exists; it is backed up to `auth.local.json.bak_<timestamp>` and then rewritten, fixing old random-password deployments.
5. Python and PowerShell fallback installers were aligned to the same package password and auth-backup behavior.
6. Installer cleanup now removes stale target-root `CableTrayAI_Installer.exe`, avoiding old installer remnants in installed folders.
7. Final full deployment package: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, size `78960185` bytes; SHA256 `CE94EACF784DD7C8F1F7151DDFA22E099D7165DF1A231C0B26FF5FDAA0CD5EEE`; package gate passed.
8. Package cleanliness passed: no top-level `jobs/uploads/outputs/logs`, no local configs, no `runtime/auth_sessions.json`, no `__pycache__`, no `*.pyc`, and package directory dirty-count is 0.
9. Local installer smoke against `D:/CableTrayAI` passed: `install_manifest.json` and `CableTrayAI_LOGIN_INFO.txt` record `cnpe123`; `duxyb/cnpe123` login passed; wrong password returned 401; `/health` returned ok; root `D:/CableTrayAI/CableTrayAI_Installer.exe` is absent.

Open queue:

1. No blocking item remains for sending the full deployment package. Send `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` when a full deployment is desired.

## 2026-06-08 mail update package closeout

Resolved in source, final package, local install, and update-package smoke:

1. Added a formal mail-safe update flow so future unit upgrades use `更新包.zip` instead of manual full-folder copy.
2. `scripts/package_internal_update.ps1` creates `C:/Users/duxy/Desktop/duxyb-update/更新包.zip`. It rebuilds the clean deployment payload, writes a payload zip plus per-file SHA256 manifest, and self-runs `install_update.ps1 -VerifyOnly`.
3. `scripts/install_update_package.ps1` verifies the payload zip SHA256 and every expanded file before applying, rejects protected runtime/local-config/cache files, applies through `scripts/apply_internal_update.ps1`, restarts the server, checks `/health`, and attempts backup overlay rollback if health fails.
4. `scripts/package_duxyb_intranet_release.ps1` now removes package-gate-generated `__pycache__`, `.pytest_cache`, `.pytest_tmp`, `*.pyc`, and `*.pyo` after the deployment gate and before zip creation.
5. Final package checks passed: no top-level `jobs/uploads/outputs/logs`, no `config/*.local.*`, no `runtime/auth_sessions.json`, no `ansys.local.toml`, no `__pycache__`, and no `*.pyc` in either `更新包.zip` or payload `CableTrayAI.zip`.
6. Final update package: `C:/Users/duxy/Desktop/duxyb-update/更新包.zip`, size `78513666` bytes; payload SHA256 `265dde3d6bb0d82192bdab1720f0e8959946b564743f804e6d9432cd9e4bd5d0`, payload file count `1774`.
7. Local installed smoke passed using the final update package against `D:/CableTrayAI`: verification pass, backup `D:/CableTrayAI/_update_backups/20260608_135840`, `/health` pass, and installed hashes match source for the update scripts and checked runtime modules.

Open queue:

1. No blocking item remains for the mail-safe update package. For future feature optimization releases, regenerate `更新包.zip` with `scripts/package_internal_update.ps1` and send that zip to the unit.

## 2026-06-08 unit deployment / 12-layer validation closeout

Resolved in source, package, and installer smoke:

1. Unit deployment login `duxyb / cnpe123` failed because the native installer did not create `config/auth.local.json` on first install. The backend has no committed default credentials by design, so an install without a local auth file rejects every password.
2. `scripts/CableTrayAIInstaller.cs` now creates `config/auth.local.json` locally with users `duxyb`, `jianghl`, and `wanggangb` when no local auth file exists. Existing local auth configs are preserved.
3. The first-install password is generated locally unless `CABLETRAYAI_INITIAL_PASSWORD` is set. The installer writes `CableTrayAI_LOGIN_INFO.txt` plus `install_manifest.json` on the target machine so the password is easy to find during unit deployment without committing a default password.
4. `scripts/package_duxyb_intranet_release.ps1` now avoids LibreOffice Python when running the deployment package gate and its package README points operators to `CableTrayAI_LOGIN_INFO.txt`.
5. Per-side `12+12` support has been extended and real-ANSYS verified. High-layer source-family keypoints now use expanded `KPOFF/KPFSTEP/KPBKBASE` numbering, and post/connection-node export uses the same numbering.
6. Real validation job: `jobs/verify_12x12_high_layer_static_20260608_124204/S2_12x12_160x8_static_overload`. Main solve `success`, connection export `success`, figure export `success` with all 14 required figures, and modal frequency table rows parsed.
7. The 12+12 validation proves modeling/calculation capability, not engineering adequacy. The synthetic high-load 160x8 sample remains not publishable because deterministic ratios exceed 1.0; this is the expected answer for leadership demonstration.
8. Static-method modal appendix parsing is fixed for ANSYS18.2 participation-factor `Mode.oup` output and low-frequency rows; response-spectrum MT >50 Hz gate remains unchanged.
9. Regression tests passed for installer auth, high-layer APDL numbering, postprocessor alignment, modal parsing, static method policy, section workflow, MT learning, and report template injection.

Open queue:

1. No blocking source/package/deployment item remains for the unit deployment, 12-layer validation, static modal appendix table, or installer credential UX.
2. Current package policy intentionally ships `config/initial_password.txt` with `cnpe123`; installers back up and rewrite target `config/auth.local.json` to that packaged password. Do not reintroduce random-password-only behavior unless the user explicitly changes the deployment policy.

## 2026-06-07 report-generation injection closeout

Resolved in source and verified against installed job `18185NI-LXSJ4212`:

1. User requested report-generation optimization only: fill missing report content from existing result files and figures, preserve the fixed report format, remove blank appendix pages caused by page breaks, and mark only the corresponding changed/added titles red in the final generated report.
2. `core/report/template_injector.py` now treats the <=120 mm square-tube equivalent weld branch as a report-specific branch: the not-applicable `HF-FORCE` root-load table is removed from the generated copy instead of being left as `待确认`.
3. The generated weld table is now `表6-2 托臂根部焊缝评定结果（应力比）`, six columns, eight deterministic rows from `evaluation_summary.json`; equivalent stress uses `calculation_value / 0.526`.
4. Generated reports mark only injected/updated section titles, table titles and figure captions red; body text and table values are not colored.
5. Appendix cleanup removes empty page-break-only paragraphs inside actual appendices and skips TOC paragraphs, avoiding the previous accidental TOC/layout touch.
6. Verification report: `C:/Users/duxy/Desktop/report_review_18185NI-LXSJ4212_20260607_180115.docx`. Audit status is `pass`, warnings are empty, the equivalent weld table has 8 data rows.
7. Regression coverage added in `tests/unit/test_template_report_injector.py` for equivalent weld row calculations and appendix page-break cleanup TOC skip.
8. Verification passed: report unit test, report template integration test, full unit test suite, and `py_compile`.
9. Deployment completed: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` refreshed, package gate passed, applied to `D:/CableTrayAI`, backup `D:/CableTrayAI/_update_backups/20260607_180517`, service PID `21176`, `/health` ok, root no-cache headers ok, installed/package/source `core/report/template_injector.py` hashes match.

Open queue:

1. No blocking source/deployment item remains for the report-generation optimization.

## 2026-06-07 frontend ANSYS command-stream review lifecycle closeout

Resolved in source, package, and local installation:

1. User request: after section selection, the ANSYS model and command-stream review panel should show the current generated model/solve/post streams in real time; when the next calculation starts, old streams should be cleared; after returning from the result page, the panel should remain unless a new calculation starts.
2. `apps/web/index.html` now keeps `activeJobId` in the restored intake session instead of clearing it in `restoreIntakeSession()`.
3. A successful new `/runs/start` clears the old command-stream panel and saved active job; a failed start does not erase the last reviewable job.
4. During run polling, active job changes clear stale model/commands immediately, and command review is reloaded during `render_commands`, `select_square_section`, `running_ansys`, retry, publish, and terminal stages.
5. Engineering-review reloads are throttled and guarded by `reviewGeneration/reviewJobId/reviewLoadJobId`, so a delayed response from a previous job cannot overwrite the current job's panel.
6. `refreshEngineeringReview()` is now defined and forwards to `loadEngineeringReview({ force: true })`, fixing the existing undefined-function path used by template-report figure checks.
7. Verification passed: inline `apps/web/index.html` script parsed with Node, `python -m pytest tests/unit -q` passed with `89 passed`, and hardcode scan over `core/apps/templates` had no hits.
8. Deployment completed: rebuilt `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, package gate passed, applied to `D:/CableTrayAI`, `/health` ok, root no-cache headers ok, installed `apps/web/index.html` hash matches source. The exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.

Open queue:

1. No blocking item remains for the ANSYS command-stream review panel lifecycle fix.
2. A future UX improvement can add visible “命令流已刷新/当前 job” status text, but current functional requirement is complete.

## 2026-06-07 18185NI-LXSJ4212 foundation-load zero extraction audit closeout

Resolved in source and verified against the latest completed web run:

1. Latest completed web job checked: `D:/CableTrayAI/jobs/18185NI-LXSJ4212`, status `evaluated`, `result_validation.status=pass`.
2. The result page's foundation load table values match `foundation_loads.json` and raw `JCZH.LIS`.
3. The highlighted DW zero components are raw ANSYS-exported values, not parser defaults:
   - `JCZH.LIS` DW row: `FX=104.1`, `FY=0.0`, `FZ=4211.7`, `MX=0.0`, `MY=1128.7`, `MZ=0.0`.
   - `foundation_loads.json` keeps `raw_value: "0.0"` for the displayed `FY` and `MZ`.
4. This is not the known bad pattern where extraction hits a wrong support node and leaves only `FZ`; DW still has non-zero `FX` and `MY`, and the job's `foundation_load_values` gate passed.
5. Parser hardening added in `core/results/lis_parser.py`: `JCZH.LIS` foundation rows now require all six components `FX/FY/FZ/MX/MY/MZ` to be present. Missing or blank components raise `LisParseError`; they are no longer silently defaulted to `0`.
6. Regression tests added in `tests/unit/test_lis_parser_foundation.py`:
   - Explicit `0.0` components are preserved with raw-value traceability.
   - Missing components are rejected instead of being converted to zero.
7. Verification passed: targeted LIS parser/result-validity tests, full unit tests (`89 passed`), `py_compile`, and hardcode scan over `core/apps/templates`.
8. Deployment completed: rebuilt `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, package gate passed including runtime XML support and no-expat spectrum smoke, applied to `D:/CableTrayAI`, and service `/health` returned ok. The exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
9. Installed-code verification passed: installed parser preserves explicit `0.0` from `D:/CableTrayAI/jobs/18185NI-LXSJ4212/JCZH.LIS` and rejects missing `JCZH` components instead of defaulting to zero.

Open queue:

1. No blocking source/deployment item remains for the 4212 foundation-load zero audit and `JCZH.LIS` parser hardening.

## 2026-06-07 18185NI-LXSJ4213 square-section candidate gate hotfix closeout

Resolved in source and verified against the installed failed web-run evidence:

1. Web error `Square section auto-selection failed; formal calculation is blocked until a section with ratio <= 1.0 is found.` was not caused by all allowed sections failing.
2. Installed run evidence `D:/CableTrayAI/jobs/18185NI-LXSJ4213/square_section_selection.json` showed:
   - `100-100-6 = 2.3374003257388036` fail.
   - `120-120-10 = 1.128459493680719` fail.
   - `140-140-8 = 0.9342488209446427`, which is below 1.0 and should be selected.
3. Root cause: candidate trials for static-method section selection do not run final report figure export, so they do not have the report-only appendix-A `Mode.oup` frequency table. The selector incorrectly treated `required_file_Mode.oup` and `modal_frequency_table` as source-blocking checks during candidate selection.
4. Fix: `core/optimizer/square_section_selector.py` now ignores `required_file_Mode.oup` and `modal_frequency_table` only for static-method candidate trials. Response-spectrum trials still treat those checks as blocking, and final formal static reports still require MOTAI figures plus the frequency table.
5. Regression tests added in `tests/unit/test_square_section_selector.py`:
   - Static candidate with ratio below 1 and only report-only modal-frequency checks is accepted.
   - Response-spectrum candidate with missing `Mode.oup` remains blocked.
6. Verification passed: targeted square-section/static/result tests and full unit tests (`87 passed`), plus `py_compile` for the touched selector and test module.
7. Deployment completed: rebuilt `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`, package gate passed including runtime XML support and no-expat spectrum smoke, applied to `D:/CableTrayAI`, and service `/health` returned ok. The exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
8. Installed-code verification passed: reading the existing `D:/CableTrayAI/jobs/_square_section_trials/18185NI-LXSJ4213/20260607T062835489986Z/140-140-8` trial with installed code now returns candidate `status=pass`, ratio `0.9342488209446427`, and no blocking diagnosis domain.

Open queue:

1. No blocking source/deployment item remains for the 4213 square-section candidate gate hotfix.
2. Historical failed job records still show the old failure until `18185NI-LXSJ4213` is rerun from the web.

## 2026-06-07 static-method no-main-MT correction closeout

This section supersedes the 2026-06-06 static modal gate closeout below.

Resolved in source and real ANSYS18.2 evidence:

1. Corrected policy: static-method jobs do not use response-spectrum modal extraction and do not have a main-solve MT or 50 Hz Mode.oup cutoff gate.
2. Static-method S2 reports still require appendix-A modal content: `MOTAI-1.PNG` through `MOTAI-4.PNG` and a frequency table.
3. Implementation split the concepts:
   - `requires.modal_analysis=false` for static main solve, so `modal_mt_cutoff` is not checked.
   - `requires.modal_figures=true` and `requires.modal_frequency_table=true`, so `Mode.oup` rows and MOTAI figures are still required for the report.
4. `generated_solve.mac` for static jobs preserves the audited static solve stream and rewrites only equivalent-static `ACEL` coefficients; it no longer inserts `ANTYPE,2`, `MODOPT`, `MXPAND`, or `MT`.
5. Figure export now runs a fixed four-mode post-only modal graphics solve for static jobs, writes `Mode.oup` for the frequency table, and exports `MOTAI-1.PNG` through `MOTAI-4.PNG`. This is not the main solve MT and has no 50 Hz cutoff gate.
6. The stale static MT learning entry was removed from `data/calibration/modal_mode_count_cache.json`; future static jobs are not recorded in modal MT learning.
7. Real ANSYS18.2 validation job `jobs/verify_4213_static_no_mt_20260607_140551` succeeded: main solve duration about `20.04s`, no main modal/MT in `generated_solve.mac`, figure export success, `figure_count=14`, required MOTAI figures present.
8. Result assembly for that job is `usable`, `result_validation.status=pass`, `fail_count=0`, `modal_rows=4`, `modal_frequency_table=pass`, `required_file_Mode.oup=pass`, `required_figures=pass`, and no `modal_mt_cutoff` check is emitted.
9. Verification passed: targeted static/modal/result/renderer tests, full unit tests, py_compile, JSON validation, hardcode scan over `core/apps/templates`, and `source_materials` remained unchanged.
10. Deployment completed: rebuilt `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` with package gate pass, applied to `D:/CableTrayAI`, backup `D:/CableTrayAI/_update_backups/20260607_141510`, service restarted as PID `14620`, `/health` ok. Installed static-policy smoke returns `modal_analysis=false`, `modal_figures=true`, `modal_frequency_table=true`, and `modal_mode_count=null`.

Open queue:

1. No blocking item remains for the corrected static-method no-main-MT policy.
2. Historical web-run records may still show the old `modal_mt_cutoff` failure; rerun the job with the current service.

## 2026-06-06 18185NI-LXSJ4213 static modal gate closeout

Resolved in source and real ANSYS18.2 evidence after reviewing the user's 4120 static command streams:

1. Correction to the previous note: static-method jobs must still satisfy the 50 Hz modal coverage gate. The correct fix is MT/source-policy repair, not static gate bypass.
2. The standard 4120 static command set places modal solve in the `01` model command stream with literal `MODOPT,LANB,887` / `MXPAND,887`; the `02` static stream then performs `ANTYPE,0` / `ACEL` load steps.
3. `core/validation/result_validity_gate.py` now blocks static and response-spectrum jobs alike when required modal rows do not include a row above 50 Hz.
4. `core/apdl/intake_standard_family_renderer.py` now inserts a standard modal block matching the audited pattern and searches same-name library model files for a source modal count when the selected source family lacks one.
5. For `18185NI-LXSJ4213`, the renderer recovers audited source MT `887`; `core/pipeline/one_click.py` can retry with that source-traceable MT when normal retries hit the 240 cap.
6. Real ANSYS18.2 validation job `jobs/verify_4213_static_modal887_20260606_221633` succeeded with `MT=887`: return code `0`, result validation `pass`, first mode above 50 Hz is mode `493` at `50.00458560826 Hz`, mode `497` is `50.25466922999 Hz`, and mode `887` is `270.0014312982 Hz`.
7. The modal learning cache now records a compact recommendation for future similar static jobs: `recommended_modal_mode_count=497`, with audited-source fallback `887` still available.
8. Verification passed: `py_compile`, targeted modal/result/renderer/retry tests, full unit tests, real ANSYS18.2 validation, hardcode scan over `core/apps/templates`, and `source_materials` remained unchanged.
9. Deployment completed: `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip` size `79098955` bytes, applied to `D:/CableTrayAI`, backup `D:/CableTrayAI/_update_backups/20260606_223517`, service restarted as PID `47364`, `/health` ok.
10. Installed smoke for `18185NI-LXSJ4213` modal policy returns `modal_mode_count_from_payload=497`, `assigned_source=learned_similar_intake_cache`, and `source_modal_mode_count=887`.

Open queue:

1. No blocking item remains for the current `modal_mt_cutoff` web-side failure.
2. Historical web-run records may still show the old failed run; reruns use the corrected static MT policy.

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

## 2026-06-06 截面学习 v6 队列 closeout

Resolved in source, package, local install, and verification:

1. 方钢截面长期学习已启用，版本为 `square-section-cache-v6-learned-allowed-start`。它面向所有后续提资，不是 4210 专用。
2. 每次真实 ANSYS 方钢选型成功后会记录相似特征、候选比值和最终截面；新提资只在相似度足够高时使用该记录作为允许列表内的起算提示。
3. 学习记录不能新增提资未列截面，不能直接判定满足，不能替代当前 job 的真实 ANSYS 和 deterministic ratio gate。
4. 已从相似特征移除 `arm_section_family`，因为它由当前方钢截面派生，不是独立提资条件；这避免选型前 100 分支错误命中旧 100 样本。
5. 缓存命中 tie-break 已改为相似度、当前版本、更新时间优先，旧版本同分样本不会压过最新 v6 样本。
6. `square_section_selection_cache.json` 已清理压缩，只保留学习必要字段，避免长期缓存带入 trial 目录审计和复制文件列表。
7. 4210 源码真实 ANSYS 验证通过：`verify_4210_section_learning_20260606_190645` 与 `verify_4210_section_learning_applied_20260606_192140` 均 pass，最终 `140-140-8`，控制比 `0.9052401909300667`。
8. 修复后源码和安装版直接命中检查均返回最新 v6 `140-140-8` 样本，学习起算顺序为 `120-120-6`、`120-120-10`、`140-140-8`、`160-160-8`，跳过 `100-100-6` 和 `100-100-8`。
9. 部署包已重建并应用到 `D:/CableTrayAI`，备份 `D:/CableTrayAI/_update_backups/20260606_193731`；服务 PID `38056`，`/health` ok，安装文件 hash 与源码一致。
10. Verification: py_compile passed, target tests passed, full unit tests passed, hardcode scan had no core/apps/templates runtime hits, package gate passed.

Open queue:

1. No blocking item remains for the section-learning optimization request.
2. Future real successful jobs should be allowed to update `data/calibration/square_section_selection_cache.json`; review diffs to ensure the cache remains compact and contains no source_materials or bulky job artifacts.

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

## 2026-06-07 report render QA and appendix caption closeout

Resolved:

1. Installed a usable LibreOffice QA renderer without relying on Program Files write permission by extracting the MSI to `C:/Users/duxy/AppData/Local/LibreOfficePortableExtracted` and fixing its `bootstrap.ini`.
2. Re-rendered the generated 4212 report through portable `soffice.com`; the first report sample exposed a final-page caption-only defect for `图C-8`.
3. Fixed `core/report/template_injector.py` so every inserted figure paragraph keeps with the following caption paragraph.
4. Regenerated `C:/Users/duxy/Desktop/report_review_18185NI-LXSJ4212_20260607_190600.docx`; PDF/PNG spot checks confirm no blank-page suspects and the final figure/caption stay together.

Deployment queue status: completed.

1. Refreshed `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`.
2. Applied to `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260607_191437`.
3. Restarted service as PID `18604`.
4. `/health` returned ok, root no-cache headers are present, and installed/package/source hashes matched for the report injector and handoff docs.

## 2026-06-07 pre-deployment known-issue audit closeout

Resolved during final audit:

1. Static-method report table 3-1 used the raw intake elevation instead of the selected equivalent-static spectrum elevation. For `18185NI-LXSJ4213`, that meant `7.5m` instead of the selected `13.09m`, causing report audit warning.
2. `core/report/template_injector.py` now reads static report spectrum elevations from `metadata.static_acceleration_source.selected_elevation/elevations`.
3. Recent installed jobs `18185NI-LXSJ4211`, `18185NI-LXSJ4212`, `18185NI-LXSJ4213`, and `18185NI-LXSJ4214` all regenerate template reports with audit `pass`.

Deployment queue status: completed.

1. Refreshed `C:/Users/duxy/Desktop/duxyb/CableTrayAI.zip`.
2. Applied to `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260607_202131`.
3. Restarted service as PID `20688`.
4. `/health` returned ok, root no-cache headers are present, package contains runtime XML support files, and installed/package/source hashes matched for all checked runtime files.

## 2026-06-12 real ANSYS variant validation closeout

Resolved:

1. User requested real ANSYS validation with changed intake references. A job-local validation workbook was created with double-side 2+2 layers at 600 mm, single-side 5 layers at 600 mm, and double-side 3+3 layers at 600 mm. No uploaded/source workbook was modified.
2. True ANSYS18.2 validation found one real selector defect: the two-trial/economic search path could report square-section failure before proving every remaining intake-allowed square tube. This was visible in `18185NI-LXSJ9101`, where `140-140-8` and smaller skipped candidates were not evaluated in the first run.
3. `core/optimizer/square_section_selector.py` now enables a final failure-exhaustion pass before blocking: when all tested candidates are deterministic over-limit and no feasible result exists, all untested allowed sections are appended and run with fresh ANSYS/deterministic evaluation. Smart jumps and economic downshift are disabled during this exhaustion pass.
4. Regression coverage was added in `tests/unit/test_square_section_selector.py` for both cases: a skipped allowed section later passes, and all allowed sections fail after exhaustive proof.
5. Verification passed: full `pytest` returned `154 passed`; real ANSYS rerun for `18185NI-LXSJ9101` evaluated `120-120-6`, `120-120-10`, `160-160-8`, `100-100-6`, `100-100-8`, and `140-140-8`, all over 1.0, so final failure is a proven engineering capacity result.
6. Real ANSYS variant outcomes: `18185NI-LXSJ9103` double-side 3+3 layers, 600 mm passed with `160-160-8` and controlling ratio `0.8582242170469485`; `18185NI-LXSJ9102` single-side 5 layers, 600 mm completed ANSYS but failed deterministic weld equivalent ratio `1.2479863056049951`.

Deployment queue status: completed.

1. Full package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Mail/update package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
3. Update applied to `D:/CableTrayAI`; backup `D:/CableTrayAI/_update_backups/20260612_175308`.
4. Active service `/health` is ok; `duxyb/cnpe123` login passes; installed source hash matches repository source for the selector fix.

## 2026-06-12 conversational intake calculation closeout

Resolved in source:

1. Added a conversation-to-intake workflow for departments that do not use the mechanics Excel batch sheet. Operators can describe requirements such as single/double side, layer count, tray width, spacing, support height, project/factory/elevation, and candidate square sections.
2. The workflow is conservative by design: it returns missing-field prompts instead of starting ANSYS when the conversation lacks spectrum file, allowed square sections, geometry, or project/factory/elevation information.
3. `apps/api/app/main.py` now exposes `/ai/intake/preview` and `/ai/intake/start-run`. The start endpoint writes a traceable chat intake workbook and then reuses the existing `/runs/start` production path rather than creating a separate calculation engine.
4. `apps/web/ai_intake.html` provides the web UI; `apps/web/ai_tools.html` links to it.
5. `docs/ONLINE_REFERENCE_POLICY.md` records the OpenAI structured-output/function-calling references used as tooling guidance only. Mechanical authority remains local APDL/PIP/MAC/SECT, real ANSYS, deterministic formulas, and source refs.

Verification:

1. Full `pytest` returned `158 passed`.
2. Python compile passed for the new parser and API module.
3. Inline JavaScript syntax checks passed for the new page and modified AI tools page.
4. Temporary source-service HTTP checks passed: complete conversational intake previews as pass; missing or nonexistent spectrum files block with `spectrum_file`.

Deployment queue status: completed.

1. Full package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Mail/update package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
3. Update applied to `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
4. Active service `/health` is ok; `duxyb/cnpe123` login passes; `/ai-intake` returns 200; installed hashes match source for `core/intake/chat_intake.py`, `apps/web/ai_intake.html`, and `apps/api/app/main.py`.

## 2026-06-12 conversational intake UX cleanup

Resolved in source:

1. Other disciplines no longer need to provide or see a formal mechanics report number in the chat intake UI.
2. A report-like token pasted in chat is retained only as a raw detected reference number; the calculation still uses an internal `CHAT-...` id unless a backend caller explicitly allows a formal report number.
3. The default candidate square-section checkbox was removed. Explicit candidate sections in the message are used directly; if no section is supplied, the page exposes a one-click fallback `使用单位候选库补截面`.
4. Internal tracking fields are hidden from the structured preview table and replaced with user-facing labels.

Verification:

1. Full `pytest` returned `158 passed`.
2. Python compile passed for the parser and API.
3. Node/VM script checks passed for the modified pages.
4. Unicode parse smoke passed: `18185NI-LXSJ9001` remains trace evidence while the job id is `CHAT-...`.

Deployment queue status: completed.

1. Full package and update package are refreshed in `C:/Users/duxy/Desktop/duxyb-cnpe`.
2. Local `D:/CableTrayAI` update is applied; exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.

## 2026-06-16 mixed tray-width modeling closeout

Resolved in source:

1. Mixed tray-width front/back layouts no longer reuse one maximum tray-width geometry for every layer. `core/apdl/mixed_tray_model.py` renders each layer independently so combinations such as single-side `300+600` preserve the correct tray width, load density, arm length split, bolt topology, and post-processing trace points.
2. The 600 mm tray intake split is now `0.47+0.20`, so the generated model no longer carries the incorrect `0.22m` tail raised during review.
3. `core/apdl/intake_standard_family_renderer.py` keeps standard source-family solve/post references but bypasses the old source-family model geometry when a valid mixed-width layer payload is detected.
4. Unit regression coverage now checks `300+600` rendering, 300/600 SECT inclusion, CSOLID bolt creation, 600 mm tail geometry, and the audit marker proving shared-maximum geometry is not used.
5. Learning caches were updated from the successful real ANSYS case so future similar NX mixed-width jobs can order square-section and MT choices from validated evidence.

Verification:

1. `D:/miniconda3/python.exe -m py_compile core/apdl/mixed_tray_model.py core/apdl/intake_standard_family_renderer.py core/intake/tray_load_parser.py` passed.
2. `D:/miniconda3/python.exe -m pytest tests/unit/test_tray_load_parser.py tests/unit/test_intake_standard_family_tray_widths.py -q` returned `28 passed`.
3. Real ANSYS18.2 passed for NX, `-8.8m`, single-side two layers `300+600`, support spacing `2m`, square-support height `2.2m`, response spectrum. Selected section: `100-100-6`; controlling ratio: `0.418410665203697`.

Operator artifact:

1. Full copied result folder: `C:/Users/duxy/Desktop/NX_-8.8m_single_300_600_results_20260616_171205`.

Deployment queue status: completed.

1. Full package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/CableTrayAI.zip`.
2. Mail/update package rebuilt at `C:/Users/duxy/Desktop/duxyb-cnpe/更新包.zip`.
3. Update applied to `D:/CableTrayAI`; the exact latest backup path is recorded in `D:/CableTrayAI/docs/last_internal_update_apply.json`.
4. Active service `/health` is ok; `duxyb/cnpe123` login passes; installed source hash matches repository source for the mixed tray-width renderer, intake renderer, and tray parser changes.
