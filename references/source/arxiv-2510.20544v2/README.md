# arXiv:2510.20544v2 source snapshot

论文：Diego Cifelli, Adolfo Anta, “Decentralized Small Gain and Phase Stability Conditions for Grid-Forming Converters: Limitations and Extensions.”

本目录保存 arXiv v2 官方源码。v2 是当前理论与算例实现基线；v1 仍并列保留，用于追溯项目最初归档的 PDF 和早期复现结果。

## 目录

- `source/`：官方压缩包的原样展开，共 27 个文件。
- `archive/arxiv-2510.20544v2-source.tar.gz`：原始下载包。
- `SHA256SUMS.txt`：压缩包和展开文件的 SHA-256 校验清单。

## 入口与编译

主文件：`source/main_final.tex`

```powershell
pdflatex -interaction=nonstopmode -halt-on-error main_final.tex
bibtex main_final
pdflatex -interaction=nonstopmode -halt-on-error main_final.tex
pdflatex -interaction=nonstopmode -halt-on-error main_final.tex
```

已在 TeX Live 2026 下验证：编译成功，生成 9 页 PDF，最终无未解析引用。

## 与 v1 的关系

- 新增多机变流器整体相位展宽小于 `pi` 的约束。
- IEEE 14 节点不稳定算例线路由 `8-9` 修正为 `7-8`。
- 补充虚拟导纳参数、滤波截止频率、控制器传递函数及 Zenodo 数据入口。
- 原始源码保持只读；派生产物不得写回 `source/`。
