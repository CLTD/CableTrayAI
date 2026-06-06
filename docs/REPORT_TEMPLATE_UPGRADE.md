# Report Template Upgrade

Stage 3 adds a formal S2 report structure and a template file:

```text
templates/report/s2_report_template.docx
```

The generated report follows these headings:

1. 概述
2. 结构说明
2.1 材料参数
2.2 结构设计参数
3. 工况
3.1 载荷工况
3.2 工况组合
4. 规范要求
5. 计算方法、程序和计算模型
6. 结果评定
6.1 支架的评定
6.2 焊缝的评定
6.3 基础载荷
6.4 螺栓的评定
7. 结论
参考资料
附录A 模态分析结果
附录B 支架应力图
附录C 焊缝评定原理

All tables are populated from `input.json` and `result.json`. All images are populated from `figures_manifest.json`.

The report audit now checks:

- minimum table count;
- required heading presence;
- figure existence;
- conclusion consistency with maximum ratio and unconfirmed formulas;
- source references included in the audit output.
