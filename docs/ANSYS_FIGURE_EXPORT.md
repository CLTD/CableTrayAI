# ANSYS 云图导出策略

## 目标

真实 ANSYS job 必须产出可追溯的 BMP/PNG 云图文件，不能只解析数值，也不能从报告里反向截图。

## 实现

- `core/ansys/figure_export.py` 生成 `export_figures.mac`。
- `export_figures.mac` 只做后处理导图，不重新求解。
- 它读取 job 目录中的 `generated_post.mac`，机械转换其中的 `/image,save,<name>,bmp` 导图点。
- 每个导图点使用 `/SHOW,PNG` 在批处理模式下生成真实 PNG。
- 生成后的顺序 PNG 按标准 PIP 图名复制为命名文件，例如：
  - `MOTAI-1.PNG` ~ `MOTAI-4.PNG`
  - `SQ-B1SDIR1.PNG`
  - `SQ-D3SBEND.PNG`
  - `TB1SDIR1.PNG`
  - `TD4SHEAR.PNG`

## 应力云图显示规则

方钢和托臂应力云图必须保留 ANSYS `PLLS` 线应力图的工程信息，便于和第六章评定表逐项核对：

- 左上角显示 `LINE STRESS`、`STEP`、`SUB`、应力类型、`MIN/MAX` 和对应 `ELEM`。
- 底部保留颜色标尺。
- 去掉右上角 ANSYS 版本号、Build、日期和 `PLOT NO.` 这类软件版本戳。

实现方式：

- 图 5.1 / 图 5.2 模型图先在干净的 `PREP7` 图形状态中导出。
- 回到 `POST1` 并进入标准后处理命令流前，恢复线应力云图显示参数：
  - `/PLOPTS,INFO,3`：启用 ANSYS Multi-legend 等值云图模式，保留原生 `LINE STRESS`、`MIN/MAX`、`ELEM` 和色标。
  - `/PLOPTS,LEG1,1`、`/PLOPTS,LEG3,1`、`/PLOPTS,MINM,1`：保留线应力信息、色标和极值标记。
  - `/PLOPTS,LOGO,0`、`/UDOC,1,DATE,0`：避免软件标识和日期污染正式报告图片。
- 图片收集阶段只对白色右上角版本区域做遮盖，不改左上角工程信息和底部色标。

这一步只改变显示样式，不改变 `PLLS` 的选集、工况、应力类型或计算结果。

参考依据：

- ANSYS MAPDL/PyMAPDL `PLOPTS` 官方说明：`INFO=3` 为 Multi-legend 图例模式，适合等值云图保留工程图例和色标。采用范围仅限云图显示参数，不作为计算公式或评定依据。

## 输出

每个 job 目录新增：

- `export_figures.mac`
- `generated_post_figure_export.mac`
- `figure_export_command.json`
- `figure_export_macro_audit.json`
- `figure_export_audit.json`
- `figure_export_names.txt`
- `figures_manifest.json`
- 命名 PNG 云图文件

`figures_manifest.json` 记录：

- `source_file`
- `target_file`
- `figure_type`
- `component_scope`
- `appendix`
- `case`
- `stress_type`

## 分类

- `MOTAI-*`：附录 A，模态图。
- `SQ-*`：附录 B，方钢立柱/方钢构件应力图。
- `TB*` / `TD*`：附录 C，托臂应力图。
- `SHITI`：整体模型图，报告图 5.1。
- `TBMODEL`：托臂模型图，报告图 5.2。

## 注意

- 不修改 `source_materials`。
- 不切换 mock。
- 不重新计算，只读取已完成真实 ANSYS job 的 `.db/.rst/.l*` 和后处理命令。
- 新的 real-run 成功后会自动调用该导图流程。
