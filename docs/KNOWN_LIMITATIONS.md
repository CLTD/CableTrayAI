# Known Limitations

## 计算能力限制

- Stage 1 不执行真实 ANSYS，只生成 deterministic mock 输出。
- APDL 模板是 S2 方钢托臂骨架，不是完整生产命令流。
- 反应谱没有从真实 XLSM 中解析，模板内谱点仅用于占位。
- PIP/LIS parser 当前支持 Stage 1 mock CSV-like LIS；真实 ANSYS/PIP 文本格式需要下一阶段适配。

## 评定限制

- 已实现的公式只覆盖 Excel 中可明确识别的基础比值、螺栓拉剪平方和、焊缝有效焊喉。
- 支架梁组合评定、完整焊缝等效应力、膨胀螺栓评定仍标记为 `TODO_FORMULA_SOURCE_REQUIRED`。
- 许用值来源需要人工确认后才能作为生产结论使用。
- AI 审核只输出建议和风险，不替代确定性计算结论。

## 报告限制

- `report.docx` 是固定最小骨架，不是最终生产版报告格式。
- 报告审计当前确认报告由 `result.json`、`evaluation_summary.json`、`figures_manifest.json` 生成，并记录 hash；尚未逐字段反解 docx 内容。
- 图片为 mock 占位图，不代表真实模态图或应力云图。

## 部署限制

- API 没有鉴权、队列、并发锁和持久化数据库。
- job 状态由文件存在性隐含表达，尚无正式状态机。
- 真实 ANSYS 路径只在示例配置中给出，生产环境应复制为 `config/ansys.local.toml` 并按本机修改。

## 资料限制

- `source_materials` 当前只读扫描；未建立逐段资料语义索引。
- `docs/source_inventory.json` 记录文件 hash、大小、扩展名、修改时间和文本编码，但不代表资料内容已经完成审核。
