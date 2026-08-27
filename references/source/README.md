# 论文源码快照

本目录保存与项目核心论文版本严格对应的官方源码，用于可靠读取章节、公式、引用和图题关系。

- `arxiv-2510.20544v1/`：Cifelli 与 Anta 论文的 arXiv v1 源码快照，对应项目归档的 v1 PDF。
- `arxiv-2510.20544v2/`：同一论文的 arXiv v2 源码快照，包含修订后的多机小相位条件和更完整的算例参数；作为当前实现基线。

规则：原始源码只读；版本不可混用；派生文本和渲染结果放入项目 `output/`，不写回源码快照。

在项目根目录运行以下命令，可将 v1/v2 的逐文件 SHA-256 与受信清单逐项比较；缺失、篡改、清单外文件或越界路径都会使进程以非零状态退出：

```powershell
python .\scripts\verify_reference_baselines.py
```

若还要强制核验被 Git 忽略的核心论文 PDF 与完整作者仓库，使用：

```powershell
python .\scripts\verify_reference_baselines.py --strict-local-archive
```

默认模式适用于干净克隆：跟踪的论文源码和作者许可快照必须通过，未随仓库分发的 PDF 与作者仓库会明确报告为“可选本地归档缺失”，不会伪装成已验证。
