# 元件库拖放与快捷键验证

日期：2026-10-07。正式项目：`E:\git_Projects\grid-forming-converter-stability`。
本轮回应画布难以拖动、新增元件依赖默认母线与缺少快捷键的反馈，不修改模型方程、论文基线或作者代码。

## 实现与边界

- 元件库提供母线、构网型变流器、等值电源和线路工具。采用 Pointer Events 指针捕获，不新增依赖；点击后放置作为替代入口。
- 原“＋”按钮进入待放置或接线，不再立即绑定第一条空闲母线或前两条母线。
- 电源放到已有母线上时以实际命中母线为准；被电源占用的端口拒绝放置。放到空白处则新增设备与接入母线，不自动增加线路，二者可作为同一步撤销。
- 屏幕坐标转换先关闭内部吸附，再按图元最终位置吸附一次；设备接入已有母线时保持端子对齐。
- 选择和接线模式均可从符号或名称拖动元件；平移模式及按住空格时仅改变视图。模式切换不会偷偷修改接入母线。
- 提供七项可修改的字母快捷键，设置存于本机浏览器，不写入案例。输入框保留文字编辑，按钮保留标准空格激活；既有 Ctrl+Z / Y / Shift+Z 继续处理模型与版面撤销。
- 选中元素可按 Delete/Backspace 或点击删除；母线级联删除先确认，取消不写历史，接受后可整体撤销。保留现有至少两母线、至少一个无限大母线的删除限制。

初始拖动诊断在当时生产构建的选择模式下 6/6 通过；这不能证明用户当时打开了同一版本或处于该模式，故未将反馈归咎于用户操作。当前实现减少模式限制，同时增加版本识别与源码入口说明。
实际检查到本机 5173 服务提供新版画布模块，8000 为 API，根路径返回 404。未停止或重启任何既有服务；不将此端口事实作为其他电脑的永久配置。

## 已执行测试

| 测试 | 结果 | 说明 |
|---|---|---|
| TypeScript / Vite 生产构建 | 通过 | 两个纯模块与画布接入；保留既有大分块提示 |
| `test_network_palette_operations.mjs` | 27 个场景通过 | 非有限坐标、ID 避让、显式/新建接入、默认参数、不可变输入及删除保护 |
| `test_network_editor_shortcuts.mjs` | 14 个场景通过 | 严格格式、重复键、大小写、存储版本与独立默认副本 |
| `test_network_editor_drag_targets.mjs` | 6 个真实鼠标场景通过 | 三类图元的 SVG 笔画/名称拖动、保存与真实撤销 |
| `test_network_palette_ui.mjs` | 21 个真实操作场景通过 | 元件库、指定目标、吸附、撤销、快捷键、删除与响应式界面 |
| 既有 `test_network_editor_usability.mjs` | 25 个场景通过 | 端子、并联、参数表、历史、扩大保存及手机版面回归 |
| 既有接线适用性 UI / 输入结果归属 UI | 9 / 33 个场景通过 | 未修改两组原测试脚本 |
| `verify_all.ps1` 语法 | 通过 | 新四个脚本接入入口；未运行全量入口 |

各组不合并为新增算法测试总数。浏览器使用独立随机本机端口及合成预设，只验证交互、输入和保存，不调用求解器或报告 API；脚本保留 60 秒上限并关闭测试服务与浏览器。

21 个新 UI 场景检查了真实指针拖入、点击放置、显式目标与占用拒绝、缩放后的落点、设备与新母线原子撤销、旧加号等待放置、线路指定两端、图元移动与平移分离、空格待放置保护、按钮空格激活、键盘放置/取消、独立删除及关联删除确认、改键保存重载、冲突拒绝、原生文字输入、恢复默认、1440px/390px 保存和页面宽度。

### 排查过程

真实测试揭示并修复了双重吸附：库默认吸附转换后的中心，应用再次吸附左上角，导致落点偏移。改为转换时不吸附，仅保留最终位置吸附，原坐标断言未放宽。
独立复核补了临时平移仍会新增元件、按钮空格激活被拦截两处问题，并以实际键盘操作验证。
测试脚本曾因保存造成页面滚动后未滚回画布而找不到空白点；修正为真实滚到画布、限制可见区域并用实际命中检测确认空白，不改变案例或放宽位置标准。

## 截图和交付范围

- [桌面复杂编辑案例](../../output/ui-review/network-editor-20261007/network-palette-ui-1440.png)
- [手机复杂编辑案例](../../output/ui-review/network-editor-20261007/network-palette-ui-390.png)
- [桌面基础接线与新元件库](../../output/ui-review/network-palette-20261007/network-editor-usability-1440.png)
- [手机基础接线与新元件库](../../output/ui-review/network-palette-20261007/network-editor-usability-390.png)

复杂编辑截图已实际查看，无页面级横向溢出；其测试案例包含未接线的独立设备区域，低频模型提示不适用是预期结果，不是已完成计算的工程案例。基础接线截图由最终构建的既有25场景回归生成并回看，便于看清库与图形；同样不作为数值分析证据。
最终构建上，主代理又独立复跑21个新场景与25个既有场景，退出码均为0；同一测试的复跑不重复累计。
旧失败截图只保留排查过程，不作为成功证据。

没有引入新设备数学模型、潮流或短路算法，没有运行 MATLAB/Simulink、异机试验、打包、提交或推送。旧便携包不包含新增元件库。
操作说明见 [网络接线编辑](../../docs/software/NETWORK_EDITOR.md)。本轮属于软件交互与可靠性改进，不声称新增稳定性理论或原论文未提出的研究结果。

## 重跑

在既有 Node/浏览器依赖环境下，先运行 `npm.cmd run build --prefix apps/web`，再从项目根目录执行：

```powershell
node scripts/test_network_palette_operations.mjs
node scripts/test_network_editor_shortcuts.mjs
node scripts/test_network_editor_drag_targets.mjs
$env:GFM_UI_REVIEW_DIR='output/ui-review/network-editor-20261007'
node scripts/test_network_palette_ui.mjs
```

拖放实现依据：[React Flow 官方 Pointer Events 示例](https://reactflow.dev/examples/interaction/drag-and-drop)。键盘行为依据：[React Flow 可访问性说明](https://reactflow.dev/learn/advanced-use/accessibility)。未复制付费模板或添加外部代码快照。
