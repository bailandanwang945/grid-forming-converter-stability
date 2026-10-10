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
- Windows 发布流程使用的作者代码 MIT 许可证快照位于 `packaging/research-licenses/Cifelli-Anta-author-code-v1.0.0-LICENSE.txt`，SHA-256 为 `0F8DEBA5D0BE7DC0177BA107408B2D848FB3CA23CE4C625FE48B048B25BF2BF4`；其文字内容与上述固定上游提交中的 `LICENSE` 一致，仅换行编码不同。构建脚本会核对该快照哈希，使干净提交构建不依赖未纳入版本控制的本地作者仓库。
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
- Florian Dörfler, Francesco Bullo, “Kron Reduction of Graphs with Applications to Electrical Networks,” *IEEE Transactions on Circuits and Systems I*, 60(1), 2013，arXiv:1102.2950。用于核对电气网络 Kron 约简的 Schur 补形式及图论性质，不把文中的同步或网络性质直接替代 GFM 稳定判据。本地 PDF：`references/papers/Dorfler-Bullo-2013-Kron-reduction-arxiv-1102.2950.pdf`，SHA-256：`6A238D2F0786C9002DA010C21C5A4E2481544B5F86432AB46149A3CDE0D1A5E4`。<https://arxiv.org/abs/1102.2950>
- Arjan van der Schaft, Bernhard Maschke, “Port-Hamiltonian Systems on Graphs,” *SIAM Journal on Control and Optimization*, 51(2), 2013，DOI: 10.1137/110840091，arXiv:1107.2006。用于端口方向、功率共轭变量和图上守恒互联的结构设计；本项目不据此把受控 GFM 假定为无源，也不以端口哈密顿模型替代小增益—小相位判据。本地 PDF：`references/papers/van-der-Schaft-Maschke-2013-Port-Hamiltonian-systems-on-graphs-arxiv-1107.2006.pdf`，SHA-256：`33F322CECDA9268E494C1CD1195DF6278B85E74B6C985FA3174BF25C825EF026`。<https://arxiv.org/abs/1107.2006>
- UNIFI Consortium，“UNIFI Specifications for Grid-Forming Inverter-Based Resources: Version 3,” 2026-01-30，DOI: 10.2172/3016250。**当前仅核对了题名、版本、日期、发布机构和 DOI 元数据，尚未取得并阅读正文。** 因此它只登记为可能相关的候选规范，不能据此声称其中包含哪些具体功能、试验项目或判据，也暂不作为团队模型与实验设计的依据。因 OSTI 下载端点连接失败，尚未在仓库归档 PDF；后续取得原文并完成内容核查后，再决定是否采用并登记文件 SHA-256。<https://doi.org/10.2172/3016250>

上述开源项目的 GitHub 关注量仅用于判断社区规模，不作为模型正确性的证据。2026-08-20 核查时，`PowerSimulationsDynamics.jl` 约 220 stars、`PowerDynamics.jl` 约 134 stars，且近期均有正式发布；数值可能随时间变化，研究引用固定 tag 与 commit，不固定关注量。

## 内环、LCL与线路动态补充（2026-08-21 在线核查）

