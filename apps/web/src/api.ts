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

export type Fig8DomainClassification =
  | 'criterion-covered-stable'
  | 'stable-not-covered'
  | 'unstable-not-covered'
  | 'numerical-pending'
  | 'consistency-violation'

export type Fig8DomainPoint = {
  impedance_scale_kappa: number
  scr: number
  damping_d: number
  maximum_real_pole_hz: number
  dominant_oscillation_frequency_hz: number
  closed_loop_reference: 'stable' | 'marginal' | 'unstable'
  sampled_criterion_status: string
  classification: Fig8DomainClassification
  gain_pass_count: number
  gain_fail_count: number
  gain_indeterminate_count: number
  phase_pass_count: number
  phase_fail_count: number
  phase_indeterminate_count: number
  uncovered_frequency_count: number
  indeterminate_frequency_count: number
}

export type Fig8DomainComparison = {
  status: 'completed'
  analysis_mode: string
  axes: {
    impedance_scale_kappa: number[]
    scr_by_kappa: number[]
    damping_d: number[]
    row_axis: string
    column_axis: string
  }
  summary: {
    schemaVersion: string
    method: string
    parameterPointCount: number
    frequencyPointCountPerParameterPoint: number
    frequencyMinimumHz: number
    frequencyMaximumHz: number
    phaseClassifierAngles: number
    scrMinimum: number
    scrMaximum: number
    criterionCoveredSubsetOfReferenceStable: boolean
    classificationCounts: {
      criterionCoveredStable: number
      stableNotCovered: number
      unstableNotCovered: number
      numericalPending: number
      consistencyViolation: number
    }
    anchorEvidence: Record<string, number>
  }
  rows: Fig8DomainPoint[]
  provenance: {
    source_kind: string
    generator: string
    source_workbook: string
    portable_behavior: string
    claim_boundary: string
    interpretation: string
    closed_loop_boundary: string
    claim_boundary_zh: string
    interpretation_zh: string
    closed_loop_boundary_zh: string
  }
}

export async function getFig8DomainComparison(): Promise<Fig8DomainComparison> {
  const response = await fetch('/api/comparison/fig8-domain')
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `同域对照服务返回 ${response.status}`)
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
  parameter_set_id?: string | null
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

export type AverageDQParameters = {
  schema_version: '1.0'
  id: string
  converter_id: string
  frame_convention_id: 'power-invariant-park-q-lag-v1'
  converter_side_resistance_pu: number
  converter_side_reactance_pu: number
  filter_capacitor_susceptance_pu: number
  grid_side_resistance_pu: number
  grid_side_reactance_pu: number
  modulation_time_constant_s: number
  reactive_power_measurement_time_constant_s: number
  reactive_power_voltage_droop_pu: number
  voltage_proportional_gain_pu: number
  voltage_integral_gain_per_s: number
  current_proportional_gain_pu: number
  current_integral_gain_per_s: number
  virtual_resistance_pu: number
  virtual_reactance_pu: number
  diagnostic_current_limit_pu: number
  diagnostic_internal_voltage_limit_pu: number
}

export type AverageDQPreset = {
  id: 'average-dq-smib-verification'
  name: string
  description: string
  expected_stability: 'stable'
  topology: NetworkTopology
  parameters: AverageDQParameters
  provenance: Record<string, unknown>
}

export type AverageDQResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  input_topology: NetworkTopology
  input_parameters: AverageDQParameters
  operating_point: {
    state_labels: string[]
    state: number[]
    grid_voltage_global_pu: number[]
    pcc_voltage_local_pu: number[]
    pcc_voltage_global_pu: number[]
    algebraic_residual: number[]
    closed_rhs_residual_inf: number
    device_rhs_residual_inf: number
    active_power_balance_residual_pu: number
    converter_current_magnitude_pu: number
    grid_current_magnitude_pu: number
    internal_voltage_magnitude_pu: number
  }
  result: {
    stability: 'stable' | 'marginal' | 'unstable'
    stability_tolerance_per_s: number
    closed_state_matrix: number[][]
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
    }
    port_interconnection_max_abs_error: number
    quasisteady_reduction_comparison: {
      synchronizing_stiffness_pu_per_rad: number
      reduced_state_matrix: number[][]
      reduced_poles: Array<{
        real_per_s: number
        imag_per_s: number
        real_hz: number
        imag_hz: number
      }>
      full_dominant_pole: {
        real_per_s: number
        imag_per_s: number
        real_hz: number
        imag_hz: number
      }
      reduced_dominant_pole: {
        real_per_s: number
        imag_per_s: number
        real_hz: number
        imag_hz: number
      }
      matched_full_pole: {
        real_per_s: number
        imag_per_s: number
        real_hz: number
        imag_hz: number
      }
      oscillation_frequency_relative_error: number | null
      real_part_relative_error: number | null
      decay_rate_relative_error: number | null
      matching_method: string
      interpretation: string
    }
    port_admittance: {
      current_direction: string
      voltage_frame: string
      frequencies_hz: number[]
      matrices: Array<Array<Array<{ real: number; imag: number }>>>
    }
    time_response: {
      response_kind: string
      time_s: number[]
      state_labels: string[]
      initial_state: number[]
      nonlinear_states: number[][]
      linear_states: number[][]
    }
  }
  model_scope: {
    claim_level: string
    statement: string
    retained_dynamics: string[]
    excluded_dynamics: string[]
  }
  provenance: Record<string, unknown>
}

