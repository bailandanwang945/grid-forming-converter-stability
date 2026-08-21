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

export type Fig8SensitivityRow = {
  sample_count: number
  gain_counts: { pass: number; fail: number; indeterminate: number }
  phase_counts: { pass: number; fail: number; indeterminate: number }
  uncovered_count: number
  indeterminate_coverage_count: number
  first_uncovered_frequency_hz: number | null
  last_uncovered_frequency_hz: number | null
  requested_point_count?: number
  maximum_log10_frequency_step?: number
  detects_uncovered_region?: boolean
  observed_full_grid_uncovered_points?: number
  unobserved_full_grid_uncovered_points?: number
  gain_relative_tolerance?: number
  phase_tolerance_rad?: number
  coverage_mismatch_from_default?: number
  common_post_transformation_matrix_scale?: number
  coverage_mismatch_from_unit_scale?: number
}

export type Fig8SensitivityResult = {
  status: 'completed'
  analysis_mode: string
  cases: Array<{
    case_id: Fig8ScenarioId
    damping: number
    closed_loop_reference: 'stable' | 'unstable'
    baseline: {
      frequency_point_count: number
      frequency_minimum_hz: number
      frequency_maximum_hz: number
      uncovered_count: number
      indeterminate_coverage_count: number
      reconstructed_coverage_mismatch_count: number
    }
    frequency_density: Fig8SensitivityRow[]
    decision_tolerance: Fig8SensitivityRow[]
    common_matrix_scale: Fig8SensitivityRow[]
  }>
  summary: {
    baseline_reconstruction_exact: boolean
    common_scale_invariant_on_tested_range: boolean
    stable_case_remains_covered_in_all_tested_settings: boolean
  }
  experiment_contract: {
    frequency_point_counts: number[]
    decision_tolerances: number[]
    common_matrix_scales: number[]
    frequency_sampling_method: string
    randomness: string
    failure_conditions: string[]
  }
  model_scope: {
    claim_level: string
    statement: string
    continuous_frequency_coverage_proved: boolean
    paper_theorem_evaluated: boolean
    physical_model_perturbed: boolean
  }
}

export async function getFig8Sensitivity(): Promise<Fig8SensitivityResult> {
  const response = await fetch('/api/analysis/fig8-sensitivity')
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `敏感性分析服务返回 ${response.status}`)
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

export type AverageDQPortIdentificationPoint = {
  frequency_hz: number
  settling_periods: number
  measurement_periods: number
  samples_per_period: number
  solver_method: string
  identified_admittance_pu: Array<Array<{
    real: number
    imag: number
    magnitude: number
    phase_deg: number
  }>>
  linearized_admittance_pu: Array<Array<{
    real: number
    imag: number
    magnitude: number
    phase_deg: number
  }>>
  magnitude_relative_error: number[][]
  phase_error_deg: number[][]
  voltage_matrix_condition_number: number
  maximum_magnitude_relative_error: number
  maximum_phase_error_deg: number
  maximum_harmonic_residual_ratio: number
  passed: boolean
}

export type AverageDQPortIdentificationResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  preset_id: 'average-dq-smib-verification'
  input_topology: NetworkTopology
  input_parameters: AverageDQParameters
  result: {
    summary: {
      passed: boolean
      frequency_count: number
      maximum_magnitude_relative_error: number
      maximum_phase_error_deg: number
      maximum_harmonic_residual_ratio: number
      maximum_voltage_matrix_condition_number: number
    }
    contract: {
      frequencies_hz: number[]
      source_amplitude_pu: number
      minimum_settling_time_s: number
      measurement_periods: number
      samples_per_period: number
      magnitude_error_limit: number
      phase_error_limit_deg: number
      harmonic_residual_limit: number
      voltage_matrix_condition_limit: number
      frame: string
      current_direction: string
    }
    points: AverageDQPortIdentificationPoint[]
    amplitude_halving_check_at_2hz: {
      baseline_amplitude_pu: number
      halved_amplitude_pu: number
      maximum_element_relative_difference: number
      halved_amplitude_point: AverageDQPortIdentificationPoint
    }
  }
  model_scope: {
    claim_level: string
    physical_validation: boolean
    emt_validation: boolean
    paper_fig8_fixture: boolean
    statement: string
  }
  provenance: Record<string, unknown>
}

