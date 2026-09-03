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
    role: '稳定性核查',
    title: '复核分散式稳定判据',
    description: '从版本固定的论文算例重新计算增益、相位与未覆盖频带，核对判据与闭环参考结果。',
    scope: '当前能力：作者 Fig. 8 固定算例',
    action: '进入判据核查',
    icon: BookOpenCheck,
  },
  {
    id: 'comparison' as const,
    number: '02',
    role: '稳定性核查',
    title: '评估参数域与判据保守性',
    description: '在同一模型和参数域内比较充分判据覆盖区、闭环特征根参考稳定区与数值待定点。',
    scope: '当前能力：冻结 D–SCR 参数网格',
    action: '进入参数域评估',
    icon: Grid3X3,
  },
  {
    id: 'model' as const,
    number: '03',
    role: '系统规划与分析',
    title: '建立网络并筛查低频模态',
    description: '编辑母线、线路、VSM与无限大电网，观察阻尼和网络强度对相角—频率动态的影响。',
    scope: '当前能力：小型低频网络模型',
    action: '进入网络分析',
    icon: Network,
  },
  {
    id: 'average-dq' as const,
    number: '04',
    role: '变流器控制设计',
    title: '研究设备模型与控制参数',
    description: '分析VSM外环、双PI内环、LCL滤波器和线路的闭环极点、响应、导纳及模型层级差异。',
    scope: '当前能力：单机16状态平均值 dq 模型',
    action: '进入设备与控制',
    icon: SlidersHorizontal,
  },
]

export default function WorkspaceOverview({ onNavigate }: WorkspaceOverviewProps) {
  return <main className="overview-main" data-testid="workspace-overview">
    <section className="overview-hero">
      <div>
        <small>DECENTRALIZED STABILITY WORKBENCH</small>
        <h2>从设备级模型到系统级稳定性证据</h2>
        <p>面向稳定性核查人员、系统规划人员与变流器控制设计人员，组织模型输入、充分判据、闭环参考和交叉核查结果。</p>
        <div className="audience-chips" aria-label="目标用户">
          <span><ShieldCheck size={14}/>稳定性核查</span>
          <span><Network size={14}/>系统规划</span>
          <span><SlidersHorizontal size={14}/>控制设计</span>
        </div>
      </div>
      <ol className="workflow-sequence" aria-label="分析流程">
        <li><span>1</span><div><b>选择任务与模型</b><small>明确研究层级和适用假设</small></div></li>
        <li><span>2</span><div><b>计算并核查</b><small>判据、极点、响应与参数域</small></div></li>
        <li><span>3</span><div><b>解释并导出</b><small>结论与证据边界同步保存</small></div></li>
      </ol>
    </section>

    <div className="overview-section-title">
      <div><small>ANALYSIS TASKS</small><h3>选择要完成的稳定性任务</h3></div>
      <p>每个工作区对应不同模型和证据等级，结果不可跨模型直接外推。</p>
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
      <div><b>当前是可复现研究工作台，不是正式并网认证系统</b><p>尚不支持任意厂商黑箱阻抗或频率响应数据导入，也不生成工程合格证明；判据未覆盖不等于系统失稳。</p></div>
    </aside>
  </main>
}
