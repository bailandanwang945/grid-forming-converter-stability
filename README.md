# 构网型变流器稳定性分析大创项目

天津市市级大学生创新训练项目的结项工作目录。

## 项目执行入口

- `docs/PROJECT_PLAN.md`：持续维护的研究与实施规划；
- `docs/PROJECT_EXECUTION_GOVERNANCE.md`：中央判断、并行代理、测试门和版本演进规则；
- `docs/EXTERNAL_RESOURCES.md`：外部资源获取、版本固定和许可证要求；
- `docs/SUBMISSION_CHECKLIST.md`：中期检查与结项验收材料清单；
- `docs/research/`：数值方法和独立模型候选的来源可追溯调研；
- `docs/specs/algorithms/`：算法原理、接口和测试计划；
- `notes/PROJECT_LOG.md`：可复核的执行与测试记录；
- `experiments/run_unit_tests.m`：MATLAB 快速单元测试入口。
- `experiments/baseline/run_inf_bus_baseline.m`：论文无限大母线稳定/不稳定基线入口。

## 当前结项主线

1. 复现 Cifelli 与 Anta 的单机无穷大母线算例，建立可信基线。
2. 对每个频率点的复矩阵计算数值域分离裕度及条件性上下包络；证据不足时保留“暂不能判定”。
3. 重点复查边界频率附近的误判，区分理论边界、离散采样和浮点容差问题。
4. 选择一个新的构网型变流器小信号模型，判断其是否满足小相位定理的应用前提。
5. 用时域仿真或闭环极点结果交叉验证判据，形成结项报告和可复现实验。

## 目录

- `docs/project/`：申报书、结项要求等项目管理材料（本地保存，不默认提交 Git）。
- `references/papers/`：论文原文（本地保存，不默认提交 Git）。
- `references/source/`：与论文版本对应的官方源码快照；原始文件保持只读，派生产物不写入此处。
- `references/SOURCES.md`：文献和代码来源、版本及校验信息。
- `external/`：第三方原始代码；不直接在其中开发。
- `src/`：团队自行实现的稳健判定函数和工具。
- `models/`：自建或经过许可使用的模型说明及参数。
- `experiments/`：可重复运行的实验入口和配置。
- `results/`：精选结果；大体积原始结果不进 Git。
- `notes/`：会议记录、待确认概念和研究决策。

## 上游代码

论文作者仓库已按 `v1.0.0` 浅克隆到：

`external/cifelli-small-gain-phase`

固定提交：`ef67c7a4ac84e4e1142e95b072d241db89eb64ba`。

该代码依赖 Simplus Grid Tool。先不要覆盖其安装目录中的 `GridFormingVSI.m`；复现时应保留原文件并用脚本完成受控替换或路径覆盖。

## MATLAB / Simulink AI 工具

- MATLAB：R2024b，安装于 `G:\matlab`。
- MATLAB MCP Server：v0.11.2，已在 Codex 中注册并实际验证 12 个 MATLAB/Simulink 工具。
- MATLAB Agentic Toolkit：2026.07.02。
- Simulink Agentic Toolkit：2026.07.08。
- Codex MCP 默认工作目录为本项目，工具超时为 600 秒，并已转发 Windows `WINDIR`。

使用 Simulink MCP 工具前，在 MATLAB 会话中运行：

```matlab
addpath("C:\Users\18073\.matlab\agentic-toolkits\simulink")
satk_initialize
```

`C:\Users\18073\Documents\MATLAB\startup.m` 已配置自动执行上述初始化。若 MCP 工具未出现，应保持 MATLAB 会话运行并建立新的 Codex 任务，使工具清单重新加载。

## 工作原则

- 原始文献、上游代码、自研代码和实验产物分开保存。
- 论文存在官方 TeX 源码时，优先按相同版本读取 TeX 语义结构，并以 PDF 核对图表和最终排版；不要默认生成逐页拼接 Markdown。
- 上游目录保持只读基线；所有修正写入 `src/`，并记录与原实现的差异。
- 单一判据不能作为正确性证明，至少与数值域图和闭环稳定性结果交叉验证。
- 会议录音转写只作为待核对线索，不直接写进论文结论或作为导师原话引用。
