# 数值域扇形性判定方法审查与升级建议

> 审查日期：2026-07-16  
> 审查对象：论文 arXiv:2510.20544v2、`src/classifyNumericalRange.m`、现有算法规范与单元测试  
> 文档性质：研究方法论审查，不构成新的矩阵相位定理

## 1. 结论摘要

现有实现采用旋转 Hermitian 部分的最小特征值判断数值域与原点的关系，数学主线成立；均匀角网格误差上界

\[
2\sin(h/4)\lVert A\rVert_2
\]

在精确算术下也是有效的。需要修正的不是核心公式，而是结果的表述和后续算法结构：

1. \(\lambda_{\min}(H_\theta)\) 严格说是数值域在给定方向上的**最小投影**，等于相反方向支撑函数的负值，不宜直接称为“支撑函数”。
2. 现有上下界只控制角度离散误差，尚未计入浮点特征值计算误差，因此应称为“离散化包络”或“条件性数值界”，不宜称为严格的计算机辅助证明。
3. `fminbnd` 只能作为改善已知下界的局部搜索工具；MathWorks 文档明确指出它可能只给出局部解，不能承担全局最优性认证。
4. 最适合本科大创周期的升级不是引入复杂的高精度边界跟踪，而是实现一维 Lipschitz 分支定界：逐次二分上界最大的角区间，保持全局下界单调不减、全局上界单调不增，并在计算预算耗尽时保留“暂不能判定”。
5. 本项目可主张的贡献是：将已有的数值域几何、Hermitian 特征值扰动界和 Lipschitz 全局优化思想，落实为适用于构网型变流器频率响应矩阵的可复现判定流程，并量化临界频段中的离散误判风险。不能声称提出了新的数值域理论或首个全局算法。

## 2. 审查范围与版本依据

本次审查读取了以下本地材料：

- `references/source/arxiv-2510.20544v2/source/sec1_Introduction.tex`：数值域、sectorial、quasi-sectorial 与 semi-sectorial 的论文表述；
- `references/source/arxiv-2510.20544v2/source/sec2_Preliminary.tex`：混合小增益—小相位条件；
- `references/source/arxiv-2510.20544v2/source/sec3_Limitations.tex`：构网型变流器零频非扇形性论证；
- `references/source/arxiv-2510.20544v2/source/sec4b_ProposedApproach.tex`：坐标变换和环路整形后的扇形性要求；
- `src/classifyNumericalRange.m`；
- `tests/classifyNumericalRangeTest.m`；
- `docs/specs/algorithms/sectoriality-classifier/` 下两份现有规范。

论文 v2 在第 1 节将数值域定义为

\[
W(A)=\{x^*Ax:\lVert x\rVert_2=1\},
\]

并将 sectorial 矩阵描述为 \(0\notin W(A)\) 且数值域包含于角宽小于 \(\pi\) 的扇形内。该定义与矩阵相位文献的出发点一致。论文同时明确：分散式小相位条件需要变流器频响矩阵为 quasi-sectorial、网络相应矩阵为 sectorial。因此，当前分类器只解决“严格分离/原点边界/原点内部”的前置几何问题，不能代替完整的矩阵相位计算，也不能单独推出闭环稳定性。

## 3. 数学核验

### 3.1 方向投影与 Hermitian 特征值

令

\[
H_\theta(A)=\operatorname{Re}(e^{-\mathrm{i}\theta}A)
=\frac{e^{-\mathrm{i}\theta}A+e^{\mathrm{i}\theta}A^*}{2}.
\]

对任意单位向量 \(x\)，有

\[
x^*H_\theta(A)x
=\operatorname{Re}\!\left(e^{-\mathrm{i}\theta}x^*Ax\right).
\]

由 Hermitian 矩阵的 Rayleigh 商极值原理，

