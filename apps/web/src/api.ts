export type AnalysisResult = {
  run_id: string
  summary: {
    closed_loop_reference: 'stable' | 'unstable'
    criterion_status: string
    dominant_pole_hz: { real: number; imag: number }
    critical_damping_reference: number
    uncovered_points: number
    frequency_points: number
    theorem_status: string
  }
  frequency_scan: {
    frequencies_hz: number[]
    mixed_margin: number[]
    coverage: string[]
  }
  provenance: { mode: string; paper_case: string; interpretation: string }
}

export async function runAnalysis(damping: number, scr: number): Promise<AnalysisResult> {
  const response = await fetch('/api/analysis/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario_id: 'author-fig8', damping, scr }),
  })
  if (!response.ok) throw new Error(`分析服务返回 ${response.status}`)
  return response.json()
}
