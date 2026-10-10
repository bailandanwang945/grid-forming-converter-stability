# LC内部约束与功率下界计算测试（2026-10-05）

正式目录：`E:\git_Projects\grid-forming-converter-stability`。Python：`F:\SOFTWARE\Python312\python.exe`。仅本进程将OPENBLAS/OMP/MKL线程数设为1；没有修改全局环境或启动MATLAB。

## 实际执行

```text
python -X utf8 -m unittest discover -s experiments/phase-jump -p "test_*.py" -v
```

实际结果：48 Passed / 0 Failed / 0 Skipped，16.665s。单独新增功率内近似测试7/7通过，.055s。本轮之前31项，本轮新增LC10项和功率下界7项，不是48项均为新功能。

覆盖仿射LC硬件映射与直接B样条导数、方程/端点连接、epigraph Jacobian、新电流约束不改变原约束、结果核查拒绝损坏端点、数值布尔JSON序列化；功率模块另覆盖含correction全部Q/q/r项、精确差值恒等式、相切值/梯度、凹性、实际样条功率/Jacobian一致性、小特征值不丢弃和非法输入。

静态检查：本轮新增11源/测试文件Ruff通过。此前冻结的`run_phase_one_refinement.py`两项E731样式提示未修改；不称整个仓库静态检查全通过。

## 保存结果的核查

- `lc-voltage-envelope-2026-10-05/independent-verification.json`：原始结果SHA-256为`fe1da5c548ea561365c39958e8e4e9a6195312d497b5f5b7bfffae297b9e9860`；检查旧可行轨迹、新A/B候选及端点条件，新A/B均未通过。
- `lc-followup-verification-2026-10-05.json`：重新读取九条固定组合及两条固定电压上限候选，核对来源指纹，重新数值计算，均无联合约束可行轨迹。
- 上述检查使用独立于优化评估器的原始样条/多项式计算，但共享同一声明物理模型。它们是浮点核查，不是严格区间证明、硬件验证或独立实测。

## 不能据此声称

测试通过不等于优化问题已找到可行解。本轮三项检查均未成功，失败不证明原问题不可行。功率凹下界模块测试通过不等于已运行凸轨迹优化或全时间区间验证，也不是新算法。本轮不改论文稳定性定理状态或生产API/UI。
