// UI-only palette placement and local shortcut regression. No build or solver.
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
assert.ok(executablePath, 'An installed Chrome or Edge is required; nothing is installed by this test.')
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
  schema_version: '1.0', id: 'palette-ui-only', name: '元件放置操作测试',
  frame_convention_id: 'power-invariant-park-q-lag-v1',
  base_values: { apparent_power_va: 1e6, voltage_v: 400, frequency_hz: 50 }, reference_bus_id: 'grid-bus',
  buses: ['bus-1', 'grid-bus'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
  lines: [{ id: 'line-1', name: '线路 1', from_bus_id: 'bus-1', to_bus_id: 'grid-bus',
    resistance_pu: 0.01, reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true }],
  grid_forming_converters: [{ id: 'gfm-1', name: 'VSM 1', bus_id: 'bus-1',
    control_mode: 'virtual_synchronous_machine', rated_apparent_power_va: 1e6,
    active_power_setpoint_pu: 0, reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1,
    virtual_inertia_s: 2, damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1 }],
  infinite_buses: [{ id: 'grid-1', name: '等值电源', bus_id: 'grid-bus', voltage_magnitude_pu: 1, voltage_angle_deg: 0 }],
  loads: [],
}
const storageKey = 'gfm-network-editor-shortcuts/1.0'
const defaults = { select: 'V', connect: 'C', pan: 'H', bus: 'B', gfm: 'G', grid: 'E', fit: 'F' }
const collections = ['buses', 'lines', 'grid_forming_converters', 'infinite_buses', 'loads']
const reviewDir = process.env.GFM_UI_REVIEW_DIR ? resolve(process.env.GFM_UI_REVIEW_DIR) : null
let browser, context, page, timeout, scenarios = 0
const pageErrors = [], apiCalls = []
const pass = description => { scenarios += 1; console.log(`PASS ${description}`) }
const until = async (predicate, description) => {
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolveWait => setTimeout(resolveWait, 25))
  }
  throw new Error(`Timed out: ${description}`)
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
          id: `reduced-smib-${kind}`, name: `UI ${kind}`, topology: structuredClone(fixture),
        })) } }); return
      }
      apiCalls.push(path)
      await route.fulfill({ status: 422, json: { detail: 'UI-only test: numerical and report requests are prohibited.' } })
    })
    page = await context.newPage()
    page.setDefaultTimeout(5000)
    page.on('pageerror', error => pageErrors.push(error.message))
    const editor = page.getByTestId('network-graph-editor')
    const canvas = editor.locator('.network-graph-canvas')
    const properties = page.getByTestId('network-editor-properties')
    const node = id => page.getByTestId(`network-node-${id}`)
    const mode = name => page.getByTestId(`network-mode-${name}`)
    const palette = tool => page.getByTestId(`network-palette-${tool}`)
    const frames = () => page.evaluate(() => new Promise(resolveFrames => requestAnimationFrame(() => requestAnimationFrame(resolveFrames))))
    const settleViewport = () => page.evaluate(() => new Promise((resolveStable, reject) => {
      const viewport = document.querySelector('[data-testid="network-graph-editor"] .react-flow__viewport')
      let previous, stable = 0, count = 0
      const sample = () => {
        const value = viewport?.getAttribute('style')
        stable = value === previous ? stable + 1 : 0
        previous = value
        if (stable >= 3) resolveStable()
        else if (++count >= 120) reject(new Error('Viewport animation did not settle'))
        else requestAnimationFrame(sample)
      }
      requestAnimationFrame(sample)
    }))
    const save = async () => {
      const [download] = await Promise.all([
        page.waitForEvent('download'), page.getByRole('button', { name: '保存案例', exact: true }).click(),
      ])
      return JSON.parse(readFileSync(await download.path(), 'utf8'))
    }
    const assertCase = (actual, expected) => {
      assert.deepEqual(actual.topology, expected.topology)
      assert.deepEqual(actual.diagram_layout, expected.diagram_layout)
      assert.deepEqual(actual.simulation_settings, expected.simulation_settings)
    }
    const importCase = async value => {
      await page.locator('input[type="file"]').setInputFiles({ name: 'palette-mock.gfm-case.json',
        mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(value)) })
      await until(async () => { try { assertCase(await save(), value); return true } catch { return false } }, 'mock import committed')
      await frames()
    }
    const openEditor = async () => {
      await page.goto(baseUrl)
      await page.getByRole('button', { name: /网络建模/ }).click()
      await editor.waitFor()
      await until(() => node('gfm-1').count().then(count => count === 1), 'fixture loaded')
      await editor.scrollIntoViewIfNeeded()
      await settleViewport()
    }
    const flowPoint = point => canvas.evaluate((element, point) => {
      const flow = element.querySelector('.react-flow')
      const viewport = element.querySelector('.react-flow__viewport')
      if (!flow || !viewport) throw new Error('Canvas transform is missing')
      const box = flow.getBoundingClientRect()
      const matrix = new DOMMatrixReadOnly(getComputedStyle(viewport).transform)
      const local = new DOMPoint(point.x - box.x, point.y - box.y).matrixTransform(matrix.inverse())
      return { x: local.x, y: local.y }
    }, point)
    const blankPoint = async (preferred = [0.8, 0.2]) => {
      // Saving from the sidebar can scroll the actual canvas out of view.
      await canvas.scrollIntoViewIfNeeded()
      return canvas.evaluate((element, preferred) => {
        const box = element.getBoundingClientRect()
        const candidates = [preferred, [0.2, 0.2], [0.8, 0.8], [0.2, 0.8], [0.5, 0.15], [0.5, 0.85], [0.5, 0.5]]
        for (const y of [0.12, 0.28, 0.44, 0.6, 0.76, 0.9]) {
          for (const x of [0.1, 0.25, 0.4, 0.55, 0.7, 0.85, 0.95]) candidates.push([x, y])
        }
        for (const [x, y] of candidates) {
          const point = { x: box.x + box.width * x, y: box.y + box.height * y }
          if (point.x < 8 || point.x > innerWidth - 8 || point.y < 8 || point.y > innerHeight - 8) continue
          const hit = document.elementFromPoint(point.x, point.y)
          if (hit?.closest('.network-graph-canvas') === element && !hit.closest('.react-flow__node, .react-flow__edge')) return point
        }
        throw new Error(`No actual visible empty canvas hit point: ${JSON.stringify({ x: box.x, y: box.y, width: box.width, height: box.height, viewport: [innerWidth, innerHeight] })}`)
      }, preferred)
    }
    const busPoint = async id => {
      await node(id).waitFor({ state: 'visible' })
      await node(id).scrollIntoViewIfNeeded()
      return node(id).evaluate((element, id) => {
        const symbol = element.querySelector('.electrical-node-symbol')
        const box = symbol.getBoundingClientRect()
        const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 }
        const hit = document.elementFromPoint(point.x, point.y)?.closest('.react-flow__node')
        if (hit?.getAttribute('data-id') !== `bus:${id}`) throw new Error(`Bus ${id} is not the real pointer target`)
        return point
      }, id)
    }
    const dragTool = async (tool, target) => {
      await editor.scrollIntoViewIfNeeded()
      await palette(tool).scrollIntoViewIfNeeded()
      const source = await palette(tool).boundingBox()
      assert.ok(source)
      await page.mouse.move(source.x + source.width / 2, source.y + source.height / 2)
      await page.mouse.down()
      await frames()
      const point = await target()
      await page.mouse.move(point.x, point.y, { steps: 8 })
      const diagramPoint = await flowPoint(point)
      await page.mouse.up()
      await frames()
      return { point, diagramPoint }
    }
    const added = (before, after, collection) => after.topology[collection].filter(item => !before.topology[collection].some(old => old.id === item.id))
    const assertAddOnly = (before, after, counts) => {
      for (const collection of collections) {
        assert.equal(after.topology[collection].length, before.topology[collection].length + (counts[collection] ?? 0), collection)
        for (const old of before.topology[collection]) assert.deepEqual(after.topology[collection].find(item => item.id === old.id), old)
      }
      assert.deepEqual(after.topology.base_values, before.topology.base_values)
      assert.equal(after.topology.reference_bus_id, before.topology.reference_bus_id)
      for (const [id, position] of Object.entries(before.diagram_layout.node_positions)) {
        assert.deepEqual(after.diagram_layout.node_positions[id], position)
      }
    }
    const assertDropPosition = (saved, nodeId, point, half) => {
      const position = saved.diagram_layout.node_positions[nodeId]
      assert.ok(position && Number.isFinite(position.x) && Number.isFinite(position.y))
      for (const axis of ['x', 'y']) {
        assert.ok(Math.abs(position[axis] / 20 - Math.round(position[axis] / 20)) < 1e-8, 'Placement uses a 20-unit grid')
        assert.ok(Math.abs(position[axis] - (point[axis] - half[axis])) <= 10.01,
          `Saved placement matches the actual drop center after canvas transformation: ${JSON.stringify({ axis, position, drop: point, half })}`)
      }
    }
    const assertAtomic = async (before, after) => {
      await page.getByTestId('network-undo').click(); assertCase(await save(), before)
      await page.getByTestId('network-redo').click(); assertCase(await save(), after)
    }
    const settings = () => page.getByTestId('network-shortcut-settings')
    const keyInput = name => page.getByTestId(`network-shortcut-input-${name}`)
    const readStored = () => page.evaluate(key => localStorage.getItem(key), storageKey)
    const setEditorKey = async key => { await mode('select').focus(); await page.keyboard.press(key); await frames() }

    await openEditor()
    let current = await save()
    assert.deepEqual({ ...current.topology, id: fixture.id, name: fixture.name }, fixture)
    for (const tool of ['bus', 'gfm', 'grid', 'line']) await palette(tool).waitFor({ state: 'visible' })
    pass('palette loads with the real fixture, without numerical requests')

    let before = current
    const busDrop = await dragTool('bus', () => blankPoint([0.8, 0.2]))
    current = await save(); assertAddOnly(before, current, { buses: 1 })
    const targetBus = added(before, current, 'buses')[0]
    assertDropPosition(current, `bus:${targetBus.id}`, busDrop.diagramPoint, { x: 88, y: 44 })
    pass('real pointer drag inserts one independent bus at the transformed snapped drop location')

    before = current
    await palette('bus').click(); assertCase(await save(), before)
    const clickPoint = await blankPoint([0.2, 0.2])
    await page.mouse.click(clickPoint.x, clickPoint.y); await frames()
    current = await save(); assertAddOnly(before, current, { buses: 1 })
    const unassignedBus = added(before, current, 'buses')[0]
    pass('palette click waits for an actual canvas placement and does not immediately add equipment')

    before = current
    await dragTool('gfm', () => busPoint(targetBus.id))
    current = await save(); assertAddOnly(before, current, { grid_forming_converters: 1 })
    const attachedGfm = added(before, current, 'grid_forming_converters')[0]
    assert.equal(attachedGfm.bus_id, targetBus.id)
    assert.notEqual(attachedGfm.bus_id, unassignedBus.id)
    pass('pointer drop onto an explicitly hit free bus attaches there, not to another free bus')

    for (const [tool, occupiedBus] of [['grid', targetBus.id], ['gfm', 'grid-bus']]) {
      before = current
      const history = { undo: await page.getByTestId('network-undo').isEnabled(), redo: await page.getByTestId('network-redo').isEnabled() }
      await dragTool(tool, () => busPoint(occupiedBus))
      assertCase(await save(), before)
      assert.equal(await page.getByTestId('network-undo').isEnabled(), history.undo)
      assert.equal(await page.getByTestId('network-redo').isEnabled(), history.redo)
      await setEditorKey('Escape')
    }
    pass('source drops onto occupied buses are refused without fallback attachment or history changes')

    before = current
    const gridDrop = await dragTool('grid', () => blankPoint([0.8, 0.8]))
    current = await save(); assertAddOnly(before, current, { buses: 1, infinite_buses: 1 })
    const newGrid = added(before, current, 'infinite_buses')[0]
    const gridBus = added(before, current, 'buses')[0]
    assert.equal(newGrid.bus_id, gridBus.id)
    assertDropPosition(current, `grid:${newGrid.id}`, gridDrop.diagramPoint, { x: 64, y: 64 })
    const gridPosition = current.diagram_layout.node_positions[`grid:${newGrid.id}`]
    assert.deepEqual(current.diagram_layout.node_positions[`bus:${gridBus.id}`], { x: gridPosition.x - 24, y: gridPosition.y - 132 })
    await assertAtomic(before, current)
    pass('blank-canvas grid placement creates its own bus and source in one undo/redo transaction')

    before = current
    await page.getByTestId('network-zoom-out').click(); await settleViewport()
    const gfmDrop = await dragTool('gfm', () => blankPoint([0.2, 0.2]))
    current = await save(); assertAddOnly(before, current, { buses: 1, grid_forming_converters: 1 })
    const blankGfm = added(before, current, 'grid_forming_converters')[0]
    const gfmBus = added(before, current, 'buses')[0]
    assert.equal(blankGfm.bus_id, gfmBus.id)
    assert.notEqual(blankGfm.bus_id, unassignedBus.id)
    assertDropPosition(current, `gfm:${blankGfm.id}`, gfmDrop.diagramPoint, { x: 64, y: 64 })
    const gfmPosition = current.diagram_layout.node_positions[`gfm:${blankGfm.id}`]
    assert.deepEqual(current.diagram_layout.node_positions[`bus:${gfmBus.id}`], { x: gfmPosition.x - 24, y: gfmPosition.y + 144 })
    await assertAtomic(before, current)
    pass('zoomed pointer drop creates a new GFM/bus at the actual canvas coordinates, with one-step undo/redo')

    before = current
    await page.locator('.editor-toolbar .inline-actions').getByRole('button', { name: 'VSM', exact: true }).click()
    assertCase(await save(), before)
    const legacyPoint = await blankPoint([0.8, 0.2])
    await page.mouse.click(legacyPoint.x, legacyPoint.y); await frames()
    current = await save(); assertAddOnly(before, current, { buses: 1, grid_forming_converters: 1 })
    const legacyGfm = added(before, current, 'grid_forming_converters')[0]
    assert.notEqual(legacyGfm.bus_id, unassignedBus.id)
    assert.ok(added(before, current, 'buses').some(bus => bus.id === legacyGfm.bus_id))
    pass('legacy add-source toolbar also waits for placement and does not choose the first free bus')

    before = current
    await page.getByTestId('network-fit').click(); await settleViewport()
    await page.locator('.editor-toolbar .inline-actions').getByRole('button', { name: '阻抗线路', exact: true }).click()
    assert.equal(await mode('connect').getAttribute('aria-pressed'), 'true')
    assertCase(await save(), before)
    await node(targetBus.id).click(); await node(gridBus.id).click()
    current = await save(); assertAddOnly(before, current, { lines: 1 })
    const explicitLine = added(before, current, 'lines')[0]
    assert.equal(explicitLine.from_bus_id, targetBus.id); assert.equal(explicitLine.to_bus_id, gridBus.id)
    await palette('line').click(); assertCase(await save(), current)
    await setEditorKey('Escape')
    before = current
    await page.getByTestId('network-connect-kind-line').click()
    await node(unassignedBus.id).click()
    assertCase(await save(), before)
    await node('bus-1').click(); await frames()
    current = await save(); assertAddOnly(before, current, { lines: 1 })
    const draggedLine = added(before, current, 'lines')[0]
    assert.equal(draggedLine.from_bus_id, unassignedBus.id); assert.equal(draggedLine.to_bus_id, 'bus-1')
    pass('impedance-line mode waits for explicit endpoints and never substitutes an ordinary wire')

    await setEditorKey('H'); assert.equal(await mode('pan').getAttribute('aria-pressed'), 'true')
    const viewport = editor.locator('.react-flow__viewport')
    const initialView = await viewport.getAttribute('style')
    const panPoint = await blankPoint([0.5, 0.8])
    await page.mouse.move(panPoint.x, panPoint.y); await page.mouse.down()
    await page.mouse.move(panPoint.x - 35, panPoint.y - 25, { steps: 8 }); await page.mouse.up()
    await until(async () => (await viewport.getAttribute('style')) !== initialView, 'keyboard pan mode moves the viewport')
    assertCase(await save(), current)
    await setEditorKey('V'); assert.equal(await mode('select').getAttribute('aria-pressed'), 'true')
    const pannedView = await viewport.getAttribute('style')
    await setEditorKey('F'); await settleViewport()
    assert.notEqual(await viewport.getAttribute('style'), pannedView, 'F really fits the panned canvas')
    const movable = await node(unassignedBus.id).boundingBox()
    assert.ok(movable)
    await page.mouse.move(movable.x + movable.width / 2, movable.y + movable.height / 2)
    await page.mouse.down(); await page.mouse.move(movable.x + movable.width / 2 + 30, movable.y + movable.height / 2 + 20, { steps: 8 }); await page.mouse.up()
    await frames()
    const moved = await save(); assert.deepEqual(moved.topology, current.topology)
    assert.notDeepEqual(moved.diagram_layout.node_positions[`bus:${unassignedBus.id}`], current.diagram_layout.node_positions[`bus:${unassignedBus.id}`])
    current = moved
    await setEditorKey('C'); assert.equal(await mode('connect').getAttribute('aria-pressed'), 'true')
    await setEditorKey('V')
    pass('default keyboard modes permit real panning, F fit and SVG-node dragging without changing electrical data')

    for (const [key, collection] of [['G', 'grid_forming_converters'], ['E', 'infinite_buses']]) {
      await setEditorKey(key)
      const point = await blankPoint([0.5, 0.15])
      await page.mouse.click(point.x, point.y); await frames()
      const placed = await save()
      assertAddOnly(current, placed, { buses: 1, [collection]: 1 })
      const equipment = added(current, placed, collection)[0]
      assert.ok(added(current, placed, 'buses').some(bus => bus.id === equipment.bus_id))
      assert.notEqual(equipment.bus_id, unassignedBus.id)
      await page.getByTestId('network-undo').click(); assertCase(await save(), current)
    }
    pass('G and E perform actual source placement with a new paired bus; one undo restores each prior case')

    await setEditorKey('B')
    await editor.focus()
    await page.keyboard.down('Space')
    const spacePoint = await blankPoint([0.5, 0.15])
    await page.mouse.click(spacePoint.x, spacePoint.y)
    await page.keyboard.up('Space'); await frames()
    assert.match(await page.getByTestId('network-editor-hint').textContent(), /正在放置母线/,
      'Space release preserves the pending bus instead of inserting it or cancelling it')
    assertCase(await save(), current)
    await setEditorKey('Escape')
    await palette('bus').focus(); await page.keyboard.press('Space'); await frames()
    assert.match(await page.getByTestId('network-editor-hint').textContent(), /正在放置母线/,
      'Space on a focused palette button performs its native activation')
    assertCase(await save(), current)
    const spacePlaced = await blankPoint([0.5, 0.85])
    await page.mouse.click(spacePlaced.x, spacePlaced.y); await frames()
    assertAddOnly(current, await save(), { buses: 1 })
    await page.getByTestId('network-undo').click(); assertCase(await save(), current)
    pass('held Space prevents pending placement and retains it on release; focused palette-button Space remains native activation')

    before = current
    await setEditorKey('B')
    const keyboardPoint = await blankPoint([0.5, 0.15])
    await page.mouse.click(keyboardPoint.x, keyboardPoint.y); await frames()
    current = await save(); assertAddOnly(before, current, { buses: 1 })
    const deletable = added(before, current, 'buses')[0]
    await node(deletable.id).click(); await page.keyboard.press('Delete'); await frames()
    assertCase(await save(), before)
    await page.getByTestId('network-undo').click(); assertCase(await save(), current)
    await setEditorKey('B'); await setEditorKey('Escape')
    const cancelledPoint = await blankPoint([0.5, 0.85])
    await page.mouse.click(cancelledPoint.x, cancelledPoint.y); assertCase(await save(), current)
    pass('B placement, Delete of an independent bus, undo and Escape cancellation are actual keyboard actions')

    await page.getByTestId('network-fit').click(); await settleViewport()
    await node(targetBus.id).click()
    const historyBeforeCancel = { undo: await page.getByTestId('network-undo').isEnabled(), redo: await page.getByTestId('network-redo').isEnabled() }
    await Promise.all([
      page.waitForEvent('dialog').then(async dialog => { assert.equal(dialog.type(), 'confirm'); await dialog.dismiss() }),
      page.keyboard.press('Delete'),
    ])
    assertCase(await save(), current)
    assert.equal(await page.getByTestId('network-undo').isEnabled(), historyBeforeCancel.undo)
    assert.equal(await page.getByTestId('network-redo').isEnabled(), historyBeforeCancel.redo)
    await node(targetBus.id).click()
    await Promise.all([
      page.waitForEvent('dialog').then(async dialog => { assert.equal(dialog.type(), 'confirm'); await dialog.accept() }),
      page.keyboard.press('Delete'),
    ])
    const cascade = await save()
    const expectedCascade = structuredClone(current)
    expectedCascade.topology.buses = expectedCascade.topology.buses.filter(bus => bus.id !== targetBus.id)
    expectedCascade.topology.lines = expectedCascade.topology.lines.filter(line => line.from_bus_id !== targetBus.id && line.to_bus_id !== targetBus.id)
    expectedCascade.topology.grid_forming_converters = expectedCascade.topology.grid_forming_converters.filter(gfm => gfm.bus_id !== targetBus.id)
    expectedCascade.topology.infinite_buses = expectedCascade.topology.infinite_buses.filter(grid => grid.bus_id !== targetBus.id)
    expectedCascade.topology.loads = expectedCascade.topology.loads.filter(load => load.bus_id !== targetBus.id)
    delete expectedCascade.diagram_layout.node_positions[`bus:${targetBus.id}`]
    for (const [collection, kind] of [['grid_forming_converters', 'gfm'], ['infinite_buses', 'grid']]) {
      for (const source of current.topology[collection].filter(item => item.bus_id === targetBus.id)) {
        delete expectedCascade.diagram_layout.node_positions[`${kind}:${source.id}`]
      }
    }
    assertCase(cascade, expectedCascade)
    await assertAtomic(current, cascade)
    await page.getByTestId('network-undo').click(); assertCase(await save(), current)
    pass('Delete confirmation cancel preserves case/history; accepting cascades attached entities and remains one undo/redo transaction')

    await settings().click()
    for (const [name, key] of Object.entries(defaults)) assert.equal((await keyInput(name).inputValue()).toUpperCase(), key)
    await keyInput('select').fill('s')
    await page.getByTestId('network-shortcut-save').click()
    const stored = JSON.parse(await readStored())
    assert.equal(stored.schema_version, '1.0'); assert.deepEqual(stored.bindings, { ...defaults, select: 'S' })
    assertCase(await save(), current)
    await settings().click()
    await setEditorKey('H'); await setEditorKey('V')
    assert.equal(await mode('pan').getAttribute('aria-pressed'), 'true', 'The old select key must no longer act')
    await setEditorKey('S'); assert.equal(await mode('select').getAttribute('aria-pressed'), 'true')
    pass('single-letter shortcut changes are normalized, saved locally and affect real keyboard behavior only')

    const persistedCase = current
    await openEditor()
    await settings().click()
    assert.equal((await keyInput('select').inputValue()).toUpperCase(), 'S')
    await settings().click()
    await setEditorKey('H'); await setEditorKey('S')
    assert.equal(await mode('select').getAttribute('aria-pressed'), 'true')
    await importCase(persistedCase); current = await save(); assertCase(current, persistedCase)
    pass('actual page reload restores configured keys, and actual case import restores topology/layout independently')

    await settings().click()
    const storageBeforeConflict = await readStored()
    await keyInput('connect').fill('S'); await page.getByTestId('network-shortcut-save').click()
    await page.getByRole('alert').waitFor({ state: 'visible' })
    assert.equal(await readStored(), storageBeforeConflict)
    assertCase(await save(), current)
    await keyInput('connect').fill('C')
    await settings().click()
    pass('conflicting shortcut save is refused with an alert; mapping, storage and case remain unchanged')

    await node(unassignedBus.id).click()
    const originalName = current.topology.buses.find(bus => bus.id === unassignedBus.id).name
    const nativeInput = properties.getByRole('textbox', { name: '名称', exact: true })
    await nativeInput.fill(''); await nativeInput.focus(); await page.keyboard.press('B')
    assert.equal(await nativeInput.inputValue(), 'B')
    await nativeInput.fill(originalName)
    const nativePoint = await blankPoint([0.5, 0.85])
    await page.mouse.click(nativePoint.x, nativePoint.y); assertCase(await save(), current)
    pass('real typing in the element-name input is native text entry, not graph placement or graph keyboard handling')

    await settings().click()
    await page.getByTestId('network-shortcut-reset').click()
    for (const [name, key] of Object.entries(defaults)) assert.equal((await keyInput(name).inputValue()).toUpperCase(), key)
    await settings().click()
    await setEditorKey('H'); await setEditorKey('S')
    assert.equal(await mode('pan').getAttribute('aria-pressed'), 'true')
    await setEditorKey('V'); assert.equal(await mode('select').getAttribute('aria-pressed'), 'true')
    assertCase(await save(), current)
    pass('reset restores default keyboard behavior without altering the saved engineering case')

    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 })
      await editor.scrollIntoViewIfNeeded()
      await page.getByTestId('network-fit').click(); await settleViewport()
      const dimensions = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth }))
      assert.ok(dimensions.document <= dimensions.viewport + 1, `Page overflow at ${width}px`)
      assertCase(await save(), current)
      if (reviewDir) {
        mkdirSync(reviewDir, { recursive: true })
        await editor.screenshot({ path: resolve(reviewDir, `network-palette-ui-${width}.png`) })
      }
      pass(`${width}px: palette and editable case remain usable without horizontal page overflow`)
    }
    assert.deepEqual(pageErrors, []); assert.deepEqual(apiCalls, [])
    console.log(`GFM_NETWORK_PALETTE_UI_OK (${scenarios} UI-only action scenarios)`)
  })(), new Promise((_, reject) => { timeout = setTimeout(() => reject(new Error('Palette test exceeded its 60-second total limit.')), 60000) })])
} catch (error) {
  if (reviewDir && page && !page.isClosed()) {
    mkdirSync(reviewDir, { recursive: true })
    await page.screenshot({ path: resolve(reviewDir, 'network-palette-ui-failure.png'), fullPage: true }).catch(() => {})
  }
  throw error
} finally {
  clearTimeout(timeout)
  await context?.close().catch(() => {}); await browser?.close().catch(() => {})
  server.closeAllConnections()
  await new Promise(resolveClose => server.close(resolveClose))
}
