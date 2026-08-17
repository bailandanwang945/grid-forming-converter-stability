import { useEffect, useMemo, useState } from 'react'
import * as echarts from 'echarts/core'
import { HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Activity, BookOpenCheck, CircleCheck, Download, Gauge, Play, ShieldAlert, SlidersHorizontal } from 'lucide-react'
import {
  AverageDQAblationResult,
  AverageDQBoundaryResult,
  AverageDQParameters,
  AverageDQPortIdentificationResult,
  AverageDQResult,
  AverageDQScanResult,
  MathWorksExternalEvidenceResult,
  MathWorksTeamComparisonResult,
  NetworkTopology,
  getAverageDQPreset,
  getMathWorksExternalEvidence,
  getMathWorksTeamComparison,
  getAverageDQPortIdentificationReportHtml,
  getAverageDQReportHtml,
  runAverageDQAblation,
  runAverageDQBoundary,
  runAverageDQPortIdentification,
  runAverageDQAnalysis,
  runAverageDQScan,
} from './api'
import EChart from './EChart'

echarts.use([HeatmapChart, LineChart, ScatterChart, GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))

function download(filename: string, content: string, type = 'application/json') {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    anchor.remove()
    URL.revokeObjectURL(url)
  }, 5000)
}

function logarithmicFrequencies() {
  return Array.from({ length: 31 }, (_, index) => 10 ** (-1 + index * 3 / 30))
}

const stateNames: Record<string, string> = {
  delta_rad: '相角 δ',
  frequency_deviation_pu: '频率偏差',
  measured_active_power_pu: '有功测量',
  measured_reactive_power_pu: '无功测量',
  converter_current_d_pu: '变流器侧电流 d',
  converter_current_q_pu: '变流器侧电流 q',
  internal_voltage_d_pu: '内部电压 d',
  internal_voltage_q_pu: '内部电压 q',
  voltage_integrator_d_pu: '电压积分 d',
  voltage_integrator_q_pu: '电压积分 q',
  current_integrator_d_pu: '电流积分 d',
  current_integrator_q_pu: '电流积分 q',
}

const ablationFactorNames: Record<string, string> = {
  voltage_pi: '电压 PI',
  current_pi: '电流 PI',
  modulator_time: '调制器时间常数',
  converter_side_reactance: '变流器侧电抗',
  filter_capacitor: '滤波电容',
  grid_side_reactance: '电网侧电抗',
  qv_droop: 'Q–V 下垂',
}

function formatAblationFactors(factors: Record<string, number>) {
  const entries = Object.entries(factors)
  if (entries.length === 0) return '基准'
  return entries.map(([name, scale]) => `${ablationFactorNames[name] ?? name} × ${scale}`).join('；')
}

function leadingParticipationGroup(groups: Record<string, number>) {
  const leading = Object.entries(groups).sort((left, right) => right[1] - left[1])[0]
  return leading ? `${leading[0]}（${(leading[1] * 100).toFixed(1)}%）` : '—'
}

