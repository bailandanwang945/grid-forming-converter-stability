# 构网型变流器稳定性分析项目成果与支撑材料索引

> 编制日期：2026-08-27
>
> 用途：供项目组、指导教师和结项评委从“成果陈述”追溯到模型、代码、原始结果、测试与适用边界。本索引不是结题验收表，也不替代学院正式模板。

## 一、成果概览

本项目已经形成四类可核查成果：论文基线复算与充分判据适用性评估、接口透明的分层构网型变流器模型、参数域与跨模型核查实验、可离线运行的 Windows 分析软件。当前软件候选可用于内部展示，但合格异机验收、项目自有代码许可证、指导教师审阅和学院正式材料尚未闭合。

## 二、核心成果及证据

| 编号 | 成果 | 可陈述内容 | 主要支撑材料 | 复核入口 | 表述上限 |
|---|---|---|---|---|---|
| C01 | 核心论文与源码基线 | 保存 Cifelli–Anta 论文 arXiv v1/v2 官方 TeX、原始归档包、来源与逐文件哈希 | [`references/SOURCES.md`](../../references/SOURCES.md)、[`references/source/`](../../references/source/)、[`scripts/verify_reference_baselines.py`](../../scripts/verify_reference_baselines.py) | `python .\scripts\verify_reference_baselines.py --strict-local-archive` | 证明本地基线与登记版本一致，不证明论文定理本身正确 |
| C02 | 作者代码基线 | 固定作者仓库 `v1.0.0 / ef67c7a…`，发布构建使用受哈希约束的 MIT 许可快照和跟踪夹具 | [`references/SOURCES.md`](../../references/SOURCES.md)、[`experiments/baseline/`](../../experiments/baseline/)、[`packaging/research-licenses/`](../../packaging/research-licenses/) | 同 C01；MATLAB 入口见 `experiments/run_unit_tests.m` | 完整作者仓库不进入 Git 或便携包；独立实现不等于逐行复刻作者代码 |
| C03 | Fig. 8 便携式有限网格复算 | Python 内核复算固定1000点网格；失稳工况75点未被充分判据覆盖，稳定工况0点未覆盖 | [`backend/core/fig8_kernel.py`](../../backend/core/fig8_kernel.py)、[`experiments/baseline/fixtures/`](../../experiments/baseline/fixtures/)、[`results/fig8-sensitivity/`](../../results/fig8-sensitivity/) | 网页“论文 Fig. 8”工作区；统一测试入口 | 属于固定有限网格评价；`theorem_status` 保持未由采样 API 评价，不能称连续全频定理已完整验证 |
| C04 | 同一模型参数域对照 | 在176个冻结样点比较有限网格判据覆盖区与闭环特征根参考稳定区：判据覆盖且参考稳定45点、参考稳定但未覆盖96点、参考失稳且未覆盖35点、数值待定0点、一致性违例0点 | [`experiments/comparison/run_fig8_parameter_domain_comparison.m`](../../experiments/comparison/run_fig8_parameter_domain_comparison.m)、[`results/comparison/fig8-damping-grid-strength/`](../../results/comparison/fig8-damping-grid-strength/) | 网页“同域对照”工作区；MATLAB 实验入口 | 未满足充分判据不等于失稳；闭环特征根结果只作有限模型参考稳定域 |
| C05 | 三状态低频网络模型 | 支持小型连通网络中的 GFM、母线、交流线路、无限大电网、静态负荷和被动母线消元，并提供441点 D–X 扫描 | [`backend/core/reduced_order_model.py`](../../backend/core/reduced_order_model.py)、[`docs/specs/model-and-port-conventions.md`](../specs/model-and-port-conventions.md)、[`models/README.md`](../../models/README.md) | 网页“低频模型”工作区 | 只描述低频相角—频率—有功动态，不是平均值 `dq`、EMT 或任意多机编辑器 |
| C06 | 16状态平均值 `dq` 单机模型 | 实现 VSM、P–f/Q–V 外环、双 PI 内环、LCL 与外部 RL 线路；完成42点层级扫描、固定19点消融、四条临界边界和三点非线性阶跃 | [`backend/core/average_dq_model.py`](../../backend/core/average_dq_model.py)、[`docs/specs/models/average-dq-gfm-v1-proposal.md`](../specs/models/average-dq-gfm-v1-proposal.md)、[`results/average-dq-ablation/`](../../results/average-dq-ablation/)、[`results/average-dq-boundary/`](../../results/average-dq-boundary/) | 网页“平均值 dq”工作区；`experiments/average-dq/` | 42点中39点分类一致、3点层级失配只界定冻结网格内的降阶适用性；不外推为一般强网失稳定理 |
| C07 | 参数与动态结构核查 | 分别考察端口辨识、调制环节、功率测量延迟、PLL测量位置和动态/静态线路等结构变量 | [`experiments/average-dq/`](../../experiments/average-dq/)、[`results/average-dq-port-identification/`](../../results/average-dq-port-identification/)、[`results/average-dq-external-line/`](../../results/average-dq-external-line/)、[`results/sienna-team-isomorphism/`](../../results/sienna-team-isomorphism/) | 各实验脚本；网页研究验证区 | 对照用于排查结构差异和模态分支，不把单因素相关变化写成唯一因果机理 |
| C08 | 第三方模型交叉核查 | MathWorks冻结工况与团队模型八点比较为7点分类一致、1点不一致；Sienna Test 08完成分层方程门并保留五项整机比较阻塞 | [`results/mathworks-team-comparison/`](../../results/mathworks-team-comparison/)、[`results/mathworks-gfm-external-validation/`](../../results/mathworks-gfm-external-validation/)、[`docs/research/independent-gfm-model-candidates.md`](../research/independent-gfm-model-candidates.md) | 网页外部模型证据卡；相应实验入口 | 属于跨模型结构核查和有限工况比较，不是整机同构、EMT、硬件在环或实物确认 |
| C09 | 前后端分析工作台 | 四个主要工作区支持参数输入、受控拓扑编辑、图表、案例保存—重载和后端统一计算 | [`apps/web/`](../../apps/web/)、[`backend/api/app.py`](../../backend/api/app.py)、[`docs/software/FRONTEND_BACKEND_MVP.md`](../software/FRONTEND_BACKEND_MVP.md) | 双击 `启动平台.bat` 或运行 `scripts/start_dev.ps1` | 界面展示后端可追溯结果，不以页面变化替代模型验证 |
| C10 | 报告与数据导出 | 提供六类打印式 HTML 报告以及 JSON/CSV 导出，报告与 API 共用后端计算结果 | [`backend/core/reporting.py`](../../backend/core/reporting.py)、[`scripts/browser_smoke.mjs`](../../scripts/browser_smoke.mjs) | 浏览器各工作区“导出/打印报告”操作 | 报告是计算结果载体，不自动提升结论的科学证据等级 |
| C11 | 自动测试与证据边界 | 冻结候选统一验收为 Python 263项、MATLAB 128项、前端构建、启动器和真实浏览器全部通过；其后6项基线完整性测试定向通过 | [`docs/software/VERIFICATION.md`](../software/VERIFICATION.md)、[`results/test-reports/`](../../results/test-reports/)、[`backend/tests/`](../../backend/tests/)、[`tests/`](../../tests/) | `powershell.exe -File .\scripts\verify_all.ps1 -NoBootstrap` | 当前269项 Python 测试尚无新的全量合并通过记录；不得把定向通过写成269/269 |
| C12 | Windows 内部结项候选 | `v0.5.0-rc1` 从干净提交 `6ca0b75` 构建，ZIP SHA-256为 `40c3248…329e1a`，本机整包功能链通过 | [`docs/software/V050_RC1_TEAMMATE_ACCEPTANCE_HANDOFF.md`](../software/V050_RC1_TEAMMATE_ACCEPTANCE_HANDOFF.md)、[`docs/software/CROSS_MACHINE_ACCEPTANCE.md`](../software/CROSS_MACHINE_ACCEPTANCE.md)、[`docs/software/THIRD_PARTY_DISTRIBUTION_AUDIT.md`](../software/THIRD_PARTY_DISTRIBUTION_AUDIT.md) | 包内 `VERIFY_THIS_PC.cmd` | 本机 `FUNCTIONAL_OK` 不代替另一台无开发环境电脑的 `GFM_M5_QUALIFIED` |
| C13 | 研究与开发过程记录 | 保存研究假设、失败路径、适用边界、版本演进和阶段总结 | [`notes/PROJECT_LOG.md`](../../notes/PROJECT_LOG.md)、[`docs/PROJECT_PLAN.md`](../PROJECT_PLAN.md)、[`docs/deliverables/gfm-stability-research-summary.md`](gfm-stability-research-summary.md)、[`docs/software/PROJECT_COMPLETION_AUDIT.md`](../software/PROJECT_COMPLETION_AUDIT.md) | 按日期、实验编号和文件链接回溯 | 日志中的阶段事实须以对应提交和原始结果为准；历史计划不等于最终完成状态 |

