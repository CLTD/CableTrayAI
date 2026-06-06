# LLM 辅助工程编排策略

## 目标

本次底层调整不是让大模型自由编写 ANSYS 命令流。正确边界是：

提资/谱文件/历史规则 → 大模型提出结构化工程意图 → 命令计划审计 → 标准命令流模板编译 → ANSYS 计算 → LIS/图片解析 → Excel/规范公式评定。

大模型可以提高解析弹性和发现异常的能力，但不能替代 ANSYS、Excel 权威评定、确定性公式和 `source_ref`。

## 新增文件

- `core/ai/engineering_intent.py`
  - 生成 `llm_intake_intent.json`。
  - 大模型只输出结构化提资意图、风险、待确认项。
  - 如果模型输出 APDL/PIP/MAC 或自由命令字段，审计会标记为失败。

- `core/apdl/command_plan.py`
  - 生成 `command_plan.json` 和 `command_plan_audit.json`。
  - 明确三份最终命令流：`generated_model.mac`、`generated_solve.mac`、`generated_post.mac`。
  - 强制 `authority = standard_template_compilation_only`。

- `core/apdl/llm_orchestrated_renderer.py`
  - 执行“LLM 意图 + 标准命令流编译”。
  - 最终仍调用 `render_standard_command_package`，从标准 APDL/PIP/MAC 源生成三份命令。
  - 输出 `llm_generation_audit.json`。

- API：
  - `POST /jobs/{job_id}/render-llm-standard-commands`

## 为什么不能让模型直接写 APDL

APDL/PIP/MAC 中的约束、耦合、载荷、后处理集合直接决定工程结论。大模型可以帮助识别“这条提资应该走静力法还是反应谱法”“方钢截面是否缺失”“谱文件是否未确认”，但如果让模型直接写可执行命令，会失去以下审查能力：

- 无法证明命令来自标准化命令流；
- 无法给出稳定的 `source_ref`；
- 同一提资多次生成可能不一致；
- 后续报告和人工校核无法判断差异来自模型、ANSYS 还是公式。

因此当前实现采用“模型生成计划，软件按标准模板编译”的方式。

## 大模型选型

当前本地包内默认轻量模型适合快速日志解释、网页问题定位和质控建议，不适合作为唯一的工程意图生成模型。

推荐策略：

1. 本机离线轻量模型：
   - 用于实时质控、部署问题、日志解释、错误定位；
   - 响应快，不依赖外网；
   - 不作为最终工程判断来源。

2. 单位内网或远程 DeepSeek：
   - 适合结构化提资意图、命令计划复核和复杂冲突分析；
   - 官方 DeepSeek API `/models` 文档列出 `deepseek-v4-flash` 和 `deepseek-v4-pro`；
   - `DeepSeek-V3.2` 官方说明强调 agent/tool-use 能力，可作为单位已有部署的替代候选。

3. 单位内网 Qwen：
   - Qwen Cloud 文档支持结构化输出和 OpenAI-compatible 接入；
   - 可作为与 DeepSeek 竞聘的候选模型。

参考：

- DeepSeek Models API: https://api-docs.deepseek.com/api/list-models
- DeepSeek-V3.2 Release: https://api-docs.deepseek.com/news/news251201
- Qwen Structured Output: https://docs.qwencloud.com/developer-guides/text-generation/structured-output

## 接入 DeepSeek 的配置方式

不要把 API key 写进仓库或部署包。配置文件只写环境变量名：

```toml
[provider]
enabled = true
base_url = "https://api.deepseek.com"
model = "deepseek-v4-flash"
api_key_env = "DEEPSEEK_API_KEY"
timeout_seconds = 120
```

DeepSeek 官方 OpenAI-compatible base URL 是 `https://api.deepseek.com`；如果单位数字化科部署的服务明确给出 `/v1`，再按单位地址填写 `/v1`。

Windows 上由运维或本机管理员设置：

```powershell
setx DEEPSEEK_API_KEY "新生成的 key"
```

已经粘贴到聊天里的 key 建议在 DeepSeek 控制台作废并重建。

## 小批量验证要求

本次重构后的验证重点不是重新全跑 47 个历史报告，而是验证底层边界：

- 无模型时能稳定回退到确定性提资意图；
- 模型返回自由 APDL/PIP/MAC 时会被拦截；
- 命令计划必须只产出三份标准命令流；
- 三份命令流仍来自标准源，并保留 `command_source_traceability.json`；
- API 可以调用 LLM 辅助渲染入口；
- 后续真实 ANSYS 仍必须走 preflight、result_validation 和 Excel/公式评定门禁。
