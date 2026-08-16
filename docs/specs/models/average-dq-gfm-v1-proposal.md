# 平均值 dq 构网型变流器模型 v1：实施前技术规格

状态：**v1 实验内核已实现并接入软件；已完成内部 verification，尚未完成实物或可信 EMT validation。**

用途：定义并实现一个透明、便携、可验证的单机构网型变流器—无限大母线模型。当前低频降阶内核和 Fig. 8 作者模型复现均不因此被改名或替代；本模型也不因状态数增加而被称为工程真值。

## 1. 模型身份与首版边界

建议名称：**基于功率不变 Park 变换的 LCL 型平均值 dq 构网型变流器模型**。

首版保留：

- 恒定直流侧等效源和平均调制器一阶延迟；
- LCL 滤波器电磁动态；
- VSM 有功—频率外环；
- 无功—电压下垂；
- dq 电压外环与电流内环 PI；
- 可选虚拟阻抗；
- 单台 GFM、单条外部串联 RL 线路和无限大母线；
- 闭环极点、`2×2` 端口导纳与非线性平均值时域响应。

首版排除：

- PWM 开关纹波、直流母线和原动机动态；
- 电流限幅、抗积分饱和、故障穿越和控制模式切换；
- 不平衡、零序、谐波；
- 恒功率负荷形成的代数约束；
- 任意多机网络的非线性 DAE 仿真。

外部方法参照：

