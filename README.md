# 电缆桥架智能力学分析平台

本项目聚焦电缆桥架 S2 支架智能计算：提资解析、反应谱选择、APDL 参数化建模、ANSYS 批处理、结果提取、Excel/确定性公式评定、图片提取、模板报告注入和单位内网 AI 实时质控。

## 平台目标

1. 基于既有标准化建模命令流、PIP 文件、计算 MAC 文件、SECT 截面文件和结果评定 Excel，完成电缆桥架力学分析闭环。
2. 自动生成三份可审核命令流：`generated_model.mac`、`generated_solve.mac`、`generated_post.mac`。
3. ANSYS 输出必须经过 LIS/OUP/BMP/PNG/RST/OUT/ERR 解析和结果有效性审计。
4. 评定结论来自 ANSYS 结果、Excel 权威评定或带 `source_ref` 的确定性公式。
5. 单位内网模型只负责提资意图理解、命令流计划审核、实时质控、错误归因、日志解释和安全修复建议。

AI 只负责资料检索、命令流解释、异常审核、错误归因和优化建议；最终计算与评定必须来自 ANSYS 结果、Excel 权威评定或确定性公式。

## 操作入口

单位部署推荐运行一键部署脚本，弹窗选择部署目录，不需要固定在 `E:\CODEX`：

```powershell
powershell -ExecutionPolicy Bypass -File INSTALL_AND_START.ps1
```

开发机本地启动网页：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_dashboard.ps1
```

打开 `http://127.0.0.1:8000/` 或 `http://127.0.0.1:8000/dashboard`。

## 单位内网模型

默认接入单位模型清单中的 `Qwen3-coder-30B`，用于提资意图理解、命令流计划审核、实时质控、错误归因和安全修复建议。管理员在网页中用下拉框切换模型，不手填模型名。

模型质控入口：`http://127.0.0.1:8000/ai-tools` 或 `http://部署电脑IP:8000/ai-tools`。

```toml
[provider]
enabled = true
base_url = "http://models.ai.cnpe.cc/deepseek32b/v1"
model = "Qwen3-coder-30B"
api_key_env = ""
preset_id = "qwen3-coder-30b"
timeout_seconds = 60
```

可选预设包括 `DeepSeek-R1-32B`、`Qwen3-235B`、`Qwen3-32B` 和 `Qwen2.5-VL-7B`。平台探测连接时只发送一句测试文本，不上传工程资料。

单位模型的自动修复边界：

- 可自动修复：部署脚本、端口、路径、网页显示、配置缺失、日志定位、已验证的非工程性解析错误。
- 必须人工审核：APDL/PIP 力学逻辑、材料许用值、评定公式、结果映射、报告正式结论。

## 电缆桥架生产规则

- 提资中包含“钢平台”的条目按静力法处理。
- 其它条目按反应谱法处理，必须选择对应项目的反应谱文件。
- ANSYS 路径优先使用 `config/ansys.local.toml`，没有可用配置时自动 discovery。
- 手工报告/基准比对只作为开发验证手段，不放在操作员主流程中。
- 不允许把 mock/dry-run 当作正式工程结论。
- 报告数值必须来自 `result.json`、Excel 权威评定或带 `source_ref` 的确定性公式。
