// UI-only regression: synthetic responses test request/input ownership, not mathematics.
// Uses its own ephemeral loopback server and browser; no backend or network is required.
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { createServer } from 'node:http'
import { dirname, extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from '../apps/web/node_modules/playwright-core/index.mjs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const dist = resolve(root, 'apps/web/dist')
assert.ok(existsSync(resolve(dist, 'index.html')), 'Run the frontend build first.')
const executablePath = [process.env.GFM_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean).find(existsSync)
assert.ok(executablePath, 'Chrome or Edge is required; no browser is installed by this test.')

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
let browser
let context
let timeout
const pending = []
const reportInputs = []
const requests = []
const pageErrors = []
const unexpectedApi = []
const scope = 'Synthetic UI response only; not numerical or scientific evidence.'
const topology = {
  schema_version: '1.0', id: 'ui-test-only', name: 'UI ownership fixture',
  frame_convention_id: 'power-invariant-park-q-lag-v1',
  base_values: { apparent_power_va: 1000000, voltage_v: 400, frequency_hz: 50 },
  reference_bus_id: 'grid-bus',
  buses: ['bus-1', 'bus-2', 'grid-bus'].map(id => ({ id, name: id, nominal_voltage_v: 400 })),
  lines: [1, 2].map(index => ({ id: `line-${index}`, name: `Line ${index}`,
    from_bus_id: `bus-${index}`, to_bus_id: 'grid-bus', resistance_pu: 0.01,
    reactance_pu: 0.2, shunt_susceptance_pu: 0, in_service: true })),
  grid_forming_converters: [1, 2].map(index => ({ id: `gfm-${index}`, name: `VSM ${index}`,
    bus_id: `bus-${index}`, rated_apparent_power_va: 1000000,
    control_mode: 'virtual_synchronous_machine', active_power_setpoint_pu: 0,
    reactive_power_setpoint_pu: 0, voltage_setpoint_pu: 1,
    virtual_inertia_s: 2, damping_coefficient_pu: 60,
    active_power_measurement_time_constant_s: 0.1 })),
  infinite_buses: [{ id: 'grid', name: 'Grid', bus_id: 'grid-bus',
    voltage_magnitude_pu: 1, voltage_angle_deg: 0 }], loads: [],
}
const paths = {
  analysis: '/api/reduced-order/analyze', scan: '/api/reduced-order/scan',
  contingency: '/api/reduced-order/n-minus-one', dq: '/api/network/dq-admittance',
  report: '/api/reports/reduced-order',
}
function analysisResult(input) {
  return {
    run_id: 'synthetic-reduced-analysis', status: 'completed', input_topology: input.topology ?? topology,
    input_validation: { network_contract: 'UI-only', status: 'valid' },
    result: { stability: 'stable', stability_tolerance_per_s: 1e-8,
      synchronous_stiffness_matrix: [[1, 0], [0, 1]],
      poles: [{ real_per_s: -1, imag_per_s: 2, real_hz: -0.159, imag_hz: 0.318 }],
      dominant_mode: { real_per_s: -1, real_hz: -0.159, oscillation_frequency_hz: 0.318 },
      time_response: { state_labels: ['delta_rad:gfm-1'], time_s: [0, 1], states: [[0.001], [0]] } },
    model_scope: { statement: scope, assumptions: [scope] },
  }
}
function scanResult(input) {
  return { run_id: 'synthetic-reduced-scan', input_topology: input.topology,
    scan: { target_vsm_id: input.target_vsm_id, target_line_id: input.target_line_id,
      axes: { damping_values_pu: [60], reactance_values_pu: [0.2] }, point_count: 1,
      stability_counts: { stable: 1, marginal: 0, unstable: 0 },
      rows: [[{ damping_coefficient_pu: 60, line_reactance_pu: 0.2, stability: 'stable',
        dominant_real_per_s: -1, dominant_real_hz: -0.159, oscillation_frequency_hz: 0.318 }]] },
    model_scope: { line_reactance_interpretation: scope, statement: scope } }
}
function contingencyResult() {
  return { run_id: 'synthetic-contingency',
    study: { counts: { total: 2, analyzed: 0, islanding: 2, stability_changed: 0 }, cases: [] },
    model_scope: { statement: scope } }
}
function dqResult(input) {
  return { run_id: 'synthetic-network', network: {
    frequencies_hz: [0.1, 1], port_bus_order: input.topology.grid_forming_converters.map(item => item.bus_id),
    grounded_bus_ids: ['grid-bus'], eliminated_bus_ids: [],
    singular_values: { maximum: [2, 2], minimum: [1, 1] } },
    model_scope: { statement: scope } }
}
async function until(predicate, description) {
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolveWait => setTimeout(resolveWait, 25))
  }
  throw new Error(`Timed out: ${description}`)
}
async function take(path) {
  await until(() => pending.some(item => item.path === path), `pending ${path}`)
  return pending.splice(pending.findIndex(item => item.path === path), 1)[0]
}
async function release(request, fail = false) {
  const fixtures = { [paths.analysis]: analysisResult, [paths.scan]: scanResult,
    [paths.contingency]: contingencyResult, [paths.dq]: dqResult }
  await request.route.fulfill(fail
    ? { status: 422, json: { detail: `Synthetic failure: ${request.path}` } }
    : request.path === paths.report
      ? { contentType: 'text/html', body: `<p>${scope}</p>` }
      : { json: fixtures[request.path](request.input) })
}
let scenarios = 0
function pass(description) { scenarios += 1; console.log(`PASS ${description}`) }