- [MathWorks：Design and Analyze Grid-Forming Converter](https://www.mathworks.com/help/sps/ug/design-analyze-gridforming-converter.html) 用于核对 VSM、SCR、X/R 与场景试验的组织方式；
- [MathWorks：Droop Control](https://www.mathworks.com/discovery/droop-control.html) 用于核对下垂控制的概念边界；
- [Imperix TN168：Grid-forming inverter](https://imperix.com/doc/implementation/grid-forming-inverter) 用于核对 dq 双闭环、滤波器和控制延迟结构；
- [Imperix TN170：Virtual synchronous generator](https://imperix.com/doc/implementation/virtual-synchronous-generator-for-droop-control) 用于核对 VSG/VSM 外环组织方式。

这些来源只作为结构与验证方法参照，不替代本项目的方程、单位、工作点和测试。

## 2. 坐标、功率和端口方向

冻结坐标约定 `power-invariant-park-q-lag-v1`：

\[
T_p(\theta)=\sqrt{\frac23}
\begin{bmatrix}
\cos\theta&\cos(\theta-2\pi/3)&\cos(\theta+2\pi/3)\\
-\sin\theta&-\sin(\theta-2\pi/3)&-\sin(\theta+2\pi/3)
\end{bmatrix}.
\]

定义

\[
J=\begin{bmatrix}0&-1\\1&0\end{bmatrix},\qquad
R(\alpha)=e^{J\alpha},\qquad
z^\ell=R(-\delta)z^g.
\]

网侧电流 `i2` 以变流器流向网络为正，`vt` 是外部线路近端的公共连接点（PCC）电压：

\[
p=v_t^{\ell T}i_2,\qquad
q=v_t^{\ell T}Ji_2=v_{tq}i_{2d}-v_{td}i_{2q}.
\]

界面与功率报告使用 `i_inj=R(δ)i2`；端口导纳采用网络流入变流器为正的 `i_dev=-i_inj`。负号必须体现在数据变换中，不能只改标签。这里的端口导纳属于本项目平均值模型，不冒充作者 Fig. 8 的变流器导纳。

采用三相基值：

\[
V_b=V_{LL,rms},\quad I_b=S_b/V_b,\quad Z_b=V_b^2/S_b,\quad
\omega_b=2\pi f_b.
\]

所有设备参数先换算到 `NetworkTopology.base_values`；首版拒绝设备基值与系统基值混用。

## 3. 状态和参数

状态顺序固定为

\[
x=[\delta,\nu,\bar p,\bar q,i_{1d},i_{1q},v_{cd},v_{cq},
i_{2d},i_{2q},\xi_{vd},\xi_{vq},\xi_{id},\xi_{iq},e_d,e_q]^T.
\]

其中 `ν=(ωc-ωb)/ωb`。新增参数对象 `AverageDQGFMParameters/1.0` 至少包含：

- 滤波器：`R1, X1, Bc, R2, X2`；
- 平均调制：`Tm`；
- VSM 与测量：`M, D, tau_p, tau_q`；
- 无功下垂：`n_q`；
- PI：`Kpv, Kiv, Kpi, Kii`；
- 虚拟阻抗：`Rv, Xv`；
- 仅用于工作点诊断、不进入限幅动态的 `Imax, Emax`。

现有拓扑中的 `P*、Q*、V*、M、D、tau_p` 可沿用，但必须记录参数对象版本和基值。

## 4. 非线性平均值方程

外环：

\[
\dot\delta=\omega_b\nu,
\qquad M\dot\nu=P^\star-\bar p-D\nu,
\]

\[
\tau_p\dot{\bar p}=p-\bar p,
\qquad \tau_q\dot{\bar q}=q-\bar q,
\]

\[
E^\star=V^\star+n_q(Q^\star-\bar q),
\]

\[
v_c^\star=\begin{bmatrix}E^\star\\0\end{bmatrix}
-R_vi_2-X_v(1+\nu)Ji_2.
\]

双闭环：

\[
\varepsilon_v=v_c^\star-v_c,
\quad \dot\xi_v=K_{iv}\varepsilon_v,
\]

\[
i_1^\star=i_2+B_c(1+\nu)Jv_c+K_{pv}\varepsilon_v+\xi_v,
\]

\[
\varepsilon_i=i_1^\star-i_1,
\quad \dot\xi_i=K_{ii}\varepsilon_i,
\]

\[
e^\star=v_c+R_1i_1+X_1(1+\nu)Ji_1
+K_{pi}\varepsilon_i+\xi_i,
\quad T_m\dot e=e^\star-e.
\]

LCL 电气动态：

\[
\dot i_1=\frac{\omega_b}{X_1}(e-v_c-R_1i_1)
-\omega_b(1+\nu)Ji_1,
\]

\[
\dot v_c=\frac{\omega_b}{B_c}(i_1-i_2)
-\omega_b(1+\nu)Jv_c,
\]

\[
\dot i_2=\frac{\omega_b}{X_2}(v_c-v_t^\ell-R_2i_2)
-\omega_b(1+\nu)Ji_2.
\]

闭合单机—无限大母线系统时，网侧滤波电感与外部线路电感串联且共享 `i2`。实现将两段 R、X 合并到同一电流微分方程，但不把功率测量点移动到无限大母线。外部线路近端 PCC 电压按线路方程重构：

\[
v_t^\ell=v_g^\ell+R_n i_2+\frac{X_n}{\omega_b}
[\dot i_2+\omega_b(1+\nu)Ji_2].
\]

该处理避免在保持 16 个状态的同时混淆 PCC 功率、线路损耗和无限大母线端功率。

交叉耦合项必须显式写入方程与代码，不得藏入不透明的控制器对象。

## 5. 工作点、线性化和端口导纳

工作点求解先以 `(δ0,E0)` 两个标量为未知量，满足有功设定与无功—电压下垂平衡，再回代其余 14 个状态。不得直接以通用求根器盲解 16 个状态。

每次分析必须报告：

- 两个工作点代数残差；
- `||f(x0,u0)||∞`；
- `||i1||、||i2||、||e||` 与诊断限值；
- 稳态有功平衡残差。

工作点无解、残差超限或状态超出诊断限值时，返回“工作点不可接受”，不得继续输出稳定性结论。

围绕工作点线性化：

\[
\Delta\dot x=A\Delta x+B_v\Delta v_t^g+B_r\Delta r,
\]

\[
\Delta i_{dev}^g=C_i\Delta x+D_v\Delta v_t^g,
\]

\[
Y_{dev}(s)=C_i(sI-A)^{-1}B_v+D_v.
\]

输入与输出均固定在全局同步 dq 坐标中；不得在每个频率点重新令 d 轴跟随端口电压。

外部串联 RL 网络：

\[
Y_{net}(s)=\left[\left(R_n+\frac{X_n}{\omega_b}s\right)I+X_nJ\right]^{-1}.
\]

闭环特征条件为 `det[Ydev(s)+Ynet(s)]=0`。首版只允许一台 VSM GFM、一条外部 ACLine、一个无限大母线、零并联电纳和无静态负荷；不满足时显式拒绝。

## 6. 验证门槛与当前状态

实现不得只验证“代码能运行”。当前状态如下：

1. **已通过**：空载解析工作点 `P*=Q*=0、vt=[1,0]、Rv=Xv=0` 得到 `δ0=0、E0=1、i20=0`；
2. **已通过**：稳态有功平衡残差 `<1e-8 pu`；
3. **已通过**：全局坐标旋转后功率与极点不变，端口导纳满足相似旋转关系；
4. **已通过**：RL 网络频响与解析导纳逐点一致；
5. **已通过**：以 `h、h/2、h/4` 核查数值 Jacobian 收敛，工作点动态残差 `<1e-9`；
6. **已通过内部核查**：在稳定的“变流器—RL 线路—无限大母线”闭环中，分别沿全局 `d、q` 轴注入 `1e-4 p.u.` 源电压正弦扰动，由非线性响应的 PCC 电压与端口电流相量按 `Y=I V^-1` 辨识 `0.2、2、20 Hz` 的 2×2 设备导纳；最大幅值相对误差约 `0.0171%`、最大相位误差约 `0.0231°`，均低于 `<1% / <1°` 门槛。设备开端口矩阵自身不稳定，因此不采用“直接钳位 PCC 后等待稳态”的不适定试验；完整方法、残差和幅值减半核查见 `docs/research/average-dq-port-sinestream-identification.md`；
7. **已通过**：非线性平均值响应与同工作点线性响应的小扰动交叉核对；
8. **已通过内部核查**：从非线性自由衰减相角正峰值辨识频率和指数衰减率，与闭环主导极点的误差分别控制在 `2%` 和 `5%` 内；该核查仍使用同一平均值模型，不冒充外部物理确认；
9. **已通过**：由变流器端口状态空间和外部线路方程重新组装闭环矩阵，与直接闭合矩阵逐元素及逐极点一致；
10. **部分完成**：已在7个阻尼值与6个外部线路电抗值组成的42点网格逐点重算工作点和线性化，并与工作点匹配三状态近似比较；39点稳定性分类一致、3点不一致、0点不可计算。典型失配锚点 `D=60、X=0.1 p.u.` 中，16状态最右极点约为 `+4.586+j35.934 s^-1`，三状态最右极点约为 `-1.231+j14.355 s^-1`，而16状态中与三状态同步模态邻近的模态约为 `-1.140+j14.898 s^-1`；该锚点已通过三档中心差分步长、工作点残差和端口重组复核。线路电阻、内环带宽与 `nq` 的系统灵敏度仍待补。

实现优先使用 Python/SciPy 纯函数 `rhs(x,u,p)` 与 `outputs(x,u,p)`，保持最终软件不依赖 MATLAB；MATLAB/Simulink 只作外部趋势对照。

## 7. 与当前低频模型的层级关系

在内环足够快、忽略线路电阻、固定电压幅值、忽略无功—电压耦合并于平坦工作点线性化时，完整模型可近似为：

\[
\dot\delta=\omega_b\Delta\omega_{pu},
\]

\[
M\dot{\Delta\omega}_{pu}=-D\Delta\omega_{pu}-\Delta p_m,
\]

\[
T_p\dot{\Delta p_m}=K_\delta\Delta\delta-\Delta p_m.
\]

当前模型的 `Kδ≈1/X` 只是无损、平坦、单位电压特例。实现现已在同一带载工作点保持 Q–V 准稳态关系，数值计算 `Kδ=∂p/∂δ`，再组装三状态 VSM—有功测量近似。冻结校核算例中，三状态最右模态与16状态最邻近正虚部同步模态的振荡频率与衰减率误差均小于 `5%`；稳定性分类仍分别使用两层模型各自的最右极点，不能用模态匹配替代稳定性判断。这里的“最邻近”是复平面距离启发式，只用于当前参数点的局部对照；若要论证同一模态跨参数连续演化，还须增加参与向量相似度或模态延拓。

42点 `D–X` 层级扫描进一步说明这种一致性具有参数范围：39点稳定性分类一致，但在 `D=50、60、80` 与 `X=0.1 p.u.` 的强网侧区域出现3个“低频近似稳定、16状态模型失稳”点。以 `D=60、X=0.1` 为例，三状态模态仍接近16状态中的稳定同步模态，但16状态模型另有一个更靠右的失稳模态。左右特征向量构造的归一化参与因子显示，该额外失稳模态的前四项为变流器侧 `q/d` 电流与内部 `q/d` 电压，随后才是电压/电流 PI 积分状态，而相角—有功—频率不再主导。这个内部诊断只能说明“电气与内环状态参与度较高”，不能在没有消融或外部对照时把具体原因归结为 LCL、某一控制环或调制器。该观察是一个可由后续带宽消融和外部模型对照检验的研究假设，不证明现实硬件必然发生同类强网失稳，也不构成对论文小增益—小相位定理的评价。

## 8. 实施边界与止损条件

当前实现已经冻结坐标、端口方向、基值和状态顺序，首版范围仍限定为单机无穷大母线。前端只开放这一范围内确实进入数值内核的参数；不允许通过界面添加负荷、多机或并联电纳后仍沿用当前结论。

若项目同时扩张到限流、故障、不平衡和任意多机 DAE，应立即停止并重新裁剪范围。该规格的价值是形成可解释的第二层模型，而不是把本科结项项目扩展成不可验收的大型仿真平台。