export type MathWorksExternalEvidenceResult = {
  run_id: string
  status: 'completed'
  mode: 'frozen-read-only-external-validation-evidence'
  source: {
    provider: string
    release_tag: string
    commit: string
    matlab_release: string
  }
  summary: {
    three_point_vendor_outcomes: string[]
    factorial_stable_point_count: number
    factorial_point_count: number
    vendor_classification_bracket_pu: number[]
    vendor_classification_bracket_width_pu: number
    project_tracking_observed_bracket_pu: number[]
    project_tracking_target_achieved: boolean
  }
  studies: Record<string, unknown>
  artifact_sha256: Record<string, string>
  scope: {
    claim_level: string
    reruns_matlab_or_simulink: boolean
    closed_loop_eigenvalue_boundary: boolean
    continuous_stability_proof: boolean
    physical_hardware_validation: boolean
    paper_sufficient_condition_evaluated: boolean
    statement: string
  }
}

export type MathWorksTeamComparisonPoint = {
  scr: number
  x_by_r: number
  source_resistance_pu: number
  source_reactance_pu: number
  damping_mathworks_pu_per_hz: number
  damping_team_native_pu_per_pu_frequency: number
  external_vendor_outcome: 'Stable' | 'Unstable'
  team_pre_step_stability: 'stable' | 'marginal' | 'unstable'
  team_post_step_stability: 'stable' | 'marginal' | 'unstable'
  team_endpoints_same_class: boolean
  classification_agreement: boolean
  team_pre_step_dominant_mode: { real_per_s: number; oscillation_frequency_hz: number }
  team_post_step_dominant_mode: { real_per_s: number; oscillation_frequency_hz: number }
}

export type MathWorksTeamComparisonResult = {
  run_id: string
  status: 'completed'
  analysis_mode: string
  mapping_contract: {
    base_frequency_hz: number
    damping_mathworks_unit: string
    damping_team_native_unit: string
    damping_conversion: string
    mathworks_model_gain_expression: string
    team_model_equation: string
    source_impedance_definition: string
    x_by_r: number
    pre_step_active_power_pu: number
    post_step_active_power_pu: number
  }
  summary: {
    point_count: number
    classification_agreement_count: number
    classification_disagreement_count: number
    all_team_pre_post_endpoint_classes_equal: boolean
    disagreement_points: Array<Record<string, string | number>>
    interpretation: string
  }
  points: MathWorksTeamComparisonPoint[]
  boundary_comparison: {
    external_vendor_classification_bracket_pu_per_hz: number[]
    team_local_eigenvalue_boundaries: Array<{
      active_power_setpoint_pu: number
      damping_mw_equivalent_pu_per_hz: number
      damping_team_native_pu_per_pu_frequency: number
      spectral_abscissa_per_s: number
    }>
    external_and_team_boundaries_are_same_evidence_type: boolean
    external_lower_minus_team_boundary_pu_per_hz: number[]
    quantitative_transition_reproduced: boolean
  }
  provenance: Record<string, unknown>
  scope: {
    claim_level: string
    external_classifier: string
    team_classifier: string
    same_full_physical_model: boolean
    same_classifier: boolean
    same_controller_inner_loops: boolean
    nonlinear_team_step_completed: boolean
    nonlinear_team_step_study_id: string
    paper_sufficient_condition_evaluated: boolean
    physical_hardware_validation: boolean
    statement: string
  }
}