- Liang Zhao, Xiongfei Wang, Zheming Jin, “Exploring Damping Effect of Inner Control Loops for Grid-Forming VSCs,” arXiv:2310.09660v1。论文以阻抗与复转矩系数分析外环、内环和电网阻抗共同形成的净阻尼，并讨论同步与次同步模态；本项目只把它用于内环/LCL模态实验设计，不直接套用参数结论。本地PDF：`references/papers/Zhao-Wang-Jin-2023-inner-loop-damping-GFM-VSC-arxiv-2310.09660v1.pdf`，SHA-256：`A1B1FC93FDA1A60456F4836693371D0194F53B78BA46BB6577D45BA66BC6DE2E`。<https://arxiv.org/abs/2310.09660v1>
- Sushobhan Chatterjee, Sijia Geng, “Effects of Line Dynamics on Stability Margin to Hopf Bifurcation in Grid-Forming Inverters,” arXiv:2412.15449v1。论文在其算例中比较静态与动态线路，说明忽略线路动态可能高估Hopf稳定裕度；该结论不自动归因团队与Sienna的差异。本地PDF：`references/papers/Chatterjee-Geng-2024-line-dynamics-Hopf-GFM-arxiv-2412.15449v1.pdf`，SHA-256：`31BAB593ECA34A201FD03C9D89305871DDCF30C603D139CF0894254DECCCD2AB`。<https://arxiv.org/abs/2412.15449v1>
- Yasuaki Mitsugi, Jumpei Baba, “Phaser-Based Transfer Function Analysis of Power Synchronization Control Instability for a Grid Forming Inverter in a Stiff Grid,” *IEEE Access*, 11, 42146–42159, 2023，DOI: `10.1109/ACCESS.2023.3270700`，CC BY 4.0。论文给出含有功测量时间常数的VSG三阶相量模型、Hurwitz条件与CHIL验证；本项目只采用其方程结构和方向校核，不移植论文算例的延迟阈值。IEEE PDF端点在本机返回HTTP 418，本轮已核对在线全文与DOI元数据，尚未伪造本地PDF。<https://doi.org/10.1109/ACCESS.2023.3270700>
- Jaume Girona-Badia, Juan Carlos Olives-Camps, Vinicius Albernaz Lacerda, Eduardo Prieto-Araujo, Oriol Gomis-Bellmunt, “Control Performance and Stability Analysis of Frequency Estimator in Grid-Forming Synchronization Control,” *Journal of Modern Power Systems and Clean Energy*, 14(2), 2026，DOI: `10.35833/MPCE.2025.000144`，CC BY 4.0。论文用于核对VSM/droop频率估计器的结构、整定和交流电压测量位置；不把其配置优劣直接外推到团队模型。本地PDF：`references/papers/Girona-Badia-et-al-2026-frequency-estimator-GFM-synchronization.pdf`，SHA-256：`7017502FFF546E0E1389AFB554240AE4CE13A480674FCB1B37413B7FCFFF464E`。<https://doi.org/10.35833/MPCE.2025.000144>
- Xi Luo, Yadala Pavankumar, Efstratios I. Batzelis, Georgia Saridaki, Panos Kotsampopoulos, “Boundary Analysis of Damping Methods for Virtual Synchronous Generators,” *2025 IEEE Power & Energy Society General Meeting*, DOI: `10.1109/PESGM52009.2025.11225526`。论文以稳定边界比较VSG阻尼与PLL阻尼并考察电网阻抗；本项目只采用“PLL阻尼—测量点—电网强度应拆分对照”的方法线索。本地作者接收稿：`references/papers/Luo-et-al-2025-VSG-damping-method-boundaries.pdf`，SHA-256：`54BD30C170E9570671954625DC95B8BB9A1D08D681200D3A650B889AF85BA98C`。<https://doi.org/10.1109/PESGM52009.2025.11225526>
- Meng Chen, Yufei Xi, Frede Blaabjerg, Lin Cheng, Ioannis Lestas, “LCL Resonance Analysis and Damping in Single-Loop Grid-Forming Wind Turbines,” arXiv:2504.06981v2。论文指出其单环droop-I结构中的LCL高频稳定性与低频功率环并非必然解耦，且有源阻尼需考虑开环非最小相位特性；本项目不把单环结论直接外推到双PI内环。本地PDF：`references/papers/Chen-et-al-2026-LCL-resonance-single-loop-GFM-arxiv-2504.06981v2.pdf`，SHA-256：`947AE0E0C6115A54C9E68C942D14E1713245DCED7657287EAD4EFC95AB93A37D`。<https://arxiv.org/abs/2504.06981v2>
- Luke Ian Benedetti, Robin Preece, Panagiotis N. Papadopoulos, “Bifurcation Analysis of Sub-Synchronous Oscillations Related to Grid-Forming Converter Inner Controllers,” arXiv:2607.18894v1。论文针对级联内环构网变流器，以连续化与分岔分析研究强网内环相关振荡及电压/电流控制时间尺度；本项目只采用其“先核查内环时间尺度与模态身份”的方法线索。本地PDF：`references/papers/Benedetti-et-al-2026-inner-controller-SSO-bifurcation-arxiv-2607.18894v1.pdf`，SHA-256：`DB28D1F32F08E0630BCC3BCD111A87901E621F31BF65DD784E59D1F8C9EC995C`。<https://arxiv.org/abs/2607.18894v1>
- Han Deng, Jingyang Fang, “State-Space Modeling, Stability Analysis, and Controller Design of Grid-Forming Converters With Distributed Virtual Inertia,” *Frontiers in Energy Research*, 10, 2022，DOI：`10.3389/fenrg.2022.833387`，CC BY。论文详细模型含LCL滤波器、级联电压/电流PI控制，并在采样频率等于开关频率时把计算与PWM合计延时写为`1.5T_s`，再用一阶Padé近似；本项目据此区分纯时延、Padé有理近似和团队一阶调制滞后，不复制其参数结论。本地12页PDF：`references/papers/Deng-Fang-2022-GFM-state-space-PWM-delay.pdf`，SHA-256：`44937A75959BEE33472A53768B844B9020900F3FF6E36836BBF6A04A73E5CFB4`；2页补充矩阵：`references/papers/Deng-Fang-2022-GFM-state-space-supplement.pdf`，SHA-256：`F6A0FDED73391F74AECA36168345F9AE9ECD51A5A873D5C31B53D4C243989749`。<https://doi.org/10.3389/fenrg.2022.833387>
- Michael Dokus, Axel Mertens, “On the Coupling of Power-Related and Inner Inverter Control Loops of Grid-Forming Converter Systems,” *IEEE Access*, 9, 2021，DOI：`10.1109/ACCESS.2021.3053060`，CC BY 4.0。论文式(53)把物理侧PWM与采样的一阶近似变换到同步`dq`坐标，所得电压状态除`(v_ctrl-v_inv)/T_d`外还含`-jω_0v_inv`交叉耦合；这表明团队逐轴局部`dq`一阶滞后与物理`αβ`侧一阶环节不是同一模型。本项目据此把坐标落点作为显式结构变量，而不把两者混称为PWM延时。本地20页PDF：`references/papers/Dokus-Mertens-2021-PWM-delay-state-space-model.pdf`，SHA-256：`FA2443EEFB478FC00AF797F2787E178DF8EA88B5D4CE9BDE2386F2C638CF31E0`。<https://doi.org/10.1109/ACCESS.2021.3053060>
- Shan He, Chao Gao, Zhiqing Yang, Helong Li, Lijian Ding, Frede Blaabjerg, “Enhancing Voltage Control Stability of Grid-Forming VSCs Under PWM Delays: A Study on Feedforward Damping Methods,” *IEEE Transactions on Circuits and Systems I: Regular Papers*, 72(9), 2025，DOI：`10.1109/TCSI.2024.3523196`，作者接收稿为CC BY 4.0。论文把常规采样的控制延时写为`T_d=1.5T_sw/N`，并从内部受控电压源与外部输出阻抗两方面说明PWM延时可导致高频稳定性问题；本项目只采用“高频支路必须与低频外环分开跟踪”和时延定义，不移植其前馈阻尼参数。本地15页作者稿（含资料库封面）：`references/papers/He-et-al-2025-GFM-PWM-delay-feedforward-damping.pdf`，SHA-256：`B3070AD199D7E24B992F86A9E6B7093F91AB7C7105F85A71A5AAF126F14682F4`。<https://doi.org/10.1109/TCSI.2024.3523196>
- Rui Kong, Subham Sahoo, Yubo Song, Frede Blaabjerg, “Damping Control and Improvement of Grid-Forming Inverter from a Wideband Stability Perspective,” *2025 IEEE Applied Power Electronics Conference and Exposition (APEC)*, pp. 696–702，DOI：`10.1109/APEC48143.2025.10977067`。论文在同一宽频模型中先定义纯时延 `G_d=exp(-sT_d)`，再另以一阶惯性环节近似，并以实验考察低频与高频振荡模态的阻尼措施及副作用；本项目据此强化“低频与宽频命名支路分别报告”和“纯时延与一阶近似分别命名”的方法边界，不复制其控制参数。本地9页机构作者稿（含资料库封面）：`references/papers/Kong-et-al-2025-wideband-damping-GFM-APEC.pdf`，SHA-256：`B380186D6DE3951FB505DD562E2593CFC4734EDB20FEE38DF3F6C51C2A2F8877`；未见明确再分发许可，故只存本地研究归档，不进入便携式发行包。<https://doi.org/10.1109/APEC48143.2025.10977067>
- `python-control`：固定版本 `0.10.2`、commit `17d8b0ddc290b592a69a664a1b33c8973a0a9da7`，BSD-3-Clause。项目仅小范围改写 `control.delay.pade` 的方形 `[n/n]` 系数递推并复用其参考向量，不引入完整运行依赖；精选源码、测试、许可证和逐文件SHA-256清单位于 `references/_archive/python-control-0.10.2-selected/`，发行声明另保留上游许可证全文。<https://github.com/python-control/python-control/tree/0.10.2>
- `motulator`：固定版本 `v0.7.5`、commit `a72bc3d521814d9679221265e173ac832aa9a051`，MIT。精选快照保留采样数据说明、整数采样延迟、零阶保持及仿真调用顺序，用作未来离散控制时域对照；它不是连续一阶惯性环节，当前不作为便携式软件运行依赖。清单位于 `references/_archive/motulator-0.7.5-selected/`。<https://github.com/Aalto-Electric-Drives/motulator/tree/v0.7.5>
- `l2ep-epmlab/VSC_Lib`：MIT许可的MATLAB/SimPowerSystem构网与跟网模型库，公开L/LCL、单机与多节点示例；2026-08-21在线核查约50 stars。固定commit `61d1535f9581525a7281bcf3a2b6132862b19054`，已在`references/_archive/VSC_Lib-61d1535-selected/`保存R2021a的14个相关文件及逐文件SHA-256清单。核读确认其平均模型使用`TransportDelay(Output_Delay)`，与团队一阶调制状态不是同一方程；只作为LCL、PLL和输出延迟的结构参照，不引入为便携式软件运行依赖。<https://github.com/l2ep-epmlab/VSC_Lib/tree/61d1535f9581525a7281bcf3a2b6132862b19054>
- `ATayebi/GridFormingConverters`：IEEE 9节点 droop、VSM、matching与dVOC算例代码，约138 stars，但最后代码推送为2020-05-30且仓库未声明SPDX许可；只作论文算例线索，不作为当前依赖。<https://github.com/ATayebi/GridFormingConverters>
- `PowerImpedance.jl`：较新的Julia频域分析项目，公开GFM/GFL、线路电缆和广义奈奎斯特/相位移分析能力；2026-08-21在线核查约9 stars、GPL-3.0。方向相关但社区与项目成熟度尚不足以替代当前作者基线或Sienna固定参照。<https://github.com/Electa-Git/PowerImpedance.jl>

