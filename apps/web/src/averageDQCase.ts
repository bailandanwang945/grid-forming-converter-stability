import type { AverageDQAnalysisInput, AverageDQParameters, NetworkTopology } from './api'

export const AVERAGE_DQ_CASE_SCHEMA_VERSION = 'AverageDQCase/1.0' as const

export type CompleteAverageDQAnalysisInput = AverageDQAnalysisInput & {
  topology: NetworkTopology
  parameters: AverageDQParameters
}

export type AverageDQCase = {
  schema_version: typeof AVERAGE_DQ_CASE_SCHEMA_VERSION
  input: CompleteAverageDQAnalysisInput
}

type RecordValue = Record<string, unknown>
type Validator = (value: unknown, path: string) => void
type Shape = Record<string, Validator>

function hasOwn(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key)
}

function fail(path: string, message: string): never {
  throw new Error(`平均值 dq 案例 ${path}：${message}`)
}

function record(value: unknown, path: string): RecordValue {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    fail(path, '必须是对象。')
  }
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) {
    fail(path, '必须是普通 JSON 对象。')
  }
  return value as RecordValue
}

function object(
  value: unknown,
  path: string,
  required: Shape,
  optional: Shape = {},
): RecordValue {
  const result = record(value, path)
  for (const key of Object.keys(result)) {
    if (!hasOwn(required, key) && !hasOwn(optional, key)) {
      fail(`${path}.${key}`, '不支持此字段。')
    }
  }
  for (const [key, validate] of Object.entries(required)) {
    if (!hasOwn(result, key)) fail(`${path}.${key}`, '缺少必填字段。')
    validate(result[key], `${path}.${key}`)
  }
  for (const [key, validate] of Object.entries(optional)) {
    if (hasOwn(result, key)) validate(result[key], `${path}.${key}`)
  }
  return result
}

function literal(...allowed: string[]): Validator {
  return (value, path) => {
    if (typeof value !== 'string' || !allowed.includes(value)) {
      fail(path, `必须是 ${allowed.join(' / ')}。`)
    }
  }
}

function number(min: number, max: number, exclusiveMin = false): Validator {
  return (value, path) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      fail(path, '必须是有限数值。')
    }
    if ((exclusiveMin ? value <= min : value < min) || value > max) {
      fail(path, `必须在 ${exclusiveMin ? '(' : '['}${min}, ${max}] 范围内。`)
    }
  }
}

const identifier: Validator = (value, path) => {
  if (typeof value !== 'string') fail(path, '必须是标识字符串。')
  const stripped = value.trim()
  if (stripped.length < 1 || stripped.length > 64 || !/^[A-Za-z0-9][A-Za-z0-9_.:-]*$/.test(stripped)) {
    fail(path, '标识长度应为 1–64，且只能包含字母、数字、下划线、点、冒号和连字符。')
  }
}

const name: Validator = (value, path) => {
  if (typeof value !== 'string' || value.trim().length < 1 || value.trim().length > 120) {
    fail(path, '名称必须是长度 1–120 的字符串。')
  }
}

const boolean: Validator = (value, path) => {
  if (typeof value !== 'boolean') fail(path, '必须是布尔值。')
}

function nullable(validate: Validator): Validator {
  return (value, path) => { if (value !== null) validate(value, path) }
}

function array(validate: Validator, minLength = 0, maxLength = Infinity): Validator {
  return (value, path) => {
    if (!Array.isArray(value)) fail(path, '必须是数组。')
    if (value.length < minLength || value.length > maxLength) {
      fail(path, `数组长度必须在 ${minLength}–${maxLength} 范围内。`)
    }
    for (let index = 0; index < value.length; index += 1) {
      validate(value[index], `${path}[${index}]`)
    }
  }
}

const bus: Validator = (value, path) => {
  object(value, path, {
    id: identifier,
    name,
    nominal_voltage_v: number(0, 1e9, true),
  }, { kind: literal('bus') })
}

const line: Validator = (value, path) => {
  const item = object(value, path, {
    id: identifier,
    name,
    from_bus_id: identifier,
    to_bus_id: identifier,
    resistance_pu: number(0, 100),
    reactance_pu: number(0, 100, true),
  }, {
    kind: literal('ac_line'),
    shunt_susceptance_pu: number(-100, 100),
    thermal_limit_pu: nullable(number(0, 1000, true)),
    in_service: boolean,
  })
  if ((item.from_bus_id as string).trim() === (item.to_bus_id as string).trim()) {
    fail(path, '线路首、末端节点不能相同。')
  }
}

const converter: Validator = (value, path) => {
  const item = object(value, path, {
    id: identifier,
    name,
    bus_id: identifier,
    rated_apparent_power_va: number(0, 1e12, true),
    control_mode: literal('virtual_synchronous_machine', 'droop', 'user_defined'),
  }, {
    kind: literal('grid_forming_converter'),
    active_power_setpoint_pu: number(-2, 2),
    reactive_power_setpoint_pu: number(-2, 2),
    voltage_setpoint_pu: number(0.5, 1.5),
    virtual_inertia_s: nullable(number(0, 1000, true)),
    damping_coefficient_pu: nullable(number(0, 1e4, true)),
    active_power_measurement_time_constant_s: nullable(number(0, 1000, true)),
    active_power_frequency_droop_pu: nullable(number(0, 1, true)),
    reactive_power_voltage_droop_pu: nullable(number(0, 1, true)),
    parameter_set_id: nullable(identifier),
  })
  const controlFields = item.control_mode === 'virtual_synchronous_machine'
    ? ['virtual_inertia_s', 'damping_coefficient_pu', 'active_power_measurement_time_constant_s']
    : item.control_mode === 'droop'
      ? ['active_power_frequency_droop_pu', 'reactive_power_voltage_droop_pu']
      : ['parameter_set_id']
  for (const field of controlFields) {
    if (item[field] === undefined || item[field] === null) {
      fail(`${path}.${field}`, '当前控制模式必须给出此字段。')
    }
  }
}

