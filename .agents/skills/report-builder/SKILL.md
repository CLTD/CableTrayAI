---
name: report-builder
description: 根据 result.json、evaluation_summary.json 和 figures_manifest.json，用固定 Word 模板生成电缆桥架抗震分析报告，并执行格式和数值一致性审核。
---

# 原则

- 报告数值只来自 result.json。
- 图片只来自 figures_manifest.json。
- 结论只来自 evaluation_summary.json。
- 不允许自由排版。
- 表格和图片尺寸固定。

# 输出

- report.docx
- report_audit.json

# 报告内容

- 概述
- 结构说明
- 工况
- 规范要求
- 计算方法、程序和计算模型
- 结果评定
- 结论
- 参考资料
- 附录 A 模态分析结果
- 附录 B 支架应力图
- 附录 C 焊缝评定原理
