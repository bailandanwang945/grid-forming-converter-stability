// Pure drawing-constraint compilation tests: no browser, server or numerical claims.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkIdealConnections.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext }, reportDiagnostics: true,
})
assert.deepEqual((compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { createIdealConnection, removeIdealConnection, parseIdealConnections, compileIdealConnections } =
  await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)

function fixture() {
  return {
    schema_version: '1.0', id: 'ideal-wire-test', name: 'Equipotential compilation fixture',
    frame_convention_id: 'power-invariant-park-q-lag-v1', reference_bus_id: 'b',
    base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 },
    buses: ['a', 'b', 'c', 'd', 'e'].map(id => ({ id, name: `Bus ${id}`, nominal_voltage_v: 400 })),
    lines: [
      { id: 'line-1', name: 'Original line', from_bus_id: 'a', to_bus_id: 'd', resistance_pu: 0.047,
        reactance_pu: 0.395, shunt_susceptance_pu: 0.017, thermal_limit_pu: 0.9, in_service: true },
      { id: 'line-2', name: 'Original reverse parallel', from_bus_id: 'd', to_bus_id: 'b', resistance_pu: 0.031,
        reactance_pu: 0.25, in_service: false },
    ],
    grid_forming_converters: [{ id: 'gfm-1', name: 'VSM', bus_id: 'a', control_mode: 'virtual_synchronous_machine',
      rated_apparent_power_va: 1e6, virtual_inertia_s: 2, damping_coefficient_pu: 60,
      active_power_measurement_time_constant_s: 0.1, parameter_set_id: 'original', active_power_setpoint_pu: 0.1 }],
    infinite_buses: [{ id: 'grid-1', name: 'Grid', bus_id: 'e', voltage_magnitude_pu: 1.02, voltage_angle_deg: 3 }],
    loads: [{ id: 'load-1', name: 'Load', bus_id: 'c', load_model: 'constant_power', active_power_pu: 0.1, reactive_power_pu: 0.03 }],
    source_metadata: { origin: 'retained fixture', nested: { tags: ['raw', 'do not replace'] } },
  }
}
const wire = (id, from, to) => ({ id, name: `Wire ${id}`, from_bus_id: from, to_bus_id: to })
function frozen(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(frozen)
    Object.freeze(value)
  }
  return value
}
let scenarios = 0
function test(name, run) {
  run()
  scenarios += 1
  console.log(`PASS ${name}`)
}

test('empty wires are identity without copying or altering API topology', () => {
  const topology = frozen(fixture())
  const result = compileIdealConnections(topology, [])
  assert.equal(result.ok, true)
  assert.strictEqual(result.topology, topology)
  assert.deepEqual(result.busMap, { a: 'a', b: 'b', c: 'c', d: 'd', e: 'e' })
  assert.deepEqual(result.groups, [['a'], ['b'], ['c'], ['d'], ['e']])
})

test('chain merges transitively and remaps every device while retaining original branches', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const wires = frozen([wire('wire-1', 'a', 'b'), wire('wire-2', 'b', 'c')])
  const result = compileIdealConnections(frozen(topology), wires)
  assert.equal(result.ok, true)
  assert.deepEqual(result.groups, [['a', 'b', 'c'], ['d'], ['e']])
  assert.deepEqual(result.busMap, { a: 'b', b: 'b', c: 'b', d: 'd', e: 'e' })
  assert.deepEqual(result.topology.buses.map(bus => bus.id), ['b', 'd', 'e'])
  assert.equal(result.topology.reference_bus_id, 'b')
  assert.deepEqual(result.topology.lines, before.lines.map(line => ({ ...line,
    from_bus_id: result.busMap[line.from_bus_id], to_bus_id: result.busMap[line.to_bus_id] })))
  assert.deepEqual(result.topology.grid_forming_converters, before.grid_forming_converters.map(device => ({ ...device, bus_id: 'b' })))
  assert.deepEqual(result.topology.loads, before.loads.map(device => ({ ...device, bus_id: 'b' })))
  assert.deepEqual(result.topology.infinite_buses, before.infinite_buses)
  assert.deepEqual(result.topology.source_metadata, before.source_metadata)
  assert.deepEqual(result.topology.base_values, before.base_values)
  assert.equal(result.topology.schema_version, '1.0')
  assert.deepEqual(topology, before)
  result.topology.lines[0].reactance_pu = 99
  result.topology.source_metadata.nested.tags.push('changed result')
  result.topology.base_values.frequency_hz = 60
  assert.deepEqual(topology, before, 'Output nested data must not alias input')
})

