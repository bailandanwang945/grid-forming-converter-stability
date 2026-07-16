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