本轮阶段决策见 `docs/research/next-stage-online-review-2026-08-21.md`。GitHub stars与更新时间只用于维护性筛查，不构成模型验证。

## 研究价值与候选改进核查补充（2026-10-01）

- Zhongze Li, Xiaoyu Peng, Xi Ru, Zhaojian Wang, Jianxin Zhang, Yingshang Liu, Feng Liu, “When Can Phasor-Domain Device Models Be Trusted for Electromechanical Stability Analysis of Grid-Forming Converter-Dominated Microgrids?”, arXiv:2606.08082v1，2026-06-06，预印本。以结构化不确定性和结构奇异值充分条件评估理想内环跟踪降阶模型的有效性，并提供模型/测量权重构造。本地PDF：`references/papers/Li-et-al-2026-GFM-model-validity-arxiv-2606.08082v1.pdf`，2,982,451 bytes，SHA-256：`C71B071F304BA9A3E24FBFB4ED336B9CCA10E0A7D296F3CFB61B21B7AF42D33D`。已核对首面题名、作者与版本，并阅读官方HTML的问题表述与结论；未复现算法。<https://arxiv.org/abs/2606.08082v1>
- Diego Cifelli, Adolfo Anta, “Partitioned Mixed Small Gain-Phase Decentralized Stability Criterion for Power Systems”, arXiv:2608.03641v1，2026-08-04，预印本。允许同频率下不同设备子集分别满足增益和相位条件，以网络二次约束耦合，并给出界限选择算法；包含GFM/GFL两机及IEEE39算例。它是原论文作者的独立后续工作，不是arXiv:2510.20544的v2。本地PDF：`references/papers/Cifelli-Anta-2026-partitioned-gain-phase-arxiv-2608.03641v1.pdf`，764,886 bytes，SHA-256：`7B953B6FCFF35F07097F4783AEA9F9038CA80A29F1FBAEE0E533920D26275FCD`。已核对首面题名、作者与版本，并阅读官方HTML的判据、参数选择与结论。<https://arxiv.org/abs/2608.03641v1>
- 分组判据作者代码：<https://github.com/diegoCifelli/Partitioned-Mixed-Small-Gain-Phase-Decentralized-Stability-Criterion-for-Power-Systems>。固定提交 `3ab48eb782f7b0150f949968705d802405e2cd32`（提交时间2026-07-22T13:47:35Z），本地快照 `references/_archive/Cifelli-Anta-partitioned-3ab48eb782f7/`。原始ZIP为104,352 bytes，SHA-256：`8AE633BBD31A541A299975569F7B0604D6545FA6AFCF27F737A120A6AE7068CC`；保留全部22个源码文件、两机/IEEE39工作簿及许可。MATLAB/Control System Toolbox、Simplus、YALMIP、SDPT3依赖；顶层MIT，定制Simplus模型BSD-3-Clause。本轮完成归档，尚未执行或移植。两篇PDF、ZIP及逐文件清单见 `references/manifests/research-snapshot-2026-10-01.json`。