test('cycles are legal and order and orientation do not change representative selection', () => {
  const topology = fixture()
  const cycle = [wire('wire-1', 'a', 'b'), wire('wire-2', 'b', 'c'), wire('wire-3', 'c', 'a')]
  const first = compileIdealConnections(topology, cycle)
  const reversed = compileIdealConnections(topology, cycle.toReversed().map(item => ({ ...item,
    from_bus_id: item.to_bus_id, to_bus_id: item.from_bus_id })))
  assert.equal(first.ok, true)
  assert.equal(reversed.ok, true)
  assert.deepEqual(first.topology, reversed.topology)
  assert.deepEqual(first.busMap, reversed.busMap)
  assert.deepEqual(first.groups, reversed.groups)
  topology.reference_bus_id = 'e'
  const noReference = compileIdealConnections(topology, cycle)
  assert.equal(noReference.ok, true)
  assert.equal(noReference.busMap.c, 'a')
  assert.deepEqual(noReference.topology.buses.map(bus => bus.id), ['a', 'd', 'e'])
})

test('preexisting explicit parallel lines retain distinct IDs, impedance and service state', () => {
  const topology = fixture()
  topology.lines[1].to_bus_id = 'a'
  const before = structuredClone(topology)
  const result = compileIdealConnections(topology, [wire('wire-1', 'a', 'b')])
  assert.equal(result.ok, true)
  assert.equal(result.topology.lines.length, 2)
  assert.deepEqual(result.topology.lines, [
    { ...before.lines[0], from_bus_id: 'b' },
    { ...before.lines[1], to_bus_id: 'b' },
  ])
  assert.deepEqual(topology, before)
})

test('deleting a wire breaks only that constraint and deleting all restores original topology', () => {
  const topology = fixture()
  const wires = [wire('wire-1', 'a', 'b'), wire('wire-2', 'b', 'c')]
  const removed = removeIdealConnection(wires, 'wire-1')
  assert.deepEqual(wires, [wire('wire-1', 'a', 'b'), wire('wire-2', 'b', 'c')])
  const result = compileIdealConnections(topology, removed)
  assert.equal(result.ok, true)
  assert.deepEqual(result.busMap, { a: 'a', b: 'b', c: 'b', d: 'd', e: 'e' })
  assert.equal(result.topology.grid_forming_converters[0].bus_id, 'a')
  assert.equal(result.topology.loads[0].bus_id, 'b')
  assert.strictEqual(removeIdealConnection(wires, 'missing'), wires)
  const empty = removeIdealConnection(removed, 'wire-2')
  assert.strictEqual(compileIdealConnections(topology, empty).topology, topology)
})

test('new wire IDs avoid every equipment category and existing wires', () => {
  const topology = fixture()
  topology.buses[3].id = 'wire-1'
  topology.lines[0].id = 'wire-2'
  topology.grid_forming_converters[0].id = 'wire-3'
  topology.infinite_buses[0].id = 'wire-4'
  topology.loads[0].id = 'wire-5'
  const connections = [wire('wire-6', 'a', 'b')]
  const before = structuredClone({ topology, connections })
  const result = createIdealConnection(topology, connections, 'b', 'c')
  assert.equal(result.ok, true)
  assert.equal(result.connection.id, 'wire-7')
  assert.strictEqual(result.connections.at(-1), result.connection)
  assert.equal(result.connections.length, 2)
  assert.equal(Object.hasOwn(result.connection, 'resistance_pu'), false)
  assert.equal(Object.hasOwn(result.connection, 'reactance_pu'), false)
  assert.deepEqual({ topology, connections }, before)
})

test('creation rejects self, missing, cross-voltage and invalid-voltage endpoints without mutation', () => {
  for (const invalid of [null, 0, -1, NaN, Infinity, -Infinity, '400']) {
    const topology = fixture()
    topology.buses[2].nominal_voltage_v = invalid
    const before = structuredClone(topology)
    assert.equal(createIdealConnection(topology, [], 'a', 'c').ok, false)
    assert.deepEqual(topology, before)
  }
  const topology = fixture()
  topology.buses[2].nominal_voltage_v = 10000
  const before = structuredClone(topology)
  for (const [from, to] of [['a', 'a'], ['missing', 'a'], ['a', 'missing'], ['a', 'c'], ['c', 'a'], ['', 'b']]) {
    const result = createIdealConnection(topology, [], from, to)
    assert.equal(result.ok, false)
    assert.ok(result.message.trim())
    assert.deepEqual(topology, before)
  }
})

test('strict import rejects malformed types, unknown fields, duplicate IDs and bad references', () => {
  const topology = fixture()
  const good = wire('wire-1', 'a', 'b')
  const invalid = [undefined, null, {}, 'wire', [null], [[]], [1], [{ ...good, id: 1 }], [{ ...good, name: '' }],
    [{ ...good, name: '  ' }], [{ ...good, from_bus_id: null }], [{ ...good, to_bus_id: undefined }],
    [{ ...good, reactance_pu: 0 }], [{ ...good, kind: 'ac_line' }], [good, wire('wire-1', 'b', 'c')],
    [{ ...good, id: 'line-1' }], [{ ...good, id: 'a' }], [{ ...good, id: 'gfm-1' }],
    [{ ...good, id: 'grid-1' }], [{ ...good, id: 'load-1' }], [wire('wire-1', 'a', 'missing')],
    [wire('wire-1', 'a', 'a')], [good, wire('wire-2', 'b', 'a')]]
  const before = structuredClone(topology)
  for (const value of invalid) {
    assert.throws(() => parseIdealConnections(value, topology), error => error instanceof Error && /普通导线/.test(error.message))
    if (Array.isArray(value)) assert.equal(compileIdealConnections(topology, value).ok, false)
    assert.deepEqual(topology, before)
  }
  const parsed = parseIdealConnections([good], topology)
  assert.deepEqual(parsed, [good])
  assert.notStrictEqual(parsed[0], good)
  topology.buses[1].nominal_voltage_v = 10000
  assert.throws(() => parseIdealConnections([good], topology), /电压等级不同/)
})

