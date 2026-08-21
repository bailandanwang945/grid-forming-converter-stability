# 资源来源与版本

## 项目材料

- 《构网型变流器稳定性分析创新训练项目申报书》：项目组提供，原文件来自微信本地缓存；本地副本位于 `docs/project/项目申报书.pdf`。SHA-256：`ABC71843640B807677D31032DE80FC3028D04E56368D511B7FBC229E0D07BF8F`。
- 《构网型变流器单机并网及多机并联系统的失稳机理分析与稳定控制方案》（孙慧强）：项目组提供；本地副本位于 `references/papers/构网型变流器单机并网及多机并联系统分析_孙慧强.pdf`。SHA-256：`6323D4407E122AC63672870C61F025594011F64D9B73E34B20F8CE614E621E4E`。

## 核心论文与代码

- Diego Cifelli, Adolfo Anta, “Decentralized Small Gain and Phase Stability Conditions for Grid-Forming Converters: Limitations and Extensions,” arXiv:2510.20544，已被 PSCC 2026 接收（以作者仓库 README 为准）。
- 论文副本：`references/papers/Cifelli_2025_Decentralized_Small_Gain_Phase_GFM.pdf`。SHA-256：`78C0B5F926A80F71F5C3391B4D115D332D8CB1817452EBCAD77D3A606B73EC49`。
- 与该 PDF 对应的官方 arXiv v1 TeX 源码快照：`references/source/arxiv-2510.20544v1/`。入口为 `source/main_arxiv.tex`；原始下载包位于 `archive/arxiv-2510.20544v1-source.tar.gz`，SHA-256：`AECCE1C7E956C052CA04AA6A47E43712AC0E3F4BEC298156F1C26A7881D4290E`。
- 官方 arXiv v2 TeX 源码快照：`references/source/arxiv-2510.20544v2/`。入口为 `source/main_final.tex`；原始下载包位于 `archive/arxiv-2510.20544v2-source.tar.gz`，SHA-256：`F1F8DA4256370D255BD3D85B0EFD81832A8941FBA8B7629210AC652C525D3D1E`。v2 是当前理论与算例实现基线，v1 保留用于追溯原始 PDF 和早期结果。
- 作者代码：https://github.com/diegoCifelli/Decentralized-Small-Gain-and-Phase-Stability-Conditions-for-GFM-Converters
- 本地上游基线：tag `v1.0.0`，commit `ef67c7a4ac84e4e1142e95b072d241db89eb64ba`。
- 依赖：https://github.com/Future-Power-Networks/Simplus-Grid-Tool

## 注意

- 微信缓存不是长期存储位置；本目录中的 PDF 副本是当前项目归档。
- PDF 和第三方仓库默认被父目录 `.gitignore` 排除，避免课程资料和上游历史误推到团队仓库。
- 阅读论文时优先使用同版本 TeX 获取章节、公式、引用和图题关系，以 PDF 作为视觉与最终排版权威；派生文本放在 `output/`，不得混入原始源码快照。
- 第三方代码使用前应保留其 LICENSE，并在结项报告中明确引用来源。

## 研究方法与创新边界补充（2026-07-19）

- Linbin Huang, Dan Wang, Xiongfei Wang, et al., “Gain and Phase: Decentralized Stability Conditions for Power Electronics-Dominated Power Systems,” arXiv:2309.08037v2, 2024-01-10：组合小增益与小相位定理的分散式稳定充分条件来源。<https://arxiv.org/abs/2309.08037>
- Verena Häberle, Xiuqiang He, Linbin Huang, et al., “Decentralized Parametric Stability Certificates for Grid-Forming Converter Control,” arXiv:2503.05403v8, 2026-06-09：已有依赖局部控制参数的分散式参数稳定充分条件和整定规则。中文材料不直译题名中的 `certificate` 为“证书”，按语境写作“可验证稳定条件”或“稳定性充分判据”。<https://arxiv.org/abs/2503.05403>
- Ruohan Leng, Linbin Huang, Liangxiao Luo, et al., “Geometric Decentralized Stability Certificate of Power Electronics-Dominated Power Systems Covering Variable Operating Points,” arXiv:2607.10335v1, 2026-07-11：利用 Davis–Wielandt 壳投影处理可变运行点并构造由分散式充分判据确认的运行区域。<https://arxiv.org/abs/2607.10335>
- 王印松，田晓民，郝亚峰：《构网型变流器并网系统小干扰稳定域快速构建》，《电力系统及其自动化学报》，网络出版 2025-11-14，DOI: 10.19635/j.cnki.csu-epsa.001733：已有基于序阻抗、广义奈奎斯特判据、盖尔圆盘和相似变换的 GFM 参数稳定域快速构建方法。<https://doi.org/10.19635/j.cnki.csu-epsa.001733>
- Alan L. Andrew, K.-W. Eric Chu, Peter Lancaster, “Derivatives of Eigenvalues and Eigenvectors of Matrix Functions,” *SIAM Journal on Matrix Analysis and Applications*, 14(4), 1993, DOI: 10.1137/0614061：含参数矩阵函数非线性特征值及特征向量灵敏度的理论来源。<https://doi.org/10.1137/0614061>
- 迟永宁，江炳蔚，范译文，等：《构网型变流器：控制与稳定特性》，《高电压技术》，2025, 51(4): 1527–1542，DOI: 10.13336/j.1003-6520.hve.20241154：构网型变流器扰动建模、惯量阻尼、故障电流和宽频振荡研究综述。<https://doi.org/10.13336/j.1003-6520.hve.20241154>

