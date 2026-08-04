# 前后端 MVP

首版软件沿用零碳园区项目已经验证的“本地后端 API + 独立前端 + 后续统一打包”交付方式，
但不复用其视觉设计。

## 当前闭环

1. 前端载入论文 Fig. 8 单机无穷大系统；
2. 用户调整 VSM 阻尼与短路比；
3. `POST /api/analysis/run` 返回频率扫描和闭环参考结果；
4. 页面展示拓扑、主导极点、判据覆盖情况和频率裕度曲线。

当前后端是受控作者夹具的预览适配层，不声称已经由便携式内核完整实现论文定理。
下一步将依次接入 Python 数值内核、可编辑多节点拓扑和结果报告导出。

## 本地启动

```powershell
python -m uvicorn backend.api.app:app --reload --port 8000
cd apps/web
npm install
npm run dev
```
