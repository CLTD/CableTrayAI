# CableTrayAI Stage 1 Summary

## 1. 已完成模块

- 资料扫描与索引：`core/intake/source_inventory.py`
- 输入/结果数据模型：`core/schemas/input_models.py`、`core/schemas/result_models.py`
- APDL 模板渲染与审计：`core/apdl/template_renderer.py`、`core/apdl/audit.py`、`templates/apdl/*.j2`
- ANSYS mock runner：`core/ansys/runner.py`
- LIS/Mode 解析、图片收集、result.json 组装：`core/results/*.py`
- RCC-M 评定骨架：`core/evaluators/materials.py`、`support_beam.py`、`bolt.py`、`weld.py`、`summary.py`
- Excel 公式溯源：`core/evaluators/excel_trace.py`、`docs/formula_traceability.md`
- Word 报告生成与审计：`core/report/docx_builder.py`、`core/report/report_audit.py`
- FastAPI 最小接口：`apps/api/app/main.py`
- pytest 单元/集成测试：`tests/unit/*.py`、`tests/integration/test_mock_job_flow.py`

## 2. 已创建/更新文件列表

- `.gitignore`
- `pyproject.toml`
- `apps/api/app/main.py`
- `core/intake/source_inventory.py`
- `core/schemas/input_models.py`
- `core/schemas/result_models.py`
- `core/apdl/audit.py`
- `core/apdl/template_renderer.py`
- `core/ansys/runner.py`
- `core/results/lis_parser.py`
- `core/results/figure_collector.py`
- `core/results/result_assembler.py`
- `core/evaluators/materials.py`
- `core/evaluators/support_beam.py`
- `core/evaluators/bolt.py`
- `core/evaluators/weld.py`
- `core/evaluators/summary.py`
- `core/evaluators/excel_trace.py`
- `core/report/docx_builder.py`
- `core/report/report_audit.py`
- `templates/apdl/geometry_s2.mac.j2`
- `templates/apdl/solve_spectrum.mac.j2`
- `templates/apdl/post_extract_s2.mac.j2`
- `tests/conftest.py`
- `tests/unit/test_source_inventory.py`
- `tests/unit/test_apdl_renderer.py`
- `tests/unit/test_lis_parser.py`
- `tests/unit/test_evaluator_shapes.py`
- `tests/integration/test_mock_job_flow.py`
- `docs/source_inventory.json`
- `docs/source_warnings.json`
- `docs/formula_traceability.md`
- `docs/CODEX_STAGE1_SUMMARY.md`
- `docs/NEXT_ACTIONS_FOR_HUMAN_REVIEW.md`
- `docs/KNOWN_LIMITATIONS.md`

同时生成了一个示例闭环 job：`jobs/stage1_mock_demo/`，包含 `input.json`、三份 APDL、mock LIS/Mode/图片、`result_raw.json`、`result.json`、`evaluation_summary.json`、`audit_comments.json`、`report.docx` 和 `report_audit.json`。

## 3. 如何运行测试

```powershell
pytest -q
```

当前结果：`7 passed`。

## 4. 如何启动 API

```powershell
uvicorn apps.api.app.main:app --reload
```

接口包括：

- `GET /`
- `POST /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/render-apdl`
- `POST /jobs/{job_id}/run-mock`
- `GET /jobs/{job_id}/result`
- `POST /jobs/{job_id}/report`
- `GET /jobs/{job_id}/audit`

## 5. 已实现公式

- 材料正应力许用值：Excel `应力评定!G2` 的 `MIN(0.45*E2,0.37*D2)` 模式，在材料强度输入明确时可计算。
- 材料剪应力许用值：Excel `应力评定!J2` 的 `MIN(0.4*E2,0.33*D2)` 模式，在材料强度输入明确时可计算。
- 支架梁直接应力比：采用 Excel 应力评定表中“计算值/许用值”的比值模式。
- 机械螺栓拉剪组合：采用 Excel `螺栓!E57` 模式，即拉应力比平方加剪应力比平方。
- 焊缝有效焊喉：采用 Excel `异型钢焊缝评定!J30` 模式，`weld_size * sqrt(2) / 2`。

## 6. 需要人工确认的公式

- 支架梁拉伸+弯曲组合。
- 支架梁压缩+弯曲组合。
- 焊缝等效应力完整组合细则。
- 膨胀螺栓评定。
- Excel 中含 `OFFSET`、`MATCH` 等动态引用公式的确定性复刻，详见 `docs/formula_traceability.md` 的 Manual Confirmation List。

## 7. 仍然是 mock 的地方

- ANSYS 批处理执行仍为 mock runner。
- LIS、Mode.oup 和 BMP 图片由 mock runner 生成。
- 反应谱点在 APDL solve 模板中是占位骨架，尚未接入真实谱选择/插值模块。
- Word 报告为固定最小模板骨架，还不是最终单位报告模板。

## 8. 下一阶段开发建议

- 将谱选择模块接入真实 XLSM 解析，输出 `spectrum_selection.json`、`spectrum_points.json` 和 `ansys_spectrum.mac`。
- 用 Excel golden tests 锁定已确认公式，逐步替换 `TODO_FORMULA_SOURCE_REQUIRED`。
- 接入真实 ANSYS runner，并保留失败 job 的 out/err/lis/rst/bmp 文件。
- 将 `report.docx` 替换为单位固定模板填充方式，并增加报告数值反查测试。
- 增加 source_ref 索引到报告每张表的字段级追溯。

## 9. 硬编码检查

已运行核心代码检查：

```powershell
rg --pcre2 -n "1818|7\.5m|(?<![A-Za-z])NB(?![A-Za-z])" core apps templates
```

结果：未发现匹配。`source_materials` 原始资料和 `docs/source_inventory.json` 中会自然出现样例文件名，这不是核心逻辑硬编码。

## 10. 原始资料修改检查

本阶段对 `source_materials` 只读扫描，未写入、删除或覆盖原始资料。生成物写入 `docs/`、`templates/`、`core/`、`apps/`、`tests/` 和 `jobs/stage1_mock_demo/`。
