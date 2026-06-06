---
name: excel-evaluation-replicator
description: 读取电缆桥架结果评定 Excel，提取关键公式、输入单元格、结果单元格、许用值来源，并复刻为确定性 Python 评定函数和 golden tests。
---

# 原则

- Excel 是公式来源，不是不可解释黑盒。
- 能解析的公式翻译为 Python。
- 不能解析的公式标记 TODO_FORMULA_SOURCE_REQUIRED。
- 每个公式必须记录 source_ref：文件名、sheet、单元格、公式文本。

# 输入

- 电缆桥架结果评定-q235材料.xlsx
- 电缆桥架结果评定-06Cr19Ni10材料.xlsx
- 18185NI-LXSJ4120.docx

# 输出

- docs/formula_traceability.md
- core/evaluators/*.py
- data/materials/*.json
- tests/golden/test_excel_formula_replication.py
