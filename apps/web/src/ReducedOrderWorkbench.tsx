import { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkLineComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  Activity,
  Box,
  CircleCheck,
  Download,
  FileUp,
  Gauge,
  Network,
  Play,
  Plus,
  Save,
  ShieldAlert,
  Trash2,
} from 'lucide-react'
import {
  ACLine,
  Bus,
  GridFormingConverter,
  NetworkTopology,
  ReducedOrderAnalysisResult,
  ReducedOrderPreset,
  ReducedOrderPresetId,
  ReducedOrderScanResult,
  getReducedOrderReportHtml,
  getReducedOrderPresets,
  runReducedOrderAnalysis,
  runReducedOrderScan,
} from './api'

echarts.use([
  LineChart,
  ScatterChart,
  HeatmapChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const stabilityText = { stable: '稳定', marginal: '临界', unstable: '失稳' }

function downloadText(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function downloadJson(filename: string, value: unknown) {
  downloadText(filename, JSON.stringify(value, null, 2), 'application/json')
}

function csvCell(value: unknown) {
  const text = String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function estimateResponseFrequency(result: ReducedOrderAnalysisResult | null) {
  if (!result) return null
  const response = result.result.time_response
  const angleIndex = response.state_labels.findIndex(label => label.startsWith('delta_rad:'))
  if (angleIndex < 0 || response.time_s.length < 10) return null
  const start = Math.floor(response.time_s.length * 0.2)
  const samples = response.states.slice(start).map(row => row[angleIndex])
  const mean = samples.reduce((sum, value) => sum + value, 0) / samples.length
  const crossings: number[] = []
  for (let index = start + 1; index < response.time_s.length; index += 1) {
    const left = response.states[index - 1][angleIndex] - mean
    const right = response.states[index][angleIndex] - mean
    if (left <= 0 && right > 0) {
      const ratio = left === right ? 0 : -left / (right - left)
      crossings.push(response.time_s[index - 1] + ratio * (response.time_s[index] - response.time_s[index - 1]))
    }
  }
  if (crossings.length < 2) return null
  const periods = crossings.slice(1).map((value, index) => value - crossings[index]).filter(value => value > 0)
  periods.sort((a, b) => a - b)
  const period = periods[Math.floor(periods.length / 2)]
  return period > 0 ? 1 / period : null
}

function numeric(value: string, fallback: number) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function linspace(start: number, end: number, count: number) {
  if (count <= 1) return [start]
  return Array.from({ length: count }, (_, index) => start + (end - start) * index / (count - 1))
}

function nextEntityId(prefix: string, ids: string[]) {
  const occupied = new Set(ids)
  let index = 1
  while (occupied.has(`${prefix}-${index}`)) index += 1
  return `${prefix}-${index}`
}

function allEntityIds(topology: NetworkTopology) {
  return [
    ...topology.buses.map(item => item.id),
    ...topology.lines.map(item => item.id),
    ...topology.grid_forming_converters.map(item => item.id),
    ...topology.infinite_buses.map(item => item.id),
    ...topology.loads.map(item => item.id),
  ]
}

export default function ReducedOrderWorkbench() {
  const [presets, setPresets] = useState<ReducedOrderPreset[]>([])
  const [selectedPreset, setSelectedPreset] = useState<ReducedOrderPresetId>('reduced-smib-stable')
  const [topology, setTopology] = useState<NetworkTopology | null>(null)
  const [customized, setCustomized] = useState(false)
  const [result, setResult] = useState<ReducedOrderAnalysisResult | null>(null)
  const [simulationTime, setSimulationTime] = useState(20)
  const [timeStep, setTimeStep] = useState(0.02)
  const [initialAngleMrad, setInitialAngleMrad] = useState(1)
  const [running, setRunning] = useState(false)
  const [scanResult, setScanResult] = useState<ReducedOrderScanResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanDMin, setScanDMin] = useState(0.05)
  const [scanDMax, setScanDMax] = useState(70)
  const [scanXMin, setScanXMin] = useState(0.08)
  const [scanXMax, setScanXMax] = useState(0.6)
  const [scanAxisCount, setScanAxisCount] = useState(21)
  const [scanTargetVsmId, setScanTargetVsmId] = useState('')
  const [scanTargetLineId, setScanTargetLineId] = useState('')
  const [error, setError] = useState('')
  const importRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    getReducedOrderPresets()
      .then(payload => {
        setPresets(payload.presets)
        const initial = payload.presets.find(item => item.id === selectedPreset) ?? payload.presets[0]
        if (initial) setTopology(clone(initial.topology))
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '无法读取预设'))
  }, [])

  useEffect(() => {
    if (!topology) return
    if (!topology.grid_forming_converters.some(item => item.id === scanTargetVsmId)) {
      setScanTargetVsmId(topology.grid_forming_converters[0]?.id ?? '')
    }
    if (!topology.lines.some(item => item.id === scanTargetLineId)) {
      setScanTargetLineId(topology.lines[0]?.id ?? '')
    }
  }, [topology, scanTargetVsmId, scanTargetLineId])

  function choosePreset(id: ReducedOrderPresetId) {
    setSelectedPreset(id)
    const preset = presets.find(item => item.id === id)
    if (preset) setTopology(clone(preset.topology))
    setCustomized(false)
    setResult(null)
    setScanResult(null)
    setError('')
  }

  function changeTopology(mutator: (draft: NetworkTopology) => void) {
    if (!topology) return
    const draft = clone(topology)
    mutator(draft)
    draft.id = `custom-${draft.id.replace(/^custom-/, '')}`.slice(0, 64)
    draft.name = draft.name.replace(/（自定义）$/, '') + '（自定义）'
    setTopology(draft)
    setCustomized(true)
    setResult(null)
    setScanResult(null)
  }

  function updateBus(index: number, patch: Partial<Bus>) {
    changeTopology(draft => {
      const oldId = draft.buses[index].id
      Object.assign(draft.buses[index], patch)
      const newId = draft.buses[index].id
      if (oldId !== newId) {
        draft.lines.forEach(line => {
          if (line.from_bus_id === oldId) line.from_bus_id = newId
          if (line.to_bus_id === oldId) line.to_bus_id = newId
        })
        draft.grid_forming_converters.forEach(gfm => { if (gfm.bus_id === oldId) gfm.bus_id = newId })
        draft.infinite_buses.forEach(grid => { if (grid.bus_id === oldId) grid.bus_id = newId })
        draft.loads.forEach(load => { if (load.bus_id === oldId) load.bus_id = newId })
        if (draft.reference_bus_id === oldId) draft.reference_bus_id = newId
      }
    })
  }

  function updateLine(index: number, patch: Partial<ACLine>) {
    changeTopology(draft => Object.assign(draft.lines[index], patch))
  }

  function updateGfm(index: number, patch: Partial<GridFormingConverter>) {
    changeTopology(draft => Object.assign(draft.grid_forming_converters[index], patch))
  }

  function updateInfiniteBus(index: number, patch: Partial<NetworkTopology['infinite_buses'][number]>) {
    changeTopology(draft => {
      const oldBusId = draft.infinite_buses[index].bus_id
      Object.assign(draft.infinite_buses[index], patch)
      const newBusId = draft.infinite_buses[index].bus_id
      if (oldBusId !== newBusId && draft.reference_bus_id === oldBusId) {
        draft.reference_bus_id = newBusId
      }
    })
  }

  function addBus() {
    if (!topology) return
    const id = nextEntityId('bus', allEntityIds(topology))
    changeTopology(draft => draft.buses.push({
      id,
      name: `母线 ${id.split('-').pop()}`,
      nominal_voltage_v: draft.base_values.voltage_v,
    }))
  }

  function removeBus(index: number) {
    if (!topology || topology.buses.length <= 2) return
    const busId = topology.buses[index].id
    if (topology.infinite_buses.length === 1 && topology.infinite_buses[0].bus_id === busId) {
      setError('当前低频模型至少需要保留一个无限大母线；请先新增或迁移无限大母线。')
      return
    }
    changeTopology(draft => {
      draft.buses.splice(index, 1)
      draft.lines = draft.lines.filter(line => line.from_bus_id !== busId && line.to_bus_id !== busId)
      draft.grid_forming_converters = draft.grid_forming_converters.filter(gfm => gfm.bus_id !== busId)
      draft.infinite_buses = draft.infinite_buses.filter(grid => grid.bus_id !== busId)
      draft.loads = draft.loads.filter(load => load.bus_id !== busId)
      if (draft.reference_bus_id === busId) {
        draft.reference_bus_id = draft.infinite_buses[0]?.bus_id ?? draft.buses[0].id
      }
    })
  }

  function addLine() {
    if (!topology || topology.buses.length < 2) return
    const id = nextEntityId('line', allEntityIds(topology))
    changeTopology(draft => draft.lines.push({
      id,
      name: `线路 ${id.split('-').pop()}`,
      from_bus_id: draft.buses[0].id,
      to_bus_id: draft.buses[1].id,
      resistance_pu: 0.01,
      reactance_pu: 0.2,
      shunt_susceptance_pu: 0,
    }))
  }

  function addGfm() {
    if (!topology) return
    const id = nextEntityId('gfm', allEntityIds(topology))
    const occupied = new Set(topology.grid_forming_converters.map(item => item.bus_id))
    const bus = topology.buses.find(item => !occupied.has(item.id) && !topology.infinite_buses.some(grid => grid.bus_id === item.id))
    if (!bus) {
      setError('请先新增一个未被无限大母线或其他 VSM 占用的母线。')
      return
    }
    changeTopology(draft => draft.grid_forming_converters.push({
      id,
      name: `VSM ${id.split('-').pop()}`,
      bus_id: bus.id,
      rated_apparent_power_va: draft.base_values.apparent_power_va,
      control_mode: 'virtual_synchronous_machine',
      active_power_setpoint_pu: 0,
      reactive_power_setpoint_pu: 0,
      voltage_setpoint_pu: 1,
      virtual_inertia_s: 2,
      damping_coefficient_pu: 60,
      active_power_measurement_time_constant_s: 0.1,
    }))
  }

  function addInfiniteBus() {
    if (!topology) return
    const occupied = new Set([
      ...topology.grid_forming_converters.map(item => item.bus_id),
      ...topology.infinite_buses.map(item => item.bus_id),
    ])
    const bus = topology.buses.find(item => !occupied.has(item.id))
    if (!bus) {
      setError('请先新增一个未被 VSM 或其他无限大母线占用的母线。')
      return
    }
    const id = nextEntityId('grid', allEntityIds(topology))
    changeTopology(draft => {
      const wasEmpty = draft.infinite_buses.length === 0
      draft.infinite_buses.push({
        id,
        name: `无限大母线 ${id.split('-').pop()}`,
        bus_id: bus.id,
        voltage_magnitude_pu: 1,
        voltage_angle_deg: 0,
      })
      if (wasEmpty) draft.reference_bus_id = bus.id
    })
  }

  function removeInfiniteBus(index: number) {
    if (!topology) return
    if (topology.infinite_buses.length <= 1) {
      setError('当前低频模型至少需要保留一个无限大母线。')
      return
    }
    const removedBusId = topology.infinite_buses[index].bus_id
    changeTopology(draft => {
      draft.infinite_buses.splice(index, 1)
      if (draft.reference_bus_id === removedBusId) {
        draft.reference_bus_id = draft.infinite_buses[0]?.bus_id ?? draft.buses[0].id
      }
    })
  }

  async function analyze() {
    if (!topology) return
    setRunning(true)
    setError('')
    try {
      const common = {
        simulation_time_s: simulationTime,
        time_step_s: timeStep,
        initial_angle_perturbation_rad: initialAngleMrad / 1000,
      }
      setResult(await runReducedOrderAnalysis(customized
        ? { ...common, topology }
        : { ...common, preset_id: selectedPreset }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '分析失败')
    } finally {
      setRunning(false)
    }
  }

  function requestPayload() {
    if (!topology) throw new Error('拓扑尚未加载。')
    const common = {
      simulation_time_s: simulationTime,
      time_step_s: timeStep,
      initial_angle_perturbation_rad: initialAngleMrad / 1000,
    }
    return customized ? { ...common, topology } : { ...common, preset_id: selectedPreset }
  }

  async function openPrintableReport() {
    setError('')
    const reportWindow = window.open('', '_blank')
    try {
      const html = await getReducedOrderReportHtml(requestPayload())
      const blobUrl = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
      if (reportWindow) {
        reportWindow.location.href = blobUrl
      } else {
        window.open(blobUrl, '_blank', 'noopener,noreferrer')
      }
      window.setTimeout(() => URL.revokeObjectURL(blobUrl), 60000)
    } catch (reason) {
      reportWindow?.close()
      setError(reason instanceof Error ? reason.message : '报告生成失败')
    }
  }

  async function importCase(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    try {
      const parsed = JSON.parse(await file.text()) as Record<string, unknown>
      let importedTopology: NetworkTopology
      if (parsed.schema_version === 'gfm-reduced-order-case/1.0') {
        importedTopology = parsed.topology as NetworkTopology
        const settings = parsed.simulation_settings as Record<string, number> | undefined
        if (settings) {
          setSimulationTime(settings.simulation_time_s ?? 20)
          setTimeStep(settings.time_step_s ?? 0.02)
          setInitialAngleMrad((settings.initial_angle_perturbation_rad ?? 0.001) * 1000)
        }
      } else if (parsed.schema_version === '1.0') {
        importedTopology = parsed as NetworkTopology
      } else {
        throw new Error(`不支持的案例版本：${String(parsed.schema_version ?? '缺失')}`)
      }
      if (!importedTopology?.buses || !importedTopology?.lines) throw new Error('案例缺少网络拓扑字段。')
      setTopology(importedTopology)
      setCustomized(true)
      setResult(null)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? `案例文件无法读取：${reason.message}` : '案例文件无法读取')
    } finally {
      event.target.value = ''
    }
  }

  function exportCase() {
    if (!topology) return
    downloadJson(`${topology.id}.gfm-case.json`, {
      schema_version: 'gfm-reduced-order-case/1.0',
      analysis_mode: 'low-frequency-angle-frequency-active-power-reduced-order',
      topology,
      simulation_settings: {
        simulation_time_s: simulationTime,
        time_step_s: timeStep,
        initial_angle_perturbation_rad: initialAngleMrad / 1000,
      },
      model_scope: 'low-frequency-reduced-order-model-only',
    })
  }

  function exportCsv() {
    if (!result) return
    const poleRows = [
      ['pole_index', 'real_per_s', 'imag_per_s', 'real_hz', 'imag_hz'],
      ...result.result.poles.map((pole, index) => [index, pole.real_per_s, pole.imag_per_s, pole.real_hz, pole.imag_hz]),
    ]
    const response = result.result.time_response
    const timeRows = [
      ['time_s', ...response.state_labels],
      ...response.time_s.map((time, index) => [time, ...response.states[index]]),
    ]
    downloadText(`${result.run_id}-poles.csv`, poleRows.map(row => row.map(csvCell).join(',')).join('\r\n'), 'text/csv;charset=utf-8')
    window.setTimeout(() => downloadText(`${result.run_id}-time-response.csv`, timeRows.map(row => row.map(csvCell).join(',')).join('\r\n'), 'text/csv;charset=utf-8'), 150)
  }

  async function runParameterScan() {
    if (!topology) return
    const targetVsm = topology.grid_forming_converters.find(item => item.id === scanTargetVsmId)
    const targetLine = topology.lines.find(item => item.id === scanTargetLineId)
    if (!targetVsm || !targetLine) {
      setError('D–X 扫描至少需要一台 VSM 和一条交流线路。')
      return
    }
    const count = Math.max(2, Math.min(50, Math.round(scanAxisCount)))
    setScanning(true)
    setError('')
    try {
      setScanResult(await runReducedOrderScan({
        topology,
        target_vsm_id: targetVsm.id,
        target_line_id: targetLine.id,
        damping_values_pu: linspace(scanDMin, scanDMax, count),
        reactance_values_pu: linspace(scanXMin, scanXMax, count),
      }))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '参数扫描失败')
    } finally {
      setScanning(false)
    }
  }

  function exportScanCsv() {
    if (!scanResult) return
    const rows = [
      ['damping_D_pu', 'line_reactance_X_pu', 'stability', 'dominant_real_per_s', 'dominant_real_hz', 'oscillation_frequency_hz'],
      ...scanResult.scan.rows.flat().map(point => [
        point.damping_coefficient_pu,
        point.line_reactance_pu,
        point.stability,
        point.dominant_real_per_s,
        point.dominant_real_hz,
        point.oscillation_frequency_hz,
      ]),
    ]
    downloadText(`${scanResult.run_id}.csv`, rows.map(row => row.map(csvCell).join(',')).join('\r\n'), 'text/csv;charset=utf-8')
  }

  const poleChart = useMemo(() => {
    if (!result) return {}
    return {
      animationDuration: 400,
      grid: { left: 62, right: 25, top: 32, bottom: 50 },
      tooltip: { formatter: (params: { data: number[] }) => `实部 ${params.data[0].toFixed(5)} Hz<br/>虚部 ${params.data[1].toFixed(5)} Hz` },
      xAxis: { type: 'value', name: '实部 / Hz', nameLocation: 'middle', nameGap: 32 },
      yAxis: { type: 'value', name: '虚部 / Hz' },
      series: [{
        type: 'scatter', symbolSize: 11, itemStyle: { color: '#276c9b' },
        data: result.result.poles.map(pole => [pole.real_hz, pole.imag_hz]),
        markLine: { silent: true, symbol: 'none', lineStyle: { color: '#c54b4b', type: 'dashed' }, data: [{ xAxis: 0, name: '稳定边界' }] },
      }],
    }
  }, [result])

  const timeChart = useMemo(() => {
    if (!result) return {}
    const response = result.result.time_response
    const angleIndices = response.state_labels
      .map((label, index) => label.startsWith('delta_rad:') ? index : -1)
      .filter(index => index >= 0)
    return {
      animationDuration: 400,
      grid: { left: 65, right: 25, top: 38, bottom: 50 },
      tooltip: { trigger: 'axis' },
      legend: { top: 2, textStyle: { fontSize: 10 } },
      xAxis: { type: 'value', name: '时间 / s', nameLocation: 'middle', nameGap: 31 },
      yAxis: { type: 'value', name: '相角偏差 / mrad' },
      series: angleIndices.map(index => ({
        name: response.state_labels[index].split(':')[1],
        type: 'line', symbol: 'none',
        data: response.time_s.map((time, sample) => [time, response.states[sample][index] * 1000]),
      })),
    }
  }, [result])

  const scanChart = useMemo(() => {
    if (!scanResult) return {}
    const scan = scanResult.scan
    const classification = { stable: -1, marginal: 0, unstable: 1 }
    const data = scan.rows.flatMap((row, dIndex) => row.map((point, xIndex) => [
      xIndex,
      dIndex,
      classification[point.stability],
      point.dominant_real_hz,
      point.oscillation_frequency_hz,
    ]))
    return {
      animationDuration: 350,
      grid: { left: 72, right: 115, top: 28, bottom: 58 },
      tooltip: {
        formatter: (params: { data: number[] }) => {
          const [xIndex, dIndex, status, realPart, frequency] = params.data
          const label = status < 0 ? '稳定' : status > 0 ? '失稳' : '临界'
          return `D = ${scan.axes.damping_values_pu[dIndex].toFixed(4)}<br/>X = ${scan.axes.reactance_values_pu[xIndex].toFixed(4)} p.u.<br/>${label}<br/>主导实部 ${realPart.toExponential(3)} Hz<br/>振荡频率 ${frequency.toFixed(4)} Hz`
        },
      },
      xAxis: { type: 'category', name: '目标线路电抗 X / p.u.', nameLocation: 'middle', nameGap: 38, data: scan.axes.reactance_values_pu.map(value => value.toFixed(3)), axisLabel: { interval: Math.max(0, Math.floor(scan.axes.reactance_values_pu.length / 7) - 1) } },
      yAxis: { type: 'category', name: 'VSM 阻尼 D / p.u.', data: scan.axes.damping_values_pu.map(value => value.toFixed(3)), axisLabel: { interval: Math.max(0, Math.floor(scan.axes.damping_values_pu.length / 7) - 1) } },
      visualMap: {
        type: 'piecewise', right: 8, top: 45, dimension: 2,
        pieces: [
          { value: -1, label: '稳定', color: '#62a99b' },
          { value: 0, label: '临界', color: '#e2a33f' },
          { value: 1, label: '失稳', color: '#cc6262' },
        ],
      },
      series: [{ type: 'heatmap', data, emphasis: { itemStyle: { borderColor: '#1d313b', borderWidth: 1 } } }],
    }
  }, [scanResult])

  const statusClass = result?.result.stability === 'stable'
    ? 'good'
    : result?.result.stability === 'marginal' ? 'warn' : 'bad'
  const responseFrequency = estimateResponseFrequency(result)
  const modalFrequency = result?.result.dominant_mode.oscillation_frequency_hz ?? null
  const frequencyDifference = responseFrequency !== null && modalFrequency !== null
    ? Math.abs(responseFrequency - modalFrequency)
    : null

  if (!topology) return <main><div className="panel loading-state">正在加载独立模型预设……</div></main>

  return <main className="model-main">
    <aside className="panel controls model-controls">
      <div className="panel-title"><Network size={18}/><span>独立模型输入</span></div>
      <label>解析校核预设
        <select value={selectedPreset} onChange={event => choosePreset(event.target.value as ReducedOrderPresetId)}>
          {presets.map(preset => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
        </select>
      </label>
      <div className="case-description">
        <span>{customized ? '当前输入' : '预设性质'}</span>
        <strong>{customized ? '已修改的自定义网络' : '团队定义的解析校核算例'}</strong>
        <p>本页不调用论文 Fig. 8 夹具；所有结论仅适用于下方声明的低频降阶模型。</p>
      </div>
      <div className="compact-fields three">
        <label>时长 / s<input type="number" min="0.1" max="300" step="1" value={simulationTime} onChange={event => setSimulationTime(numeric(event.target.value, 20))}/></label>
        <label>步长 / s<input type="number" min="0.001" max="1" step="0.01" value={timeStep} onChange={event => setTimeStep(numeric(event.target.value, 0.02))}/></label>
        <label>扰动 / mrad<input type="number" min="-100" max="100" step="0.5" value={initialAngleMrad} onChange={event => setInitialAngleMrad(numeric(event.target.value, 1))}/></label>
      </div>
      <button onClick={analyze} disabled={running}><Play size={17} fill="currentColor"/>{running ? '正在建立状态空间…' : '验证拓扑并分析'}</button>
      <div className="button-row">
        <button className="secondary-button" onClick={exportCase}><Save size={16}/>保存案例</button>
        <button className="secondary-button" onClick={() => importRef.current?.click()}><FileUp size={16}/>导入案例</button>
      </div>
      <input ref={importRef} className="hidden-input" type="file" accept="application/json,.json" onChange={importCase}/>
      {result && <button className="secondary-button" onClick={() => downloadJson(`${result.run_id}.json`, result)}><Download size={16}/>导出分析结果</button>}
      {result && <button className="secondary-button" onClick={exportCsv}><Download size={16}/>导出极点与响应 CSV</button>}
      {result && <button className="secondary-button" onClick={openPrintableReport}><FileUp size={16}/>生成打印式报告</button>}
      {error && <p className="error">{error}</p>}
      <p className="scope-note">模型采用平坦电压工作点的 1/X 同步刚度，接地无限大母线并对无动态母线作 Kron 消元；暂不包含无功—电压耦合、内环、限幅与电磁暂态。</p>
    </aside>

    <section className="workspace">
      <div className="panel model-editor">
        <div className="panel-title"><Box size={18}/><span>可编辑网络与控制参数</span><em>NetworkTopology/1.0</em></div>
        <div className="editor-toolbar">
          <div><b>{topology.name}</b><small>{topology.buses.length} 母线 · {topology.lines.length} 线路 · {topology.grid_forming_converters.length} 台 VSM</small></div>
          <div className="inline-actions"><button onClick={addBus}><Plus size={14}/>母线</button><button onClick={addLine}><Plus size={14}/>线路</button><button onClick={addGfm}><Plus size={14}/>VSM</button><button onClick={addInfiniteBus}><Plus size={14}/>电网</button></div>
        </div>
        <div className="network-map">
          {topology.buses.map(bus => {
            const gfm = topology.grid_forming_converters.find(item => item.bus_id === bus.id)
            const grid = topology.infinite_buses.find(item => item.bus_id === bus.id)
            return <div className={`network-bus ${gfm ? 'has-gfm' : ''} ${grid ? 'has-grid' : ''}`} key={bus.id}>
              <span>{gfm ? 'GFM' : grid ? '∞' : 'BUS'}</span><b>{bus.name}</b><small>{bus.id}</small>
            </div>
          })}
          <div className="network-lines">{topology.lines.map(line => <span key={line.id}>{line.from_bus_id} — X={line.reactance_pu} — {line.to_bus_id}</span>)}</div>
        </div>

        <details open><summary>系统基值与参考条件</summary><div className="editable-table">
          <div className="edit-row system-row">
            <label>容量基值 / VA<input type="number" min="1" value={topology.base_values.apparent_power_va} onChange={event => changeTopology(draft => { draft.base_values.apparent_power_va = numeric(event.target.value, draft.base_values.apparent_power_va) })}/></label>
            <label>电压基值 / V<input type="number" min="1" value={topology.base_values.voltage_v} onChange={event => changeTopology(draft => { draft.base_values.voltage_v = numeric(event.target.value, draft.base_values.voltage_v) })}/></label>
            <label>基频 / Hz<input type="number" min="1" value={topology.base_values.frequency_hz} onChange={event => changeTopology(draft => { draft.base_values.frequency_hz = numeric(event.target.value, draft.base_values.frequency_hz) })}/></label>
            <label>参考母线<select value={topology.reference_bus_id} disabled={topology.infinite_buses.length === 0} onChange={event => changeTopology(draft => { draft.reference_bus_id = event.target.value })}>{topology.infinite_buses.map(grid => <option key={grid.id} value={grid.bus_id}>{grid.bus_id}</option>)}</select></label>
          </div>
          {topology.infinite_buses.map((grid, index) => <div className="edit-row grid-row" key={`${grid.id}-${index}`}>
            <label>无限大母线 ID<input value={grid.id} onChange={event => updateInfiniteBus(index, { id: event.target.value })}/></label>
            <label>名称<input value={grid.name} onChange={event => updateInfiniteBus(index, { name: event.target.value })}/></label>
            <label>连接母线<select value={grid.bus_id} onChange={event => updateInfiniteBus(index, { bus_id: event.target.value })}>{topology.buses.filter(bus => bus.id === grid.bus_id || (!topology.grid_forming_converters.some(gfm => gfm.bus_id === bus.id) && !topology.infinite_buses.some((other, otherIndex) => otherIndex !== index && other.bus_id === bus.id))).map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
            <label>电压 / pu<input type="number" min="0.5" max="1.5" step="0.01" value={grid.voltage_magnitude_pu ?? 1} onChange={event => updateInfiniteBus(index, { voltage_magnitude_pu: numeric(event.target.value, 1) })}/></label>
            <button className="icon-button" disabled={topology.infinite_buses.length <= 1} title={topology.infinite_buses.length <= 1 ? '至少保留一个无限大母线' : '删除无限大母线'} onClick={() => removeInfiniteBus(index)}><Trash2 size={15}/></button>
          </div>)}
        </div></details>

        <details open><summary>母线参数</summary><div className="editable-table">
          {topology.buses.map((bus, index) => <div className="edit-row bus-row" key={`${bus.id}-${index}`}>
            <label>ID<input value={bus.id} onChange={event => updateBus(index, { id: event.target.value })}/></label>
            <label>名称<input value={bus.name} onChange={event => updateBus(index, { name: event.target.value })}/></label>
            <label>额定电压 / V<input type="number" value={bus.nominal_voltage_v} onChange={event => updateBus(index, { nominal_voltage_v: numeric(event.target.value, bus.nominal_voltage_v) })}/></label>
            <button className="icon-button" disabled={topology.buses.length <= 2 || (topology.infinite_buses.length === 1 && topology.infinite_buses[0].bus_id === bus.id)} onClick={() => removeBus(index)} title={topology.infinite_buses.length === 1 && topology.infinite_buses[0].bus_id === bus.id ? '至少保留一个无限大母线节点' : '删除母线'}><Trash2 size={15}/></button>
          </div>)}
        </div></details>

        <details open><summary>线路参数</summary><div className="editable-table">
          {topology.lines.map((line, index) => <div className="edit-row line-row" key={`${line.id}-${index}`}>
            <label>ID<input value={line.id} onChange={event => updateLine(index, { id: event.target.value })}/></label>
            <label>首端<select value={line.from_bus_id} onChange={event => updateLine(index, { from_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
            <label>末端<select value={line.to_bus_id} onChange={event => updateLine(index, { to_bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
            <label>R / pu<input type="number" min="0" step="0.01" value={line.resistance_pu} onChange={event => updateLine(index, { resistance_pu: numeric(event.target.value, line.resistance_pu) })}/></label>
            <label>X / pu<input type="number" min="0.0001" step="0.01" value={line.reactance_pu} onChange={event => updateLine(index, { reactance_pu: numeric(event.target.value, line.reactance_pu) })}/></label>
            <button className="icon-button" onClick={() => changeTopology(draft => draft.lines.splice(index, 1))}><Trash2 size={15}/></button>
          </div>)}
        </div></details>

        <details open><summary>VSM 控制参数</summary><div className="editable-table">
          {topology.grid_forming_converters.map((gfm, index) => <div className="edit-row gfm-row" key={`${gfm.id}-${index}`}>
            <label>ID<input value={gfm.id} onChange={event => updateGfm(index, { id: event.target.value })}/></label>
            <label>接入母线<select value={gfm.bus_id} onChange={event => updateGfm(index, { bus_id: event.target.value })}>{topology.buses.map(bus => <option key={bus.id}>{bus.id}</option>)}</select></label>
            <label>惯量 M / s<input type="number" min="0.001" step="0.1" value={gfm.virtual_inertia_s} onChange={event => updateGfm(index, { virtual_inertia_s: numeric(event.target.value, gfm.virtual_inertia_s) })}/></label>
            <label>阻尼 D / pu<input type="number" min="0.0001" step="0.05" value={gfm.damping_coefficient_pu} onChange={event => updateGfm(index, { damping_coefficient_pu: numeric(event.target.value, gfm.damping_coefficient_pu) })}/></label>
            <label>有功测量 Tₚ / s<input type="number" min="0.001" step="0.01" value={gfm.active_power_measurement_time_constant_s} onChange={event => updateGfm(index, { active_power_measurement_time_constant_s: numeric(event.target.value, gfm.active_power_measurement_time_constant_s) })}/></label>
            <button className="icon-button" disabled={topology.grid_forming_converters.length <= 1} onClick={() => changeTopology(draft => draft.grid_forming_converters.splice(index, 1))}><Trash2 size={15}/></button>
          </div>)}
        </div></details>
      </div>

      {result ? <>
        <div className="metrics four">
          <article className={`metric ${statusClass}`}>{result.result.stability === 'stable' ? <CircleCheck/> : <ShieldAlert/>}<div><small>闭环极点分类</small><strong>{stabilityText[result.result.stability]}</strong><p>容差 {result.result.stability_tolerance_per_s.toExponential(1)} s⁻¹</p></div></article>
          <article className="metric neutral"><Activity/><div><small>主导极点实部</small><strong>{result.result.dominant_mode.real_hz.toFixed(6)} Hz</strong><p>{result.result.dominant_mode.real_per_s.toFixed(6)} s⁻¹</p></div></article>
          <article className="metric neutral"><Gauge/><div><small>主导振荡频率</small><strong>{result.result.dominant_mode.oscillation_frequency_hz.toFixed(6)} Hz</strong><p>由极点虚部换算</p></div></article>
          <article className="metric neutral"><Network/><div><small>同步刚度矩阵</small><strong>{result.result.synchronous_stiffness_matrix.length} × {result.result.synchronous_stiffness_matrix.length}</strong><p>Kron 消元后</p></div></article>
        </div>
        <div className="panel evidence-strip reduced-evidence">
          <div><small>输入契约</small><b>{result.input_validation.network_contract} · {result.input_validation.status}</b></div>
          <div><small>极点—响应频率自检</small><b>{responseFrequency === null ? '响应周期不足，无法估计' : `${responseFrequency.toFixed(6)} Hz · 差 ${frequencyDifference?.toExponential(2)} Hz`}</b></div>
          <div><small>计算边界</small><b>降阶闭环极点，不评价论文定理</b></div>
        </div>
        <div className="chart-grid">
          <div className="panel chart-card"><div className="panel-title"><Gauge size={18}/><span>闭环极点分布</span><em>虚轴右侧为失稳</em></div><ReactEChartsCore echarts={echarts} option={poleChart} style={{height: 320}}/></div>
          <div className="panel chart-card"><div className="panel-title"><Activity size={18}/><span>线性自由响应</span><em>初始相角扰动，不是大扰动仿真</em></div><ReactEChartsCore echarts={echarts} option={timeChart} style={{height: 320}}/></div>
        </div>
        <div className="panel scan-panel">
          <div className="panel-title"><Network size={18}/><span>D–X 参数平面</span><em>逐点重建状态矩阵，不做显示层插值</em></div>
          <div className="scan-toolbar">
            <label>目标 VSM<select value={scanTargetVsmId} onChange={event => setScanTargetVsmId(event.target.value)}>{topology.grid_forming_converters.map(gfm => <option key={gfm.id}>{gfm.id}</option>)}</select></label>
            <label>目标线路<select value={scanTargetLineId} onChange={event => setScanTargetLineId(event.target.value)}>{topology.lines.map(line => <option key={line.id}>{line.id}</option>)}</select></label>
            <label>D 最小<input type="number" min="0.0001" step="0.05" value={scanDMin} onChange={event => setScanDMin(numeric(event.target.value, 0.05))}/></label>
            <label>D 最大<input type="number" min="0.0001" step="1" value={scanDMax} onChange={event => setScanDMax(numeric(event.target.value, 70))}/></label>
            <label>X 最小 / pu<input type="number" min="0.0001" step="0.02" value={scanXMin} onChange={event => setScanXMin(numeric(event.target.value, 0.08))}/></label>
            <label>X 最大 / pu<input type="number" min="0.0001" step="0.02" value={scanXMax} onChange={event => setScanXMax(numeric(event.target.value, 0.6))}/></label>
            <label>每轴点数<input type="number" min="2" max="50" step="1" value={scanAxisCount} onChange={event => setScanAxisCount(numeric(event.target.value, 21))}/></label>
            <button onClick={runParameterScan} disabled={scanning}>{scanning ? '扫描中…' : '重算参数平面'}</button>
            {scanResult && <button className="outline-button" onClick={exportScanCsv}><Download size={14}/>导出 CSV</button>}
          </div>
          {scanResult ? <>
            <div className="scan-summary">
              <span>总点数 <b>{scanResult.scan.point_count}</b></span>
              <span className="stable-count">稳定 <b>{scanResult.scan.stability_counts.stable}</b></span>
              <span className="marginal-count">临界 <b>{scanResult.scan.stability_counts.marginal}</b></span>
              <span className="unstable-count">失稳 <b>{scanResult.scan.stability_counts.unstable}</b></span>
              <span>目标 <b>{scanResult.scan.target_vsm_id} × {scanResult.scan.target_line_id}</b></span>
            </div>
            <ReactEChartsCore echarts={echarts} option={scanChart} style={{height: 430}}/>
            <p className="scan-boundary">{scanResult.model_scope.line_reactance_interpretation} {scanResult.model_scope.statement}</p>
          </> : <div className="scan-empty">设置阻尼和目标线路电抗范围后，可生成稳定、临界与失稳分区。这里的 X 是选定线路的标幺电抗，不自动改称短路比 SCR。</div>}
        </div>
        <div className="panel provenance-card"><div className="panel-title"><ShieldAlert size={18}/><span>模型适用范围与交叉核对</span></div><p>{result.model_scope.statement}</p><div className="assumption-grid">{result.model_scope.assumptions.map(item => <span key={item}>{item}</span>)}</div></div>
      </> : <div className="panel empty-state"><Network size={34}/><h2>编辑网络后运行分析</h2><p>后端先校验实体 ID、连接关系、额定电压、控制参数与接地条件，再构造同步刚度、状态矩阵、闭环极点和线性自由响应。</p></div>}
    </section>
  </main>
}