export async function getAverageDQPreset(): Promise<AverageDQPreset> {
  const response = await fetch('/api/average-dq/presets')
  if (!response.ok) throw new Error(`平均值 dq 预设服务返回 ${response.status}`)
  const payload = await response.json()
  return payload.presets[0]
}

export type AverageDQAnalysisInput = {
  preset_id?: 'average-dq-smib-verification'
  topology?: NetworkTopology
  parameters?: AverageDQParameters
  simulation_time_s: number
  time_step_s: number
  initial_angle_perturbation_rad: number
  frequency_values_hz: number[]
}

export type AverageDQScanInput = {
  preset_id?: 'average-dq-smib-verification'
  topology?: NetworkTopology
  parameters?: AverageDQParameters
  damping_values_pu: number[]
  reactance_values_pu: number[]
}

export type AverageDQScanResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  input_topology: NetworkTopology
  input_parameters: AverageDQParameters
  result: {
    topology_id: string
    parameter_set_id: string
    axes: {
      damping_values_pu: number[]
      reactance_values_pu: number[]
      row_axis: string
      column_axis: string
    }
    point_count: number
    counts: {
      valid: number
      invalid: number
      agreement: number
      disagreement: number
      full: { stable: number; marginal: number; unstable: number }
      reduced: { stable: number; marginal: number; unstable: number }
    }
    rows: Array<Array<{
      damping_coefficient_pu: number
      line_reactance_pu: number
      valid: boolean
      full_stability: 'stable' | 'marginal' | 'unstable' | null
      reduced_stability: 'stable' | 'marginal' | 'unstable' | null
      stability_agreement: boolean | null
      full_dominant_real_per_s: number | null
      full_oscillation_frequency_hz: number | null
      reduced_dominant_real_per_s: number | null
      reduced_oscillation_frequency_hz: number | null
      matched_full_mode_real_per_s: number | null
      matched_full_mode_frequency_hz: number | null
      synchronizing_stiffness_pu_per_rad: number | null
      frequency_relative_error: number | null
      real_part_relative_error: number | null
      matching_method: string | null
      full_dominant_participation: Array<{
        state: string
        normalized_participation: number
      }> | null
      error: string | null
    }>>
  }
  model_scope: {
    statement: string
    interpretation: string
    paper_theorem_evaluated: boolean
    physical_validation: boolean
  }
  provenance: Record<string, unknown>
}

export type AverageDQAblationPresetId = 'average-dq-hierarchy-disagreement-ablation-v1'

export type AverageDQPole = {
  real_per_s: number
  imag_per_s: number
  real_hz: number
  imag_hz: number
}

export type AverageDQModeTracking = {
  pole: AverageDQPole
  reference_pole: AverageDQPole
  status: 'matched' | 'pending'
  reason: string
  path_label: string
  cumulative_tracking_steps: number
  minimum_step_right_mac: number
  minimum_step_left_mac: number
  minimum_step_combined_mac: number
  maximum_step_normalized_eigenvalue_distance: number
  minimum_step_confidence: number
  maximum_step_second_candidate_confidence: number
  minimum_step_local_candidate_margin: number
  maximum_eigenvalue_condition_number: number
  maximum_right_eigenpair_residual: number
  maximum_left_eigenpair_residual: number
  thresholds: {
    minimum_individual_mac: number
    maximum_normalized_eigenvalue_distance: number
    maximum_eigenvalue_condition_number: number
    maximum_eigenpair_residual: number
    minimum_local_candidate_margin: number
  }
}

export type AverageDQAblationPoint = {
  scenario_id: string
  factors: Record<string, number>
  damping_coefficient_pu: number
  line_reactance_pu: number
  stability: 'stable' | 'marginal' | 'unstable'
  rightmost_pole: AverageDQPole
  poles: AverageDQPole[]
  extra_mode: AverageDQModeTracking
  synchronous_mode: AverageDQModeTracking
  extra_group_participation: Record<string, number>
  synchronous_group_participation: Record<string, number>
  reduced_poles: AverageDQPole[]
  reduced_dominant_pole: AverageDQPole
  synchronizing_stiffness_pu_per_rad: number
  synchronous_frequency_relative_error: number | null
  synchronous_decay_relative_error: number | null
  residuals: {
    algebraic_inf: number
    closed_rhs_inf: number
    device_rhs_inf: number
    active_power_balance_abs_pu: number
  }
}