研究建议及失败条件见 `docs/research/research-value-and-software-direction-2026-10-01.md`。两篇PDF只作本地研究归档；SHA-256是下载身份记录，尚无上游可信哈希用于一致性比较。既有核心论文v2/作者v1.0.0及原实验结果未改写。

## 扩展文献：模态诊断、模型适用性与开放接口（2026-10-01）

本轮选读相关方法与结论，未运行或移植新算法。四篇PDF的路径、下载地址、版本、页数、字节数和SHA-256统一登记在 `references/manifests/expanded-literature-2026-10-01.json`；用途、假设和阅读范围见 `docs/research/expanded-literature-and-software-priorities-2026-10-01.md`。原始论文保持只读，仅用于本地研究，不默认纳入发行包或推送GitHub。

- Yue Zhu, Yunjie Gu, Yitong Li, Timothy C. Green，*Impedance-based Root-cause Analysis: Comparative Study of Impedance Models and Calculation of Eigenvalue Sensitivity*，arXiv:2204.01608v1，2022-04-04。固定预印本13页，3,401,466 bytes；SHA-256 `5DE9CC5EF7AE8B8AFCE31A22F38969F68E9F67BFD6677F4F59901B0F3C242D82`。可借鉴设备/参数层面的方向灵敏度；局部预测不替代大步参数改动及全部模态重算。<https://arxiv.org/abs/2204.01608v1>
- Juho Määttä, Jarno Kukkola, Janne Seppänen, Marko Hinkkanen，*Open-Source Python Tool for Grid Converter Output Admittance Identification*，arXiv:2607.10653v1，2026-07-12。8页，599,799 bytes；SHA-256 `499C4EDA9FAC4DA005492639C9F4FB76603C9051A4EB4CA2EFAADF0CD19B2504`。motulator提供MIT实现和官方示例；论文DO-GFM不等于团队VSM，新辨识实现也不等于既有v0.7.5采样/延迟精选快照。作者说明精确复现使用专门归档分支，本轮未取得固定新源码提交或执行。<https://arxiv.org/abs/2607.10653v1>
- Olaoluwapo Ajala, Nathan Baeckeland, Brian Johnson, Sairaj Dhople, Alejandro Domínguez-García，*Model Reduction and Dynamic Aggregation of Grid-Forming Inverter Networks*，IEEE Transactions on Power Systems，38(6)，5475–5490，2023；DOI `10.1109/TPWRS.2022.3229970`。本地为16页接收作者稿，5,004,955 bytes；SHA-256 `B8A0EF35183FF0C6A6206EBB77448BE8084698B760D8CE6A9B6DB8A25ED7F660`。保存网络电流与限流参考动态的结构化降阶；动态约简、聚合和奇异摄动各有假设，不能直接推广到任意RL网络/团队三状态模型。<https://experts.umn.edu/en/publications/model-reduction-and-dynamic-aggregation-of-grid-forming-inverter-/>
- Endalkachew Degarege Almawu, Federico Cecati, Marco Liserre，*Robust Stability Analysis of Grid-Forming Converter-Dominated Grids Using Grey-Box Modelling Approach*，Energies，18(3)，587，2025；DOI `10.3390/en18030587`，CC BY 4.0。22页，8,062,177 bytes；SHA-256 `87FB3663C8374C227A220D0AA18B0DB8C6BDCC707D76BE7997B9C5EDF91B06AA`。借鉴未知控制环节的不确定性建模和名义/鲁棒稳定区别；不沿用其算例SCR界限或假定权重覆盖所有控制器。<https://doi.org/10.3390/en18030587>
- 待补读：Feifan Chen等，*Limitations of Using Passivity Index to Analyze Grid–Inverter Interactions*，IEEE Transactions on Power Electronics，39(11)，14465–14477，2024，DOI `10.1109/TPEL.2024.3428403`。仅核对作者机构元数据与摘要；全文下载未完成，残片移到临时目录，不列为已保存PDF，也不据摘要宣称已核对具体方法。<https://vbn.aau.dk/en/publications/limitations-of-using-passivity-index-to-analyze-grid-inverter-int/>

