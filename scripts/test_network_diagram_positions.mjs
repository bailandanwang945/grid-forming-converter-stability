// Layout-only regression: no browser, solver, network or electrical-model edits.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../apps/web/package.json', import.meta.url))
const ts = require('typescript')
const source = await readFile(new URL('../apps/web/src/networkDiagramPositions.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2020, module: ts.ModuleKind.ESNext },
  reportDiagnostics: true,
})
assert.deepEqual((compiled.diagnostics ?? []).filter(item => item.category === ts.DiagnosticCategory.Error), [])
const { mergeDiagramPositions, isFiniteDiagramPosition, mergeDiagramDimensions, mergeDiagramBusWidth, diagramBusWidth } =
  await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)

const allowed = new Set(['bus:1', 'gfm:1', 'grid:1', 'bus:2'])
const fixture = () => ({ schema_version: 'gfm-network-diagram-layout/1.0', node_positions: {
  'bus:1': { x: 100, y: 200 }, 'gfm:1': { x: 124, y: 56 }, 'grid:1': { x: 400, y: 332 },
} })
let scenarios = 0
function test(name, run) { run(); scenarios += 1; console.log(`PASS ${name}`) }

test('one source moves without rewriting other positions or mutating inputs', () => {
  const layout = fixture(), before = structuredClone(layout)
  const changes = [{ id: 'gfm:1', position: { x: 144, y: 76 } }]
  const result = mergeDiagramPositions(layout, changes, allowed)
  assert.deepEqual(layout, before)
  assert.notStrictEqual(result, layout)
  assert.strictEqual(result.node_positions['bus:1'], layout.node_positions['bus:1'])
  assert.deepEqual(result.node_positions['gfm:1'], changes[0].position)
  assert.notStrictEqual(result.node_positions['gfm:1'], changes[0].position)
  changes[0].position.x = 999
  assert.equal(result.node_positions['gfm:1'].x, 144)
})
test('missing position and unchanged snapped position retain the same layout object', () => {
  const layout = fixture()
  assert.strictEqual(mergeDiagramPositions(layout, [{ id: 'gfm:1' }], allowed), layout)
  assert.strictEqual(mergeDiagramPositions(layout, [{ id: 'gfm:1', position: { x: 124, y: 56 } }], allowed), layout)
})
test('NaN, infinity and null positions cannot poison the diagram', () => {
  const layout = fixture()
  for (const position of [undefined, null, { x: NaN, y: 1 }, { x: 1, y: Infinity }, { x: -Infinity, y: 1 }]) {
    assert.equal(isFiniteDiagramPosition(position), false)
    assert.strictEqual(mergeDiagramPositions(layout, [{ id: 'gfm:1', position }], allowed), layout)
  }
})
test('unknown or deleted nodes are not recreated by a stale event', () => {
  const layout = fixture()
  assert.strictEqual(mergeDiagramPositions(layout, [{ id: 'deleted:1', position: { x: 1, y: 2 } }], allowed), layout)
})
test('merging against the latest layout retains a just-inserted source and bus', () => {
  const old = fixture()
  const latest = { ...old, node_positions: { ...old.node_positions, 'bus:2': { x: 700, y: 300 } } }
  const result = mergeDiagramPositions(latest, [{ id: 'gfm:1', position: { x: 144, y: 56 } }], allowed)
  assert.deepEqual(result.node_positions['bus:2'], { x: 700, y: 300 })
})
test('sequential source moves preserve each other', () => {
  const first = mergeDiagramPositions(fixture(), [{ id: 'gfm:1', position: { x: 144, y: 56 } }], allowed)
  const second = mergeDiagramPositions(first, [{ id: 'grid:1', position: { x: 420, y: 352 } }], allowed)
  assert.deepEqual(second.node_positions['gfm:1'], { x: 144, y: 56 })
  assert.deepEqual(second.node_positions['grid:1'], { x: 420, y: 352 })
})
test('negative coordinates are valid; valid changes survive adjacent invalid events', () => {
  const layout = fixture()
  const result = mergeDiagramPositions(layout, [
    { id: 'gfm:1', position: { x: NaN, y: 10 } },
    { id: 'grid:1', position: { x: -20, y: -40 } },
  ], allowed)
  assert.strictEqual(result.node_positions['gfm:1'], layout.node_positions['gfm:1'])
  assert.deepEqual(result.node_positions['grid:1'], { x: -20, y: -40 })
})
test('real measured dimensions persist and do not alias observer notifications', () => {
  const measured = { 'bus:1': { width: 176, height: 88 } }
  const dimensions = { width: 128, height: 128 }
  const result = mergeDiagramDimensions(measured, [{ id: 'gfm:1', dimensions }], allowed)
  assert.deepEqual(measured, { 'bus:1': { width: 176, height: 88 } })
  assert.strictEqual(result['bus:1'], measured['bus:1'])
  assert.notStrictEqual(result['gfm:1'], dimensions)
  dimensions.width = 999
  assert.equal(result['gfm:1'].width, 128)
})
test('unchanged measurements do not trigger a node-rebuild loop', () => {
  const measured = { 'gfm:1': { width: 128, height: 128 } }
  assert.strictEqual(mergeDiagramDimensions(measured, [{ id: 'gfm:1', dimensions: { width: 128, height: 128 } }], allowed), measured)
})
test('hidden-tab zero dimensions and invalid sizes cannot clear measured nodes', () => {
  const measured = { 'gfm:1': { width: 128, height: 128 } }
  for (const dimensions of [undefined, { width: 0, height: 0 }, { width: NaN, height: 128 }, { width: 128, height: Infinity }]) {
    assert.strictEqual(mergeDiagramDimensions(measured, [{ id: 'gfm:1', dimensions }], allowed), measured)
  }
})
test('dimension events for deleted nodes are ignored', () => {
  const measured = {}
  assert.strictEqual(mergeDiagramDimensions(measured, [{ id: 'deleted:1', dimensions: { width: 128, height: 128 } }], allowed), measured)
})
test('bus width changes are layout-only, versioned and do not mutate coordinates', () => {
  const layout = fixture(), before = structuredClone(layout)
  assert.equal(diagramBusWidth(layout, '1'), 176)
  const changed = mergeDiagramBusWidth(layout, '1', 440)
  assert.deepEqual(layout, before)
  assert.strictEqual(changed.node_positions, layout.node_positions)
  assert.equal(changed.schema_version, 'gfm-network-diagram-layout/1.1')
  assert.equal(changed.bus_widths['1'], 440)
  assert.strictEqual(mergeDiagramBusWidth(changed, '1', 440), changed)
})
test('bus width is finite and bounded without changing other bus lengths', () => {
  const layout = { ...fixture(), bus_widths: { '2': 280 } }
  assert.strictEqual(mergeDiagramBusWidth(layout, '1', NaN), layout)
  assert.equal(mergeDiagramBusWidth(layout, '1', 1).bus_widths['1'], 128)
  const changed = mergeDiagramBusWidth(layout, '1', 2000)
  assert.equal(changed.bus_widths['1'], 1200)
  assert.equal(changed.bus_widths['2'], 280)
})
test('ordinary object prototype keys do not masquerade as a bus length', () => {
  assert.equal(diagramBusWidth({ ...fixture(), bus_widths: {} }, 'toString'), 176)
})
console.log(`GFM_NETWORK_DIAGRAM_POSITIONS_OK ${scenarios}`)
