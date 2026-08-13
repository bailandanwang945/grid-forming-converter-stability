import { CSSProperties, useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption, EChartsType } from 'echarts/core'

type ChartEventHandler = (parameters: unknown) => void

interface EChartProps {
  option: EChartsCoreOption
  style?: CSSProperties
  onEvents?: Record<string, ChartEventHandler>
}

const inkPaperTheme = {
  color: ['#667d7d', '#96745c', '#59635f', '#9b6654', '#a4aaa4'],
  backgroundColor: 'transparent',
  textStyle: {
    color: '#59635f',
    fontFamily: 'Inter, "Noto Sans SC", "Microsoft YaHei", sans-serif',
  },
  title: { textStyle: { color: '#29312f', fontWeight: 500 } },
  legend: { textStyle: { color: '#69716d' } },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#aeb2ab' } },
    axisTick: { lineStyle: { color: '#aeb2ab' } },
    axisLabel: { color: '#707771' },
    splitLine: { lineStyle: { color: ['rgba(55,67,63,.09)'] } },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#aeb2ab' } },
    axisTick: { lineStyle: { color: '#aeb2ab' } },
    axisLabel: { color: '#707771' },
    splitLine: { lineStyle: { color: ['rgba(55,67,63,.09)'] } },
  },
  logAxis: {
    axisLine: { lineStyle: { color: '#aeb2ab' } },
    axisTick: { lineStyle: { color: '#aeb2ab' } },
    axisLabel: { color: '#707771' },
    splitLine: { lineStyle: { color: ['rgba(55,67,63,.09)'] } },
  },
  tooltip: {
    backgroundColor: 'rgba(250,248,242,.96)',
    borderColor: 'rgba(55,67,63,.22)',
    textStyle: { color: '#29312f' },
  },
}

export default function EChart({ option, style, onEvents }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsType | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const chart = echarts.init(container, inkPaperTheme)
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
  }, [])

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
