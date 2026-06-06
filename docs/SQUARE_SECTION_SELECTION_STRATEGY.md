# 方钢截面自动选型策略

## 目标

I 列为空时，软件需要自己选择方钢截面。这个步骤不能靠把所有候选截面逐个完整 ANSYS 计算一遍，也不能靠大模型猜结论。

当前策略是：用历史标准命令流生成同一类 S2 模型，用截面几何量做候选排序和少量跳跃，用 ANSYS 真实试算确认应力比，最后仍以 `result_validation.json` 和 `evaluation_summary.json` 的确定性比值作为门禁。

## 借鉴的工程思路

这些资料只用于优化“怎么更少试算”，不用于材料许用值、焊缝公式、报告映射或力学结论。

| 来源 | 采用的思路 | 本项目边界 |
| --- | --- | --- |
| SciPy `minimize_scalar` bounded method, https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.minimize_scalar.html | 有界一维搜索应围绕目标区间收敛，而不是全量枚举。 | 本项目不直接用 SciPy 替代 ANSYS，只借鉴“区间收敛/少量验证”的搜索思想。 |
| Ansys optiSLang, https://www.ansys.com/products/connect/ansys-optislang | CAE 设计优化通常先参数化，再用响应/约束指导下一组设计点。 | 方钢截面仍必须经本地 APDL、PIP、ANSYS 和评定公式验证。 |
| PyMAPDL / MAPDL 批处理文档, https://mapdl.docs.pyansys.com/version/stable/user_guide/mapdl.html | 批处理和参数化计算要保留可追溯输入、输出和日志。 | 当前仍使用本地 ANSYS 批处理；PyMAPDL 只作为后续自动化参考。 |

## 当前实现

1. 候选截面来源仍是 `source_materials/model_commands` 里的 `*.SECT`，原始资料只读。
2. 候选按估算弯曲截面模量排序。
3. 新提资没有方钢截面时，以标准模板当前方钢为锚点。
4. 只保留一个比锚点略小的经济性保护候选，然后向上搜索。
5. 如果某个候选的方钢立柱/方钢构件应力比大于 1.0，按“应力比与截面模量近似反比”的趋势估算下一候选，但每次最多跳过少量候选，防止托臂形式、焊缝、螺栓或连接节点成为控制项时跳过真实最优点。
6. 候选试算阶段不因缺最终报告图片继续扫截面；正式输出阶段仍检查图片完整性。
7. 发现连续多次都是焊缝或螺栓控制，而方钢立柱/方钢构件已经满足时，停止继续放大方钢，改为连接/焊缝/提取集合问题，不硬凑通过。
8. 选出的截面必须满足完整确定性比值 `< 1.0`，并且应力比最接近 1.0。

## 为什么比全量试算快

旧思路是从小到大逐个跑，最多会把 20 个候选都跑一遍。

新思路把 ANSYS 试算压缩成：

1. 一个经济性保护候选；
2. 当前模板候选；
3. 按方钢控制比值估算后的相邻候选；
4. 必要时一个确认候选；
5. 如果控制项不是方钢，提前退出。

这样仍然保留“最终 ANSYS 验证”，但避免大量明显无用的候选。

## 大模型参与边界

大模型可以做：

- 解释为什么某次选型停在某个截面；
- 发现候选试算异常，例如全零、UNKNOWN、缺图、日志报错；
- 根据历史成功样例建议优先试算哪个区间；
- 给工程人员说明需要人工确认的规则。

大模型不能做：

- 直接判定通过；
- 替代 ANSYS；
- 替代 Excel 或确定性公式；
- 根据报告接近程度硬选截面；
- 修改材料许用值或焊缝/螺栓公式。

## 已落地的效率和门禁策略

下面这些不是待办项，已经进入代码和测试。后续只能在这些规则基础上优化，不能绕开门禁。

1. 相似提资缓存已经落地。相同或相近的支架类型、分析方法、层数、托盘宽度、托盘载荷、厂房、标高等信息只用于候选截面排序提示，不直接复用上一次结论。最终截面仍必须通过本 job 的 ANSYS 输出和确定性评定。
2. 失败诊断已经落地。MT、谱选择、JCZH、LS-FORCE、HF-FORCE、MAXBEAMSTRESS、TMAXBEAMSTRESS、运行超时或输出停滞等问题会先阻断截面放大。也就是说，后处理来源不可信时，不允许继续加大方钢来“掩盖”错误。
3. 网页已经显示“为什么只跑这些候选”。当前 job 存在 `square_section_selection.json` 或 `square_section_trial_summary.json` 时，操作页会展示候选排序原因、相似提资提示、提前停止原因和候选试算摘要。
4. 候选试算已经接入超时和输出增长门禁。`timeout`、`startup_no_output_timeout`、`output_stall_timeout` 都会被记录到候选选型结果里，并给出标准截面临时策略或阻断原因。临时策略不等于正式通过，最终仍要靠正式 ANSYS 结果和比值门禁。

## 已落地的整体架构规则

1. 提资解析采用“两层结构”。`core/intake/intake_excel_reader.py` 和 `core/intake/job_input_builder.py` 先做确定性字段抽取、托盘载荷解析和字段校验；低置信度内容只允许进入 AI/人工建议，不直接写成正式计算结论。
2. 建模命令保持“三份命令流”。正式 job 仍输出 `generated_model.mac`、`generated_solve.mac`、`generated_post.mac`，`run_all.mac` 只负责顺序调用三份命令。大模型只能解释和审查命令段，不能绕过标准命令流自由生成不可审查 APDL。
3. 结果提取采用“集合先验 + 数值门禁”。JCZH、LS-FORCE、HF-FORCE、MAXBEAMSTRESS、TMAXBEAMSTRESS、Mode 和图片集合都必须能追溯到源文件；出现全零、UNKNOWN、缺源文件或关键图片缺失时，`result_validation.json` 会阻断正式发布和报告注入。
4. AI 质控是后台巡检。网页不把 AI 作为正式计算结论来源；AI 只解释运行状态、ANSYS 日志、输出增长、UNKNOWN 节点、全零载荷、缺图、MT 截断和报告注入失败，并给出修复建议。正式结论仍以 ANSYS、Excel 和确定性公式为准。
5. 批量运行先做轻量预检。提资字段、谱表、SECT、模板、输出目录、权限和 ANSYS 路径必须先过关，再启动 ANSYS，避免运行很久以后才发现基础配置错误。
6. 网页进度按真实阶段单调显示。预检、建模、选截面、求解、后处理、解析、评定、图片、报告注入分别有状态；同一 run 的百分比不倒退，阶段失败时保留日志和可读原因。

## 对应代码入口

- 方钢候选排序和诊断：`core/optimizer/square_section_selector.py`
- 方钢选型工作流和相似提资缓存：`core/optimizer/square_section_workflow.py`
- 正式结果有效性门禁：`core/validation/result_validity_gate.py`
- 一键运行阶段状态：`core/pipeline/one_click.py`
- 操作页面候选原因展示：`apps/web/index.html`
- API 查询候选原因：`apps/api/app/main.py` 的 `/jobs/{job_id}/square-section-selection`
- ANSYS 输出增长和超时门禁：`core/ansys/runner.py`
