---
name: rccm-evaluator
description: 实现 RCC-M 支架梁单元、机械螺栓、膨胀螺栓、焊缝评定的确定性计算模块，输出应力比、结论和公式溯源。
---

# 必须实现

- 梁单元拉伸评定。
- 梁单元剪切评定。
- 梁单元压缩评定。
- 梁单元弯曲评定。
- 拉伸 + 弯曲组合。
- 压缩 + 弯曲组合。
- 机械螺栓拉伸、剪切、拉剪组合。
- 膨胀螺栓拉力、剪力、拉剪组合。
- 焊缝有效焊喉、剪应力、等效应力。

# 输出

- support_eval.json
- bolt_eval.json
- expansion_bolt_eval.json
- weld_eval.json
- evaluation_summary.json

# 禁止

- 禁止编造许用应力。
- 禁止没有 source_ref 的公式。
- 禁止忽略单位。
