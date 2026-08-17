import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from '../apps/web/node_modules/playwright-core/index.mjs'

const candidates = [
  process.env.GFM_BROWSER_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
].filter(Boolean)
const executablePath = candidates.find(candidate => existsSync(candidate))
if (!executablePath) throw new Error('Chrome or Edge was not found for browser acceptance testing.')

const baseUrl = process.env.GFM_BASE_URL ?? 'http://127.0.0.1:5173'
const screenshotPath = resolve(process.env.GFM_SMOKE_OUTPUT ?? 'tmp/browser-smoke.png')
const browser = await chromium.launch({ headless: true, executablePath })
const page = await browser.newPage({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 1 })

try {
  await page.goto(baseUrl, { waitUntil: 'networkidle' })

  await page.locator('select').first().selectOption('fig8_D_0p05')
  await page.getByRole('button', { name: /运行稳定性分析/ }).click()
  await page.locator('.metrics .metric').first().waitFor({ timeout: 30000 })
  const fig8Text = await page.locator('body').innerText()
  for (const evidence of ['0.578', '1.2', '75 个未覆盖点']) {
    if (!fig8Text.includes(evidence)) throw new Error(`Fig. 8 page is missing ${evidence}.`)
  }

  await page.getByTestId('fig8-sensitivity-run').click()
  await page.getByTestId('fig8-sensitivity-summary').waitFor({ timeout: 30000 })
  const sensitivitySummary = await page.getByTestId('fig8-sensitivity-summary').innerText()
  for (const evidence of ['漏检未覆盖带', '最大分类变化 0 点']) {
    if (!sensitivitySummary.includes(evidence)) {
      throw new Error(`Fig. 8 sensitivity summary is missing ${evidence}.`)
    }
  }
  const sparseRow = await page.getByTestId('fig8-sensitivity-row-9').innerText()
  if (!sparseRow.includes('未检出') || !sparseRow.includes('75')) {
    throw new Error(`Nine-point counterexample is incomplete: ${sparseRow}`)
  }
  const sensitivityScope = await page.getByTestId('fig8-sensitivity-scope').innerText()
  for (const evidence of ['不生成新的频率响应', '不评价论文连续全频定理']) {
    if (!sensitivityScope.includes(evidence)) {
      throw new Error(`Fig. 8 sensitivity scope is missing ${evidence}.`)
    }
  }
  if (await page.getByTestId('fig8-sensitivity-export').isDisabled()) {
    throw new Error('Fig. 8 sensitivity JSON export is disabled after calculation.')
  }
  const sensitivityReportPromise = page.waitForEvent('popup')
  await page.getByTestId('fig8-sensitivity-report').click()
  const sensitivityReport = await sensitivityReportPromise
  await sensitivityReport.waitForFunction(
    () => document.body?.innerText.includes('漏检75个完整网格未覆盖样点'),
    null,
    { timeout: 30000 },
  )
  if (!(await sensitivityReport.locator('body').innerText()).includes('不评价论文连续全频定理')) {
    throw new Error('Fig. 8 sensitivity report is missing the continuous-frequency boundary.')
  }
  await sensitivityReport.close()
  console.log('[browser] Fig. 8 baseline and sampled sensitivity passed.')

  await page.getByRole('button', { name: '同域对照' }).click()
  await page.getByText('D–SCR 参数域分类图').waitFor({ timeout: 15000 })
  const comparisonText = await page.locator('body').innerText()
  for (const evidence of ['45 点', '96 点', '35 点', '不是系统失稳']) {
    if (!comparisonText.includes(evidence)) throw new Error(`Comparison page is missing ${evidence}.`)
  }
  const comparisonDownloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /导出参数域 CSV/ }).click()
  const comparisonDownload = await comparisonDownloadPromise
  if (!comparisonDownload.suggestedFilename().endsWith('.csv')) {
    throw new Error('Same-domain CSV export failed.')
  }
  const comparisonReportPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: /打开可打印报告/ }).click()
  const comparisonReport = await comparisonReportPromise
  await comparisonReport.waitForFunction(() => document.body?.innerText.includes('未覆盖不等于失稳'), null, { timeout: 30000 })
  await comparisonReport.close()
  await page.screenshot({ path: resolve('tmp/browser-smoke-comparison.png'), fullPage: true })
  console.log('[browser] Same-domain comparison passed.')

  await page.getByRole('button', { name: '低频模型' }).click()
  await page.getByText('可编辑网络与控制参数').waitFor({ timeout: 15000 })
  const referenceBus = page.getByLabel('参考母线')
  if (await referenceBus.inputValue() !== 'bus-grid' || await referenceBus.locator('option').count() !== 1) {
    throw new Error('Reference bus selector must contain only grounded infinite-bus nodes.')
  }
  if (!(await page.getByRole('button', { name: '至少保留一个无限大母线', exact: true }).isDisabled())) {
    throw new Error('The last infinite bus must not be removable from the reduced-order editor.')
  }
  await page.getByLabel('阻尼 D / pu').first().fill('0.05')
  await page.getByRole('button', { name: /验证拓扑并分析/ }).click()
  await page.locator('.metrics .metric').first().waitFor({ timeout: 30000 })
  const firstStatus = await page.locator('.metrics .metric').first().locator('strong').innerText()
  if (firstStatus !== '失稳') throw new Error(`Expected low-damping case to be unstable, got ${firstStatus}.`)

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /保存案例/ }).click()
  const download = await downloadPromise
  const savedCasePath = await download.path()
  if (!download.suggestedFilename().endsWith('.gfm-case.json') || !savedCasePath) {
    throw new Error('Versioned case export failed.')
  }
  await page.getByLabel('末端').first().selectOption('bus-gfm')
  await page.getByRole('button', { name: /验证拓扑并分析/ }).click()
  await page.locator('.error').waitFor({ timeout: 15000 })
  if (!(await page.locator('.error').innerText()).includes('首、末端节点不能相同')) {
    throw new Error('Invalid self-loop topology did not return an understandable validation error.')
  }
  await page.locator('select').first().selectOption('reduced-smib-stable')
  await page.waitForTimeout(150)
  await page.locator('input.hidden-input').setInputFiles(savedCasePath)
  const dampingInput = page.getByLabel('阻尼 D / pu').first()
  let restoredDamping = Number(await dampingInput.inputValue())
  for (let attempt = 0; attempt < 30 && restoredDamping !== 0.05; attempt += 1) {
    await page.waitForTimeout(100)
    restoredDamping = Number(await dampingInput.inputValue())
  }
  if (restoredDamping !== 0.05) {
    throw new Error(`Case import did not restore damping; got ${restoredDamping}.`)
  }
  await page.getByRole('button', { name: /验证拓扑并分析/ }).click()
  await page.locator('.metrics .metric').first().waitFor({ timeout: 30000 })
  if (await page.locator('.metrics .metric').first().locator('strong').innerText() !== '失稳') {
    throw new Error('Reloaded case did not reproduce its stability classification.')
  }

  await page.getByRole('button', { name: '重算参数平面' }).click()
  await page.locator('.scan-summary').waitFor({ timeout: 30000 })
  const scanText = await page.locator('.scan-summary').innerText()
  if (!scanText.includes('总点数 441') || !scanText.includes('稳定') || !scanText.includes('失稳')) {
    throw new Error(`D-X scan summary is incomplete: ${scanText}`)
  }

  const reportPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: /生成打印式报告/ }).click()
  const reportPage = await reportPromise
  await reportPage.waitForFunction(() => document.body?.innerText.includes('不是完整 dq'), null, { timeout: 30000 })
  const reportText = await reportPage.locator('body').innerText()
  if (!reportText.includes('0.05')) throw new Error('Report did not retain the custom damping parameter.')
  await reportPage.close()
  console.log('[browser] Reduced-order workflow passed.')

  await page.getByRole('button', { name: '平均值 dq' }).click()
  await page.getByText('16 状态平均值 dq 模型').waitFor({ timeout: 15000 })

  await page.setViewportSize({ width: 1078, height: 997 })
  await page.waitForTimeout(200)
  const responsiveLayout = await page.evaluate(() => {
    const controls = document.querySelector('.controls')?.getBoundingClientRect()
    const workspace = document.querySelector('.workspace')?.getBoundingClientRect()
    const parameterGrid = document.querySelector('.controls .parameter-grid')?.getBoundingClientRect()
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      controlsLeft: controls?.left ?? Number.NaN,
      controlsRight: controls?.right ?? Number.NaN,
      workspaceLeft: workspace?.left ?? Number.NaN,
      workspaceTop: workspace?.top ?? Number.NaN,
      controlsTop: controls?.top ?? Number.NaN,
      parameterGridRight: parameterGrid?.right ?? Number.NaN,
    }
  })
  if (responsiveLayout.documentWidth > responsiveLayout.viewportWidth + 1) {
    throw new Error(`Average-dq page has horizontal overflow at 1078 px: ${JSON.stringify(responsiveLayout)}`)
  }
  if (responsiveLayout.parameterGridRight > responsiveLayout.controlsRight + 1) {
    throw new Error(`Average-dq parameter grid escapes its panel: ${JSON.stringify(responsiveLayout)}`)
  }
  if (responsiveLayout.workspaceLeft < responsiveLayout.controlsRight + 20) {
    throw new Error(`Average-dq columns overlap or lose their intended gutter at 1078 px: ${JSON.stringify(responsiveLayout)}`)
  }
  if (Math.abs(responsiveLayout.workspaceTop - responsiveLayout.controlsTop) > 1) {
    throw new Error(`Average-dq columns are not top-aligned at 1078 px: ${JSON.stringify(responsiveLayout)}`)
  }
  await page.screenshot({ path: resolve('tmp/browser-smoke-average-dq-responsive.png'), fullPage: true })
  await page.setViewportSize({ width: 1600, height: 1100 })

  const ablationScope = page.getByTestId('average-dq-ablation-fixed-scope')
  await ablationScope.waitFor({ timeout: 15000 })
  const ablationScopeText = await ablationScope.innerText()
  for (const evidence of ['D=60', 'X=0.1 p.u.', '19 点']) {
    if (!ablationScopeText.includes(evidence)) {
      throw new Error(`Average-dq fixed ablation scope is missing ${evidence}.`)
    }
  }

  await page.getByTestId('average-dq-ablation-run').click()
  await page.getByTestId('average-dq-ablation-results').waitFor({ timeout: 45000 })
  const ablationSummaryText = await page.getByTestId('average-dq-ablation-summary').innerText()
  if (!/固定消融点数\s+19/.test(ablationSummaryText)
      || !/整体稳定 \/ 失稳\s+5 \/ 14/.test(ablationSummaryText)) {
    throw new Error(`Average-dq ablation summary is incomplete: ${ablationSummaryText}`)
  }
  await page.getByTestId('average-dq-ablation-row-baseline').waitFor({ timeout: 15000 })
  await page.getByTestId('average-dq-ablation-row-voltage_pi__2').waitFor({ timeout: 15000 })
  const trackingBoundaryText = await page.getByTestId('average-dq-ablation-tracking-boundary').innerText()
  for (const evidence of ['不是全局指派唯一性证明', '当前固定状态', '不证明唯一因果']) {
    if (!trackingBoundaryText.includes(evidence)) {
      throw new Error(`Average-dq ablation tracking boundary is missing ${evidence}.`)
    }
  }

  const ablationExport = page.getByTestId('average-dq-ablation-export')
  if (await ablationExport.isDisabled()) {
    throw new Error('Average-dq ablation JSON export is still disabled after calculation.')
  }

  await page.getByTestId('average-dq-boundary-run').click()
  await page.getByTestId('average-dq-boundary-results').waitFor({ timeout: 45000 })
  const boundarySummaryText = await page.getByTestId('average-dq-boundary-summary').innerText()
  if (!/冻结单因素路径\s+4/.test(boundarySummaryText)
      || !/附加模态 \/ 整体边界收敛\s+4 \/ 4/.test(boundarySummaryText)
      || !/两类边界一致\s+4 \/ 4/.test(boundarySummaryText)) {
    throw new Error(`Average-dq boundary summary is incomplete: ${boundarySummaryText}`)
  }
  for (const factor of ['voltage_pi', 'current_pi', 'converter_side_reactance', 'grid_side_reactance']) {
    await page.getByTestId(`average-dq-boundary-row-${factor}`).waitFor({ timeout: 15000 })
  }
  const boundaryInterpretation = await page.getByTestId('average-dq-boundary-interpretation').innerText()
  for (const evidence of ['不证明唯一因果', '论文定理边界', '硬件稳定性确认']) {
    if (!boundaryInterpretation.includes(evidence)) {
      throw new Error(`Average-dq boundary interpretation is missing ${evidence}.`)
    }
  }
  if (await page.getByTestId('average-dq-boundary-export').isDisabled()) {
    throw new Error('Average-dq boundary JSON export is still disabled after calculation.')
  }
  console.log('[browser] Average-dq ablation and boundary workflow passed.')

  await page.getByTestId('average-dq-port-identification-run').click()
  await page.getByTestId('average-dq-port-identification-results').waitFor({ timeout: 45000 })
  const portIdentificationSummary = await page.getByTestId('average-dq-port-identification-summary').innerText()
  for (const evidence of ['三频点判定\n全部通过', '最大幅值误差\n0.0171%', '最大相位误差\n0.0231°']) {
    if (!portIdentificationSummary.includes(evidence)) {
      throw new Error(`Average-dq port-identification summary is missing ${evidence}: ${portIdentificationSummary}`)
    }
  }
  for (const frequency of ['0.2', '2', '20']) {
    await page.getByTestId(`average-dq-port-identification-row-${frequency}`).waitFor({ timeout: 15000 })
  }
  const portBoundary = await page.getByTestId('average-dq-port-identification-boundary').innerText()
  for (const evidence of ['不确认真实硬件', '开端口矩阵并非渐近稳定', '不评价论文稳定性充分条件']) {
    if (!portBoundary.includes(evidence)) {
      throw new Error(`Average-dq port-identification boundary is missing ${evidence}.`)
    }
  }
  const portDownloadPromise = page.waitForEvent('download')
  await page.getByTestId('average-dq-port-identification-export').click()
  const portDownload = await portDownloadPromise
  if (!portDownload.suggestedFilename().endsWith('.json')) {
    throw new Error('Average-dq port-identification JSON export failed.')
  }
  const portReportPromise = page.waitForEvent('popup')
  await page.getByTestId('average-dq-port-identification-report').click()
  const portReport = await portReportPromise
  await portReport.waitForFunction(
    () => document.body?.innerText.includes('平均值 dq 三频点端口正弦辨识报告'),
    null,
    { timeout: 45000 },
  )
  const portReportText = await portReport.locator('body').innerText()
  for (const evidence of ['Y=I·V⁻¹', '不评价论文稳定性充分条件', '未完成硬件、硬件在环或可信 EMT 确认']) {
    if (!portReportText.includes(evidence)) {
      throw new Error(`Average-dq port-identification report is missing ${evidence}.`)
    }
  }
  await portReport.close()
  console.log('[browser] Average-dq port-identification workflow passed.')

  await page.getByTestId('mathworks-external-evidence-load').click()
  await page.getByTestId('mathworks-external-evidence-results').waitFor({ timeout: 15000 })
  const externalSummary = await page.getByTestId('mathworks-external-evidence-summary').innerText()
  for (const evidence of ['Stable / Stable / Unstable', '6 / 8', '[1.30675, 1.32150]', '[1.3215, 1.3510] · 目标未达成']) {
    if (!externalSummary.includes(evidence)) {
      throw new Error(`MathWorks external-evidence summary is missing ${evidence}: ${externalSummary}`)
    }
  }
  const externalBoundary = await page.getByTestId('mathworks-external-evidence-boundary').innerText()
  for (const evidence of ['供应商分类与项目跟踪门分列', '不把区间称为临界阻尼', '不评价论文稳定性充分条件']) {
    if (!externalBoundary.includes(evidence)) {
      throw new Error(`MathWorks external-evidence boundary is missing ${evidence}.`)
    }
  }
  const externalDownloadPromise = page.waitForEvent('download')
  await page.getByTestId('mathworks-external-evidence-export').click()
  const externalDownload = await externalDownloadPromise
  if (externalDownload.suggestedFilename() !== 'mathworks-gfm-external-evidence-v1.json') {
    throw new Error('MathWorks external-evidence JSON export failed.')
  }
  console.log('[browser] MathWorks frozen external-evidence workflow passed.')

  await page.getByLabel('P* / p.u.').fill('0.4')
  await page.getByRole('button', { name: /运行平均值 dq 分析/ }).click()
  await page.getByText('端口—线路重组误差').waitFor({ timeout: 30000 })
  const averageText = await page.locator('body').innerText()
  for (const evidence of ['参考稳定', '有功平衡残差', '硬件参数拟合', '未进行']) {
    if (!averageText.includes(evidence)) throw new Error(`Average-dq page is missing ${evidence}.`)
  }
  const averageDownloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /结果 JSON/ }).click()
  const averageDownload = await averageDownloadPromise
  if (!averageDownload.suggestedFilename().endsWith('.json')) {
    throw new Error('Average-dq JSON export failed.')
  }
  await page.getByLabel('初始相角 / mrad').fill('0.2')
  if (await page.getByRole('button', { name: /结果 JSON/ }).isEnabled()) {
    throw new Error('Average-dq result was not invalidated after changing the time-domain input.')
  }
  if (await page.getByRole('button', { name: /分析报告/ }).isEnabled()) {
    throw new Error('Average-dq report remained enabled for stale on-screen results.')
  }
  await page.getByRole('button', { name: /运行平均值 dq 分析/ }).click()
  await page.getByText('端口—线路重组误差').waitFor({ timeout: 30000 })
  const averageReportPromise = page.waitForEvent('popup')
  await page.getByRole('button', { name: /分析报告/ }).click()
  const averageReport = await averageReportPromise
  await averageReport.waitForFunction(() => document.body?.innerText.includes('不宣称完成工程模型确认'), null, { timeout: 30000 })
  const averageReportText = await averageReport.locator('body').innerText()
  if (!averageReportText.includes('0.4')) throw new Error('Average-dq report did not retain the edited active-power setpoint.')
  await averageReport.close()

  await page.getByRole('button', { name: /运行42点扫描/ }).click()
  await page.getByText('16状态—三状态 D–X 层级对照').waitFor({ timeout: 30000 })
  const hierarchyText = await page.locator('body').innerText()
  for (const evidence of ['扫描点数\n42', '两层分类不一致\n3', '不是论文小增益—小相位定理的反例']) {
    if (!hierarchyText.includes(evidence)) throw new Error(`Average-dq hierarchy scan is missing ${evidence}.`)
  }
  const hierarchyDownloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /导出层级扫描 JSON/ }).click()
  const hierarchyDownload = await hierarchyDownloadPromise
  if (!hierarchyDownload.suggestedFilename().endsWith('.json')) {
    throw new Error('Average-dq hierarchy JSON export failed.')
  }

  await page.screenshot({ path: screenshotPath, fullPage: true })
  console.log('BROWSER_E2E_SMOKE_OK')
  console.log(`Screenshot: ${screenshotPath}`)
} finally {
  await browser.close()
}
