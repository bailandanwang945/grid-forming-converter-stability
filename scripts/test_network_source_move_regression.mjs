// New-source short-drag regression. UI only: no builds, solvers or installs.
// node scripts/test_network_source_move_regression.mjs --dev|--dist|--real|--resize-gate|--both
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../apps/web/node_modules/playwright-core/index.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = resolve(root, 'apps/web/dist')
const reviewDir = resolve(root, 'output/ui-review/network-source-move-20261007')
const executablePath = [process.env.GFM_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find(existsSync)
assert.ok(executablePath, 'Installed Chrome or Edge required; this script installs nothing.')
const fixture = {
  schema_version: '1.0', id: 'source-move-ui-only', name: '新插入电源短拖测试',
  frame_convention_id: 'power-invariant-park-q-lag-v1',
  base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 }, reference_bus_id: 'grid-bus',
  buses: ['bus-1', 'grid-bus', 'free-bus'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
  lines: [{ id: 'line-1', name: '线路 1', from_bus_id: 'bus-1', to_bus_id: 'grid-bus',
    resistance_pu: 0.01, reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true }],
  grid_forming_converters: [{ id: 'gfm-1', name: 'VSM 1', bus_id: 'bus-1',
    control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
    active_power_setpoint_pu: 0, reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1,
    virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
  infinite_buses: [{ id: 'grid-1', name: '等值电源', bus_id: 'grid-bus', voltage_magnitude_pu: 1, voltage_angle_deg: 0 }],
  loads: [],
}
const arg = process.argv[2] ?? '--dist'
assert.ok(['--dev', '--dist', '--real', '--resize-gate', '--both'].includes(arg), 'Use --dev, --dist, --real, --resize-gate or --both.')
let browser, server
const failures = []
const frame = page => page.evaluate(() => new Promise(done => requestAnimationFrame(() => requestAnimationFrame(done))))
const inspectGraph = page => page.evaluate(() => {
  const editor = document.querySelector('[data-testid="network-graph-editor"]')
  const rect = element => { const r = element.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height } }
  const style = element => {
    if (!element) return null
    const s = getComputedStyle(element)
    return { display: s.display, opacity: s.opacity, visibility: s.visibility, overflow: s.overflow, clipPath: s.clipPath, transform: s.transform, rect: rect(element) }
  }
  const viewport = editor?.querySelector('.react-flow__viewport')
  const flow = editor?.querySelector('.react-flow')
  let flowStore = null
  let fiber = flow && flow[Object.keys(flow).find(key => key.startsWith('__reactFiber$'))]
  for (let depth = 0; fiber && depth < 100; depth += 1, fiber = fiber.return) {
    let dependency = fiber.dependencies?.firstContext
    const values = [fiber.memoizedProps?.value]
    while (dependency) { values.push(dependency.memoizedValue); dependency = dependency.next }
    const api = values.find(value => typeof value?.getState === 'function')
    if (!api) continue
    const state = api.getState()
    if (!Array.isArray(state.nodes) || !state.nodeLookup) continue
    flowStore = {
      transform: state.transform, width: state.width, height: state.height,
      nodes: state.nodes.map(node => ({ id: node.id, position: node.position, selected: node.selected, measured: node.measured })),
      internals: [...state.nodeLookup.entries()].map(([id, node]) => ({ id, position: node.position, positionAbsolute: node.internals?.positionAbsolute, measured: node.measured })),
    }
    break
  }
  return {
    editorPresent: Boolean(editor), canvasPresent: Boolean(editor?.querySelector('.network-graph-canvas')),
    editorGeometry: style(editor), canvasGeometry: style(editor?.querySelector('.network-graph-canvas')),
    flowGeometry: style(flow), viewportGeometry: style(viewport), flowStore,
    viewportStyle: viewport?.getAttribute('style') ?? null,
    viewportTransform: viewport ? getComputedStyle(viewport).transform : null,
    nodes: [...(editor?.querySelectorAll('.react-flow__node') ?? [])].map(element => ({
      id: element.getAttribute('data-id'), style: element.getAttribute('style'), rect: rect(element), geometry: style(element), text: element.textContent,
    })),
    edges: [...(editor?.querySelectorAll('.react-flow__edge') ?? [])].map(element => element.getAttribute('data-id')),
    bodyText: editor ? undefined : document.body.innerText.slice(-1600),
  }
})
const until = async (predicate, label) => {
  const deadline = Date.now() + 4000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(done => setTimeout(done, 20))
  }
  throw new Error(`Timed out: ${label}`)
}
async function runVariant(variant, baseUrl) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  const forbiddenApi = []
  await context.route('**/*', route => new URL(route.request().url()).origin === new URL(baseUrl).origin ? route.continue() : route.abort())
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reduced-order/presets') {
      await route.fulfill({ json: { presets: ['stable', 'marginal', 'unstable'].map(kind => ({
        id: `reduced-smib-${kind}`, name: `UI ${kind}`, topology: structuredClone(fixture),
      })) } }); return
    }
    forbiddenApi.push(path)
    await route.fulfill({ status: 422, json: { detail: 'UI-only test: solvers and report APIs are disabled.' } })
  })
  let timer
  const results = []
  try {
    await Promise.race([(async () => {
      for (const tool of ['gfm', 'grid']) for (const placement of ['blank', 'existing-bus']) {
        for (const [target, dx, dy] of [['body', 5, 5], ['body', 20, 12], ['name', 12, -8], ['bus', 20, 12]]) {
          const name = `${variant}-${tool}-${placement}-${target}-${dx}px`
          const page = await context.newPage()
          page.setDefaultTimeout(4000)
          const pageErrors = [], consoleErrors = []
          page.on('pageerror', error => pageErrors.push({ message: error.message, stack: error.stack }))
          page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
          const editor = page.getByTestId('network-graph-editor')
          const canvas = editor.locator('.network-graph-canvas')
          const node = id => page.getByTestId(`network-node-${id}`)
          const snapshot = () => inspectGraph(page)
          const save = async () => {
            const [download] = await Promise.all([
              page.waitForEvent('download'), page.getByRole('button', { name: '保存案例', exact: true }).click(),
            ])
            return JSON.parse(readFileSync(await download.path(), 'utf8'))
          }
          const visiblePoint = async (id, part = 'body') => {
            await node(id).scrollIntoViewIfNeeded()
            return node(id).evaluate((element, part) => {
              const child = element.querySelector(part === 'name' ? '.electrical-node-label b' : '.electrical-node-symbol')
              if (!child) throw new Error(`Missing node target ${part}`)
              const r = child.getBoundingClientRect()
              const point = { x: r.x + r.width / 2, y: r.y + r.height / 2 }
              const hit = document.elementFromPoint(point.x, point.y)
              const actual = hit?.closest('.react-flow__node')?.getAttribute('data-id')
              const expected = element.closest('.react-flow__node')?.getAttribute('data-id')
              if (actual !== expected || hit?.closest('.react-flow__handle')) throw new Error(`Wrong real pointer target: ${JSON.stringify({ actual, expected, part })}`)
              return { ...point, actual, tag: hit.tagName, className: hit.getAttribute('class') }
            }, part)
          }
          const blankPoint = async () => {
            await canvas.scrollIntoViewIfNeeded()
            return canvas.evaluate(element => {
              const r = element.getBoundingClientRect()
              for (const [fx, fy] of [[0.78, 0.48], [0.3, 0.55], [0.65, 0.5], [0.85, 0.7], [0.15, 0.65]]) {
                const p = { x: r.x + r.width * fx, y: r.y + r.height * fy }
                if (p.y < 10 || p.y > innerHeight - 10) continue
                const hit = document.elementFromPoint(p.x, p.y)
                if (hit?.closest('.network-graph-canvas') === element && !hit.closest('.react-flow__node, .react-flow__edge')) return p
              }
              throw new Error('No visible real blank-canvas hit point')
            })
          }
          let record = { name, dx, dy, pageErrors, consoleErrors }
          try {
            await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 10000 })
            await page.getByRole('button', { name: /网络建模/ }).click()
            await editor.waitFor()
            await until(() => node('free-bus').count().then(count => count === 1), 'mock fixture')
            await editor.scrollIntoViewIfNeeded()
            await page.evaluate(() => new Promise(done => setTimeout(done, 350)))
            const before = await save()
            assert.equal(before.topology.buses.length, fixture.buses.length)
            const oldIds = await canvas.locator('.react-flow__node').evaluateAll(elements => elements.map(element => element.getAttribute('data-id')))
            const palette = page.getByTestId(`network-palette-${tool}`)
            await palette.scrollIntoViewIfNeeded()
            const source = await palette.boundingBox(); assert.ok(source)
            await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2)
            await page.mouse.down(); await frame(page)
            const drop = placement === 'blank' ? await blankPoint() : await visiblePoint('free-bus')
            await page.mouse.move(drop.x, drop.y, { steps: 8 }); await page.mouse.up(); await frame(page)
            const ids = await canvas.locator('.react-flow__node').evaluateAll(elements => elements.map(element => element.getAttribute('data-id')))
            const sourceId = ids.find(id => id?.startsWith(`${tool}:`) && !oldIds.includes(id))
            assert.ok(sourceId, 'Real palette drop must insert a new source')
            const newBusId = placement === 'blank' ? ids.find(id => id?.startsWith('bus:') && !oldIds.includes(id)) : 'bus:free-bus'
            assert.ok(newBusId, 'New source must have its target bus')
            record.sourceId = sourceId; record.busId = newBusId; record.drop = drop
            record.afterInsert = await snapshot()
            // Important: no save/import/undo/fit between insertion and first short drag.
            const draggedId = target === 'bus' ? newBusId : sourceId
            const pointer = await visiblePoint(draggedId.slice(draggedId.indexOf(':') + 1), target === 'name' ? 'name' : 'body')
            record.pointer = pointer
            await page.mouse.move(pointer.x, pointer.y); await page.mouse.down()
            await page.mouse.move(pointer.x + dx, pointer.y + dy, { steps: 5 }); await page.mouse.up(); await frame(page)
            record.afterMove = await snapshot()
            assert.deepEqual(pageErrors, [], 'No uncaught browser error on first short drag')
            assert.equal(record.afterMove.editorPresent, true, 'Editor survives source drag')
            assert.deepEqual(record.afterMove.nodes.map(item => item.id).sort(), ids.sort(), 'Graph nodes survive source drag')
            assert.equal(record.afterMove.edges.length, record.afterInsert.edges.length, 'Graph edges survive source drag')
            assert.equal(record.afterMove.viewportTransform, record.afterInsert.viewportTransform, 'A central source drag must not teleport the viewport')
            const after = await save()
            const collection = tool === 'gfm' ? 'grid_forming_converters' : 'infinite_buses'
            const added = after.topology[collection].filter(item => !before.topology[collection].some(old => old.id === item.id))
            assert.equal(added.length, 1)
            assert.equal(added[0].bus_id, newBusId.slice(4))
            assert.equal(after.topology.buses.length, before.topology.buses.length + (placement === 'blank' ? 1 : 0))
            for (const position of Object.values(after.diagram_layout.node_positions)) assert.ok(Number.isFinite(position.x) && Number.isFinite(position.y))
            const movedBefore = record.afterInsert.nodes.find(item => item.id === draggedId)
            const movedAfter = record.afterMove.nodes.find(item => item.id === draggedId)
            // A 5px gesture may legitimately stay within the 20-unit snap cell.
            if (dx >= 12) assert.notEqual(movedAfter.style, movedBefore.style, 'Real-pointer drag beyond the snap cell moves the target')
            record.targetMoved = movedAfter.style !== movedBefore.style
            record.savedPositions = after.diagram_layout.node_positions
            // Save once more to reject one-frame/stale export snapshots.
            const second = await save()
            assert.deepEqual(second.topology, after.topology)
            assert.deepEqual(second.diagram_layout, after.diagram_layout)
            record.status = 'pass'
            console.log(`PASS ${name} (${dx},${dy}px)`)
          } catch (error) {
            record.status = 'fail'; record.error = error.stack
            record.afterFailure = await snapshot().catch(snapshotError => ({ error: snapshotError.message }))
            mkdirSync(reviewDir, { recursive: true })
            record.screenshot = resolve(reviewDir, `${name}-failure.png`)
            await page.screenshot({ path: record.screenshot, fullPage: true }).catch(() => {})
            failures.push(record)
            const compact = value => value && ({ ...value, nodes: value.nodes?.map(({ id, style, rect }) => ({ id, style, rect })) })
            console.log(`FAIL ${name}\n${JSON.stringify({ ...record, afterInsert: compact(record.afterInsert), afterMove: compact(record.afterMove), afterFailure: compact(record.afterFailure) })}`)
          } finally {
            results.push(record)
            await page.close().catch(() => {})
          }
        }
      }
      assert.deepEqual(forbiddenApi, [], 'No numerical or report API may be called')
    })(), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${variant} exceeded its 60-second total limit`)), 60000) })])
  } finally {
    clearTimeout(timer)
    await context.close().catch(() => {})
    console.log(`${variant.toUpperCase()} SUMMARY ${JSON.stringify({ scenarios: results.length, passed: results.filter(item => item.status === 'pass').length, failed: results.filter(item => item.status === 'fail').length, forbiddenApi })}`)
  }
}
async function runRealVariant(baseUrl, resizeGate = false, mockPresets = false) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
  if (resizeGate) await context.addInitScript(() => {
    const NativeResizeObserver = window.ResizeObserver
    const gate = { paused: false, pending: new Map(), release() {
      this.paused = false
      const pending = [...this.pending.values()]
      this.pending.clear()
      pending.forEach(invoke => invoke())
      return pending.length
    } }
    window.__gfmResizeGate = gate
    window.ResizeObserver = class extends NativeResizeObserver {
      constructor(callback) { super((entries, observer) => {
        const invoke = () => callback(entries, observer)
        if (gate.paused) gate.pending.set(observer, invoke)
        else invoke()
      }) }
    }
  })
  const forbiddenApi = [], presetReads = [], records = []
  await context.route('**/*', route => new URL(route.request().url()).origin === new URL(baseUrl).origin ? route.continue() : route.abort())
  await context.route('**/api/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    if (request.method() === 'GET' && path === '/api/reduced-order/presets') {
      presetReads.push(path)
      if (mockPresets) await route.fulfill({ json: { presets: ['stable', 'marginal', 'unstable'].map(kind => ({
        id: `reduced-smib-${kind}`, name: `UI ${kind}`, topology: structuredClone(fixture),
      })) } })
      else await route.continue()
      return
    }
    forbiddenApi.push(`${request.method()} ${path}`)
    await route.fulfill({ status: 422, json: { detail: 'Real-presets UI test: all solvers and report APIs disabled.' } })
  })
  let timer
  try {
    await Promise.race([(async () => {
      for (const width of resizeGate ? [1440] : [1440, 1024]) for (const snap of resizeGate ? [true] : [true, false]) {
        const page = await context.newPage()
        await page.setViewportSize({ width, height: 1000 })
        page.setDefaultTimeout(4000)
        const record = { name: `${mockPresets ? 'dist-' : ''}${resizeGate ? 'resize-gate' : 'real'}-${width}-snap-${snap}`, pageErrors: [], consoleErrors: [], gestures: [] }
        page.on('pageerror', error => record.pageErrors.push({ message: error.message, stack: error.stack }))
        page.on('console', message => { if (message.type() === 'error') record.consoleErrors.push(message.text()) })
        const editor = page.getByTestId('network-graph-editor'), canvas = editor.locator('.network-graph-canvas')
        const save = async () => {
          const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: '保存案例', exact: true }).click()])
          return JSON.parse(readFileSync(await download.path(), 'utf8'))
        }
        const point = async (id, part = 'body') => {
          const node = editor.locator(`.react-flow__node[data-id="${id}"]`)
          await node.scrollIntoViewIfNeeded()
          return node.evaluate((element, part) => {
            const child = element.querySelector(part === 'name' ? '.electrical-node-label b' : '.electrical-node-symbol')
            const r = child.getBoundingClientRect(), p = { x: r.x + r.width / 2, y: r.y + r.height / 2 }
            const hit = document.elementFromPoint(p.x, p.y)
            if (hit?.closest('.react-flow__node') !== element || hit?.closest('.react-flow__handle')) throw new Error(`Wrong node pointer target for ${part}`)
            return p
          }, part)
        }
        const drag = async (id, part, dx, dy, selected = false) => {
          const before = await inspectGraph(page)
          if (selected) assert.equal(await editor.locator(`.react-flow__node[data-id="${id}"]`).evaluate(element => element.classList.contains('selected')), true, 'New source is selected before immediate drag')
          const p = await point(id, part)
          await page.mouse.move(p.x, p.y); await page.mouse.down()
          await page.mouse.move(p.x + dx, p.y + dy, { steps: 5 }); await page.mouse.up(); await frame(page)
          const after = await inspectGraph(page)
          record.gestures.push({ id, part, dx, dy, before, after })
          assert.deepEqual(record.pageErrors, [])
          assert.deepEqual(after.nodes.map(node => node.id).sort(), before.nodes.map(node => node.id).sort())
          assert.equal(after.edges.length, before.edges.length)
          assert.ok(after.canvasGeometry.rect.width > 0 && after.canvasGeometry.rect.height > 0)
          assert.equal(after.viewportGeometry.opacity, '1')
          assert.equal(after.viewportGeometry.visibility, 'visible')
          assert.ok(after.nodes.every(node => node.geometry.visibility === 'visible'), 'Every rendered node remains visible after the short drag')
          const c = after.flowGeometry.rect
          assert.ok(after.nodes.some(node => {
            const r = node.rect
            return r.width > 0 && r.height > 0 && r.x + r.width > c.x && r.x < c.x + c.width && r.y + r.height > c.y && r.y < c.y + c.height
          }), 'At least one node remains visible in the actual canvas clipping region')
          for (const node of after.nodes) assert.ok(Object.values(node.rect).every(Number.isFinite), 'DOM node geometry remains finite')
          if (after.flowStore) for (const node of after.flowStore.internals) {
            assert.ok(Number.isFinite(node.position.x) && Number.isFinite(node.position.y))
            assert.ok(Number.isFinite(node.positionAbsolute.x) && Number.isFinite(node.positionAbsolute.y))
          }
          console.log(`PASS ${record.name} ${id} ${part} (${dx},${dy}px) viewport=${after.viewportTransform} nodes=${after.nodes.length} store=${Boolean(after.flowStore)}`)
        }
        const insert = async tool => {
          const beforeIds = await canvas.locator('.react-flow__node').evaluateAll(elements => elements.map(element => element.getAttribute('data-id')))
          const palette = page.getByTestId(`network-palette-${tool}`)
          await palette.scrollIntoViewIfNeeded()
          const r = await palette.boundingBox()
          await page.mouse.move(r.x + r.width / 2, r.y + r.height / 2); await page.mouse.down(); await frame(page)
          await canvas.scrollIntoViewIfNeeded()
          const p = await canvas.evaluate(element => {
            const r = element.getBoundingClientRect()
            const candidates = [[0.78, 0.48], [0.5, 0.62], [0.28, 0.48], [0.6, 0.4], [0.85, 0.6]]
            for (const fy of [0.35, 0.45, 0.55, 0.65]) for (const fx of [0.25, 0.4, 0.55, 0.7, 0.85]) candidates.push([fx, fy])
            for (const [fx, fy] of candidates) {
              const p = { x: r.x + r.width * fx, y: r.y + r.height * fy }
              if (p.y < 10 || p.y > innerHeight - 10) continue
              const hit = document.elementFromPoint(p.x, p.y)
              if (hit?.closest('.network-graph-canvas') === element && !hit.closest('.react-flow__node, .react-flow__edge')) return p
            }
            throw new Error('No visible blank-canvas pointer point')
          })
          await page.mouse.move(p.x, p.y, { steps: 8 }); await page.mouse.up(); await frame(page)
          const ids = await canvas.locator('.react-flow__node').evaluateAll(elements => elements.map(element => element.getAttribute('data-id')))
          const id = ids.find(id => id.startsWith(`${tool}:`) && !beforeIds.includes(id))
          assert.ok(id, `New ${tool} from real presets exists`)
          const busId = ids.find(id => id.startsWith('bus:') && !beforeIds.includes(id))
          assert.ok(busId)
          return { id, busId }
        }
        try {
          await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 10000 })
          await page.getByRole('button', { name: /网络建模/ }).click(); await editor.waitFor()
          await until(() => canvas.locator('.react-flow__node').count().then(count => count >= 4), 'real presets loaded')
          await editor.scrollIntoViewIfNeeded(); await page.evaluate(() => new Promise(done => setTimeout(done, 350)))
          await page.getByTestId('network-snap').setChecked(snap)
          const initial = await save()
          record.initialTopologyId = initial.topology.id
          const gfm = await insert('gfm')
          await drag(gfm.id, 'body', 20, 12, true)
          const gfmCase = await save()
          assert.equal(gfmCase.topology.buses.length, initial.topology.buses.length + 1)
          assert.equal(gfmCase.topology.grid_forming_converters.length, initial.topology.grid_forming_converters.length + 1)
          const grid = await insert('grid')
          await drag(grid.id, 'body', 5, 5, true)
          const gridCase = await save()
          assert.equal(gridCase.topology.buses.length, initial.topology.buses.length + 2)
          assert.equal(gridCase.topology.infinite_buses.length, initial.topology.infinite_buses.length + 1)
          if (resizeGate) {
            await until(async () => (await inspectGraph(page)).nodes.every(node => node.geometry.visibility === 'visible'), 'all newly inserted source/bus measurements delivered before gate')
            record.beforeResizeGate = await inspectGraph(page)
            await page.evaluate(() => { window.__gfmResizeGate.paused = true })
            await drag(gfm.id, 'body', 20, 12)
            await drag(grid.id, 'body', 20, 12)
            record.resizeCallbacksReleased = await page.evaluate(() => window.__gfmResizeGate.release())
            await frame(page)
          }
          // Both freshly inserted sources now coexist; alternate tiny moves without undo/import.
          for (const source of [gfm, grid]) {
            await drag(source.id, 'body', 5, -5)
            await drag(source.id, 'name', 12, 8)
            await drag(source.busId, 'body', 20, -12)
            await drag(source.id, 'body', -20, 12)
          }
          await page.getByTestId('network-snap').setChecked(!snap)
          await drag(gfm.id, 'body', 5, 5)
          await drag(grid.id, 'body', 20, 12)
          // Double-click can zoom and clip another source out of the visible pane.
          // Test a tiny drag of that same clicked source, then fit before the next source.
          for (const source of [gfm, grid]) {
            const p = await point(source.id, 'name')
            await page.mouse.dblclick(p.x, p.y); await frame(page)
            await page.evaluate(() => new Promise(done => setTimeout(done, 300)))
            await drag(source.id, 'body', 5, 5)
            await page.getByTestId('network-fit').click()
            await page.evaluate(() => new Promise(done => setTimeout(done, 200)))
          }
          const final = await save(), second = await save()
          assert.deepEqual(final.topology, gridCase.topology)
          assert.deepEqual(second.topology, final.topology)
          assert.deepEqual(second.diagram_layout, final.diagram_layout)
          record.beforeRestore = await inspectGraph(page)
          await page.getByTestId('network-restore-display').click(); await frame(page)
          await until(async () => {
            const state = await inspectGraph(page)
            return state.nodes.length === record.beforeRestore.nodes.length && state.edges.length === record.beforeRestore.edges.length
              && state.nodes.every(node => node.geometry.visibility === 'visible')
          }, 'restored display keeps all source/bus nodes and edges visible')
          record.afterRestore = await inspectGraph(page)
          assert.deepEqual(record.afterRestore.nodes.map(node => node.id).sort(), record.beforeRestore.nodes.map(node => node.id).sort())
          assert.deepEqual(record.afterRestore.edges.slice().sort(), record.beforeRestore.edges.slice().sort())
          const restored = await save()
          assert.deepEqual(restored.topology, final.topology, 'Restore display never clears or changes electrical data')
          assert.deepEqual(restored.diagram_layout, final.diagram_layout, 'Restore display never changes saved node coordinates')
          assert.deepEqual(restored.simulation_settings, final.simulation_settings)
          console.log(`PASS ${record.name} restore display preserves topology/layout/settings and ${record.afterRestore.nodes.length} visible nodes/${record.afterRestore.edges.length} edges`)
          record.savedPositions = final.diagram_layout.node_positions
          mkdirSync(reviewDir, { recursive: true })
          await editor.scrollIntoViewIfNeeded()
          record.screenshot = resolve(reviewDir, `${record.name}.png`)
          await editor.screenshot({ path: record.screenshot })
          record.status = 'pass'
        } catch (error) {
          record.status = 'fail'; record.error = error.stack
          record.afterFailure = await inspectGraph(page).catch(error => ({ error: error.message }))
          mkdirSync(reviewDir, { recursive: true })
          record.screenshot = resolve(reviewDir, `${record.name}-failure.png`)
          await page.screenshot({ path: record.screenshot, fullPage: true }).catch(() => {})
          if (resizeGate) {
            record.resizeCallbacksReleased = await page.evaluate(() => window.__gfmResizeGate.release())
            await frame(page)
            record.afterGateRelease = await inspectGraph(page)
          }
          failures.push(record)
          const compact = snapshot => snapshot && ({ viewport: snapshot.viewportTransform, canvas: snapshot.canvasGeometry, nodes: snapshot.nodes?.map(({ id, rect, style, geometry }) => ({ id, rect, style, visibility: geometry.visibility })), edges: snapshot.edges, store: snapshot.flowStore })
          console.log(`FAIL ${record.name}\n${JSON.stringify({ ...record, beforeRestore: compact(record.beforeRestore), afterRestore: compact(record.afterRestore), beforeResizeGate: compact(record.beforeResizeGate), afterFailure: compact(record.afterFailure), afterGateRelease: compact(record.afterGateRelease), gestures: record.gestures.map(({ id, part, dx, dy, before, after }) => ({ id, part, dx, dy, beforeViewport: before.viewportTransform, afterViewport: after.viewportTransform, nodesBefore: before.nodes.length, nodesAfter: after.nodes.length })) })}`)
        } finally { records.push(record); await page.close().catch(() => {}) }
      }
      assert.ok(presetReads.length > 0, 'Presets must be loaded through the UI API path')
      assert.deepEqual(forbiddenApi, [])
    })(), new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Real-presets sequence exceeded its 60-second total limit')), 60000) })])
  } finally {
    clearTimeout(timer); await context.close().catch(() => {})
    console.log(`${resizeGate ? 'RESIZE_GATE' : 'REAL'} SUMMARY ${JSON.stringify({ cases: records.length, gestures: records.reduce((sum, record) => sum + record.gestures.length, 0), passed: records.filter(record => record.status === 'pass').length, failed: records.filter(record => record.status === 'fail').length, presetReads: presetReads.length, forbiddenApi })}`)
  }
}
try {
  browser = await chromium.launch({ headless: true, executablePath, timeout: 15000 })
  if (arg === '--dev' || arg === '--both') await runVariant('dev', process.env.GFM_DEV_URL ?? 'http://127.0.0.1:5173')
  if (arg === '--dist' || arg === '--both') {
    assert.ok(existsSync(resolve(dist, 'index.html')), 'Current dist is required; this test does not build.')
    server = createServer((request, response) => {
      try {
        const path = resolve(dist, `.${decodeURIComponent(new URL(request.url, 'http://localhost').pathname)}`)
        if (path !== dist && !path.startsWith(dist + sep)) { response.writeHead(403).end(); return }
        const file = existsSync(path) && extname(path) ? path : resolve(dist, 'index.html')
        const type = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' }[extname(file)] ?? 'application/octet-stream'
        response.writeHead(200, { 'Content-Type': type }).end(readFileSync(file))
      } catch { response.writeHead(404).end() }
    })
    await new Promise(done => server.listen(0, '127.0.0.1', done))
    const baseUrl = `http://127.0.0.1:${server.address().port}`
    await runVariant('dist', baseUrl)
    await runRealVariant(baseUrl, true, true)
  }
  if (arg === '--real' || arg === '--both') await runRealVariant(process.env.GFM_DEV_URL ?? 'http://127.0.0.1:5173')
  if (arg === '--resize-gate') await runRealVariant(process.env.GFM_DEV_URL ?? 'http://127.0.0.1:5173', true)
  assert.equal(failures.length, 0, `${failures.length} new-source move scenarios failed; full browser stacks printed above.`)
  console.log('GFM_NETWORK_SOURCE_MOVE_UI_OK')
} finally {
  await browser?.close().catch(() => {})
  if (server) { server.closeAllConnections(); await new Promise(done => server.close(done)) }
}
