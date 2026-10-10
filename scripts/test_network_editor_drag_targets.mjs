// Read-only browser diagnosis: real mouse drags from SVG strokes and labels.
// Own random port, installed browser, mocked presets; no solver or source edits.
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../apps/web/node_modules/playwright-core/index.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = resolve(root, 'apps/web/dist')
assert.ok(existsSync(resolve(dist, 'index.html')))
const executablePath = [process.env.GFM_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find(existsSync)
assert.ok(executablePath, 'An installed browser is required; nothing is installed.')
const fixture = {
  schema_version: '1.0', id: 'editor-drag-targets-ui-only', name: '拖动起点诊断',
  frame_convention_id: 'power-invariant-park-q-lag-v1',
  base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 },
  reference_bus_id: 'grid-bus',
  buses: ['bus-1', 'grid-bus'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
  lines: [{ id: 'line-1', name: '线路 1', from_bus_id: 'bus-1', to_bus_id: 'grid-bus',
    resistance_pu: 0.01, reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true }],
  grid_forming_converters: [{ id: 'gfm-1', name: 'VSM 1', bus_id: 'bus-1',
    control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
    active_power_setpoint_pu: 0, reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1,
    virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
  infinite_buses: [{ id: 'grid-1', name: '等值电源', bus_id: 'grid-bus',
    voltage_magnitude_pu: 1, voltage_angle_deg: 0 }], loads: [],
}
const server = createServer((request, response) => {
  try {
    const path = resolve(dist, `.${decodeURIComponent(new URL(request.url, 'http://localhost').pathname)}`)
    if (path !== dist && !path.startsWith(dist + sep)) { response.writeHead(403).end(); return }
    const file = existsSync(path) && extname(path) ? path : resolve(dist, 'index.html')
    const type = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' }[extname(file)] ?? 'application/octet-stream'
    response.writeHead(200, { 'Content-Type': type }).end(readFileSync(file))
  } catch { response.writeHead(404).end() }
})
await new Promise(resolveListen => server.listen(0, '127.0.0.1', resolveListen))
const baseUrl = `http://127.0.0.1:${server.address().port}`
let browser, context, page, timeout
const pageErrors = [], apiRequests = [], results = []
try {
  await Promise.race([(async () => {
    browser = await chromium.launch({ headless: true, executablePath, timeout: 15000 })
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
    await context.route('**/*', route => new URL(route.request().url()).origin === baseUrl ? route.continue() : route.abort())
    await context.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/reduced-order/presets') {
        await route.fulfill({ json: { presets: ['stable', 'marginal', 'unstable'].map(kind => ({
          id: `reduced-smib-${kind}`, name: `UI ${kind}`, topology: structuredClone(fixture),
        })) } }); return
      }
      apiRequests.push(path)
      await route.fulfill({ status: 422, json: { detail: 'UI-only diagnosis; computation is prohibited' } })
    })
    page = await context.newPage()
    page.setDefaultTimeout(5000)
    page.on('pageerror', error => pageErrors.push(error.message))
    await page.goto(baseUrl)
    await page.getByRole('button', { name: /网络建模/ }).click()
    await page.getByTestId('network-graph-editor').waitFor()
    await page.getByRole('button', { name: '验证拓扑并分析', exact: true }).waitFor({ state: 'visible' })
    await page.getByTestId('network-node-grid-1').waitFor()
    await page.getByTestId('network-mode-select').click()
    assert.equal(await page.getByTestId('network-mode-select').getAttribute('aria-pressed'), 'true')
    const frames = () => page.evaluate(() => new Promise(resolveFrames => requestAnimationFrame(() => requestAnimationFrame(resolveFrames))))
    const save = async () => {
      const [download] = await Promise.all([
        page.waitForEvent('download'), page.getByRole('button', { name: '保存案例', exact: true }).click(),
      ])
      return JSON.parse(readFileSync(await download.path(), 'utf8'))
    }
    await frames()
    const baseline = await save()
    for (const { id, kind } of [
      { id: 'bus-1', kind: 'bus' }, { id: 'gfm-1', kind: 'gfm' }, { id: 'grid-1', kind: 'grid' },
    ]) for (const targetType of ['stroke', 'label']) {
      const node = page.getByTestId(`network-node-${id}`)
      const source = targetType === 'stroke'
        ? page.getByTestId(`network-symbol-${id}`).locator(kind === 'grid' ? 'circle' : 'path').first()
        : node.locator('.electrical-node-label b')
      const before = await save()
      // Saving scrolls to the toolbar; restore the node before hit testing.
      await node.scrollIntoViewIfNeeded()
      await frames()
      const point = await source.evaluate((element, targetType) => {
        const describe = hit => ({
          tag: hit?.tagName.toLowerCase(), cssClass: hit?.getAttribute('class') ?? '',
          pointerEvents: hit ? getComputedStyle(hit).pointerEvents : null,
          cursor: hit ? getComputedStyle(hit).cursor : null,
          nodrag: !!hit?.closest('.nodrag'), draggable: hit?.closest('.react-flow__node')?.classList.contains('draggable'),
        })
        if (targetType === 'stroke') {
          if (!(element instanceof SVGGeometryElement)) throw new Error('Expected actual SVG geometry')
          const matrix = element.getScreenCTM()
          if (!matrix) throw new Error('SVG shape not rendered')
          for (const fraction of [.23, .41, .63, .81]) {
            const local = element.getPointAtLength(element.getTotalLength() * fraction)
            const screen = new DOMPoint(local.x, local.y).matrixTransform(matrix)
            const hit = document.elementFromPoint(screen.x, screen.y)
            if (hit === element) return { x: screen.x, y: screen.y, hit: describe(hit) }
          }
          throw new Error(`No visible real-stroke hit point on ${element.tagName}`)
        }
        const box = element.getBoundingClientRect()
        const x = box.x + box.width / 2, y = box.y + box.height / 2
        const hit = document.elementFromPoint(x, y)
        if (hit !== element) throw new Error(`Label point hits ${hit?.tagName}, not label`)
        return { x, y, hit: describe(hit) }
      }, targetType)
      await page.mouse.move(point.x, point.y)
      await page.mouse.down()
      await page.mouse.move(point.x - 51, point.y + 33, { steps: 10 })
      await page.mouse.up()
      await frames()
      const after = await save()
      assert.deepEqual(after.topology, before.topology, `${kind}/${targetType}: electrical topology unchanged`)
      const key = `${kind}:${id}`
      const beforePosition = before.diagram_layout.node_positions[key]
      const afterPosition = after.diagram_layout.node_positions[key]
      const moved = JSON.stringify(beforePosition) !== JSON.stringify(afterPosition)
      const result = { kind, targetType, moved, hit: point.hit,
        beforePosition: beforePosition ?? null, afterPosition: afterPosition ?? null }
      if (moved) {
        assert.notDeepEqual(after.diagram_layout, before.diagram_layout)
        await page.getByTestId('network-undo').click()
        const undone = await save()
        assert.deepEqual(undone.topology, before.topology)
        assert.deepEqual(undone.diagram_layout, before.diagram_layout)
        result.undoRestored = true
      } else result.undoRestored = null
      results.push(result)
      console.log(JSON.stringify(result))
    }
    assert.deepEqual((await save()).topology, baseline.topology)
    assert.deepEqual((await save()).diagram_layout, baseline.diagram_layout)
    assert.deepEqual(pageErrors, [])
    assert.deepEqual(apiRequests, [])
    assert.equal(results.filter(result => result.moved && result.undoRestored).length, 6,
      'Every SVG stroke and label drag must change saved layout and support real Undo')
    console.log('GFM_NETWORK_EDITOR_DRAG_TARGETS_UI_OK (6 real-mouse target scenarios)')
  })(), new Promise((_, reject) => {
    timeout = setTimeout(() => reject(new Error('Drag diagnosis exceeded its 60-second total limit.')), 60000)
  })])
} finally {
  clearTimeout(timeout)
  await context?.close().catch(() => {})
  await browser?.close().catch(() => {})
  server.closeAllConnections()
  await new Promise(resolveClose => server.close(resolveClose))
}
