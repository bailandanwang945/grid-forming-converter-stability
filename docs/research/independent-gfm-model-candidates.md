# 独立构网型变流器模型候选调研

## 1. 调研目的与约束

本文档用于选择论文作者代码之外的构网型变流器模型。候选模型的用途不是替代论文基线复现，而是检验稳定性判据及数值算法是否依赖作者代码的具体实现。

选择模型时采用以下约束：

- 项目身份为天津大学本科生市级大学生创新训练项目，模型必须能够在中期检查和结项答辩前复现，并由项目成员说明其物理含义；
- 固定运行环境为 MATLAB/Simulink R2024b；
- 优先采用平均值模型、下垂控制或虚拟同步机控制，不以高开关频率电磁暂态模型作为参数扫描主模型；
- 必须能够说明交流端口、电流正方向、功率正方向、dq 坐标定义、标幺基值和工作点；
- 研究所需证据至少包括频域 $2\times2$ 导纳、闭环极点和时域扰动响应；
- 外部模型只能作为有版本记录的只读来源，项目派生接口和试验脚本应由本项目维护。

初次调研日期：2026-07-16；2026-08-20 补充核查活跃开源动态框架。本文仅依据官方文档、机构数据仓储、作者仓库和论文随附资料进行候选评估。

## 2. 评价方法

候选模型按以下六项评价：

1. **来源与可追溯性**：是否有永久链接、固定发布版本、发布日期和许可条款；
2. **R2024b 适配性**：是否明确支持 R2024b，或存在可在 R2024b 打开的较早固定发布；
3. **模型透明度**：控制结构、dq 坐标和功率方向是否明确；
4. **频域分析可行性**：是否可围绕交流端口定义电压扰动和电流响应，并形成 $2\times2$ 导纳；
5. **稳定性验证可行性**：能否取得闭环极点并进行时域扰动验证；
6. **本科项目成本**：模型初始化、线性化、参数扫描和答辩解释所需工作量是否适当。

“可线性化”不等同于“可以直接导出本项目所需导纳”。即使 Simulink Control Design 能够得到线性模型，仍需先明确交流端口、dq 参考系、扰动注入点、限幅器工作状态和电流符号。

## 3. 候选总览

| 候选 | 来源与固定版本 | 许可证 | R2024b | 线性化与极点 | $2\times2$ 导纳 | 时域成本 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MathWorks `Design and Analyze Grid-Forming Converter` | 官方 GitHub，固定 `23.2.1.4`（R2023b，提交 `a65692b`） | MathWorks 三条款许可，限与 MathWorks 产品共同使用 | 可采用 R2023b 固定发布；不可采用当前 `master` | 原则上可行，需关闭或避开限流等非线性环节后实测 | 官方页面未给出现成 dq 导纳接口，需另建测量适配层 | 中等至较高 | **外部参照模型首选** |
| MathWorks 岛屿微电网下垂控制示例 | R2024b 内置示例；当前文档已演化为多保真度版本 | 随 MATLAB 产品许可 | 是，但必须固定 R2024b 模型副本 | 低保真平均开关模型原则上可线性化；模型级验证待做 | 需隔离单台逆变器并固定公共参考系，改造成本较高 | 低保真约为分钟内，高保真数分钟 | **备用参照模型** |
| Naderi `Dynamic Modeling and Simulation of Interconnected Microgrids` | Mendeley Data V1，2022-11-18，DOI 固定 | CC BY 4.0 | 未明确；使用 SimPowerSystems，需在 R2024b 实测 | 随附独立小信号 `.m` 文件，闭环特征值分析条件最好 | 数据页未说明单机端口导纳，不能假定可以直接取得 | 中等 | **极点与时域交叉验证候选** |
| Imperix TN168/TN169/TN170 | 技术说明 TN168，2024-01-30；关联下垂与 VSG 说明 | 下载模型许可未在技术说明中明确给出 | MATLAB/Simulink R2016a 以上；另需 ACG SDK 2024.2 以上 | 可研究，但专用块集和硬件实现结构增加线性化成本 | dq 电压、电流接口清楚；仍需建立交流端口频响测量 | 中等至较高 | **用于接口和控制整定参考，不作基线** |
| Sienna `PowerSimulationsDynamics.jl` | `v0.16.2`，commit `dfb56d8` | BSD-3-Clause | Julia，不依赖 MATLAB | Test 08 为19状态 VSM—无穷大母线并核对特征值与 PSCAD 频率；Test 23 为15状态下垂 GFM 并核对 PSCAD 相角 | 可从公开组件构造端口响应，仍需冻结坐标与基值 | 中等 | **第三方动态实现参照首选** |
| JuliaEnergy `PowerDynamics.jl` | `v5.0.0`，commit `b46f595` | 以 MIT 为主，个别文件 MPL-2.0 | Julia，不依赖 MATLAB | 方程式组件可符号组装和线性化 | L/LC/LCL、双闭环、虚拟阻抗和端口方向透明 | 中等 | **方程审计首选，不先作为产品依赖** |
| `Different-Inverter-Control-Models-Simulink` | GitHub 默认分支；File Exchange 标为 1.0.0，2025-12-25 | GitHub 仓库未见许可证文件 | 作者声明需要 R2024b 与 SPS | 未提供线性化工作流；仓库仅有少量提交和说明 | 未说明 | 可能较低，但审计成本高 | **暂不采用** |
| `Microgrid Dynamic Operation` | File Exchange 1.0.2，2023-10-26 | File Exchange 提供许可入口，但公开列表未解析出正文 | 官方列示仅兼容 R2020a--R2021a | 未提供线性化或极点流程 | 未说明 | 中等 | **因版本不符淘汰** |

