// UI-only regression: synthetic API responses verify input/result ownership.
// No backend, model integration, MATLAB, or network access is required.
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
  const path = resolve(dist, `.${decodeURIComponent(new URL(request.url, 'http://localhost').pathname)}`)
  if (path !== dist && !path.startsWith(dist + sep)) { response.writeHead(403).end(); return }
  const file = existsSync(path) && extname(path) ? path : resolve(dist, 'index.html')
  const type = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' }[extname(file)] ?? 'application/octet-stream'
  try { response.writeHead(200, { 'Content-Type': type }).end(readFileSync(file)) }
  catch { response.writeHead(404).end() }
})
await new Promise(resolveListen => server.listen(0, '127.0.0.1', resolveListen))
const baseUrl = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ headless: true, executablePath })
const context = await browser.newContext()
const page = await context.newPage()
page.setDefaultTimeout(5000)
const pageErrors = []
page.on('pageerror', error => pageErrors.push(error.message))
const pending = []
const reportInputs = []
let requestCount = 0
const topology = {
  id: 'ui-test-only', base_values: { frequency_hz: 50 },
  grid_forming_converters: [{ active_power_setpoint_pu: 0.5, reactive_power_setpoint_pu: 0.1,
    voltage_setpoint_pu: 1, damping_coefficient_pu: 60 }],
  lines: [{ resistance_pu: 0.02, reactance_pu: 0.3 }],
}
const parameters = { converter_side_reactance_pu: 0.15, filter_capacitor_susceptance_pu: 0.05,
  grid_side_reactance_pu: 0.1, reactive_power_voltage_droop_pu: 0.05 }

