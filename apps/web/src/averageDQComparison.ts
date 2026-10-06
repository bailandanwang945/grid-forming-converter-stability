import type { AverageDQAnalysisInput } from './api'

export type CaseInputChange = { field: string; label: string; before: unknown; after: unknown }

const fieldLabels: Record<string, string> = {
  simulation_time_s: '仿真时长 / s', time_step_s: '输出采样间隔 / s',
  initial_angle_perturbation_rad: '初始相角扰动 / rad', frequency_values_hz: '导纳频率网格 / Hz',
  active_power_setpoint_pu: '有功功率给定 / p.u.', reactive_power_setpoint_pu: '无功功率给定 / p.u.',
  voltage_setpoint_pu: '电压幅值给定 / p.u.', damping_coefficient_pu: '阻尼系数 D',
  virtual_inertia_s: '虚拟惯性 / s', active_power_measurement_time_constant_s: '有功测量时间常数 / s',
  resistance_pu: '电阻 / p.u.', reactance_pu: '电抗 / p.u.', in_service: '投运状态',
  converter_side_resistance_pu: '变流器侧滤波电阻 / p.u.', converter_side_reactance_pu: '变流器侧滤波电抗 / p.u.',
  filter_capacitor_susceptance_pu: '滤波电容电纳 / p.u.', grid_side_resistance_pu: '电网侧滤波电阻 / p.u.',
  grid_side_reactance_pu: '电网侧滤波电抗 / p.u.', modulation_time_constant_s: '调制器时间常数 / s',
  reactive_power_measurement_time_constant_s: '无功测量时间常数 / s', reactive_power_voltage_droop_pu: '无功—电压下垂系数',
  voltage_proportional_gain_pu: '电压环比例增益', voltage_integral_gain_per_s: '电压环积分增益 / s⁻¹',
  current_proportional_gain_pu: '电流环比例增益', current_integral_gain_per_s: '电流环积分增益 / s⁻¹',
  virtual_resistance_pu: '虚拟电阻 / p.u.', virtual_reactance_pu: '虚拟电抗 / p.u.',
  diagnostic_current_limit_pu: '诊断电流限值 / p.u.', diagnostic_internal_voltage_limit_pu: '诊断内部电压限值 / p.u.',
  voltage_magnitude_pu: '母线电压幅值 / p.u.', voltage_angle_deg: '母线相角 / °', frequency_hz: '基频 / Hz',
  apparent_power_va: '功率基准 / VA', voltage_v: '电压基准 / V', nominal_voltage_v: '额定电压 / V',
  id: '标识', name: '名称', converter_id: '关联设备标识', parameter_set_id: '参数组标识',
  control_mode: '控制方式', from_bus_id: '起点母线', to_bus_id: '终点母线', bus_id: '接入母线',
  frame_convention_id: '坐标约定', schema_version: '格式版本', reference_bus_id: '参考母线',
}

function fieldLabel(path: string) {
  const pieces = path.split('.')
  const collectionNames: Record<string, string> = {
    grid_forming_converters: '变流器', lines: '线路', buses: '母线', infinite_buses: '无穷大母线', loads: '负荷',
  }
  const collectionIndex = pieces.findIndex(piece => piece in collectionNames)
  const prefix = collectionIndex >= 0
    ? `${collectionNames[pieces[collectionIndex]]}${Number(pieces[collectionIndex + 1]) + 1} · `
    : pieces[0] === 'parameters' ? '控制与滤波参数 · ' : ''
  return prefix + (fieldLabels[pieces[pieces.length - 1] ?? ''] ?? path)
}

export function describeCaseInputChanges(before: AverageDQAnalysisInput, after: AverageDQAnalysisInput): CaseInputChange[] {
  const changes: CaseInputChange[] = []
  function visit(left: unknown, right: unknown, path: string) {
    if (JSON.stringify(left) === JSON.stringify(right)) return
    if (path === 'frequency_values_hz') {
      changes.push({ field: path, label: fieldLabel(path), before: left, after: right })
      return
    }
    if (left !== null && right !== null && typeof left === 'object' && typeof right === 'object'
        && Array.isArray(left) === Array.isArray(right)) {
      const a = left as Record<string, unknown>
      const b = right as Record<string, unknown>
      for (const key of new Set([...Object.keys(a), ...Object.keys(b)])) visit(a[key], b[key], path ? `${path}.${key}` : key)
    } else changes.push({ field: path, label: fieldLabel(path), before: left ?? null, after: right ?? null })
  }
  visit(before, after, '')
  return changes
}

export function formatCaseInputValue(value: unknown): string {
  if (value === null || value === undefined) return '未设置'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (Array.isArray(value)) return value.length ? `${value.length} 点（${value[0]} 至 ${value[value.length - 1]}）` : '空列表'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}
