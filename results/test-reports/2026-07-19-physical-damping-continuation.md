# Fig. 8 物理阻尼延拓验证

日期：2026-07-19<br>
模型：Cifelli–Anta 单台 GFM—无穷大母线 Fig. 8 工况

## 实验设计

以作者的 `UserData_inf_bus_Fig_8.xlsm` 为基准，固定下列量：

- 线路：`R = 0.5 pu`，`ωL = 1 pu`；
- 母线 2：发电有功 `PGi = 0.5 pu`，负载有功 `PLi = 0.5 pu`；
- 虚拟惯量：`H = 12.5`；
- 无功控制：`Q Control Enable = 1`。

仅改变 `Apparatus!I39`。该单元格经作者数据链映射为
`Para{2}.Dw`，再进入作者 `GridFormingVSI` 的 `obj.Para(7)`，模型方程中用作
VSM 阻尼 `D`：

\[
\dot\omega=\frac{D(\omega_0-\omega)+(P_0-p)}{2J}.
\]

因此这是一条物理控制参数延拓，而不是人工闭环比例参数延拓。

## 结果

在 `D ∈ [0.05, 0.5]` 上先作 19 点粗扫，再对首次虚轴穿越区间二分 28 次，得到

\[
D_{\mathrm{crit}}=0.0742176904809,
\qquad
f_{\mathrm{crit}}=0.576101471277\ \mathrm{Hz}.
\]

临界点处：

- 闭环主导极点：`3.64279e-11 + j0.576101471277 Hz`；
- 端口特征矩阵 `J_net(s) + J_C(s;D)` 的主导零点：
  `3.64174e-11 + j0.576101471277 Hz`；
- 二者复数距离：`1.57e-14 Hz`。

端点核验：

| 阻尼 D | 主导极点（Hz） | 判定 |
| ---: | ---: | --- |
| 0.05 | `0.0211544 + j0.5781133` | 不稳定 |
| 0.50 | `-0.2898914 + j0.3996010` | 稳定 |

## 解释与边界

1. 在本算例、其余参数固定且 `D ∈ [0.05,0.5]` 的范围内，线性化稳定边界可写成
   `D > Dcrit`；这是一条可用于控制器整定的工程阈值。
2. 闭环极点和端口特征零点的数值重合，验证了“在物理参数路径上跟踪总特征矩阵零点”
   与完整状态空间稳定性的一致性。
3. 先前人工路径 `I + τ J_C J_net^{-1}` 得到的 `1.247 Hz` 是该人工闭环路径的
   穿越频率，不是阻尼变化造成的物理稳定边界频率。本次结果表明，不应把它解释成
   Fig. 8 的实际振荡模态；物理阻尼路径给出的是约 `0.576 Hz`。
4. 参数延拓和二分本身是标准工具，单独不足以构成论文创新。可形成研究增量的方向是：
   把特征零点灵敏度、局部设备贡献以及可验证的鲁棒参数区间组合成分散式整定方法，
   并在多机系统中证明不会漏检其他模态穿越。

## 可复现产物

- 程序：`experiments/schur/run_inf_bus_damping_continuation.m`
- 粗扫数据：`results/schur/damping-continuation/damping_sweep.csv`
- 数值摘要：`results/schur/damping-continuation/summary.json`
- MATLAB 工作区：`results/schur/damping-continuation/damping_continuation_workspace.mat`
