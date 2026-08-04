# 论文无限大母线基线复现

本目录提供论文 v2 无限大母线稳定与不稳定算例的隔离运行入口。运行时复制本地 Simplus 快照到 `tmp/baseline/`，再覆盖作者提供的 `GridFormingVSI.m` 和输入工作簿；第三方源目录保持只读。运行结束后临时副本自动删除。

## 运行方式

在项目根目录的 MATLAB 会话中执行：

```matlab
addpath("experiments/baseline")
stableSummary = run_inf_bus_baseline("stable");
unstableSummary = run_inf_bus_baseline("unstable");
```

输入分别为作者仓库中的：

- `UserData_inf_bus.xlsm`；
- `UserData_inf_bus_Fig_8.xlsm`。

精选 CSV 与摘要写入 `results/baseline/<case>/`。包含频响对象和闭环模型的 `baseline_workspace.mat` 作为本地回归输入保留，但按项目规则不进入 Git。

## 2026-07-16 核验结果

- 稳定算例：作者布尔判定的首个扇形频点为 `0.9203732 Hz`；团队裕度零点插值为 `0.9131644 Hz`；闭环无右半平面极点。
- 不稳定算例：闭环最大极点实部为 `0.0211544 Hz`，确认存在不稳定共轭极点。
- 不稳定共轭极点的虚部约为 `0.5781133 Hz`，与论文正文所述 `1.2 Hz` 尚不一致。该差异可能涉及输入版本、模型约定或报告频率定义，未核清前不得宣称完成定量复现。

## 验证边界

当前脚本验证原始矩形坐标下的变流器扇形性边界和闭环极点符号，尚未复现论文全部环路整形、增益—相位图和时域波形。充分条件未满足不等同于闭环不稳定。

## 2026-08-04 Fig. 8 受控阻尼夹具

旧 `stable` 基线来自 `UserData_inf_bus.xlsm`，它与 Fig. 8 工作簿同时改变了阻尼、电网、
工作点和无功控制，不能作为 Fig. 8 的单参数稳定对照。新的受控夹具只使用
`UserData_inf_bus_Fig_8.xlsm`，固定其余参数，仅把 VSM 阻尼由 `D=0.05` 改为 `D=0.5`。

- `export_author_fig8_raw_fixture`：从本地忽略的 MAT 工作区导出双精度原始频响，以及按
  `abs(value_Hz)>1e-7` 排除平凡零模态后的动态极点与返回零点谱；
- `load_author_fig8_raw_fixture`：在干净克隆中读取受版本约束的 CSV/JSON；
- `run_author_fig8_mixed_regression`：执行修正版动态整形和有限网格混合判据筛查。

当前 1000 点结果：`D=0.05` 闭环主导极点实部为 `+0.0211544371 Hz`，有 75 个样点在
声明的相位分支下未被两类条件覆盖；`D=0.5` 主导极点实部为 `-0.289891361 Hz`，无未覆盖
样点。两种结果都不是论文定理的连续全频证明，相位筛查仍依赖显式种子和最近邻分支假设。
