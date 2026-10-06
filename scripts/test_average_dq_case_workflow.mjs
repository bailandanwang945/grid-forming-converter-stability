// UI-only regression: all API results below are synthetic ownership fixtures.
// This checks case/comparison workflows, not backend computation or numerical validity.
// Build apps/web first. Uses an installed Chrome/Edge; never installs dependencies.
import assert from 'node:assert/strict'
import { existsSync, mkdirSync, readFileSync } from 'node:fs'
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

const clone = value => JSON.parse(JSON.stringify(value))
const topology = {
  schema_version: '1.0', id: 'average-dq-ui-workflow-fixture',
  name: 'Synthetic UI-only SMIB case',
  base_values: { apparent_power_va: 1e6, voltage_v: 690, frequency_hz: 50 },
  frame_convention_id: 'power-invariant-park-q-lag-v1', reference_bus_id: 'bus-grid',
  buses: [
    { kind: 'bus', id: 'bus-gfm', name: 'GFM bus', nominal_voltage_v: 690 },
    { kind: 'bus', id: 'bus-grid', name: 'Infinite bus', nominal_voltage_v: 690 },
  ],
  lines: [{ kind: 'ac_line', id: 'line-grid', name: 'External RL line',
    from_bus_id: 'bus-gfm', to_bus_id: 'bus-grid', resistance_pu: 0.02,
    reactance_pu: 0.3, shunt_susceptance_pu: 0, thermal_limit_pu: null, in_service: true }],
  grid_forming_converters: [{ kind: 'grid_forming_converter', id: 'gfm-1',
    name: 'Synthetic VSM', bus_id: 'bus-gfm', rated_apparent_power_va: 1e6,
    control_mode: 'virtual_synchronous_machine', active_power_setpoint_pu: 0.5,
    reactive_power_setpoint_pu: 0.1, voltage_setpoint_pu: 1, virtual_inertia_s: 2,
    damping_coefficient_pu: 60, active_power_measurement_time_constant_s: 0.1,
    parameter_set_id: 'average-dq-default-v1' }],
  infinite_buses: [{ kind: 'infinite_bus', id: 'grid-1', name: 'Ideal grid',
    bus_id: 'bus-grid', voltage_magnitude_pu: 1, voltage_angle_deg: 0 }],
  loads: [],
}
const parameters = {
  schema_version: '1.0', id: 'average-dq-default-v1', converter_id: 'gfm-1',
  frame_convention_id: 'power-invariant-park-q-lag-v1',
  converter_side_resistance_pu: 0.01, converter_side_reactance_pu: 0.15,
  filter_capacitor_susceptance_pu: 0.05, grid_side_resistance_pu: 0.01,
  grid_side_reactance_pu: 0.1, modulation_time_constant_s: 0.001,
  reactive_power_measurement_time_constant_s: 0.02, reactive_power_voltage_droop_pu: 0.05,
  voltage_proportional_gain_pu: 0.3, voltage_integral_gain_per_s: 5,
  current_proportional_gain_pu: 0.3, current_integral_gain_per_s: 5,
  virtual_resistance_pu: 0, virtual_reactance_pu: 0,
  diagnostic_current_limit_pu: 2, diagnostic_internal_voltage_limit_pu: 1.5,
}
const completeInput = {
  topology, parameters, simulation_time_s: 0.6, time_step_s: 0.003,
  initial_angle_perturbation_rad: 0.0003, frequency_values_hz: [0, 0.25, 2, 60],
}
const completeCase = { schema_version: 'AverageDQCase/1.0', input: completeInput }
const legacyInput = {
  topology, parameters, simulation_time_s: 2, time_step_s: 0.002,
  initial_angle_perturbation_rad: 0.0001,
  frequency_values_hz: Array.from({ length: 31 }, (_, index) => 10 ** (-1 + index * 3 / 30)),
}

