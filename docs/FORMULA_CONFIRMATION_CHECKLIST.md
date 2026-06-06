# Formula Confirmation Checklist

阶段二已经把可确认的公式放入 `core/evaluators/formula_registry.py`，并为这些公式建立 golden tests。以下项目仍不能作为生产评定结论使用，必须由人工从 Excel、报告或规范条文中确认。

| Formula id | Current status | Required confirmation |
| --- | --- | --- |
| support_tension_bending_combination | TODO | 确认支架梁拉伸 + 弯曲组合公式、适用工况和许用值来源。 |
| support_compression_bending_combination | TODO | 确认支架梁压缩 + 弯曲组合公式、稳定性参数和许用值来源。 |
| weld_equivalent_stress | TODO | 确认焊缝剪应力、法向应力和等效应力组合方式。 |
| expansion_bolt_combination | TODO | 确认膨胀螺栓拉剪组合公式和许用载荷来源。 |

已建立 golden tests 的公式：

- `material_allowable_normal`
- `material_allowable_shear`
- `direct_stress_ratio`
- `bolt_tension_shear_combination`
- `weld_effective_throat`

原则：未确认公式只能输出 `TODO_FORMULA_SOURCE_REQUIRED`，不能编造。

Stage 3 update:

- `formula_status=confirmed` is emitted for confirmed formulas.
- `formula_status=unconfirmed_todo` is emitted for unresolved formulas.
- `evaluation_summary.json` does not treat unresolved formulas as final passed checks.
- Candidate source locations are listed in `docs/FORMULA_SOURCE_CANDIDATES.md`.