export type AverageDQAlignedStepSolverResult = {
  method: 'Radau' | 'LSODA'
  outcome: 'converged_within_horizon' | 'bounded_not_converged_within_horizon' | 'departed_declared_diagnostic_range' | 'numerical_failure'
  solver_success: boolean
  event_name: string | null
  event_time_s: number | null
  completed_time_s: number
  sample_count: number
  elapsed_wall_time_s: number
  maximum_frequency_deviation_hz: number | null
  active_power_settling_time_s: number | null
  frequency_settling_time_s: number | null
  final_metrics: {
    frequency_error_pu: number
    active_power_error_pu: number
    angle_error_rad: number
    grid_current_error_pu: number
  } | null
  time_s: number[]
  states: number[][]
}

export type AverageDQAlignedStepResult = {
  schema_version: string
  study_id: string
  status: 'completed'
  research_question: string
  contract: {
    scr: number
    damping_mathworks_pu_per_hz: number[]
    active_power_step_pu: number[]
    duration_s: number
    sample_step_s: number
    solver_methods: string[]
  }
  points: Array<{
    scr: number
    damping_mathworks_pu_per_hz: number
    damping_team_native_pu_per_pu_frequency: number
    external_vendor_outcome: 'Stable' | 'Unstable'
    team_pre_step_local_stability: 'stable' | 'marginal' | 'unstable'
    team_post_step_local_stability: 'stable' | 'marginal' | 'unstable'
    solver_agreement: boolean
    study_outcome: string
    solver_results: AverageDQAlignedStepSolverResult[]
  }>
  summary: {
    point_count: number
    solver_agreement_count: number
    disagreement_coordinate_outcome: string
    interpretation: string
  }
  scope: {
    same_full_model_as_mathworks: boolean
    emt_validation: boolean
    hardware_validation: boolean
    diagnostic_exit_is_physical_instability: boolean
    saturation_and_protection_modelled: boolean
  }
}

type SiennaDelayPole = {
  real_per_s: number
  imag_per_s: number
  frequency_hz: number
}

type SiennaDelayTracking = {
  status: 'anchor' | 'matched' | 'pending'
  reason: string
  right_mac?: number
  left_mac?: number
  combined_mac?: number
  normalized_eigenvalue_distance?: number
  relative_candidate_margin?: number
  condition_number?: number
  right_eigenpair_residual?: number
  left_eigenpair_residual?: number
}