\[
\begin{aligned}
\max_{z\in W(A)}\operatorname{Re}(e^{-\mathrm{i}\theta}z)
&=\lambda_{\max}(H_\theta(A)),\\
\min_{z\in W(A)}\operatorname{Re}(e^{-\mathrm{i}\theta}z)
&=\lambda_{\min}(H_\theta(A)).
\end{aligned}
\]

第一式是标准支撑函数；现有代码使用第二式。数值域边界通过旋转 Hermitian 部分的特征值确定，是经典数值域计算方法的基础，可追溯至 Kippenhahn 的边界生成曲线和 Johnson 的数值算法。可参见 [Kippenhahn 原文英译及 DOI](https://doi.org/10.1080/03081080701553768)、[Johnson, 1978, SIAM Journal on Numerical Analysis](https://doi.org/10.1137/0715039) 以及较新的高精度路径跟踪研究 [Loisel 与 Maxwell, 2018](https://doi.org/10.1137/17M1148608)。

定义

\[
m(A)=\max_{\theta\in[-\pi,\pi)} f_A(\theta),\qquad
f_A(\theta)=\lambda_{\min}(H_\theta(A)).
\]

由于有限维数值域是紧凸集，严格分离定理给出：

\[
\begin{array}{rcl}
m(A)>0 &\Longleftrightarrow& 0\notin W(A),\\
m(A)=0 &\Longleftrightarrow& 0\in\partial W(A),\\
m(A)<0 &\Longleftrightarrow& 0\in\operatorname{int}W(A),
\end{array}
\]

其中最后一式要求按复平面中的通常内部理解；对退化为线段或点的数值域，应单独处理其低维边界语义。现有代码把零矩阵单列为 `degenerate` 是合理的，但将来若要细分 quasi-sectorial 与 semi-sectorial，还必须引入秩、相位张角及退化数值域的定义，不能只依据 \(m(A)\) 的符号。

数值域的系统教材可参见 [Gustafson 与 Rao, *Numerical Range*](https://doi.org/10.1007/978-1-4613-8498-4)；矩阵相位定义及其与数值域的关系可参见 [Wang 等, 2020](https://doi.org/10.1016/j.laa.2020.01.035) 和 [Chen 等, *A Phase Theory of MIMO LTI Systems*](https://arxiv.org/abs/2105.03630v2)。

### 3.2 Hermitian 最小特征值的 Lipschitz 界

对任意 \(\theta,\varphi\)，Weyl 的 Hermitian 特征值扰动界给出

\[
|\lambda_{\min}(X)-\lambda_{\min}(Y)|\leq\lVert X-Y\rVert_2.
\]

该结论可参见 Bhatia 的 [*Perturbation Bounds for Matrix Eigenvalues*, 第 3 章](https://doi.org/10.1137/1.9780898719079.ch3)；Horn 与 Johnson 的 [*Matrix Analysis*](https://www.cambridge.org/highereducation/books/matrix-analysis/FDA3627DC2B9F5C3DF2FD8C3CC136B48) 也是标准参考书。

取 \(X=H_\theta(A)\)、\(Y=H_\varphi(A)\)，则

\[
\begin{aligned}
\lVert H_\theta(A)-H_\varphi(A)\rVert_2
&\leq |e^{-\mathrm{i}\theta}-e^{-\mathrm{i}\varphi}|\lVert A\rVert_2\\
&=2\sin\!\left(\frac{d_{\mathbb S^1}(\theta,\varphi)}{2}\right)\lVert A\rVert_2,
\end{aligned}
\]

其中 \(d_{\mathbb S^1}\in[0,\pi]\) 是圆周最短角距离。因此

\[
|f_A(\theta)-f_A(\varphi)|
\leq 2\sin\!\left(\frac{d_{\mathbb S^1}(\theta,\varphi)}{2}\right)\lVert A\rVert_2.
\]

若均匀网格步长为 \(h\)，任意角度到最近网格点的距离不超过 \(h/2\)，从而

\[
m(A)\leq \max_k f_A(\theta_k)
+2\sin(h/4)\lVert A\rVert_2.
\]

这正是现有代码中的 `gridErrorBound`。该常数来自圆周弦长，比直接使用 \(\lVert A\rVert_2|\theta-\varphi|\) 略紧；其推导有效。

### 3.3 需要保留的限定条件

上述上界在以下意义下成立：矩阵 \(A\)、谱范数和每次最小特征值均按精确算术计算。实际 MATLAB `eig` 的舍入误差尚未包含在当前 `lowerBound` 与 `upperBound` 中。因此：

- 对普通双精度工程计算，可以把它们称为“角度离散误差包络”；
- 若要使用“严格认证”一词，需要再加入 Hermitian 特征值残差界、向外取整的区间算术或高精度复核；
- 本科大创阶段没有必要实现完整区间特征值算法，但必须在论文和答辩中陈述这一限制。

## 4. 现有实现审查

| 项目 | 审查结论 | 建议 |
|---|---|---|
| `separationMargin` | 公式正确，Hermitian 化后取最小特征值合理 | 可在后续版本中显式执行 `(H+H')/2` 抑制舍入导致的微小非 Hermitian 分量 |
| 均匀网格上界 | `2*sin(h/4)*norm(A,2)` 正确 | 保留作为基线算法和自适应算法的初始界 |
| `fminbnd` 细化 | 只改善已求得的函数值下界，不破坏现有安全性 | 文档中改称“启发式局部细化”；不得把其退出标志解释为全局最优证明 |
| `lowerBound` | 取已评价点的最大值，确为 \(m(A)\) 的下界 | 保留，并要求迭代过程中单调不减 |
| `upperBound` | 基于全网格覆盖，确为离散化上界 | 自适应版改为各角区间上界的最大值，并要求单调不增 |
| `boundary` | 当前默认参数下通常返回 `indeterminate`，做法保守 | 将标签明确改述为“容差意义下的边界带”，不要声称证明 \(m(A)=0\) |
| 尺度处理 | `RelTol*norm(A,2)` 支持正比例缩放不变性 | 建议先归一化再优化，使角优化容差与矩阵物理量纲分离 |
| 方法命名 | `rotated-Hermitian-separation-bounds-v2` 基本准确 | 升级后建议使用 `adaptive-rotated-Hermitian-envelope-v1`，避免使用 `certified` |

[MathWorks `fminbnd` 文档](https://www.mathworks.com/help/matlab/ref/fminbnd.html)说明该函数求解固定区间内的单变量局部最小化，可能只返回局部解。现有代码把它的结果仅用于提高下界，因此在逻辑上是安全的；但若未来删除全局网格上界而只依赖 `fminbnd`，就会失去全局判定依据。

此外，现有两份 Markdown 规范在当前 PowerShell 输出中出现乱码，文件本身需另行核验 UTF-8 编码。此问题不影响 MATLAB 实现，但会影响中期答辩材料和跨工具读取，应在文档整理阶段修复，且不要借此改动原始论文源码快照。

## 5. 本科大创可实现的算法升级

### 5.1 目标与边界

升级目标不是追踪整个数值域边界，而是对标量全局最优值 \(m(A)\) 形成给定容差下的上下包络。对于项目主要使用的 \(2\times2\) 导纳矩阵，每次函数评价只需一次小规模 Hermitian 特征值计算，计算负担很低。

建议首先归一化

\[
B=A/\lVert A\rVert_2,
\]

并在 \(B\) 上计算 \(\widehat m\)。最终再按 \(m(A)=\lVert A\rVert_2\widehat m\) 恢复量纲。零矩阵或低于绝对退化阈值的矩阵继续单独处理。

### 5.2 区间上界

对圆周角区间 \(I=[c-r,c+r]\)，在中心 \(c\) 评价 \(f_B(c)\)。由上一节的扰动界，对任意 \(\theta\in I\)，

\[
f_B(\theta)\leq f_B(c)+2\sin(r/2).
\]

因此定义

\[
U(I)=f_B(c)+2\sin(r/2),\qquad L(I)=f_B(c).
\]

所有已评价点的最大值是全局下界 \(L\)，所有活动区间上界的最大值是全局上界 \(U\)。这是一维 Lipschitz 全局优化的标准结构；经典出处可参见 [Shubert, 1972](https://doi.org/10.1137/0709036)，算法复杂度分析可参见 [Hansen、Jaumard 与 Lu, 1991](https://doi.org/10.1287/moor.16.2.334)。本项目不需要复现这些通用算法的全部技巧，只需实现适合周期角变量的二分版本。

### 5.3 推荐迭代流程

1. 用 16 或 32 个等长区间覆盖圆周，评价每个区间中心。
2. 计算各区间 \(U(I)\)，用最大堆或排序表选择上界最大的区间。
3. 将该区间二分，评价两个子区间中心，更新全局 \(L\) 和 \(U\)。
4. 可在当前最佳角附近调用 `fminbnd` 改善 \(L\)，但不得用它删除未经上界排除的区间。
5. 满足下列任一条件时停止：
   - \(L>\tau\)：确认严格扇形；
   - \(U<-\tau\)：确认原点位于数值域内部，即非扇形；
   - \(-\tau\leq L\leq U\leq\tau\)：归入容差边界带；
   - \(U-L\leq\varepsilon_{\mathrm{opt}}\)：达到目标最优性间隙；
   - 达到最大特征值评价次数或最小区间宽度：输出 `indeterminate`，同时返回剩余包络。

其中 \(\tau\) 是几何分类容差，\(\varepsilon_{\mathrm{opt}}\) 是角优化误差，两者不应混为一个参数。建议默认值均在归一化尺度上定义，例如 \(\tau=10^{-8}\)、\(\varepsilon_{\mathrm{opt}}=10^{-10}\)，实际值再依据论文频响矩阵的条件数和重复实验确定，而不是直接写死为最终科学结论。

### 5.4 频率扫描中的使用方式

频率响应 \(A(j\omega)\) 随 \(\omega\) 通常连续，可把上一频点的最佳角用于下一频点的优先搜索顺序，以减少平均评价次数。但不能只搜索该角附近，因为特征值分支交叉时全局最优方向可能发生跳变。每个频点仍需保留完整圆周覆盖的区间上界。

建议在结果中保存：

- 频率；
- 归一化下界、上界及最优性间隙；
- 分类标签；
- 特征值评价次数；
- 最佳角；
- 是否使用局部细化；
- 达到的停止条件；
- 矩阵尺度和容差。

这些字段足以支撑“临界频段是否受角离散误差影响”的定量分析。

## 6. 反例与验收测试设计

### 6.1 必须保留的解析矩阵族

1. **旋转正定矩阵**

   \[
   A=e^{\mathrm{i}\alpha}\operatorname{diag}(a_1,\ldots,a_n),\qquad a_i>0.
   \]

   解析值为 \(m(A)=\min_i a_i\)，最佳角为 \(\alpha\)（模 \(2\pi\)）。用于验证严格扇形、相位旋转协变性和正比例缩放不变性。

2. **Jordan 型临界族**

   \[
   A=e^{\mathrm{i}\alpha}
   \begin{bmatrix}1&k\\0&1\end{bmatrix}.
   \]

   有

   \[
   f_A(\theta)=\cos(\theta-\alpha)-|k|/2,
   \qquad m(A)=1-|k|/2.
   \]

   因而 \(|k|<2\)、\(|k|=2\)、\(|k|>2\) 分别给出严格扇形、边界和非扇形解析样本。取 \(k=1.99\)、\(\alpha\) 位于粗网格两点中间，即可构造“真实严格扇形但粗网格样值为负”的离散误判反例。现有测试已覆盖这一思想，应在自适应版本中进一步验证最终包络包含解析值。

3. **幂零 Jordan 块**

   \[
   A=\begin{bmatrix}0&1\\0&0\end{bmatrix},\qquad f_A(\theta)=-1/2.
   \]

   用于验证全方向均为负、无需局部细化即可确认非扇形。

4. **低维数值域边界**

   \[
   A=\operatorname{diag}(-1,1),\qquad
   f_A(\theta)=-|\cos\theta|,qquad m(A)=0.
   \]

   该例的数值域是穿过原点的线段，可暴露“平面边界”“相对内部”和 semi-sectorial 分类之间的语义差异。第一阶段只能输出容差边界带或 `indeterminate`，不能贸然称为 quasi-sectorial。

5. **相同特征值、不同数值域**

   \[
   A_1=I,qquad
   A_2=\begin{bmatrix}1&k\\0&1\end{bmatrix},\quad |k|>2.
   \]

   两者特征值完全相同，但 \(A_1\) 严格扇形，\(A_2\) 非扇形。该反例说明只观察导纳矩阵特征值不能替代数值域判定。

### 6.2 性质测试

自适应版本应新增以下性质测试：

- **包络单调性**：每次二分后，全局下界不减、全局上界不增；
- **解析包含性**：对上述解析矩阵，真值始终落在返回包络中；
- **酉相似不变性**：\(A\) 与 \(U^*AU\) 的包络及分类一致；
- **正比例缩放不变性**：归一化包络和分类不随正尺度变化；
- **相位旋转协变性**：\(e^{\mathrm{i}\alpha}A\) 的最优值不变、最佳角平移 \(\alpha\)；
- **非光滑性**：使用存在最小特征值分支切换的正规矩阵，验证算法不依赖导数和单峰性；
- **局部细化隔离**：开启或关闭 `fminbnd` 只影响收敛速度和下界质量，不改变在相同最终包络下的认证逻辑；
- **预算耗尽**：评价次数很小时必须返回 `indeterminate`，不得使用候选分类冒充确认分类；
- **极端尺度**：\(10^{-12}A\) 到 \(10^{12}A\) 的归一化结果一致，并记录绝对退化阈值的影响。

### 6.3 随机与频响回归测试

对随机 \(2\times2\) 和 \(4\times4\) 复矩阵，可用极密角网格作为独立参考值，但必须标为“高分辨率对照”而不是精确真值。验收条件是对照值落在自适应包络内，且不存在高分辨率对照与已确认分类相冲突的样本。

论文频响回归测试应保存原始复矩阵快照及其来源元数据，在下列位置重点加密频率采样：

- 论文所述矩形坐标系约 \(0.7\) Hz 的适用边界附近；
- 功率—极坐标系约 \(64\) Hz 的扇形性丧失附近；
- 作者图中任一判据切换、相位张角接近 \(\pi\) 或上下界接触零的频段。

这些频率来自论文 v2 的定性算例描述，必须用复现模型重新计算，不能把图中文字直接当成本项目实验结果。

### 6.4 建议验收门槛

1. 全部解析矩阵的真值位于返回包络内；
2. 已确认分类在解析族和随机高分辨率对照中无假阳性、无假阴性；
3. 正常停止时归一化最优性间隙不超过配置的 \(\varepsilon_{\mathrm{opt}}\)；
4. 预算停止、数值异常和退化输入均有独立状态，不被归并为稳定或不稳定；
5. MATLAB 单元测试记录版本、随机种子、评价次数和运行时间；
6. 对至少一组论文频响，比较固定 16/32/720 点网格、自适应包络和密集对照的分类差异及计算量。

## 7. 学术定位与表述边界

### 7.1 可以采用的表述

建议将本部分工作表述为：

> 针对构网型变流器频率响应矩阵在扇形性临界频段可能发生的角离散误判，构建基于旋转 Hermitian 部分与 Lipschitz 区间包络的自适应判定流程；在明确浮点计算限制的前提下，给出最优分离裕度的离散化上下界，并量化固定角网格对判据适用范围识别的影响。

这属于“面向特定稳定性判据的数值实现改进与误差分析”。如果后续实验表明确实降低了评价次数或减少了错误分类，可以陈述为“提高了临界判定的可靠性和可解释性”。

### 7.2 不应采用的表述

在未完成更广泛检索和严格浮点误差分析前，不应声称：

- 首次提出数值域扇形性判定算法；
- 提出了新的 Hermitian 特征值扰动理论；
- 获得数学意义上的严格机器认证；
- 仅凭扇形性分类即可证明构网型变流器闭环稳定；
- `indeterminate` 等同于系统临界稳定；
- 判据不满足等同于系统不稳定。

分散式小增益—小相位条件是充分条件，项目必须继续用闭环极点和时域响应检验其保守性。数值域判定方法只是这一研究链条中的一个可独立检验的组成部分。

## 8. 推荐实施次序

1. 先把现有均匀网格实现冻结为基线版本，并保留当前 17 项测试；
2. 新增自适应包络函数或选项，不立即替换基线结果；
3. 完成解析矩阵的包络、单调性和预算停止测试；
4. 比较 `fminbnd` 开关对评价次数的影响，确认它不参与上界认证；
5. 从作者算例提取复频响矩阵，建立固定网格—自适应包络—密集对照三方比较；
6. 只有在上述结果稳定后，再讨论 quasi-sectorial、semi-sectorial 与相位上下界的进一步分类；
7. 最终将数值不确定频段与闭环极点、时域仿真结果叠加，形成中期及结项答辩的实质性证据。

## 9. 外部参考文献

1. R. Kippenhahn, “On the numerical range of a matrix,” *Linear and Multilinear Algebra*, English translation of the 1951 paper. [DOI](https://doi.org/10.1080/03081080701553768)
2. C. R. Johnson, “Numerical determination of the field of values of a general complex matrix,” *SIAM Journal on Numerical Analysis*, 1978. [DOI](https://doi.org/10.1137/0715039)
3. K. E. Gustafson and D. K. M. Rao, *Numerical Range: The Field of Values of Linear Operators and Matrices*. Springer. [DOI](https://doi.org/10.1007/978-1-4613-8498-4)
4. R. Bhatia, *Perturbation Bounds for Matrix Eigenvalues*, Chapter 3: Spectral Variation of Hermitian Matrices. SIAM. [DOI](https://doi.org/10.1137/1.9780898719079.ch3)
5. R. A. Horn and C. R. Johnson, *Matrix Analysis*, 2nd ed. Cambridge University Press. [Publisher page](https://www.cambridge.org/highereducation/books/matrix-analysis/FDA3627DC2B9F5C3DF2FD8C3CC136B48)
6. D. Wang, W. Chen, S. Z. Khong, and L. Qiu, “On the Phases of a Complex Matrix,” *Linear Algebra and its Applications*, 2020. [DOI](https://doi.org/10.1016/j.laa.2020.01.035)
7. W. Chen, D. Wang, S. Z. Khong, and L. Qiu, “A Phase Theory of MIMO LTI Systems.” [arXiv v2](https://arxiv.org/abs/2105.03630v2)
8. B. Shubert, “A Sequential Method Seeking the Global Maximum of a Function,” *SIAM Journal on Numerical Analysis*, 1972. [DOI](https://doi.org/10.1137/0709036)
9. P. Hansen, B. Jaumard, and S.-H. Lu, “On the Number of Iterations of Piyavskii's Global Optimization Algorithm,” *Mathematics of Operations Research*, 1991. [DOI](https://doi.org/10.1287/moor.16.2.334)
10. S. Loisel and P. Maxwell, “Path-Following Method to Determine the Field of Values of a Matrix with High Accuracy,” *SIAM Journal on Matrix Analysis and Applications*, 2018. [DOI](https://doi.org/10.1137/17M1148608)
11. MathWorks, “`fminbnd` — Solve single-variable local minimization problem on a fixed interval.” [Official documentation](https://www.mathworks.com/help/matlab/ref/fminbnd.html)
12. 项目基准论文：D. Cifelli 等, arXiv:2510.20544v2. [arXiv](https://arxiv.org/abs/2510.20544v2)
