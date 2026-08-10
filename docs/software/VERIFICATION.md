# 统一验收与发布边界

## 源码工作树验收

Windows 下在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1
```

脚本依次执行：

1. Python `unittest` 全套测试，当前测试集为 60 项；
2. React/TypeScript 前端生产构建；
3. 开发态一键启动器冒烟测试；
4. 使用本机现有 Chrome 或 Edge 的浏览器端到端流程；
5. 若能找到 MATLAB，则运行 `experiments/run_unit_tests.m`。

浏览器端到端流程覆盖 Fig. 8 失稳工况的 75 个未覆盖点、独立模型参数修改、案例导出—导入—重算、打印式报告，以及 441 点 D–X 参数扫描。它验证软件链路实际可操作，不替代对模型物理有效性的确认。

首次运行如缺少项目依赖，脚本会根据 `backend/requirements-dev.txt` 和前端锁文件安装依赖。若只允许检查现有环境，使用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1 -NoBootstrap
```

MATLAB 是科研交叉回归环境，不是前后端运行的必需依赖。未安装 MATLAB 时，汇总表会明确记为 `SKIP`，而不是 `PASS`；也可以用 `-SkipMatlab` 显式跳过。若 MATLAB 不在 `PATH` 或默认安装目录，可设置安装根目录，例如：

```powershell
$env:MATLAB_ROOT = "D:\matlab"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1
```

`D:\matlab` 仅为示例，应替换为本机实际安装目录。当前仓库中可追溯的最新 MATLAB 记录为 128 Passed、0 Failed、0 Incomplete；Python 当前测试集为 60 项。两者验证不同实现，不应相加或互相替代。

成功标记分为：

- `VERIFY_ALL_OK`：所有执行阶段通过，且没有跳过项；
- `VERIFY_ALL_OK_WITH_SKIPS`：必选阶段通过，但 MATLAB 等可选阶段被明确跳过；
- `VERIFY_ALL_FAILED`：至少一个必选或已执行阶段失败。

## Windows 发布验收

源码验收要求 Windows 10/11、Python 3.10+ 和 Node.js 20+。`scripts/build_release.ps1` 与 `packaging/` 已在本机生成 Windows `onedir` 候选包；打包后的同一进程能够提供静态前端和 API，并通过 Fig. 8 固定 1000 点复算（75 个未覆盖点）及退出后端口释放冒烟。

本机候选产物记录如下：

| 项目 | 数值 |
|---|---|
| 版本标识 | `0.3.0-rc4` |
| 源代码提交 | `e00a825d7532fef7d5b1dc6b880d1dbf3e0931fa` |
| 解压目录大小 | 151.51 MiB |
| ZIP 大小 | 66.10 MiB |
| ZIP SHA-256 | `b118c2ccd1d97a38da5f9bd7b56c6d54816eca775ffe0b004030cea861ad9ef0` |
| 清单状态 | `workingTreeDirty=false`，885 个受清单约束文件 |
| 发布结论 | 本机验收通过的结项候选；异机验收未完成 |

上述哈希只标识提交 `e00a825` 对应的本次候选，不得沿用于后续重新构建的包。

M5 发布完成至少需要保存以下证据：

- 与确定提交版本对应的发布目录、ZIP、文件清单与 SHA-256；
- 在干净提交上重建候选包，并完成打包后启动、健康检查、分析和退出清理（本候选已完成）；
- 在另一台没有 Python、Node.js、MATLAB 和项目缓存的 Windows 电脑上断网启动；
- 完成 Fig. 8 分析、独立案例导入重算、CSV/报告导出和退出清理；
- 记录操作系统、命令、结果、失败现象和修复版本。

当前本机候选证明发布技术路径和干净提交构建均可行，但不证明跨机可运行。只有上述异机断网验收完成，才可把正式发布包称为“无需开发环境、可跨机运行”。许可证与第三方材料分发边界未确定前，不得对外正式发布。
