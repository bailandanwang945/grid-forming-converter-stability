# arXiv:2510.20544v1 source snapshot

论文：Diego Cifelli, Adolfo Anta, “Decentralized Small Gain and Phase Stability Conditions for Grid-Forming Converters: Limitations and Extensions.”

本目录保存与项目 PDF 对应的 arXiv v1 官方源码。源码快照是连续正文、公式、引用和图题关系的首选读取入口；项目 PDF 仍是图表与最终排版的权威版本。

## 目录

- `source/`：官方压缩包的原样展开，共 25 个文件；保持平铺结构以维持上游相对路径和直接编译能力。
- `archive/arxiv-2510.20544v1-source.tar.gz`：原始下载包。
- `SHA256SUMS.txt`：压缩包和展开文件的 SHA-256 校验清单。

## 入口与编译

主文件：`source/main_arxiv.tex`

在 `source/` 中运行：

```powershell
pdflatex -interaction=nonstopmode -halt-on-error main_arxiv.tex
pdflatex -interaction=nonstopmode -halt-on-error main_arxiv.tex
```

正式验证时建议用单独的输出目录，避免把 `.aux`、`.log`、`.out` 和重编译 PDF 混入源码快照。

## 维护约定

- 不编辑 `source/` 内的上游文件；修订、摘录、Markdown 或渲染图写入项目 `output/`。
- 不把 arXiv v2 内容静默混入本快照；若未来采用 v2，应建立新的并列版本目录。
- 阅读优先级：同版本 TeX 负责语义结构，原 PDF 负责视觉核对，逐页文本抽取仅作为显式需要时的辅助产物。
