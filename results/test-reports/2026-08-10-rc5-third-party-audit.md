# v0.3.0-rc5 软件与第三方组件审计测试报告

## 1. 验收对象

- 软件版本：`v0.3.0-rc5`；
- 验收日期：2026-08-10；
- 范围：Python 后端、React/TypeScript 前端、开发态一键启动、真实浏览器流程、MATLAB 研究测试、Windows 候选包和第三方组件清单；
- 边界：本报告不评价学院提交材料，不修改或复核答辩 PPT/PDF，也不替代另一台无开发环境电脑上的断网验收。

## 2. 统一验收结果

| 阶段 | 结果 | 主要证据 |
|---|---:|---|
| Python 单元与接口测试 | 62 Passed / 0 Failed | 新增包内相对许可路径与开发依赖排除测试；原 Fig. 8、同域对照、低频模型、报告、扫描、发布和证据复核回归保持通过 |
| 前端生产构建 | PASS | 2171 个模块；主 JavaScript 约 776.89 kB，gzip 后约 258.13 kB |
| 开发态启动器 | PASS | 前后端启动、健康检查与自有进程退出通过 |
| 真实浏览器端到端流程 | PASS | Fig. 8、同域对照、独立模型、扫描、案例往返和报告导出路径通过 |
| MATLAB 研究测试 | 128 Passed / 0 Failed / 0 Incomplete | 统一 MATLAB 测试入口通过 |

汇总：`PASS=5, FAIL=0, SKIP=0`，标志为 `VERIFY_ALL_OK`，阶段耗时约 94.3 s。

## 3. Windows 候选包核验

- PyInstaller `onedir` 可执行程序完成启动、API、网页资源、三条计算链、打印报告和端口释放冒烟；
- 包内 `release-manifest.json` 逐文件记录 SHA-256，并明确记录构建版本、提交和工作树是否干净；
- 在本开发机上运行包内 `verify_this_pc.ps1 -NonInteractive`，得到 `GFM_CROSS_MACHINE_FUNCTIONAL_OK`；原始 ZIP 哈希被写入结构化证据；
- 同一测试正确返回 `GFM_M5_QUALIFICATION_INCOMPLETE`，因为本机不是声明断网且无 Python、Node.js、MATLAB 的外部验收机。该结果证明工具没有把本机功能通过误报为 M5 完成。

## 4. 第三方组件审计

当前构建期盘点得到：

- Python 发行包 50 个；
- 网页生产包 9 个；
- 运行时条目 2 个；
- 研究来源条目 1 个；
- 合计 62 个组件条目、108 份去重后的许可或通知文件。

`third-party-sbom.json` 中的许可文件路径均为包内相对路径，未发现构建机盘符或绝对目录。构建门会在实际纳入的 Python 发行包或网页生产包找不到许可文件时失败。论文 PDF/TeX、完整作者 MATLAB 仓库、MATLAB、Simulink 与 Simplus 不进入候选包。

## 5. 结论与剩余条件

rc5 已通过本机软件全链验收和候选包功能验收，可以交给团队成员做外部电脑测试。它仍不是正式公共发行版：项目自有代码许可证尚未由负责人确定，Microsoft 运行时再分发条款仍需在公共发布前复核；M5 仍须由另一台无开发环境的 Windows 电脑断网执行，并补充人工浏览器与导出文件证据。

最终 ZIP 的提交号、文件数和 SHA-256 以包内 `build_info.json`、`release-manifest.json` 及构建终端输出为准，避免在文档中手工维护会随重建改变的校验值。
