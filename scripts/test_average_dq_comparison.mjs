// Pure input-difference tests; no numerical analysis or backend is performed.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import ts from '../apps/web/node_modules/typescript/lib/typescript.js'

const source = readFileSync(fileURLToPath(new URL('../apps/web/src/averageDQComparison.ts', import.meta.url)), 'utf8')
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext } }).outputText
const { describeCaseInputChanges: changes, formatCaseInputValue: format } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const input = { topology: { grid_forming_converters: [{ damping_coefficient_pu: 60 }], lines: [{ reactance_pu: 0.3 }] },
  parameters: { modulation_time_constant_s: 0.001 }, simulation_time_s: 2, time_step_s: 0.002,
  initial_angle_perturbation_rad: 0.0001, frequency_values_hz: [0.1, 1, 10] }
const clone = value => JSON.parse(JSON.stringify(value))
let count = 0
function test(name, action) { action(); count += 1; console.log(`PASS ${name}`) }
test('identical inputs have no changes', () => assert.deepEqual(changes(input, clone(input)), []))
test('damping changes are named and retain raw values', () => {
  const next = clone(input); next.topology.grid_forming_converters[0].damping_coefficient_pu = 50
  assert.deepEqual(changes(input, next), [{ field: 'topology.grid_forming_converters.0.damping_coefficient_pu',
    label: '变流器1 · 阻尼系数 D', before: 60, after: 50 }])
})
test('line and parameter changes are both retained', () => {
  const next = clone(input); next.topology.lines[0].reactance_pu = 0.4; next.parameters.modulation_time_constant_s = 0.002
  assert.deepEqual(changes(input, next).map(row => row.field), ['topology.lines.0.reactance_pu', 'parameters.modulation_time_constant_s'])
})
test('frequency changes preserve the entire grids, including interior points', () => {
  const next = clone(input); next.frequency_values_hz = [0.1, 2, 10]
  assert.deepEqual(changes(input, next), [{ field: 'frequency_values_hz', label: '导纳频率网格 / Hz', before: [0.1, 1, 10], after: [0.1, 2, 10] }])
})
test('simulation-only changes are visible', () => {
  const next = clone(input); next.simulation_time_s = 3; next.time_step_s = 0.005
  assert.deepEqual(changes(input, next).map(row => row.field), ['simulation_time_s', 'time_step_s'])
})
test('object key order is not a physical input change', () => {
  const next = Object.fromEntries(Object.entries(input).reverse()); assert.deepEqual(changes(input, next), [])
})
test('changes do not modify inputs', () => {
  const a = clone(input), b = clone(input); b.simulation_time_s = 3
  const expected = JSON.stringify([a, b]); changes(a, b); assert.equal(JSON.stringify([a, b]), expected)
})
test('display values have explicit null and boolean meanings', () => {
  assert.equal(format(null), '未设置'); assert.equal(format(true), '是'); assert.equal(format(false), '否')
  assert.equal(format([0.1, 1, 10]), '3 点（0.1 至 10）'); assert.equal(format(0.0001), '0.0001')
})
console.log(`GFM_AVERAGE_DQ_COMPARISON_OK (${count} pure-input scenarios)`)