上述来源表明，参数稳定域、特征根/阻抗灵敏度、参数化分散稳定条件和可变运行点确认区域均已有研究。本项目的可辩护增量应收缩为：对 Cifelli–Anta 小增益—小相位充分判据在 GFM 低频非扇形问题上的适用性、保守性来源和数值不确定性进行可复现评估，而不是声称上述一般方法本身为首创。

## 开源动态模型与工程规范补充（2026-08-20）

- Sienna Platform，`PowerSimulationsDynamics.jl`，固定发布 `v0.16.2`，commit `dfb56d80b7a019b2d287f1da4d65157d6de134fa`，BSD-3-Clause。2026-08-20 已核读用户解压的完整固定版本：Test 08 是19状态 VSM—无穷大母线，执行 `P_ref=0.5→0.7`，同时核对初始化、19个小信号特征值以及 PSCAD 频率波形；Test 23 是15状态下垂型构网变流器—无穷大母线，并核对 PSCAD 相角波形。归档还包含两个 PSCAD 工程、参考 CSV、固定初值和特征值。该来源适合作为团队平均值模型的第三方动态实现参照，但因控制结构和参数不同，不直接替代 MathWorks VSM 工况。<https://github.com/Sienna-Platform/PowerSimulationsDynamics.jl/tree/v0.16.2>
- J. D. Lara, R. Henriquez-Auba, M. Bossart, D. S. Callaway, C. Barrows, “PowerSimulationsDynamics.jl -- An Open Source Modeling Package for Modern Power Systems with Inverter-Based Resources,” arXiv:2308.02921，及 J. D. Lara 等，“Revisiting Power Systems Time-domain Simulation Methods and Models,” *IEEE Transactions on Power Systems*, DOI: 10.1109/TPWRS.2023.3303291。前者说明软件结构，后者用于核对现代电力系统时域仿真的模型与数值方法边界。<https://arxiv.org/abs/2308.02921>
- JuliaEnergy，`PowerDynamics.jl`，固定发布 `v5.0.0`，commit `b46f59506c76e625995f4587d5113737a68ea512`。其 `ComposableInverter` 明确公开 L/LC/LCL 滤波器、dq 电压—电流双闭环、虚拟阻抗、下垂外环、坐标变换和功率符号，可用于逐式核对团队16状态模型；项目整体以 MIT 为主，部分派生文件为 MPL-2.0，使用具体文件前仍须核对文件头。该版本中的新构网组件不能仅凭框架论文被称为已单独实验验证。<https://github.com/JuliaEnergy/PowerDynamics.jl/tree/v5.0.0>
- A. Plietzsch 等，“PowerDynamics.jl--An experimentally validated open-source package for the dynamical analysis of power grids,” *SoftwareX*, 17, 100861, 2022，DOI: 10.1016/j.softx.2021.100861。该论文支持对框架整体可复现性和实验对照历史的描述，不自动确认 `v5.0.0` 后加入的每一种变流器组件。<https://doi.org/10.1016/j.softx.2021.100861>
- UNIFI Consortium，“UNIFI Specifications for Grid-Forming Inverter-Based Resources: Version 3,” 2026-01-30，DOI: 10.2172/3016250。**当前仅核对了题名、版本、日期、发布机构和 DOI 元数据，尚未取得并阅读正文。** 因此它只登记为可能相关的候选规范，不能据此声称其中包含哪些具体功能、试验项目或判据，也暂不作为团队模型与实验设计的依据。因 OSTI 下载端点连接失败，尚未在仓库归档 PDF；后续取得原文并完成内容核查后，再决定是否采用并登记文件 SHA-256。<https://doi.org/10.2172/3016250>

