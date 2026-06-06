# Result Table Mapping Policy

## Core Rule

报告对比和网页展示不得按“哪个数接近就用哪个”。每一行必须按以下逻辑映射：

1. 报告表标题和章节；
2. APDL/PIP 后处理选择集；
3. 输出文件名；
4. 评定公式或系数来源。

无法按这个逻辑映射时，结果必须失败或等待人工确认，不允许换文件凑数。

## Current S2 Mapping

| Report / UI section | Result source | Command selection | Rule |
| --- | --- | --- | --- |
| 支架方钢应力评定 | `SQUAREBEAMSTRESS.LIS` | `TYPE=1` square support narrowed to `SEC=1` | 方钢立柱/方钢构件使用独立 section-1 导出，不能从混合梁结果中按数值挑选。 |
| 托臂应力评定 | `TMAXBEAMSTRESS.LIS` | parameterized tray-arm type family: `10*I+2`, `10*I+3`, `200*I+2`, `200*I+3` | 参数化模型中 `TYPE=1` 是方钢立柱/方钢构件，托臂必须按建模 `LATT` 的实际类型族导出。 |
| 托臂根部焊缝评定 | `HF-FORCE.LIS` plus weld evaluator | source PIP weld/root extraction branch | 方钢外边长 `>120 mm` 时走焊缝评定原理，不发布 TB/TD 托臂云图。 |
| 拉弯组合 / 压弯组合 | mapped component stress rows | same component source as the report table | 许用值为报告/Excel 明确的 `1.0` 比值准则，不能另算许用应力。 |
| 支架基础载荷 | `JCZH.LIS` | source PIP foundation reaction export | 三个工况映射 `FX/FY/FZ/MX/MY/MZ`；节点不得为 `UNKNOWN`。 |
| 支架连接螺栓载荷 | `LS-FORCE.LIS` and audited node export | source PIP tray-arm connection export | 两个地震工况映射 `FX/FY/FZ/MX/MY/MZ`；全零拓扑行不得显示。 |
| 支架螺栓应力评定 | bolt evaluator from connection loads | same tray-arm connection source | 拉伸、剪切和组合比按已确认公式或 Excel 权威结果输出。 |
| 模态频率 | `Mode.oup` | modal solve output | 按模态阶次比较和展示。 |
| 附录A 模态图 | `MOTAI-1.PNG` to `MOTAI-4.PNG` | ANSYS image export | 必须是非空白真实 ANSYS 图。 |
| 附录B 方钢应力图 | `SQ-B*.PNG`, `SQ-D*.PNG` | section-1 square support image export | 必须与方钢立柱/方钢构件选择集一致。 |
| 附录C 托臂应力图 | `TB*.PNG`, `TD*.PNG` | tray-arm type family image export | 仅方钢外边长 `<=120 mm` 需要。 |
| 附录C 焊缝评定原理 | no TB/TD image requirement | weld-principle branch | 仅方钢外边长 `>120 mm` 需要。 |

## Selector Alignment

The original source PIP contains the historical `TMAXBEAMSTRESS` selector:

```apdl
ALLSEL
ESEL,S,TYPE,,1
ESEL,U,SEC,,1
```

For the generated parameterized model this can become an empty set, because `TYPE=1` is the square support. CableTrayAI now records this source difference in `postprocessor_alignment_audit.json` and aligns only that selector to the actual tray-arm element types assigned by `generated_model.mac`:

```apdl
ESEL,NONE
*DO,I,1,qiancengshu,1
ESEL,A,TYPE,,10*I+2
ESEL,A,TYPE,,10*I+3
*ENDDO
*DO,I,1,houcengshu,1
ESEL,A,TYPE,,200*I+2
ESEL,A,TYPE,,200*I+3
*ENDDO
```

`result_source_map.json` must show `TMAXBEAMSTRESS.LIS` as `parameterized_cantilever_arm_type_family`. If it does not, the job is not publishable.

## Hard Failure Rules

- Stress or load rows all zero: fail.
- Rows with no parseable numeric value: fail.
- Foundation or connection nodes shown as `UNKNOWN`: fail.
- Required figures missing or blank-like: fail.
- Required output source map missing: fail.
- Report comparison conflicts are calibration findings, not a reason to substitute a different runtime source.