## 参数信息补充试验的最近邻与数学依据（2026-10-03）

以下三个作者站点PDF已实际下载、解析，标题与相关章节已核对；身份和阅读范围登记在 `references/manifests/parameter-information-literature-2026-10-03.json`。PDF仅在`references/papers/`本地归档，Git忽略，不包含在发行包，尚未建立再分发授权。

- Daniel Golovin、Andreas Krause、Debajyoti Ray，*Near-Optimal Bayesian Active Learning with Noisy Observations*，2010，9页。EC²是为确定等价类别而逐次获取信息的直接近邻；本项目不能将“少问几个参数”本身认定为原创。已读第1—3节，不把其有限假设及噪声理论保证移用于本项目连续矩阵族。<https://www.cs.cmu.edu/~dgolovin/papers/nips10.pdf>
- X. Bombois、G. Scorletti、M. Gevers、P. M. J. Van den Hof、R. Hildebrand，*Least costly identification experiment for control*，2006年5月16日作者预印本，12页。已读引言及问题建模；体现满足控制性能后不必继续追求辨识精度的成本思想，物理辨识试验与索取参数不是同一行动。<https://perso.uclouvain.be/michel.gevers/PublisMig/LCID_final.pdf>
- Oliver Mason、Robert Shorten、Selim Solmaz，*On the Kalman-Yacubovich-Popov lemma and common Lyapunov solutions for matrices with regular inertia*，2006年7月生成的作者稿，22页；最终出版元数据未查定。已核第2.3定理（第8—9页）：严格Lyapunov不等式联系P与−A的惯性。未将其特殊伴随形式、秩一差矩阵对的后续定理套用到GFM模型。<https://www.hamilton.ie/selim/General_Matrix_Inertia_Result_3July06.pdf>

## 创新概念与研究方法补充（2026-10-03）

- Mark A. Runco、Garrett J. Jaeger，*The Standard Definition of Creativity*，Creativity Research Journal，24(1)，92—96，2012，DOI:10.1080/10400419.2012.650092。用于区分原创性与有效性，阅读范围为开篇及相邻讨论，非普适创新标准的实验证明。已保存PDF，7物理页（含封面），187,959 bytes。<https://disf.org/files/doc/2012runcojaegerstandarddefinition.pdf>
- OECD，*Frascati Manual 2015*，第2章§2.6—2.17。用于区分新增知识与例行修改、记录可复现研究条件，不替代大创验收规范。已保存PDF，402页，4,974,093 bytes，未通读全书。<https://www.oecd.org/en/publications/2015/10/frascati-manual-2015_g1g57dcb.html>

