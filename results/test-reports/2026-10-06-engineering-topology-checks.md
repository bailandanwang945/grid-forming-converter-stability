# 工程接线检查分离与 R7 局部连接试验

日期：2026-10-06。范围：前端预检、接线资料提取及独立结构检查，不包含潮流、短路或新的稳定性模型。

## 实际修改

- 前端接线关系检查与低频模型适用性分开显示；无 GFM、缺外部参考和不连通不再统一写成“结构错误”。
- 低频主分析、参数扫描、N-1 增加执行前检查与按钮禁用；不适用输入不会发出对应求解请求。
- 未修改后端 `NetworkTopology/1.0`、数学模型、作者基线及定理状态；后端仍对完整契约、参数与数值条件负责。
- 原有保存、导入、请求修订和报告输入归属逻辑保留。能保存草稿不等于后端能够计算该草稿。
- R7 提取 G1、T1、220 kV I/II 段、分段开关组及 L1：12 个连接节点、12 个元件、9 个独立开关。
- 实际运行状态保持未知。四组教学覆盖单独声明，不向来源草稿回填。
- 连接检查保留设备端子映射，闭合理想开关合并节点，T1/L1 本体不作为理想导线合并。

## 验证与阅读范围

| 检查 | 命令或方式 | 结果 |
|---|---|---|
| 接线/适用性纯函数 | `node scripts/test_network_topology_checks.mjs` | 20 场景通过 |
| 浏览器操作 | `node scripts/test_network_topology_applicability_ui.mjs` | 9 场景通过；随机本地端口、模拟 API，没有运行数值内核 |
| 既有异步结果归属 | `node scripts/test_reduced_order_request_consistency.mjs` | 33 既有场景通过，不作为新增测试累计 |
| R7 连接结构 | `python -m unittest discover -s experiments/engineering-main-connection -p "test_*.py" -v` | 14 项通过；主代理复跑 0.031 s |
| Python 静态及格式 | `ruff check` / `ruff format --check`，仅两份连接检查文件 | 通过 |
| 前端生产构建 | `npm run build`，工作目录 `apps/web` | TypeScript 与构建通过，保留既有大分块提示 |
| 结构草稿来源绑定 | JSON 解析、唯一标识、端子引用、源 PDF 哈希与记录比较 | 通过；这是记录与当前文件一致，不是上游可信摘要校验 |
| 已保存连接结果 | 回读结果并比较输入 SHA-256、四工况摘要及非物理计算标记 | 通过 |
| 统一验证入口 | PowerShell 语法解析；加入两项前端测试及连接检查测试阶段 | 解析通过；未在本轮重跑完整 `verify_all.ps1` |
| 响应式预检区域 | 1440/390 px 浏览器检查并查看截图 | 页面无横向溢出，新增状态能换行；截图使用模拟输入 |

截图只检查本次预检区域，不是全站视觉验收，也不说明网络参数正确。
已有缩略图遮挡部分画布及窄屏视野问题仍可后续改进；本轮未重做网络画布或实现 CAD 主接线编辑。

## 四组教学状态的已保存结果

| 工况 | 等电位节点 | 连接区域 | I/II 段同节点 |
|---|---:|---:|---|
| 全部开关闭合 | 3 | 1 | 是 |
| QF-S 断开 | 4 | 2 | 否 |
| QS-S1 断开，QF-S 闭合 | 4 | 2 | 否 |
| QF-L1 断开 | 4 | 2 | 是 |

全部工况 T1 高低压不合并。原草稿实际状态编译被拒绝，不用正常合闸标注代替实际状态。
来源草稿 SHA-256：`865af492a287dde00e301cce2194ac3af868f2ff9f1466f3a7afd3c05f40a9ca`。
结果：`results/engineering-main-connection/r7-switch-connectivity-2026-10-06.json`，`analysis_kind=connectivity-only`，物理结果列表为空。

## 尚未完成与下一步范围

- 该工程草稿尚不能导入现有网络 API，也未形成独立开关、变压器与同步机的完整网页编辑功能。
- 含变流器潮流/短路方法评估已保存，但没有接入 pandapower 或新增这两类数值分析。
- 潮流应区分端口 PV/PQ 近似与控制一致的 GFM 工作点；短路须明确故障电流模型与限流策略，不能当同步机计算。
- 尚未补全图纸运行参数、实际开关工况、外部等值及省略支路，不能报告原电厂潮流或安全结论。
- 没有执行 MATLAB/Simulink、安装新包、生成新发行包、提交或推送本轮改动。

恢复入口：`docs/design/engineering-main-connection-plan-2026-10-06.md`、`docs/design/r7-subnetwork-parameter-gaps-2026-10-06.md`、`docs/design/converter-power-flow-short-circuit-feasibility-2026-10-06.md`。
