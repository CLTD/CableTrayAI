# 操作界面简化说明

网页端面向后续新提资的一键计算，不再把开发校准、历史报告比对和调试字段暴露给普通操作流程。

## 主界面保留

- 上传提资 Excel。
- 上传或选择对应项目反应谱文件。
- 选择结果输出根目录。
- 自动查找 ANSYS。
- 勾选一个或多个提资任务并计算。
- 查看计算进度、三份命令流、结果核查、附录图片和输出文件。

## 提资任务列表

任务列表只保留主体字段：

- 计算勾选；
- 序号；
- 综合编号：有报告号时显示报告号，没有报告号时显示提资单号或临时批次；
- 支架类型；
- 分析方法；
- 厂房；
- 标高；
- 方钢截面。

支架号、报告号/提资号分列、调试路径等非主体字段不再放进任务列表，避免页面过杂。

## 厂房和标高

提资解析后会自动填入当前行的厂房和标高。反应谱文件上传后，页面在下拉框中列出当前项目可用的厂房/谱表和标高，操作人员可以选择候选值定位到对应提资行。

如果一个反应谱工作簿同时包含多个项目的谱表，例如 `*_1916` 和 `*_1818`，下拉框必须按当前提资项目号过滤。1818 提资只显示 `*_1818` 谱表，1916 提资只显示 `*_1916` 谱表；不能把其他项目的谱表混进当前提资。

如果谱文件不是标准分段谱格式，页面会先做通用预览，只列出可能的厂房和标高；真实 ANSYS 运行仍需要谱配置确认，不能把预览当作最终谱选择依据。

## 方钢截面

如果提资给出了方钢截面，界面直接显示该截面。如果提资没有给出，界面显示“经验拟选，计算后优化”。后续计算流程应先按经验截面建模，再通过抗震计算寻找满足 `ratio < 1.0` 且最接近 1 的经济截面。

## 后端保留但不放主界面

- 历史报告基准比对；
- 真实输出目录导入；
- Excel 权威评定调试；
- 单 job 分步 preflight / dry-run / real-run；
- 报告模板注入审计。

这些能力用于开发验证、公式锁定和科室审核，不应要求普通操作人员逐项理解。

## 2026-05-18 Current UI Rule

- The task table keeps only: calculate checkbox, detail button, combined identity, method, building, elevation, and square-section status.
- The combined identity displays the report number when present; otherwise it displays the intake/order/provisional identity.
- Support number, separate report/intake columns, and support-type-only columns are not shown in the main task list.
- The current-task strip hides secondary material/support chips and keeps the operational fields needed for one-click calculation.
- Spectrum preview loads project-matched building/sheet and elevation candidates from the uploaded spectrum workbook into the `厂房/谱表` and `标高` dropdowns. Mixed-project workbooks are filtered by the active intake project code.
- Selecting a dropdown value locates the first existing intake row that already matches that building/elevation. It does not silently overwrite the currently selected row; the `应用` button is the only path that writes an override to the active row.
- Primary buttons and native dropdowns use explicit focus/active/disabled text colors so mouse selection must not turn visible text blank.
- If the square-section cell is blank, the operator sees `经验拟选，计算后优化`; the one-click calculation path must select a candidate section before publishing final results.
- The 1916-style compact task descriptions are supported: `双侧3+4层600` expands to seven tray layers and `单侧4层500` expands to four tray layers.