上述下载身份、阅读范围及哈希登记在`references/manifests/innovation-methodology-2026-10-03.json`。科学哲学、企业创新定义和控制更新错位的技术来源及阅读限制见`docs/research/brainstorming-session-2026-10-02.md`本日再议节；未完成的技术PDF下载不登记为完整归档。这里修正的是研究筛选方法，不表示新机制已经发现。

## 虚拟电抗频率反馈候选的核查资料（2026-10-03）

- Yicheng Liao、Xiongfei Wang、Frede Blaabjerg，*Passivity-Based Analysis and Design of Linear Voltage Controllers for Voltage-Source Converters*，IEEE Open Journal of the Industrial Electronics Society，1，114—126，2020，DOI:10.1109/OJIES.2020.3001406，CC BY 4.0。数字延迟与虚拟阻抗联合分析为已有工作；该文忽略慢外环，不能直接套用为本项目VSM反馈结论。本轮已读物理第2—4、8—9页，核对第4、8页版面与图表。完整PDF保存于`references/papers/Liao-Wang-Blaabjerg-2020-voltage-control-passivity.pdf`，14物理页（含机构封面），5,587,144 bytes；SHA-256 `337A84C99A2E57BE0058C059E2E972CB4008ED6AA8627614CDB1B025E30776CF`。本地身份记录，不称已与上游可信摘要校验。<https://vbn.aau.dk/en/publications/passivity-based-analysis-and-design-of-linear-voltage-controllers/>
- Nature Genetics编辑文章*Cause, correlation, conjecture*（2015，DOI:10.1038/ng.3271）与Nature Methods编辑文章*So you're writing a paper*（2017，DOI:10.1038/nmeth.4532），用于结论—证据—方法对应及清楚陈述；不是电力系统技术来源。读取在线相关正文，PDF未下载成功。<https://www.nature.com/articles/ng.3271>；<https://www.nature.com/articles/nmeth.4532>

下载状态、用途和另外两篇技术近邻的有限阅读范围见`references/manifests/virtual-reactance-frequency-literature-2026-10-03.json`；本轮试验、作者模型区别和处置见`docs/research/virtual-reactance-frequency-pilot-2026-10-03.md`。全文原件保持本地，不纳入发行包或自动推送Git。

## 分析变换可用范围与第二候选的文献（2026-10-03）

- Kaustav Dey、A. M. Kulkarni，*Passivity of Electrical Transmission Networks modelled using Rectangular and Polar D-Q variables*，arXiv:2111.15377v1，2021。原件5页、537,699 bytes，SHA-256 `4A0219D5C5412D1B0E23F3C62E2DFB65FA5857421CBE77F2BBA6CB2E98E2CF25`。本轮读物理第2—4页，检查第2页版面；用于说明坐标变换、适当性和极点检查为已有理论背景，不作为新截止频率公式的来源。<https://arxiv.org/abs/2111.15377v1>
- M A Awal、Rahul Chakraborty、David Michaud、Mikko Qvintus、Devin Dilley，*Quantifying Implicit Overload Mandates in Phase Jump Requirements for Grid Forming Inverters*，arXiv:2607.07904v1，2026。原件10页、4,171,616 bytes，SHA-256 `A3639891DCE05A209EC98D39C34C77875ABAB552DE32E66CD39E7F638DA3A69F`。本轮读原始HTML相关第I—VI节、PDF第5—7页，检查第5页版面；第二候选要区分电压跟踪目标最优与功率要求可行，尚未复现其数值门槛或取得同条件反例。<https://arxiv.org/abs/2607.07904v1>

原件均已完整下载并解析，身份／阅读范围见`references/manifests/transformation-admissibility-literature-2026-10-03.json`；本地计算哈希不是上游可信摘要核验。仅本地归档，不纳入发行包，不自动推送。新研究推导、135项试验与独立复核见`docs/research/transformation-admissibility-2026-10-03.md`。

同时核到Cifelli—Anta同名工作的EPSR出版页面 <https://www.sciencedirect.com/science/article/abs/pii/S037877962600903X>，搜索索引给出0.5Hz截止频率片段；网页直接访问403，未取得完整期刊版，不将索引片段冒充全文查重。Chen等2025扩展频域无源理论（DOI `10.1109/TPEL.2024.3488853`）仅查机构摘要，不能据此排除其含有关联结果。以上是本轮新颖性审查的明确缺口，不阻塞特定公式的本地验证，也不允许声称“首次”。

## 轨迹优化核查方法及Awal参数复查（2026-10-05）

