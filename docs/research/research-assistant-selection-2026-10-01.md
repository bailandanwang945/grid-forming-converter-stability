# 科研助手筛选与小范围复用建议

核查日期：2026-10-01。用途：辅助本地电力系统论文与代码核对、提出可检验研究问题；不替代数值计算、理论证明或责任作者判断。

## 结论

建议只读下载 **K-Dense-AI/scientific-agent-skills** 的两个子目录：`skills/hypothesis-generation/`、`skills/scientific-critical-thinking/`。它是供现有 Codex 使用的指令与资料包，不是另一个必须部署的科研代理服务。本轮仅审核，没有下载或安装，也没有执行第三方脚本。

固定提交：`91497e335489dcb544ec8ddc8f6b7ce5fd6d1121`。每个目录应保留其引用的 `references/`、`assets/`、`scripts/`（若有），同时保留根 `LICENSE.md`。不得把单独 `SKILL.md` 当作完整包。

## 候选比较

星数来自核查时 GitHub API，随时间变化；维护判断额外检查实际改动，未把最新 README 日期当作功能维护。

| 候选 | 核查时星数 | 实质维护证据 | 类型与适配判断 |
|---|---:|---|---|
| [Scientific Agent Skills](https://github.com/K-Dense-AI/scientific-agent-skills) | 47,274 | 2026-10-01 有脚本编码兼容修复及测试更新 | 指令包；官方声明兼容 Codex；两项选定技能可本地阅读，无独立服务 |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | 29,860 | 2026-09-26 新增本地关键词上下文筛选与测试 | 完整 Python 服务；适合网页及文档综述，但增加模型、搜索和服务配置；本轮不选 |
| [HKUDS AI-Researcher](https://github.com/HKUDS/AI-Researcher) | 5,772 | 最新 push 为 2025-10-16；近年持续核心维护未核实 | 完整研究代理；示例偏机器学习，依赖 Linux 容器及外部模型；不选 |
| [Sakana AI-Scientist](https://github.com/SakanaAI/AI-Scientist) | 14,647 | 2025-12-19 最新提交主要为许可证；此前功能提交更早 | 完整自主实验框架；官方以 Linux、CUDA/PyTorch 为运行环境，不适合现阶段 Windows 电力模型工作；不选 |

### 许可证、费用与本地输入

- Scientific Agent Skills 仓库为 MIT；所选两项技能也分别标明 MIT。只读方法指导无额外 API/key。`hypothesis-generation` 的辅助脚本声明 Python 3.11+ 标准库、本地确定性运行；本轮没有审核或运行其全部脚本。`scientific-critical-thinking` 的图示为可选项，调用外部生成服务需另行配置；本项目不使用。
- GPT Researcher 为 Apache-2.0，当前版本要求 Python 3.12+。默认示例配置 OpenAI/Tavily key，也支持其他模型端点；模型与搜索可能另收费，不能把 Codex 登录额度视为其 API 额度。官方列 PDF、文本、Markdown 等本地输入；没有本轮核实的 TeX/MATLAB 数值语义核验能力。它不能自动证明公式与实现一致。Windows 原生运行本轮未实测。
- HKUDS 仓库 API 未识别许可证，固定树中也未找到许可证文件；因此不能按“公共 GitHub 即可自由复制”处理。官方示例配置 OpenRouter、GitHub token 和 `linux/amd64` 容器；本轮未验证 Windows，也不接入账户。
- Sakana 当前为专门的 The AI Scientist Source Code License，不能沿用旧 Apache-2.0 印象。官方要求披露自主 AI 生成论文，并提醒框架会执行模型编写的代码。此处不启动，也不将其机器学习实验模板当作 GFM 模型验证。

## 为什么不整体安装

选定的 `hypothesis-generation` 明确要求区分观察、假设、预测、证据和竞争解释，并保留否定结果；`scientific-critical-thinking` 有助于检查“作者已有”“工程包装”“研究增量”的边界。这两项能与现有电力系统复现技能互补，但没有电力系统专项知识保证。

仓库的 `literature-review` 目前要求 `parallel-cli` 并强制 AI 示意图，与本项目不在本地自动生成图、避免扩展工具栈的约束不合，因此不选。GRADE/Cochrane 等医学证据框架也不能直接套到确定性电力系统仿真；只借鉴通用的对照、偏差和论断核查原则。

## 最小整合方案

1. 原始两个技能及根许可证放本地隔离资料目录，记录上游 URL、完整提交、文件清单、SHA-256；先只读，不运行安装器，也不改用户全局技能目录。
2. 研究线阅读必要引用后，将一个候选问题整理为“既有方法—团队增量—可判别实验—失败条件”；应用现有电力模型核查规则，不照搬临床模板。
3. 人机交互线不依赖此包：模型计算仍由正式后端负责，界面不得根据语言模型回答判定稳定性。
4. 如果具体模板有用，再做最小本地派生，并保留许可与差异说明；最终记录进入项目文档入口。整体安装或新科研代理服务不是当前开发前置条件。

## 核查入口

- [Scientific Agent Skills 固定提交](https://github.com/K-Dense-AI/scientific-agent-skills/tree/91497e335489dcb544ec8ddc8f6b7ce5fd6d1121)
- [hypothesis-generation 固定源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/91497e335489dcb544ec8ddc8f6b7ce5fd6d1121/skills/hypothesis-generation/SKILL.md)
- [scientific-critical-thinking 固定源码](https://github.com/K-Dense-AI/scientific-agent-skills/blob/91497e335489dcb544ec8ddc8f6b7ce5fd6d1121/skills/scientific-critical-thinking/SKILL.md)
- [编码修复提交](https://github.com/K-Dense-AI/scientific-agent-skills/commit/a0aea743b3059cbae85ae4ba861cc6b2c0d1e083)
- [GPT Researcher 功能维护提交](https://github.com/assafelovic/gpt-researcher/commit/2906e63275788d1252d59194d6e06dc4aace116e)
- [HKUDS 当前固定提交](https://github.com/HKUDS/AI-Researcher/tree/f9a6f8480860c193afff600eeffe3defcee8a978)
- [Sakana 当前固定提交](https://github.com/SakanaAI/AI-Scientist/tree/1de1dbc1f4ee2c5f61e9c94348d55eb51d7fa2eb)

边界：星数与提交不能证明研究正确性；兼容声明不等于本机运行验证。本轮推荐只读复用的方法资料，不保证产生原创理论。
