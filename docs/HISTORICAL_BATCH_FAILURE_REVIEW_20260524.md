# Historical Batch Failure Review

## 结论

- 状态：`fail`
- 报告样例数：47
- 通过：7
- 仍需排查：11
- 已判为历史报告/源文件冲突：29
- 最大剩余门控误差：0.2622107969151671

历史报告只作为后验校验和冲突发现依据；生产逻辑以标准命令流、规范公式、Excel 权威评定、真实 ANSYS 输出和 source_ref 为准。不能用报告数值硬凑结果。

## 按问题域统计

| 问题域 | 失败指标数 | 涉及报告 | 主要判断 |
| --- | ---: | ---: | --- |
| 应力评定 | 125 | 8 | 优先看输出集合和表章节映射，不允许按接近值替代。 |
| 基础载荷 | 57 | 10 | 优先看根部反力组件、谱/静力系数和力矩参考点。 |
| 连接螺栓 | 51 | 11 | 优先看 LS-FORCE 托盘-托臂连接节点集。 |
| 焊缝 | 43 | 8 | 优先看 HF-FORCE 根部载荷和焊缝公式输入。 |

## 历史报告/源文件冲突

- 冲突数：29
- 主要含义：主要冲突是历史报告或对应命令流采用多楼层包络谱/不同标高谱，而提资行只给出单一标高；需以命令流 source_ref 判定，不能用报告数值反推新提资谱选择。
- 检查项统计：`{"spectrum_elevation_m": 22, "support_spacing_m": 6, "support_height_m": 5, "double_side_layer_count": 4, "square_section_spec": 1, "three_side_layer_count": 1, "tray_loads_kg_per_m": 1}`
- 谱标高证据来源：`{"command_envelope_line": 15, "static_calculation_filename": 12, "report_text": 2}`
- 报告文字与命令流谱标高不一致数：7

## 剩余失败样例

### 18185NI-LXSJ4144

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4144__row_136`
- 最大门控误差：0.2622107969151671
- 失败指标数：13
- 域统计：`{"stress": 2, "weld": 2, "foundation_load": 5, "connection_bolt": 4}`
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `tray_arm_connection_loads[1].my` | 连接螺栓 | 28.7 | 38.9 | 0.2622107969151671 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `beam.mixed_beam_type_1.upset.compression.calculation_value` | 应力评定 | 0.3562206 | 0.37 | 0.03724162162162162 | MAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `beam.cantilever_root_weld.upset.compression.calculation_value` | 应力评定 | 0.3562206 | 0.37 | 0.03724162162162162 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `tray_arm_connection_loads[0].fy` | 连接螺栓 | 552.3 | 567.6 | 0.026955602536998004 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[1].my` | 基础载荷 | 549.4 | 564.3 | 0.02640439482544742 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `tray_arm_connection_loads[0].fx` | 连接螺栓 | 461.0 | 472.2 | 0.02371876323591696 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[1].fx` | 基础载荷 | 1087.4 | 1112.5 | 0.022561797752808907 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `tray_arm_connection_loads[0].my` | 连接螺栓 | 13.8 | 14.1 | 0.021276595744680778 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |

### 18185NI-LXSJ4135

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4135__row_77`
- 最大门控误差：0.18634268510377536
- 失败指标数：64
- 域统计：`{"stress": 36, "weld": 8, "foundation_load": 11, "connection_bolt": 9}`
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `foundation_loads[1].fz` | 基础载荷 | 3053.9 | 3753.3 | 0.18634268510377536 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `combination.cantilever_arm.upset.compression_bending.calculation_value` | 应力评定 | 0.08752401867790205 | 0.1 | 0.12475981322097957 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `combination.cantilever_arm.upset.tension_bending.calculation_value` | 应力评定 | 0.08754489341300326 | 0.1 | 0.1245510658699675 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `foundation_loads[1].my` | 基础载荷 | 3924.1 | 4349.2 | 0.09774211349213646 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `beam.cantilever_arm.faulted.tension.calculation_value` | 应力评定 | 0.6515675 | 0.72 | 0.09504513888888891 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `beam.cantilever_root_weld.faulted.tension.calculation_value` | 应力评定 | 0.6515675 | 0.72 | 0.09504513888888891 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `foundation_loads[2].mz` | 基础载荷 | 748.9 | 825.0 | 0.09224242424242426 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `foundation_loads[2].mx` | 基础载荷 | 6127.1 | 6749.2 | 0.09217388727552887 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |

