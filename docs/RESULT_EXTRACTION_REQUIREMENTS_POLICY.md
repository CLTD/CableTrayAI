# 结果提取范围判定策略

## 目标

本策略用于防止不同提资按同一套结果清单和同一套图片清单提取。平台必须先判定该提资实际结构对象和确认后的输出范围，再执行结果组装和图片发布。

历史报告章节只用于校准和回归验证，不能作为新提资的一手判据。新提资尚未生成报告，因此不能用“报告有没有附录C”决定是否计算或提取托臂结果。

## 判定规则

1. 钢平台与非钢平台分开判定。
   - 报告正文出现“钢平台”时，`classification = steel_platform`，计算方法按静力法处理。
   - 未出现“钢平台”时，默认 `classification = non_steel_platform`，计算方法按反应谱法处理，除非报告明确写静力法。

2. 新提资按 `analysis_scope.json` 判定。
   - `analysis_method = static`：来自提资/配置明确静力法，或提资文字包含“钢平台”。
   - `analysis_method = response_spectrum`：非钢平台且未明确静力法。
   - S2 且托盘载荷描述包含“单侧/双侧/托盘”时，认定存在托臂、托盘-托臂连接和托臂根部焊缝。
   - 托臂根部焊缝评定和托臂应力云图是两件事：前者只要存在托臂就要评定；后者由方钢截面外边长决定。
   - 方钢截面外边长 `<= 120mm`：`appendix_c_mode = cantilever_stress_cloud`，输出 `TB*`、`TD*` 托臂应力云图。历史资料中 `120*120*6`、`120*120*8`、`120*120*10` 均属于这一类。
   - 方钢截面外边长 `> 120mm`：`appendix_c_mode = weld_evaluation_principle`，不输出 `TB*`、`TD*` 托臂应力云图，附录C走焊缝评定原理。
   - 如果提资 I 列为空、方钢截面尚未选定，则 `analysis_scope.status = needs_square_section_selection`，先跑候选 `*.SECT` 选型，再决定附录C模式。

3. 历史报告校准时，附录图片按章节标题和图号判定，不按文件夹里有什么图片判定。
   - `附录A：模态分析结果` 对应 `MOTAI-1.PNG` 至 `MOTAI-4.PNG`。
   - `附录B：方钢应力图` 对应 `SQ-B*` 和 `SQ-D*` 方钢立柱/方钢构件应力图。
   - 只有出现精确章节 `附录C：托臂应力图` 时，才允许输出 `TB*`、`TD*` 托臂应力图。

4. 非钢平台不等于一定没有托臂云图。
   - 有些非钢平台报告仍包含 `附录C：托臂应力图`，这些报告必须提取托臂应力图。
   - 没有该章节的非钢平台报告，例如清单中 `4120/4142/4150/4151/4152/4249` 这类报告，不得输出托臂应力图。

5. QA 盖章、签字页、公式说明图、焊缝评定原理图不得当作附录应力云图。

6. `result_requirements.json` 必须先于 `result.json` 生成。
   - 批量真实运行流程中先读取对应报告并写入 `result_requirements.json`。
   - `figure_collector` 只根据 `required_figures` 发布图片；没有要求的图片即使存在于 job 目录，也不进入 `figures_manifest.json`。

## 历史报告源冲突处理

历史报告章节可用于比对，但不能覆盖生产规则。按完整方钢截面核对后，当前样例规律为：

- `100*100*6`、`100*100*8`：`附录C：托臂应力图`。
- `120*120*6`、`120*120*8`、`120*120*10`：`附录C：托臂应力图`。
- `>120mm` 的方钢截面：`附录C：焊缝评定原理`。当前历史资料里对应 `140*140*8`、`160*160*8`。

审计文件：

- `docs/SECTION_APPENDIX_RULE_AUDIT.json`
- `docs/SECTION_APPENDIX_RULE_AUDIT.md`

## 审核输出

每个 job 输出：

- `result_requirements.json`
- `figures_manifest.json`
- `square_section_selection.json`

全量报告清单输出：

- `docs/RESULT_EXTRACTION_REQUIREMENTS_INVENTORY.json`

## 命令流审核

发布到结果输出文件夹的审核命令流只保留三份：

1. `generated_model.mac`：建模命令流。
2. `generated_solve.mac`：计算命令流。
3. `generated_post.mac`：结果提取命令流。

`run_all.mac` 只作为内部 ANSYS 批处理入口使用，不作为科室审核命令流发布。