export type AverageDQAblationResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  preset_id: AverageDQAblationPresetId
  fixed_anchor: {
    damping_coefficient_pu: number
    external_line_reactance_pu: number
    state_definition: string
  }
  result: {
    point_count: number
    summary: {
      stability_counts: Record<'stable' | 'marginal' | 'unstable', number>
      extra_mode_tracking_counts: Record<'matched' | 'pending', number>
      synchronous_mode_tracking_counts: Record<'matched' | 'pending', number>
    }
    baseline_extra_mode: AverageDQPole
    baseline_synchronous_mode: AverageDQPole
    state_scaling: Record<string, number>
    state_scaling_scope: string
    points: AverageDQAblationPoint[]
  }
  model_scope: {
    claim_level: string
    statement: string
    tracking_method: string
    tracking_boundary: string
    paper_theorem_evaluated: boolean
    physical_validation: boolean
    causal_identification: boolean
    accepts_arbitrary_state_definition: boolean
  }
  provenance: Record<string, unknown>
}

export type AverageDQBoundaryEstimate = {
  metric: 'extra-mode-real-part' | 'spectral-abscissa'
  status: 'converged' | 'unbracketed' | 'pending' | 'maximum-iterations'
  reason: string
  factor_value: number | null
  initial_interval: number[]
  final_interval: number[] | null
  real_part_per_s: number | null
  iterations: number
}

export type AverageDQBoundaryPath = {
  path_id: string
  factor_name: string
  label_zh: string
  baseline_factor: number
  screening_endpoint_factor: number
  extra_mode_boundary: AverageDQBoundaryEstimate
  overall_stability_boundary: AverageDQBoundaryEstimate
  boundaries_agree: boolean | null
  relative_boundary_difference: number | null
  mode_handoff_observed: boolean
  trial_count: number
}

export type AverageDQBoundaryResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  preset_id: AverageDQAblationPresetId
  result: {
    topology_id: string
    parameter_set_id: string
    fixed_anchor: {
      damping_coefficient_pu: number
      external_line_reactance_pu: number
      state_definition: string
    }
    numerical_contract: {
      factor_midpoint: string
      factor_relative_tolerance: number
      real_part_tolerance_per_s: number
      maximum_iterations: number
      failed_tracking_policy: string
    }
    path_count: number
    converged_extra_mode_boundaries: number
    converged_overall_boundaries: number
    agreeing_boundary_count: number
    paths: AverageDQBoundaryPath[]
    interpretation_boundary: string
  }
  model_scope: {
    claim_level: string
    statement: string
    tracking_boundary: string
    paper_theorem_evaluated: boolean
    physical_validation: boolean
    causal_identification: boolean
    accepts_arbitrary_parameter_paths: boolean
  }
  provenance: Record<string, unknown>
}

type AverageDQAblationInput = {
  preset_id: AverageDQAblationPresetId
}

async function averageDQRequest(path: string, input: AverageDQAnalysisInput | AverageDQScanInput | AverageDQAblationInput) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    const message = Array.isArray(detail?.detail)
      ? detail.detail.map((item: { msg?: string }) => item.msg ?? String(item)).join('；')
      : detail?.detail
    throw new Error(message ?? `平均值 dq 服务返回 ${response.status}`)
  }
  return response
}

export async function runAverageDQAnalysis(input: AverageDQAnalysisInput): Promise<AverageDQResult> {
  return (await averageDQRequest('/api/average-dq/analyze', input)).json()
}

export async function getAverageDQReportHtml(input: AverageDQAnalysisInput): Promise<string> {
  return (await averageDQRequest('/api/reports/average-dq', input)).text()
}

export async function runAverageDQScan(input: AverageDQScanInput): Promise<AverageDQScanResult> {
  return (await averageDQRequest('/api/average-dq/scan', input)).json()
}

export async function runAverageDQAblation(): Promise<AverageDQAblationResult> {
  return (await averageDQRequest('/api/average-dq/ablation', {
    preset_id: 'average-dq-hierarchy-disagreement-ablation-v1',
  })).json()
}

export async function runAverageDQBoundary(): Promise<AverageDQBoundaryResult> {
  return (await averageDQRequest('/api/average-dq/boundary', {
    preset_id: 'average-dq-hierarchy-disagreement-ablation-v1',
  })).json()
}
