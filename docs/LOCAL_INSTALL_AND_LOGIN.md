# CableTrayAI 本地安装与登录说明

## 安装方式

1. 解压 `CableTrayAI.zip`。
2. 双击 `CableTrayAI_Installer.exe`。
3. 在弹出的目录选择框里选择安装目录，例如 `D:\CableTrayAI`。
4. 安装完成后，桌面会生成 `CableTrayAI` 快捷方式。
5. 开始菜单会生成 `CableTrayAI` 和 `Uninstall CableTrayAI`，Windows 搜索里可以搜到 `CableTrayAI`。
6. 控制面板/Windows 设置的程序卸载列表会出现 `CableTrayAI 电缆桥架力学分析一体化平台`。
7. 后续只需要双击桌面图标，程序会自动启动本机网页。

`INSTALL_CABLETRAYAI.cmd` 只是兼容入口，会优先调用 `CableTrayAI_Installer.exe`。现场推荐直接双击安装器。

## 登录账号

当前放开的账号：

| 账号 | 初始密码 |
| --- | --- |
| duxyb | configured-locally |
| jianghl | configured-locally |
| wanggangb | configured-locally |

本版本取消 IP 白名单强制拦截，只验证账号登录权限。IP 配置文件保留为备用记录，不再决定是否能打开网页。

## 启动后会做什么

1. 自动查找本机 ANSYS Mechanical APDL。
2. 让当前用户选择本机结果输出目录。
3. 启动本机 Web 服务。
4. 打开登录页面。
5. 登录成功后进入电缆桥架力学分析工作台。

正式计算结论仍以 ANSYS、Excel 权威评定、确定性公式和 `source_ref` 为准；AI 只做质控、解释和修复建议。

## 后续小版本更新

后续只需要使用 `CableTrayAI_Update.zip` 和其中的 `UPDATE_CABLETRAYAI.cmd` 做小版本增量更新。增量更新不会覆盖：

- `jobs`
- `uploads`
- `outputs`
- `config/*.local.toml`
- `config/*.local.json`

如果首次安装或运行时损坏，再使用完整 `CableTrayAI.zip`。