export default function AverageDQWorkbench() {
  const [topology, setTopology] = useState<NetworkTopology | null>(null)
  const [parameters, setParameters] = useState<AverageDQParameters | null>(null)
  const [result, setResult] = useState<AverageDQResult | null>(null)
  const [scanResult, setScanResult] = useState<AverageDQScanResult | null>(null)
  const [ablationResult, setAblationResult] = useState<AverageDQAblationResult | null>(null)
  const [boundaryResult, setBoundaryResult] = useState<AverageDQBoundaryResult | null>(null)
  const [portIdentificationResult, setPortIdentificationResult] = useState<AverageDQPortIdentificationResult | null>(null)
  const [externalEvidence, setExternalEvidence] = useState<MathWorksExternalEvidenceResult | null>(null)
  const [crossModelComparison, setCrossModelComparison] = useState<MathWorksTeamComparisonResult | null>(null)
  const [running, setRunning] = useState(false)
  const [scanRunning, setScanRunning] = useState(false)
  const [ablationRunning, setAblationRunning] = useState(false)
  const [boundaryRunning, setBoundaryRunning] = useState(false)
  const [portIdentificationRunning, setPortIdentificationRunning] = useState(false)
  const [externalEvidenceRunning, setExternalEvidenceRunning] = useState(false)
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
      type: 'scatter', symbolSize: 9, itemStyle: { color: '#667d7d' },
      data: result.result.poles.map(pole => [pole.real_hz, pole.imag_hz]),
      markLine: { silent: true, symbol: 'none', lineStyle: { color: '#9b6654', type: 'dashed' }, data: [{ xAxis: 0 }] },
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
        { name: '非线性平均值模型', type: 'line', symbol: 'none', lineStyle: { width: 2.2, color: '#58736f' }, data: response.time_s.map((time, index) => [time, (response.nonlinear_states[index][0] - result.operating_point.state[0]) * 1000]) },
        { name: '局部线性模型', type: 'line', symbol: 'none', lineStyle: { width: 1.6, color: '#96745c', type: 'dashed' }, data: response.time_s.map((time, index) => [time, (response.linear_states[index][0] - result.operating_point.state[0]) * 1000]) },
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
      series: [{ type: 'line', symbol: 'none', lineStyle: { width: 2.2, color: '#667d84' }, data: port.frequencies_hz.map((frequency, index) => [frequency, magnitude[index]]) }],
    }
  }, [result])

  const scanChart = useMemo(() => {
    if (!scanResult) return {}
    const scan = scanResult.result
    const data = scan.rows.flatMap((row, dampingIndex) => row.map((point, reactanceIndex) => {
      const code = !point.valid ? 3 : point.stability_agreement === false ? 2 : point.full_stability === 'stable' ? 1 : point.full_stability === 'marginal' ? 4 : 0
      return [reactanceIndex, dampingIndex, code]
    }))
    return {
      animationDuration: 300,
      grid: { left: 74, right: 28, top: 34, bottom: 72 },
      tooltip: {
        trigger: 'item',
        formatter: (item: { data: [number, number, number] }) => {
          const [reactanceIndex, dampingIndex] = item.data
          const point = scan.rows[dampingIndex][reactanceIndex]
          if (!point.valid) return `D=${point.damping_coefficient_pu}<br/>X=${point.line_reactance_pu}<br/>不可计算：${point.error}`
          const frequencyError = point.frequency_relative_error === null ? '不适用' : `${(point.frequency_relative_error * 100).toFixed(2)}%`
          return `D=${point.damping_coefficient_pu}<br/>线路 X=${point.line_reactance_pu} p.u.<br/>16状态：${point.full_stability}<br/>三状态：${point.reduced_stability}<br/>匹配同步模态频率误差：${frequencyError}`
        },
      },
      xAxis: { type: 'category', name: '外部线路 X / p.u.', nameLocation: 'middle', nameGap: 42, data: scan.axes.reactance_values_pu.map(String) },
      yAxis: { type: 'category', name: '阻尼 D', data: scan.axes.damping_values_pu.map(String) },
      visualMap: {
        type: 'piecewise', orient: 'horizontal', left: 'center', bottom: 2,
        pieces: [
          { value: 1, label: '稳定一致', color: '#718b82' },
          { value: 0, label: '失稳一致', color: '#9b6654' },
          { value: 2, label: '层级失配', color: '#a88a68' },
          { value: 4, label: '临界', color: '#748488' },
          { value: 3, label: '不可计算', color: '#b9b9b1' },
        ],
      },
      series: [{ type: 'heatmap', data, itemStyle: { borderColor: '#fff', borderWidth: 2 }, label: { show: true, formatter: (item: { data: [number, number, number] }) => item.data[2] === 2 ? '失配' : '' } }],
    }
  }, [scanResult])

  const ablationChart = useMemo(() => {
    if (!ablationResult) return {}
    const points = ablationResult.result.points
    return {
      animationDuration: 350,
      grid: { left: 72, right: 28, top: 48, bottom: 112 },
      tooltip: { trigger: 'axis' },
      legend: { top: 4 },
      xAxis: {
        type: 'category',
        name: '消融工况',
        nameLocation: 'middle',
        nameGap: 88,
        axisLabel: { interval: 0, rotate: 42, fontSize: 10 },
        data: points.map(point => formatAblationFactors(point.factors)),
      },
      yAxis: { type: 'value', name: '极点实部 / s⁻¹' },
      series: [
        {
          name: '最右极点实部',
          type: 'line',
          symbolSize: 7,
          lineStyle: { width: 2.2, color: '#9b6654' },
          itemStyle: { color: '#9b6654' },
          data: points.map(point => point.rightmost_pole.real_per_s),
          markLine: {
            silent: true,
            symbol: 'none',
            lineStyle: { color: '#59635f', type: 'dashed' },
            label: { formatter: '稳定边界' },
            data: [{ yAxis: 0 }],
          },
        },
        {
          name: '被追踪额外模态实部',
          type: 'line',
          symbolSize: 7,
          lineStyle: { width: 2.2, color: '#667d84' },
          itemStyle: { color: '#667d84' },
          data: points.map(point => point.extra_mode.pole.real_per_s),
        },
      ],
    }
  }, [ablationResult])

  const boundaryChart = useMemo(() => {
    if (!boundaryResult) return {}
    const paths = boundaryResult.result.paths
    return {
      animationDuration: 350,
      grid: { left: 68, right: 28, top: 48, bottom: 58 },
      tooltip: { trigger: 'axis' },
      legend: { top: 4 },
      xAxis: { type: 'category', name: '单因素路径', nameLocation: 'middle', nameGap: 38, data: paths.map(path => path.label_zh) },
      yAxis: { type: 'value', name: '临界倍率' },
      series: [
        {
          name: '附加模态过零', type: 'line', symbolSize: 9,
          lineStyle: { width: 2.2, color: '#667d84' }, itemStyle: { color: '#667d84' },
          data: paths.map(path => path.extra_mode_boundary.factor_value),
        },
        {
          name: '完整模型谱横坐标过零', type: 'line', symbolSize: 6,
          lineStyle: { width: 1.6, color: '#9b6654', type: 'dashed' }, itemStyle: { color: '#9b6654' },
          data: paths.map(path => path.overall_stability_boundary.factor_value),
        },
      ],
    }
  }, [boundaryResult])

  function updateConverter(field: string, value: number) {
    if (!topology) return
    const next = clone(topology)
    ;(next.grid_forming_converters[0] as unknown as Record<string, number>)[field] = value
    setTopology(next)
    setResult(null)
    setScanResult(null)
  }

  function updateLine(field: 'resistance_pu' | 'reactance_pu', value: number) {
    if (!topology) return
    const next = clone(topology)
    next.lines[0][field] = value
    setTopology(next)
    setResult(null)
    setScanResult(null)
  }

  function updateParameter(field: keyof AverageDQParameters, value: number) {
    if (!parameters) return
    setParameters({ ...parameters, [field]: value })
    setResult(null)
    setScanResult(null)
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

  async function scanModelHierarchy() {
    if (!topology || !parameters) return
    setScanRunning(true)
    setError('')
    try {
      setScanResult(await runAverageDQScan({
        topology,
        parameters,
        damping_values_pu: [10, 20, 30, 40, 50, 60, 80],
        reactance_values_pu: [0.1, 0.2, 0.3, 0.5, 0.8, 1.2],
      }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '平均值 dq 模型层级扫描失败')
    } finally {
      setScanRunning(false)
    }
  }

  async function runFixedAblation() {
    setAblationRunning(true)
    setError('')
    try {
      setAblationResult(await runAverageDQAblation())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '固定 19 点模态消融失败')
    } finally {
      setAblationRunning(false)
    }
  }

  async function runFixedBoundary() {
    setBoundaryRunning(true)
    setError('')
    try {
      setBoundaryResult(await runAverageDQBoundary())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '四条单因素临界边界追踪失败')
    } finally {
      setBoundaryRunning(false)
    }
  }

  async function runFixedPortIdentification() {
    setPortIdentificationRunning(true)
    setError('')
    try {
      setPortIdentificationResult(await runAverageDQPortIdentification())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '三频点端口正弦辨识失败')
    } finally {
      setPortIdentificationRunning(false)
    }
  }

  async function loadExternalEvidence() {
    setExternalEvidenceRunning(true)
    setError('')
    try {
      const [evidence, comparison] = await Promise.all([
        getMathWorksExternalEvidence(),
        getMathWorksTeamComparison(),
      ])
      setExternalEvidence(evidence)
      setCrossModelComparison(comparison)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'MathWorks 外部验证证据读取失败')
    } finally {
      setExternalEvidenceRunning(false)
    }
  }

  async function openPortIdentificationReport() {
    const reportWindow = window.open('', '_blank')
    try {
      const html = await getAverageDQPortIdentificationReportHtml()
      if (reportWindow) {
        reportWindow.document.open()
        reportWindow.document.write(html)
        reportWindow.document.close()
      } else download('average-dq-port-identification-report.html', html, 'text/html')
    } catch (reason) {
      reportWindow?.close()
      setError(reason instanceof Error ? reason.message : '端口辨识报告生成失败')
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
  const firstDisagreement = scanResult?.result.rows.flat().find(point => point.stability_agreement === false)

  return <main className="average-dq-workbench">
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
      <button className="primary-analysis-button" onClick={analyze} disabled={running}><Play size={17} fill="currentColor"/>{running ? '正在求工作点并积分…' : '运行平均值 dq 分析'}</button>
      <button className="quiet-button" onClick={() => download('average-dq-case.json', JSON.stringify({ topology, parameters }, null, 2))}><Download size={15}/>保存当前模型参数</button>
      <p className="scope-note">参数变化会清空旧分析结果。固定研究任务使用各自冻结的锚点，不受这里的临时编辑影响。</p>
      {error && <p className="error">{error}</p>}
    </aside>

    <section className="workspace">
      <div className="study-launcher" aria-label="固定研究任务">
        <article className="study-task hierarchy-task">
          <div className="study-task-heading"><span>01</span><small>MODEL HIERARCHY</small></div>
          <h3>D–X 模型层级对照</h3>
          <p>逐点重算42个参数点，比较16状态模型与三状态近似的稳定性分类。</p>
          <div className="study-task-actions">
            <button onClick={scanModelHierarchy} disabled={scanRunning}>{scanRunning ? '正在逐点重算…' : '运行42点扫描'}</button>
            <button className="icon-action" aria-label="导出层级扫描 JSON" disabled={!scanResult} onClick={() => scanResult && download(`${scanResult.run_id}.json`, JSON.stringify(scanResult, null, 2))}><Download size={15}/></button>
          </div>
        </article>
        <article className="study-task ablation-task">
          <div className="study-task-heading"><span>02</span><small>MODAL ABLATION</small></div>
          <h3>固定19点模态消融</h3>
          <p data-testid="average-dq-ablation-fixed-scope">冻结 D=60、外部线路 X=0.1 p.u.，以固定 19 点追踪控制与LCL参数变化下的候选模态。</p>
          <div className="study-task-actions">
            <button data-testid="average-dq-ablation-run" onClick={runFixedAblation} disabled={ablationRunning}>{ablationRunning ? '正在追踪模态…' : '运行19点消融'}</button>
            <button className="icon-action" aria-label="导出模态消融 JSON" data-testid="average-dq-ablation-export" disabled={!ablationResult} onClick={() => ablationResult && download(`${ablationResult.run_id}.json`, JSON.stringify(ablationResult, null, 2))}><Download size={15}/></button>
          </div>
        </article>
        <article className="study-task boundary-task">
          <div className="study-task-heading"><span>03</span><small>BOUNDARY TRACE</small></div>
          <h3>四条一维临界边界</h3>
          <p data-testid="average-dq-boundary-fixed-scope">在同一锚点沿四条单因素路径，分别求解附加模态过零与完整模型稳定边界。</p>
          <div className="study-task-actions">
            <button data-testid="average-dq-boundary-run" onClick={runFixedBoundary} disabled={boundaryRunning}>{boundaryRunning ? '正在二分加密…' : '追踪临界边界'}</button>
            <button className="icon-action" aria-label="导出临界边界 JSON" data-testid="average-dq-boundary-export" disabled={!boundaryResult} onClick={() => boundaryResult && download(`${boundaryResult.run_id}.json`, JSON.stringify(boundaryResult, null, 2))}><Download size={15}/></button>
          </div>
        </article>
        <article className="study-task port-identification-task">
          <div className="study-task-heading"><span>04</span><small>PORT IDENTIFICATION</small></div>
          <h3>三频点端口正弦辨识</h3>
          <p data-testid="average-dq-port-identification-fixed-scope">固定 0.2、2、20 Hz，由非线性 PCC 电压与端口电流相量反演导纳，并与局部线性化逐元素核对。</p>
          <div className="study-task-actions has-two-icons">
            <button data-testid="average-dq-port-identification-run" onClick={runFixedPortIdentification} disabled={portIdentificationRunning}>{portIdentificationRunning ? '正在逐频辨识…' : '运行三频点辨识'}</button>
            <button className="icon-action" aria-label="导出端口辨识 JSON" data-testid="average-dq-port-identification-export" disabled={!portIdentificationResult} onClick={() => portIdentificationResult && download(`${portIdentificationResult.run_id}.json`, JSON.stringify(portIdentificationResult, null, 2))}><Download size={15}/></button>
            <button className="icon-action" aria-label="生成端口辨识报告" data-testid="average-dq-port-identification-report" disabled={!portIdentificationResult || portIdentificationRunning} onClick={openPortIdentificationReport}><BookOpenCheck size={15}/></button>
          </div>
        </article>
        <article className="study-task external-evidence-task">
          <div className="study-task-heading"><span>05</span><small>EXTERNAL REFERENCE</small></div>
          <h3>MathWorks 固定模型参照</h3>
          <p data-testid="mathworks-external-evidence-fixed-scope">对齐50 Hz阻尼归一化、SCR、X/R与有功工作点，比较外部时域分类和团队16状态模型局部极点。</p>
          <div className="study-task-actions">
            <button data-testid="mathworks-external-evidence-load" onClick={loadExternalEvidence} disabled={externalEvidenceRunning}>{externalEvidenceRunning ? '正在重算八点对照…' : '运行外部—团队对照'}</button>
            <button className="icon-action" aria-label="导出跨模型对照 JSON" data-testid="mathworks-team-comparison-export" disabled={!crossModelComparison} onClick={() => crossModelComparison && download(`${crossModelComparison.run_id}.json`, JSON.stringify(crossModelComparison, null, 2))}><Download size={15}/></button>
          </div>
        </article>
      </div>

      <div className="result-toolbar">
        <div><small>LIVE ANALYSIS</small><b>{result ? '当前结果可追溯' : '等待运行模型'}</b></div>
        <div className="inline-actions">
          <button disabled={!result} onClick={() => result && download(`${result.run_id}.json`, JSON.stringify(result, null, 2))}><Download size={15}/>结果 JSON</button>
          <button disabled={!result} onClick={openReport}><BookOpenCheck size={15}/>分析报告</button>
        </div>
      </div>

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
          <div><small>匹配同步模态频率误差</small><b>{result.result.quasisteady_reduction_comparison.oscillation_frequency_relative_error === null ? '不适用' : `${(result.result.quasisteady_reduction_comparison.oscillation_frequency_relative_error * 100).toFixed(2)}%`}</b></div>
        </div>
        <div className="chart-grid">
          <div className="panel chart-card"><div className="panel-title"><Gauge size={18}/><span>闭环极点分布</span><em>虚轴右侧为失稳</em></div><EChart option={poleChart} style={{ height: 320 }}/></div>
          <div className="panel chart-card"><div className="panel-title"><Activity size={18}/><span>非线性—线性相角响应</span><em>小扰动实现核对</em></div><EChart option={responseChart} style={{ height: 320 }}/></div>
        </div>
        <div className="panel chart-card"><div className="panel-title"><Activity size={18}/><span>变流器端口导纳范数</span><em>网络流入变流器为正 · 全局同步 dq 坐标</em></div><EChart option={admittanceChart} style={{ height: 330 }}/></div>
        <div className="panel provenance-card"><div className="panel-title"><BookOpenCheck size={18}/><span>模型身份与结论边界</span></div><p>{result.model_scope.statement}</p><p>{result.result.quasisteady_reduction_comparison.interpretation}</p><dl><div><dt>模型层级</dt><dd>正序平均值 ODE，16 个状态</dd></div><div><dt>工作点同步刚度 Kδ</dt><dd>{result.result.quasisteady_reduction_comparison.synchronizing_stiffness_pu_per_rad.toFixed(5)} p.u./rad</dd></div><div><dt>匹配同步模态衰减率误差</dt><dd>{result.result.quasisteady_reduction_comparison.decay_rate_relative_error === null ? '不适用' : `${(result.result.quasisteady_reduction_comparison.decay_rate_relative_error * 100).toFixed(2)}%`}</dd></div><div><dt>硬件参数拟合</dt><dd>未进行</dd></div></dl></div>
      </> : <div className="panel empty-state"><Activity size={34}/><h2>编辑参数后运行16状态模型</h2><p>平台会先求解工作点并检查功率平衡，再计算闭环极点、端口导纳以及非线性—线性小扰动响应。</p></div>}
      {scanResult && <>
        <div className="panel evidence-strip">
          <div><small>扫描点数</small><b>{scanResult.result.point_count}</b></div>
          <div><small>两层分类一致</small><b>{scanResult.result.counts.agreement}</b></div>
          <div><small>两层分类不一致</small><b>{scanResult.result.counts.disagreement}</b></div>
          <div><small>不可计算点</small><b>{scanResult.result.counts.invalid}</b></div>
        </div>
        <div className="panel chart-card"><div className="panel-title"><ShieldAlert size={18}/><span>16状态—三状态 D–X 层级对照</span><em>逐点重算，不做显示层插值</em></div><EChart option={scanChart} style={{ height: 390 }}/>{firstDisagreement && <div className="evidence-strip"><div><small>首个失配锚点</small><b>D={firstDisagreement.damping_coefficient_pu}，X={firstDisagreement.line_reactance_pu}</b></div><div><small>16状态最右极点实部</small><b>{firstDisagreement.full_dominant_real_per_s?.toFixed(4)} s⁻¹</b></div><div><small>匹配同步模态实部</small><b>{firstDisagreement.matched_full_mode_real_per_s?.toFixed(4)} s⁻¹</b></div><div><small>主要参与状态</small><b>{firstDisagreement.full_dominant_participation?.slice(0, 4).map(item => stateNames[item.state] ?? item.state).join('、')}</b></div></div>}<p className="scope-note">{scanResult.model_scope.interpretation} {scanResult.model_scope.statement}</p></div>
      </>}
      {ablationResult && <section data-testid="average-dq-ablation-results">
        <div className="panel evidence-strip" data-testid="average-dq-ablation-summary">
          <div><small>固定消融点数</small><b>{ablationResult.result.point_count}</b></div>
          <div><small>整体稳定 / 失稳</small><b>{ablationResult.result.summary.stability_counts.stable} / {ablationResult.result.summary.stability_counts.unstable}</b></div>
          <div><small>额外模态 matched / pending</small><b>{ablationResult.result.summary.extra_mode_tracking_counts.matched} / {ablationResult.result.summary.extra_mode_tracking_counts.pending}</b></div>
        </div>
        <div className="panel chart-card" data-testid="average-dq-ablation-chart">
          <div className="panel-title"><ShieldAlert size={18}/><span>固定 19 点模态消融</span><em>D=60，外部线路 X=0.1 p.u.</em></div>
          <EChart option={ablationChart} style={{ height: 430 }}/>
        </div>
        <div className="panel" data-testid="average-dq-ablation-table" style={{ overflowX: 'auto' }}>
          <div className="panel-title"><BookOpenCheck size={18}/><span>消融工况与模态追踪证据</span></div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead><tr>
              {['工况', '因素', '整体稳定性', '额外模态实部 / s⁻¹', '主要参与组', '追踪状态'].map(label => <th key={label} style={{ padding: '9px 8px', textAlign: 'left', borderBottom: '1px solid #dfe6ea' }}>{label}</th>)}
            </tr></thead>
            <tbody>{ablationResult.result.points.map(point => <tr key={point.scenario_id} data-testid={`average-dq-ablation-row-${point.scenario_id}`}>
              <td style={{ padding: '8px', borderBottom: '1px solid #edf1f3' }}>{point.scenario_id}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #edf1f3' }}>{formatAblationFactors(point.factors)}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #edf1f3' }}>{point.stability === 'stable' ? '稳定' : point.stability === 'marginal' ? '临界' : '失稳'}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #edf1f3' }}>{point.extra_mode.pole.real_per_s.toFixed(6)}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #edf1f3' }}>{leadingParticipationGroup(point.extra_group_participation)}</td>
              <td style={{ padding: '8px', borderBottom: '1px solid #edf1f3' }}>{point.extra_mode.status}</td>
            </tr>)}</tbody>
          </table>
          <p className="scope-note" data-testid="average-dq-ablation-tracking-boundary">{ablationResult.model_scope.tracking_boundary}</p>
        </div>
      </section>}
      {boundaryResult && <section data-testid="average-dq-boundary-results">
        <div className="panel evidence-strip" data-testid="average-dq-boundary-summary">
          <div><small>冻结单因素路径</small><b>{boundaryResult.result.path_count}</b></div>
          <div><small>附加模态 / 整体边界收敛</small><b>{boundaryResult.result.converged_extra_mode_boundaries} / {boundaryResult.result.converged_overall_boundaries}</b></div>
          <div><small>两类边界一致</small><b>{boundaryResult.result.agreeing_boundary_count} / {boundaryResult.result.path_count}</b></div>
        </div>
        <div className="panel chart-card" data-testid="average-dq-boundary-chart">
          <div className="panel-title"><Activity size={18}/><span>四条单因素临界边界</span><em>对数中点二分 · 逐点重建工作点</em></div>
          <EChart option={boundaryChart} style={{ height: 360 }}/>
        </div>
        <div className="panel boundary-table" data-testid="average-dq-boundary-table">
          <div className="panel-title"><BookOpenCheck size={18}/><span>临界倍率与模态交接</span></div>
          <div className="table-scroll">
            <table>
              <thead><tr>{['路径', '筛查端点', '附加模态边界', '整体稳定边界', '一致', '边界后模态交接', '计算点数'].map(label => <th key={label}>{label}</th>)}</tr></thead>
              <tbody>{boundaryResult.result.paths.map(path => <tr key={path.path_id} data-testid={`average-dq-boundary-row-${path.factor_name}`}>
                <td>{path.label_zh}</td>
                <td>{path.screening_endpoint_factor.toFixed(3)}</td>
                <td>{path.extra_mode_boundary.factor_value?.toFixed(6) ?? path.extra_mode_boundary.status}</td>
                <td>{path.overall_stability_boundary.factor_value?.toFixed(6) ?? path.overall_stability_boundary.status}</td>
                <td>{path.boundaries_agree === null ? '待定' : path.boundaries_agree ? '是' : '否'}</td>
                <td>{path.mode_handoff_observed ? '观察到' : '未观察到'}</td>
                <td>{path.trial_count}</td>
              </tr>)}</tbody>
            </table>
          </div>
          <p className="scope-note" data-testid="average-dq-boundary-interpretation">{boundaryResult.result.interpretation_boundary}</p>
        </div>
      </section>}
      {portIdentificationResult && <section data-testid="average-dq-port-identification-results">
        <div className="panel evidence-strip" data-testid="average-dq-port-identification-summary">
          <div><small>三频点判定</small><b>{portIdentificationResult.result.summary.passed ? '全部通过' : '存在未通过点'}</b></div>
          <div><small>最大幅值误差</small><b>{(portIdentificationResult.result.summary.maximum_magnitude_relative_error * 100).toFixed(4)}%</b></div>
          <div><small>最大相位误差</small><b>{portIdentificationResult.result.summary.maximum_phase_error_deg.toFixed(4)}°</b></div>
          <div><small>幅值减半最大变化</small><b>{(portIdentificationResult.result.amplitude_halving_check_at_2hz.maximum_element_relative_difference * 100).toFixed(4)}%</b></div>
        </div>
        <div className="panel port-identification-table" data-testid="average-dq-port-identification-table">
          <div className="panel-title"><Activity size={18}/><span>非线性辨识—端口线性化对照</span><em>固定全局同步 dq · 网络流向设备为正</em></div>
          <div className="table-scroll">
            <table>
              <thead><tr>{['频率 / Hz', '舍弃周期', '求解器', '最大幅值误差', '最大相位误差', '最大残差', 'cond(V)', '判定'].map(label => <th key={label}>{label}</th>)}</tr></thead>
              <tbody>{portIdentificationResult.result.points.map(point => <tr key={point.frequency_hz} data-testid={`average-dq-port-identification-row-${point.frequency_hz}`}>
                <td>{point.frequency_hz}</td>
                <td>{point.settling_periods}</td>
                <td>{point.solver_method}</td>
                <td>{(point.maximum_magnitude_relative_error * 100).toFixed(5)}%</td>
                <td>{point.maximum_phase_error_deg.toFixed(5)}°</td>
                <td>{(point.maximum_harmonic_residual_ratio * 100).toFixed(5)}%</td>
                <td>{point.voltage_matrix_condition_number.toFixed(4)}</td>
                <td>{point.passed ? '通过' : '未通过'}</td>
              </tr>)}</tbody>
            </table>
          </div>
          <p className="scope-note" data-testid="average-dq-port-identification-boundary">{portIdentificationResult.model_scope.statement} 设备开端口矩阵并非渐近稳定，因此采用稳定闭环源电压注入；本结果不评价论文稳定性充分条件。</p>
        </div>
      </section>}
      {externalEvidence && <section data-testid="mathworks-external-evidence-results">
        <div className="panel evidence-strip" data-testid="mathworks-external-evidence-summary">
          <div><small>三点 SCR 供应商分类</small><b>{externalEvidence.summary.three_point_vendor_outcomes.join(' / ')}</b></div>
          <div><small>2×4 因子稳定点</small><b>{externalEvidence.summary.factorial_stable_point_count} / {externalEvidence.summary.factorial_point_count}</b></div>
          <div><small>供应商分类过渡区 / p.u.</small><b>[{externalEvidence.summary.vendor_classification_bracket_pu.map(value => value.toFixed(5)).join(', ')}]</b></div>
          <div><small>项目跟踪门已测区间 / p.u.</small><b>[{externalEvidence.summary.project_tracking_observed_bracket_pu.map(value => value.toFixed(4)).join(', ')}] · {externalEvidence.summary.project_tracking_target_achieved ? '目标已达成' : '目标未达成'}</b></div>
        </div>
        <div className="panel external-evidence-panel">
          <div className="panel-title"><BookOpenCheck size={18}/><span>固定版本外部时域参照</span><em>MathWorks {externalEvidence.source.release_tag} · MATLAB R{externalEvidence.source.matlab_release}</em></div>
          <p data-testid="mathworks-external-evidence-boundary">{externalEvidence.scope.statement} 本证据不评价论文稳定性充分条件，也不构成实物或硬件在环确认。</p>
        </div>
        {crossModelComparison && <div className="panel cross-model-comparison" data-testid="mathworks-team-comparison-results">
          <div className="panel-title"><Activity size={18}/><span>外部时域分类—团队局部极点对照</span><em>D_team = 50·D_MW · |Z源| = 1/SCR</em></div>
          <div className="panel evidence-strip" data-testid="mathworks-team-comparison-summary">
            <div><small>固定对齐点</small><b>{crossModelComparison.summary.point_count}</b></div>
            <div><small>分类一致</small><b>{crossModelComparison.summary.classification_agreement_count} / {crossModelComparison.summary.point_count}</b></div>
            <div><small>分类不一致</small><b>{crossModelComparison.summary.classification_disagreement_count}</b></div>
            <div><small>定量过渡位置</small><b>{crossModelComparison.boundary_comparison.quantitative_transition_reproduced ? '已复现' : '未复现'}</b></div>
          </div>
          <div className="table-scroll">
            <table>
              <thead><tr>{['SCR', 'D_MW / p.u./Hz', 'D_team', '外部时域', '团队 P*=0.6', '团队 P*=0.8', '对照'].map(label => <th key={label}>{label}</th>)}</tr></thead>
              <tbody>{crossModelComparison.points.map(point => <tr key={`${point.scr}-${point.damping_mathworks_pu_per_hz}`} data-testid={`mathworks-team-row-${point.scr}-${point.damping_mathworks_pu_per_hz}`}>
                <td>{point.scr}</td>
                <td>{point.damping_mathworks_pu_per_hz}</td>
                <td>{point.damping_team_native_pu_per_pu_frequency.toFixed(3)}</td>
                <td>{point.external_vendor_outcome === 'Stable' ? '稳定' : '失稳'}</td>
                <td>{point.team_pre_step_stability === 'stable' ? '稳定' : point.team_pre_step_stability === 'unstable' ? '失稳' : '临界'}</td>
                <td>{point.team_post_step_stability === 'stable' ? '稳定' : point.team_post_step_stability === 'unstable' ? '失稳' : '临界'}</td>
                <td className={point.classification_agreement ? 'comparison-agree' : 'comparison-disagree'}>{point.classification_agreement ? '一致' : '不一致'}</td>
              </tr>)}</tbody>
            </table>
          </div>
          <div className="boundary-comparison-grid" data-testid="mathworks-team-boundary-comparison">
            <div><small>MathWorks 供应商时域分类区间</small><b>[{crossModelComparison.boundary_comparison.external_vendor_classification_bracket_pu_per_hz.map(value => value.toFixed(5)).join(', ')}] p.u./Hz</b></div>
            {crossModelComparison.boundary_comparison.team_local_eigenvalue_boundaries.map(boundary => <div key={boundary.active_power_setpoint_pu}><small>团队局部极点边界 · P*={boundary.active_power_setpoint_pu}</small><b>{boundary.damping_mw_equivalent_pu_per_hz.toFixed(6)} p.u./Hz 等效值</b></div>)}
          </div>
          <p className="scope-note" data-testid="mathworks-team-comparison-boundary">{crossModelComparison.summary.interpretation} {crossModelComparison.scope.statement} 外部供应商时域阈值与团队局部特征根并非同一种证据，差值不命名为预测误差。</p>
        </div>}
      </section>}
    </section>
  </main>
}
