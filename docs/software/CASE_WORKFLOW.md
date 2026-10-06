# 案例保存与方案对照

本说明针对当前开发版本。旧的 `v0.5.0-rc1` 运行包不包含本轮新增功能。

## 一次完整分析

1. 启动平台，进入“设备与控制”工作区。
2. 使用默认校核案例，或选择“导入案例”。当前平均值模型只支持单台虚拟同步机（VSM）、LCL 滤波器、单条外部 RL 线路和无穷大母线。
3. 设置模型参数及仿真时长、输出采样间隔、初始相角扰动，运行平均值 dq 分析。
4. 查看工作点检查、闭环特征值和小扰动响应。工作点不可接受或计算失败时，不把结果判为稳定。
5. 选择“保存完整案例”，取得可重新导入的 JSON 文件；选择“结果 JSON”，取得本次返回值和对应完整输入。
6. 选择“分析报告”，按本次成功计算的输入重新生成 HTML 报告。该接口仍会重新计算，并非直接渲染已保存的那一次结果；本次原始返回值以“结果 JSON”为准。

输出采样间隔指定时域输出网格，不代表积分器内部采用固定步长。频率网格随案例保存与导入，不会被默认网格覆盖。

## 比较两项方案

1. 成功运行方案 A，选择“设为基准”。
2. 改变阻尼、线路或其他已有模型参数，重新运行方案 B。
3. 查看“基准与当前方案对照”：两次计算标识、参考稳定性分类、最右特征值实部、主导振荡频率，以及具体输入差异。
4. 选择“导出对比记录”，保存两次完整输入、结果与全部差异。

基准只保存在当前工作区；刷新或离开工作区会清除。单独的案例文件不保存结果，不能替代计算。对比记录不作为可直接导入的案例文件；其中的 `baseline.input`、`candidate.input` 是各自的完整输入。

这项功能用于解释参数调整的计算影响，不自动证明某种控制方法更优，也不构成新的稳定性理论。

## 文件格式与旧文件

- 完整案例：`AverageDQCase/1.0`，包含 `input.topology`、`input.parameters` 和全部仿真、频率设置。
- 对比记录：`AverageDQComparison/1.0`，包含 `baseline`、`candidate`、`changes`。
- 旧文件 `{topology, parameters}`：导入时明确提示采用原界面默认设置，即 2 s、0.002 s、0.1 mrad 和 31 个对数导纳频点。
- 新格式缺字段、版本不支持、非有限数值或超出接口范围时拒绝导入，不半覆盖当前输入。
- 模型暂不支持的拓扑会在应用到平均值工作区之前拒绝。格式校验通过不等于工作点有解或系统稳定。

低频网络工作区仍使用其自身的网络案例格式。网络图的版面位置与电气拓扑分开；只移动图形位置不改变计算模型。

## 复核入口

```powershell
cd E:\git_Projects\grid-forming-converter-stability
npm.cmd --prefix apps/web run build
node scripts/test_average_dq_case_format.mjs
node scripts/test_average_dq_comparison.mjs
node scripts/test_average_dq_request_consistency.mjs
node scripts/test_average_dq_case_workflow.mjs
node scripts/test_reduced_order_request_consistency.mjs
python -m unittest backend.tests.test_average_dq_case_replay -v
```

浏览器测试使用合成接口响应，只核查交互行为；最后一项使用真实 Python 内核核查完整输入重算与阻尼调整。浏览器测试需要本机 Chrome 或 Edge，或设置 `GFM_BROWSER_PATH`，不会下载浏览器。
