# Report Field Mapping

报告生成由 `core/report/template_mapper.py` 定义字段映射，`core/report/report_audit.py` 审计映射是否存在、图片是否存在、结论是否与最大 ratio 一致。

| Report section | Table / figure | Data source |
| --- | --- | --- |
| 材料参数 | 材料参数表 | `input.json:materials` |
| 结构设计参数 | 结构设计参数 | `input.json:support` |
| 工况 | 工况表 | `input.json:load_cases` |
| 支架评定 | 支架评定表 | `result.json:evaluation_summary` |
| 焊缝评定 | 焊缝评定表 | `result.json:evaluation_summary` |
| 基础载荷 | 基础载荷表 | `result.json:foundation_loads` |
| 螺栓载荷 | 螺栓载荷表 | `result.json:bolt_force_results` |
| 螺栓评定 | 螺栓评定表 | `result.json:evaluation_summary` |
| 模态 | 模态频率表 | `result.json:modal_results` |
| 附录 A | 模态图 | `figures_manifest.json` where `figure_type=modal` |
| 附录 B | 应力图 | `figures_manifest.json` where `figure_type=stress` |
| 结论 | 结论 | `result.json:evaluation_summary` |

审计规则：

- result/input 字段路径必须存在。
- figures manifest 中的 `target_file` 必须存在。
- 任一评定项 `pass_fail=不满足` 时，报告结论必须为“不满足”。
- 表格数值只从 `input.json`、`result.json` 和 `figures_manifest.json` 写入。
