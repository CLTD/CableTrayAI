---
name: offline-deployment
description: 处理单位内网离线部署，包括 wheelhouse、npm-cache、ANSYS 路径配置、无外网运行、依赖锁定和资料保密。
---

# 原则

- 不访问外网。
- 不自动下载依赖。
- source_materials 不进普通远程 Git。
- ANSYS 路径写本地配置。
- 计算任务保留 hash。
