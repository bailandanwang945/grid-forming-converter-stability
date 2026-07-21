# 基于端口特征零点灵敏度的阻尼—电网强度稳定边界追踪

日期：2026-07-19<br>
状态：单机无穷大母线原型已运行；尚未形成一般性分散稳定定理。

## 1. 研究问题

考虑由变流器端口导纳与网络端口导纳组成的特征矩阵

\[
M(s,D,\kappa)=Y_{\mathrm{net}}(s,\kappa)+Y_C(s,D,\kappa),
\]

其中 (D) 为 VSM 阻尼，\(\kappa\) 同比例缩放 Fig. 8 工况中的线路
\(R\) 与 \(\omega L\)，并保持线路 (X/R) 不变。研究目标不是在离散参数网格上重复判稳，
而是连续追踪满足

\[
\det M(j\omega,D,\kappa)=0
\]

的 Hopf 稳定边界。

在本算例的标幺基准下，采用

\[
\mathrm{SCR}=\frac{1}{|R+j\omega L|}
=\frac{1}{\kappa\sqrt{0.5^2+1^2}}.
\]

## 2. 隐式特征零点灵敏度

设边界点 (s_c=j\omega_c) 为简单特征零点，并存在归一化左右零向量

\[
M(s_c,D,\kappa)v=0,
\qquad
u^*M(s_c,D,\kappa)=0.
\]

对参数 (p\in\{D,\kappa\}) 求导，有

\[
\frac{\mathrm ds}{\mathrm dp}
=-
\frac{u^*M_pv}{u^*M_sv}.
\]

稳定边界满足 \(\operatorname{Re}s=0\)。因此其局部切向为

\[
\boxed{
\frac{\mathrm dD_{\mathrm{crit}}}{\mathrm d\kappa}
=-
\frac{\operatorname{Re}(\mathrm ds/\mathrm d\kappa)}
{\operatorname{Re}(\mathrm ds/\mathrm dD)}
}.
\]

该公式直接由端口特征矩阵给出边界的行进方向，不需要先在二维参数平面上铺设密集网格。

## 3. 预测—校正算法

已知第 (n) 个边界点 \((D_n,\kappa_n)\) 后：

1. 根据左右零向量计算边界切向 \(q_n=\mathrm dD/\mathrm d\kappa\)；
2. 对下一阻抗尺度作切向预测

   \[
   D_{n+1}^{\mathrm{pred}}
   =D_n+q_n(\kappa_{n+1}-\kappa_n);
   \]

3. 以预测值为中心寻找稳定/失稳夹逼区间；
4. 用闭环主导极点实部作校正，得到 \(D_{n+1}^{\mathrm{crit}}\)；
5. 用 \(Y_{\mathrm{net}}+Y_C\) 的特征零点独立复核校正结果。

这种算法把完整状态空间模型用作边界校正与验证，而把端口矩阵的零向量结构用于预测和解释。

## 4. Fig. 8 数值结果

线路参数取

\[
R=0.5\kappa\ \mathrm{pu},
\qquad
\omega L=1.0\kappa\ \mathrm{pu},
\]

其余负载、运行点、惯量和无功控制方式保持不变。

| \(\kappa\) | SCR | \(D_{\mathrm{crit}}\) | 临界频率/Hz | \(\mathrm dD/\mathrm d\kappa\) |
| ---: | ---: | ---: | ---: | ---: |
| 0.5 | 1.7889 | 0.057965 | 0.757557 | 0.045549 |
| 0.8 | 1.1180 | 0.068969 | 0.631012 | 0.029601 |
| 1.0 | 0.8944 | 0.074218 | 0.576101 | 0.023268 |
| 1.2 | 0.7454 | 0.078397 | 0.533813 | 0.018762 |
| 1.5 | 0.5963 | 0.083276 | 0.485224 | 0.014095 |

共追踪 11 个边界点。结果表明：电网越弱，维持小信号稳定所需的最低阻尼越高；同时临界振荡频率下降。

数值一致性：

- 切向预测的最大阻尼误差：\(3.43\times10^{-4}\)；
- 解析切向与相邻边界点中心差分的最大相对误差：\(5.89\times10^{-3}\)；
- 闭环主导极点与端口特征零点的最大复数距离：\(2.34\times10^{-14}\) Hz；
- 临界特征矩阵的最大最小奇异值：\(3.33\times10^{-14}\)。

这些结果同时核验了边界位置、零点等价关系和切向公式。

## 5. 学术判断

参数延拓、左右特征向量灵敏度和预测—校正都属于成熟数学工具；它们本身不能被声称为新理论。
本项目可能形成的研究增量在于以下组合：

1. 以 GFM 端口特征零点而非完整状态矩阵作为物理参数边界的主要追踪对象；
2. 将真实稳定边界作为参照，定量计算小增益—小相位充分条件的认证缺口；
3. 将边界切向进一步分解到各变流器的局部导纳参数，形成设备—参数贡献排序；
4. 在多机系统中验证该排序能以较小的局部参数调整恢复稳定，且不漏检其他模态穿越。

其中第 2—4 项尚未完成，不能提前写成既成创新。

## 6. 可复现产物

- 实验程序：`experiments/schur/run_inf_bus_damping_grid_boundary.m`
- 完整边界数据：`results/schur/damping-grid-boundary/boundary.csv`
- 数值摘要：`results/schur/damping-grid-boundary/summary.json`
- MATLAB 工作区：`results/schur/damping-grid-boundary/boundary_workspace.mat`