## 4. 候选详细评价

### 4.1 MathWorks：Design and Analyze Grid-Forming Converter

**来源与版本。** MathWorks 官方示例自 R2023b 提供，支持下垂控制和虚拟同步机控制，包含 500 kVA、415 V、50 Hz 构网型变流器、升压变压器、线路、局部负荷和电网，并可改变短路比、X/R 比、功率给定、孤岛状态及故障条件。[官方示例说明](https://www.mathworks.com/help/sps/ug/design-analyze-gridforming-converter.html) 当前 GitHub 仓库已经转向 R2025b 及以后，不能把当前 `master` 作为 R2024b 基线。发布页仍保留 R2023b 固定发布 `23.2.1.4` 和提交 `a65692b`，应以该发布作为候选版本。[官方发布记录](https://github.com/simscape/Power-Converter-Circuit-Control-Simscape/releases)

**许可证与工具箱。** 仓库使用 MathWorks 三条款许可，允许修改和再分发，但衍生物仅可与 MathWorks 产品和服务共同使用。[许可证原文](https://github.com/simscape/Power-Converter-Circuit-Control-Simscape/blob/master/License.txt) 官方页面列出 Simulink、Simscape、Simscape Electrical、Simulink Control Design、Control System Toolbox 和 Stateflow。本机 MATLAB MCP 已核验 R2024b 中上述产品均已安装。

**分析适用性。** 该模型的优势在于物理场景完整、SCR 和 X/R 可直接配置、下垂与 VSM 可在同一平台比较，并已有 13 类时域试验。它适合验证“参数变化是否产生相同的时域趋势”。不足是公开页面没有定义本项目需要的 dq 交流端口导纳，也未说明可直接线性化的工作点和分析 I/O。模型还包含虚拟阻抗、限流、故障和状态逻辑；在非线性环节进入限幅时，小信号线性化结果不能直接代表扰动后的大信号行为。

**预估工作量。** 若仅运行正常工况和功率阶跃，成本中等；若要求从物理网络中隔离变流器、构造固定同步坐标系的 $v_{dq}\rightarrow i_{dq}$ 频响、处理 Simscape 代数状态并核对电流方向，成本较高。因此该模型适合作为独立时域参照，不宜直接成为项目的唯一分析模型。

### 4.2 MathWorks：岛屿微电网下垂控制示例

**来源与模型结构。** 当前官方示例包含两台下垂控制逆变器和多保真度变体；低保真变体使用平均开关，高保真变体逐个表示开关器件。官方说明明确指出，每台逆变器的下垂控制产生 d、q 轴电压参考值，低保真模型适合快速控制迭代。[官方示例说明](https://www.mathworks.com/help/slcontrol/ug/islanded-microgrid-using-droop-control.html)

**版本演化风险。** R2024b 中的旧示例与当前“多保真度”模型不应混为同一不可变模型。MathWorks 支持答复确认 R2024b 示例的 dq 轴选择和电流前馈形式与其引用论文并非逐项相同，并给出了该示例采用的功率关系：$P=V_qI_q+V_dI_d$、$Q=V_qI_d-V_dI_q$。[R2024b 模型差异说明](https://uk.mathworks.com/matlabcentral/answers/2178526-why-are-there-differences-between-the-microgrid-islanded-operation-example-in-simulink-r2024b-and-th) 这说明选用该模型时必须保存 R2024b 模型副本、文件校验值及实际接口说明，不能仅引用会随版本更新的在线页面。

**分析适用性。** 低保真平均开关有利于线性化和参数扫描，dq 功率关系也较明确。但该示例是两台逆变器共同形成的孤岛微电网，并非单机接无限大母线。要取得单台装置 $2\times2$ 导纳，必须隔离单机、指定全系统公共同步角、固定另一台装置或网络的扰动响应，并说明由谁形成参考坐标。该改造比搭建透明的单机平均值模型更难解释。

**结论。** 可作为下垂控制时域对照或参数整定参考，不作为主导纳模型。

### 4.3 Naderi：Dynamic Modeling and Simulation of Interconnected Microgrids

**来源与许可。** 数据集由 University of Kurdistan 的 Mobin Naderi 发布于 Mendeley Data，固定版本为 V1，发布日期为 2022-11-18，永久标识为 [DOI: 10.17632/p5h576s247.1](https://data.mendeley.com/datasets/p5h576s247/1)，采用 CC BY 4.0。

**模型内容。** 数据集包含一份小信号 MATLAB 文件和一份 Simulink 模型：系统由两台下垂控制构网型 DER 与一台 PQ 控制 DER 组成。数据页明确说明小信号文件可以独立运行，Simulink 模型用于暂态稳定性和控制验证；这为“解析小信号模型的闭环特征值—Simulink 时域响应”的交叉验证提供了现成结构。其相关综述发表于 Applied Energy，并说明该数据集用于支持动态建模与稳定性研究。[相关同行评议论文](https://doi.org/10.1016/j.apenergy.2023.120647)

**限制。** 数据集使用 MATLAB/SimPowerSystems，但未声明创建版本及 R2024b 兼容性；也没有在元数据页说明 dq 坐标定义、功率正方向和单机端口导纳。虽然随附状态空间模型非常适合极点分析，但不能在未检查源文件前宣称可直接导出本项目要求的 $2\times2$ 导纳。

**结论。** 若后续只下载一个学术模型做独立交叉验证，该数据集优先级较高。它更适合承担“闭环极点与时域响应一致性验证”，不承担交流端口导纳基线。

### 4.4 Imperix：TN168/TN169/TN170

**来源与接口。** Imperix TN168 给出可引用 DOI、滤波器参数、双闭环 dq 电压电流控制、控制延迟、PI 整定公式和实验结果，并提供 Simulink 模型。其输入为形成电压的幅值和频率参考，正文明确描述 d、q 轴耦合及解耦控制；关联 TN169 和 TN170 分别讨论比例下垂和虚拟同步机。[TN168 技术说明](https://doi.org/10.66800/0168)

**依赖与许可。** 模型要求 Imperix ACG SDK 2024.2 以上、MATLAB/Simulink R2016a 以上，离线仿真还需 Simscape Electrical。技术说明公开了下载入口，但没有在页面中给出下载模型的明确开源许可证。因此它适合被引用为接口、参数和实验依据，不适合在未确认许可前复制进本项目仓库。

**分析适用性。** dq 接口与物理参数比多数演示模型清楚，且具有实物试验结果；但 ACG SDK 专用块、控制离散化和硬件代码生成结构会增加线性化与持续集成成本。若项目目标是低频稳定性而非控制器部署，引入该依赖得不偿失。

### 4.5 不建议采用的社区模型

`Different-Inverter-Control-Models-Simulink` 同时包含 VSG、下垂、功率同步和其他控制方法，并明确面向 R2024b 与 Specialized Power Systems。[File Exchange 条目](https://www.mathworks.com/matlabcentral/fileexchange/182913-different-inverter-control-models-simulink) 但其 GitHub 仓库没有固定 release，提交历史很短，且未见许可证文件；因此不能仅因“能够运行”就作为可归档、可修改的正式模型。[GitHub 仓库](https://github.com/mshasan4003/Different-Inverter-Control-Models-Simulink)

`Microgrid Dynamic Operation` 的版本为 1.0.2，公开页面明确列示兼容范围仅为 R2020a--R2021a；在 R2024b 项目中使用会引入升级和行为差异风险，故淘汰。[File Exchange 条目](https://www.mathworks.com/matlabcentral/fileexchange/93235-microgrid-dynamic-operation)

### 4.6 Sienna 与 PowerDynamics 开源动态框架

2026-08-20 对用户解压完整包的核查改变了“外部参照必须来自 MATLAB”的早期假设。Sienna `PowerSimulationsDynamics.jl v0.16.2` 的 Test 08 是19状态 VSM—无穷大母线模型：同时核对初始化、小信号特征值，并用 ResidualModel/IDA 与 MassMatrixModel/Rodas5 两条数值路径比较同一 PSCAD 频率波形，测试门为 `||ω-ω_PSCAD||≤1e-4`。Test 23 则是15状态下垂型构网变流器，核对特征值并比较 PSCAD 相角。完整包含参考 CSV 和 PSCAD 工程，不只是测试脚本。它比一般社区 Simulink 文件更适合回答“我们的动态实现是否与另一套透明实现一致”。[固定发布](https://github.com/Sienna-Platform/PowerSimulationsDynamics.jl/tree/v0.16.2) [Test 08](https://github.com/Sienna-Platform/PowerSimulationsDynamics.jl/blob/v0.16.2/test/test_case_VirtualSynchMachine.jl) [Test 23](https://github.com/Sienna-Platform/PowerSimulationsDynamics.jl/blob/v0.16.2/test/test_case_droopinverter.jl)

`PowerDynamics.jl v5.0.0` 的 `ComposableInverter` 将滤波器、dq 双闭环、虚拟阻抗、下垂和坐标变换直接写成方程式组件，与团队16状态模型的结构接近。该来源适合逐式检查单位、符号、前馈和端口方向；但 v5 新组件不能仅凭2022年的框架论文被称为逐组件实验确认。[固定发布](https://github.com/JuliaEnergy/PowerDynamics.jl/tree/v5.0.0) [组件源码](https://github.com/JuliaEnergy/PowerDynamics.jl/blob/v5.0.0/src/Library/Renewables/ComposableInverter.jl)

这两个项目都不应立即成为交付软件的 Julia 运行时依赖。第一步只读取固定版本建立方程映射；只有映射显示工况能够公平比较后，才在隔离环境优先运行 Sienna Test 08，并以 Test 23 辅助拆分外环与共同内环结构。

## 5. 版本更迭对选择的影响

### 5.1 不采用滚动默认分支

MathWorks 的 `Power-Converter-Circuit-Control-Simscape` 当前默认分支已要求 R2025b 以上，而项目环境为 R2024b。后续如取得该模型，必须固定 R2023b 发布 `23.2.1.4`、提交 `a65692b`，记录下载日期、文件清单和 SHA-256；不得在复现实验中自动跟随 `master`。

### 5.2 R2024b 是旧 SPS 模型的最后阶段性适用环境，而不是长期接口

部分学术和社区模型依赖 Specialized Power Systems。MathWorks 已在 R2026a 移除该技术，并提供 `spsConversionAssistant` 迁移到原生 Simscape Electrical。[官方发布说明](https://www.mathworks.com/help/sps/release-notes.html) 因此：

- 在本项目周期内，可以利用固定的 R2024b 环境复现 SPS 模型；
- 新建的项目主模型不宜继续依赖 SPS，以免模型与未来 MATLAB 版本绑定；
- 若使用 SPS 外部模型，只把它作为只读验证对象，不在其上发展项目核心算法；
- 答辩材料应明确“运行环境固定为 R2024b”，避免把版本兼容性误写为方法本身的普适性。

### 5.3 在线文档不是模型版本凭证

岛屿微电网示例已经发生结构演化。正式实验必须记录本地模型文件、MATLAB 版本、模型保存版本和校验值；在线帮助页面只用于说明模型意图，不能代替本地版本证据。

## 6. 推荐方案

### 6.1 推荐的两层模型体系

本项目不应把某一个大型外部 Simulink 模型同时用于算法开发、导纳计算、极点分析和时域验证。建议采用两层结构：

1. **项目自建的透明平均值 dq 模型作为独立分析模型。** 模型只保留直流侧等效源、调制器平均环节、LC/LCL 滤波器、dq 电压电流内环、下垂或 VSM 外环以及电网阻抗。所有状态、端口、符号和基值由本项目定义。该模型负责导出 $2\times2$ 导纳、闭环极点和参数扫描，是结项答辩中需要由成员完整解释的核心模型。
2. **固定版本的外部模型作为独立参照。** 首选 MathWorks R2023b GFM 示例 `23.2.1.4` 验证 SCR、X/R、下垂/VSM 参数变化下的时域趋势；若需要验证“解析特征值—Simulink 暂态”的一致性，再评估 Naderi Mendeley Data V1。

这不是重复建模。自建模型保证数学接口可审计，外部模型用于检验主要结论是否依赖自建实现。

### 6.2 外部候选的优先级

1. **第一优先：MathWorks R2023b GFM 固定发布。** 权威性、场景完整性、R2024b 可适配性和答辩可接受度最好；仅作为时域参照，不强行承担导纳提取。
2. **第二优先：Naderi Mendeley Data V1。** 有 DOI、固定版本、CC BY 4.0 和独立小信号文件，适合极点与时域交叉验证；下载前先做 R2024b 兼容性预检。
3. **第三优先：MathWorks R2024b 岛屿微电网示例。** 低保真平均开关适合快速试验，但多机公共参考系使单机导纳提取复杂，仅作备用。
4. **参考而非模型基线：Imperix TN168--TN170。** 用于核对 dq 内环、控制延迟、参数量级和实验现象，不引入 ACG SDK 依赖。

### 6.3 淘汰原则

出现下列任一情形时，不进入正式模型基线：

- 无明确许可证；
- 只有默认分支而无固定提交或发布版本；
- 仅给出仿真截图，缺少参数、接口或可执行模型；
- 需要项目未安装的专用硬件块集，且不能以普通 Simulink/Simscape 仿真替代；
- 无法说明 dq 坐标、电流方向或标幺基值；
- 为取得 $2\times2$ 导纳必须大规模改写第三方模型，以致模型来源和项目改动无法区分。

## 7. 下载前的核验门槛

本轮不下载模型。进入下一阶段前，应按以下顺序执行：

1. 先完成项目自建平均值模型的接口规范，冻结 $v_{dq}$、$i_{dq}$、功率和坐标变换定义；
2. 仅下载一个首选外部候选到隔离目录，记录来源 URL、发布标签或 DOI、SHA-256 和文件清单；
3. 不修改原始模型，先验证打开、更新模型和一个最短时域工况；
4. 检查模型保存版本、缺失产品、初始化脚本、数据字典和回调函数；
5. 只有在最短工况通过后，才建立项目侧适配脚本；
6. 对外部模型只要求复现一至两个能够回答研究问题的工况，不追求完整运行全部演示；
7. 任何频域稳定性结论仍须与闭环极点或时域响应交叉验证。

## 8. 当前结论

在本科市级大创的时间和解释能力约束下，最合理的路线不是寻找一个“功能最多”的现成模型，而是建立一个接口透明、能够导出导纳和状态矩阵的项目自建平均值模型，再用固定版本的 MathWorks 官方 GFM 示例验证时域趋势。Naderi 数据集可作为第二独立来源，但应在 R2024b 兼容性验证通过后再纳入。

因此，当前不建议立即下载多个模型并行试错。下一项与模型有关的工作应是编写自建模型的接口与验证规范；外部下载应等待该规范完成后，仅对首选候选实施一次有门槛的兼容性预检。
