# AI 审核模型适配

## 定位

AI 模型只做实时审核、错误定位、规则解释和优化建议，不替代以下确定性来源：

- 标准化 APDL/PIP/MAC 命令流
- ANSYS real run 或 real imported 输出
- 已确认 Python 公式
- job 本地 Excel 权威评定副本
- 带 `source_ref` 的规范/报告/评定表来源

## 配置

复制示例配置：

```powershell
Copy-Item config/ai.local.example.toml config/ai.local.toml
```

The dashboard can also write the same file from the `DeepSeek / 本地大模型` panel. This is intended for the unit digital department's local DeepSeek service. Use an OpenAI-compatible `/v1` endpoint:

```toml
[provider]
enabled = true
base_url = "http://<deepseek-server>:<port>/v1"
model = "deepseek-r1"
api_key_env = "CABLETRAYAI_LLM_API_KEY"
timeout_seconds = 60
```

The model is only allowed to assist with QA dialogue, bug triage, and explanation. It must not overwrite deterministic ANSYS output, Excel authoritative evaluation, RCC-M/spec formula conclusions, or report traceability.

内网 DeepSeek 或其他 OpenAI-compatible 模型服务示例：

```toml
[provider]
enabled = true
base_url = "http://<内网模型服务>/v1"
model = "deepseek-coder"
api_key_env = "CABLETRAYAI_LLM_API_KEY"
timeout_seconds = 60
```

如果 `enabled=false` 或模型不可用，系统会退回固定工程规则审核。

## 接口

```powershell
Invoke-RestMethod -Method Post `
  -ContentType application/json `
  -Body '{"question":"检查当前 job 的结果提取和报告注入风险"}' `
  http://127.0.0.1:8000/jobs/<job_id>/ai-audit
```

输出写入：

- `jobs/<job_id>/ai_audit_comments.json`

## 模型需要知道的逻辑

系统提示词已内置 CableTrayAI 关键边界：

- 命令流必须来自标准模板，不凭空改力学逻辑。
- 计算结果必须来自 ANSYS。
- 评定必须来自确定性公式或 Excel 权威评定。
- 关键载荷全零、节点 UNKNOWN、图片缺失、公式未确认时不得建议通过。
- AI 输出只是建议，最终工程结论仍由确定性模块给出。
