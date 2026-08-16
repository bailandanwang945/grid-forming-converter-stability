import { useMemo, useState } from 'react'
import { Activity, BookOpenCheck, Download, FlaskConical, ShieldAlert } from 'lucide-react'
import { Fig8SensitivityResult, getFig8Sensitivity } from './api'
import EChart from './EChart'

function saveJson(result: Fig8SensitivityResult) {
  const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'fig8-sampled-sensitivity.json'
  document.body.appendChild(anchor)
  anchor.click()
  window.setTimeout(() => {
    anchor.remove()
    URL.revokeObjectURL(url)
  }, 5000)
}

export default function Fig8SensitivityPanel() {
  const [result, setResult] = useState<Fig8SensitivityResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const chart = useMemo(() => {
    if (!result) return {}
    const unstable = result.cases.find(value => value.case_id === 'fig8_D_0p05')!
    const stable = result.cases.find(value => value.case_id === 'fig8_D_0p5')!
    return {
      animationDuration: 350,
      grid: { left: 64, right: 26, top: 52, bottom: 54 },
      tooltip: { trigger: 'axis' },
      legend: { top: 5 },
      xAxis: {
        type: 'category', name: '子网格点数', nameLocation: 'middle', nameGap: 36,
        data: unstable.frequency_density.map(row => String(row.requested_point_count)),
      },
      yAxis: { type: 'value', name: '检出的未覆盖点数', minInterval: 1 },
      series: [
        {
          name: 'D=0.05 失稳工况', type: 'line', symbolSize: 8,
          lineStyle: { width: 2.2, color: '#9b6654' }, itemStyle: { color: '#9b6654' },
          data: unstable.frequency_density.map(row => row.uncovered_count),
        },
        {
          name: 'D=0.5 稳定工况', type: 'line', symbolSize: 7,
          lineStyle: { width: 1.8, color: '#667d7d' }, itemStyle: { color: '#667d7d' },
          data: stable.frequency_density.map(row => row.uncovered_count),
        },
      ],
    }
  }, [result])

  async function run() {
    setRunning(true)
    setError('')
    try {
      setResult(await getFig8Sensitivity())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '敏感性核查失败')
    } finally {
      setRunning(false)
    }
  }

  const unstable = result?.cases.find(value => value.case_id === 'fig8_D_0p05')
  const ninePoint = unstable?.frequency_density.find(row => row.requested_point_count === 9)
  const maximumToleranceMismatch = result ? Math.max(...result.cases.flatMap(value => value.decision_tolerance.map(row => row.coverage_mismatch_from_default ?? 0))) : null
  const maximumScaleMismatch = result ? Math.max(...result.cases.flatMap(value => value.common_matrix_scale.map(row => row.coverage_mismatch_from_unit_scale ?? 0))) : null

  return <section className="panel sensitivity-panel" data-testid="fig8-sensitivity-panel">
    <div className="sensitivity-heading">
      <div className="panel-title"><FlaskConical size={18}/><span>有限频率网格敏感性核查</span><em>采样密度 · 判定容差 · 矩阵尺度</em></div>
      <div className="inline-actions">
        <button data-testid="fig8-sensitivity-run" onClick={run} disabled={running}>{running ? '正在重算…' : '运行固定敏感性实验'}</button>
        <button data-testid="fig8-sensitivity-export" onClick={() => result && saveJson(result)} disabled={!result}><Download size={14}/>导出 JSON</button>
        <button data-testid="fig8-sensitivity-report" onClick={() => window.open('/api/reports/fig8-sensitivity', '_blank', 'noopener,noreferrer')} disabled={!result}><BookOpenCheck size={14}/>打印式报告</button>
      </div>
    </div>
    {!result ? <div className="sensitivity-intro">
      <Activity size={28}/><p>用同一作者1000点夹具构造多个子网格，并改变判定容差与共同矩阵表示尺度。实验允许出现漏检，用于回答“有限网格结果对数值设置有多敏感”。</p>
    </div> : <>
      <div className="panel evidence-strip" data-testid="fig8-sensitivity-summary">
        <div><small>9点子网格</small><b>{ninePoint?.detects_uncovered_region ? '检出未覆盖带' : '漏检未覆盖带'}</b></div>
        <div><small>容差 10⁻¹²–10⁻⁶</small><b>最大分类变化 {maximumToleranceMismatch} 点</b></div>
        <div><small>共同尺度 10⁻⁹–10⁹</small><b>最大分类变化 {maximumScaleMismatch} 点</b></div>
      </div>
      <div className="sensitivity-layout">
        <div className="sensitivity-chart"><EChart option={chart} style={{ height: 330 }}/></div>
        <div className="sensitivity-finding">
          <ShieldAlert size={22}/>
          <h3>稀疏网格可能给出“未发现反例”</h3>
          <p data-testid="fig8-sensitivity-counterexample">9点子网格没有命中完整网格中的75个未覆盖样点；15点子网格仅命中1点。它说明“采样点均被覆盖”不能推出连续频带均被覆盖。</p>
          <p>本次容差与尺度变化没有改变已采样点分类，只能说明这些固定工况远离所测试的数值判定门，并不证明任意算例同样稳健。</p>
        </div>
      </div>
      <div className="table-scroll">
        <table data-testid="fig8-sensitivity-density-table">
          <thead><tr>{['频率点数', '最大对数步长', '检出未覆盖点', '首个检出频率 / Hz', '末个检出频率 / Hz', '未观察到的1000点未覆盖样点'].map(label => <th key={label}>{label}</th>)}</tr></thead>
          <tbody>{unstable?.frequency_density.map(row => <tr key={row.requested_point_count} data-testid={`fig8-sensitivity-row-${row.requested_point_count}`}>
            <td>{row.requested_point_count}</td>
            <td>{row.maximum_log10_frequency_step?.toFixed(4)}</td>
            <td>{row.uncovered_count}</td>
            <td>{row.first_uncovered_frequency_hz?.toPrecision(6) ?? '未检出'}</td>
            <td>{row.last_uncovered_frequency_hz?.toPrecision(6) ?? '未检出'}</td>
            <td>{row.unobserved_full_grid_uncovered_points}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <p className="scope-note" data-testid="fig8-sensitivity-scope">{result.model_scope.statement} 因而该实验不评价论文连续全频定理，也不改变闭环特征根参考结论。</p>
    </>}
    {error && <p className="error">{error}</p>}
  </section>
}
