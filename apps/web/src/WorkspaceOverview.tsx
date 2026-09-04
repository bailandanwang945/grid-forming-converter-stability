import {
  ArrowRight,
  BookOpenCheck,
  Grid3X3,
  Network,
  ShieldCheck,
  SlidersHorizontal,
} from 'lucide-react'

export type AnalysisWorkspace = 'paper' | 'comparison' | 'model' | 'average-dq'

interface WorkspaceOverviewProps {
  onNavigate: (workspace: AnalysisWorkspace) => void
}

const workflows = [
  {
    id: 'paper' as const,
    number: '01',
    role: '论文复现',
    title: '核查分散式稳定判据',
    description: '复算论文图 8 的增益条件与相位条件，并与闭环特征根相互印证。',
    scope: '算例：论文图 8',
    action: '开始核查',
    icon: BookOpenCheck,
  },
  {
    id: 'comparison' as const,
    number: '02',
    role: '参数分析',
    title: '比较判据覆盖范围',
    description: '在同一 D–SCR 参数平面内，对照充分判据与闭环特征根的分类结果。',
    scope: '范围：预设 D–SCR 参数网格',
    action: '查看参数域',
    icon: Grid3X3,
  },
  {
    id: 'model' as const,
    number: '03',
    role: '网络建模',
    title: '建立网络模型并分析低频模态',
    description: '连接母线、线路、构网型变流器与等值电源，校核拓扑后考察阻尼和网络强度对低频动态的影响。',
    scope: '模型：小型低频网络',
    action: '开始建模',
    icon: Network,
  },
  {
    id: 'average-dq' as const,
    number: '04',
    role: '控制分析',
    title: '分析变流器与控制参数',
    description: '计算 VSM、双 PI 控制器及 LCL 滤波器模型的极点、响应与端口导纳。',
    scope: '模型：单机 16 状态平均值 dq 模型',
    action: '设置设备参数',
    icon: SlidersHorizontal,
  },
]

export default function WorkspaceOverview({ onNavigate }: WorkspaceOverviewProps) {
  return <main className="overview-main" data-testid="workspace-overview">
    <section className="overview-hero">
      <div>
        <small>构网型变流器稳定性分析</small>
        <h2>选择分析任务</h2>
        <p>从论文算例、参数域、网络模型或变流器模型开始分析。</p>
        <div className="audience-chips" aria-label="目标用户">
          <span><ShieldCheck size={14}/>稳定性核查</span>
          <span><Network size={14}/>系统规划</span>
          <span><SlidersHorizontal size={14}/>控制设计</span>
        </div>
      </div>
      <ol className="workflow-sequence" aria-label="分析流程">
        <li><span>1</span><div><b>选择模型</b><small>确认对象与假设</small></div></li>
        <li><span>2</span><div><b>运行分析</b><small>计算判据、极点或响应</small></div></li>
        <li><span>3</span><div><b>核对结果</b><small>查看依据并导出报告</small></div></li>
      </ol>
    </section>

    <div className="overview-section-title">
      <div><small>四类任务</small><h3>从哪里开始？</h3></div>
      <p>各工作区采用不同模型，计算结果不可直接互换。</p>
    </div>
    <section className="workflow-grid">
      {workflows.map(workflow => {
        const Icon = workflow.icon
        return <article key={workflow.id} className="workflow-card">
          <div className="workflow-card-heading"><span>{workflow.number}</span><em>{workflow.role}</em><Icon size={18}/></div>
          <h3>{workflow.title}</h3>
          <p>{workflow.description}</p>
          <small>{workflow.scope}</small>
          <button onClick={() => onNavigate(workflow.id)}>{workflow.action}<ArrowRight size={15}/></button>
        </article>
      })}
    </section>

    <aside className="overview-boundary">
      <ShieldCheck size={18}/>
      <div><b>适用范围</b><p>本软件用于研究与教学，不作并网认证。判据未覆盖，只表示该充分条件不能确认稳定。</p></div>
    </aside>
  </main>
}
