# 平均值模型的指令采样保持对照（试验性）

## 用途与适用对象

在团队单台构网型变流器（GFM，grid-forming converter）与无穷大母线的平均值模型中，比较不同指令执行假设的闭环谱。用户可以改变已支持的设备、控制及线路参数，再比较连续调制近似与采样保持判断；本功能不读取固定试验结果作为答案。

这是一项模型假设检查，不是新的稳定性定理，也不是原作者完整MATLAB流程的替代品。现有16状态平均值分析的默认行为不变。新功能不含完整数字比例—积分控制（PI，proportional–integral control）、采样测量链、限幅、脉宽调制（PWM，pulse-width modulation）、开关过程或硬件确认。

## 变量、单位与计算关系

原模型的前14个状态记为x（state perturbation），最后两个状态是局部dq内部电压u（internal-voltage perturbation）。Tmod为原连续调制滞后的时间常数，Ts为指令采样周期，单位均为s。指令Jacobian记为F（command-feedback matrix），连续子系统矩阵记为A0和B（plant and input matrices）：

\[
A_{\rm original}=\begin{bmatrix}A_0&B\\F/T_{\rm mod}&-I/T_{\rm mod}\end{bmatrix},
\qquad A_*=A_0+BF.
\]

A*为理想即时指令参照，不等于原固定Tmod模型。原模型有16个状态，理想模型有14个状态。

采用零阶保持（ZOH，zero-order hold）时，块矩阵指数给出E和Gamma，无须假定A0可逆：

\[
\exp\left(T_s\begin{bmatrix}A_0&B\\0&0\end{bmatrix}\right)
=\begin{bmatrix}E&\Gamma\\0&I\end{bmatrix}.
\]

零拍指令延迟的周期矩阵为Phi=E+Gamma F。若本周期施加上一采样计算的指令v，下一周期施加本次起点计算的F x，则一拍延迟的增广周期矩阵为

\[
\Phi_d=\begin{bmatrix}E&\Gamma\\F&0\end{bmatrix},\qquad
z_k=[x_k;v_k].
\]

一拍模型的16个周期乘子均参与稳定性分类，不能删除指令记忆分支。对整个原闭环矩阵计算exp(A_original Ts)只是观察采样，不是增加采样反馈。

源码约定局部量=R(-delta)全局量。J=[[0,-1],[1,0]]，u0是工作点局部电压，e_delta抽取角度状态。全局同步dq保持使用工作点对齐的缓存扰动，C=(J u0)e_delta^T，A0g=A0-B C、Fg=F+C、B不变；于是A0g+B Fg=A*。全局缓存是上一采样时完成坐标变换的完整快照，不用当前角度重转旧局部指令。两种保持均不是固定物理abc或静止alpha-beta电压保持。

同保持坐标的连续低频一阶参照使用tau=(d+0.5)Ts，其中d为0或1。它仅作慢动态首阶延迟匹配，不是保持器的全频等价实现，不保证稳定分类相同。原固定Tmod模型与这个随Ts变化的参照分别返回。

## 结果字段与不确定性

每次比较返回四类谱：原连续调制、理想即时指令、同保持坐标的低频一阶滞后、采样指令。连续谱以alpha=max Re(lambda)报告，采样谱以g=log(rho(Phi))/Ts报告；单位均为s^-1。rho为谱半径（spectral radius），不是振荡频率。负值参考稳定、正值参考失稳，接近边界或数值诊断失败的记录单列为数值待定。周期乘子本身无量纲。

不输出主支复对数频率作为唯一物理频率，不推导通用安全采样周期。特征对残差和双线性化步长差异是数值诊断，不是经证明的根误差上界。缺少第二步长模型时应显式标为未提供步长检查；不能将其显示为已通过。

