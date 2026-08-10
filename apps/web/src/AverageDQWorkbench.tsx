import { useEffect, useMemo, useState } from 'react'
import * as echarts from 'echarts/core'
import { LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Activity, BookOpenCheck, CircleCheck, Download, Gauge, Play, ShieldAlert, SlidersHorizontal } from 'lucide-react'
import {
  AverageDQParameters,
  AverageDQResult,
  NetworkTopology,
  getAverageDQPreset,
  getAverageDQReportHtml,
  runAverageDQAnalysis,
} from './api'
import EChart from './EChart'

echarts.use([LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, CanvasRenderer])

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))

function download(filename: string, content: string, type = 'application/json') {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function logarithmicFrequencies() {
  return Array.from({ length: 31 }, (_, index) => 10 ** (-1 + index * 3 / 30))
}

export default function AverageDQWorkbench() {
  const [topology, setTopology] = useState<NetworkTopology | null>(null)
  const [parameters, setParameters] = useState<AverageDQParameters | null>(null)
  const [result, setResult] = useState<AverageDQResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [simulationTime, setSimulationTime] = useState(2)
  const [timeStep, setTimeStep] = useState(0.002)
  const [initialAngleMrad, setInitialAngleMrad] = useState(0.1)

  useEffect(() => {
    getAverageDQPreset()
      .then(preset => {
        setTopology(clone(preset.topology))
        setParameters(clone(preset.parameters))
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '无法读取平均值模型预设'))
  }, [])

  const analysisInput = useMemo(() => topology && parameters ? {
    topology,
    parameters,
    simulation_time_s: simulationTime,
    time_step_s: timeStep,
    initial_angle_perturbation_rad: initialAngleMrad / 1000,
    frequency_values_hz: logarithmicFrequencies(),
  } : null, [topology, parameters, simulationTime, timeStep, initialAngleMrad])

  const poleChart = useMemo(() => result ? {
    animationDuration: 350,
    grid: { left: 66, right: 25, top: 28, bottom: 52 },
    tooltip: { trigger: 'item', formatter: (value: { data: number[] }) => `实部 ${value.data[0].toFixed(5)} Hz<br/>虚部 ${value.data[1].toFixed(5)} Hz` },
    xAxis: { type: 'value', name: '实部 / Hz', nameLocation: 'middle', nameGap: 32 },
    yAxis: { type: 'value', name: '虚部 / Hz' },
    series: [{
      type: 'scatter', symbolSize: 9, itemStyle: { color: '#176e64' },
      data: result.result.poles.map(pole => [pole.real_hz, pole.imag_hz]),
      markLine: { silent: true, symbol: 'none', lineStyle: { color: '#c54b4b', type: 'dashed' }, data: [{ xAxis: 0 }] },
    }],
  } : {}, [result])

  const responseChart = useMemo(() => {
    if (!result) return {}
    const response = result.result.time_response
    return {
      animationDuration: 350,
      grid: { left: 66, right: 25, top: 34, bottom: 52 },
      tooltip: { trigger: 'axis' },
      legend: { top: 2 },
      xAxis: { type: 'value', name: '时间 / s', nameLocation: 'middle', nameGap: 32 },
      yAxis: { type: 'value', name: '相角偏差 / mrad' },
      series: [
        { name: '非线性平均值模型', type: 'line', symbol: 'none', lineStyle: { width: 2.2, color: '#176e64' }, data: response.time_s.map((time, index) => [time, (response.nonlinear_states[index][0] - result.operating_point.state[0]) * 1000]) },
        { name: '局部线性模型', type: 'line', symbol: 'none', lineStyle: { width: 1.6, color: '#b77824', type: 'dashed' }, data: response.time_s.map((time, index) => [time, (response.linear_states[index][0] - result.operating_point.state[0]) * 1000]) },
      ],
    }
  }, [result])

  const admittanceChart = useMemo(() => {
    if (!result) return {}
    const port = result.result.port_admittance
    const magnitude = port.matrices.map(matrix => Math.sqrt(matrix.flat().reduce((sum, value) => sum + value.real ** 2 + value.imag ** 2, 0)))
    return {
      animationDuration: 350,
      grid: { left: 66, right: 25, top: 28, bottom: 52 },
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'log', name: '频率 / Hz', nameLocation: 'middle', nameGap: 32 },
      yAxis: { type: 'log', name: '||Ydev||F' },
      series: [{ type: 'line', symbol: 'none', lineStyle: { width: 2.2, color: '#3c6fa3' }, data: port.frequencies_hz.map((frequency, index) => [frequency, magnitude[index]]) }],
    }
  }, [result])

  function updateConverter(field: string, value: number) {
    if (!topology) return
    const next = clone(topology)
    ;(next.grid_forming_converters[0] as unknown as Record<string, number>)[field] = value
    setTopology(next)
    setResult(null)
  }

  function updateLine(field: 'resistance_pu' | 'reactance_pu', value: number) {
    if (!topology) return
    const next = clone(topology)
    next.lines[0][field] = value
    setTopology(next)
    setResult(null)
  }

  function updateParameter(field: keyof AverageDQParameters, value: number) {
    if (!parameters) return
    setParameters({ ...parameters, [field]: value })
    setResult(null)
  }

  async function analyze() {
    if (!analysisInput) return
    setRunning(true)
    setError('')
    try {
      setResult(await runAverageDQAnalysis(analysisInput))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '平均值 dq 分析失败')
    } finally {
      setRunning(false)
    }
  }

  async function openReport() {
    if (!analysisInput) return
    const reportWindow = window.open('', '_blank')
    try {
      const html = await getAverageDQReportHtml(analysisInput)
      if (reportWindow) {
        reportWindow.document.open()
        reportWindow.document.write(html)
        reportWindow.document.close()
      } else download('average-dq-analysis-report.html', html, 'text/html')
    } catch (reason) {
      reportWindow?.close()
      setError(reason instanceof Error ? reason.message : '报告生成失败')
    }
  }

  if (!topology || !parameters) return <main><div className="panel empty-state"><Activity size={34}/><h2>正在载入平均值模型</h2>{error && <p className="error">{error}</p>}</div></main>
  const converter = topology.grid_forming_converters[0]
  const line = topology.lines[0]
  const stable = result?.result.stability === 'stable'
  const maximumResidual = result ? Math.max(
    ...result.operating_point.algebraic_residual.map(Math.abs),
    result.operating_point.closed_rhs_residual_inf,
  ) : null

  return <main>
    <aside className="panel controls">
      <div className="panel-title"><SlidersHorizontal size={18}/><span>平均值 dq 参数</span></div>
      <p className="scope-note">首版固定为单台 VSM、LCL 滤波器、单条外部 RL 线路和无限大母线。这里修改的是实际计算参数，不是显示层滑杆。</p>
      <div className="parameter-grid">
        <label>P* / p.u.<input type="number" step="0.05" value={converter.active_power_setpoint_pu} onChange={event => updateConverter('active_power_setpoint_pu', Number(event.target.value))}/></label>
        <label>Q* / p.u.<input type="number" step="0.05" value={converter.reactive_power_setpoint_pu} onChange={event => updateConverter('reactive_power_setpoint_pu', Number(event.target.value))}/></label>
        <label>V* / p.u.<input type="number" step="0.01" value={converter.voltage_setpoint_pu} onChange={event => updateConverter('voltage_setpoint_pu', Number(event.target.value))}/></label>
        <label>阻尼 D<input type="number" step="1" value={converter.damping_coefficient_pu} onChange={event => updateConverter('damping_coefficient_pu', Number(event.target.value))}/></label>
        <label>线路 R / p.u.<input type="number" step="0.01" value={line.resistance_pu} onChange={event => updateLine('resistance_pu', Number(event.target.value))}/></label>
        <label>线路 X / p.u.<input type="number" step="0.05" value={line.reactance_pu} onChange={event => updateLine('reactance_pu', Number(event.target.value))}/></label>
        <label>滤波器 X1<input type="number" step="0.01" value={parameters.converter_side_reactance_pu} onChange={event => updateParameter('converter_side_reactance_pu', Number(event.target.value))}/></label>
        <label>滤波器 Bc<input type="number" step="0.01" value={parameters.filter_capacitor_susceptance_pu} onChange={event => updateParameter('filter_capacitor_susceptance_pu', Number(event.target.value))}/></label>
        <label>滤波器 X2<input type="number" step="0.01" value={parameters.grid_side_reactance_pu} onChange={event => updateParameter('grid_side_reactance_pu', Number(event.target.value))}/></label>
        <label>Q–V 下垂 nq<input type="number" step="0.01" value={parameters.reactive_power_voltage_droop_pu} onChange={event => updateParameter('reactive_power_voltage_droop_pu', Number(event.target.value))}/></label>
        <label>仿真时长 / s<input type="number" step="0.2" value={simulationTime} onChange={event => { setSimulationTime(Number(event.target.value)); setResult(null) }}/></label>
        <label>初始相角 / mrad<input type="number" step="0.05" value={initialAngleMrad} onChange={event => { setInitialAngleMrad(Number(event.target.value)); setResult(null) }}/></label>
      </div>
      <button onClick={analyze} disabled={running}><Play size={17} fill="currentColor"/>{running ? '正在求工作点并积分…' : '运行平均值 dq 分析'}</button>
      <button className="secondary-button" disabled={!result} onClick={() => result && download(`${result.run_id}.json`, JSON.stringify(result, null, 2))}><Download size={16}/>导出可追溯 JSON</button>
      <button className="secondary-button" disabled={!result} onClick={openReport}><BookOpenCheck size={16}/>生成打印式分析报告</button>
      <button className="secondary-button" onClick={() => download('average-dq-case.json', JSON.stringify({ topology, parameters }, null, 2))}><Download size={16}/>保存模型参数</button>
      {error && <p className="error">{error}</p>}
    </aside>

    <section className="workspace">
      <div className="panel topology-card">
        <div className="panel-title"><Activity size={18}/><span>16 状态平均值 dq 模型</span><em>团队自建校核模型，不是论文 Fig. 8</em></div>
        <div className="topology">
          <div className="node converter"><span className="node-icon">VSM</span><b>平均调制 + 双闭环</b><small>L1–C–L2 滤波器</small></div>
          <div className="line"><span>PCC</span></div>
          <div className="node bus"><span className="node-icon">RL</span><b>外部并网线路</b><small>R={line.resistance_pu} · X={line.reactance_pu}</small></div>
          <div className="line"></div>
          <div className="node grid"><span className="node-icon">∞</span><b>无限大母线</b><small>{topology.base_values.frequency_hz} Hz</small></div>
        </div>
      </div>

      {result ? <>
        <div className="metrics four">
          <article className={stable ? 'metric good' : 'metric bad'}>{stable ? <CircleCheck/> : <ShieldAlert/>}<div><small>16 状态闭环极点</small><strong>{result.result.stability === 'stable' ? '参考稳定' : result.result.stability === 'marginal' ? '临界' : '参考失稳'}</strong><p>主导实部 {result.result.dominant_mode.real_hz.toFixed(6)} Hz</p></div></article>
          <article className="metric neutral"><Gauge/><div><small>主导振荡频率</small><strong>{result.result.dominant_mode.oscillation_frequency_hz.toFixed(4)} Hz</strong><p>由直接闭合矩阵得到</p></div></article>
          <article className="metric good"><CircleCheck/><div><small>工作点最大残差</small><strong>{maximumResidual?.toExponential(2)}</strong><p>含代数方程与动态方程</p></div></article>
          <article className="metric good"><CircleCheck/><div><small>端口—线路重组误差</small><strong>{result.result.port_interconnection_max_abs_error.toExponential(2)}</strong><p>独立闭环组装核对</p></div></article>
        </div>
        <div className="panel evidence-strip">
          <div><small>PCC 电流</small><b>{result.operating_point.grid_current_magnitude_pu.toFixed(5)} p.u.</b></div>
          <div><small>内部电压</small><b>{result.operating_point.internal_voltage_magnitude_pu.toFixed(5)} p.u.</b></div>
          <div><small>有功平衡残差</small><b>{result.operating_point.active_power_balance_residual_pu.toExponential(2)}</b></div>
          <div><small>三状态近似频率误差</small><b>{(result.result.quasisteady_reduction_comparison.oscillation_frequency_relative_error * 100).toFixed(2)}%</b></div>
        </div>
        <div className="chart-grid">
          <div className="panel chart-card"><div className="panel-title"><Gauge size={18}/><span>闭环极点分布</span><em>虚轴右侧为失稳</em></div><EChart option={poleChart} style={{ height: 320 }}/></div>
          <div className="panel chart-card"><div className="panel-title"><Activity size={18}/><span>非线性—线性相角响应</span><em>小扰动实现核对</em></div><EChart option={responseChart} style={{ height: 320 }}/></div>
        </div>
        <div className="panel chart-card"><div className="panel-title"><Activity size={18}/><span>变流器端口导纳范数</span><em>网络流入变流器为正 · 全局同步 dq 坐标</em></div><EChart option={admittanceChart} style={{ height: 330 }}/></div>
        <div className="panel provenance-card"><div className="panel-title"><BookOpenCheck size={18}/><span>模型身份与结论边界</span></div><p>{result.model_scope.statement}</p><p>{result.result.quasisteady_reduction_comparison.interpretation}</p><dl><div><dt>模型层级</dt><dd>正序平均值 ODE，16 个状态</dd></div><div><dt>工作点同步刚度 Kδ</dt><dd>{result.result.quasisteady_reduction_comparison.synchronizing_stiffness_pu_per_rad.toFixed(5)} p.u./rad</dd></div><div><dt>三状态近似衰减率误差</dt><dd>{(result.result.quasisteady_reduction_comparison.decay_rate_relative_error * 100).toFixed(2)}%</dd></div><div><dt>硬件参数拟合</dt><dd>未进行</dd></div></dl></div>
      </> : <div className="panel empty-state"><Activity size={34}/><h2>编辑参数后运行16状态模型</h2><p>平台会先求解工作点并检查功率平衡，再计算闭环极点、端口导纳以及非线性—线性小扰动响应。</p></div>}
    </section>
  </main>
}
