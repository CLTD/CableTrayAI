---
name: spectrum-selector
description: 解析楼层谱 Excel/XLSM，按项目、厂房、区域、标高、阻尼比、SL-1/SL-2、X/Y/Z 方向选择或插值反应谱，并生成 ANSYS 谱命令。
---

# 原则

- 1818 只是样例。
- 必须支持 project_code = 1818 / 2016 / 2026 / 自定义。
- 不写死厂房、区域、标高。
- 支持精确标高匹配和上下标高线性插值。
- 缺谱必须报错，不允许默认取谱。

# 输出

- spectrum_selection.json
- spectrum_points.json
- ansys_spectrum.mac
- spectrum_audit.json

# 审核项

- X/Y/Z 三向是否完整。
- SL-1/SL-2 阻尼比是否正确。
- 插值来源标高是否记录。
- 谱文件 sha256 是否记录。