const infiniteBus: Validator = (value, path) => {
  object(value, path, { id: identifier, name, bus_id: identifier }, {
    kind: literal('infinite_bus'),
    voltage_magnitude_pu: number(0.5, 1.5),
    voltage_angle_deg: number(-180, 180),
  })
}

const load: Validator = (value, path) => {
  object(value, path, {
    id: identifier,
    name,
    bus_id: identifier,
    active_power_pu: number(0, 100),
  }, {
    kind: literal('static_load'),
    load_model: literal('constant_power', 'constant_impedance'),
    reactive_power_pu: number(-100, 100),
  })
}

// The topology's contract is validated here, not the average-dq model's scope.
// Supported device counts, network connectivity, and operating-point feasibility
// remain backend responsibilities; this file introduces no model assumptions.
const topology: Validator = (value, path) => {
  object(value, path, {
    schema_version: literal('1.0'),
    id: identifier,
    name,
    base_values: (base, basePath) => {
      object(base, basePath, {
        apparent_power_va: number(0, 1e12, true),
        voltage_v: number(0, 1e9, true),
        frequency_hz: number(1, 1000),
      })
    },
    frame_convention_id: identifier,
    reference_bus_id: identifier,
    buses: array(bus, 1),
    lines: array(line),
    grid_forming_converters: array(converter),
    infinite_buses: array(infiniteBus),
    loads: array(load),
  })
}

/** Validate the shared topology format before applying any imported state.
 * Network connectivity and individual analysis-model scope stay on the backend.
 */
export function parseNetworkTopology(value: unknown): NetworkTopology {
  topology(value, 'topology')
  return JSON.parse(JSON.stringify(value)) as NetworkTopology
}

const parameters: Validator = (value, path) => {
  object(value, path, {
    schema_version: literal('1.0'),
    id: identifier,
    converter_id: identifier,
    frame_convention_id: literal('power-invariant-park-q-lag-v1'),
    converter_side_resistance_pu: number(0, 10),
    converter_side_reactance_pu: number(0, 10, true),
    filter_capacitor_susceptance_pu: number(0, 10, true),
    grid_side_resistance_pu: number(0, 10),
    grid_side_reactance_pu: number(0, 10, true),
    modulation_time_constant_s: number(0, 1, true),
    reactive_power_measurement_time_constant_s: number(0, 10, true),
    reactive_power_voltage_droop_pu: number(0, 10),
    voltage_proportional_gain_pu: number(0, 1e4),
    voltage_integral_gain_per_s: number(0, 1e6, true),
    current_proportional_gain_pu: number(0, 1e4),
    current_integral_gain_per_s: number(0, 1e6, true),
    virtual_resistance_pu: number(0, 10),
    virtual_reactance_pu: number(0, 10),
    diagnostic_current_limit_pu: number(0, 100, true),
    diagnostic_internal_voltage_limit_pu: number(0, 100, true),
  })
}

function validateInput(value: unknown): CompleteAverageDQAnalysisInput {
  const input = object(value, 'input', {
    topology,
    parameters,
    simulation_time_s: number(0, 30, true),
    time_step_s: number(0.0001, 0.1),
    initial_angle_perturbation_rad: number(-0.01, 0.01),
    frequency_values_hz: array(number(0, Number.MAX_VALUE), 1, 200),
  })
  const sampleCount = Math.ceil((input.simulation_time_s as number) / (input.time_step_s as number)) + 1
  if (sampleCount > 3001) {
    fail('input', `非线性时域采样点数 ${sampleCount} 超过上限 3001。`)
  }
  const frequencies = input.frequency_values_hz as number[]
  for (let index = 1; index < frequencies.length; index += 1) {
    if (frequencies[index] <= frequencies[index - 1]) {
      fail('input.frequency_values_hz', '频率必须严格递增且不得重复。')
    }
  }
  // Clone only after all validation has succeeded; callers can commit the whole
  // returned snapshot atomically and never receive partially accepted input.
  return JSON.parse(JSON.stringify(input)) as CompleteAverageDQAnalysisInput
}

export function makeAverageDQCase(input: AverageDQAnalysisInput): AverageDQCase {
  return { schema_version: AVERAGE_DQ_CASE_SCHEMA_VERSION, input: validateInput(input) }
}

export function parseAverageDQCase(value: unknown): {
  input: CompleteAverageDQAnalysisInput
  legacy: boolean
} {
  const candidate = record(value, '文件')
  if (hasOwn(candidate, 'schema_version')) {
    object(candidate, '文件', {
      schema_version: literal(AVERAGE_DQ_CASE_SCHEMA_VERSION),
      input: () => {},
    })
    return { input: validateInput(candidate.input), legacy: false }
  }
  object(candidate, '旧版文件', { topology, parameters })
  return {
    input: validateInput({
      topology: candidate.topology,
      parameters: candidate.parameters,
      simulation_time_s: 2,
      time_step_s: 0.002,
      initial_angle_perturbation_rad: 0.0001,
      frequency_values_hz: Array.from({ length: 31 }, (_, index) => 10 ** (-1 + index * 3 / 30)),
    }),
    legacy: true,
  }
}