function syntheticResult(input, number) {
  const damping = input.topology.grid_forming_converters[0].damping_coefficient_pu
  const realHz = -damping / 100
  const frequency = 1 + damping / 100
  const pole = { real_per_s: realHz * 2 * Math.PI, imag_per_s: frequency * 2 * Math.PI,
    real_hz: realHz, imag_hz: frequency }
  const labels = Array.from({ length: 16 }, (_, index) => `synthetic_state_${index}`)
  const zero = labels.map(() => 0)
  const identity = [[{ real: 1, imag: 0 }, { real: 0, imag: 0 }],
    [{ real: 0, imag: 0 }, { real: 1, imag: 0 }]]
  return {
    run_id: `synthetic-ui-workflow-${number}`, status: 'completed', analysis_mode: 'synthetic-ui-only',
    input_topology: clone(input.topology), input_parameters: clone(input.parameters),
    operating_point: { state_labels: labels, state: zero, grid_voltage_global_pu: [1, 0],
      pcc_voltage_local_pu: [1, 0], pcc_voltage_global_pu: [1, 0], algebraic_residual: [0, 0],
      closed_rhs_residual_inf: 0, device_rhs_residual_inf: 0, active_power_balance_residual_pu: 0,
      converter_current_magnitude_pu: 0.5, grid_current_magnitude_pu: 0.5, internal_voltage_magnitude_pu: 1 },
    result: { stability: 'stable', stability_tolerance_per_s: 1e-7,
      closed_state_matrix: labels.map(() => labels.map(() => 0)),
      poles: [pole, { ...pole, imag_per_s: -pole.imag_per_s, imag_hz: -pole.imag_hz }],
      dominant_mode: { ...pole, oscillation_frequency_hz: frequency },
      port_interconnection_max_abs_error: 0,
      quasisteady_reduction_comparison: { synchronizing_stiffness_pu_per_rad: 1,
        reduced_state_matrix: [[0]], reduced_poles: [pole], full_dominant_pole: pole,
        reduced_dominant_pole: pole, matched_full_pole: pole,
        oscillation_frequency_relative_error: 0, real_part_relative_error: 0,
        decay_rate_relative_error: 0, matching_method: 'synthetic-ui-only',
        interpretation: 'Synthetic fixture; no model or numerical claim.' },
      port_admittance: { current_direction: 'synthetic-ui-only', voltage_frame: 'synthetic-ui-only',
        frequencies_hz: clone(input.frequency_values_hz),
        matrices: input.frequency_values_hz.map(() => clone(identity)) },
      time_response: { response_kind: 'synthetic-ui-only', time_s: [0, input.simulation_time_s],
        state_labels: labels, initial_state: zero, nonlinear_states: [zero, zero], linear_states: [zero, zero] },
    },
    model_scope: { claim_level: 'ui-only', statement: 'Synthetic UI test only; not scientific evidence.',
      retained_dynamics: [], excluded_dynamics: ['All numerical computation is mocked.'] },
    provenance: { source_kind: 'synthetic-ui-only' },
  }
}

const server = createServer((request, response) => {
  const path = resolve(dist, `.${decodeURIComponent(new URL(request.url, 'http://localhost').pathname)}`)
  if (path !== dist && !path.startsWith(dist + sep)) { response.writeHead(403).end(); return }
  const file = existsSync(path) && extname(path) ? path : resolve(dist, 'index.html')
  const type = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' }[extname(file)] ?? 'application/octet-stream'
  try { response.writeHead(200, { 'Content-Type': type }).end(readFileSync(file)) }
  catch { response.writeHead(404).end() }
})
let browser
let context
let page
let suiteTimer
const pageErrors = []
const unexpectedRequests = []
const layoutErrors = []
const pending = []
let requestCount = 0

async function within(operation, milliseconds, description) {
  let timer
  try {
    return await Promise.race([operation(), new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`Timed out: ${description}`)), milliseconds)
    })])
  } finally { clearTimeout(timer) }
}
async function scenario(name, operation) {
  await within(operation, 5000, name)
  console.log(`PASS ${name}`)
}
async function until(predicate, description) {
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    if (await predicate()) return
    await new Promise(resolveWait => setTimeout(resolveWait, 20))
  }
  throw new Error(`Timed out: ${description}`)
}
const run = () => page.getByRole('button', { name: '运行平均值 dq 分析', exact: true })
const report = () => page.getByRole('button', { name: '分析报告', exact: true })
const damping = () => page.getByRole('spinbutton', { name: 'VSM 阻尼系数', exact: true })
const comparison = () => page.getByTestId('average-dq-comparison')
const saveBaseline = () => page.getByTestId('average-dq-save-baseline')
const exportComparison = () => page.getByTestId('average-dq-comparison-export')

