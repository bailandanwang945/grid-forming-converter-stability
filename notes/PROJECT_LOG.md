# 项目执行日志

本日志记录可复核的项目动作、输入、结果和后续决策。临时猜测不写入本文件。

## 2026-07-16：执行主线与首个算法原型

### 已完成

- 核对作者仓库：`v1.0.0`，提交 `ef67c7a4ac84e4e1142e95b072d241db89eb64ba`，工作树干净；
- 核对论文 v2 对 numerical range、sectorial、quasi-sectorial 和 semi-sectorial 的定义；
- 调研教育部大创管理原则与天津大学公开答辩流程；
- 创建持续维护的 `docs/PROJECT_PLAN.md`；
- 创建 sectoriality classifier 的系统/架构规格和实现/测试计划；
- 实现 `src/classifyNumericalRange.m` 第一版；
- 创建 `tests/classifyNumericalRangeTest.m` 类式测试和 `experiments/run_unit_tests.m` 入口。

### 测试环境

- MATLAB：R2024b，安装于 `G:\matlab`；
- 执行方式：MATLAB `-batch`；
- 原因：Hermes 已确认 MATLAB MCP 注册存在，但当前 Codex 会话未暴露 MATLAB MCP 工具。

### 测试命令

```powershell
& 'G:\matlab\bin\matlab.exe' -batch "cd('E:/git_Projects/grid-forming-converter-stability'); addpath('experiments'); results = run_unit_tests();"
```

### 测试结果

- 9 Passed；
- 0 Failed；
- 0 Incomplete；
- 测试执行时间：约 1.49 s；
- MATLAB 进程总耗时：约 51.1 s（主要为冷启动）。

### 尚待审查

- 独立核对 `m(A)=max_theta lambda_min(H_theta(A))` 分类的数学边界；
- 外部可获取模型、依赖和许可证清单；
- Hermes CLI/MCP 的最小自修复结果；
- 项目根目录尚未初始化 Git，当前不能 commit。

## 2026-07-16：全局误差界修正

独立数学审查构造了有限角网格的漏检反例。原实现只在最佳采样点附近细化，负的候选裕度不能证明全局最大裕度为负。已采取以下修正：

- 增加均匀角网格的 Lipschitz 上界；
- 返回 `lowerBound`、`upperBound` 和 `optimalityGap`；
- 证据不足时输出 `indeterminate`，不强行报告 `non-sectorial`；
- 增加 off-grid 非正规 Jordan 解析族、酉相似不变性和复数选项测试；
- 增加候选分类与已认证分类的区分。

第一次运行扩展后的 17 项测试时，16 项通过、1 项失败。失败项为旋转角数值误差 `1.52e-8 rad` 超过测试容差 `1e-8 rad`；分类和裕度结果正确。测试角度容差调整为 `1e-7 rad`，等待全量复测。

全量复测结果：

- 17 Passed；
- 0 Failed；
- 0 Incomplete；
- 测试时间：约 4.02 s；
- `checkcode('src/classifyNumericalRange.m','-id')` 无报告项。

## 2026-07-16：Simplus 依赖与包类解析核对

- 本地 Simplus 快照位于 `external/simplus-grid-tool`；
- 文件数：281；体积：约 13.69 MB；
- README 标记版本：`v2026-Mar-9`；
- 本地快照没有 `.git`，尚无可核验的上游 commit；
- 许可证文件存在；
- MATLAB R2024b 所需的 Simulink、Simscape、Simscape Electrical 和控制相关工具箱均已安装。

MATLAB 包类解析测试表明：

```text
Simplus class: external/simplus-grid-tool/+SimplusGT/+Class/GridFormingVSI.m
After author root: external/simplus-grid-tool/+SimplusGT/+Class/GridFormingVSI.m
```

结论：把作者仓库根目录加入 MATLAB 路径不能覆盖 Simplus 包类。Phase 2 必须建立隔离的 `+SimplusGT/+Class` 覆盖层，并在运行前用 `which SimplusGT.Class.GridFormingVSI -all` 核对实际解析路径；不得覆盖 vendor 快照。
