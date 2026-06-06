---
name: apdl-pip-template
description: 基于标准化建模命令流、PIP 建模文件和计算 MAC 文件，将 S2 电缆桥架 ANSYS APDL 建模、求解、后处理模板化。
---

# 原则

- 不从零重写建模逻辑。
- 优先复用建模标准化命令流、PIP 和 MAC。
- 所有几何、材料、截面、层数、载荷、谱文件路径来自 input.json。
- 不允许写死 1818、NB、7.5m。

# 输出

- templates/apdl/geometry_s2.mac.j2
- templates/apdl/solve_spectrum.mac.j2
- templates/apdl/post_extract_s2.mac.j2
- jobs/<job_id>/generated_model.mac
- jobs/<job_id>/generated_solve.mac
- jobs/<job_id>/generated_post.mac
- jobs/<job_id>/apdl_audit.json

# 审核项

- 是否定义 BEAM188。
- 是否读取 SECT。
- 是否定义材料。
- 是否有约束。
- 是否有 CP/CPCYC 耦合。
- 是否有模态分析。
- 是否有反应谱分析。
- 是否有结果提取命令。
- 是否存在未替换占位符。