async function uploadCase(value) {
  const input = page.getByTestId('average-dq-case-import')
  await input.setInputFiles([])
  await input.setInputFiles({ name: 'synthetic-case.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(value)) })
}
async function importCase(value, noticePattern = /导入/) {
  await uploadCase(value)
  await until(async () => noticePattern.test(await page.getByTestId('average-dq-case-notice').innerText()), 'case import notice')
}
async function rejectCase(value, expectedField) {
  // Success/migration notices and errors are separate UI surfaces. Require the
  // failure prefix plus this fixture's field, so an old notice cannot satisfy it.
  await uploadCase(value)
  const error = page.locator('main.average-dq-workbench aside.controls p.error')
  await error.waitFor({ state: 'visible' })
  await until(async () => {
    const message = await error.innerText()
    return message.startsWith('导入失败：') && expectedField.test(message)
  }, 'specific case import error')
}
async function downloadJson(button) {
  const downloadPromise = page.waitForEvent('download', { timeout: 5000 })
  await button.click()
  const download = await downloadPromise
  assert.equal(await download.failure(), null)
  const stream = await download.createReadStream()
  assert.ok(stream, 'The download must have readable content.')
  const chunks = []
  for await (const chunk of stream) chunks.push(chunk)
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}
const saveCase = () => downloadJson(page.getByTestId('average-dq-case-save'))
async function takeRequest() {
  await until(() => pending.length > 0, 'pending synthetic analysis request')
  return pending.shift()
}
async function release(request) {
  const result = syntheticResult(request.input, request.number)
  await request.route.fulfill({ json: result })
  await until(() => run().isEnabled(), 'analysis request finished')
  return result
}
async function analyze(expectedInput) {
  await run().click()
  const request = await takeRequest()
  assert.deepEqual(request.input, expectedInput, 'The API request must exactly match all imported inputs.')
  const result = await release(request)
  assert.equal(await report().isEnabled(), true)
  return { input: clone(request.input), result }
}
async function noCurrentResult() {
  assert.equal(await report().isDisabled(), true)
  assert.equal(await saveBaseline().isDisabled(), true)
  assert.equal(await comparison().count(), 0, 'No current result means no candidate comparison.')
  if (await exportComparison().count()) assert.equal(await exportComparison().isDisabled(), true)
}
async function checkComparison(expectedBaseline, expectedCandidate) {
  await comparison().waitFor()
  const baselineText = await page.getByTestId('average-dq-comparison-baseline').innerText()
  const candidateText = await page.getByTestId('average-dq-comparison-candidate').innerText()
  assert.ok(baselineText.includes(expectedBaseline.result.run_id))
  assert.ok(candidateText.includes(expectedCandidate.result.run_id))
  const metric = (label, column) => comparison().getByRole('row').filter({ hasText: label }).locator('td').nth(column)
  for (const [column, snapshot] of [[1, expectedBaseline], [2, expectedCandidate]]) {
    const result = snapshot.result.result
    const stability = { stable: '稳定', marginal: '临界', unstable: '失稳' }[result.stability]
    assert.equal(await metric('闭环特征值参考判断', column).innerText(), stability,
      'Each comparison column must display its own stability classification.')
    assert.equal(await metric('最右特征值实部 / Hz', column).innerText(),
      Math.max(...result.poles.map(pole => pole.real_hz)).toFixed(6),
      'Each comparison column must display its own rightmost pole.')
    assert.equal(await metric('主导振荡频率 / Hz', column).innerText(),
      result.dominant_mode.oscillation_frequency_hz.toFixed(6),
      'Each comparison column must display its own dominant frequency.')
  }
  const exported = await downloadJson(exportComparison())
  assert.equal(exported.schema_version, 'AverageDQComparison/1.0')
  assert.deepEqual(exported.baseline, expectedBaseline, 'Baseline must remain a complete independent snapshot.')
  assert.deepEqual(exported.candidate, expectedCandidate, 'Candidate must use its own completed input and result.')
  assert.ok(Array.isArray(exported.changes))
  return exported
}
async function captureComparisonReview() {
  const directory = resolve(root, 'output/ui-review')
  mkdirSync(directory, { recursive: true })
  await page.evaluate(() => {
    const label = document.createElement('div')
    label.id = 'synthetic-ui-review-label'
    label.textContent = '合成 UI 响应｜仅检查软件流程，不是数值验证'
    Object.assign(label.style, { position: 'fixed', left: '8px', bottom: '8px',
      maxWidth: 'calc(100vw - 16px)', boxSizing: 'border-box', padding: '6px 10px',
      fontFamily: 'Arial, Microsoft YaHei, sans-serif', fontSize: '12px', lineHeight: '1.4',
      color: '#5f4300', background: '#fff2d4', border: '1px solid #d8b267',
      zIndex: '9999', pointerEvents: 'none' })
    document.body.appendChild(label)
  })
  try {
    for (const [name, viewport] of [['desktop', { width: 1440, height: 1000 }],
      ['mobile', { width: 390, height: 844 }]]) {
      await page.setViewportSize(viewport)
      await comparison().scrollIntoViewIfNeeded()
      const width = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth,
        viewport: window.innerWidth }))
      const path = resolve(directory, `2026-10-06-average-dq-comparison-${name}.png`)
      await page.screenshot({ path, fullPage: false })
      assert.ok(existsSync(path), 'The UI review image must exist at its final output path.')
      if (width.scroll > width.viewport) {
        layoutErrors.push(`${name}: document ${width.scroll}px > viewport ${width.viewport}px`)
        const diagnostic = await comparison().evaluate(section => {
          const elements = [section, section.parentElement, ...section.querySelectorAll('.table-scroll, table')]
          const describe = element => {
            const style = getComputedStyle(element)
            const bounds = element.getBoundingClientRect()
            return { tag: element.tagName, class: element.className, width: Math.round(bounds.width),
              right: Math.round(bounds.right), clientWidth: element.clientWidth, scrollWidth: element.scrollWidth,
              display: style.display, minWidth: style.minWidth, overflowX: style.overflowX,
              inlineStyle: element.getAttribute('style') }
          }
          const outside = [...document.querySelectorAll('body *')].filter(element => {
            const bounds = element.getBoundingClientRect()
            return bounds.width > 0 && bounds.right > window.innerWidth
          }).slice(0, 5).map(describe)
          return { comparison: elements.filter(Boolean).map(describe), outside }
        })
        console.log(`UI_LAYOUT_DIAGNOSTIC ${JSON.stringify(diagnostic)}`)
      }
      console.log(`UI_REVIEW ${name} ${width.scroll}/${width.viewport}px ${path} (synthetic responses only)`)
    }
  } finally {
    await page.evaluate(() => document.getElementById('synthetic-ui-review-label')?.remove())
    await page.setViewportSize({ width: 1440, height: 1000 })
  }
}

