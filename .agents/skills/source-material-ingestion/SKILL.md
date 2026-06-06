---
name: source-material-ingestion
description: 扫描和登记电缆桥架原始资料，包括 APDL、PIP、MAC、SECT、Excel、XLSM、PDF、DOCX，生成 source_inventory.json 和 source_ref 溯源索引。
---

# 工作要求

1. 扫描 source_materials/model_commands 和 source_materials/learning_docs。
2. 计算文件 sha256、大小、扩展名、修改时间。
3. 对 txt、mac、pip、sect 尝试 UTF-8、GBK、GB2312 编码读取。
4. 输出 docs/source_inventory.json。
5. 原始资料只读，不得修改。
6. 缺关键文件时输出 docs/source_warnings.json。

# 关键文件

- 建模标准化命令流.txt
- 01 双侧同类型电缆桥架-方钢托臂.PIP
- 02 计算用命令流.mac
- 导出数据-S2.PIP
- 100-100-8.SECT
- 电缆桥架结果评定-q235材料.xlsx
- 电缆桥架结果评定-06Cr19Ni10材料.xlsx
- 楼层谱1818 ANSYS格式 标高线性.xlsm
- 18185NI-LXSJ4120.docx
- HDLXSC-25A5-02-03 支架、设备抗震分析工作手册.docx
