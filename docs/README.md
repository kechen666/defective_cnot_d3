# defective_cnot_d3 阅读文档

主文档：[Notebook 逐步实现与正确性核验](04_code_walkthrough.md)。

Patch 专题：[Patch 数据类与关键函数说明](patches_guide.md)，从字段、边界和 SnL 转换讲到构造工厂、四类核验及可运行示例。先理解编码区域的数据结构时，可从这篇开始。

线路构建专题：[circuit_builder.py 初学者指南](circuit_builder_guide.md)，解释完整 CNOT 流程、Experiment 数据类、Builder 各方法、测量记录、detector 和 Pauli frame。

按顺序阅读可从实验目标走到 patch、物理门、测量关系、Pauli frame、DEM 和解码。若先关心核验结果，可直接读主文档第 12 节；复跑命令见第 13 节。

整体流程集中在 `04_code_walkthrough.md`，Patch 数据结构与函数另有上述专题。01 架构、02 设计思想、03 必要语法、06 环境、08 调试和 09 约定的相关内容并入整体导读；05 运行时和 07 二次开发指南不独立成篇。

辅助文件：

- [.project-map.md](.project-map.md)：源码取材位置和统一术语。
- [完整执行核验](validation/2026-10-15/verification.json)：全部 notebook 单元及原始文件指纹检查。
- [导出物补充核验](validation/2026-10-15-artifacts/verification.json)：CSV、Wilson 区间、DEM 和距离重算。
- [复核脚本](validation/verify_walkthrough.py)：可重复执行的额外核验，保留原 notebook 和历史结果。

整体导读初版日期为 2026-10-15，Patch 专题更新日期为 2026-10-23。当前模型和验证范围在相应文档中说明。
