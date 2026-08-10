import { useMemo, useState } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { LineChart, ScatterChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  Activity,
  BookOpenCheck,
  CircleCheck,
  Download,
  Gauge,
  Network,
  Play,
  ShieldAlert,
  SlidersHorizontal,
} from 'lucide-react'
import { AnalysisResult, Fig8ScenarioId, runAnalysis } from './api'
import ReducedOrderWorkbench from './ReducedOrderWorkbench'
import ParameterDomainComparison from './ParameterDomainComparison'

echarts.use([
  LineChart,
  ScatterChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
])

const scenarios: Array<{ id: Fig8ScenarioId; label: string; damping: number }> = [
  { id: 'fig8_D_0p05', label: 'Fig. 8 低阻尼失稳工况', damping: 0.05 },
  { id: 'fig8_D_0p5', label: 'Fig. 8 高阻尼稳定工况', damping: 0.5 },
]

const markZero = {
  silent: true,
  symbol: 'none',
  lineStyle: { color: '#c54b4b', type: 'dashed' },
  data: [{ yAxis: 0, name: '判定边界' }],
}

function App() {
  const [workspaceMode, setWorkspaceMode] = useState<'paper' | 'comparison' | 'model'>('paper')
  const [scenarioId, setScenarioId] = useState<Fig8ScenarioId>('fig8_D_0p5')
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const selectedScenario = scenarios.find(value => value.id === scenarioId) ?? scenarios[1]
  const stable = result?.summary.closed_loop_reference === 'stable'

  const gainChart = useMemo(() => {
    if (!result) return {}
    const scan = result.frequency_scan
    const uncovered = scan.frequencies_hz
      .map((frequency, index) => scan.coverage[index] === 'uncovered' ? [frequency, 0] : null)
      .filter(Boolean)
    return {
      animationDuration: 450,
      grid: { left: 64, right: 24, top: 38, bottom: 52 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'log', name: '频率 / Hz', nameLocation: 'middle', nameGap: 32 },
      yAxis: { type: 'value', name: '增益裕度' },
      series: [
        {
          name: 'σmin(Ynet) − σmax(Yc)', type: 'line', symbol: 'none',
          lineStyle: { width: 2.2, color: '#167d70' },
          data: scan.frequencies_hz.map((frequency, index) => [frequency, scan.gain_margin[index]]),
          markLine: markZero,
        },
        {
          name: '增益与相位均未覆盖', type: 'scatter', symbolSize: 5,
          itemStyle: { color: '#c94747' }, data: uncovered,
        },
      ],
    }
  }, [result])

  const phaseChart = useMemo(() => {
    if (!result) return {}
    const scan = result.frequency_scan
    return {
      animationDuration: 450,
      grid: { left: 64, right: 24, top: 38, bottom: 52 },
      tooltip: { trigger: 'axis' },
      legend: { top: 4, right: 8, textStyle: { fontSize: 10 } },
      xAxis: { type: 'log', name: '频率 / Hz', nameLocation: 'middle', nameGap: 32 },
      yAxis: { type: 'value', name: '相位裕度 / rad' },
      series: [
        {
          name: '上相位裕度', type: 'line', symbol: 'none', connectNulls: false,
          lineStyle: { width: 2, color: '#3c6fa3' },
          data: scan.frequencies_hz.map((frequency, index) => [frequency, scan.upper_phase_margin[index]]),
          markLine: markZero,
        },
        {
          name: '下相位裕度', type: 'line', symbol: 'none', connectNulls: false,
          lineStyle: { width: 2, color: '#b77824' },
          data: scan.frequencies_hz.map((frequency, index) => [frequency, scan.lower_phase_margin[index]]),
        },
      ],
    }
  }, [result])

  async function analyze() {
    setRunning(true)
    setError('')
    try {
      setResult(await runAnalysis(scenarioId))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '分析失败')
    } finally {
      setRunning(false)
    }
  }

  function exportJson() {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${result.run_id}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  function openPrintableReport() {
    window.open(`/api/reports/fig8?scenario_id=${scenarioId}`, '_blank', 'noopener,noreferrer')
  }

  return <div className="app-shell">
    <header>
      <div className="brand-mark"><Activity size={22}/></div>
      <div><h1>构网型变流器稳定性分析平台</h1><p>拓扑建模 · 分散式充分判据 · 闭环参考验证</p></div>
      <nav className="workspace-tabs" aria-label="工作台切换">
        <button className={workspaceMode === 'paper' ? 'active' : ''} onClick={() => setWorkspaceMode('paper')}>论文复现</button>
        <button className={workspaceMode === 'comparison' ? 'active' : ''} onClick={() => setWorkspaceMode('comparison')}>同域对照</button>
        <button className={workspaceMode === 'model' ? 'active' : ''} onClick={() => setWorkspaceMode('model')}>独立模型</button>
      </nav>
      <span className="research-tag">双内核工作台 v0.3</span>
    </header>
    {workspaceMode === 'model' ? <ReducedOrderWorkbench/> : workspaceMode === 'comparison' ? <ParameterDomainComparison/> : <main>
      <aside className="panel controls">
        <div className="panel-title"><SlidersHorizontal size={18}/><span>论文基线算例</span></div>
        <label>分析场景
          <select value={scenarioId} onChange={event => setScenarioId(event.target.value as Fig8ScenarioId)}>
            {scenarios.map(value => <option key={value.id} value={value.id}>{value.label}</option>)}
          </select>
        </label>
        <div className="case-description">
          <span>唯一变化参数</span><strong>VSM 阻尼 D = {selectedScenario.damping.toFixed(2)}</strong>
          <p>两组响应均来自同一作者 Fig. 8 工作簿的固定夹具，不在端点之间插值。</p>
        </div>
        <div className="parameter-grid">
          <div><small>频率范围</small><strong>0.001–10⁴ Hz</strong></div>
          <div><small>离散点数</small><strong>{result?.summary.frequency_points ?? 1000}</strong></div>
        </div>
        <button onClick={analyze} disabled={running}>
          <Play size={17} fill="currentColor"/>{running ? '正在重算 1000 个频点…' : '运行稳定性分析'}
        </button>
        <button className="secondary-button" onClick={exportJson} disabled={!result}>
          <Download size={16}/>导出可追溯 JSON
        </button>
        <button className="secondary-button" onClick={openPrintableReport} disabled={!result}>
          <BookOpenCheck size={16}/>生成打印式分析报告
        </button>
        {error && <p className="error">{error}：请确认后端已启动。</p>}
        <p className="scope-note">
          当前结果由 Python 便携内核从作者频响夹具重新计算。有限频率网格不等同于论文全频定理；判据未覆盖也不等于系统必然失稳。
        </p>
      </aside>

      <section className="workspace">
        <div className="panel topology-card">
          <div className="panel-title"><Network size={18}/><span>单机构网型变流器—无限大母线</span><em>作者 Fig. 8 固定拓扑</em></div>
          <div className="topology">
            <div className="node converter"><span className="node-icon">GFM</span><b>构网型变流器</b><small>VSM · D={selectedScenario.damping.toFixed(2)}</small></div>
            <div className="line"><span>并网阻抗</span></div>
            <div className="node bus"><span className="node-icon">PCC</span><b>公共连接点</b><small>纯电阻负荷</small></div>
            <div className="line"></div>
            <div className="node grid"><span className="node-icon">∞</span><b>无限大电网</b><small>50 Hz</small></div>
          </div>
        </div>

        {result ? <>
          <div className="metrics four">
            <article className={stable ? 'metric good' : 'metric bad'}>
              {stable ? <CircleCheck/> : <ShieldAlert/>}
              <div><small>闭环特征根参考</small><strong>{stable ? '参考稳定' : '参考失稳'}</strong><p>实部 {result.summary.dominant_pole_hz.real.toFixed(6)} Hz</p></div>
            </article>
            <article className={result.summary.uncovered_points ? 'metric warn' : 'metric good'}>
              <Gauge/><div><small>有限网格充分判据</small><strong>{result.summary.uncovered_points ? `${result.summary.uncovered_points} 个未覆盖点` : '1000 点均有条件覆盖'}</strong><p>定理状态：未由采样接口评价</p></div>
            </article>
            <article className="metric neutral">
              <Activity/><div><small>工作簿主导振荡模态</small><strong>{result.summary.reproduced_dominant_oscillation_hz.toFixed(6)} Hz</strong><p>由闭环极点虚部得到</p></div>
            </article>
            <article className="metric warn">
              <BookOpenCheck/><div><small>论文正文报告</small><strong>{result.summary.paper_reported_oscillation_hz.toFixed(1)} Hz</strong><p>与工作簿结果的差异尚未闭合</p></div>
            </article>
          </div>

          <div className="panel evidence-strip">
            <div><small>增益筛查</small><b>{result.summary.screening_counts.gain.pass} 通过 / {result.summary.screening_counts.gain.fail} 未通过 / {result.summary.screening_counts.gain.indeterminate} 待定</b></div>
            <div><small>相位筛查</small><b>{result.summary.screening_counts.phase.pass} 通过 / {result.summary.screening_counts.phase.fail} 未通过 / {result.summary.screening_counts.phase.indeterminate} 待定</b></div>
            <div><small>相位分支锚点</small><b>{result.phase_seed.converter_frequency_hz.toPrecision(7)} Hz</b></div>
          </div>

          <div className="chart-grid">
            <div className="panel chart-card"><div className="panel-title"><Gauge size={18}/><span>小增益条件裕度</span><em>正值表示该频点由小增益条件覆盖</em></div><ReactEChartsCore echarts={echarts} option={gainChart} style={{height: 320}}/></div>
            <div className="panel chart-card"><div className="panel-title"><Activity size={18}/><span>严格扇形相位裕度</span><em>空段表示相位不可用或数值待定</em></div><ReactEChartsCore echarts={echarts} option={phaseChart} style={{height: 320}}/></div>
          </div>

          <div className="panel provenance-card">
            <div className="panel-title"><BookOpenCheck size={18}/><span>结果来源与解释边界</span></div>
            <p>{result.provenance.interpretation}</p>
            <dl>
              <div><dt>作者代码</dt><dd>{result.provenance.author_tag} · {result.provenance.author_commit.slice(0, 10)}</dd></div>
              <div><dt>固定夹具</dt><dd>{result.provenance.fixture_id}</dd></div>
              <div><dt>计算方法</dt><dd>{result.provenance.python_method}</dd></div>
              <div><dt>原工作簿 SHA-256</dt><dd>{result.provenance.source_workbook_sha256.slice(0, 16)}…</dd></div>
            </dl>
          </div>
        </> : <div className="panel empty-state"><Activity size={34}/><h2>选择工况并运行分析</h2><p>平台将从固定复矩阵夹具重新计算 1000 个频率点，而不是读取预制结论或绘制人工曲线。</p></div>}
      </section>
    </main>}
  </div>
}

export default App