export type SiennaTest08AuditResult = {
  schema_version: string
  benchmark_id: string
  status: 'passed' | 'failed'
  source_contract: {
    power_simulations_dynamics_version: string
    power_simulations_dynamics_commit: string
    power_system_case_builder_version: string
    power_system_case_builder_commit: string
    power_systems_test_data_version: string
    test_case: string
    license: string
  }
  model_contract: {
    state_count: number
    state_labels: string[]
    system_frequency_hz_used_by_frozen_result: number
    legacy_raw_header_frequency_hz: number
    system_base_power_mva: number
    device_base_power_mva: number
    network_reactance_pu_system_base: number
    static_terminal_active_power_pu_device_base: number
    initialized_internal_active_power_reference_pu: number
  }
  results: {
    initial_residual_inf: number
    terminal_voltage_error: number
    matched_eigenvalue_max_error_per_s: number
    matched_eigenvalue_l2_error_per_s: number
    computed_stable: boolean
    computed_eigenvalues: Array<{ real_per_s: number; imag_per_s: number; oscillation_frequency_hz: number }>
    upstream_expected_eigenvalues: Array<{ real_per_s: number; imag_per_s: number; oscillation_frequency_hz: number }>
    frequency_base_counterfactual: {
      frequency_hz: number
      matched_eigenvalue_max_error_per_s: number
      interpretation: string
    }
  }
  common_lcl_isomorphism: {
    schema_version: string
    status: 'passed' | 'failed'
    common_layer: {
      state_count: number
      state_labels: string[]
      input_count: number
      input_labels: string[]
      terminal_definition: string
      source_coordinates: string
      team_coordinates: string
      alignment_angle_rad: number
    }
    verification_gates: {
      matrix_and_rhs_max_abs_difference_per_s: number
      counterfactual_state_matrix_difference_min_per_s: number
    }
    results: {
      state_matrix_max_abs_difference_per_s: number
      input_matrix_max_abs_difference_per_s: number
      probe_rhs_max_abs_difference_per_s: number
      counterfactual: {
        change: string
        state_matrix_max_abs_difference_per_s: number
        input_matrix_max_abs_difference_per_s: number
        probe_rhs_max_abs_difference_per_s: number
      }
    }
    network_interface: {
      network_reactance_pu_system_base: number
      network_reactance_pu_device_base: number
      included_in_common_lcl_gate: boolean
      reason: string
    }
    scope: {
      common_lcl_equations_isomorphic: boolean
      full_state_dimensions_equal: boolean
      outer_controls_compared: boolean
      pll_or_active_damping_compared: boolean
      external_network_dynamics_compared: boolean
      full_model_eigenvalues_comparable_from_this_gate: boolean
      statement: string
    }
  }
  inner_control_mapping: {
    schema_version: string
    status: 'partial' | 'failed'
    verification_gates: {
      matrix_max_abs_difference: number
    }
    pi_state_mapping: {
      status: 'passed' | 'failed'
      source_definition: string
      team_definition: string
      coordinate_transform: string
      state_input_matrix_max_abs_difference: number
      state_output_matrix_max_abs_difference: number
      proportional_matrix_max_abs_difference: number
    }
    compensation_mapping: {
      test08_to_team_max_abs_difference: number
      parameter_only_aligned_max_abs_difference: number
      parameter_only_aligned_probe_max_abs_difference: number
      parameter_only_isomorphic: boolean
      structural_counterfactual_max_abs_difference: number
      structural_counterfactual_passed: boolean
      remaining_term: string
    }
    scope: {
      pi_states_isomorphic_after_scaling: boolean
      test08_and_team_complete_inner_controls_isomorphic: boolean
      parameter_only_alignment_sufficient: boolean
      structural_counterfactual_is_source_test08: boolean
      statement: string
    }
  }
  common_inner_loop: {
    schema_version: string
    status: 'passed' | 'failed'
    common_model: {
      state_count: number
      source_state_labels: string[]
      team_state_labels: string[]
      input_count: number
      input_labels: string[]
      alignment_angle_rad: number
      current_feedforward_gain: number
      voltage_feedforward_gain: number
      active_damping_gain: number
    }
    variants: {
      both_omit_resistive_drop_feedforward: {
        status: 'passed' | 'failed'
        state_matrix_max_abs_difference_per_s: number
        input_matrix_max_abs_difference_per_s: number
        probe_rhs_max_abs_difference_per_s: number
        spectral_abscissa_per_s: number
        stable_by_eigenvalues: boolean
      }
      both_include_resistive_drop_feedforward: {
        status: 'passed' | 'failed'
        state_matrix_max_abs_difference_per_s: number
        input_matrix_max_abs_difference_per_s: number
        probe_rhs_max_abs_difference_per_s: number
        spectral_abscissa_per_s: number
        stable_by_eigenvalues: boolean
      }
    }
    structural_choice_sensitivity: {
      maximum_matched_eigenvalue_displacement_per_s: number
      spectral_abscissa_change_per_s: number
      stability_classification_changed: boolean
    }
    counterfactual: {
      change: string
      state_matrix_max_abs_difference_per_s: number
      input_matrix_max_abs_difference_per_s: number
      probe_rhs_max_abs_difference_per_s: number
      gate_rejected_mismatch: boolean
    }
    scope: {
      source_baselines_modified: boolean
      both_intermediate_variants_isomorphic: boolean
      outer_controls_compared: boolean
      pll_compared: boolean
      active_damping_compared: boolean
      modulation_or_limits_compared: boolean
      external_network_dynamics_compared: boolean
      statement: string
    }
  }
  common_active_damping: {
    schema_version: string
    status: 'passed' | 'failed'
    active_damping_contract: {
      filter_state_count: number
      cutoff_rad_s: number
      gain: number
      feedback: string
      filter_dynamics: string
    }
    variants: {
      both_omit_resistive_drop_feedforward: {
        without_active_damping: {
          state_count: number
          spectral_abscissa_per_s: number
          stable_by_eigenvalues: boolean
        }
        with_active_damping: {
          state_count: number
          status: 'passed' | 'failed'
          spectral_abscissa_per_s: number
          stable_by_eigenvalues: boolean
        }
        spectral_abscissa_change_per_s: number
        stability_classification_changed: boolean
      }
      both_include_resistive_drop_feedforward: {
        without_active_damping: {
          state_count: number
          spectral_abscissa_per_s: number
          stable_by_eigenvalues: boolean
        }
        with_active_damping: {
          state_count: number
          status: 'passed' | 'failed'
          spectral_abscissa_per_s: number
          stable_by_eigenvalues: boolean
        }
        spectral_abscissa_change_per_s: number
        stability_classification_changed: boolean
      }
    }
    counterfactual: {
      change: string
      state_matrix_max_abs_difference_per_s: number
      probe_rhs_max_abs_difference_per_s: number
      gate_rejected_mismatch: boolean
    }
    hypothesis_test: {
      hypothesis: string
      supported_for_both_structural_paths: boolean
    }
    scope: {
      source_baselines_modified: boolean
      team_original_model_modified: boolean
      common_active_damping_intermediate_only: boolean
      outer_controls_compared: boolean
      pll_compared: boolean
      modulation_or_limits_compared: boolean
      external_network_dynamics_compared: boolean
      statement: string
    }
  }
  common_inner_loop_modal_fingerprint: {
    schema_version: string
    status: 'passed' | 'failed'
    variants: Record<string, {
      state_count: number
      resistive_drop_feedforward_gain: number
      active_damping_gain: number
      active_damping_cutoff_rad_s: number | null
      baseline_named_branch: {
        eigenvalue: {
          real_per_s: number
          imag_per_s: number
          oscillation_frequency_hz: number
        }
        group_participation_frozen_coordinates: Record<string, number>
        lcl_group_total: number
        control_state_group_total: number
        condition_number: number
        right_eigenpair_residual: number
        left_eigenpair_residual: number
      }
      sensitivity_ranking: Array<{
        factor_name: string
        central_real_sensitivity_per_log_factor_per_s: number
        central_frequency_sensitivity_hz_per_log_factor: number
        maximum_absolute_real_shift_per_s: number
      }>
      all_pre_registered_endpoints_matched: boolean
      candidate_interaction_evidence: {
        status: 'consistent' | 'not-supported'
        statement: string
      }
    }>
    tracking_counterexample: {
      direct_jump_rejected: boolean
      refined_path_status: 'matched' | 'pending'
      refined_path_step_count_including_rejected_attempt: number
      refinement_recovers_branch: boolean
    }
    hypothesis_test: {
      hypothesis: string
      consistent_in_all_four_variants: boolean
      result: 'supported-as-bounded-candidate-interaction' | 'not-supported'
    }
    scope: {
      state_scaling: string
      participation_invariant_to_future_state_rescaling: boolean
      full_spectrum_global_continuation: boolean
      grid_strength_scanned: boolean
      grid_side_reactance_meaning: string
      causal_attribution_established: boolean
      statement: string
    }
  }
  common_outer_loop: {
    schema_version: string
    status: 'passed' | 'failed'
    model_contract: {
      state_count: number
      pcc_voltage_global_pu: number[]
      ideal_limits: {
        team_active_power_measurement_delay_s: number
        team_modulation_delay_s: number
        sienna_pll_damping_gain: number
      }
      parameter_mapping: Record<string, string>
    }
    verification_gates: {
      equilibrium_residual_inf_max: number
      rhs_and_matrix_difference_max_per_s: number
      mixed_power_port_difference_min_per_s: number
    }
    variants: Record<'filter_capacitor' | 'pcc', {
      equilibrium_residual_inf: number
      rhs_difference_inf: number
      state_matrix_max_abs_difference_per_s: number
      spectral_abscissa_per_s: number
      stable_by_eigenvalues: boolean
      oscillatory_modes: Array<{
        real_per_s: number
        imag_per_s: number
        frequency_hz: number
      }>
      equilibrium: Record<string, number>
    }>
    counterexample: {
      change: string
      state_matrix_max_abs_difference_per_s: number
      gate_rejected_mismatch: boolean
    }
    scope: {
      source_baselines_modified: boolean
      team_original_model_modified: boolean
      common_intermediate_cases_only: boolean
      loaded_equilibrium: boolean
      power_measurement_port_originally_identical: boolean
      external_network_dynamics_compared: boolean
      statement: string
    }
  }
  common_active_power_measurement_delay: {
    schema_version: string
    status: 'passed' | 'failed'
    model_contract: {
      state_count: number
      ideal_limit_state_count: number
      team_state_labels: string[]
      source_state_labels: string[]
      power_measurement_equation: string
      delay_levels_s: number[]
      team_declared_time_constant_s: number
      pcc_voltage_global_pu: number[]
    }
    verification_gates: {
      equilibrium_residual_inf_max: number
      rhs_and_matrix_difference_max_per_s: number
      mixed_power_port_difference_min_per_s: number
    }
    variants: Record<'filter_capacitor' | 'pcc', {
      ideal_thirteen_state_limit: {
        low_frequency_mode: SiennaDelayPole
        wide_frequency_mode: SiennaDelayPole
      }
      points: Array<{
        active_power_time_constant_s: number
        equilibrium_residual_inf: number
        rhs_difference_inf: number
        state_matrix_max_abs_difference_per_s: number
        spectral_abscissa_per_s: number
        stable_by_eigenvalues: boolean
        low_frequency_mode: {
          pole: SiennaDelayPole
          tracking: SiennaDelayTracking
        }
        wide_frequency_mode: {
          pole: SiennaDelayPole
          tracking: SiennaDelayTracking
        }
        measurement_associated_pole: SiennaDelayPole
      }>
      endpoint_normalized_displacement_from_0p01s: {
        low_frequency_mode: number
        wide_frequency_mode: number
      }
      candidate_hypothesis_low_branch_moves_more: boolean
    }>
    counterexample: {
      change: string
      state_matrix_max_abs_difference_per_s: number
      gate_rejected_mismatch: boolean
    }
    hypothesis_test: {
      hypothesis: string
      supported_in_both_port_conventions: boolean
      result: 'supported-in-bounded-scan' | 'not-supported-in-bounded-scan'
    }
    scope: {
      source_baselines_modified: boolean
      team_original_model_modified: boolean
      common_intermediate_cases_only: boolean
      power_measurement_port_held_common_within_each_variant: boolean
      ideal_limit_force_matched_to_fourteen_state_spectrum: boolean
      whole_system_hopf_margin_claimed: boolean
      modulation_dynamics_compared: boolean
      pll_or_frequency_estimator_compared: boolean
      external_network_dynamics_compared: boolean
      paper_sufficient_condition_evaluated: boolean
      statement: string
    }
  }
  common_pll_measurement: {
    schema_version: string
    status: 'passed' | 'failed'
    model_contract: {
      state_count: number
      base_state_count: number
      power_measurement_port: string
      active_power_time_constant_s: number
      pll_voltage_ports: string[]
      pll_cutoff_rad_s: number
      pll_kp: number
      pll_ki: number
      damping_levels: number[]
      damping_equation: string
    }
    cases: Record<string, {
      pll_voltage_port: string
      damping_gain: number
      equilibrium_residual_inf: number
      rhs_difference_inf: number
      state_matrix_max_abs_difference_per_s: number
      spectral_abscissa_per_s: number
      stable_by_eigenvalues: boolean
      low_frequency_mode: {
        pole: SiennaDelayPole
        tracking: SiennaDelayTracking
      }
      wide_frequency_mode: {
        pole: SiennaDelayPole
        tracking: SiennaDelayTracking
      }
      negative_control: {
        base_submatrix_max_abs_difference_per_s: number
        pll_to_converter_feedback_max_abs_per_s: number
      }
      continuation?: {
        status: 'resolved' | 'pending'
        adaptive_bisection_max_depth: number
        attempt_count: number
      }
    }>
    hypothesis_tests: {
      four_common_equations_match: boolean
      damping_off_is_structural_negative_control: boolean
      named_modes_resolved: boolean
      damping_on_low_mode_real_part_position_difference_per_s: number | null
      measurement_position_effect_conclusion: string
    }
    scope: {
      source_baselines_modified: boolean
      team_original_model_modified: boolean
      common_intermediate_cases_only: boolean
      pll_measurement_position_and_damping_separated: boolean
      pll_gain_scan_performed: boolean
      whole_system_hopf_margin_claimed: boolean
      modulation_or_external_network_dynamics_compared: boolean
      paper_sufficient_condition_evaluated: boolean
      statement: string
    }
  }
  scope: {
    source_equation_transcription_verified: boolean
    julia_runtime_executed_on_this_machine: boolean
    pscad_rerun: boolean
    upstream_pscad_trace_present_in_fixed_source: boolean
    team_16_state_model_validated_by_this_audit: boolean
    team_common_lcl_layer_compared: boolean
    team_pi_state_scaling_compared: boolean
    team_complete_inner_control_compared: boolean
    team_common_inner_loop_variants_compared: boolean
    team_common_active_damping_variants_compared: boolean
    team_common_inner_loop_modal_fingerprint_evaluated: boolean
    team_common_outer_loop_power_ports_compared: boolean
    team_common_active_power_measurement_delay_compared: boolean
    team_common_pll_measurement_position_compared: boolean
    mathworks_model_evaluated: boolean
    paper_sufficient_condition_evaluated: boolean
    statement: string
  }
}

