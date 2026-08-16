# 科研软件前端参照与本项目取舍

日期：2026-08-16

## 结论

本项目不再把传统实验室桌面软件或通用企业设计系统作为主要视觉模板。当前采用“现代科研画布”路线：以 AutoFigure-Edit 的公开网页界面为主视觉参照，以 NHERI SimCenter 的任务分区思想约束工作流，以 DeepScientist 的简洁顶部导航控制品牌层；不使用水墨山景，也不复制任何项目标志、插画或业务内容。

## 官方参照

| 项目 | 团队与来源 | 可借鉴部分 | 不直接采用部分 |
|---|---|---|---|
| AutoFigure-Edit | ResearAI，[GitHub](https://github.com/ResearAI/AutoFigure-Edit)，MIT | 40 px 细网格、米灰—薄荷背景、圆角白卡、黑色任务按钮、浮动工具区、主次操作层级 | 品牌标志、生成式绘图业务、SVG 编辑器布局 |
| DeepScientist | ResearAI，[官网](https://deepscientist.cc/) | 简洁顶部导航、短标签、克制的标题与按钮密度 | 水彩山景、落地页式大标题，不适合高密度参数工作区 |
| quoFEM | NHERI SimCenter，[用户界面文档](https://nheri-simcenter.github.io/quoFEM-Documentation/common/user_manual/usage/desktop/usage.html) | 左侧任务选择、中央输入面板、运行与结果分离、后台状态可见 | 传统桌面控件外观和底部按钮条 |
| OpenMDAO N2 | OpenMDAO，[官方文档](https://openmdao.org/newdocs/versions/latest/features/model_visualization/n2_basics/n2_basics.html) | 将模型结构可视化作为独立证据视图 | N2 矩阵交互不适合直接替代本项目网络拓扑与频域图表 |

## 已实施的信息架构

平均值 dq 工作区按“输入—研究任务—当前结果—证据视图”组织：

1. 左栏仅保留12项可编辑参数、主分析按钮和模型参数保存；
2. 42点 D–X 层级对照、固定19点模态消融、四条单因素临界边界分别形成三张任务卡；
3. 当前结果 JSON 与分析报告进入随结果启用的黑色工具条；
4. 网络拓扑、极点、响应、导纳与研究表格继续使用原有可追溯数据，不因视觉重构改变计算路径。

在1080 px视口下，参数栏为320 px，工作区为692 px，间距24 px；三个研究任务卡各约223 px，页面无横向溢出。900 px以下工作区改为单列，620 px及以下研究任务卡也改为单列。

## 借鉴边界

- AutoFigure-Edit 的视觉令牌来源于其公开 MIT 许可源码；本项目没有复制其图片、Logo、文案或业务组件。
- DeepScientist 仅作为布局参照，不采用其水彩素材。
- 外观一致性不构成科研证据；模型、单位、端口方向、数值验证和结论边界仍以本项目后端、测试与结果文件为准。
