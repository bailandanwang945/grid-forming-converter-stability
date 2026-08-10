# 平均值 dq 构网型变流器模型 v1：实施前技术规格

状态：**设计提案，尚未实现，不构成当前软件能力声明。**

用途：在指导教师确认完整平均值模型属于结项必要范围后，按本文件实现一个透明、便携、可验证的单机构网型变流器—无限大母线模型。当前低频降阶内核和 Fig. 8 作者模型复现均不因此被改名或替代。

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

网侧电流 `i2` 以变流器流向网络为正：

\[
p=v_t^{\ell T}i_2,\qquad
q=v_t^{\ell T}Ji_2=v_{tq}i_{2d}-v_{td}i_{2q}.
\]

界面与功率报告使用 `i_inj=R(δ)i2`；与作者判据的 `Y_C+Y_net` 接口对接时使用网络流入变流器为正的 `i_dev=-i_inj`。负号必须体现在数据变换中，不能只改标签。

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

## 6. 最低验证门槛

实现不得只验证“代码能运行”，至少包含：

1. 空载解析工作点：`P*=Q*=0、vt=[1,0]、Rv=Xv=0` 时得到 `δ0=0、E0=1、i20=0`；
2. 稳态有功平衡残差 `<1e-8 pu`；
3. 全局坐标旋转后功率与极点不变，导纳满足相似旋转关系；
4. RL 网络数值频响与解析导纳逐点一致；
5. 以 `h、h/2、h/4` 核查数值 Jacobian 收敛，工作点动态残差 `<1e-9`；
6. 三个频点的小幅正弦扰动辨识：导纳幅值误差 `<1%`、相位误差 `<1°`；
7. 非线性平均值响应与同工作点线性响应的小扰动交叉核对；
8. 自由衰减辨识频率和衰减率分别与闭环极点控制在 `2%` 和 `5%` 内；
9. 端口特征零点与直接闭环组装极点交叉核对；
10. 对 `R/X、D、内环带宽、nq` 做稳定、临界附近、失稳三组回归。

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

当前模型的 `Kδ≈1/X` 只是无损、平坦、单位电压特例。未来验证应逐步提高内环带宽、减小 `R、nq、Tm`，检查完整模型主导极点是否收敛到低频模型，而不是预设二者天然等价。

## 8. 启动条件与止损条件

只有在下列条件满足后进入实现：

- 指导教师确认该模型是结项硬指标，或当前同域对照与材料主线已冻结；
- 坐标、端口方向、基值和状态顺序经一次人工审查；
- 首版范围仍限定为单机无穷大母线。

若项目同时扩张到限流、故障、不平衡和任意多机 DAE，应立即停止并重新裁剪范围。该规格的价值是形成可解释的第二层模型，而不是把本科结项项目扩展成不可验收的大型仿真平台。
