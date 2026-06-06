# Next Actions for Human Review

## 必须人工确认

1. 核对 `docs/formula_traceability.md` 中已实现公式的单元格含义，尤其是材料强度列 D/E 的工程含义。
2. 确认支架梁拉伸+弯曲、压缩+弯曲组合公式的 Excel 单元格和 RCC-M 条款。
3. 确认焊缝评定中等效应力、有效面积、惯性参数和力分量映射关系。
4. 确认机械螺栓、膨胀螺栓的许用值来源、面积取值和组合判据。
5. 审核 APDL 三份模板与标准化命令流/PIP/MAC 的差异，标出必须保留的命令块。
6. 审核 mock LIS 格式是否能覆盖真实 PIP/LIS 输出的字段和单位。
7. 指定最终 Word 报告模板，明确每张表对应 `result.json` 的字段路径。

## 建议下一阶段任务

1. 建立 Excel golden tests：每个已确认公式至少一组输入、Excel 期望值、Python 复刻值。
2. 建立真实样例 job 的解析回归测试：用已有 LIS/Mode/BMP 输出验证 parser。
3. 接入真实反应谱选择模块：支持项目、厂房、区域、标高、阻尼比、方向和谱级别。
4. 接入真实 ANSYS runner：读取 `config/ansys.local.toml`，记录命令行、退出码、stdout/stderr、耗时。
5. 把报告生成从最小模板升级为固定单位模板填充，并增加 docx 内容一致性审计。
6. 增加 API job 状态机，区分 created/rendered/running/parsed/reported/failed。