- Matthew Kelly，*An Introduction to Trajectory Optimization: How to Do Your Own Direct Collocation*，SIAM Review，59(4)，849–904，2017，DOI `10.1137/16M1062569`。下载的是44页作者站点版本，不是56页出版社排版；990,404 bytes，SHA-256 `A81D9939283EE58A207A6C32A447FAE5DBA46C81116EF023783FDF7DBFB40CF9`。已读§5.1–5.5（物理页11–14）并视觉核页12，用于初始化、网格/误差和优化失败核查，不作为GFM创新性的依据。文件、版本与再分发边界见`references/manifests/trajectory-optimization-methodology-2026-10-05.json`。<https://www.matthewpeterkelly.com/research/MatthewKelly_IntroTrajectoryOptimization_SIAM_Review_2017.pdf>；出版元数据：<https://doi.org/10.1137/16M1062569>。
- SciPy官方SLSQP接口说明：<https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html>；仅使用现有安装依赖与官方接口，没有复制第三方源码或安装新工具。不能把优化器success当作连续时间可行性或全局最优证明。
- Awal2607.07904v1复查：式(15)不含有功下限硬约束，式(17)-(18)为事后功率评价；式(18)/图5明确故障前POI有功，纠正先前“测量点未披露”的笼统提示。R2、Vmax、明确基频、完整LC参数/初态、N与容差仍有精确复现缺口。原PDF本次与既有登记哈希比较通过；当前提交历史仅v1。正文引用的GitHub仓库是PNNL通用模型，不是本篇OCP程序，不能据此宣称所有网上源码均不存在。研究细节及范围见`docs/research/phase-jump-power-feasibility-2026-10-03.md`。

## 可行性阶段补充依据（2026-10-05）

- Stephen Boyd、Lieven Vandenberghe，*Convex Optimization*，Cambridge University Press，2004，作者站点公开PDF第579–580印刷页（物理页593–594），§11.4.1。在线完整读取所需页面，借鉴通过统一松弛最小化最大约束违反的构造；本项目增加非负松弛下界，目标是寻找非严格可行点，且硬有功问题非凸，不套用书中凸优化不可行性/全局最优结论。<https://web.stanford.edu/~boyd/cvxbook/bv_cvxbook.pdf>。
- **下载未完成：** 首次请求仅取得49,152字节后中断，残片移到`tmp/downloads/Boyd-Vandenberghe-2004-Convex-Optimization-incomplete.pdf.part`；一次有上限的替代下载也失败。不列为本地完整PDF，不纳入发行包，不宣称已通读全书。来源和状态见`references/manifests/phase-one-methodology-2026-10-05.json`。

## LC内部约束与功率内近似方法（2026-10-05）

- Jaume Girona-Badia、Eduardo Prieto-Araujo、Oriol Gomis-Bellmunt，*Pairing grid-forming VSC filter topologies with voltage control structures*，International Journal of Electrical Power & Energy Systems，155，109670，2024，DOI `10.1016/j.ijepes.2023.109670`。出版社最终版11页，3,468,217 bytes，2023-11-28在线发布；CC BY-NC-ND 4.0。本地原件`references/papers/Girona-Badia-et-al-2024-filter-control-pairing-109670.pdf`，SHA-256 `3F83183B67492EFA1F47DC79F17C25F1B6D56CE091D9D3FDC0AD1E15A666C12E`。主代理读页1、3–4、8–10，视觉核页3；另一代理读页1–6相关内容，重点§3.2、算法1–2及§5.2。该文已处理内部电流/输入电压限制、滤波器与控制配对和相位跳变测试；不能把这些通用内容作为本项目创新。所读范围未见完全相同的硬POI有功轨迹约束，不意味着已完成穷尽查重。原件仅本地保存，不纳入发行包，不自动推送。出版入口：<https://doi.org/10.1016/j.ijepes.2023.109670>；机构原件：<https://upcommons.upc.edu/server/api/core/bitstreams/a4703edb-ec6a-4c7e-bffe-e0015d23e902/content>。
- Ruusila等，*Grid-Forming and -Following Model Predictive Control for Converters With an LCL Filter*，IEEE Transactions on Industrial Electronics，2026，早期在线，DOI `10.1109/TIE.2026.3686588`。仅读取Aalto官方摘要/元数据；官方12页PDF链接下载403，没有完整本地文件或哈希。摘要提到LCL模型预测控制、参考量限制、软电流约束及故障试验，不能据此判断正文是否覆盖硬有功下限。<https://research.aalto.fi/fi/publications/grid-forming-and-following-model-predictive-control-for-converter/>。
- CVXPY官方`linearize`说明，已读相关段落：凸函数的仿射下界、凹函数的仿射上界在参考点相切；非DCP表达式不保证上下界。此轮自行实现实对称二次型的正负谱分解，不直接对非凸功率调用`linearize`，未安装或运行CVXPY。<https://www.cvxpy.org/api_reference/cvxpy.transforms.html>。
- Luo、Elango、Açıkmeşe，*Remarks on "Successive Convexification: A Superlinearly Convergent Algorithm for Non-convex Optimal Control Problems"*，arXiv:2403.00733v2，2024-03-13。已读官方摘要与版本历史，未读全文、未下载PDF。摘要指出原2018年收敛证明的问题及修订所需更强假设；不能将通用SCvx收敛主张直接套到本项目。<https://arxiv.org/abs/2403.00733v2>。

本轮文献阅读范围、下载状态和用途见`references/manifests/lc-hardware-constraints-literature-2026-10-05.json`；实验范围及失败候选见现有相位跳变研究文档。没有以未获取全文、算法名称或代理认同证明创新。