type AverageDQAblationInput = {
  preset_id: AverageDQAblationPresetId
}

type AverageDQPortIdentificationInput = {
  preset_id: 'average-dq-smib-verification'
}

async function averageDQRequest(path: string, input: AverageDQAnalysisInput | AverageDQScanInput | AverageDQAblationInput | AverageDQPortIdentificationInput) {
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

export async function runAverageDQPortIdentification(): Promise<AverageDQPortIdentificationResult> {
  return (await averageDQRequest('/api/average-dq/port-identification', {
    preset_id: 'average-dq-smib-verification',
  })).json()
}

export async function getAverageDQPortIdentificationReportHtml(): Promise<string> {
  return (await averageDQRequest('/api/reports/average-dq-port-identification', {
    preset_id: 'average-dq-smib-verification',
  })).text()
}

export async function getMathWorksExternalEvidence(): Promise<MathWorksExternalEvidenceResult> {
  const response = await fetch('/api/evidence/mathworks-gfm')
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `外部验证证据服务返回 ${response.status}`)
  }
  return response.json()
}

export async function getMathWorksTeamComparison(): Promise<MathWorksTeamComparisonResult> {
  const response = await fetch('/api/evidence/mathworks-team-comparison')
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `跨模型对照服务返回 ${response.status}`)
  }
  return response.json()
}

export async function getAverageDQAlignedStepEvidence(): Promise<AverageDQAlignedStepResult> {
  const response = await fetch('/api/evidence/average-dq-aligned-nonlinear-step')
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `团队非线性阶跃证据服务返回 ${response.status}`)
  }
  return response.json()
}

export async function getSiennaTest08Audit(): Promise<SiennaTest08AuditResult> {
  const response = await fetch('/api/reference/sienna-test08/audit')
  if (!response.ok) {
    const detail = await response.json().catch(() => null)
    throw new Error(detail?.detail ?? `Sienna Test 08 方程复核服务返回 ${response.status}`)
  }
  return response.json()
}
