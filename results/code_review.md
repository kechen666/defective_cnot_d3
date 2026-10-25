# 独立审阅记录

结论：按用户已确认的首版范围，可交付。Critical、Important、Minor 问题均为零。审阅者使用独立上下文，只读检查，没有修改文件。

主执行验证：27 项 pytest 测试通过，pip check 通过，安装脚本完成固定源码指纹核验及锁定依赖安装。`verify_outputs.py` 重新读取交付线路，校验计数、SHA-256、局域边、时隙、严格 DEM、无噪声输出及原生 Choi flows。图像尺寸、DPI 和布局已检查。

独立审阅增加的证据：

- 对健康/缺陷 C、A、T、CA、AT 和两个 gauge 时相验证 248 条单轮 Stim measurement flows；均正确提取指定 check。Stabilizers 位于 gauge span 并与所有 gauges 对易；固定 C/CA 各有唯一 SnL 策略。
- 逐门确认导出 Choi harness 的核心与主线路操作一致。理想前缀原生建立 C/T 与参考比特的 X、Z Bell 关联，四个带符号输出 flow 均通过。
- 重算每个 TICK 的 active/busy 集合，idle targets 均准确等于 active−busy；routing 在初始化前不加噪，数据在读出后不加噪，最后全部数据 inactive。
- 从四条导出的 noisy circuits 重新生成 full/matching DEM，均与交付模型一致；重新搜索 graphlike witness，均一致。完整 DEM 没有权重 1 logical witness，缺陷有权重 2，健康下界 3，与对应上界相合。
- JSON/CSV 的 12 组配置、raw/decoded 计数和率、控制/目标分项率及全部 Wilson 区间一致，总量 1,200,000 shots。
- 所有计划交付物存在：固定来源和环境、patch 代数和布局、阶段操作和索引、frame/selectors、主物理线路及噪声版本、两种 DEM 和 witness、SnL memory、TQEC k=1 参考、统计和可复现文档。

审阅者明确列出的范围外行为及执行者裁定：

1. 其他永久缺陷、边界/corner、ancilla/link、多缺陷和任意缺陷 API：认可，用户已指定中心单缺陷并将边界缺陷留待以后；接口明确拒绝未支持实例。
2. 通用 TQEC 缺陷 convention 和任意阶段长度：认可，首版使用自有 emitter 和每阶段六轮；全局 gauge 相位经偶数长度保持。
3. 不支持的输入形状/basis 的一般 API 加固及缓存对象被用户修改：认可，交付目标为固定、可复现 demo；支持的输入通过测试，当前 CLI 仅生成规定实例。
4. Optimal/correlated decoder、阈值拟合、门 infidelity 和任意输入信道的故障距离认证：认可，采用已确认 MWPM 和指定 Pauli 读出的独立 DEM 模型，README 明确区分估计量。
5. 单独的 noisy merge-only 性能研究：认可，当前统计针对完整连接的 CNOT；阶段元数据可用于后续定位。
6. 测量辅助器件的 idle noise：认可，已确认噪声规则仅对激活数据添加 idle noise，辅助器件按实际门加噪。
7. 独立 Choi harness 中的理想全局门：认可，仅用于验证，没有进入主物理线路、距离分析或 LER 采样。
