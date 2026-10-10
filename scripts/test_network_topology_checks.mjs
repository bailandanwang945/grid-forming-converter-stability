// Frontend connection/applicability checks only; not power flow or stability evidence.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkTopologyChecks.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual((compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { summarizeTopology } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)

function fixture() {
  return {
    schema_version: '1.0', id: 'connection-test-only', name: 'Connection test',
    frame_convention_id: 'power-invariant-park-q-lag-v1',
    base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 },
    reference_bus_id: 'grid-bus',
    buses: ['gfm-bus', 'grid-bus'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
    lines: [{ id: 'line-1', name: 'Line', from_bus_id: 'gfm-bus', to_bus_id: 'grid-bus',
      resistance_pu: 0.01, reactance_pu: 0.2, in_service: true }],
    grid_forming_converters: [{ id: 'gfm-1', name: 'VSM', bus_id: 'gfm-bus',
      control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
      virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
    infinite_buses: [{ id: 'grid-1', name: 'Grid', bus_id: 'grid-bus' }], loads: [],
  }
}
let scenarios = 0
function test(name, mutate, expected) {
  const topology = fixture()
  mutate(topology)
  const before = JSON.stringify(topology)
  const summary = summarizeTopology(topology)
  for (const [key, value] of Object.entries(expected)) assert.deepEqual(summary[key], value, `${name}: ${key}`)
  assert.equal(JSON.stringify(topology), before, `${name}: check must not mutate input`)
  if (!summary.wiringValid) assert.ok(summary.wiringIssues.length)
  if (!summary.lowFrequencyApplicable) assert.ok(summary.lowFrequencyIssues.length)
  scenarios += 1
}
test('connected VSM with reference', () => {}, { wiringValid: true, lowFrequencyApplicable: true, componentCount: 1, cycleRank: 0 })
test('no GFM is not a connection error', t => { t.grid_forming_converters = [] }, { wiringValid: true, lowFrequencyApplicable: false })
test('missing external reference is not a connection error', t => { t.infinite_buses = [] }, { wiringValid: true, lowFrequencyApplicable: false })
test('no source remains a saveable connection draft', t => { t.grid_forming_converters = []; t.infinite_buses = [] }, { wiringValid: true, lowFrequencyApplicable: false })
test('non-grid angular reference affects applicability', t => { t.reference_bus_id = 'gfm-bus' }, { wiringValid: true, lowFrequencyApplicable: false })
test('missing angular reference affects applicability', t => { t.reference_bus_id = 'missing-bus' }, { wiringValid: true, lowFrequencyApplicable: false })
test('disconnected but well-formed connection draft', t => { t.lines[0].in_service = false }, { wiringValid: true, lowFrequencyApplicable: false, componentCount: 2, isolatedBusIds: ['gfm-bus', 'grid-bus'] })
test('missing line endpoint', t => { t.lines[0].to_bus_id = 'missing-bus' }, { wiringValid: false, lowFrequencyApplicable: false, invalidLineIds: ['line-1'], componentCount: 2 })
test('self-loop', t => { t.lines[0].to_bus_id = 'gfm-bus' }, { wiringValid: false, lowFrequencyApplicable: false, invalidLineIds: ['line-1'] })
test('missing GFM attachment', t => { t.grid_forming_converters[0].bus_id = 'missing-bus' }, { wiringValid: false, lowFrequencyApplicable: false })
test('missing source attachment', t => { t.infinite_buses[0].bus_id = 'missing-bus' }, { wiringValid: false, lowFrequencyApplicable: false })
test('missing load attachment', t => { t.loads.push({ id: 'load-1', bus_id: 'missing-bus' }) }, { wiringValid: false, lowFrequencyApplicable: false })
test('duplicate global IDs', t => { t.grid_forming_converters[0].id = 'line-1' }, { wiringValid: false, lowFrequencyApplicable: false })
test('unsupported controller is not a connection error', t => { t.grid_forming_converters[0].control_mode = 'droop' }, { wiringValid: true, lowFrequencyApplicable: false })
test('multiple ideal sources at same bus', t => { t.infinite_buses.push({ id: 'grid-2', bus_id: 'grid-bus' }) }, { wiringValid: true, lowFrequencyApplicable: false })
test('multiple GFM at same bus exceeds low-frequency model scope', t => { t.grid_forming_converters.push({ ...t.grid_forming_converters[0], id: 'gfm-2' }) }, { wiringValid: true, lowFrequencyApplicable: false })
test('GFM attached to ideal source bus exceeds low-frequency model scope', t => { t.grid_forming_converters[0].bus_id = 'grid-bus' }, { wiringValid: true, lowFrequencyApplicable: false })
test('cross-voltage line is not a transformer', t => { t.buses[1].nominal_voltage_v = 10000 }, { wiringValid: false, lowFrequencyApplicable: false, invalidLineIds: ['line-1'] })
test('stopped invalid equipment is still malformed', t => { t.lines[0].in_service = false; t.lines[0].to_bus_id = 'missing-bus' }, { wiringValid: false, lowFrequencyApplicable: false })
test('parallel branches contribute a graph cycle', t => { t.lines.push({ ...t.lines[0], id: 'line-2' }) }, { wiringValid: true, lowFrequencyApplicable: true, cycleRank: 1 })
test('no bus is a connection error', t => { t.buses = []; t.lines = []; t.grid_forming_converters = []; t.infinite_buses = [] }, { wiringValid: false, lowFrequencyApplicable: false, componentCount: 0 })
const topology = fixture()
const before = summarizeTopology(topology)
const layout = { node_positions: { 'bus:gfm-bus': { x: 10, y: 20 } } }
layout.node_positions['bus:gfm-bus'] = { x: 200, y: 300 }
assert.deepEqual(summarizeTopology(topology), before, 'layout-only movement must not affect checks')
scenarios += 1
console.log(`GFM_NETWORK_TOPOLOGY_CHECKS_OK (${scenarios} connection/applicability scenarios; no numerical claims)`)