## 有限输入轨迹检查的成熟求解器（2026-10-05）

- Clarabel0.11.1，Apache-2.0，采用官方Python直接锥接口，不复制第三方实现源码。已读取问题格式、矩阵符号、SOC类型、二次目标、时间/线程/容差选项及状态说明：<https://clarabel.org/stable/python/getting_started_py/>、<https://clarabel.org/stable/api_settings/>。`AlmostSolved`只允许送审数值候选，不自动判为物理可行或最优。
- 官方PyPI固定版本元数据：<https://pypi.org/pypi/clarabel/0.11.1/json>。Windows wheel `clarabel-0.11.1-cp39-abi3-win_amd64.whl`，887,310 bytes，2025-06-11发布；SHA-256 `557D5148A4377AE1980B65D00605AE870A8F34F95F0F6A41E04AA6D3EDF67148`与元数据期望值实比一致。原件位于项目tmp/research-conic-wheels，隔离安装于tmp/research-conic-env，安装清单RECORD/许可证原件保留；详细版本与边界见`references/manifests/lc-conic-solver-2026-10-05.json`。
- 官方CVXPY求解器功能表在线核对Clarabel的二阶锥能力，但本轮没有安装/运行CVXPY：<https://www.cvxpy.org/tutorial/solvers/>。可选应用运行环境查询无返回后终止等待，改用已知解释器和临时隔离环境，不把工具延迟当研究阻塞。

成熟求解器、凹下界、端点等式消元均不作为新方法主张。原论文全文、硬件参数恢复和新场景确认的缺口仍按研究文档记录；没有新增付费服务、MATLAB会话、正式依赖或发行包。

## 工程接线与含变流器潮流/短路方法（2026-10-06）

### 普通导线与计算节点转换（2026-10-07）

- pandapower官方固定版本文档：[v3.3.3 Switch](https://pandapower.readthedocs.io/en/v3.3.3/elements/switch.html)。核读零阻抗闭合母线连接的内部节点合并、与小阻抗替代的区别；本项目只借鉴等电位节点合并思路，没有复制库源码、安装依赖或接入开关/潮流/短路服务。
- 本地HTML快照：`references/software-docs/engineering-connection-20261007/pandapower-switch-v3.3.3.html`，21429 bytes，SHA-256 `9C8A061BF44F57A5738376DF3ACE452E8B120C9649E6E765F3F9E153A16847C7`。已核对文件实际包含母线合并说明；哈希仅记录本地快照，不冒称与出版方可信期望值完成完整性验证。
- 实施和适用范围见`docs/software/NETWORK_EDITOR.md`与`results/test-reports/2026-10-07-network-connection-semantics.md`。属于工程输入表达与现有模型编译，不表述为新的稳定性研究方法。

- pandapower 官方稳定版文档（页面显示 3.5.5）：[Generator](https://pandapower.readthedocs.io/en/stable/elements/gen.html)、[Current Source Elements](https://pandapower.readthedocs.io/en/stable/shortcircuit/current_source.html)。核读 PV 节点定义、输入/输出、无功限值转换，以及 full-converter 电流源模型完整说明。前者可支持明确假设下的网络稳态近似，后者是给定倍率/相角的故障电流等值；均不能直接代表 GFM 的全部控制、限流切换与故障恢复。没有下载/复制库源码，没有安装或正式接入，无可声称的第三方代码固定版本/本地哈希。
- X. Lyu、W. Du、S. Mohiuddin、S. Nandanoori、M. A. Elizondo，*Criteria for Grid-Forming Inverters Transitioning Between Current Limiting Mode and Normal Operation*，IEEE Transactions on Power Systems 39(4)，6107-6110，2024，DOI `10.1109/TPWRS.2024.3402012`。本轮仅读 [PNNL 官方摘要及元数据](https://www.pnnl.gov/publications/criteria-grid-forming-inverters-transitioning-between-current-limiting-mode-and-normal)；摘要区分限流模式退出与故障恢复，并列出优先级、圆形限流、虚拟阻抗及 EMT 核查。未获取全文、未下载 PDF、未复现其判据，不将摘要当全文查重依据。
- 用户提供的两张工程接线 PDF 保持本地原件。R7 局部选择 G1、T1、220 kV I/II 段、分段开关组和 L1；原件 SHA-256 `97e7ec4340cde3ae512cf70ff984318fa7ad47989d0404366bff434c109489a4` 仅用于来源身份记录，不冒充上游完整性校验。结构草稿及参数缺项见 `examples/engineering-main-connection/r7-subnetwork-draft.json` 和 `docs/design/r7-subnetwork-parameter-gaps-2026-10-06.md`。不复制课程原始 PDF、私人会话或图纸渲染产物入 Git。

方法选择、现有 PV 潮流原型与平均值模型工作点的差别，以及本轮实施范围见 `docs/design/converter-power-flow-short-circuit-feasibility-2026-10-06.md`。本轮不宣称通用潮流/短路已接入，也不由工程输入功能推定研究创新。