test('duplicate unordered endpoints refuse creation while nonduplicate cyclic edges remain legal', () => {
  const topology = fixture()
  const wires = [wire('wire-1', 'a', 'b')]
  assert.equal(createIdealConnection(topology, wires, 'a', 'b').ok, false)
  assert.equal(createIdealConnection(topology, wires, 'b', 'a').ok, false)
  const invalidExisting = [wire('wire-1', 'a', 'b'), wire('wire-1', 'b', 'c')]
  assert.equal(createIdealConnection(topology, invalidExisting, 'a', 'c').ok, false)
})

test('shorted original line blocks compilation including out-of-service lines, never deletes it', () => {
  for (const inService of [true, false]) {
    const topology = fixture()
    topology.lines[0].in_service = inService
    const before = structuredClone(topology)
    const wires = [wire('wire-1', 'a', 'd')]
    assert.equal(createIdealConnection(topology, [], 'a', 'd').ok, true, 'Physical wire drawing is allowed')
    const result = compileIdealConnections(frozen(topology), frozen(wires))
    assert.equal(result.ok, false)
    assert.ok(result.issues.some(issue => issue.includes('line-1') && issue.includes('自环')))
    assert.deepEqual(topology, before)
    assert.equal(Object.hasOwn(result, 'topology'), false)
  }
})

test('multiple GFM, GFM plus grid and multiple ideal grids are explicit unsupported-source conflicts', () => {
  const examples = [
    ['多个 GFM', topology => topology.grid_forming_converters.push({ ...topology.grid_forming_converters[0], id: 'gfm-2', bus_id: 'b' }), 'a', 'b', ['gfm-1', 'gfm-2']],
    ['GFM', () => {}, 'a', 'e', ['gfm-1', 'grid-1']],
    ['理想电网', topology => topology.infinite_buses.push({ ...topology.infinite_buses[0], id: 'grid-2', bus_id: 'c' }), 'c', 'e', ['grid-1', 'grid-2']],
  ]
  for (const [phrase, arrange, from, to, ids] of examples) {
    const topology = fixture()
    arrange(topology)
    const before = structuredClone(topology)
    const created = createIdealConnection(topology, [], from, to)
    assert.equal(created.ok, true, 'Model limitation must not prohibit physical drawing')
    const result = compileIdealConnections(topology, created.connections)
    assert.equal(result.ok, false)
    assert.ok(result.issues.some(issue => issue.includes(phrase) && issue.includes('当前') && ids.every(id => issue.includes(id))))
    assert.deepEqual(topology, before)
  }
})

test('grid-only and load-only groups remap and preserve source parameters', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const result = compileIdealConnections(topology, [wire('wire-1', 'c', 'e')])
  assert.equal(result.ok, true)
  assert.deepEqual(result.topology.infinite_buses, before.infinite_buses.map(device => ({ ...device, bus_id: 'c' })))
  assert.deepEqual(result.topology.loads, before.loads)
  assert.deepEqual(topology, before)
})

test('dangling topology device references are blocked rather than mapped to undefined', () => {
  for (const mutate of [
    topology => { topology.reference_bus_id = 'missing' },
    topology => { topology.lines[0].from_bus_id = 'missing' },
    topology => { topology.grid_forming_converters[0].bus_id = 'missing' },
    topology => { topology.infinite_buses[0].bus_id = 'missing' },
    topology => { topology.loads[0].bus_id = 'missing' },
    topology => { topology.buses.push({ ...topology.buses[0] }) },
  ]) {
    const topology = fixture()
    mutate(topology)
    const before = structuredClone(topology)
    const result = compileIdealConnections(topology, [wire('wire-1', 'a', 'b')])
    assert.equal(result.ok, false)
    assert.ok(result.issues.length)
    assert.deepEqual(topology, before)
  }
})

test('special string IDs are safe map keys and endpoint pairs cannot collide', () => {
  const topology = fixture()
  topology.buses[0].id = '__proto__'
  topology.lines = []
  topology.grid_forming_converters = []
  const result = compileIdealConnections(topology, [wire('wire-1', '__proto__', 'b')])
  assert.equal(result.ok, true)
  assert.equal(result.busMap.__proto__, 'b')
  assert.equal(Object.hasOwn(result.busMap, '__proto__'), true)
})

console.log(`GFM_NETWORK_IDEAL_CONNECTIONS_OK (${scenarios} editing/compiler safety scenarios; no numerical or research claims)`)
