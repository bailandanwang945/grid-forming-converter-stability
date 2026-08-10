export type Fig8ScenarioId = 'fig8_D_0p05' | 'fig8_D_0p5'

export type ScreeningCounts = {
  gain: { pass: number; fail: number; indeterminate: number }
  phase: { pass: number; fail: number; indeterminate: number }
  uncovered: number
  indeterminate_coverage: number
}

export type AnalysisResult = {
  run_id: string
  scenario_id: Fig8ScenarioId
  status: 'completed'
  summary: {
    closed_loop_reference: 'stable' | 'unstable'
    criterion_status: string
    dominant_pole_hz: { real: number; imag: number }
    uncovered_points: number
    indeterminate_points: number
    frequency_points: number
    theorem_status: string
    screening_counts: ScreeningCounts
    paper_reported_oscillation_hz: number
    reproduced_dominant_oscillation_hz: number
    frequency_discrepancy_status: 'unresolved'
  }
  frequency_scan: {
    frequencies_hz: number[]
    gain_margin: number[]
    upper_phase_margin: Array<number | null>
    lower_phase_margin: Array<number | null>
    gain_status: string[]
    phase_status: string[]
    coverage: string[]
    active_constraint: string[]
  }
  phase_seed: {
    converter_index_zero_based: number
    converter_frequency_hz: number
    network_index_zero_based: number
    network_frequency_hz: number
    provenance: string
  }
  provenance: {
    mode: string
    paper_case: string
    fixture_id: string
    author_tag: string
    author_commit: string
    source_workbook_sha256: string
    matlab_release_used_to_export_fixture: string
    python_method: string
    interpretation: string
  }
}

export async function runAnalysis(scenarioId: Fig8ScenarioId): Promise<AnalysisResult> {
  const response = await fetch('/api/analysis/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario_id: scenarioId }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `分析服务返回 ${response.status}`)
  }
  return response.json()
}

export type Bus = {
  kind?: 'bus'
  id: string
  name: string
  nominal_voltage_v: number
}

export type ACLine = {
  kind?: 'ac_line'
  id: string
  name: string
  from_bus_id: string
  to_bus_id: string
  resistance_pu: number
  reactance_pu: number
  shunt_susceptance_pu?: number
  thermal_limit_pu?: number | null
}

export type GridFormingConverter = {
  kind?: 'grid_forming_converter'
  id: string
  name: string
  bus_id: string
  rated_apparent_power_va: number
  control_mode: 'virtual_synchronous_machine'
  active_power_setpoint_pu?: number
  reactive_power_setpoint_pu?: number
  voltage_setpoint_pu?: number
  virtual_inertia_s: number
  damping_coefficient_pu: number
  active_power_measurement_time_constant_s: number
}

export type InfiniteBus = {
  kind?: 'infinite_bus'
  id: string
  name: string
  bus_id: string
  voltage_magnitude_pu?: number
  voltage_angle_deg?: number
}

export type StaticLoad = {
  kind?: 'load'
  id: string
  name: string
  bus_id: string
  load_model: string
  active_power_pu: number
  reactive_power_pu: number
}

export type NetworkTopology = {
  schema_version: '1.0'
  id: string
  name: string
  base_values: {
    apparent_power_va: number
    voltage_v: number
    frequency_hz: number
  }
  frame_convention_id: string
  reference_bus_id: string
  buses: Bus[]
  lines: ACLine[]
  grid_forming_converters: GridFormingConverter[]
  infinite_buses: InfiniteBus[]
  loads: StaticLoad[]
}

export type ReducedOrderPresetId =
  | 'reduced-smib-stable'
  | 'reduced-smib-critical'
  | 'reduced-smib-unstable'

export type ReducedOrderPreset = {
  id: ReducedOrderPresetId
  name: string
  description: string
  expected_stability: 'stable' | 'marginal' | 'unstable'
  topology: NetworkTopology
  provenance: Record<string, unknown>
}

