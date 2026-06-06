# Web UI AI Contest Design

Date: 2026-05-17

## Scope

This branch is only for the CableTrayAI web interface. It must not weaken the production calculation authority chain:

1. standard APDL/PIP/MAC-derived command streams,
2. real ANSYS output,
3. deterministic/spec formulas,
4. job-local Excel authoritative evaluation when formulas are not fully replicated,
5. historical report comparison as calibration and conflict discovery.

## User Sketch Interpretation

The user-supplied `界面设计.pdf` describes an operator workstation rather than a developer dashboard. The production-facing page must assume the next case is a new intake without historical report data. Therefore the main UI must not show calibration-gate language, historical maximum error, or “production calibration passed” status.

The optimized layout keeps the sketch intent:

- top command area: show the discovered ANSYS executable, choose the result output folder, and start calculation for selected rows;
- top work area: keep intake upload, response-spectrum upload, and the reserved template-injection entry on one full-width row so the command/model review area is not squeezed;
- merge report-number binding into the parsed intake task list so row selection, calculation selection, and later report-number replacement happen in one place;
- keep the current row selector, checked calculation row, and report/order identity inputs synchronized. A single selected row must always be obvious to the operator; multi-select is allowed but the current review row is still shown explicitly.
- after selecting the intake file, parse it automatically instead of requiring a separate manual parsing step;
- allow the operator to select one or more parsed intake rows for calculation;
- allow the operator to choose a primary row for detail viewing and manually bind a temporary intake/order id or later report number;
- open the page with ANSYS auto-discovery already performed when a local config exists;
- select the result output folder through the local folder dialog where available, with a manual text fallback for browser security limitations;
- center top: show the current task as one compact task strip, including id, factory/area, elevation, method, support type, square section, tray load, equivalent density, material policy, and output folder;
- center middle: show a rotatable 3D command-stream mesh preview interpreted from `generated_model.mac` APDL variables, `*DO/*IF/*ELSEIF` blocks, and K/L commands, plus the three auditable command streams side by side; when generated commands are not available the canvas shows a neutral 3D axis/grid waiting state, not a fake engineering result;
- result review: open a separate page organized like report Chapter 6 and appendices A/B/C, including evaluation tables, load tables, modal figures, stress figures, command streams, and a manual error memo so the operator homepage stays focused;
- bottom reserved tool: keep the “result file injection into template” entry visible but disabled until the UI layout is finalized.

## Implemented Page Structure

`apps/web/index.html` is now organized as:

- 顶部命令区: ANSYS auto-discovery, result output folder selection, default output restore, and selected-row calculation.
- `新提资入口`: intake upload and spectrum upload only; selecting the intake automatically uploads and parses it.
- `提资单号 / 报告号`: choose a parsed row, select one or more rows for calculation, and bind a temporary order id or later report number.
- `提资解析行`: automatically displays parsed rows after file selection.
- `计算进度`: replaces the previous current-task detail cards. It shows queued/running/stopped/completed state, current stage, percent, and a stop button.
- `结果文件注入模板`: reserved disabled feature. It does not read files, call APIs, or write output.
- `当前任务`: selected intake summary as a compact task strip only; no historical validation statistics.
- `ANSYS 模型与命令流核查`: a full-width command-stream review section. The left canvas parses APDL parameters, common loop/branch blocks, and real K/L entities from `generated_model.mac` when available, then renders a rotatable 3D line model. This is a browser-side command audit preview, not an embedded ANSYS graphics window. The right panel shows exactly three command streams: modeling, calculation, result extraction.
- The 3D command preview now classifies geometry by command-derived spatial logic: square support/rectangular tube, cantilever/channel arm, tray longitudinal member, and connector/short brace. It uses distinct colors, thicker member strokes, section glyphs, and opening-direction arrows for channel/tray members so reviewers can visually distinguish support columns, arms, tray members, and likely section orientation. The arrow is an audit cue derived from the command preview; authoritative orientation remains the APDL/SECT definition and ANSYS output.
- The preview was further upgraded from line display to a shaded member view: larger canvas, depth-ordered members, shadows/end caps, square-tube and channel section symbols, optional section/opening/node-label toggles, axis triad, and an on-canvas model summary. This remains dependency-free for offline deployment.
- `结果核查`: a compact launch panel for `apps/web/review.html`; the full result audit no longer crowds the homepage.
- `apps/web/review.html`: a dedicated result-review page with tabs for `第六章 结果评定`, `附录A 模态分析`, `附录B 方钢应力图`, `附录C 托臂/焊缝`, `三份命令流`, and `错误备忘`. Formula/source columns are intentionally hidden from the operator table view; traceability remains in JSON and backend audits.
- The `第六章 结果评定` tab now uses report-style merged-condition tables: `工况 / 应力类型 / 计算值(MPa) / 许用值(MPa) / 应力比`. It builds the support and cantilever stress tables from `beam_stress_results` plus confirmed material allowables, while the backend validity gate still blocks all-zero, missing-figure, or unknown-node outputs.

## Contest Fit

CableTrayAI should be presented as an AI-assisted engineering design and quality-control platform for the `人工智能工程设计应用` direction:

- AI-assisted intake parsing;
- AI-assisted source traceability and missing-field review;
- AI-assisted spectrum/configuration checks;
- AI-assisted command-stream audit explanation;
- AI-assisted result anomaly diagnosis;
- AI-assisted economical square-section suggestions;
- AI-assisted source/report conflict classification.

The AI layer remains advisory and auditing-oriented. It must not replace ANSYS, APDL source logic, Excel evaluation, or confirmed formulas.

## Online References Used

Online references are implementation aids only.

| Reference | Adopted idea | Affected area | Mechanical authority impact |
| --- | --- | --- | --- |
| [PyVista documentation](https://docs.pyvista.org/) | Reserve a future engineering mesh visualization area that can later consume node/element connectivity. | Mesh-preview layout and roadmap | None. Current values still come from local ANSYS outputs. |
| [Apache ECharts](https://echarts.apache.org/en/index.html) | Use clear data-to-visual mapping for comparison envelopes and gate charts. | Browser-side SVG envelope chart design | None. Charts visualize local JSON; they do not generate results. |
| [Ant Design Data Entry](https://ant.design/docs/spec/data-entry/) | File upload and data-entry hints should be explicit and context-rich. | Intake/spectrum/result-folder input layout | None. It affects UI structure only. |
| [Ant Design Data List](https://ant.design/docs/spec/data-list/) | Data-dense engineering rows should support list/table browsing and detail switching. | Parsed-intake multi-select table plus current-row details | None. It affects navigation only. |
| [Microsoft Power Apps modern Fluent design](https://learn.microsoft.com/en-us/power-apps/user/modern-fluent-design) | Enterprise apps benefit from a command area, grid/detail pages, and visual separation of sections. | Workbench page structure and spacing | None. It affects presentation only. |

No external frontend dependency is added in this branch. The page uses native HTML/CSS/SVG so the unit can keep the offline deployment path simple.

## Deferred Feature

The result-file injection/template-writing workflow is intentionally not implemented. The interface reserves its position so that a later backend implementation can be added without changing the approved page layout.

## Removed From Main Production UI

The historical report comparison and 1% calibration gate remain development/audit assets, but they are not part of the new-intake operator homepage. A new intake usually has no validated report or manual command stream yet, so showing “calibration passed” on the primary page would misrepresent the production workflow.
