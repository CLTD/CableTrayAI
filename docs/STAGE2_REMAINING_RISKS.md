# Stage 2 Remaining Risks

1. 真实 ANSYS 尚未接入默认流程。`run_mock_ansys` 仍用于 CI 和本地闭环验证。
2. 反应谱 XLSM 的真实格式可能包含合并单元格、多 sheet 或非扁平表格；当前 selector 支持配置驱动扩展，但还需要按实际文件补配置。
3. 支架拉弯组合、压弯组合、焊缝等效应力、膨胀螺栓组合仍需人工确认公式来源。
4. 报告仍由程序生成固定结构 docx，尚未替换为单位最终 Word 模板填充。
5. PIP 输出清单已能识别主要 LIS 和图片命名，但不同历史项目的输出文件可能有额外变体，需要继续扩展 manifest 映射。
6. `.pytest_tmp` 和 `.pytest_cache` 曾出现本机 ACL 异常；当前 pytest 配置已避免使用仓库内缓存目录。
