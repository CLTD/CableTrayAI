---
name: ansys-runner-result-extractor
description: 调用本地 ANSYS 批处理或 mock runner，运行 APDL/PIP，解析 LIS 结果和 BMP/PNG 图片，生成 result_raw.json 和 figures_manifest.json。
---

# 原则

- 真实 ANSYS 路径来自 config/ansys.local.toml。
- 第一阶段支持 mock runner。
- 计算失败保留 job 目录。
- 不删除 out、err、lis、bmp、rst。

# 解析对象

- MAXBEAMSTRESS.LIS
- TMAXBEAMSTRESS.LIS
- JCZH.LIS
- HF-FORCE.LIS
- LS-FORCE.LIS
- Mode.oup
- MOTAI-1.bmp ~ MOTAI-4.bmp
- A/B/D 工况应力图

# 输出

- result_raw.json
- modal_results.json
- beam_stress_results.json
- weld_force_results.json
- bolt_force_results.json
- foundation_loads.json
- figures_manifest.json
- ansys_run_audit.json