上述开源项目的 GitHub 关注量仅用于判断社区规模，不作为模型正确性的证据。2026-08-20 核查时，`PowerSimulationsDynamics.jl` 约 220 stars、`PowerDynamics.jl` 约 134 stars，且近期均有正式发布；数值可能随时间变化，研究引用固定 tag 与 commit，不固定关注量。

## 内环、LCL与线路动态补充（2026-08-21 在线核查）

- Liang Zhao, Xiongfei Wang, Zheming Jin, “Exploring Damping Effect of Inner Control Loops for Grid-Forming VSCs,” arXiv:2310.09660v1。论文以阻抗与复转矩系数分析外环、内环和电网阻抗共同形成的净阻尼，并讨论同步与次同步模态；本项目只把它用于内环/LCL模态实验设计，不直接套用参数结论。本地PDF：`references/papers/Zhao-Wang-Jin-2023-inner-loop-damping-GFM-VSC-arxiv-2310.09660v1.pdf`，SHA-256：`A1B1FC93FDA1A60456F4836693371D0194F53B78BA46BB6577D45BA66BC6DE2E`。<https://arxiv.org/abs/2310.09660v1>
- Sushobhan Chatterjee, Sijia Geng, “Effects of Line Dynamics on Stability Margin to Hopf Bifurcation in Grid-Forming Inverters,” arXiv:2412.15449v1。论文在其算例中比较静态与动态线路，说明忽略线路动态可能高估Hopf稳定裕度；该结论不自动归因团队与Sienna的差异。本地PDF：`references/papers/Chatterjee-Geng-2024-line-dynamics-Hopf-GFM-arxiv-2412.15449v1.pdf`，SHA-256：`31BAB593ECA34A201FD03C9D89305871DDCF30C603D139CF0894254DECCCD2AB`。<https://arxiv.org/abs/2412.15449v1>
- Meng Chen, Yufei Xi, Frede Blaabjerg, Lin Cheng, Ioannis Lestas, “LCL Resonance Analysis and Damping in Single-Loop Grid-Forming Wind Turbines,” arXiv:2504.06981v2。论文指出其单环droop-I结构中的LCL高频稳定性与低频功率环并非必然解耦，且有源阻尼需考虑开环非最小相位特性；本项目不把单环结论直接外推到双PI内环。本地PDF：`references/papers/Chen-et-al-2026-LCL-resonance-single-loop-GFM-arxiv-2504.06981v2.pdf`，SHA-256：`947AE0E0C6115A54C9E68C942D14E1713245DCED7657287EAD4EFC95AB93A37D`。<https://arxiv.org/abs/2504.06981v2>
- Luke Ian Benedetti, Robin Preece, Panagiotis N. Papadopoulos, “Bifurcation Analysis of Sub-Synchronous Oscillations Related to Grid-Forming Converter Inner Controllers,” arXiv:2607.18894v1。论文针对级联内环构网变流器，以连续化与分岔分析研究强网内环相关振荡及电压/电流控制时间尺度；本项目只采用其“先核查内环时间尺度与模态身份”的方法线索。本地PDF：`references/papers/Benedetti-et-al-2026-inner-controller-SSO-bifurcation-arxiv-2607.18894v1.pdf`，SHA-256：`DB28D1F32F08E0630BCC3BCD111A87901E621F31BF65DD784E59D1F8C9EC995C`。<https://arxiv.org/abs/2607.18894v1>
- `l2ep-epmlab/VSC_Lib`：MIT许可的MATLAB/SimPowerSystem构网与跟网模型库，公开L/LCL、单机与多节点示例；2026-08-21在线核查约50 stars，最近推送为2025-10-08。适合作为后续结构参照，当前不引入为项目运行依赖。<https://github.com/l2ep-epmlab/VSC_Lib>
- `ATayebi/GridFormingConverters`：IEEE 9节点 droop、VSM、matching与dVOC算例代码，约138 stars，但最后代码推送为2020-05-30且仓库未声明SPDX许可；只作论文算例线索，不作为当前依赖。<https://github.com/ATayebi/GridFormingConverters>
- `PowerImpedance.jl`：较新的Julia频域分析项目，公开GFM/GFL、线路电缆和广义奈奎斯特/相位移分析能力；2026-08-21在线核查约9 stars、GPL-3.0。方向相关但社区与项目成熟度尚不足以替代当前作者基线或Sienna固定参照。<https://github.com/Electa-Git/PowerImpedance.jl>

本轮阶段决策见 `docs/research/next-stage-online-review-2026-08-21.md`。GitHub stars与更新时间只用于维护性筛查，不构成模型验证。
