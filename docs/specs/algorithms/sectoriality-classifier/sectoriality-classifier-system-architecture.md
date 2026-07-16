# Sectoriality Classifier：系统与架构规格

> 版本：0.1  
> 最后更新：2026-07-16

## 1. 目的

对单个频率点处的复方阵 `A`，判断其数值域与原点之间的几何关系，并给出数值误差界，为相位边界计算和小相位判据的适用性分析提供前置条件。

本算法不判断闭环稳定性，也不在第一版中细分 `semi-sectorial` 与 `quasi-sectorial`。

## 2. 外部接口

```matlab
result = classifyNumericalRange(A, options)
```

### 2.1 输入

| 名称 | 类型 | 单位 | 约束 |
|---|---|---|---|
| `A` | 有限复数方阵 | 与原模型一致 | 非空、二维、方阵、无 NaN/Inf |
| `options.NumAngles` | 正整数 | 无 | 默认 720，至少 16 |
| `options.RelTol` | 非负标量 | 无 | 默认 `1e-10` |
| `options.AbsTol` | 非负标量 | 与 `A` 相同 | 默认 `0` |
| `options.Refine` | 逻辑标量 | 无 | 默认 `true` |

### 2.2 输出

`result` 为结构体：

| 字段 | 含义 |
|---|---|
| `classification` | 已认证的 `strict-sectorial`、`boundary`、`non-sectorial`、`degenerate`，或证据不足的 `indeterminate` |
| `candidateClassification` | 仅按最佳已评估裕度给出的候选分类，不等同于证书 |
| `isStrictSectorial` | 是否能够判定为严格扇形矩阵 |
| `isBoundary` | 是否落入尺度容差带 |
| `isCertified` | 当前分类是否得到裕度上下界的共同支持 |
| `theta` | 最大化分离裕度的旋转角，rad |
| `margin` | 最佳已评估分离裕度，是全局最大值的下界 |
| `normalizedMargin` | `margin / ||A||₂` |
| `lowerBound` / `upperBound` | 全局最大分离裕度的保守数值区间 |
| `optimalityGap` | 上下界差 |
| `tolerance` | 本次实际使用的尺度容差 |
| `scale` | `||A||₂` |
| `method` | 算法与版本说明 |

## 3. 数学原理

对任意角度 `θ`：

`H_θ(A) = (e^{-jθ}A + e^{jθ}A^*)/2`。

对单位向量 `x`，`x^*H_θ(A)x` 是旋转后数值域在实轴方向的投影。若其最小值为正，则整个数值域位于过原点直线的一侧。因此：

`m(A) = max_θ λ_min(H_θ(A)) > 0`

表明 `0 ∉ W(A)`，并且 `W(A)` 可以包含在角宽小于 `π` 的扇形区域内。

实现先在均匀角网格上搜索，再在最佳网格点附近用一维有界优化细化。有限采样值只构成 `m(A)` 的下界。利用 `λ_min` 的 Lipschitz 性，角网格步长为 `h` 时采用

`upperBound = maxGrid + 2 sin(h/4) ||A||₂`

作为保守上界。仅当下界大于容差时认证严格扇形；仅当上界小于负容差时认证非扇形；证据区间未能落入单一类别时输出 `indeterminate`。

## 4. 组件架构

1. 输入验证：检查矩阵和选项；
2. 尺度计算：计算 `||A||₂` 和实际容差；
3. 粗搜索：在 `[−π, π)` 上计算分离裕度；
4. 局部细化：在最佳网格点附近优化；
5. 分类器：根据裕度和容差输出分类；
6. 结果结构化输出：返回角度、裕度、误差界、尺度和方法元数据。

## 5. 设计约束

- 不使用 `inv`；
- 不绘图、不修改路径、不写文件；
- 同一输入和选项必须确定性输出；
- 当 `AbsTol=0` 或 `AbsTol` 与矩阵同比例缩放时，分类应对正比例缩放保持一致；
- `boundary` 是保守状态，后续算法不得把它自动当作严格扇形；
- 只测试公共接口，不依赖内部函数结构。

## 6. 接受标准

- 正定 Hermitian 矩阵判为 `strict-sectorial`；
- 数值域含原点内部的幂零 Jordan 块判为 `non-sectorial`；
- 数值域接触原点的半正定矩阵候选分类为 `boundary`；若有限证据不能认证，则输出 `indeterminate`；
- 零矩阵判为 `degenerate`；
- 正比例缩放不改变非退化分类，归一化裕度保持一致；
- 非方阵、NaN/Inf 和非法选项产生稳定错误标识。

## 7. 研究说明

定义依据为项目内 arXiv v2 源码 `references/source/arxiv-2510.20544v2/source/sec1_Introduction.tex`。第一版只实现严格分离证书；`semi-sectorial` / `quasi-sectorial` 的进一步分类将在 Phase 3 单独规格化。