## 三、答辩建议采用的三条主要结论

1. 在作者固定模型与冻结参数域内，有限网格小增益—小相位充分判据能够确认部分闭环参考稳定样点，但存在保守的未覆盖区域；未覆盖本身不能判为失稳。
2. 三状态低频模型适合解释同步主导模态，但在冻结42点网格的3个强网侧样点遗漏了16状态模型中的附加失稳模态，说明模型层级选择会改变稳定性分类。
3. 项目把论文复算、模型层级对照、参数域实验、外部模型核查、报告导出和验证边界封装为可离线运行的软件，使评委能够修改参数并查看可追溯结果，而不是只观看预制曲线。

以上均为“在给定模型、参数域和数值证据下”的阶段结论，不使用“首次”“完全复现”“真实稳定域”或“工程部署”等超出证据的表述。

## 四、尚待团队或外部环境完成

| 编号 | 待完成事项 | 关闭证据 | 责任边界 |
|---|---|---|---|
| P01 | 合格异机断网验收 | 同时出现 `GFM_CROSS_MACHINE_FUNCTIONAL_OK`、`GFM_M5_QUALIFIED`，完成人工浏览器检查，并由项目侧导入得到 `GFM_CROSS_MACHINE_RELEASE_ACCEPTED` | 需要另一台符合资格的 Windows 电脑和人工操作 |
| P02 | 项目自有代码许可证 | 团队按 [`PROJECT_LICENSE_DECISION.md`](../software/PROJECT_LICENSE_DECISION.md) 确认方案与版权主体；若选择公开许可，重建发布包 | 属于权属和公开分发决定，不能由工具代替 |
| P03 | 学院正式材料 | 取得本批次通知、模板、命名规则、截止时间与系统入口 | 以学院正式通知为准；当前在线检索没有取得可确认的2026批次文件 |
| P04 | 指导教师与团队审阅 | 书面或可归档的范围确认、讲解演练记录和审核意见 | 需要指导教师和项目成员参与 |
| P05 | 最终提交 | 按学院规则生成最终结题报告、成果一览表、签字材料和系统回执 | 本项目开发流程不自行制作或修改 PPT/PDF |

## 五、历史展示文件的使用边界

`docs/deliverables/` 中现有 PPT/PDF 属于历史候选材料，不代表已按学院最新模板校准，也不作为本轮软件开发的交付目标。使用前必须由项目组人工审看内容、日期、成员信息、结论口径与模板要求；未经负责人再次明确授权，不对这些文件进行制作或修改。