### 18185NI-LXSJ4152

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4152`
- 最大门控误差：0.1485849056603773
- 失败指标数：45
- 域统计：`{"stress": 17, "foundation_load": 9, "weld": 11, "connection_bolt": 8}`
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `tray_arm_connection_loads[1].my` | 连接螺栓 | 72.2 | 84.8 | 0.1485849056603773 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `tray_arm_connection_loads[1].fz` | 连接螺栓 | 3349.9 | 3872.3 | 0.1349069028742608 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[2].fz` | 基础载荷 | 7492.2 | 8655.9 | 0.13444009288462203 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `cantilever_root_loads[1].my` | 焊缝 | 992.8 | 1142.2 | 0.13080021012081955 | HF-FORCE.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `cantilever_root_loads[1].fz` | 焊缝 | 3329.9 | 3827.5 | 0.13000653167864137 | HF-FORCE.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `foundation_loads[1].mz` | 基础载荷 | 708.1 | 631.8 | 0.12076606521050977 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `tray_arm_connection_loads[0].mz` | 连接螺栓 | 2.9 | 2.6 | 0.11538461538461531 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `beam.mixed_beam_type_1.faulted.shear.calculation_value` | 应力评定 | 9.3736849 | 10.48 | 0.10556441793893127 | MAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |

### 18185NI-LXSJ4249

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4249`
- 最大门控误差：0.11961756373937683
- 失败指标数：35
- 域统计：`{"stress": 10, "foundation_load": 8, "weld": 10, "connection_bolt": 7}`
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `tray_arm_connection_loads[1].fy` | 连接螺栓 | 4972.4 | 5648.0 | 0.11961756373937683 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `cantilever_root_loads[1].mz` | 焊缝 | 1878.7 | 2133.8 | 0.11955197300590502 | HF-FORCE.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `cantilever_root_loads[1].fy` | 焊缝 | 5102.9 | 5795.6 | 0.11952170612188569 | HF-FORCE.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `cantilever_root_loads[1].mx` | 焊缝 | 248.7 | 282.4 | 0.11933427762039657 | HF-FORCE.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `tray_arm_connection_loads[1].mz` | 连接螺栓 | 1.5 | 1.7 | 0.11764705882352938 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[2].mx` | 基础载荷 | 21740.2 | 24612.4 | 0.11669727454453854 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `foundation_loads[2].fy` | 基础载荷 | 18789.9 | 21254.8 | 0.11596909874475403 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `combination.mixed_beam_type_1.faulted.tension_bending.calculation_value` | 应力评定 | 0.7391346804909834 | 0.82 | 0.09861624330367871 | MAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |

### 18185NI-LXSJ4115

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4115__row_18`
- 最大门控误差：0.09451945988880067
- 失败指标数：37
- 域统计：`{"stress": 21, "weld": 2, "foundation_load": 7, "connection_bolt": 7}`
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `tray_arm_connection_loads[1].my` | 连接螺栓 | 114.0 | 125.9 | 0.09451945988880067 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `tray_arm_connection_loads[0].my` | 连接螺栓 | 53.7 | 58.1 | 0.07573149741824438 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[2].fz` | 基础载荷 | 7208.9 | 7596.5 | 0.051023497663397664 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `tray_arm_connection_loads[0].mz` | 连接螺栓 | 4.7 | 4.9 | 0.040816326530612276 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `tray_arm_connection_loads[0].fy` | 连接螺栓 | 641.8 | 668.3 | 0.039652850516235225 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `combination.cantilever_root_weld.faulted.compression_bending.calculation_value` | 应力评定 | 0.4424476523120384 | 0.46 | 0.03815727758252522 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `combination.cantilever_root_weld.faulted.tension_bending.calculation_value` | 应力评定 | 0.44249261334507056 | 0.46 | 0.038059536206368386 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `foundation_loads[1].mx` | 基础载荷 | 5769.7 | 5995.1 | 0.03759737118646904 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |

