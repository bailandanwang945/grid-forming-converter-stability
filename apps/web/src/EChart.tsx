import { CSSProperties, useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption, EChartsType } from 'echarts/core'

type ChartEventHandler = (parameters: unknown) => void

interface EChartProps {
  option: EChartsCoreOption
  style?: CSSProperties
  onEvents?: Record<string, ChartEventHandler>
  group?: string
}

const researchWorkbenchTheme = {
  color: ['#0b7f7a', '#477b9d', '#b17a45', '#ad563e', '#6f7b87'],
  backgroundColor: 'transparent',
  textStyle: {
    color: '#55616d',
    fontFamily: 'Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif',
  },
  title: { textStyle: { color: '#202a35', fontWeight: 600 } },
  legend: { textStyle: { color: '#65717d' } },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#b8c2cc' } },
    axisTick: { lineStyle: { color: '#b8c2cc' } },
    axisLabel: { color: '#65717d' },
    splitLine: { lineStyle: { color: ['rgba(83,99,115,.10)'] } },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#b8c2cc' } },
    axisTick: { lineStyle: { color: '#b8c2cc' } },
    axisLabel: { color: '#65717d' },
    splitLine: { lineStyle: { color: ['rgba(83,99,115,.10)'], type: 'dashed' } },
  },
  logAxis: {
    axisLine: { lineStyle: { color: '#b8c2cc' } },
    axisTick: { lineStyle: { color: '#b8c2cc' } },
    axisLabel: { color: '#65717d' },
    splitLine: { lineStyle: { color: ['rgba(83,99,115,.10)'], type: 'dashed' } },
  },
  tooltip: {
    backgroundColor: 'rgba(255,255,255,.98)',
    borderColor: '#cbd5df',
    borderWidth: 1,
    textStyle: { color: '#26323d', fontSize: 11 },
    extraCssText: 'box-shadow:0 10px 28px rgba(22,35,48,.14);border-radius:8px;',
  },
}

export default function EChart({ option, style, onEvents, group }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsType | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const chart = echarts.init(container, researchWorkbenchTheme)
    if (group) {
      chart.group = group
      echarts.connect(group)
    }
    chartRef.current = chart
    const resize = () => chart.resize()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    observer?.observe(container)
    window.addEventListener('resize', resize)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', resize)
      chart.dispose()
      chartRef.current = null
    }
  }, [group])

  useEffect(() => {
    chartRef.current?.setOption(option, { notMerge: true })
  }, [option])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart || !onEvents) return
    for (const [eventName, handler] of Object.entries(onEvents)) chart.on(eventName, handler)
    return () => {
      for (const [eventName, handler] of Object.entries(onEvents)) chart.off(eventName, handler)
    }
  }, [onEvents])

  return <div ref={containerRef} style={style}/>
}
