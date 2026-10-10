// UI-only action regression for the single-line-style network editor.
// Own random loopback port and installed Chrome/Edge; no solver, installs or build.
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../apps/web/node_modules/playwright-core/index.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = resolve(root, 'apps/web/dist')
assert.ok(existsSync(resolve(dist, 'index.html')), 'Build the frontend first; this test does not build it.')
const executablePath = [process.env.GFM_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find(existsSync)
assert.ok(executablePath, 'An installed Chrome or Edge is required; this test installs nothing.')

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
const fixture = {
  schema_version: '1.0', id: 'editor-usability-ui-only', name: '接线操作测试',
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
    voltage_magnitude_pu: 1, voltage_angle_deg: 0 }],
  loads: [],
}
let browser, context, page, timeout
let scenarios = 0
const pageErrors = []
const solverRequests = []
const unexpectedApi = []
const reviewDir = process.env.GFM_UI_REVIEW_DIR ? resolve(process.env.GFM_UI_REVIEW_DIR) : null
const pass = description => { scenarios += 1; console.log(`PASS ${description}`) }
const until = async (predicate, description) => {
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolveWait => setTimeout(resolveWait, 25))
  }
  throw new Error(`Timed out: ${description}`)
}
const frames = () => page.evaluate(() => new Promise(resolveFrames => {
  requestAnimationFrame(() => requestAnimationFrame(resolveFrames))
}))

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
      if (['/api/reduced-order/analyze', '/api/reduced-order/scan', '/api/reduced-order/n-minus-one',
        '/api/network/dq-admittance', '/api/reports/reduced-order'].includes(path)) {
        solverRequests.push(path)
      } else unexpectedApi.push(path)
      await route.fulfill({ status: 422, json: { detail: 'UI-only test; numerical computation is prohibited' } })
    })
    page = await context.newPage()
    page.setDefaultTimeout(5000)
    page.on('pageerror', error => pageErrors.push(error.message))
    await page.goto(baseUrl)
    await page.getByRole('button', { name: /网络建模/ }).click()
    const editor = page.getByTestId('network-graph-editor')
    const properties = page.getByTestId('network-editor-properties')
    const node = id => page.getByTestId(`network-node-${id}`)
    const mode = name => page.getByTestId(`network-mode-${name}`)
    const busVoltage = () => properties.getByRole('spinbutton', { name: '标称电压 / V', exact: true })
    const save = async () => {
      const [downloaded] = await Promise.all([
        page.waitForEvent('download'),
        page.getByRole('button', { name: '保存案例', exact: true }).click(),
      ])
      return JSON.parse(readFileSync(await downloaded.path(), 'utf8'))
    }
    const importMockCase = async caseData => {
      await page.locator('input[type="file"]').setInputFiles({
        name: 'editor-usability-mock.gfm-case.json', mimeType: 'application/json',
        buffer: Buffer.from(JSON.stringify(caseData)),
      })
      await until(async () => (await page.locator('.editor-message').textContent()).includes('案例已载入'), 'mock case imported')
      await frames()
      // Repeated imports can retain the same status wording, so also verify
      // the committed payload via the real case download before proceeding.
      let lastMismatch
      try {
        await until(async () => {
          const imported = await save()
          try {
            assert.deepEqual(imported.topology, caseData.topology)
            assert.deepEqual(imported.diagram_layout, caseData.diagram_layout)
            return true
          } catch (error) {
            lastMismatch = { message: error.message, expectedLayout: caseData.diagram_layout,
              actualLayout: imported.diagram_layout, status: await page.locator('.editor-message').textContent() }
            return false
          }
        }, 'imported mock payload committed')
      } catch (error) {
        console.error('CASE_IMPORT_MISMATCH', JSON.stringify(lastMismatch))
        throw error
      }
    }
    const dragBetween = async (source, target, offsetX = 0) => {
      const sourceBox = await source.boundingBox()
      const targetBox = await target.boundingBox()
      assert.ok(sourceBox && targetBox, 'Both drag endpoints are rendered')
      const offsetPoint = async (locator, box) => {
        let offset = offsetX
        if (offsetX) {
          const pseudoRadius = await locator.evaluate(element => {
            const box = element.getBoundingClientRect()
            const width = Number.parseFloat(getComputedStyle(element).width)
            const pseudoWidth = Number.parseFloat(getComputedStyle(element, '::before').width)
            return pseudoWidth * (box.width / width) / 2
          })
          assert.ok(Number.isFinite(pseudoRadius) && pseudoRadius > box.width / 2)
          if (Math.abs(offset) + 0.25 >= pseudoRadius) offset = Math.sign(offset) * pseudoRadius * 0.75
          assert.ok(Math.abs(offset) > box.width / 2, 'The drag point must be outside the actual tiny handle bbox')
        }
        const point = { x: box.x + box.width / 2 + offset, y: box.y + box.height / 2 }
        if (offsetX) {
          const hit = await locator.evaluate((element, point) => {
            const actual = document.elementFromPoint(point.x, point.y)?.closest('.react-flow__handle')
            return {
              sameElement: actual === element,
              expectedId: element.getAttribute('data-handleid'),
              actualId: actual?.getAttribute('data-handleid') ?? null,
            }
          }, point)
          assert.ok(hit.sameElement, `Offset point must hit the original handle: ${JSON.stringify(hit)}`)
          assert.equal(hit.actualId, hit.expectedId)
        }
        return point
      }
      const sourcePoint = await offsetPoint(source, sourceBox)
      const targetPoint = await offsetPoint(target, targetBox)
      await page.mouse.move(sourcePoint.x, sourcePoint.y)
      await page.mouse.down()
      await page.mouse.move(targetPoint.x, targetPoint.y, { steps: 8 })
      await page.mouse.up()
      await frames()
    }
    const parallelGeometry = async () => Promise.all(['line-1', 'line-2'].map(id =>
      page.getByTestId(`network-edge-${id}`).evaluate(element => {
        const path = element.querySelector('.react-flow__edge-path')
        const label = element.querySelector('.react-flow__edge-textwrapper')
        if (!(path instanceof SVGPathElement) || !(label instanceof SVGGraphicsElement)) {
          throw new Error('Parallel branch path and SVG label must both be rendered')
        }
        const matrix = label.getScreenCTM()
        if (!matrix) throw new Error('Parallel branch label is not rendered')
        const box = label.getBBox()
        const center = new DOMPoint(box.x + box.width / 2, box.y + box.height / 2).matrixTransform(matrix)
        return { path: path.getAttribute('d'), label: { x: center.x, y: center.y } }
      })))
    const assertParallelSeparation = geometry => {
      assert.ok(geometry.every(branch => branch.path), 'Parallel branches have real SVG paths')
      assert.notEqual(geometry[0].path, geometry[1].path, 'Parallel branches must not share one SVG path')
      assert.ok(Math.hypot(geometry[0].label.x - geometry[1].label.x,
        geometry[0].label.y - geometry[1].label.y) > 5, 'Parallel branch labels must be visibly separated')
    }
    const terminalGeometry = () => page.evaluate(() => {
      const devices = [
        { id: 'bus-1', terminals: { north: 'top', east: 'right', south: 'bottom', west: 'left' } },
        { id: 'grid-bus', terminals: { north: 'top', east: 'right', south: 'bottom', west: 'left' } },
        { id: 'gfm-1', terminals: { output: 'bottom' } },
        { id: 'grid-1', terminals: { output: 'top' } },
      ]
      return devices.flatMap(device => {
        const element = document.querySelector(`[data-testid="network-node-${device.id}"]`)
        const symbol = element?.querySelector('.electrical-node-symbol')
        if (!(symbol instanceof HTMLElement)) throw new Error(`Missing symbol wrapper for ${device.id}`)
        const symbolBox = symbol.getBoundingClientRect()
        return Object.entries(device.terminals).map(([id, position]) => {
          const handle = element.querySelector(`.react-flow__handle[data-handleid="${id}"]`)
          if (!(handle instanceof HTMLElement) || !handle.classList.contains(`react-flow__handle-${position}`)) {
            throw new Error(`Missing ${position} terminal ${device.id}:${id}`)
          }
          const handleBox = handle.getBoundingClientRect()
          // React Flow anchors at the handle's outer edge, not its center.
          const actual = position === 'top' ? { x: handleBox.x + handleBox.width / 2, y: handleBox.y }
            : position === 'bottom' ? { x: handleBox.x + handleBox.width / 2, y: handleBox.y + handleBox.height }
              : position === 'left' ? { x: handleBox.x, y: handleBox.y + handleBox.height / 2 }
                : { x: handleBox.x + handleBox.width, y: handleBox.y + handleBox.height / 2 }
          const expected = position === 'top' ? { x: symbolBox.x + symbolBox.width / 2, y: symbolBox.y }
            : position === 'bottom' ? { x: symbolBox.x + symbolBox.width / 2, y: symbolBox.y + symbolBox.height }
              : position === 'left' ? { x: symbolBox.x, y: symbolBox.y + symbolBox.height / 2 }
                : { x: symbolBox.x + symbolBox.width, y: symbolBox.y + symbolBox.height / 2 }
          return { terminal: `${device.id}:${id}`, actual, expected }
        })
      })
    })
    const assertTerminalAlignment = geometry => {
      assert.equal(geometry.length, 10, 'Two four-terminal busbars and two fixed source outputs are measured')
      for (const { terminal, actual, expected } of geometry) {
        assert.ok(Math.abs(actual.x - expected.x) <= 1 && Math.abs(actual.y - expected.y) <= 1,
          `${terminal}: actual anchor ${JSON.stringify(actual)} must align with symbol boundary ${JSON.stringify(expected)} within 1 screen pixel`)
      }
    }
    const clickEdge = async id => {
      const edge = page.getByTestId(`network-edge-${id}`)
      await edge.waitFor({ state: 'visible' })
      await edge.scrollIntoViewIfNeeded()
      const point = await edge.evaluate((element, edgeId) => {
        const path = element.querySelector('.react-flow__edge-interaction') ?? element.querySelector('path')
        if (!(path instanceof SVGPathElement)) throw new Error('Edge has no SVG hit path')
        const matrix = path.getScreenCTM()
        if (!matrix) throw new Error('Edge is not rendered')
        // A branch midpoint can be underneath a moved busbar; use a real visible
        // hit point instead of programmatically selecting the edge.
        for (const fraction of [0.5, 0.4, 0.6, 0.25, 0.75, 0.1, 0.9]) {
          const local = path.getPointAtLength(path.getTotalLength() * fraction)
          const screen = new DOMPoint(local.x, local.y).matrixTransform(matrix)
          const hit = document.elementFromPoint(screen.x, screen.y)
          if (hit?.closest(`[data-testid="network-edge-${edgeId}"]`)) return { x: screen.x, y: screen.y }
        }
        throw new Error(`Edge ${edgeId} has no visible clickable hit point`)
      }, id)
      await page.mouse.click(point.x, point.y)
      await properties.getByText(`线路 · ${id}`, { exact: true }).waitFor()
    }
    const dragNode = async (id, dx, dy) => {
      await node(id).scrollIntoViewIfNeeded()
      const box = await node(id).boundingBox()
      assert.ok(box, `Node ${id} is rendered`)
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
      await page.mouse.down()
      await page.mouse.move(box.x + box.width / 2 + dx, box.y + box.height / 2 + dy, { steps: 8 })
      await page.mouse.up()
    }
    await editor.waitFor()
    await mode('select').waitFor()
    await until(() => page.getByRole('button', { name: '验证拓扑并分析', exact: true }).isEnabled(), 'fixture loaded')
    assert.equal(await mode('select').getAttribute('aria-pressed'), 'true')
    assert.equal(await mode('connect').getAttribute('aria-pressed'), 'false')
    assert.equal(await mode('pan').getAttribute('aria-pressed'), 'false')
    assert.equal(await node('bus-1').locator('.react-flow__handle.connectablestart').count(), 0)
    pass('selection is the explicit default; connection and panning are separate modes')

    for (const id of ['bus-1', 'grid-bus', 'gfm-1', 'grid-1']) {
      const symbol = page.getByTestId(`network-symbol-${id}`)
      assert.equal(await symbol.evaluate(element => element.tagName.toLowerCase()), 'svg')
      assert.ok(await symbol.locator('line, path, rect, circle, polyline').count() > 0)
    }
    for (const id of ['bus-1', 'grid-bus']) {
      assert.equal(await node(id).locator('.lucide-network').count(), 0, 'Busbar must not be a generic network icon')
      const strokes = await page.getByTestId(`network-symbol-${id}`).evaluate(element =>
        [...element.querySelectorAll('line,path')].map(path => Number(path.getAttribute('stroke-width') ?? 0)))
      assert.ok(strokes.some(width => width >= 3), 'Busbar must have a visible heavy conductor')
    }
    pass('busbars and devices are real single-line SVG symbols, not generic card icons')

    await frames()
    const geometryInput = await save()
    const selectionTerminals = await terminalGeometry()
    assertTerminalAlignment(selectionTerminals)
    for (const nextMode of ['connect', 'select']) {
      await mode(nextMode).click()
      await frames()
      const currentTerminals = await terminalGeometry()
      assertTerminalAlignment(currentTerminals)
      for (let index = 0; index < currentTerminals.length; index += 1) {
        const current = currentTerminals[index]
        const initial = selectionTerminals[index]
        assert.equal(current.terminal, initial.terminal)
        assert.ok(Math.abs(current.actual.x - initial.actual.x) <= 1
          && Math.abs(current.actual.y - initial.actual.y) <= 1,
        `${current.terminal}: changing to ${nextMode} must not move the connection anchor`)
      }
    }
    const geometryAfterModes = await save()
    assert.deepEqual(geometryAfterModes.topology, geometryInput.topology)
    assert.deepEqual(geometryAfterModes.diagram_layout, geometryInput.diagram_layout)
    pass('actual busbar/source terminal outer-edge anchors match symbol boundaries within 1 screen pixel and do not shift between selection and connection modes')

    await mode('connect').click()
    await page.getByTestId('network-connect-kind-line').click()
    assert.equal(await mode('connect').getAttribute('aria-pressed'), 'true')
    await node('bus-1').click()
    await node('grid-bus').click()
    await page.getByTestId('network-edge-line-2').waitFor()
    const connected = await save()
    assert.equal(connected.topology.lines.length, 2)
    assert.deepEqual(connected.topology.lines[0], fixture.lines[0])
    assert.equal(connected.topology.lines[1].from_bus_id, 'bus-1')
    assert.equal(connected.topology.lines[1].to_bus_id, 'grid-bus')
    await dragBetween(
      node('bus-1').locator('.react-flow__handle[data-handleid="south"]'),
      node('grid-bus').locator('.react-flow__handle[data-handleid="north"]'),
      8,
    )
    await page.getByTestId('network-edge-line-3').waitFor()
    const terminalConnected = await save()
    assert.equal(terminalConnected.topology.lines.length, 3)
    assert.deepEqual(terminalConnected.topology.lines.slice(0, 2), connected.topology.lines)
    assert.equal(terminalConnected.topology.lines[2].from_bus_id, 'bus-1')
    assert.equal(terminalConnected.topology.lines[2].to_bus_id, 'grid-bus')
    await page.getByTestId('network-undo').click()
    assert.deepEqual((await save()).topology, connected.topology)
    pass('real bus clicks and terminal dragging from verified expanded-hit-area points create separate lines; undo restores the prior electrical input')

    await frames()
    assertParallelSeparation(await parallelGeometry())
    await page.getByTestId('network-fit').click()
    await frames()
    assertParallelSeparation(await parallelGeometry())
    const parallelRedrawn = await save()
    assert.deepEqual(parallelRedrawn.topology, connected.topology)
    assert.deepEqual(parallelRedrawn.diagram_layout, connected.diagram_layout)
    pass('parallel branches have separate real SVG paths and label positions; viewport geometry redraw and saving preserve electrical input')

    const targetUpdater = page.getByTestId('rf__edge-line:line-2').locator('.react-flow__edgeupdater-target')
    const updaterBox = await targetUpdater.boundingBox()
    const reconnectPane = await editor.locator('.react-flow__pane').boundingBox()
    assert.ok(updaterBox && reconnectPane)
    await page.mouse.move(updaterBox.x + updaterBox.width / 2, updaterBox.y + updaterBox.height / 2)
    await page.mouse.down()
    await page.mouse.move(reconnectPane.x + reconnectPane.width * 0.85, reconnectPane.y + reconnectPane.height * 0.8, { steps: 8 })
    await page.mouse.up()
    await frames()
    assert.deepEqual((await save()).topology, connected.topology)
    await page.getByTestId('network-edge-line-2').waitFor()
    pass('dropping a real branch reconnection onto blank canvas leaves its endpoints and parameters unchanged')

    await node('bus-1').click()
    await node('bus-1').click()
    await until(async () => (await page.locator('.editor-message').textContent()).includes('同一母线'), 'self-loop rejected')
    const selfLoop = await save()
    assert.deepEqual(selfLoop.topology, connected.topology)
    await page.getByTestId('network-connect-cancel').click()
    pass('self-loop attempt is rejected and the saved electrical topology is unchanged')
    await page.getByTestId('network-undo').click()
    assert.equal((await save()).topology.lines.length, 1, 'Rejected wiring must not add a history entry')
    await page.getByTestId('network-redo').click()
    await page.getByTestId('network-edge-line-2').waitFor()
    assert.deepEqual((await save()).topology, connected.topology)
    pass('rejected wiring leaves undo history unchanged; undo/redo affects the real prior edit')

    await node('bus-1').click()
    await page.getByTestId('network-connect-cancel').click()
    assert.deepEqual((await save()).topology, connected.topology)
    pass('cancelling a partially selected connection has no electrical side effect')

    await mode('select').click()
    await node('grid-bus').click()
    await busVoltage().fill('10000')
    const highVoltage = await save()
    await mode('connect').click()
    await page.getByTestId('network-connect-kind-line').click()
    await node('bus-1').click()
    await node('grid-bus').click()
    await until(async () => /电压|变压器/.test(await page.locator('.editor-message').textContent()), 'cross-voltage connection rejected')
    assert.deepEqual((await save()).topology, highVoltage.topology)
    await page.getByTestId('network-connect-cancel').click()
    await mode('select').click()
    await node('grid-bus').click()
    await busVoltage().fill('400')
    pass('cross-voltage line is rejected; editing and connecting do not invent a transformer')

    await clickEdge('line-2')
    await properties.getByRole('spinbutton', { name: 'X / p.u.', exact: true }).fill('0.37')
    const edited = await save()
    assert.equal(edited.topology.lines.find(line => line.id === 'line-2').reactance_pu, 0.37)
    assert.equal(edited.topology.lines.find(line => line.id === 'line-1').reactance_pu, 0.2)
    pass('clicking a branch opens its local parameters and edits only the selected branch')

    await page.getByTestId('network-line-delete').click()
    await until(() => page.getByTestId('network-edge-line-2').count().then(count => count === 0), 'selected line removed')
    assert.equal((await save()).topology.lines.length, 1)
    await page.getByTestId('network-undo').click()
    await page.getByTestId('network-edge-line-2').waitFor()
    assert.deepEqual((await save()).topology, edited.topology)
    pass('branch deletion and real undo restore the entire electrical input')

    // Undo restores case data, not a deleted element's selection state.
    await clickEdge('line-2')
    await properties.getByRole('spinbutton', { name: 'X / p.u.', exact: true }).fill('0.41')
    const keyboardEdited = await save()
    await page.getByTestId('network-undo').focus()
    await page.keyboard.press('Control+z')
    await until(() => properties.getByRole('spinbutton', { name: 'X / p.u.', exact: true }).inputValue().then(value => value === '0.37'), 'keyboard undo applied')
    assert.deepEqual((await save()).topology, edited.topology)
    await page.getByTestId('network-redo').focus()
    await page.keyboard.press('Control+y')
    await until(() => properties.getByRole('spinbutton', { name: 'X / p.u.', exact: true }).inputValue().then(value => value === '0.41'), 'keyboard redo applied')
    assert.deepEqual((await save()).topology, keyboardEdited.topology)
    pass('actual Ctrl+Z and Ctrl+Y undo and redo the selected branch edit')

    for (const input of [
      properties.getByRole('spinbutton', { name: 'X / p.u.', exact: true }),
      properties.getByRole('textbox', { name: '名称', exact: true }),
      properties.getByRole('combobox', { name: '首端', exact: true }),
    ]) {
      const cancelled = await input.evaluate(element => {
        element.focus()
        const event = new KeyboardEvent('keydown', { key: 'z', code: 'KeyZ', ctrlKey: true, bubbles: true, cancelable: true })
        element.dispatchEvent(event)
        return event.defaultPrevented
      })
      assert.equal(cancelled, false, 'The editor must not intercept undo inside an input/select')
      assert.deepEqual((await save()).topology, keyboardEdited.topology)
    }
    // Synthetic keydown checks editor scoping only, not browser-native text undo.
    pass('input/select Ctrl+Z keydown does not invoke graph undo or get cancelled; native text undo is not tested')
    await properties.getByRole('spinbutton', { name: 'X / p.u.', exact: true }).fill('0.37')

    const beforeExpand = await save()
    const normalBox = await editor.boundingBox()
    assert.ok(normalBox)
    await page.getByTestId('network-expand-editor').click()
    assert.equal(await page.getByTestId('network-expand-editor').getAttribute('aria-pressed'), 'true')
    assert.equal(await page.locator('.model-controls').isVisible(), false)
    const expandedBox = await editor.boundingBox()
    assert.ok(expandedBox && expandedBox.width > normalBox.width + 50, 'Expand must actually increase usable width')
    await mode('pan').click()
    assert.equal(await mode('pan').getAttribute('aria-pressed'), 'true')
    await mode('select').click()
    await node('bus-1').click()
    assert.equal(await busVoltage().inputValue(), '400')
    const expanded = await save()
    assert.deepEqual(expanded.topology, beforeExpand.topology)
    assert.deepEqual(expanded.diagram_layout, beforeExpand.diagram_layout)
    await page.getByTestId('network-expand-editor').click()
    assert.equal(await page.getByTestId('network-expand-editor').getAttribute('aria-pressed'), 'false')
    assert.equal(await page.locator('.model-controls').isVisible(), true)
    const restoredWidth = await save()
    assert.deepEqual(restoredWidth.topology, beforeExpand.topology)
    assert.deepEqual(restoredWidth.diagram_layout, beforeExpand.diagram_layout)
    pass('expanded-canvas and restored-canvas modes remain operable without changing case data')

    await mode('select').click()
    await page.getByTestId('network-snap').check()
    const beforeDrag = await save()
    const beforeStyle = await page.locator('.react-flow__node[data-id="bus:bus-1"]').getAttribute('style')
    // Move away from the adjacent bus: this test verifies dragging, not
    // automatic obstacle-avoiding routing through overlapping node hit boxes.
    await dragNode('bus-1', -73, 37)
    await until(async () => await page.locator('.react-flow__node[data-id="bus:bus-1"]').getAttribute('style') !== beforeStyle, 'bus dragged')
    const moved = await save()
    assert.deepEqual(moved.topology, beforeDrag.topology)
    const movedPosition = moved.diagram_layout.node_positions['bus:bus-1']
    assert.ok(movedPosition)
    assert.ok(Math.abs(movedPosition.x / 20 - Math.round(movedPosition.x / 20)) < 1e-8)
    assert.ok(Math.abs(movedPosition.y / 20 - Math.round(movedPosition.y / 20)) < 1e-8)
    assert.notDeepEqual(moved.diagram_layout, beforeDrag.diagram_layout)
    pass('snapped node dragging changes saved layout, not electrical data')

    await mode('pan').click()
    assert.equal(await mode('pan').getAttribute('aria-pressed'), 'true')
    assert.equal(await node('bus-1').locator('.react-flow__handle.connectablestart').count(), 0)
    const viewport = editor.locator('.react-flow__viewport')
    const beforePan = await viewport.getAttribute('style')
    const paneBox = await editor.locator('.react-flow__pane').boundingBox()
    assert.ok(paneBox)
    const panX = paneBox.x + paneBox.width * 0.8
    const panY = paneBox.y + paneBox.height * 0.85
    await page.mouse.move(panX, panY)
    await page.mouse.down()
    await page.mouse.move(panX - 70, panY - 30, { steps: 8 })
    await page.mouse.up()
    await until(async () => await viewport.getAttribute('style') !== beforePan, 'viewport panned')
    const panned = await save()
    assert.deepEqual(panned.topology, moved.topology)
    assert.deepEqual(panned.diagram_layout, moved.diagram_layout)
    pass('panning changes the viewport only, never saved node positions or electrical data')

    const pannedStyle = await viewport.getAttribute('style')
    await page.getByTestId('network-fit').click()
    await until(async () => await viewport.getAttribute('style') !== pannedStyle, 'fit changes the panned viewport')
    const fitted = await save()
    assert.deepEqual(fitted.topology, moved.topology)
    assert.deepEqual(fitted.diagram_layout, moved.diagram_layout)
    await mode('select').click()
    await node('bus-1').click()
    assert.equal(await busVoltage().inputValue(), '400')
    pass('fit-to-canvas retains input and permits node selection afterward')

    // Explicit teaching-only import: the third bus has no source attached.
    const teachingCase = structuredClone(fitted)
    teachingCase.topology.buses.push({ id: 'spare-bus', name: '测试备用母线', nominal_voltage_v: 400 })
    teachingCase.topology.lines.push({ ...fixture.lines[0], id: 'line-spare-test', name: '测试备用线路',
      from_bus_id: 'grid-bus', to_bus_id: 'spare-bus' })
    teachingCase.diagram_layout.node_positions['bus:spare-bus'] = { x: 550, y: 170 }
    await importMockCase(teachingCase)
    await node('spare-bus').waitFor()
    assert.deepEqual((await save()).topology, teachingCase.topology)
    await page.getByTestId('network-fit').click()
    await frames()
    await node('grid-1').click()
    await properties.getByRole('combobox', { name: '接入母线', exact: true }).selectOption('spare-bus')
    const migrated = await save()
    const expectedMigration = structuredClone(teachingCase.topology)
    expectedMigration.infinite_buses.find(grid => grid.id === 'grid-1').bus_id = 'spare-bus'
    expectedMigration.reference_bus_id = 'spare-bus'
    assert.deepEqual(migrated.topology, expectedMigration)
    await page.getByTestId('network-undo').click()
    const migrationUndone = await save()
    assert.deepEqual(migrationUndone.topology, teachingCase.topology)
    assert.deepEqual(migrationUndone.diagram_layout, teachingCase.diagram_layout)
    await importMockCase(fitted)
    await until(() => node('spare-bus').count().then(count => count === 0), 'teaching bus removed by restoring the actual mock case')
    const restoredMock = await save()
    assert.deepEqual(restoredMock.topology, fitted.topology)
    assert.deepEqual(restoredMock.diagram_layout, fitted.diagram_layout)
    pass('imported teaching bus: source migration updates its reference bus atomically; undo restores both fields and the original mock case is reimported')

    const lineDetails = page.locator('details').filter({ has: page.locator('summary').filter({ hasText: /^线路参数/ }) })
    await lineDetails.locator('summary').click()
    const firstLineRow = lineDetails.locator('.line-row').first()
    await firstLineRow.getByRole('textbox', { name: 'ID', exact: true }).waitFor({ state: 'visible' })
    assert.equal(await firstLineRow.getByRole('textbox', { name: 'ID', exact: true }).inputValue(), 'line-1')
    const historyBeforeRefusal = {
      undo: await page.getByTestId('network-undo').isEnabled(),
      redo: await page.getByTestId('network-redo').isEnabled(),
    }
    for (const [endpoint, invalidBus, originalBus] of [
      ['首端', 'grid-bus', 'bus-1'], ['末端', 'bus-1', 'grid-bus'],
    ]) {
      const select = firstLineRow.getByRole('combobox', { name: endpoint, exact: true })
      await select.selectOption(invalidBus)
      await until(async () => (await page.locator('.editor-message').textContent()).includes('同一母线'), 'table self-loop refused')
      assert.equal(await select.inputValue(), originalBus)
      assert.deepEqual((await save()).topology, fitted.topology)
      assert.equal(await page.getByTestId('network-undo').isEnabled(), historyBeforeRefusal.undo)
      assert.equal(await page.getByTestId('network-redo').isEnabled(), historyBeforeRefusal.redo)
    }
    await lineDetails.locator('summary').click()
    pass('real line-table expansion: invalid source and target edits leave saved topology and undo/redo availability unchanged')

    const vsmDetails = page.locator('details').filter({ has: page.locator('summary').filter({ hasText: /^VSM 控制参数/ }) })
    await vsmDetails.locator('summary').click()
    const vsmBus = vsmDetails.locator('.gfm-row').first().getByRole('combobox', { name: '接入母线', exact: true })
    await vsmBus.waitFor({ state: 'visible' })
    const vsmOptions = await vsmBus.locator('option').evaluateAll(options => options.map(option => option.value))
    assert.ok(vsmOptions.includes('bus-1'), 'The VSM retains its existing bus option')
    assert.ok(!vsmOptions.includes('grid-bus'), 'A grid-occupied bus is not a VSM attachment option')
    assert.deepEqual((await save()).topology, fitted.topology)
    await vsmDetails.locator('summary').click()
    pass('real VSM-table expansion: attachment dropdown excludes the grid-occupied bus without mutating the case')

    // Deliberately crowded teaching layout, not a modification to a real case.
    await page.setViewportSize({ width: 390, height: 1000 })
    const crowdedCase = structuredClone(fitted)
    // Unmoved nodes need not have persisted coordinates. Read the real canvas
    // position, not screen coordinates or an assumed full-layout snapshot.
    const crowdedPosition = crowdedCase.diagram_layout.node_positions['bus:grid-bus']
      ?? await node('grid-bus').evaluate(element => {
        const wrapper = element.closest('.react-flow__node')
        if (!wrapper) throw new Error('Missing grid-bus wrapper for crowded layout')
        const matrix = new DOMMatrixReadOnly(getComputedStyle(wrapper).transform)
        if (!Number.isFinite(matrix.e) || !Number.isFinite(matrix.f)) throw new Error('Non-finite crowded bus position')
        return { x: matrix.e, y: matrix.f }
      })
    crowdedCase.diagram_layout.node_positions['bus:grid-bus'] = structuredClone(crowdedPosition)
    crowdedCase.diagram_layout.node_positions['bus:bus-1'] = structuredClone(crowdedPosition)
    await importMockCase(crowdedCase)
    await mode('select').click()
    await page.getByTestId('network-fit').click()
    await frames()
    // One browser-side sample avoids reading two different fitView animation frames.
    const [crowdedBus, adjacentBus] = await page.evaluate(() => ['bus-1', 'grid-bus'].map(id => {
      const element = document.querySelector(`[data-testid="network-node-${id}"]`)
      if (!(element instanceof HTMLElement)) throw new Error(`Missing crowded bus ${id}`)
      const { x, y, width, height } = element.getBoundingClientRect()
      return { x, y, width, height }
    }))
    assert.ok(Math.min(crowdedBus.x + crowdedBus.width, adjacentBus.x + adjacentBus.width)
      - Math.max(crowdedBus.x, adjacentBus.x) > Math.min(crowdedBus.width, adjacentBus.width) / 2)
    assert.ok(Math.min(crowdedBus.y + crowdedBus.height, adjacentBus.y + adjacentBus.height)
      - Math.max(crowdedBus.y, adjacentBus.y) > Math.min(crowdedBus.height, adjacentBus.height) / 2)
    const picker = page.getByTestId('network-element-picker')
    assert.equal(await picker.evaluate(element => element.tagName.toLowerCase()), 'select')
    await picker.selectOption('line:line-1')
    await properties.getByText('线路 · line-1', { exact: true }).waitFor()
    await properties.getByRole('spinbutton', { name: 'X / p.u.', exact: true }).fill('0.29')
    const crowdedEdited = await save()
    const expectedCrowdedEdit = structuredClone(crowdedCase.topology)
    expectedCrowdedEdit.lines.find(line => line.id === 'line-1').reactance_pu = 0.29
    assert.deepEqual(crowdedEdited.topology, expectedCrowdedEdit)
    assert.deepEqual(crowdedEdited.diagram_layout, crowdedCase.diagram_layout)
    if (reviewDir) {
      mkdirSync(reviewDir, { recursive: true })
      await editor.screenshot({ path: resolve(reviewDir, 'network-editor-usability-crowded-390.png') })
    }
    await page.getByTestId('network-undo').click()
    assert.deepEqual((await save()).topology, crowdedCase.topology)
    await importMockCase(fitted)
    assert.deepEqual((await save()).diagram_layout, fitted.diagram_layout)
    await page.setViewportSize({ width: 1440, height: 1000 })
    pass('390px overlapping busbars: native element picker selects the obscured line; parameter edit, saving and undo preserve the other branch and layout')

    if (reviewDir) mkdirSync(reviewDir, { recursive: true })
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 })
      await editor.scrollIntoViewIfNeeded()
      await page.getByTestId('network-fit').click()
      await frames()
      const dimensions = await page.evaluate(() => ({
        viewport: document.documentElement.clientWidth,
        document: document.documentElement.scrollWidth,
      }))
      assert.ok(dimensions.document <= dimensions.viewport + 1, `Page overflow at ${width}px`)
      await mode('connect').click()
      await page.getByTestId('network-connect-kind-line').click()
      assert.equal(await mode('connect').getAttribute('aria-pressed'), 'true')
      await mode('select').click()
      await node('bus-1').click()
      assert.equal(await busVoltage().inputValue(), '400')
      if (width === 390) {
        const voltage = busVoltage()
        await voltage.fill('440')
        assert.equal((await save()).topology.buses.find(bus => bus.id === 'bus-1').nominal_voltage_v, 440)
        await voltage.fill('400')
        await clickEdge('line-2')
        const inService = page.getByTestId('network-line-in-service')
        await inService.uncheck()
        assert.equal((await save()).topology.lines.find(line => line.id === 'line-2').in_service, false)
        await inService.check()
        assert.deepEqual((await save()).topology, moved.topology)
        pass('390px: local parameter editing and branch service switching work and can be restored')
      }
      assert.deepEqual((await save()).topology, moved.topology)
      if (reviewDir) await editor.screenshot({ path: resolve(reviewDir, `network-editor-usability-${width}.png`) })
      pass(`${width}px: no page overflow; mode navigation, bus selection and saving work`)
    }
    assert.deepEqual(pageErrors, [])
    assert.deepEqual(solverRequests, [], 'This test must never invoke a numerical solver or report API')
    assert.deepEqual(unexpectedApi, [])
    console.log(`GFM_NETWORK_EDITOR_USABILITY_UI_OK (${scenarios} UI-only action scenarios)`)
  })(), new Promise((_, reject) => {
    timeout = setTimeout(() => reject(new Error('UI usability test exceeded its 60-second total limit.')), 60000)
  })])
} catch (error) {
  if (reviewDir && page && !page.isClosed()) {
    mkdirSync(reviewDir, { recursive: true })
    await page.screenshot({ path: resolve(reviewDir, 'network-editor-usability-failure.png'), fullPage: true }).catch(() => {})
  }
  throw error
} finally {
  clearTimeout(timeout)
  await context?.close().catch(() => {})
  await browser?.close().catch(() => {})
  server.closeAllConnections()
  await new Promise(resolveClose => server.close(resolveClose))
}