### 18185NI-LXSJ4153

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4153`
- 最大门控误差：0.08951508249688815
- 失败指标数：45
- 域统计：`{"stress": 25, "weld": 6, "foundation_load": 8, "connection_bolt": 6}`
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `foundation_loads[1].fz` | 基础载荷 | 3437.9 | 3775.9 | 0.08951508249688815 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `tray_arm_connection_loads[1].mz` | 连接螺栓 | 3.0 | 3.2 | 0.06250000000000006 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `tray_arm_connection_loads[1].fy` | 连接螺栓 | 1678.4 | 1770.8 | 0.05217980573751969 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[2].mx` | 基础载荷 | 11665.3 | 12280.5 | 0.0500956801433167 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `foundation_loads[2].fy` | 基础载荷 | 6708.6 | 7057.3 | 0.04940983095518113 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `foundation_loads[2].fz` | 基础载荷 | 4915.8 | 5094.8 | 0.03513386197691764 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `beam.mixed_beam_type_1.faulted.bending.calculation_value` | 应力评定 | 243.70524 | 252.3 | 0.03406563614744355 | MAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `beam.mixed_beam_type_1.faulted.shear.calculation_value` | 应力评定 | 8.205565400000001 | 8.49 | 0.03350230859835089 | MAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |

### 18185NI-LXSJ4149

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4149__row_151`
- 最大门控误差：0.05073170731707312
- 失败指标数：5
- 域统计：`{"foundation_load": 3, "connection_bolt": 2}`
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `foundation_loads[1].fz` | 基础载荷 | 1751.4 | 1845.0 | 0.05073170731707312 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `tray_arm_connection_loads[0].fz` | 连接螺栓 | 2840.7 | 2896.2 | 0.01916304122643464 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `tray_arm_connection_loads[1].fz` | 连接螺栓 | 3842.6 | 3903.9 | 0.015702246471477287 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[2].fz` | 基础载荷 | 3807.3 | 3855.6 | 0.012527233115468338 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `foundation_loads[1].fx` | 基础载荷 | 1396.8 | 1411.1 | 0.010133938062504398 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |

### 18185NI-LXSJ4147

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4147`
- 最大门控误差：0.04289256957413598
- 失败指标数：13
- 域统计：`{"stress": 7, "weld": 2, "foundation_load": 2, "connection_bolt": 2}`
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `foundation_loads[1].fz` | 基础载荷 | 3126.2 | 3266.3 | 0.04289256957413598 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `combination.cantilever_root_weld.upset.tension_bending.calculation_value` | 应力评定 | 0.4482989306117459 | 0.46 | 0.02543710736576979 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `combination.cantilever_root_weld.upset.compression_bending.calculation_value` | 应力评定 | 0.4485606123098631 | 0.46 | 0.024868234108993293 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `tray_arm_connection_loads[0].fz` | 连接螺栓 | 2566.0 | 2619.7 | 0.02049853036607238 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `beam.mixed_beam_type_1.upset.shear.calculation_value` | 应力评定 | 4.2479709 | 4.33 | 0.018944364896073842 | MAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `beam.cantilever_root_weld.upset.shear.calculation_value` | 应力评定 | 4.2479709 | 4.33 | 0.018944364896073842 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `weld.cantilever_root_weld.upset.shear.equivalent_stress_value` | 焊缝 | 8.07599030418251 | 8.23 | 0.01871320726822491 | TMAXBEAMSTRESS.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `weld.cantilever_root_weld.upset.bending.equivalent_stress_value` | 焊缝 | 103.12653802281369 | 104.97 | 0.01756179839179107 | TMAXBEAMSTRESS.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |

### 18185NI-LXSJ4156

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4156`
- 最大门控误差：0.04023267086766841
- 失败指标数：3
- 域统计：`{"foundation_load": 1, "connection_bolt": 2}`
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `foundation_loads[1].fz` | 基础载荷 | 594.0 | 618.9 | 0.04023267086766841 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `derived_bolt_loads[0]` | 连接螺栓 | None | {'fx': 437.1, 'fy': 426.1, 'fz': 951.4, 'my': 9.4, 'mz': 4.0} | None | LS-FORCE-NODES.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `derived_bolt_loads[1]` | 连接螺栓 | None | {'fx': 1005.6, 'fy': 993.0, 'fz': 1053.8, 'my': 13.1, 'mz': 9.3} | None | LS-FORCE-NODES.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |

