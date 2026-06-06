---
name: golden-tests
description: 使用已有 S2 报告、PIP 输出和 Excel 评定结果建立 golden regression tests，保证建模、结果提取、评定公式和报告生成修改后不破坏精度。
---

# 必须测试

- APDL 模板没有未替换占位符。
- 不硬编码 1818/NB/7.5m。
- LIS 解析稳定。
- 公式复刻有 source_ref。
- result.json 能生成。
- report.docx 能生成。
- 报告表格数值与 result.json 一致。
- 结论与最大应力比一致。