模型层只接受本项目明确的16状态结构；泛型矩阵函数仅用于数学计算和解析回归。全部输入须为有限实数且尺寸一致；布尔值不得当周期或延迟，复数不得隐式丢弃虚部。非有限矩阵、指数溢出或求谱失败不能返回稳定标签。另一份线性化模型必须来自相同参数、拓扑及工作点，并使用不同差分步长。

既有数值基准覆盖Ts=100、500、1000、2000微秒等有限参数切片；仅位于周期范围内不表示其他参数已经核验，也不表示实际设备适用。接口计算范围更宽时，须与基准覆盖分开标示。所有结果保留theorem_status=not-evaluated-by-sampled-api。

## 独立试验接口

`POST /api/experimental/average-dq/sampled-command`

- 输入：一个已有平均值校核预置算例，或完整topology和parameters；不得混用或只交一半。
- 指令假设：sampling_periods_s、holding_frames、delay_steps，全部选项显式回传。
- 周期严格递增、不得重复，最多16个；坐标最多2种、延迟只能0或1，最多64条比较。
- 接口允许周期1e-7至0.02s，只是计算规模约束，不是物理安全或适用范围。新增周期／延迟字段中的布尔值、数值字符串及未声明字段拒绝；非标准JSON数字NaN／Infinity、浮点溢出、嵌套超过32层以422拒绝，请求体超过2 MiB以413拒绝，不在错误响应中重新序列化非有限输入。既有拓扑／设备参数仍遵循原领域模型的输入规则。
- 重新求工作点、使用1e-5及5e-6两种线性化相对步长；不运行非线性时域，也不读取冻结结果表。
- 返回完整输入、工作点残差、来源、四类参照及适用范围。前端尚不默认调用此接口。

最小请求示例（服务运行后也可在现有API说明页中调用）：

```json
{
  "preset_id": "average-dq-smib-verification",
  "sampling_periods_s": [0.001],
  "holding_frames": ["local-control-dq", "global-synchronous-dq"],
  "delay_steps": [0, 1]
}
```

该请求返回四条假设比较，每条各含四类参照。自定义算例应删除preset_id，并同时提交当前编辑的完整topology和parameters；电流PI、阻尼及线路参数没有隐藏倍率或插值。结果保留原输入供报告对照。

## 回归依据

旧pilot和holdout保留为只读数值基准，迁移后须独立重建模型，对192条冻结记录逐项比较完整谱、增长率、分类和维度，并核对基准文件本体及其来源清单。不能通过改写期待值使迁移通过。原有72条采样／低频近似标签分歧、0/96保持坐标标签差异、38/96延迟标签差异分别记录，不把计数当概率。

单元测试应包含奇异A0、两个方向的稳定分类反例、一拍缓存时序、完整记忆谱、坐标角项、近边界待定、无第二步长、参数不匹配、非法输入和输入不变性。软件迁移一致性不等于外部模型或硬件确认。

实现入口：`backend/core/average_dq_sampled_command.py`；接口：`backend/api/sampled_command.py`。实际测试结果登记在开发日志和 `results/verification/`，未完成的核验不在本规格中冒称通过。

## 复用的方法与来源

零阶保持和块矩阵指数采用现成方法，不自研数值求解器。方法依据为[MathWorks连续—离散转换说明](https://www.mathworks.com/help/control/ug/continuous-discrete-conversion-methods.html)；矩阵指数使用项目既有SciPy依赖，参见[SciPy expm文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.expm.html)。2026-10-02在线核对这些官方入口；在线文档版本不代替运行记录中的实际环境版本。

接口的局部请求预检查采用[FastAPI官方自定义APIRoute方法](https://fastapi.tiangolo.com/how-to/custom-request-and-route/)，仅作用于新路由，不替换全局验证错误处理。实际异常情形由接口测试重现并核对。

完整研究来源、已核验局部非线性周期映射和未验证边界，见[本轮研究记录](../../research/brainstorming-session-2026-10-02.md)。本规格按电力系统科研技能固定公式、输入、对照及失败条件，并按科研写作技能区分实现核验与物理确认。
