# AGENTS.md — CableTrayAI 开发规则

## 一、项目目标

开发一个内网可部署的电缆桥架力学分析网页平台，核心流程为：

Excel/资料提资
→ APDL 参数化建模
→ 反应谱选择
→ ANSYS 批处理计算
→ PIP 后处理结果提取
→ RCC-M 支架、焊缝、螺栓评定
→ 模态图、应力图、载荷表提取
→ Word/PDF 报告生成
→ AI 审核与优化建议

## 二、最重要原则

1. 现有标准化建模命令流、PIP、MAC、SECT、Excel 评定表是基准，不允许从零瞎写。
2. 原始资料只读，不允许修改 source_materials 里的文件。
3. 不允许把 1818、NB、7.5m、某个谱文件名写死进核心逻辑。
4. 1818 只是样例，系统必须支持 2016、2026 等其他项目。
5. AI 只能做审核、建议、模板编排，不得替代确定性计算结论。
6. 支架、螺栓、焊缝评定必须来自确定性 Python 公式，并带 source_ref 溯源。
7. 报告所有数值必须来自 result.json，不允许 Word 里手填。
8. 报告格式必须固定模板化，不能自由排版。
9. 计算失败必须保留 job 目录、日志、APDL、PIP、LIS、图片。
10. 每个阶段都要写测试。

## 三、资料优先级

公式和数据优先级：

1. 结果评定 Excel：
   - 电缆桥架结果评定-q235材料.xlsx
   - 电缆桥架结果评定-06Cr19Ni10材料.xlsx

2. 已完成报告：
   - 18185NI-LXSJ4120.docx

3. 手册：
   - HDLXSC-25A5-02-03 支架、设备抗震分析工作手册.docx
   - HDLXSC-25A5-01-01 抗震分析规范要求工作手册.pdf

4. 标准图册：
   - 1818T5013 电缆桥架支撑的安装、预制标准手册.pdf

5. APDL/PIP/MAC：
   - 建模标准化命令流.txt
   - 01 双侧同类型电缆桥架-方钢托臂.PIP
   - 02 计算用命令流.mac
   - 导出数据-S2.PIP
   - 100-100-8.SECT

## 四、第一阶段 MVP 范围

第一阶段只做 S2 方钢托臂电缆桥架闭环：

1. 资料扫描与索引。
2. 参数模型 input.json。
3. APDL 模板渲染。
4. mock ANSYS runner。
5. PIP/LIS 结果解析骨架。
6. 模态图、应力图图片收集。
7. RCC-M 评定函数骨架。
8. Excel 公式溯源文档。
9. Word 报告生成骨架。
10. FastAPI 最小接口。
11. pytest 测试。
12. 阶段总结和待补公式清单。

## 五、必须输出

每个 job 输出到 jobs/<job_id>/：

- input.json
- generated_model.mac
- generated_solve.mac
- generated_post.mac
- apdl_audit.json
- ansys_run_audit.json
- result_raw.json
- result.json
- figures_manifest.json
- evaluation_summary.json
- audit_comments.json
- report.docx
- report_audit.json

## 六、审核要求

AI 审核意见格式：

- severity: 必改 / 建议 / 风险 / 格式 / 经济性
- location
- issue
- evidence
- suggested_fix
- source_ref
- accepted
- ignored_reason

## 七、精度要求

1. Excel 公式复刻必须建立 golden test。
2. 结果提取必须保存 raw 值和单位。
3. 评定公式必须保存 source_ref。
4. 报告数值必须能反查 result.json。
5. 应力比 > 1.0 必须判为不满足。
6. 应力比 < 0.7 提示偏保守，可给经济性优化建议，但必须重新计算后才能采纳。

## 八、禁止行为

- 禁止联网下载依赖。
- 禁止写死项目号、厂房、标高。
- 禁止删除原始资料。
- 禁止编造公式。
- 禁止没有测试就改评定逻辑。
- 禁止报告自由排版。
- 禁止把 source_materials 推送到外网。

## 九、在线资料使用规则

1. 允许主动联网学习官方文档、高星 GitHub 项目和引用较多的成熟工具，用于改进 ANSYS 调度、网页交互、三维可视化、测试方法、skills 和配置组织。
2. 在线资料只能作为工程实现参考，不能替代本地 source_materials、标准化命令流、PIP/MAC/SECT、结果评定 Excel、已完成报告和真实 ANSYS 输出。
3. 优先引用官方 ANSYS/PyMAPDL 文档、官方项目仓库、PyVista/VTK、Apache ECharts 等成熟项目；引用时必须记录 URL、采用原因和影响范围。
4. GitHub star 数只能作为工具成熟度信号，不能作为力学公式、许用值、报告映射或计算结论的依据。
5. 若联网资料影响代码或配置，必须同步更新 `docs/ONLINE_REFERENCE_POLICY.md` 或对应设计文档。

## 十、上下文压缩恢复规则

1. 如果 Codex 对话被压缩或新开对话继续本项目，必须先读取：
   - `docs/CODEX_RECOVERY_STATE.json`
   - `docs/CURRENT_WORK_STATE.md`
   - `docs/ACTIVE_FIX_QUEUE.md`
2. 不允许压缩后重新猜测目标；必须按上述文件继续执行当前修复队列。
3. 每次完成关键修复、验证或打包后，必须同步更新 `docs/CODEX_RECOVERY_STATE.json`，保证新对话能直接接续。
4. 若需要新开 5.5 超高对话，直接使用 `docs/NEXT_THREAD_HANDOFF_PROMPT.md` 作为首条消息。
