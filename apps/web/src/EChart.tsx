import { CSSProperties, useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption, EChartsType } from 'echarts/core'

type ChartEventHandler = (parameters: unknown) => void

interface EChartProps {
  option: EChartsCoreOption
  style?: CSSProperties
  onEvents?: Record<string, ChartEventHandler>
}

export default function EChart({ option, style, onEvents }: EChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsType | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const chart = echarts.init(container)
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
