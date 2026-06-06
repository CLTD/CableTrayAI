# ANSYS Discovery

`scripts/find_ansys.ps1` 只做本机 ANSYS 可执行文件发现，不执行 ANSYS。

## 默认策略

- 默认优先并强制寻找 ANSYS 18.2 / v182 Mechanical APDL。
- 只有真正的 Mechanical APDL 主程序会进入候选：
  - `...\ansys\bin\winx64\ANSYS.exe`
  - `...\ansys\bin\winx64\ANSYS182.exe`
- `ansyscl.exe`、`ansysli_util.exe`、`ansysls_client.exe` 等许可工具会被过滤，不会被当作计算入口。
- 未发现 v182 时，自动配置会停止并写明原因；不会静默选择其他版本。

## 查找范围

- `AWP_ROOT*` 环境变量
- `PATH`
- Windows 注册表中的 ANSYS Inc 安装线索
- 常见安装目录：
  - `C:\Program Files\ANSYS Inc`
  - `C:\Program Files (x86)\ANSYS Inc`
  - `D:\Program Files\ANSYS Inc`
  - `E:\Program Files\ANSYS Inc`
  - `D:\ANSYS Inc`
  - `E:\ANSYS Inc`

正式部署目录不参与写死查找；由 `INSTALL_AND_START.ps1` 弹窗选择。

## 命令

只生成发现报告：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\find_ansys.ps1 -ReportOnly
```

按默认策略写入 `config\ansys.local.toml`：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\find_ansys.ps1 -Force
```

仅在科室确认允许非 v182 时才允许：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\find_ansys.ps1 -AllowFallback -Force
```

## 输出

- `docs\ansys_discovery.json`
- `config\ansys.local.toml`，仅在自动选择成功且允许写入时生成

`docs\ansys_discovery.json` 会记录 `did_not_execute_ansys = true`，用于证明发现阶段没有启动 ANSYS。
