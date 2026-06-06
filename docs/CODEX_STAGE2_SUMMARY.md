# Codex Stage 2 Summary

阶段二把阶段一 mock 闭环升级为真实资料可校核框架。

## Completed Modules

- APDL/PIP/MAC 源差异审核：`core/apdl/source_diff.py`
- PIP 输出清单：`core/results/pip_output_manifest.py`
- LIS 解析增强：`core/results/lis_parser.py`
- 图片收集和 BMP 转 PNG：`core/results/figure_collector.py`
- 公式注册与 golden tests：`core/evaluators/formula_registry.py`
- 反应谱选择器：`core/spectra/*.py`
- 报告字段映射和一致性审计：`core/report/template_mapper.py`
- API job 状态机：`core/schemas/job_models.py`、`core/audit/job_state.py`
- 阶段二自审脚本：`scripts/stage2_self_check.ps1`

## Generated Documentation

- `docs/APDL_TEMPLATE_GAP_REPORT.md`
- `docs/APDL_SOURCE_TRACEABILITY.md`
- `docs/PIP_OUTPUT_MANIFEST.md`
- `docs/formula_traceability.md`
- `docs/FORMULA_CONFIRMATION_CHECKLIST.md`
- `docs/SPECTRUM_SELECTOR_DESIGN.md`
- `docs/REPORT_FIELD_MAPPING.md`
- `docs/STAGE2_REMAINING_RISKS.md`
- `docs/STAGE2_TEST_REPORT.md`

## Verification

```powershell
pytest -q
```

Current result: `19 passed`.

```powershell
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

Current result: no matches.

## Notes

- `source_materials` remains read-only.
- Real ANSYS execution is still not invoked by default.
- Unconfirmed formulas remain marked with `TODO_FORMULA_SOURCE_REQUIRED`.
