# Spectrum Selector Design

阶段二新增 `core/spectra` 模块，当前采用配置驱动优先、自动表头识别兜底的解析策略。

## Input Table

第一版支持扁平表格，表头字段如下：

| Field | Meaning |
| --- | --- |
| project_code | 项目号，来自输入，不在代码中写死。 |
| building | 厂房。 |
| area | 区域。 |
| elevation | 标高。 |
| damping | 阻尼比。 |
| level | SL-1 / SL-2。 |
| direction | X / Y / Z。 |
| frequency_hz | 频率点。 |
| acceleration_g | 谱加速度。 |

## Selection Rules

1. 先按 `project_code/building/area/level/direction/damping` 过滤。
2. 若目标标高存在，直接返回该标高谱点。
3. 若目标标高不存在，寻找上下相邻标高并按频率点线性插值。
4. 缺少匹配谱或上下标高时抛出清晰错误。
5. 输出谱文件 sha256 到 `spectrum_selection.json` 和 `spectrum_audit.json`。

## Outputs

- `spectrum_selection.json`
- `spectrum_points.json`
- `ansys_spectrum.mac`
- `spectrum_audit.json`

真实 XLSM 如果采用复杂多 sheet 或合并单元格格式，下一阶段应补充显式配置，例如：

```json
{
  "sheet": "Spectrum",
  "header_row": 3,
  "columns": {
    "project_code": "A",
    "building": "B",
    "area": "C",
    "elevation": "D",
    "damping": "E",
    "level": "F",
    "direction": "G",
    "frequency_hz": "H",
    "acceleration_g": "I"
  }
}
```
