# 2026-05-26 MT、压缩许用、4140 层数、焊缝等效应力和静力修正闭环

## 1. MT 取值规则

- 计算命令流中的 `MT` 是求解前必须指定的模态阶数，不能根据已经生成的 `Mode.oup` 倒推后再假装用于本次求解。
- 后处理校核规则：读取 `Mode.oup` 中 `FREQUENCY (HERTZ)` 对应的模态频率，确认最后一阶频率已经超过 50 Hz；若超过 50 Hz，则记录“最后一个大于 50 Hz 的频率行对应 MODE”为覆盖校核值。
- 如果所有模态频率均不大于 50 Hz，则不允许默认为最后一阶；结果有效性门禁标记为 `insufficient_modes_below_50hz`，需要提高求解阶数后重新运行。
- 当前经验初值为 `MT = max(15 * 托盘总层数, 已审源命令流 MT, 默认下限)`；源命令流中的 `MT` 作为下限之一，不能把低于提资几何规则的源 MT 直接保留下来。运行后再用 `Mode.oup` 检查是否覆盖 50 Hz。
- `18185NI-LXSJ4140/raw_results/Mode.oup` 当前仅导出了 10 阶，最大频率约 4.5076 Hz，因此本次输出没有覆盖 50 Hz，需要提高模态阶数或重新生成输出。

## 2. 压缩应力许用值来源

- 方钢截面 A、I 来自结果评定 Excel 的 `许用应力` 表，不再使用固定压缩许用值替代。
- 按当前方钢截面和支架长度 L 计算 `KL/R`，再按 Excel `应力评定` 中方程 4 / 方程 5 判断压缩应力极限。
- 结果输出带 `source_ref`，包含截面 A/I 单元格、L、KL/R、Cc 和采用的方程编号。

## 3. 18185NI-LXSJ4140 层数解析

- `18185NI-LXSJ4140` 为双侧 2+2 层，两侧均为 2 层，不存在第 3 层。
- 已修正提资托盘载荷解析：当表头类似 `双侧 2+2 层，500mm 托盘` 且后续已经逐条给出层信息时，表头里的 `500mm 托盘` 不再被误识别为额外一层。
- 已生成过的旧 job 仍需重新解析/重生成 input 和命令流后才会反映该修正。

## 4. <=120*120*10 方钢焊缝评定

- 方钢截面小于等于 `120*120*10` 时，托臂根部焊缝评定采用等效应力方式。
- 等效应力表格必须输出，等效应力系数固定为 `0.526`，来源为既有结果评定 Excel 的等效应力单元格逻辑。
- 该规则不取消托臂应力云图要求；图表输出仍按报告章节/图号映射。

## 5. 静力修正

- 计算文件必须写入静力修正参数。
- `paox/paoy/paoz/pasx/pasy/pasz` 取所选反应谱在 100 Hz 处的加速度，不取负号，并换算为 `m/s^2`。
- 输出 JSON 记录 `static_correction_frequency_hz=100.0` 和 `static_correction_sign=1.0`，便于审核。

## 验证

- 已增加并通过单元测试覆盖：
  - MT cutoff 解析；
  - 4140 2+2 层提资解析；
  - 压缩许用方程 4 / 方程 5；
  - 100 Hz 无负号静力修正；
  - <=120 方钢根部焊缝等效应力规则。
- `source_materials` 未修改。

## 18185NI-LXSJ4140 实例复核

- 已用 `jobs/18185NI-LXSJ4140` 重新解析提资、重生成三份命令流，并写入 `issue_fix_verification_20260526.json`。
- 层数复核：`generated_model.mac` 中 `senum=2`、`senum1=2`，`input.json` 中托盘层为前侧 2 层、后侧 2 层，无第三层。
- 静力修正复核：`ansys_zpa_parameters.mac` 已写入 100 Hz 反应谱加速度正值，`static_acceleration_coefficients.json` 中 `coefficient_source=frequency_100hz` 且 `static_correction_sign=1.0`。
- 压缩许用复核：`evaluation_summary.json` 的 `support_compression` 项已带 `许用应力` 表、L、KL/R、Cc 和方程 4/5 的 `source_ref`。
- 焊缝等效应力复核：`analysis_scope.json` 中 `cantilever_root_weld_equivalent_eval=true`，`cantilever_root_weld_equivalent_coefficient=0.526`，并要求输出等效应力表。
- 当前 `result_validation.json` 仍为 `fail`，原因是实际输出不完整：`HF-FORCE.LIS` 缺失、`Mode.oup` 最大频率仍小于 50 Hz、`TBMODEL.PNG` 缺失。该阻断是正确行为，不能把当前结果作为正式结论。
