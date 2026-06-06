# LLM 辅助命令计划小批量验证

## 验证时间

2026-05-23

## 验证范围

本次只验证新底层链路，不全量运行历史报告：

- 提资文件：`uploads/intake/1818 S2支架需求补充-7.28.xlsx`
- 反应谱文件：`uploads/spectrum/楼层谱1818 ANSYS格式 标高线性.xlsm`
- 样本数量：2 条
- ANSYS 执行：`dry_run`，不真实调用 ANSYS

输出：

- `jobs/llm_small_batch_20260523_231735/18185NI-LXSJ4157`
- `jobs/llm_small_batch_20260523_231735/18185NI-LXSJ4158`
- `docs/production_runs/llm_small_batch_20260523_231735/small_batch_result.json`

## 验证结果

两条样本均完成：

- `llm_intake_intent.json`
- `command_plan.json`
- `command_plan_audit.json`
- `llm_generation_audit.json`
- `generated_model.mac`
- `generated_solve.mac`
- `generated_post.mac`
- `run_all.mac`
- `ansys_preflight.json`
- `run_ansys.ps1`

`command_plan_audit.json` 通过项：

- schema 正确；
- 权限为 `standard_template_compilation_only`；
- 只产出三份命令流；
- 标准源引用完整；
- 不允许自由 APDL/PIP/MAC 字段；
- LLM 权限为 `proposal_only`。

## 重要说明

当前本机配置的模型端点未成功参与本次小批量验证，系统按确定性回退生成 `llm_intake_intent.json`，并继续完成命令计划和三份命令流编译。这是预期安全行为：模型不可用时不能阻断标准工程流程。

如需使用 DeepSeek 参与意图解析，请设置：

```toml
[provider]
enabled = true
base_url = "https://api.deepseek.com"
model = "deepseek-v4-flash"
api_key_env = "DEEPSEEK_API_KEY"
timeout_seconds = 120
```

不要把 key 写入配置文件。已经在聊天中暴露过的 key 建议作废重建。

## 仍需真实计算验证的内容

本次不是 1% 精度验证，不替代真实 ANSYS 小批量计算。下一步如果启用真实 ANSYS，应针对 3-5 个代表样本检查：

- `result_validation.json` 是否通过；
- 载荷节点是否非 UNKNOWN；
- 基础载荷、连接螺栓载荷、焊缝载荷是否非全零；
- 第六章结果表是否按报告章节映射；
- 模态图、方钢应力图、托臂/焊缝附录图是否齐全。
