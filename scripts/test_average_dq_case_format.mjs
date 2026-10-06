import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

// Use the project's existing TypeScript compiler without new dependencies,
// generated files, or changes to the production module.
const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/averageDQCase.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
const errors = (compiled.diagnostics ?? []).filter((item) => item.category === ts.DiagnosticCategory.Error)
assert.deepEqual(errors, [], 'case module must transpile without errors')
const { makeAverageDQCase, parseAverageDQCase, parseNetworkTopology, AVERAGE_DQ_CASE_SCHEMA_VERSION } = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`
)

function fixture() {
  return {
    topology: {
      schema_version: '1.0',
      id: 'average-dq-smib-verification',
      name: 'Average dq verification',
      base_values: { apparent_power_va: 1e6, voltage_v: 690, frequency_hz: 50 },
      frame_convention_id: 'power-invariant-park-q-lag-v1',
      reference_bus_id: 'bus-grid',
      buses: [
        { kind: 'bus', id: 'bus-gfm', name: 'GFM', nominal_voltage_v: 690 },
        { kind: 'bus', id: 'bus-grid', name: 'Grid', nominal_voltage_v: 690 },
      ],
      lines: [{
        kind: 'ac_line', id: 'line-grid', name: 'External RL line',
        from_bus_id: 'bus-gfm', to_bus_id: 'bus-grid',
        resistance_pu: 0.02, reactance_pu: 0.30,
        shunt_susceptance_pu: 0, thermal_limit_pu: null, in_service: true,
      }],
      grid_forming_converters: [{
        kind: 'grid_forming_converter', id: 'gfm-1', name: 'VSM',
        bus_id: 'bus-gfm', rated_apparent_power_va: 1e6,
        control_mode: 'virtual_synchronous_machine',
        active_power_setpoint_pu: 0.5, reactive_power_setpoint_pu: 0.1,
        voltage_setpoint_pu: 1, virtual_inertia_s: 2,
        damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1,
        parameter_set_id: 'average-dq-default-v1',
      }],
      infinite_buses: [{
        kind: 'infinite_bus', id: 'grid-1', name: 'Infinite bus', bus_id: 'bus-grid',
        voltage_magnitude_pu: 1, voltage_angle_deg: 0,
      }],
      loads: [],
    },
    parameters: {
      schema_version: '1.0', id: 'average-dq-default-v1', converter_id: 'gfm-1',
      frame_convention_id: 'power-invariant-park-q-lag-v1',
      converter_side_resistance_pu: 0.01, converter_side_reactance_pu: 0.15,
      filter_capacitor_susceptance_pu: 0.05,
      grid_side_resistance_pu: 0.01, grid_side_reactance_pu: 0.10,
      modulation_time_constant_s: 0.001,
      reactive_power_measurement_time_constant_s: 0.02,
      reactive_power_voltage_droop_pu: 0.05,
      voltage_proportional_gain_pu: 0.3, voltage_integral_gain_per_s: 5,
      current_proportional_gain_pu: 0.3, current_integral_gain_per_s: 5,
      virtual_resistance_pu: 0, virtual_reactance_pu: 0,
      diagnostic_current_limit_pu: 2, diagnostic_internal_voltage_limit_pu: 1.5,
    },
    simulation_time_s: 0.6,
    time_step_s: 0.003,
    initial_angle_perturbation_rad: 0.0003,
    frequency_values_hz: [0, 0.25, 2, 60],
  }
}

let passed = 0
function test(name, action) {
  try { action(); passed += 1 } catch (error) {
    throw new Error(`FAILED: ${name}`, { cause: error })
  }
}

function rejectsMutation(name, mutate) {
  test(name, () => {
    const input = fixture()
    mutate(input)
    assert.throws(() => makeAverageDQCase(input), /平均值 dq 案例/)
    assert.throws(() => parseAverageDQCase({ schema_version: AVERAGE_DQ_CASE_SCHEMA_VERSION, input }), /平均值 dq 案例/)
  })
}

test('direct topology parser accepts the complete contract and returns a deep snapshot', () => {
  const topology = fixture().topology
  const parsed = parseNetworkTopology(topology)
  assert.deepEqual(parsed, topology)
  parsed.buses[0].name = 'Changed only in returned snapshot'
  parsed.base_values.frequency_hz = 60
  assert.equal(topology.buses[0].name, 'GFM')
  assert.equal(topology.base_values.frequency_hz, 50)
})
for (const field of ['buses', 'lines', 'grid_forming_converters', 'infinite_buses', 'loads']) {
  test(`direct topology parser rejects missing ${field}`, () => {
    const topology = fixture().topology
    delete topology[field]
    const before = structuredClone(topology)
    assert.throws(() => parseNetworkTopology(topology), /平均值 dq 案例/)
    assert.deepEqual(topology, before)
  })
  for (const value of [null, {}, '[]']) {
    test(`direct topology parser rejects ${field} type ${String(value)}`, () => {
      const topology = fixture().topology
      topology[field] = value
      assert.throws(() => parseNetworkTopology(topology), /平均值 dq 案例/)
    })
  }
}
test('direct topology parser rejects invalid nested values without changing caller', () => {
  const topology = fixture().topology
  topology.lines[0].reactance_pu = Infinity
  const before = structuredClone(topology)
  assert.throws(() => parseNetworkTopology(topology), /平均值 dq 案例/)
  assert.deepEqual(topology, before)
})

test('complete non-default JSON round trip', () => {
  const input = fixture()
  const saved = makeAverageDQCase(input)
  assert.equal(saved.schema_version, 'AverageDQCase/1.0')
  assert.deepEqual(saved.input, input)
  assert.deepEqual(parseAverageDQCase(JSON.parse(JSON.stringify(saved))), { input, legacy: false })
})

test('make and parse return independent deep snapshots', () => {
  const input = fixture()
  const saved = makeAverageDQCase(input)
  saved.input.topology.lines[0].reactance_pu = 0.5
  saved.input.frequency_values_hz[0] = 0.1
  assert.equal(input.topology.lines[0].reactance_pu, 0.3)
  assert.equal(input.frequency_values_hz[0], 0)
  const parsed = parseAverageDQCase(saved)
  parsed.input.parameters.current_integral_gain_per_s = 9
  assert.equal(saved.input.parameters.current_integral_gain_per_s, 5)
})

test('legacy uses the original UI defaults explicitly', () => {
  const { topology, parameters } = fixture()
  const imported = parseAverageDQCase({ topology, parameters })
  assert.equal(imported.legacy, true)
  assert.deepEqual(imported.input, {
    topology, parameters,
    simulation_time_s: 2, time_step_s: 0.002,
    initial_angle_perturbation_rad: 0.0001,
    frequency_values_hz: Array.from({ length: 31 }, (_, index) => 10 ** (-1 + index * 3 / 30)),
  })
})

for (const version of ['AverageDQCase/2.0', '1.0', '', null, 1, undefined]) {
  test(`unknown schema ${String(version)}`, () => {
    assert.throws(() => parseAverageDQCase({ schema_version: version, input: fixture() }), /平均值 dq 案例/)
  })
}

test('missing schema cannot quietly migrate a new-format file', () => {
  assert.throws(() => parseAverageDQCase({ input: fixture() }), /平均值 dq 案例/)
})

test('legacy mixed with partial new settings is rejected', () => {
  const { topology, parameters } = fixture()
  assert.throws(() => parseAverageDQCase({ topology, parameters, simulation_time_s: 0.6 }), /平均值 dq 案例/)
})

for (const value of [null, [], 1, 'case', true, undefined, new Date()]) {
  test(`invalid root ${String(value)}`, () => assert.throws(() => parseAverageDQCase(value), /平均值 dq 案例/))
}

for (const field of Object.keys(fixture())) {
  rejectsMutation(`complete case requires ${field}`, (input) => { delete input[field] })
}
for (const field of Object.keys(fixture().parameters)) {
  rejectsMutation(`all parameter fields required: ${field}`, (input) => { delete input.parameters[field] })
}
for (const field of Object.keys(fixture().topology)) {
  rejectsMutation(`all topology fields required: ${field}`, (input) => { delete input.topology[field] })
}

for (const field of ['buses', 'lines', 'grid_forming_converters', 'infinite_buses', 'loads']) {
  for (const value of [null, {}, '[]']) {
    rejectsMutation(`${field} is an array, not ${String(value)}`, (input) => { input.topology[field] = value })
  }
}
for (const field of ['simulation_time_s', 'time_step_s', 'initial_angle_perturbation_rad']) {
  for (const value of [NaN, Infinity, -Infinity, null, '0.002', true]) {
    rejectsMutation(`${field} rejects ${String(value)}`, (input) => { input[field] = value })
  }
}
for (const value of [null, [], {}, [NaN], [Infinity], [-Infinity], [-1], ['1'], [true], [1, 1], [2, 1], Array.from({ length: 201 }, (_, index) => index)]) {
  rejectsMutation(`invalid frequency list ${String(value)}`, (input) => { input.frequency_values_hz = value })
}

for (const [field, values] of [
  ['simulation_time_s', [0, -1, 30.0001]],
  ['time_step_s', [0.000099, 0.100001]],
  ['initial_angle_perturbation_rad', [-0.010001, 0.010001]],
]) {
  for (const value of values) rejectsMutation(`${field} rejects out-of-range ${value}`, (input) => { input[field] = value })
}
rejectsMutation('sample count over 3001', (input) => { input.simulation_time_s = 30; input.time_step_s = 0.0001 })
test('API sampling and perturbation boundary accepted', () => {
  const input = fixture()
  input.simulation_time_s = 30
  input.time_step_s = 0.01
  input.initial_angle_perturbation_rad = -0.01
  input.frequency_values_hz = Array.from({ length: 200 }, (_, index) => index)
  assert.deepEqual(makeAverageDQCase(input).input, input)
  input.initial_angle_perturbation_rad = 0.01
  assert.deepEqual(makeAverageDQCase(input).input, input)
})
test('API has no extra single-frequency upper bound', () => {
  const input = fixture()
  input.frequency_values_hz = [Number.MAX_VALUE]
  assert.deepEqual(makeAverageDQCase(input).input.frequency_values_hz, [Number.MAX_VALUE])
})

const parameterRanges = [
  ['converter_side_resistance_pu', 0, 10, false],
  ['converter_side_reactance_pu', 0, 10, true],
  ['filter_capacitor_susceptance_pu', 0, 10, true],
  ['grid_side_resistance_pu', 0, 10, false],
  ['grid_side_reactance_pu', 0, 10, true],
  ['modulation_time_constant_s', 0, 1, true],
  ['reactive_power_measurement_time_constant_s', 0, 10, true],
  ['reactive_power_voltage_droop_pu', 0, 10, false],
  ['voltage_proportional_gain_pu', 0, 1e4, false],
  ['voltage_integral_gain_per_s', 0, 1e6, true],
  ['current_proportional_gain_pu', 0, 1e4, false],
  ['current_integral_gain_per_s', 0, 1e6, true],
  ['virtual_resistance_pu', 0, 10, false],
  ['virtual_reactance_pu', 0, 10, false],
  ['diagnostic_current_limit_pu', 0, 100, true],
  ['diagnostic_internal_voltage_limit_pu', 0, 100, true],
]
for (const [field, min, max, exclusiveMin] of parameterRanges) {
  for (const value of [NaN, Infinity, null, '1', -1, max * 1.001]) {
    rejectsMutation(`parameter ${field} rejects ${String(value)}`, (input) => { input.parameters[field] = value })
  }
  if (exclusiveMin) rejectsMutation(`parameter ${field} rejects zero`, (input) => { input.parameters[field] = min })
  test(`parameter ${field} accepted boundary`, () => {
    const input = fixture()
    input.parameters[field] = max
    assert.deepEqual(makeAverageDQCase(input).input, input)
    if (!exclusiveMin) {
      input.parameters[field] = min
      assert.deepEqual(makeAverageDQCase(input).input, input)
    }
  })
}

rejectsMutation('input unknown field', (input) => { input.unsupported = 1 })
rejectsMutation('preset and custom input cannot be mixed', (input) => { input.preset_id = 'average-dq-smib-verification' })
rejectsMutation('parameter unknown field', (input) => { input.parameters.unsupported = 1 })
rejectsMutation('topology unknown field', (input) => { input.topology.unsupported = 1 })
rejectsMutation('invalid parameter frame', (input) => { input.parameters.frame_convention_id = 'other' })
rejectsMutation('invalid entity id', (input) => { input.topology.buses[0].id = '../invalid' })
rejectsMutation('non-finite topology base', (input) => { input.topology.base_values.voltage_v = Infinity })
rejectsMutation('too large topology base', (input) => { input.topology.base_values.apparent_power_va = 1e12 + 1 })
rejectsMutation('line too large', (input) => { input.topology.lines[0].reactance_pu = 101 })
rejectsMutation('boolean field is not numeric', (input) => { input.topology.lines[0].in_service = 1 })
rejectsMutation('line self-loop matches API rejection', (input) => { input.topology.lines[0].to_bus_id = 'bus-gfm' })
rejectsMutation('VSM missing required controller parameter', (input) => { delete input.topology.grid_forming_converters[0].virtual_inertia_s })
rejectsMutation('unknown control mode', (input) => { input.topology.grid_forming_converters[0].control_mode = 'unsupported' })

for (const control of ['droop', 'user_defined']) {
  test(`backend control enum ${control} remains valid format`, () => {
    const input = fixture()
    const converter = input.topology.grid_forming_converters[0]
    converter.control_mode = control
    if (control === 'droop') {
      converter.active_power_frequency_droop_pu = 0.04
      converter.reactive_power_voltage_droop_pu = 0.05
    }
    assert.deepEqual(parseAverageDQCase(makeAverageDQCase(input)).input, input)
  })
}
test('backend static-load kind and contract remain valid format', () => {
  const input = fixture()
  input.topology.loads.push({
    kind: 'static_load', id: 'load-1', name: 'Load', bus_id: 'bus-grid',
    load_model: 'constant_impedance', active_power_pu: 0.1, reactive_power_pu: 0,
  })
  assert.deepEqual(parseAverageDQCase(makeAverageDQCase(input)).input, input)
})
test('format does not pretend to enforce average-dq model scope', () => {
  const input = fixture()
  input.topology.grid_forming_converters = []
  assert.deepEqual(parseAverageDQCase(makeAverageDQCase(input)).input, input)
})
test('failed validation cannot half-overwrite a caller snapshot', () => {
  let current = fixture()
  const before = structuredClone(current)
  const input = fixture()
  input.topology.name = 'Do not apply me'
  input.parameters.current_integral_gain_per_s = Infinity
  assert.throws(() => { current = parseAverageDQCase({ schema_version: AVERAGE_DQ_CASE_SCHEMA_VERSION, input }).input }, /平均值 dq 案例/)
  assert.deepEqual(current, before)
  assert.equal(input.topology.name, 'Do not apply me')
  assert.equal(input.parameters.current_integral_gain_per_s, Infinity)
})

console.log(`AverageDQ case-format checks passed: ${passed}`)
