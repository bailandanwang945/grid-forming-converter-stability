# 网络接线编辑器操作与显示验证

日期：2026-10-07。正式目录：`E:\git_Projects\grid-forming-converter-stability`。
这是当前开发源码的定向验证，不是便携包发行或异机验证，也不是新增稳定性方法的研究证据。

## 1. 实际改动

- 以自绘 SVG 简化单线图符号替换母线与设备的通用卡片图标；不增加设备计算模型。
- 明确分开选择、接线和平移，支持两母线点击接线、拖动端子接线、网格吸附及取消接线。
- 补齐扩大画布期间的保存、导入、分析入口，保留旧案例格式及版面与电气输入的分离。
- 同端点并联线路按编号分开显示；线路标注显示名称，R/X 保留在悬停说明及参数栏。绘图方向不改变电气端点编号。
- 元件列表可选中被遮挡的线路；未完成或无效重接保留原线，拒绝操作不新增历史。
- 线路表与图形共用端点校验；VSM 接入下拉过滤已被其他 VSM 或等值电源占用的母线，并补适用性预检。
- 固定 1×1 像素几何锚点，另以伪元素扩大点击区域，修复较大端子造成的符号—导线间隙；模式切换不移动锚点。

## 2. 已执行的测试

| 检查 | 实际结果 | 证据性质 |
|---|---|---|
| `npm.cmd run build` | TypeScript 与生产构建通过 | 源码编译；保留既有大分块体积警告 |
| `test_network_topology_checks.mjs` | 22 个场景通过 | 接线与模型范围纯函数；含新增共母线限制 |
| `test_network_editor_operations.mjs` | 9 类操作场景通过 | 创建/重接无副作用、无效端点保护及参数保留 |
| `test_network_editor_usability.mjs` | 25 个操作场景通过 | 实际浏览器点击、拖动、下载和导入；不调用数值 API |
| `test_network_topology_applicability_ui.mjs` | 既有 9 个场景通过 | 接线检查、模型范围和布局撤销回归 |
| `test_reduced_order_request_consistency.mjs` | 既有 33 个场景通过 | 输入—异步结果归属回归；合成 API 响应 |
| 既有 `ReducedOrderModelTest` 快速子集 | 10 个测试通过 | 真实 Python 内核；解析特征根、Kron 约简及范围拒绝等 |
| `verify_all.ps1` 语法检查 | 通过 | 两个新增操作测试接入统一入口；未执行全量入口 |

各组可能验证相同事实，不合并为“新增算法测试总数”。没有把浏览器合成响应作为数值结果。
真实内核子集不包含长时域频率对照、参数扫描或 MATLAB；详细方法名在第 4 节。

25 个操作场景实际检查了：默认模式、SVG 母线、点击与端子拖线、分离的并联路径与标注、无效接线和历史保护、取消、参数修改、线路删除撤销、键盘撤销重做、输入框快捷键范围、扩大后保存、吸附拖动、平移、适配、源与参考母线同步迁移、真实参数表保护、390px 重叠元件列表操作，以及桌面/手机操作与投退。
几何场景检查两条母线的 8 个端子和两电源的 2 个端子；按 React Flow 外缘公式计算的锚点与符号边界误差均不超过 1 屏幕像素，选择—接线—选择切换后位置误差仍不超过 1 像素，保存的拓扑与版面不变。
输入框的测试确认编辑器不拦截 Ctrl+Z，没有声称覆盖浏览器原生文字撤销的全部行为。
端子拖线另使用位于真实 1×1 端子边界之外的起落点；实际命中检测必须识别原端子，再由鼠标完成创建、下载核对和撤销，确认扩大点击区不是仅有 CSS 声明。
追加这一检查时，拥挤布局曾因分两次读取坐标而出现一次偶发断言失败；改为同一次取样后，完整 25 场景通过。原重叠坐标和“超过较小图元半宽/半高”的阈值未修改，没有通过改变案例或放宽阈值掩盖失败。

浏览器测试用独立的随机本机端口和已安装 Chrome/Edge，无外网访问、依赖安装或数值/报告 API 调用；脚本设 60 秒总时限并在结束时关闭浏览器与测试服务。不占用或停止原有 8000 服务。

## 3. 截图核查与保留边界

最终版本截图已生成并回看，1440px 与 390px 没有页面级横向溢出。截图使用测试接线，不是原工程图或物理试验结果：

- [桌面编辑器](../../output/ui-review/network-editor-20261007/network-editor-usability-1440.png)
- [手机编辑器](../../output/ui-review/network-editor-20261007/network-editor-usability-390.png)
- [手机重叠布局列表选线](../../output/ui-review/network-editor-20261007/network-editor-usability-crowded-390.png)

目录中旧 `failure.png` 是此前排查拥挤布局时的失败截图，不作为最终结果。
并联分槽不是障碍避让布线；拖动造成的任意遮挡或交叉仍需人工调整，元件列表提供替代选择入口。
没有独立断路器/隔离开关、变压器或同步机图形与计算模型，没有新增潮流、短路与故障穿越功能；不声明 GB/IEC 完整制图符合性。论文与作者基线、数值内核和定理状态均未修改。
当前源码与构建目录已更新；旧便携 ZIP 未重打包，未提交或推送。本次没有运行 MATLAB/Simulink、全量统一验证或异机测试。

## 4. 重跑入口

在正式项目根目录、已有依赖及浏览器环境下，先运行 `npm.cmd run build --prefix apps/web`，再分别运行：

```powershell
node scripts/test_network_topology_checks.mjs
node scripts/test_network_editor_operations.mjs
$env:GFM_UI_REVIEW_DIR='output/ui-review/network-editor-20261007'
node scripts/test_network_editor_usability.mjs
node scripts/test_network_topology_applicability_ui.mjs
node scripts/test_reduced_order_request_consistency.mjs
```

使用方法见 [网络接线编辑说明](../../docs/software/NETWORK_EDITOR.md)；工程设备与分析范围见 [主接线方案](../../docs/design/engineering-main-connection-plan-2026-10-06.md)。

真实内核快速子集可使用既有 Python 环境分别运行以下方法；本次由独立复核代理以 `python -B -m unittest -v` 执行，进程硬超时 45 秒，10 项通过（unittest 0.029 秒）；主代理复跑同一子集也通过（0.062 秒），不重复累计：

```text
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_out_of_service_parallel_line_does_not_enter_stiffness
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_kron_reduction_matches_two_series_reactances
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_stable_single_machine_poles_match_analytic_cubic
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_analytic_critical_damping_has_marginal_oscillatory_pair
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_low_damping_case_is_unstable
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_pure_island_is_rejected_with_scope_explanation
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_reference_bus_must_be_grounded_infinite_bus
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_unsupported_droop_controller_is_rejected
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_assumptions_explicitly_exclude_unmodelled_dynamics
backend.tests.test_reduced_order_model.ReducedOrderModelTest.test_time_response_rejects_nonmonotonic_samples
```