function analysisResult(input) {
  return {
    run_id: 'synthetic-ui-response', status: 'completed', input_topology: input.topology,
    input_parameters: input.parameters,
    operating_point: { state: [0], algebraic_residual: [0], closed_rhs_residual_inf: 0,
      grid_current_magnitude_pu: 0.5, internal_voltage_magnitude_pu: 1, active_power_balance_residual_pu: 0 },
    result: { stability: 'stable', poles: [{ real_hz: -1, imag_hz: 2 }],
      dominant_mode: { real_hz: -1, oscillation_frequency_hz: 2 }, port_interconnection_max_abs_error: 0,
      time_response: { time_s: [0, 1], nonlinear_states: [[0], [0]], linear_states: [[0], [0]] },
      port_admittance: { frequencies_hz: [1], matrices: [[[{ real: 1, imag: 0 }]]] },
      quasisteady_reduction_comparison: { oscillation_frequency_relative_error: 0,
        decay_rate_relative_error: 0, synchronizing_stiffness_pu_per_rad: 1, interpretation: 'Synthetic UI test only' } },
    model_scope: { statement: 'Synthetic UI test only; not scientific evidence.' },
  }
}
function scanResult(input) {
  return { run_id: 'synthetic-ui-scan', input_topology: input.topology, input_parameters: input.parameters,
    result: { point_count: 1, counts: { agreement: 1, disagreement: 0, invalid: 0 },
      axes: { damping_values_pu: [60], reactance_values_pu: [0.3] },
      rows: [[{ valid: true, stability_agreement: true, full_stability: 'stable' }]] },
    model_scope: { interpretation: 'UI test only', statement: 'Not a 42-point numerical experiment.' } }
}
await context.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname
  if (path === '/api/average-dq/presets') {
    await route.fulfill({ json: { presets: [{ topology, parameters }] } }); return
  }
  if (path === '/api/reports/average-dq') {
    reportInputs.push(route.request().postDataJSON())
    await route.fulfill({ contentType: 'text/html', body: '<p>Input snapshot report</p>' }); return
  }
  if (path === '/api/average-dq/analyze' || path === '/api/average-dq/scan') {
    requestCount += 1
    pending.push({ route, input: route.request().postDataJSON(), path }); return
  }
  await route.fulfill({ status: 404, json: { detail: 'Unexpected API call in UI-only test' } })
})
async function until(predicate, description) {
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolveWait => setTimeout(resolveWait, 25))
  }
  throw new Error(`Timed out: ${description}`)
}
async function take() {
  await until(() => pending.length > 0, 'pending API request')
  return pending.shift()
}
async function release(request, fail = false) {
  await request.route.fulfill(fail
    ? { status: 422, json: { detail: 'Synthetic request failure' } }
    : { json: request.path.endsWith('/scan') ? scanResult(request.input) : analysisResult(request.input) })
}
const run = () => page.getByRole('button', { name: '运行平均值 dq 分析', exact: true })
const report = () => page.getByRole('button', { name: '分析报告', exact: true })
const damping = () => page.getByRole('spinbutton', { name: 'VSM 阻尼系数', exact: true })
async function enter() {
  await page.getByRole('button', { name: /设备与控制/ }).click()
  await damping().waitFor()
}
async function ready() { await until(() => run().isEnabled(), 'analysis request finished') }
async function noResult() {
  assert.equal(await report().isDisabled(), true)
  assert.equal(await page.getByText('当前结果可追溯', { exact: true }).count(), 0)
}
try {
  await page.goto(baseUrl)
  await enter()
  await run().click()
  const staleSuccess = await take()
  await damping().fill('61')
  await release(staleSuccess)
  await ready()
  await noResult()
  console.log('PASS delayed success cannot overwrite edited parameters')

  await run().click()
  const changedBack = await take()
  await damping().fill('62')
  await damping().fill('61')
  await release(changedBack)
  await ready()
  await noResult()
  console.log('PASS editing back does not revive an obsolete request')

  await run().click()
  const staleFailure = await take()
  await damping().fill('63')
  await release(staleFailure, true)
  await ready()
  assert.equal(await page.getByText('Synthetic request failure', { exact: true }).count(), 0)
  await noResult()
  console.log('PASS obsolete errors are discarded')

  const previousCount = requestCount
  await run().evaluate(button => { button.click(); button.click() })
  const success = await take()
  await release(success)
  await ready()
  assert.equal(requestCount, previousCount + 1)
  assert.equal(await report().isEnabled(), true)
  const popupPromise = page.waitForEvent('popup')
  await report().click()
  const popup = await popupPromise
  await until(() => reportInputs.length === 1, 'report input received')
  assert.deepEqual(reportInputs[0], success.input)
  await popup.close()
  await damping().fill('64')
  await noResult()
  console.log('PASS duplicate clicks are locked; reports use completed input')

  await run().click()
  const currentFailure = await take()
  await release(currentFailure, true)
  await ready()
  assert.equal(await page.getByText('Synthetic request failure', { exact: true }).count(), 1)
  await noResult()
  await run().click()
  const retry = await take()
  await release(retry)
  await ready()
  assert.equal(await report().isEnabled(), true)
  console.log('PASS current failure clears results and permits retry')

  await page.getByRole('tab', { name: '研究验证', exact: true }).click()
  await page.getByRole('button', { name: '运行42点扫描', exact: true }).click()
  const staleScan = await take()
  await page.getByRole('tab', { name: '模型分析', exact: true }).click()
  await damping().fill('65')
  await release(staleScan)
  await until(() => page.getByTestId('study-status-hierarchy').innerText().then(text => text === '未运行'), 'stale scan discarded')
  assert.equal(await page.getByTestId('study-result-hierarchy').count(), 0)
  console.log('PASS editable model revisions invalidate pending hierarchy scan')

  await page.getByRole('tab', { name: '研究验证', exact: true }).click()
  await page.getByRole('button', { name: '运行42点扫描', exact: true }).click()
  const staleScanFailure = await take()
  await page.getByRole('tab', { name: '模型分析', exact: true }).click()
  await damping().fill('66')
  await release(staleScanFailure, true)
  await until(() => page.getByTestId('study-status-hierarchy').innerText().then(text => text === '未运行'), 'obsolete scan failure discarded')
  assert.equal(await page.getByText('Synthetic request failure', { exact: true }).count(), 0)
  console.log('PASS obsolete hierarchy scan failures are discarded')

  await page.getByRole('tab', { name: '研究验证', exact: true }).click()
  const previousScanCount = requestCount
  await page.getByRole('button', { name: '运行42点扫描', exact: true }).evaluate(button => { button.click(); button.click() })
  const validScan = await take()
  await release(validScan)
  await until(() => page.getByTestId('study-status-hierarchy').innerText().then(text => text === '已完成'), 'valid scan accepted')
  assert.equal(requestCount, previousScanCount + 1)
  await page.getByRole('tab', { name: '模型分析', exact: true }).click()
  await page.locator('summary').filter({ hasText: '仿真设置' }).click()
  await page.getByRole('spinbutton', { name: '仿真时长', exact: true }).fill('3')
  assert.equal(await page.getByTestId('study-status-hierarchy').innerText(), '已完成')
  console.log('PASS simulation-only edits retain an independent hierarchy scan')

  await run().click()
  const afterUnmount = await take()
  await page.getByRole('button', { name: /任务总览/ }).click()
  await release(afterUnmount)
  await enter()
  await noResult()
  assert.deepEqual(pageErrors, [])
  console.log('PASS leaving the workspace does not restore an earlier result')
  console.log('GFM_AVERAGE_DQ_INPUT_RESULT_CONSISTENCY_OK (9 UI-only scenarios)')
} finally {
  await context.close()
  await browser.close()
  await new Promise(resolveClose => server.close(resolveClose))
}