export type ReducedOrderPresetsResponse = {
  analysis_mode: string
  separation_notice: string
  claim_level: string
  presets: ReducedOrderPreset[]
}

export type ReducedOrderAnalysisResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  input_validation: {
    status: 'passed'
    network_contract: string
    topology_id: string
    frame_convention_id: string
    reference_bus_id: string
    connected_network: boolean
    core_scope_validation: string
    entity_counts: Record<string, number>
  }
  result: {
    stability: 'stable' | 'marginal' | 'unstable'
    stability_tolerance_per_s: number
    vsm_ids: string[]
    state_labels: string[]
    state_matrix: number[][]
    synchronous_stiffness_matrix: number[][]
    poles: Array<{
      real_per_s: number
      imag_per_s: number
      real_hz: number
      imag_hz: number
    }>
    dominant_mode: {
      real_per_s: number
      imag_per_s: number
      real_hz: number
      imag_hz: number
      oscillation_frequency_hz: number
      damping_ratio: number | null
    }
    time_response: {
      response_kind: string
      time_s: number[]
      state_labels: string[]
      states: number[][]
      initial_state: number[]
    }
  }
  model_scope: {
    claim_level: string
    statement: string
    assumptions: string[]
    excluded_dynamics: string[]
  }
  provenance: Record<string, unknown>
  input_topology: NetworkTopology
}

export type ReducedOrderAnalysisInput = {
  preset_id?: ReducedOrderPresetId
  topology?: NetworkTopology
  simulation_time_s: number
  time_step_s: number
  initial_angle_perturbation_rad: number
}

export async function getReducedOrderPresets(): Promise<ReducedOrderPresetsResponse> {
  const response = await fetch('/api/reduced-order/presets')
  if (!response.ok) throw new Error(`预设服务返回 ${response.status}`)
  return response.json()
}

export async function runReducedOrderAnalysis(input: ReducedOrderAnalysisInput): Promise<ReducedOrderAnalysisResult> {
  const response = await fetch('/api/reduced-order/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    const message = Array.isArray(detail?.detail)
      ? detail.detail.map((item: { msg?: string }) => item.msg ?? String(item)).join('；')
      : detail?.detail
    throw new Error(message ?? `独立模型服务返回 ${response.status}`)
  }
  return response.json()
}

export async function getReducedOrderReportHtml(input: ReducedOrderAnalysisInput): Promise<string> {
  const response = await fetch('/api/reports/reduced-order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `报告服务返回 ${response.status}`)
  }
  return response.text()
}

export type ReducedOrderScanPoint = {
  damping_coefficient_pu: number
  line_reactance_pu: number
  stability: 'stable' | 'marginal' | 'unstable'
  dominant_real_per_s: number
  dominant_real_hz: number
  oscillation_frequency_hz: number
}

export type ReducedOrderScanResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  input_topology: NetworkTopology
  scan: {
    topology_id: string
    target_vsm_id: string
    target_line_id: string
    axes: {
      damping_values_pu: number[]
      reactance_values_pu: number[]
      row_axis: string
      column_axis: string
    }
    point_count: number
    stability_counts: { stable: number; marginal: number; unstable: number }
    rows: ReducedOrderScanPoint[][]
  }
  model_scope: {
    claim_level: string
    parameter_plane: string
    line_reactance_interpretation: string
    statement: string
  }
  provenance: Record<string, unknown>
}

export async function runReducedOrderScan(input: {
  topology: NetworkTopology
  target_vsm_id: string
  target_line_id: string
  damping_values_pu: number[]
  reactance_values_pu: number[]
}): Promise<ReducedOrderScanResult> {
  const response = await fetch('/api/reduced-order/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    const message = Array.isArray(detail?.detail)
      ? detail.detail.map((item: { msg?: string }) => item.msg ?? String(item)).join('；')
      : detail?.detail
    throw new Error(message ?? `参数扫描服务返回 ${response.status}`)
  }
  return response.json()
}
