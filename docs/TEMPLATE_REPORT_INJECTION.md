# 模板报告注入

## 目标

基于真实 ANSYS 结果提取、评定结果和图片清单，把数据注入科室提供的 Word 模板副本中。模板正文、章节顺序、表格结构和样式不重排。

## 模板选择

- 钢平台或静力法任务：`templates/report/steel_platform_report_template.docx`
- 非钢平台或反应谱法任务：`templates/report/non_steel_platform_report_template.docx`

判定来自 `input.json` 的 `metadata.analysis_method` 和提资生根层信息。

## 已注入内容

- `表3-1`：按所选谱文件、厂房/区域和标高替换反应谱表头与谱值。
- `图5.1`、`图5.2`：替换为当前 job 的 ANSYS 模型/托臂相关图片。
- 第六章评定表：支架/方钢/托臂应力评定、基础载荷、连接螺栓载荷、模态频率。
- 附录图片：模态图、方钢应力图，以及钢平台模板中的托臂应力图。

## 模板副本自适应

- 原始模板文件只读使用，不直接修改。
- 注入时只修改 job 输出目录中的模板副本。
- 若模板副本缺少当前任务必须出现的图号位置，例如 `图5.1`、`图5.2`、`图A-*`、`图B-*` 或 `图C-*`，程序会在副本中补充图号和图片槽位，再插入对应图片。
- 每个自动补充项都会写入 `template_report_audit.json` 的 `caption_added_to_template_copy=true`，方便审核人员知道模板副本哪里被补齐。
- 附录 C 必须按当前方钢截面分支选择：
  - 方钢外边长 `<=120 mm`：补齐并注入托臂应力图；
  - 方钢外边长 `>120 mm`：切换为焊缝评定原理，不注入托臂云图。

## 输出

调用：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/jobs/<job_id>/template-report
```

输出：

- `jobs/<job_id>/<报告号>.docx`
- `jobs/<job_id>/report.docx`，用于兼容既有下载/审计入口
- `jobs/<job_id>/template_report_audit.json`

## 边界

- 缺少谱文件、图片或结果字段时，不伪造数据，只在 `template_report_audit.json` 记录 warning。
- 只有图号/图片槽位允许在模板副本里补齐；评定数值、载荷、频率和结论仍必须来自 `result.json`、`evaluation_summary.json` 或权威 Excel 评定结果。
- AI 不能替代模板注入和评定结论，只能辅助审核缺源、错误节点和格式风险。

## 2026-05-18 Audit Result

- Audit file: `docs/precision_gate/template_report_injection_20_case_audit.json`.
- The latest 17 numerically passed intake-as-new validation cases all produced template reports with `status=pass`.
- Required weld and bolt stress rows are filled from deterministic formulas and parsed ANSYS resultants:
  - bolt force-to-stress source: `电缆桥架结果评定-q235材料.xlsx:螺栓!E51:E57`;
  - weld force-to-stress source: `电缆桥架结果评定-q235材料.xlsx:异型钢焊缝评定!C39:K41`.
- Sections outside the analysis scope are marked `not_applicable`, for example cantilever-root weld tables when the square-section/appendix branch does not require weld-principle evaluation.
