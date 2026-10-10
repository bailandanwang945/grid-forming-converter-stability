// Pure palette/deletion operation safety: no browser, build or numerical analysis.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkPaletteOperations.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual((compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { insertCanvasElement, removeCanvasElement } =
  await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)

function fixture() {
  return {
    schema_version: '1.0', id: 'palette-operations-test-only', name: 'Palette safety fixture',
    frame_convention_id: 'power-invariant-park-q-lag-v1',
    base_values: { apparent_power_va: 2e6, voltage_v: 400, frequency_hz: 50 },
    reference_bus_id: 'bus-b',
    buses: ['bus-a', 'bus-b', 'bus-c', 'bus-d'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
    lines: [
      { id: 'line-1', name: 'Original branch', from_bus_id: 'bus-a', to_bus_id: 'bus-b',
        resistance_pu: 0.047, reactance_pu: 0.395, shunt_susceptance_pu: 0.017, in_service: false },
      { id: 'line-2', name: 'Load branch', from_bus_id: 'bus-b', to_bus_id: 'bus-c',
        resistance_pu: 0.01, reactance_pu: 0.2, thermal_limit_pu: 0.9, in_service: true },
    ],
    grid_forming_converters: [{ id: 'gfm-1', name: 'VSM', bus_id: 'bus-a',
      control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
      virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
    infinite_buses: [{ id: 'grid-1', name: 'Grid', bus_id: 'bus-b', voltage_magnitude_pu: 1.02, voltage_angle_deg: 7 }],
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

function unchanged(topology, operation, expectedOk) {
  const before = structuredClone(topology)
  const outcome = operation()
  assert.equal(outcome.ok, expectedOk)
  assert.equal(typeof outcome.message, 'string')
  assert.ok(outcome.message.trim())
  assert.deepEqual(topology, before, 'Entire original input must remain unchanged')
  if (outcome.ok) {
    assert.notStrictEqual(outcome.topology, topology)
    assert.notStrictEqual(outcome.topology.buses, topology.buses)
    assert.notStrictEqual(outcome.topology.base_values, topology.base_values)
  }
  return outcome
}

function insertion(topology, kind, position, targetBusId) {
  return unchanged(topology, () => insertCanvasElement(topology, kind, position, targetBusId), true)
}

test('bus placement preserves the exact top-left coordinate and reference voltage', () => {
  const topology = fixture()
  topology.buses[1].nominal_voltage_v = 10000
  const position = { x: -48, y: 312 }
  const result = insertion(topology, 'bus', position)
  const bus = result.topology.buses.at(-1)
  assert.deepEqual(bus, { id: 'bus-1', name: '母线 1', nominal_voltage_v: 10000 })
  assert.equal(result.selectedElement, 'bus:bus-1')
  assert.deepEqual(result.positions, { 'bus:bus-1': position })
  assert.notStrictEqual(result.positions[result.selectedElement], position)
  assert.deepEqual(result.topology.lines, topology.lines)
  assert.equal(result.topology.reference_bus_id, topology.reference_bus_id)
})

test('new bus falls back to base voltage when reference bus is absent', () => {
  const topology = fixture()
  topology.reference_bus_id = 'not-yet-created'
  topology.base_values.voltage_v = 690
  const result = insertion(topology, 'bus', { x: 0, y: 0 })
  assert.equal(result.topology.buses.at(-1).nominal_voltage_v, 690)
})

test('GFM explicit target uses Workbench defaults, adds no bus/line and keeps device position', () => {
  const topology = fixture()
  const position = { x: 144, y: 24 }
  const result = insertion(topology, 'gfm', position, 'bus-c')
  assert.deepEqual(result.topology.grid_forming_converters.at(-1), {
    id: 'gfm-2', name: 'VSM 2', bus_id: 'bus-c', rated_apparent_power_va: 2e6,
    control_mode: 'virtual_synchronous_machine', active_power_setpoint_pu: 0,
    reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1, virtual_inertia_s: 2,
    damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1,
  })
  assert.equal(result.selectedElement, 'gfm:gfm-2')
  assert.deepEqual(result.positions, { 'gfm:gfm-2': position })
  assert.deepEqual(result.topology.buses, topology.buses)
  assert.deepEqual(result.topology.lines, topology.lines)
  assert.ok(result.message.includes('bus-c'))
})

test('grid explicit target uses voltage/angle defaults and keeps the current reference', () => {
  const topology = fixture()
  const result = insertion(topology, 'grid', { x: 96, y: 420 }, 'bus-c')
  assert.deepEqual(result.topology.infinite_buses.at(-1), {
    id: 'grid-2', name: '无限大母线 2', bus_id: 'bus-c', voltage_magnitude_pu: 1, voltage_angle_deg: 0,
  })
  assert.deepEqual(result.positions, { 'grid:grid-2': { x: 96, y: 420 } })
  assert.equal(result.topology.reference_bus_id, 'bus-b')
  assert.deepEqual(result.topology.buses, topology.buses)
  assert.deepEqual(result.topology.lines, topology.lines)
})

test('GFM without a target creates a new attachment bus below without creating a line', () => {
  const topology = fixture()
  const result = insertion(topology, 'gfm', { x: 240, y: -24 })
  assert.equal(result.topology.grid_forming_converters.at(-1).bus_id, 'bus-1')
  assert.equal(result.topology.buses.at(-1).id, 'bus-1')
  assert.deepEqual(result.positions, {
    'bus:bus-1': { x: 216, y: 120 }, 'gfm:gfm-2': { x: 240, y: -24 },
  })
  assert.deepEqual(result.topology.lines, topology.lines)
  assert.ok(result.message.includes('新增接入母线 bus-1'))
  assert.ok(result.message.includes('未自动添加线路'))
})

test('grid without a target creates a new attachment bus above without creating a line', () => {
  const topology = fixture()
  const result = insertion(topology, 'grid', { x: 264, y: 432 })
  assert.equal(result.topology.infinite_buses.at(-1).bus_id, 'bus-1')
  assert.deepEqual(result.positions, {
    'bus:bus-1': { x: 240, y: 300 }, 'grid:grid-2': { x: 264, y: 432 },
  })
  assert.equal(result.topology.reference_bus_id, 'bus-b')
  assert.deepEqual(result.topology.lines, topology.lines)
  assert.ok(result.message.includes('新增接入母线 bus-1'))
  assert.ok(result.message.includes('未自动添加线路'))
})

test('a first grid synchronizes reference to either an existing or a newly created bus', () => {
  for (const target of ['bus-c', undefined]) {
    const topology = fixture()
    topology.infinite_buses = []
    const result = insertion(topology, 'grid', { x: 120, y: 360 }, target)
    assert.equal(result.topology.reference_bus_id, result.topology.infinite_buses[0].bus_id)
    assert.equal(result.topology.infinite_buses[0].id, 'grid-1')
  }
})

test('empty-source and empty-bus drafts can be built incrementally', () => {
  const topology = fixture()
  topology.buses = []
  topology.lines = []
  topology.loads = []
  topology.grid_forming_converters = []
  topology.infinite_buses = []
  topology.reference_bus_id = ''
  for (const kind of ['bus', 'gfm', 'grid']) {
    const result = insertion(topology, kind, { x: 0, y: 0 })
    assert.equal(result.topology.buses.length, 1)
    assert.equal(result.topology.buses[0].nominal_voltage_v, 400)
  }
})

test('both source types reject targets occupied by either source type without mutation', () => {
  for (const kind of ['gfm', 'grid']) {
    for (const target of ['bus-a', 'bus-b']) {
      const topology = fixture()
      const result = unchanged(topology, () => insertCanvasElement(topology, kind, { x: 0, y: 0 }, target), false)
      assert.ok(result.message.includes(target))
      assert.ok(result.message.includes('只能接入一个电源'))
    }
  }
})

test('missing and empty explicit targets are refused instead of silently creating a bus', () => {
  for (const kind of ['gfm', 'grid']) {
    for (const target of ['missing-bus', '']) {
      const topology = fixture()
      unchanged(topology, () => insertCanvasElement(topology, kind, { x: 0, y: 0 }, target), false)
    }
  }
})

test('non-finite and non-numeric positions are rejected for all element types', () => {
  for (const kind of ['bus', 'gfm', 'grid']) {
    for (const value of [NaN, Infinity, -Infinity, undefined, '24']) {
      for (const axis of ['x', 'y']) {
        const topology = fixture()
        const position = { x: 0, y: 0, [axis]: value }
        unchanged(topology, () => insertCanvasElement(topology, kind, position), false)
      }
    }
  }
})

test('invalid inherited voltage is rejected only when adding a new bus', () => {
  for (const value of [NaN, Infinity, -Infinity, 0, -400]) {
    for (const kind of ['bus', 'gfm', 'grid']) {
      const topology = fixture()
      topology.buses[1].nominal_voltage_v = value
      unchanged(topology, () => insertCanvasElement(topology, kind, { x: 0, y: 0 }), false)
      if (kind !== 'bus') insertion(topology, kind, { x: 0, y: 0 }, 'bus-c')
    }
    const topology = fixture()
    topology.reference_bus_id = 'missing'
    topology.base_values.voltage_v = value
    unchanged(topology, () => insertCanvasElement(topology, 'bus', { x: 0, y: 0 }), false)
  }
})

test('invalid base rating cannot become a new GFM rating', () => {
  for (const value of [NaN, Infinity, -Infinity, 0, -1]) {
    const topology = fixture()
    topology.base_values.apparent_power_va = value
    for (const target of ['bus-c', undefined]) {
      unchanged(topology, () => insertCanvasElement(topology, 'gfm', { x: 0, y: 0 }, target), false)
    }
  }
})

test('IDs avoid every entity collection for each palette kind', () => {
  for (const kind of ['bus', 'gfm', 'grid']) {
    const topology = fixture()
    topology.buses.push({ id: `${kind}-1`, name: 'Occupied bus ID', nominal_voltage_v: 400 })
    topology.lines[0].id = `${kind}-2`
    topology.grid_forming_converters[0].id = `${kind}-3`
    topology.infinite_buses[0].id = `${kind}-4`
    topology.loads[0].id = `${kind}-5`
    const result = insertion(topology, kind, { x: 0, y: 0 }, kind === 'bus' ? undefined : 'bus-c')
    assert.equal(result.selectedElement, `${kind}:${kind}-6`)
  }
})

test('automatic attachment bus IDs also avoid the complete entity collection', () => {
  for (const kind of ['gfm', 'grid']) {
    const topology = fixture()
    topology.buses.push({ id: 'bus-1', name: 'Occupied bus ID', nominal_voltage_v: 400 })
    topology.lines[0].id = 'bus-2'
    topology.grid_forming_converters[0].id = 'bus-3'
    topology.infinite_buses[0].id = 'bus-4'
    topology.loads[0].id = 'bus-5'
    const result = insertion(topology, kind, { x: 0, y: 0 })
    assert.equal(result.topology.buses.at(-1).id, 'bus-6')
    assert.ok(result.positions['bus:bus-6'])
  }
})

test('returned insertion topology and position objects do not alias inputs', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const position = { x: 24, y: 48 }
  const result = insertion(topology, 'gfm', position)
  result.topology.buses[0].name = 'Changed clone'
  result.topology.lines[0].reactance_pu = 123
  result.topology.loads[0].active_power_pu = 123
  result.topology.base_values.voltage_v = 123
  result.positions[result.selectedElement].x = 123
  assert.deepEqual(topology, before)
  assert.deepEqual(position, { x: 24, y: 48 })
})

test('line deletion removes only that line and needs no node-layout cleanup', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const result = unchanged(topology, () => removeCanvasElement(topology, 'line:line-1'), true)
  assert.deepEqual(result.topology, { ...before, lines: [before.lines[1]] })
  assert.deepEqual(result.removedNodeIds, [])
})

test('last GFM can be deleted while preserving the attachment bus and lines', () => {
  const topology = fixture()
  const before = structuredClone(topology)
  const result = unchanged(topology, () => removeCanvasElement(topology, 'gfm:gfm-1'), true)
  assert.deepEqual(result.topology, { ...before, grid_forming_converters: [] })
  assert.deepEqual(result.removedNodeIds, ['gfm:gfm-1'])
})

test('last ideal grid cannot be deleted directly or through its attachment bus', () => {
  for (const selection of ['grid:grid-1', 'bus:bus-b']) {
    const topology = fixture()
    const result = unchanged(topology, () => removeCanvasElement(topology, selection), false)
    assert.ok(result.message.includes('至少需要保留一个无限大母线'))
  }
})

test('grid deletion retains its bus and repairs reference to the remaining grid', () => {
  const topology = fixture()
  topology.infinite_buses.push({ id: 'grid-2', name: 'Second grid', bus_id: 'bus-d' })
  const before = structuredClone(topology)
  const result = unchanged(topology, () => removeCanvasElement(topology, 'grid:grid-1'), true)
  assert.deepEqual(result.topology, { ...before, infinite_buses: [before.infinite_buses[1]], reference_bus_id: 'bus-d' })
  assert.deepEqual(result.removedNodeIds, ['grid:grid-1'])
  const nonReference = unchanged(topology, () => removeCanvasElement(topology, 'grid:grid-2'), true)
  assert.equal(nonReference.topology.reference_bus_id, 'bus-b')
})

test('bus deletion cascades to attached devices, loads and incident lines only', () => {
  const topology = fixture()
  topology.grid_forming_converters.push({ ...topology.grid_forming_converters[0], id: 'gfm-2', bus_id: 'bus-c' })
  topology.infinite_buses.push({ id: 'grid-2', name: 'Second grid', bus_id: 'bus-c' })
  const result = unchanged(topology, () => removeCanvasElement(topology, 'bus:bus-c'), true)
  assert.deepEqual(result.topology.buses.map(item => item.id), ['bus-a', 'bus-b', 'bus-d'])
  assert.deepEqual(result.topology.lines, [topology.lines[0]])
  assert.deepEqual(result.topology.grid_forming_converters, [topology.grid_forming_converters[0]])
  assert.deepEqual(result.topology.infinite_buses, [topology.infinite_buses[0]])
  assert.deepEqual(result.topology.loads, [])
  assert.deepEqual(result.removedNodeIds, ['bus:bus-c', 'gfm:gfm-2', 'grid:grid-2'])
  assert.equal(result.topology.reference_bus_id, 'bus-b')
})

test('deleting a reference bus selects the surviving ideal grid reference', () => {
  const topology = fixture()
  topology.infinite_buses.push({ id: 'grid-2', name: 'Second grid', bus_id: 'bus-d' })
  const result = unchanged(topology, () => removeCanvasElement(topology, 'bus:bus-b'), true)
  assert.equal(result.topology.reference_bus_id, 'bus-d')
  assert.deepEqual(result.topology.lines, [])
  assert.deepEqual(result.removedNodeIds, ['bus:bus-b', 'grid:grid-1'])
})

test('grid-free drafts permit bus deletion and repair reference to the first remaining bus', () => {
  const topology = fixture()
  topology.grid_forming_converters = []
  topology.infinite_buses = []
  const result = unchanged(topology, () => removeCanvasElement(topology, 'bus:bus-b'), true)
  assert.equal(result.topology.reference_bus_id, 'bus-a')
  assert.deepEqual(result.topology.grid_forming_converters, [])
  assert.deepEqual(result.topology.infinite_buses, [])
})

test('bus deletion cannot reduce a two-bus draft and can reduce three buses to two', () => {
  const topology = fixture()
  topology.buses = topology.buses.slice(0, 2)
  topology.loads = []
  topology.lines = topology.lines.slice(0, 1)
  unchanged(topology, () => removeCanvasElement(topology, 'bus:bus-a'), false)
  topology.buses.push({ id: 'bus-c', name: 'Third bus', nominal_voltage_v: 400 })
  const result = unchanged(topology, () => removeCanvasElement(topology, 'bus:bus-c'), true)
  assert.equal(result.topology.buses.length, 2)
})

test('even an inconsistent draft cannot delete all grids sharing one attachment bus', () => {
  const topology = fixture()
  topology.infinite_buses.push({ id: 'grid-2', name: 'Same bus grid', bus_id: 'bus-b' })
  unchanged(topology, () => removeCanvasElement(topology, 'bus:bus-b'), false)
})

test('missing/invalid selection and unknown kinds fail without mutation', () => {
  for (const selection of [null, '', 'bus:', 'bus', 'unknown:bus-a', 'bus:missing', 'gfm:missing', 'grid:missing', 'line:missing']) {
    const topology = fixture()
    unchanged(topology, () => removeCanvasElement(topology, selection), false)
  }
  const topology = fixture()
  unchanged(topology, () => insertCanvasElement(topology, 'load', { x: 0, y: 0 }), false)
})

test('deletion clone is independent and entity IDs containing colons remain addressable', () => {
  const topology = fixture()
  topology.grid_forming_converters[0].id = 'source:one'
  const before = structuredClone(topology)
  const result = unchanged(topology, () => removeCanvasElement(topology, 'gfm:source:one'), true)
  assert.deepEqual(result.removedNodeIds, ['gfm:source:one'])
  result.topology.buses[0].name = 'Changed clone'
  result.topology.lines[0].resistance_pu = 123
  result.topology.base_values.frequency_hz = 123
  assert.deepEqual(topology, before)
})

console.log(`GFM_NETWORK_PALETTE_OPERATIONS_OK (${scenarios} operation-safety scenarios; no numerical claims)`)
