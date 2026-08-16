# 外部资源获取与入库决策

> 状态：持续维护  
> 最后更新：2026-07-16

## 1. 入库门槛

任何外部代码、模型、论文源码或数据在进入 `external/`、`references/source/` 或 `models/` 前，必须记录：

1. 官方/作者 URL；
2. tag 或 release；若无 tag，固定 commit SHA；
3. 下载日期、文件清单和归档 SHA-256；
4. LICENSE 及允许的使用方式；
5. MATLAB release 和工具箱依赖；
6. 最小 smoke test 命令与实际结果；
7. 与团队自研内容的边界。

网络下载、Hermes 或 MCP 不得阻塞主线。网络路径超时后，先记录缺口，继续本地可验证工作。

## 2. 已接受资源

### 2.1 Cifelli–Anta 作者仓库

- 官方仓库：<https://github.com/diegoCifelli/Decentralized-Small-Gain-and-Phase-Stability-Conditions-for-GFM-Converters>
- 固定版本：`v1.0.0`
- commit：`ef67c7a4ac84e4e1142e95b072d241db89eb64ba`
- 许可证：MIT
- 本地位置：`external/cifelli-small-gain-phase`
- 用途：论文基线和对照实现；不得直接修改。

注意：作者的 `GridFormingVSI.m` 是 Simplus 包类替换文件。不能假定把作者仓库根目录加入 MATLAB path 就能覆盖 `+SimplusGT/+Class` 中的类。应使用隔离的 Simplus 工作副本或正确的包目录覆盖层，并用以下命令实测解析顺序：

```matlab
which SimplusGT.Class.GridFormingVSI -all
```

### 2.2 arXiv v2

- 摘要页：<https://arxiv.org/abs/2510.20544>
- 固定 PDF：<https://arxiv.org/pdf/2510.20544v2>
- 固定源码：<https://arxiv.org/e-print/2510.20544v2>
- 许可证：CC BY 4.0
- 本地源码归档 SHA-256：`F1F8DA4256370D255BD3D85B0EFD81832A8941FBA8B7629210AC652C525D3D1E`
- 用途：当前理论定义、公式、算例和图表基线。

## 3. 有条件接受资源

### 3.1 Simplus Grid Tool

- 官方仓库：<https://github.com/Future-Power-Networks/Simplus-Grid-Tool>
- 许可证：BSD-3-Clause
- 状态：官方没有稳定 release/tag；README 版本字符串不能替代 commit SHA。
- 当前缺口：本地快照没有 `.git`，`references/SOURCES.md` 未登记其 commit 或归档 SHA。

处置：

1. 不阻塞分类器和解析矩阵测试；
2. 在 Phase 2 前从官方仓库按具体 commit 重新获取或下载 commit archive；
3. 记录 commit、SHA-256、文件清单和 smoke test；
4. vendor 快照保持只读，论文模型替换通过隔离副本/适配层完成。

### 3.2 MathWorks 官方 GFM 模型

- 文档：<https://www.mathworks.com/help/sps/ug/design-analyze-gridforming-converter.html>
- 仓库：<https://github.com/simscape/Power-Converter-Circuit-Control-Simscape>
- 候选固定版本：`23.2.1.4`，面向 R2023b；项目使用 R2024b，必须先做兼容性 smoke test。
- 2026-08-16 已只读取得该固定发布，提交为 `a65692b004637acb38b2f8c64db7dcf47efe24c7`；`GridFormingConverter.slx` SHA-256 为 `9cd2abfd5699e92336ceb335414403cb29826da7a4f7ab3abafd581d96c6fac4`。外部目录继续由 Git 忽略，项目只提交适配脚本、结果与来源证据。
- 用途：独立时域验证、扰动和稳定/不稳定场景；不能替代团队的小信号导纳和判定实现。
- 风险：工具箱依赖较重，许可证要求与 MathWorks 产品/服务结合使用。

处置：Phase 4 候选，不阻塞作者基线。

### 3.3 MATLAB Central 轻量 VSM/Droop 模型

- 候选：<https://www.mathworks.com/matlabcentral/fileexchange/180383-grid-forming-droop-and-virtual-synchronous-machine>
- 用途：答辩备份或独立模型候选。
- 风险：许可证文本、工具箱依赖和保存的初始条件需要下载后核验。

处置：未完成许可证、SHA 和 smoke test 前不得作为核心依赖。

## 4. 必须自行实现

- 稳健 numerical-range / sectoriality 分类器；
- 尺度化容差和临界状态输出；
- phase bounds、跨 `±π` 处理和采样收敛测试；
- 作者接口适配器与一键实验入口；
- 解析矩阵、回归和集成测试；
- 闭环极点/时域与判据的交叉验证；
- 中期/结项报告、演示与全过程证据。

外部模型只能作为输入与验证对象，不能把“模型能够运行”表述为团队算法贡献。
