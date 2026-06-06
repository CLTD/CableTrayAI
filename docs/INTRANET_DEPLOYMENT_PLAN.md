# CableTrayAI 内网部署计划

## 当前发布形态

当前发布包采用 **本机桌面程序模式**：

1. 每台使用电脑解压 `CableTrayAI.zip`。
2. 双击 `CableTrayAI.exe`。
3. 程序在当前电脑自动查找 ANSYS Mechanical APDL。
4. 程序弹出本机结果输出目录选择窗口。
5. 程序启动本机网页服务并打开 `http://127.0.0.1:8000/`。

这个模式避免浏览器远程控制文件夹和 ANSYS 的权限问题。谁运行 `CableTrayAI.exe`，谁的电脑调用本机 ANSYS，结果写到谁选择的本机目录。

## 旧客户端计算节点模式已移除

旧版曾尝试通过本机计算节点桥接浏览器和本机 ANSYS。该模式部署复杂、权限边界不清、现场容易误用。当前发布包不再交付该模式：

- 不包含 `CableTrayAI_Worker.exe`
- 不包含 `START_CLIENT_WORKER.cmd`
- 不包含“本机计算节点”启动入口
- 不再暴露 `/worker/*` API

后续如需多机任务调度，应单独设计受控计算代理，不应混在当前一键桌面包内。

## 一键部署入口

如果单位希望把程序复制到固定目录，可保留：

```text
一键部署启动.cmd
```

该入口会调用 `INSTALL_AND_START.ps1` 选择正式安装目录，例如：

```text
D:\CableTrayAI
C:\CableTrayAI
```

正式操作仍建议直接使用顶层 `CableTrayAI.exe`。

## 资料和配置保护

更新包只覆盖代码、模板、脚本、文档和配置示例，不覆盖现场数据：

- 保留：`source_materials/`
- 保留：`jobs/`
- 保留：`uploads/`
- 保留：`outputs/`
- 保留：`config/*.local.toml`
- 保留：`config/*.local.json`
- 保留：`docs/operator_feedback/`

## 访问控制和反馈

当前本机桌面模式默认只在本机打开：

```text
http://127.0.0.1:8000/
```

如后续切换为科室共享服务器模式，可按单位网络策略开放固定服务器地址，例如：

```text
http://10.102.15.203:8000/
```

共享服务器模式才需要维护白名单。默认允许客户端示例：

- `10.102.15.110`
- `10.102.15.102`
- `10.102.15.105`

人工反馈和错误备忘保存到：

```text
docs/operator_feedback/
```

## 单位内网大模型接入

CableTrayAI 通过 OpenAI-compatible `/v1` 接口接入单位内网模型。模型只用于提资理解、命令流计划复核、日志解释、异常归因和修复建议，不替代 ANSYS、Excel 权威评定、确定性公式、`result.json` 和 `source_ref`。

配置文件：

```text
config/ai.local.toml
```

示例：

```toml
[provider]
enabled = true
base_url = "http://<unit-local-model-server>:<port>/v1"
model = "<unit-local-model-name>"
api_key_env = ""
timeout_seconds = 60
```

## 打包位置

交付包生成到：

```text
C:\Users\duxy\Desktop\duxyb
```

主要文件：

```text
CableTrayAI.zip
CableTrayAI\CableTrayAI.exe
CableTrayAI\INTRANET_DEPLOY_README.txt
CableTrayAI\使用说明_中文简版.txt
```

## ANSYS 核数策略

不写死核数。配置使用 `nproc_percent` 按本机逻辑核心数换算，默认偏保守。需要调整时使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tune_ansys_resources.ps1 -NprocPercent 0.10
```

这只改配置，不执行 ANSYS。
