// UI/payload regression only: ideal wires are compiled to equipotential buses,
// not represented by tiny/zero-X AC lines. No numerical result is fabricated.
// Uses one random loopback port, one private browser context, and the existing dist.
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../apps/web/node_modules/playwright-core/index.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = resolve(root, 'apps/web/dist')
assert.ok(existsSync(resolve(dist, 'index.html')), 'Build the current frontend first; this test does not build or wait for a build.')
const executablePath = [process.env.GFM_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find(existsSync)
assert.ok(executablePath, 'An already installed Chrome or Edge is required; nothing is installed.')

const server = createServer((request, response) => {
  try {
    const path = resolve(dist, `.${decodeURIComponent(new URL(request.url, 'http://localhost').pathname)}`)
    if (path !== dist && !path.startsWith(dist + sep)) { response.writeHead(403).end(); return }
    const file = existsSync(path) && extname(path) ? path : resolve(dist, 'index.html')
    const type = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml' }[extname(file)] ?? 'application/octet-stream'
    response.writeHead(200, { 'Content-Type': type }).end(readFileSync(file))
  } catch { response.writeHead(404).end() }
})
await new Promise(resolveListen => server.listen(0, '127.0.0.1', resolveListen))
const baseUrl = `http://127.0.0.1:${server.address().port}`
const clone = value => JSON.parse(JSON.stringify(value))
const fixture = {
  // Existing Workbench behavior labels edited topologies as custom. Starting
  // with that label makes full-model comparisons isolate the electrical edit.
  schema_version: '1.0', id: 'custom-ideal-wire-ui-only', name: '普通导线 UI 验收夹具（自定义）',
  frame_convention_id: 'power-invariant-park-q-lag-v1',
  base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 },
  reference_bus_id: 'bus-b',
  buses: ['bus-a', 'bus-b', 'bus-c'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
  lines: [{ id: 'line-original', name: '原有带阻抗线路', from_bus_id: 'bus-a', to_bus_id: 'bus-b',
    resistance_pu: 0.01, reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true }],
  grid_forming_converters: [{ id: 'gfm-1', name: 'VSM 1', bus_id: 'bus-a',
    control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
    active_power_setpoint_pu: 0, reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1,
    virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
  infinite_buses: [{ id: 'grid-1', name: '等值电源', bus_id: 'bus-b', voltage_magnitude_pu: 1, voltage_angle_deg: 0 }],
  loads: [],
}
const legacyCase = {
  schema_version: 'gfm-reduced-order-case/1.1',
  analysis_mode: 'low-frequency-angle-frequency-active-power-reduced-order',
  topology: clone(fixture),
  diagram_layout: { schema_version: 'gfm-network-diagram-layout/1.0', node_positions: {
    'bus:bus-a': { x: 40, y: 170 }, 'bus:bus-b': { x: 750, y: 170 },
    'bus:bus-c': { x: 410, y: 400 }, 'gfm:gfm-1': { x: 64, y: 25 },
    'grid:grid-1': { x: 774, y: 300 },
  } },
  simulation_settings: { simulation_time_s: 20, time_step_s: 0.02, initial_angle_perturbation_rad: 0.001 },
  model_scope: 'low-frequency-reduced-order-model-only',
}
const twoBusLegacy = clone(legacyCase)
twoBusLegacy.topology.buses = twoBusLegacy.topology.buses.filter(bus => bus.id !== 'bus-c')
delete twoBusLegacy.diagram_layout.node_positions['bus:bus-c']
const blockedDetail = 'UI-only request captured; no numerical solver was invoked.'
const reviewDir = process.env.GFM_UI_REVIEW_DIR ? resolve(process.env.GFM_UI_REVIEW_DIR) : null
const startedAt = Date.now()
let browser, context, page, timeout
let scenarios = 0
const analysisRequests = [], unexpectedApi = [], pageErrors = []
const pass = description => { scenarios += 1; console.log(`PASS ${description}`) }
const until = async (predicate, description) => {
  const deadline = Date.now() + 4500
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolveWait => setTimeout(resolveWait, 20))
  }
  throw new Error(`Timed out: ${description}`)
}

try {
  await Promise.race([(async () => {
    browser = await chromium.launch({ headless: true, executablePath, timeout: 10000 })
    context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true })
    // All requests outside this private static server are blocked. API routes
    // below intercept before the server; they never reach a live backend.
    await context.route('**/*', route => new URL(route.request().url()).origin === baseUrl ? route.continue() : route.abort())
    await context.route('**/api/**', async route => {
      const request = route.request(), path = new URL(request.url()).pathname
      if (path === '/api/reduced-order/presets' && request.method() === 'GET') {
        await route.fulfill({ json: { presets: ['stable', 'critical', 'unstable'].map(kind => ({
          id: `reduced-smib-${kind}`, name: `UI fixture ${kind}`, topology: clone(fixture),
        })) } }); return
      }
      if (path === '/api/reduced-order/analyze' && request.method() === 'POST') {
        analysisRequests.push(request.postDataJSON())
        // Deliberate failure: only the actual request payload is verified. The
        // UI must not show a made-up stability classification or solver report.
        await route.fulfill({ status: 422, json: { detail: blockedDetail } }); return
      }
      unexpectedApi.push(`${request.method()} ${path}`)
      await route.fulfill({ status: 422, json: { detail: 'This UI regression prohibits solver/report/scan API calls.' } })
    })
    page = await context.newPage()
    page.setDefaultTimeout(4500)
    page.on('pageerror', error => pageErrors.push(error.message))
    const frames = () => page.evaluate(() => new Promise(resolveFrames => requestAnimationFrame(() => requestAnimationFrame(resolveFrames))))
    const editor = page.getByTestId('network-graph-editor')
    const properties = page.getByTestId('network-editor-properties')
    const node = id => page.getByTestId(`network-node-${id}`)
    const kind = value => page.getByTestId(`network-connect-kind-${value}`)
    const wires = caseData => caseData.ideal_connections ?? []
    // The per-editor test IDs exist only in expanded-canvas mode. The visible
    // controls work in both ordinary and expanded layouts.
    const saveButton = () => page.getByRole('button', { name: '保存案例', exact: true })
    const analyzeButton = () => page.getByRole('button', { name: /^(?:验证拓扑并分析|正在建立状态空间…|分析中…)$/ })
    const save = async () => {
      const [download] = await Promise.all([
        page.waitForEvent('download'), saveButton().click(),
      ])
      const path = await download.path()
      assert.ok(path, 'A real saved case download must exist')
      return JSON.parse(readFileSync(path, 'utf8'))
    }
    const assertCaseState = (actual, expected) => {
      assert.deepEqual(actual.topology, expected.topology)
      assert.deepEqual(actual.diagram_layout, expected.diagram_layout)
      assert.deepEqual(wires(actual), wires(expected))
      assert.deepEqual(actual.simulation_settings, expected.simulation_settings)
    }
    const importCase = async caseData => {
      await page.locator('input[type="file"]').setInputFiles({
        name: 'ideal-wire-ui.gfm-case.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(caseData)),
      })
      await until(async () => (await page.locator('.editor-message').textContent()).includes('案例已载入'), 'case import committed')
      await frames()
      assertCaseState(await save(), caseData)
      await page.getByTestId('network-fit').click()
      await frames()
    }
    const connectByClick = async (from, to) => {
      await node(from).click()
      await node(to).click()
      await frames()
    }
    const clickEdge = async id => {
      const edge = page.getByTestId(`network-edge-${id}`)
      await edge.waitFor()
      // The actual SVG edge label is clicked. This checks graph selection,
      // rather than directly changing React state or using an element picker.
      const box = await edge.locator('.react-flow__edge-textwrapper').boundingBox()
      assert.ok(box && box.width > 0 && box.height > 0, `Rendered SVG label for ${id}`)
      await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2)
      await frames()
    }
    const assertSameInput = (actual, expected) => {
      assert.deepEqual(actual.topology, expected.topology, 'Diagram editing must not alter the physical electrical model')
      assert.deepEqual(wires(actual), wires(expected), 'Diagram editing must not alter ideal connections')
    }
    const analyzePayload = async () => {
      const count = analysisRequests.length
      const button = analyzeButton()
      assert.equal(await button.isEnabled(), true, 'Valid compiled input must permit analysis')
      await button.click()
      await until(() => analysisRequests.length === count + 1, 'compiled request intercepted')
      await until(() => button.isEnabled(), 'mocked request finished')
      assert.ok((await page.locator('body').innerText()).includes(blockedDetail), 'Expected no-solver response is visibly surfaced')
      return analysisRequests[count]
    }
    const busGeometry = async id => node(id).evaluate(element => {
      const symbol = element.querySelector('svg.bus-symbol')
      const container = element.querySelector('.electrical-node-symbol')
      const handles = ['west', 'east'].map(side => element.querySelector(`.react-flow__handle[data-handleid="${side}"]`))
      if (!(symbol instanceof SVGSVGElement) || !(container instanceof HTMLElement) || handles.some(handle => !(handle instanceof HTMLElement))) {
        throw new Error(`Missing real bus symbol/terminals for ${element.dataset.testid}`)
      }
      const svg = symbol.getBoundingClientRect(), parent = container.getBoundingClientRect()
      const centers = handles.map(handle => { const box = handle.getBoundingClientRect(); return { x: box.x + box.width / 2, y: box.y + box.height / 2 } })
      return { viewBox: symbol.viewBox.baseVal.width, cssWidth: parseFloat(getComputedStyle(symbol).width),
        horizontalPath: symbol.querySelector('path')?.getAttribute('d'), screenWidth: svg.width,
        symbolLeft: svg.left, symbolRight: svg.right, middleY: svg.top + svg.height / 2,
        terminalSpan: centers[1].x - centers[0].x, terminals: centers, parentWidth: parent.width }
    })
    const assertBusGeometry = (geometry, width) => {
      assert.equal(geometry.viewBox, width - 16, 'SVG coordinate system must track the chosen bus length')
      assert.equal(geometry.cssWidth, width - 16, 'Real SVG display length must track the chosen bus length')
      assert.ok(geometry.horizontalPath.includes(String(width - 16)), 'The busbar path itself must become longer')
      assert.ok(Math.abs(geometry.terminals[0].x - geometry.symbolLeft) < 2, 'West terminal stays on the busbar end')
      assert.ok(Math.abs(geometry.terminals[1].x - geometry.symbolRight) < 2, 'East terminal stays on the busbar end')
      assert.ok(geometry.terminals.every(terminal => Math.abs(terminal.y - geometry.middleY) < 2), 'Both terminals stay on the busbar axis')
      assert.ok(geometry.terminalSpan > 0)
    }

    await page.goto(baseUrl)
    await page.getByRole('button', { name: /网络建模/ }).click()
    await editor.waitFor()
    assert.equal(await kind('wire').getAttribute('aria-pressed'), 'true', 'Ordinary wire is the initial connection type')
    await importCase(legacyCase)
    if (process.env.GFM_UI_CAPTURE_ONLY === '1') {
      assert.ok(reviewDir, 'Capture-only mode requires GFM_UI_REVIEW_DIR')
      await page.getByTestId('network-mode-connect').click()
      await connectByClick('bus-a', 'bus-c')
      await page.getByTestId('network-mode-select').click()
      await node('bus-a').click()
      await page.getByTestId('network-bus-width').fill('440')
      const displayCase = await save()
      mkdirSync(reviewDir, { recursive: true })
      for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 1000 })
        await editor.scrollIntoViewIfNeeded()
        await page.getByTestId('network-fit').click()
        await frames()
        await page.getByTestId('network-element-picker').selectOption('bus:bus-a')
        assertBusGeometry(await busGeometry('bus-a'), 440)
        assertCaseState(await save(), displayCase)
        const path = resolve(reviewDir, `network-ideal-wire-${width}.png`)
        // Include the parent mapping explanation beneath the canvas, not just
        // the canvas itself. This is visual QA of a teaching fixture only.
        await page.locator('.model-editor').screenshot({ path })
        console.log(`CAPTURE ${width}px ${path}`)
      }
      assert.deepEqual(pageErrors, [])
      assert.deepEqual(unexpectedApi, [])
      assert.deepEqual(analysisRequests, [])
      console.log(`GFM_NETWORK_IDEAL_WIRE_CAPTURE_OK (${Date.now() - startedAt}ms; no analysis requests)`)
      return
    }
    const oldPhysical = await save()
    assert.equal(oldPhysical.schema_version, 'gfm-reduced-order-case/1.1', 'No new drawing data must preserve old export schema')
    assert.equal(wires(oldPhysical).length, 0)
    assert.equal(await kind('wire').getAttribute('aria-pressed'), 'true')
    await page.getByTestId('network-mode-connect').click()
    await connectByClick('bus-a', 'bus-c')
    const connected = await save()
    assert.equal(connected.schema_version, 'gfm-reduced-order-case/1.2')
    assert.deepEqual(connected.topology, fixture, 'Ordinary wiring preserves all three physical bus drawings and the original R/X branch')
    assert.equal(wires(connected).length, 1)
    const wire = wires(connected)[0]
    assert.deepEqual(Object.keys(wire).sort(), ['from_bus_id', 'id', 'name', 'to_bus_id'])
    assert.deepEqual(new Set([wire.from_bus_id, wire.to_bus_id]), new Set(['bus-a', 'bus-c']))
    await page.getByTestId(`network-edge-${wire.id}`).waitFor()
    assert.equal(await editor.locator('.react-flow__node[data-id^="bus:"]').count(), 3)
    pass('default ordinary-wire click connection preserves three physical bus elements and saves a real ideal connection')

    const payload = await analyzePayload()
    assert.ok(payload.topology, 'Edited wiring must send the actual compiled topology, not only a preset ID')
    assert.equal(payload.preset_id, undefined)
    assert.equal(payload.topology.buses.length, 2, 'Equipotential compiler collapses A and C only in the API input')
    const expectedCompiled = clone(fixture)
    expectedCompiled.buses = expectedCompiled.buses.filter(bus => bus.id !== 'bus-c')
    assert.deepEqual(payload.topology, expectedCompiled, 'Bus A is the retained equipotential representative; every device ID and parameter is unchanged')
    assert.ok(payload.topology.lines.every(line => line.reactance_pu > 0), 'No X=0 or tiny-X wire surrogate reaches the analysis API')
    assert.equal(payload.ideal_connections, undefined)
    assert.equal(payload.diagram_layout, undefined)
    assert.equal(payload.topology.ideal_connections, undefined)
    assert.equal(payload.topology.bus_widths, undefined)
    assertCaseState(await save(), connected)
    pass('actual analysis request has two compiled buses, unchanged equipment/R/X parameters, and no ideal-wire surrogate or drawing fields')

    await page.reload()
    await page.getByRole('button', { name: /网络建模/ }).click()
    await editor.waitFor()
    assert.equal(wires(await save()).length, 0, 'Private-page reload returns the mock preset, not persistent hidden React state')
    await importCase(JSON.parse(JSON.stringify(connected)))
    await page.getByTestId(`network-edge-${wire.id}`).waitFor()
    assertCaseState(await save(), connected)
    pass('real JSON save, page reload, and file import restore the ideal wire and original physical topology/layout')

    await page.getByTestId('network-mode-select').click()
    await clickEdge(wire.id)
    assert.equal(await page.getByTestId('network-element-picker').inputValue(), `wire:${wire.id}`)
    assert.ok((await properties.innerText()).includes(wire.id), 'Wire selection exposes its local details')
    await page.getByTestId('network-delete-element').click()
    await until(() => page.getByTestId(`network-edge-${wire.id}`).count().then(count => count === 0), 'selected wire removed')
    const deleted = await save()
    assert.equal(wires(deleted).length, 0)
    assert.deepEqual(deleted.topology, fixture)
    await page.getByTestId('network-undo').click()
    await page.getByTestId(`network-edge-${wire.id}`).waitFor()
    assertCaseState(await save(), connected)
    pass('real SVG wire selection, generic deletion, and one undo restore exactly the saved connection')

    await node('bus-a').click()
    const widthInput = page.getByTestId('network-bus-width')
    assert.equal(await widthInput.getAttribute('min'), '128')
    assert.equal(await widthInput.getAttribute('max'), '1200')
    const beforeWidth = await save(), beforeGeometry = await busGeometry('bus-a')
    await widthInput.fill('320')
    await frames()
    const numericWidth = await save()
    assert.equal(numericWidth.diagram_layout.schema_version, 'gfm-network-diagram-layout/1.1')
    assert.equal(numericWidth.diagram_layout.bus_widths['bus-a'], 320)
    assertSameInput(numericWidth, beforeWidth)
    assert.deepEqual(numericWidth.diagram_layout.node_positions, beforeWidth.diagram_layout.node_positions)
    const numericGeometry = await busGeometry('bus-a')
    assertBusGeometry(numericGeometry, 320)
    assert.ok(numericGeometry.viewBox > beforeGeometry.viewBox)
    assert.ok(numericGeometry.terminalSpan > beforeGeometry.terminalSpan + 20, 'Actual screen terminal spacing, not just stored metadata, grows')
    await page.getByTestId('network-undo').click()
    assertCaseState(await save(), beforeWidth)
    assert.equal((await busGeometry('bus-a')).viewBox, beforeGeometry.viewBox)
    await page.getByTestId('network-redo').click()
    assertCaseState(await save(), numericWidth)
    pass('numeric bus width changes real SVG/terminal geometry and only layout; one undo/redo restores the exact edit')

    await node('bus-a').click()
    const resize = page.getByTestId('network-bus-resize-bus-a')
    const resizeBox = await resize.boundingBox()
    assert.ok(resizeBox && resizeBox.width > 0, 'Selected bus has a real pointer resize handle')
    const start = { x: resizeBox.x + resizeBox.width / 2, y: resizeBox.y + resizeBox.height / 2 }
    await page.mouse.move(start.x, start.y)
    await page.mouse.down()
    await page.mouse.move(start.x + 85, start.y, { steps: 10 })
    await page.mouse.up()
    await frames()
    const resized = await save()
    const draggedWidth = resized.diagram_layout.bus_widths['bus-a']
    assert.ok(Number.isInteger(draggedWidth) && draggedWidth > 320 && draggedWidth <= 1200, 'A real pointer drag increases the persisted bus length')
    assertSameInput(resized, numericWidth)
    assert.deepEqual(resized.diagram_layout.node_positions, numericWidth.diagram_layout.node_positions, 'Resize must not accidentally drag the mother bus')
    assertBusGeometry(await busGeometry('bus-a'), draggedWidth)
    await page.getByTestId('network-undo').click()
    assertCaseState(await save(), numericWidth)
    assertBusGeometry(await busGeometry('bus-a'), 320)
    await page.getByTestId('network-redo').click()
    assertCaseState(await save(), resized)
    pass('real bus resize drag changes SVG and port positions without moving bus coordinates; the whole gesture is one undo entry')

    await importCase(legacyCase)
    await importCase(JSON.parse(JSON.stringify(resized)))
    assertBusGeometry(await busGeometry('bus-a'), draggedWidth)
    await page.getByTestId('network-restore-display').click()
    await node('bus-a').waitFor()
    await frames()
    assertCaseState(await save(), resized)
    assertBusGeometry(await busGeometry('bus-a'), draggedWidth)
    pass('width-bearing case import and restore-display preserve coordinates, ideal wires, bus widths, and rendered terminal geometry')

    const invalidImports = [
      {
        description: 'layout 1.0 containing bus_widths is rejected atomically',
        data: { ...clone(resized), diagram_layout: { ...clone(resized.diagram_layout), schema_version: 'gfm-network-diagram-layout/1.0' } },
        error: /图形版面版本 1\.1/,
      },
      {
        description: 'old case 1.1 containing a width-bearing layout 1.1 is rejected atomically',
        data: { ...clone(resized), schema_version: 'gfm-reduced-order-case/1.1' },
        error: /案例版本 1\.2/,
      },
      {
        description: 'case 1.2 bus width referencing a missing physical bus is rejected atomically',
        data: { ...clone(resized), diagram_layout: { ...clone(resized.diagram_layout),
          bus_widths: { ...resized.diagram_layout.bus_widths, 'missing-width-bus': 320 } } },
        error: /不存在的母线 missing-width-bus/,
      },
    ]
    delete invalidImports[1].data.ideal_connections
    const importHistory = { undo: await page.getByTestId('network-undo').isEnabled(), redo: await page.getByTestId('network-redo').isEnabled() }
    for (const invalid of invalidImports) {
      await page.locator('input[type="file"]').setInputFiles({
        name: 'invalid-drawing-version.gfm-case.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(invalid.data)),
      })
      await until(async () => invalid.error.test(await page.locator('.error').textContent().catch(() => '')), invalid.description)
      assert.deepEqual(await save(), resized, 'Rejected import must preserve the entire exported case, including wires, widths and settings')
      assert.equal(await page.getByTestId('network-undo').isEnabled(), importHistory.undo)
      assert.equal(await page.getByTestId('network-redo').isEnabled(), importHistory.redo)
      assertBusGeometry(await busGeometry('bus-a'), draggedWidth)
      pass(invalid.description)
    }

    await importCase(legacyCase)
    await page.getByTestId('network-mode-select').click()
    await node('bus-c').click()
    const voltage = properties.getByRole('spinbutton', { name: '标称电压 / V', exact: true })
    await voltage.fill('690')
    const crossVoltage = await save()
    const history = { undo: await page.getByTestId('network-undo').isEnabled(), redo: await page.getByTestId('network-redo').isEnabled() }
    await kind('wire').click()
    await page.getByTestId('network-mode-connect').click()
    await connectByClick('bus-a', 'bus-c')
    await until(async () => /电压|变压器/.test(await page.locator('.editor-message').textContent()), 'cross-voltage wire explicitly rejected')
    assertCaseState(await save(), crossVoltage)
    assert.equal(await page.getByTestId('network-undo').isEnabled(), history.undo)
    assert.equal(await page.getByTestId('network-redo').isEnabled(), history.redo)
    await page.getByTestId('network-undo').click()
    assertCaseState(await save(), legacyCase)
    pass('cross-voltage ordinary wiring is rejected without data/history mutation; one undo still affects the prior actual voltage edit')

    await kind('wire').click()
    await connectByClick('gfm-1', 'bus-c')
    const sourceConnected = await save()
    const expectedSourceTopology = clone(fixture)
    expectedSourceTopology.grid_forming_converters[0].bus_id = 'bus-c'
    assert.deepEqual(sourceConnected.topology, expectedSourceTopology, 'Ordinary source-to-bus connection changes only the existing source attachment')
    assert.deepEqual(sourceConnected.diagram_layout, legacyCase.diagram_layout, 'Electrical source migration must not move the existing symbol')
    assert.equal(wires(sourceConnected).length, 0, 'Source attachment is not a new bus-to-bus ideal connection')
    assert.deepEqual(sourceConnected.topology.lines, fixture.lines, 'Source attachment never invents an R/X branch')
    await page.getByTestId('network-undo').click()
    assertCaseState(await save(), legacyCase)
    pass('real GFM-to-free-bus ordinary connection updates only bus_id, creates no impedance line, and one undo restores the whole case')

    await kind('line').click()
    assert.equal(await kind('line').getAttribute('aria-pressed'), 'true')
    await page.getByTestId('network-mode-connect').click()
    await connectByClick('bus-a', 'bus-c')
    const lineCase = await save()
    assert.equal(lineCase.topology.lines.length, 2)
    assert.deepEqual(lineCase.topology.lines[0], fixture.lines[0])
    assert.equal(wires(lineCase).length, 0)
    const newLine = lineCase.topology.lines.find(line => line.id !== 'line-original')
    assert.ok(newLine.resistance_pu > 0 && newLine.reactance_pu > 0)
    assert.deepEqual(new Set([newLine.from_bus_id, newLine.to_bus_id]), new Set(['bus-a', 'bus-c']))
    pass('explicit impedance-line type creates a real positive-R/X branch, not an ideal wire')

    await importCase(legacyCase)
    await page.getByTestId('network-palette-line').click()
    assert.equal(await kind('line').getAttribute('aria-pressed'), 'true')
    await connectByClick('bus-a', 'bus-c')
    const paletteLine = await save()
    assert.equal(paletteLine.topology.lines.length, 2)
    assert.equal(wires(paletteLine).length, 0)
    await importCase(legacyCase)
    await page.getByTestId('network-palette-wire').click()
    assert.equal(await kind('wire').getAttribute('aria-pressed'), 'true')
    await connectByClick('bus-a', 'bus-c')
    const paletteWire = await save()
    assert.deepEqual(paletteWire.topology.lines, fixture.lines)
    assert.equal(wires(paletteWire).length, 1)
    pass('actual palette pointer clicks distinguish ordinary wiring from the explicit impedance-line palette item')

    await importCase(twoBusLegacy)
    await page.getByTestId('network-palette-wire').click()
    await connectByClick('bus-a', 'bus-b')
    const shorted = await save()
    assert.equal(wires(shorted).length, 1)
    assert.deepEqual(shorted.topology, twoBusLegacy.topology, 'Shorted existing branch must remain present with all parameters')
    assert.equal(await analyzeButton().isEnabled(), false)
    assert.equal(await page.getByTestId('wiring-status').textContent(), '接线关系有效', 'A model-unsupported shorted line is not a physically illegal connection')
    assert.equal(await page.getByTestId('low-frequency-applicability').textContent(), '当前接线不适用低频模型')
    const issues = await editor.innerText()
    assert.ok(issues.includes('line-original'), 'Specific shorted physical line ID must be visible')
    assert.ok(/短接|等电位|同一|自环/.test(issues), 'Shorted-branch problem must be explained, not silently repaired')
    assert.ok((await editor.locator('.graph-diagnostic').allTextContents()).some(issue => issue.includes('line-original') && issue.includes('低频模型适用性')),
      'The specific line problem is explained under model applicability, not physical wiring validity')
    assert.equal(analysisRequests.length, 1, 'Invalid short-circuit edit must never be submitted to analysis')
    pass('ordinary wire shorting an existing R/X line is physically valid but model-unsupported; the line remains, analysis is disabled, and line-original is identified')

    await importCase(twoBusLegacy)
    const oldPayload = await analyzePayload()
    assert.deepEqual(oldPayload.topology, twoBusLegacy.topology)
    assert.equal((await save()).schema_version, 'gfm-reduced-order-case/1.1')
    const v10 = clone(twoBusLegacy)
    v10.schema_version = 'gfm-reduced-order-case/1.0'
    delete v10.diagram_layout
    await page.locator('input[type="file"]').setInputFiles({ name: 'old-v1.gfm-case.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(v10)) })
    await frames()
    await until(async () => {
      const imported = await save()
      return imported.diagram_layout && Object.keys(imported.diagram_layout.node_positions).length === 0
    }, 'old 1.0 import has its default layout')
    const oldestPayload = await analyzePayload()
    assert.deepEqual(oldestPayload.topology, twoBusLegacy.topology)
    assert.equal((await save()).schema_version, 'gfm-reduced-order-case/1.1')
    pass('old 1.1 and 1.0 cases still reach the original analysis API contract without wire or width data')

    await importCase(resized)
    if (reviewDir) mkdirSync(reviewDir, { recursive: true })
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 })
      await editor.scrollIntoViewIfNeeded()
      await page.getByTestId('network-fit').click()
      await frames()
      const dimensions = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth }))
      assert.ok(dimensions.document <= dimensions.viewport + 1, `Unexpected horizontal page overflow at ${width}px`)
      await page.getByTestId('network-mode-select').click()
      // Native picker remains usable if a long bus or small viewport overlaps a
      // symbol. Physical click behavior was already checked at desktop width.
      await page.getByTestId('network-element-picker').selectOption('bus:bus-a')
      assert.equal(await widthInput.inputValue(), String(draggedWidth))
      assertBusGeometry(await busGeometry('bus-a'), draggedWidth)
      assertCaseState(await save(), resized)
      if (reviewDir) await editor.screenshot({ path: resolve(reviewDir, `network-ideal-wire-${width}.png`) })
      pass(`${width}px: no page overflow; imported long-bus selection, terminals, and saved wire/layout data remain correct`)
    }
    assert.deepEqual(pageErrors, [])
    assert.deepEqual(unexpectedApi, [], 'No scan/report/dq/other numerical endpoint is permitted')
    assert.equal(analysisRequests.length, 3, 'Exactly three payload-only intercepted analysis calls are expected')
    console.log(`GFM_NETWORK_IDEAL_WIRE_UI_OK (${scenarios} UI/payload scenarios; 3 intercepted requests; ${Date.now() - startedAt}ms; no solver or stability claims)`)
  })(), new Promise((_, reject) => {
    timeout = setTimeout(() => reject(new Error('Ideal-wire UI regression exceeded its 55-second work limit (60 seconds including cleanup).')), 55000)
  })])
} catch (error) {
  if (page && !page.isClosed()) {
    const displayed = await page.evaluate(() => ({
      editorMessage: document.querySelector('.editor-message')?.textContent ?? null,
      saveButtons: [...document.querySelectorAll('button')].filter(element => element.textContent === '保存案例')
        .map(element => ({ text: element.textContent, disabled: element.disabled, visible: element.getClientRects().length > 0 })),
    })).catch(() => null)
    console.error('IDEAL_WIRE_UI_FAILURE', JSON.stringify({
      pageErrors, interceptedRequests: analysisRequests.length, unexpectedApi, displayed,
    }))
  }
  if (reviewDir && page && !page.isClosed()) {
    mkdirSync(reviewDir, { recursive: true })
    await page.screenshot({ path: resolve(reviewDir, 'network-ideal-wire-failure.png'), fullPage: true, timeout: 1500 }).catch(() => {})
  }
  throw error
} finally {
  clearTimeout(timeout)
  await context?.close().catch(() => {})
  await browser?.close().catch(() => {})
  server.closeAllConnections()
  await new Promise(resolveClose => server.close(resolveClose))
}
