# 平均值 dq 模型的三频点端口正弦辨识

## 研究问题与判据

本实验检验团队自建 16 状态正序平均值 `dq` 模型的端口线性化是否与同一模型的非线性小扰动响应一致。固定单机无穷大母线校核算例，在 `0.2、2、20 Hz` 分别施加幅值 `1e-4 p.u.` 的正弦源电压扰动，目标为：2×2 端口导纳各元素的幅值相对误差小于 `1%`、相位误差小于 `1°`。

- 主假设：在既定工作点和小扰动幅值下，由非线性响应辨识得到的端口导纳与局部线性化频响在预设容差内一致。
- 替代解释：误差可能被过短暂态、病态相量反演或人为选择扰动幅值掩盖。
- 失败条件：任一元素超过幅相限值，谐波与残余暂态的归一化残差达到 `2%`，PCC 电压相量矩阵条件数达到 100，积分失败，或幅值减半后结果不能保持小信号收敛。

这是一项内部软件验证（verification），不是对真实变流器、可信 EMT 模型或硬件的外部确认（validation）。

## MathWorks 方法校准

本机 MATLAB R2024b 的 `help` 与官方文档确认了以下标准流程：

1. 以已求得的稳态工作点初始化模型；
2. 使用 `frest.Sinestream` 形式的逐频正弦激励，明确 `SettlingPeriods`、`NumPeriods` 与 `SamplesPerPeriod`；
3. 对 Simulink 模型可用 `linio` 指定分析点，以 `frestimate` 估计频响；
4. 将仿真估计频响与 `linearize` 得到的精确线性化比较，并检查时变源对输出的干扰。

官方入口：

- [命令行估计 Simulink 频率响应（R2024b）](https://www.mathworks.com/help/releases/R2024b/slcontrol/ug/estimate-frequency-response-matlab-code.html)
- [独立扰动信号生成（R2024b）](https://www.mathworks.com/help/releases/R2024b/slcontrol/generate-perturbation-signals.html)
- [`frestimate`](https://www.mathworks.com/help/releases/R2024b/slcontrol/ref/frestimate.html)
- [`frest.Sinestream`](https://www.mathworks.com/help/releases/R2024b/slcontrol/ref/frest.sinestream.html)

项目的便携式 Python 实现遵循同一实验契约，但不要求最终用户安装 MATLAB。MATLAB/Simulink 保留为后续独立实现的趋势对照，而非软件运行依赖。

## 为什么不直接钳位 PCC 电压

在线性端口表达式

\[
Y_{dev}(s)=C_i(sI-A_{dev})^{-1}B_v+D_v
\]

中，PCC 电压是设备端口输入。然而当前校核工作点的设备开端口矩阵 `Adev` 的谱横坐标为 `+11.9421 s^-1`，并非渐近稳定。因而直接规定 PCC 电压、等待设备达到稳态正弦响应并不成立；这种仿真会让自由响应增长，而不是提供可靠的稳态辨识数据。

实验改为保持“变流器—外部 RL 线路—无限大母线”闭环。闭环谱横坐标为负，在无限大母线电压源处分别注入全局 `d、q` 轴正弦扰动，同时从非线性状态重构 PCC 电压相量矩阵 `V` 与网络流向设备为正的电流相量矩阵 `I`，再计算

\[
\hat Y_{dev}=I V^{-1}.
\]

两个独立轴向试验使 `V` 为 2×2 矩阵。其条件数作为反演可靠性指标；三个频点的条件数均小于 3.1。输出相量通过“常数项 + 余弦项 + 正弦项”的最小二乘拟合得到，拟合残差保留为暂态、谐波与数值误差的综合诊断。

## 冻结实验契约

| 项目 | 数值 |
|---|---:|
| 频率 | `0.2、2、20 Hz` |
| 无限大母线电压扰动幅值 | `1e-4 p.u.` |
| 最短舍弃暂态 | `2.5 s`，向上取整为完整周期 |
| 测量周期 | 2 |
| 每周期采样点数 | 128 |
| 坐标系 | 固定全局同步 `dq` |
| 电流正方向 | 网络流向设备为正 |
| 幅值误差门槛 | `<1%` |
| 相位误差门槛 | `<1°` |
| 归一化残差门槛 | `<2%` |
| PCC 电压相量矩阵条件数门槛 | `<100` |

低频点采用 BDF、高频点采用 Radau 隐式变步长积分器；两者使用同一相对与绝对容差 `1e-7 / 1e-9`。求解器切换只为提高数值效率，不改变模型、激励、测量窗口或误差定义。

## 结果

| 频率 / Hz | 舍弃周期 | 求解器 | 最大幅值相对误差 | 最大相位误差 / ° | 最大归一化残差 | `cond(V)` |
|---:|---:|---|---:|---:|---:|---:|
| 0.2 | 1 | BDF | `3.018e-5` | `0.003235` | `1.146e-4` | `3.0688` |
| 2 | 5 | BDF | `1.710e-4` | `0.023089` | `7.595e-4` | `2.8059` |
| 20 | 50 | Radau | `3.164e-6` | `0.000134` | `5.732e-6` | `1.7042` |

三点均通过预设门槛。全实验的最不利幅值误差约为 `0.0171%`，最不利相位误差约为 `0.0231°`。在 2 Hz 将扰动幅值减半至 `5e-5 p.u.` 后，辨识矩阵各元素相对变化的最大值约为 `0.0294%`，支持所用幅值处于当前数值实验的小信号区间。

## 结论边界

结果支持：在团队单机平均值 `dq` 校核算例、既定工作点、三个所测频点与小扰动范围内，非线性闭环正弦响应与端口线性化实现保持一致；端口方向、PCC 重构、坐标系和频响计算未发现达到预设门槛的矛盾。

结果不支持：模型参数已经拟合某台物理变流器；三个频点足以代表连续全频段；平均值模型已经通过 EMT、硬件在环或实物确认；开端口设备本身稳定；该实验验证了论文的小增益—小相位稳定性充分条件。

## 复现入口

```powershell
python experiments/average-dq/run_port_sinestream_identification.py
python -m unittest backend.tests.test_average_dq_port_identification -v
```

机器可读结果：

- `results/average-dq-port-identification/port_sinestream_identification.json`
- `results/average-dq-port-identification/port_sinestream_identification_elements.csv`
