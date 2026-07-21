# AGENTS.md - grid-forming-converter-stability

## Canonical workspace

- 本项目的唯一正式工作目录是 `E:\git_Projects\grid-forming-converter-stability`。
- 开始写入前先核对当前任务的 workspace root；若任务绑定到同名或相似的其他目录，不要创建镜像、初始化仓库或写入派生产物，应切换到本目录或明确说明权限限制。
- 项目边界与长期入口优先查询 Hermes；项目研究事实以本目录文档为准。

## Literature sources

- 原始 PDF 位于 `references/papers/`；官方源码快照位于 `references/source/`；来源、版本和校验值登记在 `references/SOURCES.md`。
- 若论文提供与本地 PDF 相同版本的官方 TeX，优先读取 TeX 获取连续正文、公式、引用和图题关系，并用 PDF 核对图表与最终排版。
- 原始源码快照保持只读和可复现；不要为了“整洁”改动其内部相对路径。派生 Markdown、图片和分析结果写入 `output/` 或 `results/`。
- 不默认制作逐页拼接 Markdown。只有用户明确需要 OCR、全文检索副本或审计包时才生成，并清楚标注其派生性质。

## Verification

- 下载或归档外部资料后，至少核对版本、SHA-256 和文件清单；TeX 源码应在隔离输出目录完成一次编译验证。
- 稳定性结论不得只依赖单一数值判据，需与数值域、闭环极点或时域仿真交叉验证。
- 中文学术材料不把 `stability certificate` 生硬直译为“稳定性证书”；按逻辑性质写作“稳定性充分条件”“分散式稳定判据”或“由充分判据确认的参数区域”。
- 不把有限模型和有限精度下的特征根结果称为“真实稳定域”，统一写作“闭环特征根参考稳定域”；数值证据不足的样本单列为“数值待定”，不得强制并入稳定、失稳或判据失败。

## Memory policy

- 不保存原始会话、临时尝试或长篇复盘。只把可复用的项目规则写入本文件，把来源事实写入 `references/SOURCES.md`，把跨项目边界登记到 Hermes registry。
