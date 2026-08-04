# 混合小增益—小相位充分判据：实现与测试计划

日期：2026-08-04<br>
状态：严格扇形、修正版动态整形与作者 Fig. 8 受控阻尼回归已实现；有限采样相位仅作带分支假设的筛查，准/半扇形与连续频率证明尚未完成。

## 1. 目标

把作者的绘图脚本重构为无绘图、无工作区依赖、可单元测试的数值函数。函数回答的是：

> 在给定频率样本、容差和显式相位分支声明下，哪些样点由小增益或小相位条件覆盖，哪些样点未覆盖或数值待定？

函数不得直接输出“系统稳定/不稳定”。

## 2. 分层接口

### 2.1 模型与坐标变换层

建议接口：

```matlab
responses = buildLoopShapedResponses(Yc, Ynet, operatingPoint, conventions, frequenciesHz, options)
```

职责：实现论文 v2 式 (17) 的频率相关整形变换，返回每个频率的
`Jc(:,:,k)` 与 `Jnet(:,:,k)`。该层只负责模型和坐标变换，不作稳定判定。

变换必须遵循 `docs/specs/model-and-port-conventions.md` 的端口方向、修正版
`E,C,F` 及基值约定。原始论文 TeX 中已确认的转录错误不得进入实现。

### 2.2 纯数值判据层

建议接口：

```matlab
result = evaluateMixedGainPhaseSamples( ...
    converterResponses, networkResponse, frequenciesHz, ...
    conventions, preconditions, options)
```

输入为两个 `n×n×N` 复矩阵数组。该层逐频率计算：

- 小增益裕度；
- 变流器矩阵扇形性状态；
- 网络逆矩阵扇形性状态；
- 最大、最小矩阵相位；
- 各变流器上、下相位裕度；
- 跨变流器总体相位展宽裕度；
- 当前频率由小增益、小相位、两者共同覆盖，或未被覆盖；
- 数值待定原因。

### 2.3 自适应频率验证层

建议接口：

```matlab
result = refineMixedGainPhaseFrequencyGrid(modelEvaluator, initialGrid, options)
```

职责：在增益裕度、相位裕度、扇形分离裕度接近零或相邻点状态变化的频带自动插点；
达到评价次数上限仍不能分类时返回 `indeterminate`。

## 3. 输出状态

有限频带筛查状态 `sampledBandStatus` 只允许：

- `gain-covered-on-grid`：所有频率样本均直接由小增益条件覆盖；
- `covered-on-grid-under-phase-branch-assumption`：至少部分样点依赖用户给定相位种子与最近邻分支假设才被覆盖；
- `not-covered-on-grid-under-phase-branch-assumption`：在上述分支声明下存在增益与相位条件均未覆盖的样点；
- `indeterminate`：至少一个关键频率因误差界、病态或分辨率不足无法可靠分类。

采样数组接口的 `theoremStatus` 固定为 `not-evaluated-by-sampled-api`。开环稳定、
实有理且适当、网络逆稳定、无右半平面极零相消、端点与连续全频覆盖等证明，必须由
模型级验证层完成；用户布尔声明与有限频率网格均不得冒充论文定理已确认。

只凭离散频响端点无法排除相邻样点之间发生整圈相位绕转。因此当前相位展开状态为
`resolved-under-nearest-neighbor-assumption`，并记录相位种子、种子频点和来源。真正的
连续分支确认必须增加模型级自适应加密或可验证的相位变化上界。

模型级验证不得接受孤立的 `certified=true` 声明。当前接口要求逐区间提供响应偏差
二范数上界 `delta` 与共同旋转角 `theta`，并由程序重算
`mu = lambda_min(He(exp(-j*theta)*A_left))`。只有端点差异不超过所报上界，且
`mu-delta` 严格为正时，该区间才记为
`branch-verified-under-supplied-deviation-bounds`。这一结论只排除
相位分支混叠并确认区间内严格扇形性；它不自动证明区间内的增益—相位不等式，更不
等同于论文定理的全部前提已经成立。

当前实现使用普通双精度运算，固定返回 `floatingPointCertified=false`。上界证据必须与
模型哈希、频率网格、响应标识和左端点参考约定一致；在尚未引入向外舍入或区间算术前，
不得使用“计算机辅助认证”表述。

显式相位种子必须与其所在频点的矩阵相位一致。若种子位于频带中部，则当前实现只向
高频方向传播，种子以前的频点与区间保持 `indeterminate`；不得把后置种子伪装成频带
起点的锚定证据。

缺少上述模型级证据时，`refineMixedGainPhaseFrequencyGrid` 仍可自动插入频点，以暴露
有限网格遗漏的变化，但最终只能写作 `refined-screening-only`。频点加密本身不是连续
频带证明。

逐频率原因码至少包括：

- `gain-pass`；
- `phase-pass`；
- `both-pass`；
- `gain-fail`；
- `converter-nonsectorial`；
- `network-inverse-nonsectorial`；
- `upper-phase-overlap`；
- `lower-phase-overlap`；
- `converter-phase-spread-overlap`；
- `gain-boundary-indeterminate`；
- `sectoriality-indeterminate`；
- `phase-boundary-indeterminate`；
- `ill-conditioned-network`。

