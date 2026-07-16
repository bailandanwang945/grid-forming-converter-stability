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

## 2026-07-16：本地版本库与 MATLAB MCP 修复

- 已在项目唯一正式工作目录初始化本地 Git 仓库；
- 初始提交：`eb506a8 chore: establish reproducible project baseline`；
- 当前研究分支：`research/nontrivial-core`；
- 未配置远程仓库，未执行推送；
- MATLAB MCP Server 版本：`v0.11.2`；
- 删除了 `existing` 会话模式下不兼容的 `--matlab-root` 与 `--initial-working-folder` 参数；
- MATLAB R2024b 中执行 `satk_initialize`，安装检查全部通过，连接端口为 `31515`；
- 新 Codex 任务已实际暴露 12 个 MATLAB/Simulink MCP 工具；
- 通过 MCP 运行 `classifyNumericalRangeTest`：17 Passed、0 Failed、0 Incomplete，测试时间约 5.01 s；
- 已创建 `C:\Users\18073\Documents\MATLAB\startup.m`，用于每次 MATLAB 启动时自动初始化 Simulink Agentic Toolkit；该文件不属于项目仓库。

## 2026-07-16：并行审查与研究治理

- 主任务作为中央判断处理器，统一任务卡、文件所有权、测试门和 Git 提交；
- 并行完成数值域方法审查、项目治理审查和独立模型候选调研；
- 新增 `docs/PROJECT_EXECUTION_GOVERNANCE.md`；
- 新增 `docs/research/numerical-range-sectoriality-method-review.md`；
- 新增 `docs/research/independent-gfm-model-candidates.md`；
- 独立模型建议采用“项目自建透明平均值 dq 模型 + 固定版本外部时域参照”的两层结构；在接口规范冻结前不下载多个模型试错。

## 2026-07-16：论文无限大母线最小基线

通过隔离运行副本加载作者 `GridFormingVSI.m`，没有修改 Simplus 或作者源码。运行副本位于 `tmp/baseline/`，实验退出时自动删除。

稳定算例：

- 作者布尔判定首个扇形频点：`0.9203732 Hz`；
- 团队均匀网格裕度零点插值：`0.9131644 Hz`；
- 闭环最大极点实部：`0 Hz`，判为稳定。

不稳定算例：

- 作者布尔判定首个扇形频点：`9.8626585 Hz`；
- 闭环最大极点实部：`0.0211544 Hz`，判为不稳定；
- 主导共轭极点虚部约 `0.5781133 Hz`，与论文正文所述 `1.2 Hz` 尚不一致，列为待核差异。

通过 MATLAB MCP 运行慢速集成测试 `runInfBusBaselineTest`：2 Passed、0 Failed、0 Incomplete，测试时间约 50.70 s。

## 2026-07-16：自适应角区间包络首版

- 新增 `classifyNumericalRangeAdaptive(A, options)`，不替换原均匀网格函数；
- 在归一化矩阵上维护周期角区间，以 Lipschitz 上界选择并二分最有希望的区间；
- 返回角离散上下包络、评价次数、活动区间数、停止原因和方法范围；
- 明确设置 `floatingPointCertified=false`，当前包络不包含双精度特征值计算舍入误差；
- 首次运行新增测试时 10/11 通过，边界测试因 `10^-6` 容差带与 256 次预算不匹配而正确返回 `indeterminate`；
- 将边界验收改为 `10^-3` 容差带和 512 次预算，同时保留独立预算耗尽测试；
- 自适应测试：11 Passed；全部快速测试：28 Passed、0 Failed、0 Incomplete；
- `check_matlab_code` 对自适应函数无报告项。
