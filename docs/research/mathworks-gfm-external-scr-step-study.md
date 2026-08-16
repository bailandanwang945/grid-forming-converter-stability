# MathWorks 官方 GFM 模型 SCR—有功阶跃外部对照

## 1. 研究定位

本实验属于外部模型时域对照，不替代论文 Fig. 8 基线，也不把 MathWorks 模型改造成项目的核心分析模型。项目自建16状态平均值 `dq` 模型继续承担状态、端口和闭环极点分析；本实验仅检验一个常见直觉是否依赖自建方程：在控制参数保持不变时，提高短路比（short-circuit ratio, SCR）是否必然单调改善构网型变流器的有功阶跃响应。

外部来源固定为 MathWorks 官方仓库 `Power-Converter-Circuit-Control-Simscape` 的发布标签 `23.2.1.4`、提交 `a65692b004637acb38b2f8c64db7dcf47efe24c7`。第三方源码只放在被 Git 忽略的 `external/mathworks-gfm-r2023b`，项目不修改其模型或初始化文件。

## 2. 研究问题与可推翻假设

- 研究对象：MathWorks `GridFormingConverter.slx`，R2024b 中运行 R2023b 固定发布；
- 场景：虚拟同步机（VSM）有功控制、虚拟阻抗限流、`X/R=5`、有功参考由 `0.6 p.u.` 阶跃至 `0.8 p.u.`；
- 唯一变化：`SCR = 1.5、2.5、5.0`；
- 主假设：SCR 从1.5提高至5.0时，最大频率偏差和有功整定时间均单调减小，且三个工况均被供应商函数 `FindTestOutCome` 判为稳定；
- 替代解释：固定控制整定、虚拟阻抗和网络强度存在耦合，较高 SCR 未必产生单调改善；
- 推翻条件：任一指标不满足单调关系，或任一点被供应商分类函数判为 `Unstable`。

这一定义会保留反例，不能在看到结果后移动 SCR 点、容差或扰动幅值。

## 3. 冻结来源与运行契约

| 项目 | 固定值 |
|---|---|
| 外部提交 | `a65692b004637acb38b2f8c64db7dcf47efe24c7` |
| 模型 SHA-256 | `9cd2abfd5699e92336ceb335414403cb29826da7a4f7ab3abafd581d96c6fac4` |
| 测试条件 Live Script SHA-256 | `66632a96de03f438bf63ef51afa8d80fcf720cb520431d64f3f8e6756e632823` |
| MATLAB | R2024b |
| 仿真接口 | `Simulink.SimulationInput` / `Simulink.SimulationOutput` |
| 扰动时刻与终止时刻 | `3 s` / `8 s` |
| 有功整定带 | `|P-P*| ≤ 0.01 p.u.`，进入后保持至仿真结束 |

供应商 `GridFormingConverterTestCondition.mlx` 在模型加载前会直接调用 `set_param`，且 Live Script 在函数内调用时存在工作区差异。项目适配器因此执行供应商输入参数 Live Script，但对本实验唯一使用的“有功参考变化”场景逐项重构其已冻结时间表与 SCR 缩放公式，并通过 `SimulationInput.setVariable` 显式传递依赖。测试条件文件的 SHA-256 受前置检查约束；来源一旦变化，脚本必须拒绝运行，而不是继续使用旧适配逻辑。

## 4. 运行方法

先把官方固定版本放到指定只读目录：

```powershell
git clone --depth 1 --branch 23.2.1.4 `
  git@github.com:simscape/Power-Converter-Circuit-Control-Simscape.git `
  external/mathworks-gfm-r2023b
```

在 MATLAB R2024b 中运行：

```matlab
run("experiments/external-validation/run_mathworks_gfm_scr_step_study.m")
```

脚本生成：

- `results/mathworks-gfm-external-validation/mathworks_gfm_scr_step_study.json`；
- `results/mathworks-gfm-external-validation/mathworks_gfm_scr_step_points.csv`。

首次 Simscape 编译可能明显慢于后续仿真；编译耗时必须与三点仿真耗时分开解释，不能把首次编译延迟误判为数值不收敛。

## 5. 解释边界

- 供应商 `Stable/Unstable` 是其末段信号变化阈值分类，不等同于闭环特征根证明；
- 三个 SCR 点只能构成离散反例或趋势证据，不能确定连续稳定边界；
- 即使较高 SCR 工况失稳，也不能在没有控制参数隔离和线性化证据时归因于 VSM、虚拟阻抗或某个内环；
- 该模型独立于团队 Python 平均值 `dq` 实现，但仍是仿真模型，不是实物、硬件在环或并网试验；
- 本实验不计算论文小增益—小相位稳定性充分条件，也不构成论文定理反例。

## 6. 实际结果

| SCR | 供应商分类 | 有功整定时间 / s | 最大频率偏差 / Hz | 有功末值绝对误差 / p.u. |
|---:|---|---:|---:|---:|
| 1.5 | Stable | 0.6467 | 0.0756122 | `4.21e-10` |
| 2.5 | Stable | 0.4688 | 0.0540067 | `1.44e-10` |
| 5.0 | Unstable | 未进入整定带 | 184.8215 | 0.513581 |

SCR 1.5 到2.5的两个点符合“网强提高、瞬态改善”的局部趋势，但 SCR=5.0 出现供应商分类函数确认的失稳响应。因此，预先冻结的三点单调改善假设被否定。该结果说明固定控制参数下不能把 SCR 当作脱离控制器与虚拟阻抗的单一稳定性排序量；它尚不能说明哪一控制环节导致较强电网点失稳。

结构化结果：

- JSON SHA-256：`169730ED706FA7BDAF147C071DD62C4CB6522FCD5714912184D51E5EF58860F7`；
- CSV SHA-256：`6568035027639E1EB2AB09372B7CD8B06A2C644E72F55795EA0ECCFF9CCB6799`；
- 三项冻结产物测试核对来源、三点顺序、供应商分类、数值锚点和结论边界，均已通过。

运行过程中还保留两项方法失败记录：批量快重启若只传入五字段简化 `testCondition`，会因供应商模型缺少故障和变压器字段而全部失败；供应商 Live Script 在普通函数作用域中不能稳定提供全部模型变量。正式脚本采用逐点完整初始化、普通脚本工作区和显式 `SimulationInput` 变量注入，未把失败输出用于结论。