try {
  await Promise.race([(async () => {
  browser = await chromium.launch({ headless: true, executablePath, timeout: 15000 })
  context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
  await context.route('**/*', route => new URL(route.request().url()).origin === baseUrl
    ? route.continue() : route.abort('blockedbyclient'))
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/reduced-order/presets') {
      await route.fulfill({ json: { presets: ['stable', 'marginal', 'unstable'].map(kind => ({
        id: `reduced-smib-${kind}`, name: `UI ${kind}`, topology: structuredClone(topology),
      })) } }); return
    }
    if (Object.values(paths).includes(path)) {
      const item = { route, path, input: route.request().postDataJSON() }
      requests.push(item)
      pending.push(item)
      if (path === paths.report) reportInputs.push(item.input)
      return
    }
    unexpectedApi.push(path)
    await route.fulfill({ status: 404, json: { detail: 'Unexpected API call in UI-only test' } })
  })
  const page = await context.newPage()
  page.setDefaultTimeout(5000)
  page.on('pageerror', error => pageErrors.push(error.message))
  const run = () => page.getByRole('button', { name: '验证拓扑并分析', exact: true })
  const report = () => page.getByRole('button', { name: '生成分析报告', exact: true })
  const simulationTime = () => page.getByRole('spinbutton', { name: '低频模型仿真时长', exact: true })
  const damping = () => page.getByRole('spinbutton', { name: '阻尼 D / pu', exact: true }).first()
  const scanButton = () => page.getByRole('button', { name: '重算参数平面', exact: true })
  const scanSummary = () => page.locator('.scan-summary')
  const contingencyButton = () => page.getByTestId('reduced-n-minus-one-run')
  const contingencySummary = () => page.getByTestId('reduced-n-minus-one-summary')
  const dqButton = () => page.getByTestId('dq-network-run')
  const dqSummary = () => page.getByTestId('dq-network-summary')
  const editor = async () => {
    await page.getByTestId('reduced-view-editor').click()
    const details = page.locator('details').filter({ has: page.locator('summary').filter({ hasText: 'VSM 控制参数' }) })
    if (await details.getAttribute('open') === null) await details.locator('summary').click()
  }
  const enter = async () => {
    await page.getByRole('button', { name: /网络建模/ }).click()
    await run().waitFor()
    await editor()
  }
  const ready = async () => until(() => run().isEnabled(), 'analysis request finished')
  const noResult = async () => {
    assert.equal(await report().count(), 0)
    assert.equal(await page.getByTestId('reduced-view-results').isDisabled(), true)
  }
  const noError = async path => assert.equal(await page.getByText(`Synthetic failure: ${path}`, { exact: true }).count(), 0)
  const analyzeSuccessfully = async () => {
    await run().click()
    const request = await take(paths.analysis)
    await release(request)
    await ready()
    await report().waitFor()
    return request
  }
  const editModel = async () => {
    await editor()
    await damping().fill(String(Number(await damping().inputValue()) + 1))
  }
  const clickTwice = async button => button.evaluate(element => { element.click(); element.click() })
  const requestCount = path => requests.filter(item => item.path === path).length

  await page.goto(baseUrl)
  await enter()
  await run().click()
  const staleSuccess = await take(paths.analysis)
  await editModel()
  await release(staleSuccess)
  await ready()
  await noResult()
  pass('delayed analysis cannot overwrite edited topology')

  await run().click()
  const changedBack = await take(paths.analysis)
  const originalTime = await simulationTime().inputValue()
  await simulationTime().fill('21')
  await simulationTime().fill(originalTime)
  await release(changedBack)
  await ready()
  await noResult()
  pass('editing settings back does not revive an obsolete analysis')

  await run().click()
  const staleFailure = await take(paths.analysis)
  await simulationTime().fill('22')
  await release(staleFailure, true)
  await ready()
  await noResult()
  await noError(paths.analysis)
  pass('obsolete analysis failure is discarded')

  const analysisCount = requestCount(paths.analysis)
  await clickTwice(run())
  const completed = await take(paths.analysis)
  await release(completed)
  await ready()
  assert.equal(requestCount(paths.analysis), analysisCount + 1)
  const popupPromise = page.waitForEvent('popup')
  await clickTwice(report())
  const popup = await popupPromise
  const reportRequest = await take(paths.report)
  assert.deepEqual(reportRequest.input, completed.input)
  assert.equal(reportInputs.length, 1)
  await release(reportRequest)
  await until(() => popup.url().startsWith('blob:'), 'snapshot report shown')
  await popup.close()
  pass('analysis/report duplicate clicks are locked; report uses completed input')

  await run().click()
  await noResult()
  const currentFailure = await take(paths.analysis)
  await release(currentFailure, true)
  await ready()
  assert.equal(await page.getByText(`Synthetic failure: ${paths.analysis}`, { exact: true }).count(), 1)
  await noResult()
  await analyzeSuccessfully()
  pass('current analysis failure clears prior results and permits retry')

  for (const fail of [false, true]) {
    const nextPopupPromise = page.waitForEvent('popup')
    await report().click()
    const stalePopup = await nextPopupPromise
    const staleReport = await take(paths.report)
    await simulationTime().fill(String(Number(await simulationTime().inputValue()) + 1))
    await release(staleReport, fail)
    await until(() => stalePopup.isClosed(), 'obsolete report popup closed')
    await noError(paths.report)
    await noResult()
    await analyzeSuccessfully()
    pass(`obsolete report ${fail ? 'failure' : 'success'} is discarded`)
  }

  const tasks = [
    { name: 'scan', path: paths.scan, button: scanButton, summary: scanSummary,
      prepare: async () => { if (await report().count() === 0) await analyzeSuccessfully(); await page.getByTestId('reduced-view-results').click() },
      change: async () => page.getByRole('spinbutton', { name: 'D 最大', exact: true }).fill('71') },
    { name: 'N-minus-one', path: paths.contingency, button: contingencyButton, summary: contingencySummary,
      prepare: editor, change: editModel },
    { name: 'dq compilation', path: paths.dq, button: dqButton, summary: dqSummary,
      prepare: editor, change: editModel },
  ]
  for (const task of tasks) {
    await task.prepare()
    const beforeCount = requestCount(task.path)
    await clickTwice(task.button())
    const valid = await take(task.path)
    await simulationTime().fill(String(Number(await simulationTime().inputValue()) + 1))
    await release(valid)
    if (task.path === paths.scan) await analyzeSuccessfully()
    await until(() => task.button().isEnabled(), `${task.name} finished`)
    assert.equal(await task.summary().count(), 1)
    assert.equal(requestCount(task.path), beforeCount + 1)
    pass(`${task.name}: duplicate lock and simulation-only independence`)

    await task.prepare()
    await task.button().click()
    assert.equal(await task.summary().count(), 0)
    const obsolete = await take(task.path)
    await task.change()
    await release(obsolete)
    await until(() => task.button().isEnabled(), `obsolete ${task.name} finished`)
    assert.equal(await task.summary().count(), 0)
    pass(`${task.name}: obsolete success cannot restore a result`)

    await task.prepare()
    await task.button().click()
    const obsoleteFailure = await take(task.path)
    await editModel()
    await release(obsoleteFailure, true)
    if (task.path === paths.scan) await analyzeSuccessfully()
    await until(() => task.button().isEnabled(), `obsolete ${task.name} failure finished`)
    assert.equal(await task.summary().count(), 0)
    await noError(task.path)
    pass(`${task.name}: obsolete failure is discarded`)

    await task.prepare()
    await task.button().click()
    const validAgain = await take(task.path)
    await release(validAgain)
    await until(() => task.button().isEnabled(), `${task.name} success`)
    assert.equal(await task.summary().count(), 1)
    await task.button().click()
    assert.equal(await task.summary().count(), 0)
    const currentTaskFailure = await take(task.path)
    await release(currentTaskFailure, true)
    await until(() => task.button().isEnabled(), `${task.name} current failure`)
    assert.equal(await page.getByText(`Synthetic failure: ${task.path}`, { exact: true }).count(), 1)
    await task.button().click()
    await release(await take(task.path))
    await until(() => task.button().isEnabled(), `${task.name} retry`)
    assert.equal(await task.summary().count(), 1)
    pass(`${task.name}: current failure clears a prior result and permits retry`)
  }

  await analyzeSuccessfully()
  for (const field of [
    ['spinbutton', 'D 最小', '0.1'], ['spinbutton', 'X 最大 / pu', '0.65'],
    ['spinbutton', '每轴点数', '3'], ['combobox', '目标 VSM', 'gfm-2'], ['combobox', '目标线路', 'line-2'],
  ]) {
    await scanButton().click()
    const pendingScan = await take(paths.scan)
    const control = page.getByRole(field[0], { name: field[1], exact: true })
    if (field[0] === 'combobox') await control.selectOption(field[2]); else await control.fill(field[2])
    await release(pendingScan)
    await until(() => scanButton().isEnabled(), 'scan setting request finished')
    assert.equal(await scanSummary().count(), 0)
    assert.equal(await report().count(), 1)
  }
  pass('scan axis/target edits invalidate only the scan')

  await scanButton().click()
  const layoutScan = await take(paths.scan)
  await editor()
  await run().click()
  const layoutAnalysis = await take(paths.analysis)
  await contingencyButton().click()
  const layoutContingency = await take(paths.contingency)
  await dqButton().click()
  const layoutDQ = await take(paths.dq)
  const node = page.locator('.react-flow__node[data-id="bus:bus-1"]')
  await node.scrollIntoViewIfNeeded()
  const beforePosition = await node.getAttribute('style')
  const box = await node.boundingBox()
  assert.ok(box, 'Graph node must be visible.')
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 + 65, box.y + box.height / 2 + 30, { steps: 8 })
  await page.mouse.up()
  await until(async () => await node.getAttribute('style') !== beforePosition, 'graph node position changes after dragging')
  assert.notEqual(await node.getAttribute('style'), beforePosition)
  for (const request of [layoutScan, layoutContingency, layoutDQ, layoutAnalysis]) await release(request)
  await ready()
  assert.equal(await report().count(), 1)
  for (const summary of [scanSummary, contingencySummary, dqSummary]) assert.equal(await summary().count(), 1)
  await editor()
  await page.getByTestId('network-undo').click()
  assert.equal(await node.getAttribute('style'), beforePosition)
  await page.getByTestId('network-redo').click()
  assert.notEqual(await node.getAttribute('style'), beforePosition)
  assert.equal(await report().count(), 1)
  for (const summary of [scanSummary, contingencySummary, dqSummary]) assert.equal(await summary().count(), 1)
  pass('layout dragging and layout-only undo/redo retain all numerical requests/results')

  await run().click()
  const beforePreset = await take(paths.analysis)
  await page.getByRole('combobox', { name: '解析校核预设', exact: true }).selectOption('reduced-smib-marginal')
  await release(beforePreset)
  await ready()
  await noResult()
  pass('preset changes invalidate a pending analysis')

  await run().click()
  const beforeImport = await take(paths.analysis)
  await page.locator('input[type="file"]').setInputFiles({ name: 'ui-case.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ schema_version: 'gfm-reduced-order-case/1.1', topology,
      diagram_layout: { schema_version: 'gfm-network-diagram-layout/1.0', node_positions: {} },
      simulation_settings: { simulation_time_s: 27, time_step_s: 0.03, initial_angle_perturbation_rad: 0.002 } })) })
  await until(() => simulationTime().inputValue().then(value => value === '27'), 'import applied')
  await release(beforeImport)
  await ready()
  await noResult()
  pass('case imports invalidate a pending analysis and restore settings')

  const upload = async value => page.locator('input[type="file"]').setInputFiles({ name: 'ui-import.json',
    mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(value)) })
  const invalidCases = [
    { description: 'missing topology arrays', value: { schema_version: 'gfm-reduced-order-case/1.1',
      topology: { buses: [], lines: [] }, simulation_settings: { simulation_time_s: 5 } } },
    ...[
      { simulation_time_s: 0 }, { time_step_s: '0.02' }, { initial_angle_perturbation_rad: 0.11 },
      { simulation_time_s: 300, time_step_s: 0.001 },
    ].map(settings => ({ description: `invalid settings ${JSON.stringify(settings)}`,
      value: { schema_version: 'gfm-reduced-order-case/1.1', topology, simulation_settings: settings } })),
  ]
  for (const invalid of invalidCases) {
    await analyzeSuccessfully()
    const beforeSettings = await simulationTime().inputValue()
    await upload(invalid.value)
    await until(() => page.locator('p.error').textContent().then(text => text.startsWith('案例文件无法读取：')), 'invalid import rejected')
    assert.equal(await simulationTime().inputValue(), beforeSettings)
    assert.equal(await report().count(), 1)
    await run().click()
    const unaffected = await take(paths.analysis)
    await upload(invalid.value)
    await until(() => page.locator('p.error').textContent().then(text => text.startsWith('案例文件无法读取：')), 'invalid import rejected during analysis')
    assert.equal(await simulationTime().inputValue(), beforeSettings)
    await release(unaffected)
    await ready()
    assert.equal(await report().count(), 1)
    pass(`${invalid.description}: atomic rejection preserves input, result and pending valid analysis`)
  }

  await page.evaluate(() => {
    const original = File.prototype.text
    window.__restoreFileText = () => { File.prototype.text = original }
    File.prototype.text = function () {
      return new Promise((resolveText, rejectText) => {
        original.call(this).then(text => { window.__releaseImport = () => resolveText(text) }, rejectText)
      })
    }
  })
  await upload({ schema_version: 'gfm-reduced-order-case/1.1', topology,
    simulation_settings: { simulation_time_s: 5, time_step_s: 0.02, initial_angle_perturbation_rad: 0.001 } })
  await until(() => page.evaluate(() => typeof window.__releaseImport === 'function'), 'delayed file read')
  await simulationTime().fill('29')
  await analyzeSuccessfully()
  await page.evaluate(() => { window.__releaseImport(); window.__restoreFileText() })
  await until(() => page.getByText('案例读取期间输入已修改，未覆盖当前编辑；请重新导入。', { exact: true }).count().then(count => count === 1), 'late import ignored')
  assert.equal(await simulationTime().inputValue(), '29')
  assert.equal(await report().count(), 1)
  pass('a delayed file read cannot overwrite newer edits or their completed analysis')

  for (const task of [{ name: 'analysis', path: paths.analysis, button: run, summary: report,
    prepare: async () => {} }, ...tasks]) {
    await task.prepare()
    await task.button().click()
    const afterUnmount = await take(task.path)
    await page.getByRole('button', { name: /任务总览/ }).click()
    await release(afterUnmount)
    await enter()
    await noResult()
    assert.equal(await task.summary().count(), 0)
    await noError(task.path)
    pass(`${task.name}: leaving the workspace cannot restore old state`)
  }
  assert.deepEqual(pageErrors, [])
  assert.deepEqual(unexpectedApi, [])
  assert.equal(pending.length, 0)
  console.log(`GFM_REDUCED_ORDER_INPUT_RESULT_CONSISTENCY_OK (${scenarios} UI-only scenarios)`)
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
