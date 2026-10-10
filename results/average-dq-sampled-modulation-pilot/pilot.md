# 同步采样调制指令有界预实验

- 状态：verified-bounded-pilot；实际记录 24 / 24 点。
- 采样保持与 τ=Ts/2 一阶滞后标签分歧：4 点。
- 同一 D=60、X=0.1 模型；只同步采样并保持局部控制dq调制包络，PI与外环仍连续；无一拍计算延迟。
- 局部dq包络保持包含连续相位合成，不等同物理αβ/abc保持；未建离散坐标更新时间。
- 属于模型比较，不是实机安全周期；原创性尚未建立。

|电流PI倍率|Ts(s)|原模型alpha|即时alpha|采样logρ/Ts|相位匹配滞后alpha|采样/滞后标签|
|---:|---:|---:|---:|---:|---:|---|
|0.5|0.0001|7.9034935|16.364612|15.759762|15.75726|unstable/unstable|
|0.5|0.0005|7.9034935|16.364612|13.540077|13.49449|unstable/unstable|
|0.5|0.001|7.9034935|16.364612|11.012037|11.11782|unstable/unstable|
|0.5|0.002|7.9034935|16.364612|6.6937666|7.9034935|unstable/unstable|
|1|0.0001|4.586408|17.025417|16.119528|16.111726|unstable/unstable|
|1|0.0005|4.586408|17.025417|12.90639|12.73906|unstable/unstable|
|1|0.001|4.586408|17.025417|9.6397493|9.2292735|unstable/unstable|
|1|0.002|4.586408|17.025417|2.736869|4.586408|unstable/unstable|
|1.5|0.0001|0.79492222|16.112431|15.019477|15.004622|unstable/unstable|
|1.5|0.0005|0.79492222|16.112431|11.243866|10.904307|unstable/unstable|
|1.5|0.001|0.79492222|16.112431|7.9921439|6.5893539|unstable/unstable|
|1.5|0.002|0.79492222|16.112431|-1.1639514|0.79492222|stable/unstable|
|2|0.0001|-1.1556531|14.509107|13.2963|13.273473|unstable/unstable|
|2|0.0005|-1.1556531|14.509107|9.2112032|8.6680099|unstable/unstable|
|2|0.001|-1.1556531|14.509107|6.4662239|3.7311653|unstable/unstable|
|2|0.002|-1.1556531|14.509107|-1.1605635|-1.1556531|stable/stable|
|3|0.0001|-1.1517864|10.529509|9.196234|9.1565447|unstable/unstable|
|3|0.0005|-1.1517864|10.529509|4.9470873|3.9494928|unstable/unstable|
|3|0.001|-1.1517864|10.529509|4.1167136|-1.1564667|unstable/stable|
|3|0.002|-1.1517864|10.529509|-1.1544632|-1.1517864|stable/stable|
|4|0.0001|-1.1486445|6.3947668|5.0319788|4.9758648|unstable/unstable|
|4|0.0005|-1.1486445|6.3947668|319.87293|-0.49482508|unstable/stable|
|4|0.001|-1.1486445|6.3947668|78.076666|-1.1521073|unstable/stable|
|4|0.002|-1.1486445|6.3947668|-1.1506091|-1.1486445|stable/stable|

## 核验

- 全部谱及特征对残差在 pilot.json，含全部24点的4种对照与原模型。
- F由独立控制方程有限差分核对；A22、双Tmod分块和工作点一致性均记录实际误差。
- 小Ts三点报告匹配根误差与回归趋势；整机指数仅作为稳定标签不变阴性对照。
- 两个倍率、两种命令轴及两种状态方向：逐周期固定输入DOP853独立核传播；3周期/方向。
- 原非线性RHS的delta/frequency一周期映射作三幅值中心差分；仅局部dq保持假设。
- 相邻线性化步长1e-5、5e-6核分类指标；落在10倍指标差异或1e-5/s内单列待定。
- 每个状态/谱接近边界或残差超过冻结门槛时为 numerical-pending，不强制标签。

## 复现及限制

```powershell
python experiments/average-dq/run_sampled_modulation_pilot.py
```

- Synthetic average-value single-converter model; no EMT, switching waveform, or hardware validation.
- Only the modulation command is sampled. PI integrators, outer loops and measurement filters remain continuous.
- Held values are local control-dq envelopes with continuously evolving phase synthesis, not physical alpha-beta/abc voltage holds.
- No discrete coordinate-update timing is included; this is not a physical digital-controller reference.
- No computational delay, PWM carrier dynamics, quantization, saturation or multirate control.
- Six prescribed current-PI factors and four periods do not establish a continuous parameter region.
- Small-period convergence is numerical evidence, not a theorem or physical confirmation.
- No novelty established: ZOH, matrix exponential and sampled feedback are existing methods.
- The tau=Ts/2 lag is a low-frequency phase-matched comparator, not an identical actuator.
