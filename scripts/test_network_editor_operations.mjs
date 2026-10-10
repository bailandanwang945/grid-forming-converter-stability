// Editing-operation safety only: no browser, build, network or numerical analysis.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkEditorOperations.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual((compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { validateLineEndpoints, createNetworkLine, reconnectNetworkLine } =
  await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)

function fixture() {
  return {
    schema_version: '1.0', id: 'editor-operations-test-only', name: 'Editing-operation fixture',
    frame_convention_id: 'power-invariant-park-q-lag-v1',
    base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 },
    reference_bus_id: 'bus-b',
    buses: ['bus-a', 'bus-b', 'bus-c'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
    lines: [{ id: 'line-1', name: 'Retained original branch', from_bus_id: 'bus-a', to_bus_id: 'bus-b',
      resistance_pu: 0.047, reactance_pu: 0.395, shunt_susceptance_pu: 0.017,
      thermal_limit_pu: 0.9, in_service: false }],
    grid_forming_converters: [{ id: 'gfm-1', name: 'VSM', bus_id: 'bus-a',
      control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
      virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
    infinite_buses: [{ id: 'grid-1', name: 'Grid', bus_id: 'bus-b' }],
    loads: [{ id: 'load-1', name: 'Load', bus_id: 'bus-c', load_model: 'constant_power',
      active_power_pu: 0.1, reactive_power_pu: 0.03 }],
  }
}

let scenarios = 0
function test(name, run) {
  run()
  scenarios += 1
  console.log(`PASS ${name}`)
}

// structuredClone and deep equality deliberately preserve NaN and Infinity.
// JSON snapshots would silently turn them into null and conceal input mutation.
function assertRejectedWithoutMutation(topology, fromBusId, toBusId) {
  const before = structuredClone(topology)
  const operations = [
    ['endpoint validation', () => validateLineEndpoints(topology, fromBusId, toBusId)],
    ['creation', () => createNetworkLine(topology, fromBusId, toBusId)],
    ['reconnection', () => reconnectNetworkLine(topology, 'line-1', fromBusId, toBusId)],
  ]
  for (const [name, operation] of operations) {
    const result = operation()
    assert.equal(result.ok, false, `${name} must reject invalid endpoints`)
    assert.equal(typeof result.message, 'string')
    assert.ok(result.message.trim(), `${name} must explain rejection`)
    assert.deepEqual(topology, before, `${name} must preserve the entire original input`)
    assert.deepEqual(topology.lines[0], before.lines[0], `${name} must retain the original branch and all parameters`)
  }
}

test('valid creation returns explicit example defaults and retains the original input', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  assert.deepEqual(validateLineEndpoints(topology, 'bus-a', 'bus-c'), { ok: true })
  const outcome = createNetworkLine(topology, 'bus-a', 'bus-c')
  assert.equal(outcome.ok, true)
  assert.deepEqual(outcome.line, {
    id: 'line-2', name: '线路 2', from_bus_id: 'bus-a', to_bus_id: 'bus-c',
    resistance_pu: 0.01, reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true,
  })
  assert.deepEqual(outcome.topology, { ...before, lines: [...before.lines, outcome.line] })
  assert.deepEqual(topology, before)
  assert.strictEqual(outcome.line, outcome.topology.lines.at(-1))
  assert.notStrictEqual(outcome.topology, topology)
  outcome.topology.buses[0].name = 'Changed returned clone'
  outcome.topology.lines[0].reactance_pu = 123
  assert.deepEqual(topology, before, 'Returned nested objects must not alias the input')
})

test('self-loops are refused by validation, creation and reconnection', () => {
  assertRejectedWithoutMutation(fixture(), 'bus-a', 'bus-a')
})

test('cross-voltage connections are refused in both directions without changing the branch', () => {
  const topology = fixture()
  topology.buses[2].nominal_voltage_v = 10000
  assertRejectedWithoutMutation(topology, 'bus-a', 'bus-c')
  assertRejectedWithoutMutation(topology, 'bus-c', 'bus-a')
})

test('unknown or unfinished endpoints preserve the complete original input', () => {
  for (const [from, to] of [
    ['missing-bus', 'bus-b'], ['bus-a', 'missing-bus'],
    ['', 'bus-b'], ['bus-a', ''], ['', ''],
  ]) assertRejectedWithoutMutation(fixture(), from, to)
})

test('zero, negative and non-finite voltage at either endpoint is refused without mutation', () => {
  for (const value of [0, -400, Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    for (const index of [0, 2]) {
      const topology = fixture()
      topology.buses[index].nominal_voltage_v = value
      assertRejectedWithoutMutation(topology, 'bus-a', 'bus-c')
    }
  }
})

test('valid reconnection changes endpoints only and retains impedance, name, service and optional fields', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const outcome = reconnectNetworkLine(topology, 'line-1', 'bus-b', 'bus-c')
  assert.equal(outcome.ok, true)
  const expectedLine = { ...before.lines[0], from_bus_id: 'bus-b', to_bus_id: 'bus-c' }
  assert.deepEqual(outcome.line, expectedLine)
  assert.deepEqual(outcome.topology, { ...before, lines: [expectedLine] })
  assert.deepEqual(topology, before)
  assert.strictEqual(outcome.line, outcome.topology.lines[0])
  outcome.line.name = 'Changed returned clone'
  outcome.topology.loads[0].active_power_pu = 123
  assert.deepEqual(topology, before, 'Reconnection result must not alias original objects')
})

test('reconnecting a missing line ID is refused without creating or deleting any line', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const outcome = reconnectNetworkLine(topology, 'missing-line', 'bus-a', 'bus-c')
  assert.equal(outcome.ok, false)
  assert.ok(outcome.message.includes('missing-line'))
  assert.deepEqual(topology, before)
})

