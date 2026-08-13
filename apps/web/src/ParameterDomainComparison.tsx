import { useEffect, useMemo, useState } from 'react'
import * as echarts from 'echarts/core'
import { HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { BookOpenCheck, Download, Grid3X3, ShieldCheck } from 'lucide-react'
import {
  Fig8DomainClassification,
  Fig8DomainComparison,
  Fig8DomainPoint,
  getFig8DomainComparison,
} from './api'
import EChart from './EChart'

echarts.use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

const classificationMeta: Record<Fig8DomainClassification, {
  index: number
  label: string
  color: string
}> = {
  'criterion-covered-stable': { index: 0, label: '判据覆盖且参考稳定', color: '#657f77' },
  'stable-not-covered': { index: 1, label: '参考稳定但判据未覆盖', color: '#a88a68' },
  'unstable-not-covered': { index: 2, label: '参考失稳且判据未覆盖', color: '#9b6654' },
  'numerical-pending': { index: 3, label: '数值待定', color: '#8e9690' },
  'consistency-violation': { index: 4, label: '一致性违例', color: '#756b67' },
}

function downloadText(filename: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function comparisonCsv(result: Fig8DomainComparison) {
  const header = [
    'kappa', 'SCR', 'D', 'maximum_real_pole_Hz',
    'dominant_oscillation_frequency_Hz', 'closed_loop_reference',
    'sampled_criterion_status', 'classification',
    'uncovered_frequency_count', 'indeterminate_frequency_count',
  ]
  const rows = result.rows.map(point => [
    point.impedance_scale_kappa,
    point.scr,
    point.damping_d,
    point.maximum_real_pole_hz,
    point.dominant_oscillation_frequency_hz,
    point.closed_loop_reference,
    point.sampled_criterion_status,
    point.classification,
    point.uncovered_frequency_count,
    point.indeterminate_frequency_count,
  ].join(','))
  return [header.join(','), ...rows].join('\n')
}

export default function ParameterDomainComparison() {
  const [result, setResult] = useState<Fig8DomainComparison | null>(null)
  const [selected, setSelected] = useState<Fig8DomainPoint | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getFig8DomainComparison()
      .then(value => {
        setResult(value)
        setSelected(value.rows.find(point =>
          point.impedance_scale_kappa === 1 && point.damping_d === 0.05,
        ) ?? value.rows[0])
      })
      .catch(reason => setError(reason instanceof Error ? reason.message : '同域对照载入失败'))
  }, [])

  const chart = useMemo(() => {
    if (!result) return {}
    const xLabels = result.axes.impedance_scale_kappa.map((kappa, index) =>
      `κ=${kappa.toFixed(1)}\nSCR=${result.axes.scr_by_kappa[index].toFixed(3)}`,
    )
    const dampingValues = result.axes.damping_d
    const data = result.rows.map(point => [
      result.axes.impedance_scale_kappa.indexOf(point.impedance_scale_kappa),
      dampingValues.findIndex(value => Math.abs(value - point.damping_d) < 1e-12),
      classificationMeta[point.classification].index,
      point.maximum_real_pole_hz,
      point.dominant_oscillation_frequency_hz,
      point.uncovered_frequency_count,
    ])
    return {
      animationDuration: 350,
      grid: { left: 66, right: 24, top: 32, bottom: 78 },
      tooltip: {
        position: 'top',
        formatter: (params: { dataIndex: number }) => {
          const point = result.rows[params.dataIndex]
          return [
            `<b>${classificationMeta[point.classification].label}</b>`,
            `κ=${point.impedance_scale_kappa.toFixed(2)}，SCR=${point.scr.toFixed(4)}，D=${point.damping_d.toFixed(3)}`,
            `主导极点实部 ${point.maximum_real_pole_hz >= 0 ? '+' : ''}${point.maximum_real_pole_hz.toFixed(6)} Hz`,
            `主导振荡频率 ${point.dominant_oscillation_frequency_hz.toFixed(6)} Hz`,
            `未覆盖频点 ${point.uncovered_frequency_count}`,
          ].join('<br/>')
        },
      },
      xAxis: {
        type: 'category',
        data: xLabels,
        axisLabel: { interval: 0, fontSize: 9, lineHeight: 13 },
        name: '线路阻抗缩放 κ / 对应 SCR',
        nameLocation: 'middle',
        nameGap: 54,
      },
      yAxis: {
        type: 'category',
        data: dampingValues.map(value => value.toFixed(3)),
        name: 'VSM 阻尼 D',
        nameLocation: 'middle',
        nameGap: 43,
      },
      visualMap: {
        type: 'piecewise',
        show: false,
        dimension: 2,
        pieces: Object.entries(classificationMeta).map(([, value]) => ({
          value: value.index,
          color: value.color,
        })),
      },
      series: [{
        type: 'heatmap',
        data,
        itemStyle: { borderColor: '#fff', borderWidth: 2, borderRadius: 3 },
        emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,.28)' } },
      }],
    }
  }, [result])

  if (error) return <main className="single-workspace"><div className="panel empty-state"><h2>同域对照载入失败</h2><p>{error}</p></div></main>
  if (!result) return <main className="single-workspace"><div className="panel loading-state">正在载入已核验的同域研究结果……</div></main>
  const counts = result.summary.classificationCounts

  return <main className="single-workspace comparison-workspace">
    <section className="workspace">
      <div className="panel comparison-intro">
        <div className="panel-title"><Grid3X3 size={18}/><span>同一模型、同一参数域的稳定性对照</span><em>作者 Fig. 8 模型 · {result.summary.parameterPointCount} 个参数点</em></div>
        <p>每个 D–SCR 参数点同时计算闭环特征根参考和有限频率网格充分判据。绿色区域是判据能够确认且特征根参考稳定的部分；黄色区域虽参考稳定，却没有被该充分条件覆盖，它反映的是判据保守性，而不是系统失稳。</p>
        <div className="comparison-actions">
          <button onClick={() => downloadText('fig8-domain-comparison.csv', comparisonCsv(result), 'text/csv;charset=utf-8')}><Download size={15}/>导出参数域 CSV</button>
          <button onClick={() => window.open('/api/reports/fig8-domain', '_blank', 'noopener,noreferrer')}><BookOpenCheck size={15}/>打开可打印报告</button>
        </div>
      </div>

      <div className="metrics four">
        <article className="metric good"><ShieldCheck/><div><small>判据覆盖且参考稳定</small><strong>{counts.criterionCoveredStable} 点</strong><p>有限网格覆盖区域全部落在参考稳定区内</p></div></article>
        <article className="metric warn"><Grid3X3/><div><small>参考稳定但判据未覆盖</small><strong>{counts.stableNotCovered} 点</strong><p>用于量化所考察范围内的判据保守性</p></div></article>
        <article className="metric bad"><Grid3X3/><div><small>参考失稳且判据未覆盖</small><strong>{counts.unstableNotCovered} 点</strong><p>充分判据没有给出错误的稳定确认</p></div></article>
        <article className="metric neutral"><BookOpenCheck/><div><small>数值待定 / 一致性违例</small><strong>{counts.numericalPending} / {counts.consistencyViolation}</strong><p>待定点不强行归入稳定或失稳</p></div></article>
      </div>

      <div className="panel domain-chart-card">
        <div className="panel-title"><Grid3X3 size={18}/><span>D–SCR 参数域分类图</span><em>单击色块查看该参数点</em></div>
        <div className="domain-legend">
          {Object.entries(classificationMeta).map(([key, meta]) => <span key={key}><i style={{background: meta.color}}/>{meta.label}</span>)}
        </div>
        <EChart
          option={chart}
          style={{height: 500}}
          onEvents={{click: (parameters: unknown) => {
            const { dataIndex } = parameters as { dataIndex: number }
            setSelected(result.rows[dataIndex])
          }}}
        />
      </div>

      {selected && <div className="panel selected-point">
        <div className="panel-title"><ShieldCheck size={18}/><span>所选参数点</span><em>{classificationMeta[selected.classification].label}</em></div>
        <div className="selected-point-grid">
          <div><small>参数</small><b>κ={selected.impedance_scale_kappa.toFixed(2)} · SCR={selected.scr.toFixed(4)} · D={selected.damping_d.toFixed(3)}</b></div>
          <div><small>闭环主导极点</small><b>{selected.maximum_real_pole_hz >= 0 ? '+' : ''}{selected.maximum_real_pole_hz.toFixed(6)} ± j{selected.dominant_oscillation_frequency_hz.toFixed(6)} Hz</b></div>
          <div><small>有限网格判据</small><b>{selected.uncovered_frequency_count} 个未覆盖频点 · {selected.indeterminate_frequency_count} 个待定频点</b></div>
          <div><small>频率筛查计数</small><b>增益 {selected.gain_pass_count}/{selected.gain_fail_count} · 相位 {selected.phase_pass_count}/{selected.phase_fail_count}</b></div>
        </div>
      </div>}

      <div className="panel provenance-card">
        <div className="panel-title"><BookOpenCheck size={18}/><span>证据来源与表述边界</span></div>
        <p>{result.provenance.claim_boundary_zh} {result.provenance.interpretation_zh} {result.provenance.closed_loop_boundary_zh}</p>
        <dl>
          <div><dt>参数点 / 每点频率样本</dt><dd>{result.summary.parameterPointCount} / {result.summary.frequencyPointCountPerParameterPoint}</dd></div>
          <div><dt>SCR 范围</dt><dd>{result.summary.scrMinimum.toFixed(4)}–{result.summary.scrMaximum.toFixed(4)}</dd></div>
          <div><dt>锚点最大响应误差</dt><dd>{Math.max(result.summary.anchorEvidence.damping005ConverterMaxAbsError, result.summary.anchorEvidence.damping05ConverterMaxAbsError).toExponential(2)}</dd></div>
          <div><dt>便携运行方式</dt><dd>只读加载冻结证据，无需 MATLAB</dd></div>
        </dl>
      </div>
    </section>
  </main>
}