### 18185NI-LXSJ4154

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4154__row_170`
- 最大门控误差：0.02589333333333336
- 失败指标数：15
- 域统计：`{"stress": 7, "weld": 2, "foundation_load": 3, "connection_bolt": 3}`
- 建议：审 MAX/TMAX/SQUARE 三类应力输出集合与报告 6.1/6.2 表章节映射。
- 建议：审 JCZH 根部反力节点集、谱/静力系数和力矩参考点。
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。
- 建议：审 HF-FORCE 根部组件、焊缝尺寸和焊缝等效应力 source_ref。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `beam.cantilever_root_weld.upset.tension.calculation_value` | 应力评定 | 1.2273744 | 1.26 | 0.02589333333333336 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `weld.cantilever_root_weld.upset.compression.equivalent_stress_value` | 焊缝 | 2.4168555133079845 | 2.48 | 0.025461486569361067 | TMAXBEAMSTRESS.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `foundation_loads[1].my` | 基础载荷 | 9061.8 | 9288.6 | 0.02441702732381641 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `weld.cantilever_root_weld.upset.tension.equivalent_stress_value` | 焊缝 | 2.3334114068441063 | 2.39 | 0.023677235630081093 | TMAXBEAMSTRESS.LIS | 焊缝根部载荷、焊喉面积或等效应力公式输入差异；若上游 HF-FORCE 不一致，评定比值会同步偏差。 |
| `tray_arm_connection_loads[0].fx` | 连接螺栓 | 1569.7 | 1606.2 | 0.02272444278421118 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |
| `foundation_loads[1].fx` | 基础载荷 | 5799.6 | 5932.9 | 0.02246793305129014 | JCZH.LIS | 基础反力集合或谱/静力系数差异；结果来源应限定到 JCZH.LIS 的支架根部反力集合。 |
| `beam.mixed_beam_type_1.upset.compression.calculation_value` | 应力评定 | 1.271266 | 1.3 | 0.02210307692307695 | MAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |
| `beam.cantilever_root_weld.upset.compression.calculation_value` | 应力评定 | 1.271266 | 1.3 | 0.02210307692307695 | TMAXBEAMSTRESS.LIS | 梁单元应力输出集合或 MAX/TMAX/SQUARE 表章节映射差异；支架方钢与托臂不能互相覆盖。 |

### 18185NI-LXSJ4146

- job：`E:\CODEX\tray_platform\CableTrayAI\jobs\production_full_intake_runs\full_all_intake_as_new_20260520_consolidated\18185NI-LXSJ4146`
- 最大门控误差：0.016363636363636337
- 失败指标数：1
- 域统计：`{"connection_bolt": 1}`
- 建议：审 LS-FORCE 托盘-托臂连接组件，禁止用全节点表按接近值替代。

| 指标 | 域 | 计算值 | 报告值 | 门控误差 | 来源 | 判断 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `tray_arm_connection_loads[1].my` | 连接螺栓 | 54.1 | 55.0 | 0.016363636363636337 | LS-FORCE.LIS | 托盘-托臂连接节点集或螺栓载荷后处理集合差异；不应从全节点表按接近值反推。 |