async function testWorkflow() {
  await new Promise(resolveListen => server.listen(0, '127.0.0.1', resolveListen))
  browser = await chromium.launch({ headless: true, executablePath, timeout: 5000 })
  context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } })
  page = await context.newPage()
  page.setDefaultTimeout(5000)
  page.on('pageerror', error => pageErrors.push(error.message))
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/average-dq/presets') {
      await route.fulfill({ json: { presets: [{ topology, parameters }] } }); return
    }
    if (path === '/api/average-dq/analyze') {
      const number = ++requestCount
      pending.push({ route, input: route.request().postDataJSON(), number }); return
    }
    unexpectedRequests.push(`${route.request().method()} ${path}`)
    await route.fulfill({ status: 404, json: { detail: 'Unexpected API call in UI-only workflow test' } })
  })
  await page.goto(`http://127.0.0.1:${server.address().port}`, { timeout: 5000 })
  await page.getByRole('button', { name: /设备与控制/ }).click()
  await damping().waitFor()
  let baseline
  let saved

  await scenario('complete non-default case import preserves every API input', async () => {
    await importCase(completeCase)
    await analyze(completeInput)
    assert.equal(requestCount, 1)
  })
  await scenario('case JSON download and re-import round-trip all input fields', async () => {
    saved = await saveCase()
    assert.deepEqual(saved, completeCase)
    await damping().fill('67')
    await noCurrentResult()
    await importCase(saved)
    await analyze(completeInput)
    assert.deepEqual(await saveCase(), saved)
  })
  await scenario('legacy case migrates with an explicit notice and fixed defaults', async () => {
    await importCase({ topology, parameters }, /旧版|迁移|默认/)
    await analyze(legacyInput)
    assert.deepEqual(await saveCase(), { schema_version: 'AverageDQCase/1.0', input: legacyInput })
  })
  await scenario('missing required case field is rejected without overwriting inputs', async () => {
    await importCase(completeCase)
    const invalid = clone(completeCase)
    delete invalid.input.time_step_s
    await rejectCase(invalid, /time_step_s/)
    assert.deepEqual(await saveCase(), completeCase)
    await analyze(completeInput)
  })
  await scenario('unknown case schema is rejected without overwriting inputs', async () => {
    await rejectCase({ ...completeCase, schema_version: 'AverageDQCase/99.0' }, /schema_version/)
    assert.deepEqual(await saveCase(), completeCase)
    assert.equal(await report().isEnabled(), true, 'Rejected imports do not invalidate the current successful result.')
  })
  await scenario('baseline edit rerun and comparison export retain two complete snapshots', async () => {
    baseline = await analyze(completeInput)
    await saveBaseline().click()
    await damping().fill('80')
    await noCurrentResult()
    const changed = clone(completeInput)
    changed.topology.grid_forming_converters[0].damping_coefficient_pu = 80
    const candidate = await analyze(changed)
    const exported = await checkComparison(baseline, candidate)
    const difference = exported.changes.find(item => item.field === 'topology.grid_forming_converters.0.damping_coefficient_pu')
    assert.ok(difference, 'Damping must appear as an exact parameter difference.')
    assert.equal(difference.before, 60)
    assert.equal(difference.after, 80)
    assert.ok(difference.label)
    const table = await page.getByTestId('average-dq-comparison-changes').innerText()
    assert.ok(table.includes('60') && table.includes('80'))
    await captureComparisonReview()
  })
  await scenario('pending and obsolete results cannot become a new candidate', async () => {
    await damping().fill('81')
    await noCurrentResult()
    await run().click()
    const obsolete = await takeRequest()
    await noCurrentResult()
    await damping().fill('82')
    await release(obsolete)
    await noCurrentResult()
    const changed = clone(completeInput)
    changed.topology.grid_forming_converters[0].damping_coefficient_pu = 82
    const candidate = await analyze(changed)
    await checkComparison(baseline, candidate)
    assert.equal((await page.getByTestId('average-dq-comparison-candidate').innerText()).includes(`synthetic-ui-workflow-${obsolete.number}`), false)
  })
  await scenario('import during analysis invalidates the pre-import request', async () => {
    await run().click()
    const beforeImport = await takeRequest()
    const imported = clone(completeInput)
    imported.topology.grid_forming_converters[0].damping_coefficient_pu = 42
    imported.simulation_time_s = 0.9
    imported.time_step_s = 0.004
    imported.initial_angle_perturbation_rad = -0.0005
    imported.frequency_values_hz = [0.1, 0.5, 5, 50]
    await importCase({ schema_version: 'AverageDQCase/1.0', input: imported })
    await release(beforeImport)
    await noCurrentResult()
    assert.deepEqual((await saveCase()).input, imported)
    const candidate = await analyze(imported)
    await checkComparison(baseline, candidate)
  })
  await scenario('clear baseline removes the comparison without losing current result', async () => {
    await page.getByTestId('average-dq-clear-baseline').click()
    assert.equal(await comparison().count(), 0)
    if (await exportComparison().count()) assert.equal(await exportComparison().isDisabled(), true)
    assert.equal(await saveBaseline().isEnabled(), true)
    assert.equal(await report().isEnabled(), true)
  })
  await scenario('rejected import during analysis preserves the valid pending request', async () => {
    const expectedInput = (await saveCase()).input
    await run().click()
    const valid = await takeRequest()
    const invalid = clone(completeCase)
    delete invalid.input.parameters
    await rejectCase(invalid, /parameters/)
    await release(valid)
    assert.deepEqual(valid.input, expectedInput)
    assert.equal(await report().isEnabled(), true)
    assert.deepEqual((await saveCase()).input, expectedInput)
  })
  assert.deepEqual(pageErrors, [], 'The browser must not report unhandled application errors.')
  assert.deepEqual(unexpectedRequests, [], 'The test must not call an unmocked API.')
  assert.deepEqual(layoutErrors, [], 'UI review must not have document-level horizontal overflow; tables may scroll internally.')
  assert.equal(pending.length, 0)
  console.log('GFM_AVERAGE_DQ_CASE_WORKFLOW_OK (10 UI-only scenarios; synthetic API responses, not numerical evidence)')
}

try {
  const timeout = new Promise((_, reject) => {
    suiteTimer = setTimeout(() => reject(new Error('UI-only workflow exceeded the 55-second suite limit.')), 55000)
  })
  await Promise.race([testWorkflow(), timeout])
} finally {
  clearTimeout(suiteTimer)
  // Closing the context rejects any still-pending browser actions and releases
  // downloads. Cleanup itself is bounded so a failed fixture cannot linger.
  await within(async () => {
    if (context) await context.close()
    if (browser) await browser.close()
  }, 4000, 'browser cleanup').catch(error => console.error(error.message))
  server.closeAllConnections()
  await within(() => new Promise(resolveClose => server.close(resolveClose)), 1000, 'server cleanup')
}
