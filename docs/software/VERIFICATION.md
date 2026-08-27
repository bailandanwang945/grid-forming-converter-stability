# 统一验收与发布边界

## 源码工作树验收

Windows 下在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1
```

脚本依次执行：

1. Python `unittest` 全套测试，当前测试集为270项；
2. React/TypeScript 前端生产构建；
3. 开发态一键启动器冒烟测试；
4. 使用本机现有 Chrome 或 Edge 的浏览器端到端流程；
5. 若能找到 MATLAB，则运行 `experiments/run_unit_tests.m`。

浏览器端到端流程覆盖 Fig. 8 失稳工况的 75 个未覆盖点、独立模型参数修改、案例导出—导入—重算、441 点 D–X 参数扫描、平均值 dq 模型研究任务，以及三频点端口辨识的 JSON/HTML 导出。它验证软件链路实际可操作，不替代对模型物理有效性的确认。

首次运行如缺少项目依赖，脚本会根据 `backend/requirements-dev.txt` 和前端锁文件安装依赖。若只允许检查现有环境，使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1 -NoBootstrap
```

MATLAB 是科研交叉回归环境，不是前后端运行的必需依赖。未安装 MATLAB 时，汇总表会明确记为 `SKIP`，而不是 `PASS`；也可以用 `-SkipMatlab` 显式跳过。若 MATLAB 不在 `PATH` 或默认安装目录，可设置安装根目录，例如：

```powershell
$env:MATLAB_ROOT = "D:\matlab"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1
```

`D:\matlab` 仅为示例，应替换为本机实际安装目录。2026-08-27，冻结候选统一验收记录为：Python 263项、MATLAB 128项、前端生产构建、开发态启动器和真实浏览器端到端流程全部通过，汇总 `PASS=5、FAIL=0、SKIP=0`、`VERIFY_ALL_OK`。随后当前分支加入6项论文基线完整性测试和1项长计算进度测试，Python全量 `270/270` 在387.985秒内通过；同一变更后的前端生产构建、启动器与真实浏览器流程也分别通过。MATLAB代码未变，本轮没有重复运行，故128项仍明确属于冻结候选记录。Python与MATLAB验证不同实现，不应相加或互相替代。

成功标记分为：

- `VERIFY_ALL_OK`：所有执行阶段通过，且没有跳过项；
- `VERIFY_ALL_OK_WITH_SKIPS`：必选阶段通过，但 MATLAB 等可选阶段被明确跳过；
- `VERIFY_ALL_FAILED`：至少一个必选或已执行阶段失败。

## 论文与作者代码基线完整性

不启动 MATLAB、前后端或网络时，可运行：

```powershell
python .\scripts\verify_reference_baselines.py
```

该命令逐项比较 arXiv v1/v2 源码快照、归档包和固定作者许可快照的可信 SHA-256；清单格式错误、缺失、内容变化、未登记文件和路径越界均返回非零状态。默认模式允许干净克隆缺少被 Git 忽略的核心论文 PDF 与完整作者仓库，并明确报告其缺失。研究归档机使用以下严格模式：

```powershell
python .\scripts\verify_reference_baselines.py --strict-local-archive
```

2026-08-27 严格模式实际核验：v1 共26个清单文件、v2共28个清单文件、核心论文 PDF、作者 `v1.0.0 / ef67c7a…` 仓库及发布许可快照全部通过，输出 `GFM_REFERENCE_BASELINE_OK`。与该验证器对应的6项反例和正常路径测试已纳入当前270项全量通过记录。

## Windows 发布验收

源码验收要求 Windows 10/11、Python 3.10+ 和 Node.js 20+。`scripts/build_release.ps1` 与 `packaging/` 已从干净提交生成 Windows `v0.5.0-rc1` `onedir` 候选包；包内同一进程能够提供静态前端和 API，并通过 Fig. 8 固定1000点复算（75个未覆盖点）、采样敏感性、同域对照、低频模型、平均值dq模型、42点层级扫描、三频点端口辨识、MathWorks—团队冻结证据、Sienna Test 08分层审计、六类报告及退出后端口释放冒烟。

本机候选产物记录如下：

| 项目 | 数值 |
|---|---|
| 版本标识 | `0.5.0-rc1` |
| 源代码提交 | `6ca0b757bda1972284a7282118a12e18bfe1d6a4` |
| 包目录总大小 | 164,670,923 字节 |
| ZIP 大小 | 71,728,417 字节 |
| ZIP SHA-256 | `40c3248ac8acfb208d1119ba9bc9b7ce2043a3691a30962a8b9799e22c329e1a` |
| 清单状态 | `workingTreeDirty=false`，1024 个受约束文件；包目录含清单共1025个文件 |
| 第三方清单 | 64个组件，其中Python 50项、前端生产依赖9项；生产依赖 `npm audit --omit=dev` 为0项漏洞 |
| 发布结论 | 本机整包功能验收通过；异机断网与人工浏览器验收未完成 |

上述哈希只标识提交 `6ca0b75` 对应的本次候选，不得沿用于后续重新构建的包。历史 `v0.4.0-rc2` 哈希只作旧版本追溯。

M5 发布完成至少需要保存以下证据：

- 与确定提交版本对应的发布目录、ZIP、文件清单与 SHA-256；
- 在干净提交上重建候选包，并完成打包后启动、健康检查、分析和退出清理（本候选已完成）；
- 在另一台没有 Python、Node.js、MATLAB 和项目缓存的 Windows 电脑上断网启动；
- 完成 Fig. 8 分析、独立案例导入重算、CSV/报告导出和退出清理；
- 记录操作系统、命令、结果、失败现象和修复版本。

当前本机运行得到 `GFM_CROSS_MACHINE_FUNCTIONAL_OK` 与 `GFM_M5_QUALIFICATION_INCOMPLETE`：它证明包级功能链和干净提交构建可行，不证明跨机资格。本机证据提交项目侧工具时因未满足断网、无开发环境条件而被拒绝，这是预期的资格门，不是软件功能失败。只有另一台合格电脑完成自动验收和人工浏览器检查，才可把该候选称为“已完成异机复现”。项目自身代码许可证与公开分发决定仍须由团队确认。
