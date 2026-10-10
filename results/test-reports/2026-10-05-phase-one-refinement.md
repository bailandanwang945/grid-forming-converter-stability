# 相位跳变可行性阶段与约束细化核查

- 测试：`python -X utf8 -m unittest discover -s experiments/phase-jump -p "test_*.py" -v`。
- 实际环境：既有Python3.12、NumPy2.4.6、SciPy1.17.1，BLAS/OMP/MKL各1线程，未安装依赖。
- 结果：31/31通过，13.822秒；本轮新增8项。
- 新核查/测试文件Ruff通过；冻结执行源有两项E731样式提示，不报告完整静态规则通过。
- 数值运行72.922秒，两策略各3轮。第一次硬有功性能阶段超时保留；预设不超过4轮、每阶段200迭代/10秒。
- 最终两条轨迹均来自收敛的电压目标阶段；分别满足各自策略，非凸硬有功策略不宣称全局最优。
- 独立重算保存系数的端点、分段极值和密网格一致性通过。结果SHA-256：`98e3361b8999efabfbf2cfa46e46182c0c6bb1c3fa2e37dd0cd4cbdeccd8285c`。
- 新生成器保存12阶段、所有系数和失败；最终核查文件为`results/phase-jump-power-feasibility/phase-one-refinement-2026-10-05/independent-verification.json`。
- 本轮没有异机执行，不宣称跨机验证。假设LC输入重积分仅检查方程一致，不是设备约束验证。
- 约束极小越界在原1e-7容差内；不升级为精确或严格连续时间证明。

本轮具体研究结果与缺口见`docs/research/phase-jump-power-feasibility-2026-10-03.md`。原作者源码、原PDF、前三轮记录及执行源均保持不变。