## 4. 数值要求

1. 增益条件使用奇异值，不显式形成 `inv(Jnet)` 来计算增益；
2. 需要网络逆矩阵相位时优先使用线性方程求解，并报告条件数；
3. 容差采用 `max(absTol, relTol*scale)`，不得使用与矩阵尺度无关的固定阈值；
4. 相位是矩阵合同分解意义下的相位，不得用矩阵元素相角或特征值相角冒充；
5. 相位区间必须正确处理跨 `±π` 的分支；
6. 半扇形、准扇形和严格扇形必须按定理所需对象分别处理，证据不足时返回待定；
7. 输出必须包含频率范围、频率点数、容差、最大条件数和停止原因。

逐频率相位条件除各变流器与网络逆矩阵的上下相位约束外，还必须计算

```text
phaseSpreadMargin = pi - (
    max_i upperPhase(Jc_i) - min_i lowerPhase(Jc_i))
```

多机条件要求该裕度严格为正。作者绘图脚本没有显式执行这一约束，评价器不得照搬遗漏。

## 5. 最小测试集

### 5.1 解析矩阵

- 正定 Hermitian 矩阵：相位区间为 `[0,0]`；
- 纯相位旋转的正定矩阵：相位区间整体平移；
- 对角矩阵 `diag(e^{jα},e^{jβ})`，且 `|α-β|<π`；
- 数值域包含原点的 `diag(1,-1)`：不得给出可用小相位区间；
- 数值域以原点为边界点的半扇形/准扇形候选；
- 病态但可逆的网络矩阵；
- 跨 `±π` 的窄相位区间。

### 5.2 逻辑测试

- 仅小增益通过；
- 仅小相位通过；
- 两者均通过；
- 两者均明确失败；
- 一个条件通过而另一条件数值待定时，总体仍可确认；
- 两者均未通过且至少一个待定时，总体必须待定；
- 任何频率未覆盖时，整体不得标记为已覆盖；
- 两台装置相位分别为 `0.6*pi` 与 `-0.6*pi` 时，即使各自上下相位约束通过，
  跨变流器总体相位展宽也必须使小相位条件失败；
- 有限频率网格全部覆盖时，`theoremStatus` 仍固定为不由采样接口评价。

### 5.3 变换一致性测试

- 非单位工作点下以有限差分验证修正版 `E,C,F`；
- 验证 `Jc+Jnet = E*(Yc+Ynet)*F`；
- 把网络侧误写为 `+C` 时测试必须失败；
- `E=F=I,C=0` 时严格退化为原始模型；
- 检查动态 `F(jw)` 在全频带的条件数和奇异点。

### 5.4 回归测试

- 作者稳定 Fig. 8 工况 `D=0.5`；
- 作者不稳定 Fig. 8 工况 `D=0.05`；
- 当前求得的物理临界点 `D≈0.07421769, κ=1`；
- 论文所述约 `0.9 Hz` 原始 dq 表述非扇形边界；
- 论文混合变换后的全频扇形性和相位条件图。

## 6. 验收条件

1. 解析测试和逻辑测试全部通过；
2. 作者脚本与新函数在远离边界的频点给出一致结论；
3. 边界差异能够归因于容差、相位分支或离散分辨率；
4. 一次函数调用不产生图窗、不修改工作目录、不读取基础工作区变量；
5. 输出能够直接用于构造 \((D,\mathrm{SCR})\) 参数平面上的充分判据确认区域。

## 7. 当前实现边界

- `computeStrictSectorialPhaseInterval`：基于严格扇形分离角，将旋转矩阵写成
  `H+jG`，由 Hermitian 矩阵对 `(G,H)` 的广义特征值计算合同分解意义下的矩阵相位；
- `evaluateMixedGainPhaseSamples`：已实现逐频率小增益、上下相位、多机总体相位展宽、
  网络条件数、原因码以及 `sampledBandStatus/theoremStatus` 分层；
- 解析与逻辑测试已覆盖跨 `±pi` 分支、小增益兜底、相位兜底、多机展宽失效、
  网络病态和有限网格不得冒充全频定理等情形；
- 当前只在严格扇形分类得到确认时计算相位。准扇形、半扇形或分类边界均保持待定；
- `buildMixedLoopShapingSamples` 已实现修正版动态 `E,C,F`，并用有限差分、矩阵恒等式、
  不对易权重和跨机网络块进行独立验证；
- 作者 Fig. 8 同一工作簿的 `D=0.05/0.5` 原始频响和闭环谱已固化为可跟踪夹具，
  无绘图回归分别得到 75 个未覆盖点与 0 个未覆盖点；
- 作者不稳定工况前 38 个频点的严格相位不可用，但由小增益覆盖；相位连续段从第 39 点
  显式锚定。该结果仍受最近邻分支假设约束；
- 临界阻尼已由闭环模型定位为 `D≈0.07421769048`。IEEE 14 节点、准/半扇形及模型级
  连续全频证明尚未完成。因此当前状态不能称为“完整复现论文定理”。
