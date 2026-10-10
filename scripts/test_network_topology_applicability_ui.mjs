// UI-only check: invalid model applicability must not become a connection error.
// Uses a random loopback port and mocked APIs; no numerical claims or backend.
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../apps/web/node_modules/playwright-core/index.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = resolve(root, 'apps/web/dist')
assert.ok(existsSync(resolve(dist, 'index.html')), 'Build the frontend first.')
const executablePath = [process.env.GFM_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find(existsSync)
assert.ok(executablePath, 'Installed Chrome or Edge is required.')
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
const topology = {
  schema_version: '1.0', id: 'connection-ui-only', name: 'Connection UI fixture',
  frame_convention_id: 'power-invariant-park-q-lag-v1',
  base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 },
  reference_bus_id: 'grid-bus',
  buses: ['gfm-bus', 'grid-bus'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
  lines: [{ id: 'line-1', name: 'Line', from_bus_id: 'gfm-bus', to_bus_id: 'grid-bus',
    resistance_pu: 0.01, reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true }],
  grid_forming_converters: [{ id: 'gfm-1', name: 'VSM', bus_id: 'gfm-bus',
    control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
    active_power_setpoint_pu: 0, reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1,
    virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
  infinite_buses: [{ id: 'grid-1', name: 'Grid', bus_id: 'grid-bus', voltage_magnitude_pu: 1, voltage_angle_deg: 0 }],
  loads: [],
}
let browser, context, timeout
let scenarios = 0
const pageErrors = []
const analysisRequests = []
const unexpectedApi = []
const pass = name => { scenarios += 1; console.log(`PASS ${name}`) }
const until = async (predicate, name) => {
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolveWait => setTimeout(resolveWait, 25))
  }
  throw new Error(`Timed out: ${name}`)
}
try {
  await Promise.race([(async () => {
    browser = await chromium.launch({ headless: true, executablePath, timeout: 15000 })
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
    await context.route('**/*', route => new URL(route.request().url()).origin === baseUrl ? route.continue() : route.abort())
    await context.route('**/api/**', async route => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/reduced-order/presets') {
        await route.fulfill({ json: { presets: ['stable', 'marginal', 'unstable'].map(kind => ({
          id: `reduced-smib-${kind}`, name: `UI ${kind}`, topology: structuredClone(topology),
        })) } }); return
      }
      if (['/api/reduced-order/analyze', '/api/reduced-order/scan', '/api/reduced-order/n-minus-one'].includes(path)) {
        analysisRequests.push(path)
        await route.fulfill({ status: 422, json: { detail: 'UI-only response; no numerical solver' } }); return
      }
      unexpectedApi.push(path)
      await route.fulfill({ status: 404, json: { detail: 'Unexpected UI-test request' } })
    })
    const page = await context.newPage()
    page.setDefaultTimeout(5000)
    page.on('pageerror', error => pageErrors.push(error.message))
    await page.goto(baseUrl)
    await page.getByRole('button', { name: /网络建模/ }).click()
    const run = () => page.getByRole('button', { name: '验证拓扑并分析', exact: true })
    const wiring = () => page.getByTestId('wiring-status')
    const applicability = () => page.getByTestId('low-frequency-applicability')
    const upload = async value => {
      await page.locator('input[type="file"]').setInputFiles({ name: 'connection-test.json', mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify({ schema_version: 'gfm-reduced-order-case/1.1', topology: value,
          diagram_layout: { schema_version: 'gfm-network-diagram-layout/1.0', node_positions: {} } })) })
      await page.getByText('案例已载入；电气拓扑与图形版面已分别恢复。', { exact: true }).waitFor()
    }
    const save = async () => {
      const downloaded = page.waitForEvent('download')
      await page.getByRole('button', { name: '保存案例', exact: true }).click()
      const download = await downloaded
      return JSON.parse(readFileSync(await download.path(), 'utf8'))
    }
    await until(() => run().isEnabled(), 'valid preset loaded')
    assert.equal(await wiring().textContent(), '接线关系有效')
    assert.equal(await applicability().textContent(), '低频模型输入条件满足')
    pass('VSM and reference satisfy separate connection/model checks')

    const cases = [
      { name: 'no GFM', mutate: t => { t.grid_forming_converters = [] }, valid: true, reason: '缺少构网型变流器' },
      { name: 'no reference source', mutate: t => { t.infinite_buses = [] }, valid: true, reason: '缺少无限大母线' },
      { name: 'disconnected draft', mutate: t => { t.lines[0].in_service = false }, valid: true, reason: '2 个连通分量' },
      { name: 'invalid line reference', mutate: t => { t.lines[0].to_bus_id = 'missing-bus' }, valid: false, reason: '引用了不存在的母线' },
      { name: 'invalid device reference', mutate: t => { t.grid_forming_converters[0].bus_id = 'missing-bus' }, valid: false, reason: '设备 gfm-1 引用了不存在的母线' },
      { name: 'cross-voltage line', mutate: t => { t.buses[1].nominal_voltage_v = 10000 }, valid: false, reason: '不能以线路代替变压器' },
    ]
    for (const test of cases) {
      const draft = structuredClone(topology)
      test.mutate(draft)
      await upload(draft)
      await until(() => run().isDisabled(), `${test.name} blocked`)
      await until(async () => (await page.locator('.graph-diagnostic').allTextContents()).join(' ').includes(test.reason), `${test.name} diagnosis loaded`)
      assert.equal(await wiring().textContent(), test.valid ? '接线关系有效' : '接线关系需修正')
      assert.equal(await applicability().textContent(), '当前接线不适用低频模型')
      assert.ok((await page.locator('.graph-diagnostic').allTextContents()).join(' ').includes(test.reason))
      assert.equal(await page.getByTestId('reduced-n-minus-one-run').isDisabled(), true)
      await run().evaluate(button => button.click())
      assert.equal(analysisRequests.length, 0, `${test.name}: blocked model must not invoke solver`)
      const exported = await save()
      assert.deepEqual(exported.topology, draft, `${test.name}: save must preserve draft`)
      pass(`${test.name}: correct diagnosis, blocked solver, save preserved`)
    }
    await upload(structuredClone(topology))
    await until(() => run().isEnabled(), 'valid input restored')
    const node = page.locator('.react-flow__node[data-id="bus:gfm-bus"]')
    await node.scrollIntoViewIfNeeded()
    const beforeStyle = await node.getAttribute('style')
    const box = await node.boundingBox()
    assert.ok(box)
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 + 65, box.y + box.height / 2 + 30, { steps: 8 })
    await page.mouse.up()
    await until(async () => await node.getAttribute('style') !== beforeStyle, 'node dragged')
    assert.equal(await wiring().textContent(), '接线关系有效')
    assert.equal(await applicability().textContent(), '低频模型输入条件满足')
    const moved = await save()
    assert.deepEqual(moved.topology, topology)
    assert.ok(moved.diagram_layout.node_positions['bus:gfm-bus'])
    pass('graph dragging changes layout only and preserves electrical input/checks')
    await page.getByTestId('network-undo').click()
    assert.equal(await node.getAttribute('style'), beforeStyle)
    assert.equal(await run().isEnabled(), true)
    pass('layout-only undo preserves model applicability')
    assert.deepEqual(pageErrors, [])
    assert.deepEqual(unexpectedApi, [])
    if (process.env.GFM_UI_REVIEW_DIR) {
      const reviewDir = resolve(process.env.GFM_UI_REVIEW_DIR)
      mkdirSync(reviewDir, { recursive: true })
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 1000 })
        await page.getByTestId('network-graph-editor').scrollIntoViewIfNeeded()
        await page.evaluate(() => new Promise(resolveFrames => {
          requestAnimationFrame(() => requestAnimationFrame(resolveFrames))
        }))
        const dimensions = await page.evaluate(() => ({
          viewport: document.documentElement.clientWidth,
          document: document.documentElement.scrollWidth,
        }))
        assert.ok(dimensions.document <= dimensions.viewport + 1, `Page overflow at ${width}px`)
        await page.getByTestId('network-graph-editor').screenshot({
          path: resolve(reviewDir, `topology-checks-${width}.png`),
        })
        console.log(`GFM_TOPOLOGY_VIEWPORT_OK ${width}px`)
      }
      assert.deepEqual(pageErrors, [])
    }
    console.log(`GFM_NETWORK_TOPOLOGY_APPLICABILITY_UI_OK (${scenarios} UI-only scenarios)`)
  })(), new Promise((_, reject) => {
    timeout = setTimeout(() => reject(new Error('UI regression exceeded its 60-second total limit.')), 60000)
  })])
} finally {
  clearTimeout(timeout)
  await context?.close().catch(() => {})
  await browser?.close().catch(() => {})
  server.closeAllConnections()
  await new Promise(resolveClose => server.close(resolveClose))
}
