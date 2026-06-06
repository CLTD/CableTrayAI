# 架构门禁落地审计

本文记录本轮必须落地的架构改动。结论先写清楚：AI 只能做理解、解释、质控和建议；正式计算、结果提取、评定和报告注入仍然以 ANSYS 输出、Excel 权威评定、确定性公式和 source_ref 为准。

## 1. 方钢截面选型不再全量硬扫

已落地。

实现位置：

- `core/optimizer/square_section_selector.py`
- `core/optimizer/square_section_workflow.py`

规则：

- 先以标准模板当前方钢为锚点。
- 相似提资缓存只用来调整候选顺序，不复用结论。
- 每个候选仍要真实试算并通过确定性应力比门禁。
- 如果控制项是方钢应力比，可以按截面模量趋势少量跳跃。
- 如果控制项变成焊缝、螺栓或后处理源文件异常，不继续放大方钢。

## 2. 相似提资缓存只做排序提示

已落地。

实现位置：

- `core/optimizer/square_section_workflow.py`

缓存字段：

- support_type
- analysis_method
- arm_section_family
- building
- area
- elevation_m
- support_spacing_m
- support_height_m
- layers_front
- layers_back
- tray_widths_mm
- tray_load_sum_kg_m

边界：

- 完全相同输入可复用上一轮截面选择建议，但正式 job 仍要跑 ANSYS。
- 相似输入只能把候选区间提前，不能直接当成计算通过。
- 页面会显示 similar_cache_order_hint，方便人工知道为什么从这些候选开始。

## 3. 源文件异常先阻断，不靠加大方钢掩盖

已落地。

实现位置：

- `core/optimizer/square_section_selector.py`
- `core/validation/result_validity_gate.py`

阻断类型：

- Mode.oup 的 MT 截断未满足要求。
- 反应谱或 100 Hz 静力修正来源缺失。
- JCZH.LIS 基础载荷缺失、全零或 UNKNOWN。
- LS-FORCE.LIS 连接螺栓载荷缺失、全零或 UNKNOWN。
- HF-FORCE.LIS 焊缝载荷缺失或来源集合不可信。
- MAXBEAMSTRESS.LIS / TMAXBEAMSTRESS.LIS 源集合缺失或对应表错误。
- ANSYS 启动后长时间无输出，或输出文件长时间不增长。

这些问题不允许通过继续放大方钢截面来消除。必须先修建模、载荷、谱、约束、PIP 输出集合或 parser 映射。

## 4. 网页显示候选原因

已落地。

实现位置：

- `apps/api/app/main.py`
- `apps/web/index.html`

页面数据来源：

- `square_section_selection.json`
- `square_section_trial_summary.json`
- `square_section_selection_applied.json`
- `square_section_upgrade_after_ratio_fail.json`

页面展示：

- 已选截面。
- 候选排序策略。
- 相似提资排序提示。
- 早停原因。
- 每个候选的控制比值、方钢比值、运行状态和诊断结论。

## 5. 候选试算超时和输出增长门禁

已落地。

实现位置：

- `core/ansys/runner.py`
- `core/optimizer/square_section_workflow.py`

识别状态：

- timeout
- startup_no_output_timeout
- output_stall_timeout

处理方式：

- 记录到 `ansys_run_audit.json` 和选型 JSON。
- 不能假装候选通过。
- 必要时允许标准截面临时进入正式 job，但最终正式 ANSYS 结果和比值门禁必须通过。

## 6. 提资解析两层结构

已落地。

实现位置：

- `core/intake/intake_excel_reader.py`
- `core/intake/job_input_builder.py`
- `core/intake/tray_load_parser.py`

规则：

- 确定性解析器先提取主体字段。
- 低置信度字段进入审查，不直接写入正式结论。
- 大模型只做候选字段、证据单元格和解释建议。
- 字段校验器确认后才能进入建模和计算。

## 7. 三份命令流仍是审查边界

已落地。

实现位置：

- `core/apdl/standard_command_renderer.py`
- `core/apdl/template_renderer.py`
- `core/ansys/master_macro.py`

正式输出：

- `generated_model.mac`
- `generated_solve.mac`
- `generated_post.mac`
- `run_all.mac`

说明：

- `run_all.mac` 只按顺序调用建模、计算、提取三份命令。
- 不允许大模型直接生成一整份自由 APDL 替代标准命令流。
- 命令流必须能给科室审核。

## 8. 结果提取集合先验和数值门禁

已落地。

实现位置：

- `core/results/result_assembler.py`
- `core/results/lis_parser.py`
- `core/results/figure_collector.py`
- `core/validation/result_validity_gate.py`

规则：

- 每个关键结果必须记录 source_file、source_hash、source_ref、单位和 parser 来源。
- UNKNOWN、全零、缺源文件、关键图片缺失时阻断发布。
- 网页和报告不得把被阻断的结果当成正式结论。

## 9. AI 后台巡检

已落地。

实现位置：

- `core/ai/run_monitor.py`
- `apps/api/app/main.py`
- `apps/web/index.html`

边界：

- AI 可解释运行状态和错误原因。
- AI 可建议修复部署、权限、日志、缺图、UNKNOWN、全零、MT 截断。
- AI 不替代 ANSYS、Excel 和确定性公式。
- AI 连接失败时使用固定工程规则兜底，但兜底结果只能作为质控提示。

## 10. 进度显示不倒退

已落地。

实现位置：

- `core/pipeline/one_click.py`
- `apps/api/app/main.py`
- `apps/web/index.html`

规则：

- 每个 run_id 单独记录进度。
- 同一个 run 的百分比只增不减。
- ANSYS 结束后进入解析、评定、图片、报告注入时，显示阶段变化，不把 100% 回退成 97%。

## 11. 部署包要求

已落地到打包脚本。

实现位置：

- `scripts/package_duxyb_intranet_release.ps1`

部署包必须包含：

- 网页端和 API。
- 最小标准命令流包。
- 模板报告。
- 配置示例。
- 一键安装、启动、更新脚本。
- 安装后桌面图标。

部署包不应包含：

- source_materials 全量原始资料。
- 旧版本部署残留。
- 大量历史 job 输出。
- 本机私有配置。

## 12. 本轮验证项

本轮修改后必须执行：

- 方钢选型单元测试。
- 网页结构单元测试。
- 结果有效性门禁测试。
- 一键进度测试。
- 提资解析测试。
- 硬编码扫描。
- source_materials Git 状态检查。
- 内网部署包重新打包。
