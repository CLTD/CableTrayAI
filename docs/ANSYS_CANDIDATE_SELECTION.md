# ANSYS Candidate Selection

`scripts\select_ansys_candidate.ps1` 只写本地配置，不执行 ANSYS。

## 默认行为

发现报告存在后，直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\select_ansys_candidate.ps1 -Force
```

脚本不会等待输入，会自动选择 ANSYS 18.2 / v182 Mechanical APDL。

如果没有 v182，脚本会停止并提示原因。只有科室明确确认允许其他版本时，才使用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\select_ansys_candidate.ps1 -AllowFallback -Force
```

## 人工选择

需要人工逐项选择时才启用交互：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\select_ansys_candidate.ps1 -Interactive -Force
```

也可以指定编号：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\select_ansys_candidate.ps1 -Index <n> -Force
```

## 生成配置

写入：

- `config\ansys.local.toml`

默认字段：

- `ansys.executable = "<所选 ANSYS 主程序>"`
- `ansys.default_workdir = "<所选部署目录>/jobs"`
- `runner.mode = "real"`，用于单位生产运行；真实运行仍受 preflight 和 real-run guard 保护。
- `output_import.default_source_dir = "outputs"`

## 安全规则

- 不传 `-Force` 不覆盖已有 `config\ansys.local.toml`。
- selector 不会调用 ANSYS。
- discovery 与 selector 都会过滤 `ansyscl.exe` 等许可工具。
- 真正执行 ANSYS 仍必须通过 preflight、谱配置确认和用户显式运行动作。