test('new line IDs avoid occupied IDs across buses, branches, converters, grids and loads', () => {
  const topology = fixture()
  topology.buses.push({ id: 'line-2', name: 'Occupied bus ID', nominal_voltage_v: 400 })
  topology.grid_forming_converters[0].id = 'line-3'
  topology.infinite_buses[0].id = 'line-4'
  topology.loads[0].id = 'line-5'
  const before = structuredClone(topology)
  const outcome = createNetworkLine(topology, 'bus-a', 'bus-c')
  assert.equal(outcome.ok, true)
  assert.equal(outcome.line.id, 'line-6')
  assert.equal(outcome.line.name, '线路 6')
  assert.deepEqual(topology, before)
  assert.deepEqual(outcome.topology.lines.slice(0, -1), before.lines)
})

test('explicit parallel branches are legal and receive distinct IDs in either orientation', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const parallel = createNetworkLine(topology, 'bus-a', 'bus-b')
  assert.equal(parallel.ok, true)
  assert.equal(parallel.topology.lines.length, 2)
  assert.equal(parallel.line.id, 'line-2')
  assert.deepEqual(parallel.topology.lines[0], before.lines[0])
  assert.deepEqual(topology, before)
  const parallelBefore = structuredClone(parallel.topology)
  const reversed = createNetworkLine(parallel.topology, 'bus-b', 'bus-a')
  assert.equal(reversed.ok, true)
  assert.equal(reversed.topology.lines.length, 3)
  assert.equal(reversed.line.id, 'line-3')
  assert.equal(reversed.line.from_bus_id, 'bus-b')
  assert.equal(reversed.line.to_bus_id, 'bus-a')
  assert.deepEqual(reversed.topology.lines.slice(0, -1), parallelBefore.lines)
  assert.deepEqual(parallel.topology, parallelBefore)
})

console.log(`GFM_NETWORK_EDITOR_OPERATIONS_OK (${scenarios} operation-safety scenarios; no numerical claims)`)
