# CableTrayAI 新对话接力提示词

请在 `E:\CODEX\tray_platform\CableTrayAI` 继续 CableTrayAI 发布前修复任务。先读取：

- `AGENTS.md`
- `docs/CODEX_RECOVERY_STATE.json`
- `docs/CURRENT_WORK_STATE.md`
- `docs/ACTIVE_FIX_QUEUE.md`

当前优先目标：

1. 解决上下文压缩后重复恢复慢的问题：以后每次关键修改、验证、打包后更新 `docs/CODEX_RECOVERY_STATE.json`。
2. 修复方钢截面选型和建模一致性：
   - 提资驱动建模，不能用旧缓存、历史 job 或历史报告结果替代。
   - 500 mm 托盘必须保留 `500-75-2mm` 托盘截面。
   - `50-42` 是托臂/异形钢相关截面，不是托盘截面。
   - 方钢候选必须来自提资 Excel “计算说明”，未列出的截面不得试算。
   - 选型控制比值必须来自最终确定性评定，与第六章结果来源一致。
3. 修复旧 trial/job 缓存导致 4210/4211/4212 结果串用、失败或错误选型的问题。
4. 用真实 ANSYS 路径做受控验证，不允许 silent mock。
5. 重新打包部署包到：
   - `C:\Users\duxy\Desktop\duxyb\CableTrayAI`
   - `C:\Users\duxy\Desktop\duxyb\CableTrayAI.zip`

必须遵守：

- 不修改 `source_materials`。
- 不编造公式。
- 不把历史报告数值硬凑成通过。
- 不把 mock/dry-run 当正式结果。
- 不提交或打包历史 `jobs/uploads/outputs/logs`。

请直接从修复队列继续，不要重新分析旧对话。
