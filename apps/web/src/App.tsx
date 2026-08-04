import { useMemo, useState } from 'react'
import ReactECharts from 'echarts-for-react'
import { Activity, CircleCheck, Gauge, Network, Play, ShieldAlert, SlidersHorizontal } from 'lucide-react'
import { AnalysisResult, runAnalysis } from './api'

const initialResult: AnalysisResult = {
  run_id: 'preview',
  summary: {
    closed_loop_reference: 'stable', criterion_status: 'covered-on-grid-under-phase-branch-assumption',
    dominant_pole_hz: { real: -0.289891361, imag: 0.399601028 }, critical_damping_reference: 0.07421769,
    uncovered_points: 0, frequency_points: 80, theorem_status: 'not-evaluated-by-preview-api',
  },
  frequency_scan: { frequencies_hz: [0.001, 0.01, 0.1, 1, 10, 100], mixed_margin: [0.32, 0.3, 0.22, 0.08, 0.31, 0.39], coverage: Array(6).fill('covered') },
  provenance: { mode: 'controlled-author-fixture-preview', paper_case: 'Cifelli–Anta Fig. 8', interpretation: '判据未覆盖不等于闭环必然失稳。' },
}

function App() {
  const [damping, setDamping] = useState(0.5)
  const [scr, setScr] = useState(3)
  const [result, setResult] = useState(initialResult)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const stable = result.summary.closed_loop_reference === 'stable'

  const chartOption = useMemo(() => ({
    animationDuration: 500,
    grid: { left: 56, right: 24, top: 32, bottom: 46 },
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => value.toFixed(4) },
    xAxis: { type: 'log', name: '频率 / Hz', nameLocation: 'middle', nameGap: 30, axisLine: { lineStyle: { color: '#8290a3' } } },
    yAxis: { type: 'value', name: '混合判据裕度', axisLine: { show: false }, splitLine: { lineStyle: { color: '#e9edf2' } } },
    series: [{ type: 'line', symbol: 'none', smooth: 0.2, lineStyle: { width: 3, color: '#167d70' }, areaStyle: { color: 'rgba(22,125,112,.10)' }, data: result.frequency_scan.frequencies_hz.map((f, i) => [f, result.frequency_scan.mixed_margin[i]]), markLine: { silent: true, symbol: 'none', lineStyle: { color: '#d04a4a', type: 'dashed' }, data: [{ yAxis: 0, name: '覆盖边界' }] } }],
  }), [result])

  async function analyze() {
    setRunning(true); setError('')
    try { setResult(await runAnalysis(damping, scr)) }
    catch (reason) { setError(reason instanceof Error ? reason.message : '分析失败') }
    finally { setRunning(false) }
  }

  return <div className="app-shell">
    <header><div className="brand-mark"><Activity size={22}/></div><div><h1>构网型变流器稳定性分析平台</h1><p>拓扑建模 · 分散式充分判据 · 闭环参考验证</p></div><span className="research-tag">研究原型 v0.1</span></header>
    <main>
      <aside className="panel controls">
        <div className="panel-title"><SlidersHorizontal size={18}/><span>算例与参数</span></div>
        <label>分析场景<select><option>论文 Fig. 8 单机无穷大系统</option></select></label>
        <label><span>VSM 阻尼系数 <b>{damping.toFixed(2)}</b></span><input type="range" min="0.02" max="0.8" step="0.01" value={damping} onChange={e => setDamping(+e.target.value)}/></label>
        <label><span>短路比 SCR <b>{scr.toFixed(1)}</b></span><input type="range" min="1" max="8" step="0.1" value={scr} onChange={e => setScr(+e.target.value)}/></label>
        <div className="parameter-grid"><div><small>基准频率</small><strong>50 Hz</strong></div><div><small>频率点数</small><strong>{result.summary.frequency_points}</strong></div></div>
        <button onClick={analyze} disabled={running}><Play size={17} fill="currentColor"/>{running ? '正在分析…' : '运行稳定性分析'}</button>
        {error && <p className="error">{error}：请先启动后端服务。</p>}
        <p className="scope-note">当前接口使用受控作者算例预览；MATLAB 仅用于科研核对，不是最终运行依赖。</p>
      </aside>

      <section className="workspace">
        <div className="panel topology-card"><div className="panel-title"><Network size={18}/><span>系统拓扑</span><em>可视化编辑器雏形</em></div><div className="topology">
          <div className="node converter"><span className="node-icon">GFM</span><b>构网型变流器</b><small>VSM · D={damping.toFixed(2)}</small></div><div className="line"><span>R + jX</span></div><div className="node bus"><span className="node-icon">BUS</span><b>公共连接点</b><small>SCR={scr.toFixed(1)}</small></div><div className="line"></div><div className="node grid"><span className="node-icon">∞</span><b>无限大电网</b><small>50 Hz</small></div>
        </div></div>

        <div className="metrics">
          <article className={stable ? 'metric good' : 'metric bad'}>{stable ? <CircleCheck/> : <ShieldAlert/>}<div><small>闭环特征根参考</small><strong>{stable ? '参考稳定' : '参考失稳'}</strong><p>主导极点实部 {result.summary.dominant_pole_hz.real.toFixed(4)} Hz</p></div></article>
          <article className={result.summary.uncovered_points ? 'metric warn' : 'metric good'}><Gauge/><div><small>充分判据覆盖</small><strong>{result.summary.uncovered_points ? `${result.summary.uncovered_points} 个未覆盖点` : '当前网格已覆盖'}</strong><p>不覆盖不等于系统必然失稳</p></div></article>
          <article className="metric neutral"><Activity/><div><small>参考临界阻尼</small><strong>{result.summary.critical_damping_reference.toFixed(4)}</strong><p>随网络强度联动更新</p></div></article>
        </div>

        <div className="panel chart-card"><div className="panel-title"><Activity size={18}/><span>频率域混合判据裕度</span><em>{result.provenance.paper_case}</em></div><ReactECharts option={chartOption} style={{height: 330}}/></div>
      </section>
    </main>
  </div>
}

export default App
