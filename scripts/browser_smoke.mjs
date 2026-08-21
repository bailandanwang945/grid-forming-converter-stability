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
  await page.locator('.model-editor details').filter({ hasText: 'VSM 控制参数' }).locator('summary').click()
  await page.getByLabel('阻尼 D / pu').first().fill('0.05')
  await page.getByRole('button', { name: /验证拓扑并分析/ }).click()
  await page.locator('.metrics .metric').first().waitFor({ timeout: 30000 })
  if (await page.getByTestId('reduced-view-results').getAttribute('aria-selected') !== 'true') {
    throw new Error('Reduced-order analysis did not focus the result view after a successful run.')
  }
  const firstStatus = await page.locator('.metrics .metric').first().locator('strong').innerText()
  if (firstStatus !== '失稳') throw new Error(`Expected low-damping case to be unstable, got ${firstStatus}.`)

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: /保存案例/ }).click()
  const download = await downloadPromise
  const savedCasePath = await download.path()
  if (!download.suggestedFilename().endsWith('.gfm-case.json') || !savedCasePath) {
    throw new Error('Versioned case export failed.')
  }
  await page.getByTestId('reduced-view-editor').click()
  await page.locator('.model-editor details').filter({ hasText: '线路参数' }).locator('summary').click()
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

  await page.getByTestId('reduced-view-editor').click()
  await page.getByLabel('低频模型初始相角扰动').fill('2')
  if (await page.getByTestId('reduced-view-results').isEnabled()) {
    throw new Error('Reduced-order result remained available after changing a simulation input.')
  }
  await page.getByRole('button', { name: /验证拓扑并分析/ }).click()
  await page.locator('.metrics .metric').first().waitFor({ timeout: 30000 })
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

  const analysisTab = page.getByRole('tab', { name: '模型分析' })
  const studiesTab = page.getByRole('tab', { name: '研究验证' })
  if (await analysisTab.getAttribute('aria-selected') !== 'true') {
    throw new Error('Average-dq workbench does not open in the model-analysis view.')
  }
  if (await page.getByTestId('average-dq-ablation-fixed-scope').isVisible()) {
    throw new Error('Average-dq fixed studies compete with the default model-analysis view.')
  }
  await studiesTab.click()
  if (await studiesTab.getAttribute('aria-selected') !== 'true') {
    throw new Error('Average-dq research-validation view did not become active.')
  }
  if ((await page.getByTestId('study-status-hierarchy').innerText()) !== '未运行') {
    throw new Error('Average-dq hierarchy task did not start in the not-run state.')
  }
  await page.getByTestId('study-result-empty').waitFor({ timeout: 15000 })

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
  if ((await page.getByTestId('study-status-ablation').innerText()) !== '已完成') {
    throw new Error('Average-dq ablation task did not expose its completed state.')
  }
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

  if (await page.getByTestId('mathworks-external-evidence-results').count() !== 0) {
    throw new Error('MathWorks evidence was unexpectedly loaded before its task was run.')
  }
  await page.getByTestId('sienna-test08-audit-run').click()
  await page.getByTestId('sienna-test08-audit-results').waitFor({ timeout: 30000 })
  const siennaSummary = await page.getByTestId('sienna-test08-audit-summary').innerText()
  for (const evidence of ['状态数\n19', '平衡点残差\n5.40e-11', '特征值最大误差 / s⁻¹\n1.55e-4', '冻结谱基频\n60 Hz']) {
    if (!siennaSummary.includes(evidence)) {
      throw new Error(`Sienna Test 08 audit summary is missing ${evidence}: ${siennaSummary}`)
    }
  }
  const commonLclSummary = await page.getByTestId('sienna-team-common-lcl-summary').innerText()
  for (const evidence of ['共有 LCL 状态\n6', '状态矩阵最大差 / s⁻¹\n9.09e-13', '输入矩阵最大差 / s⁻¹\n9.09e-13', '1% Xg 错配反例 / s⁻¹\n18.663']) {
    if (!commonLclSummary.includes(evidence)) {
      throw new Error(`Sienna-team common LCL summary is missing ${evidence}: ${commonLclSummary}`)
    }
  }
  const innerControlSummary = await page.getByTestId('sienna-team-inner-control-summary').innerText()
  for (const evidence of ['双 PI 状态换元\n通过', '参数对齐后补偿残差\n0.003', '完整内环同构\n否', '未闭合结构项\nRfif']) {
    if (!innerControlSummary.includes(evidence)) {
      throw new Error(`Sienna-team inner-control summary is missing ${evidence}: ${innerControlSummary}`)
    }
  }
  const commonInnerLoopSummary = await page.getByTestId('sienna-team-common-inner-loop-summary').innerText()
  for (const evidence of ['共有内环状态\n10', '双路径方程门\n通过', '最大匹配谱位移 / s⁻¹\n8.599', '两路径固定输入分类\n失稳 / 失稳']) {
    if (!commonInnerLoopSummary.includes(evidence)) {
      throw new Error(`Sienna-team common inner-loop summary is missing ${evidence}: ${commonInnerLoopSummary}`)
    }
  }
  const activeDampingSummary = await page.getByTestId('sienna-team-active-damping-summary').innerText()
  for (const evidence of ['共有有源阻尼状态\n2', '关闭 Rfif 路径 α 变化 / s⁻¹\n4.877', '加入 Rfif 路径 α 变化 / s⁻¹\n4.678', '“仅缺有源阻尼”假设\n不支持']) {
    if (!activeDampingSummary.includes(evidence)) {
      throw new Error(`Sienna-team active-damping summary is missing ${evidence}: ${activeDampingSummary}`)
    }
  }
  const modalFingerprintSummary = await page.getByTestId('sienna-team-modal-fingerprint-summary').innerText()
  for (const evidence of ['10状态命名支路频率\n103.86 Hz', '网侧滤波电流参与度\n65.4%', '局部实部灵敏度首项\nX2（滤波器）', '电气—控制相互作用假设\n有界支持']) {
    if (!modalFingerprintSummary.includes(evidence)) {
      throw new Error(`Sienna-team modal-fingerprint summary is missing ${evidence}: ${modalFingerprintSummary}`)
    }
  }
  const modalFingerprintTable = await page.getByTestId('sienna-team-modal-fingerprint-table').innerText()
  for (const evidence of ['10状态 · 关闭 Rfif', '103.861', '65.4%', '14.8%', 'X2（网侧滤波电抗）', '32.384', '12状态 · 加入 Rfif', '100.151']) {
    if (!modalFingerprintTable.includes(evidence)) {
      throw new Error(`Sienna-team modal-fingerprint table is missing ${evidence}: ${modalFingerprintTable}`)
    }
  }
  const commonOuterSummary = await page.getByTestId('sienna-team-common-outer-loop-summary').innerText()
  for (const evidence of ['共有外环中间模型\n13 状态', '电容端测量谱横坐标 / s⁻¹\n195.145', 'PCC 测量谱横坐标 / s⁻¹\n200.013', '混用功率端口反例 / s⁻¹\n500.0']) {
    if (!commonOuterSummary.includes(evidence)) {
      throw new Error(`Sienna-team common outer-loop summary is missing ${evidence}: ${commonOuterSummary}`)
    }
  }
  const commonOuterTable = await page.getByTestId('sienna-team-common-outer-loop-table').innerText()
  for (const evidence of ['滤波电容端', '3.382', '111.762', 'PCC', '3.403', '111.541', '失稳']) {
    if (!commonOuterTable.includes(evidence)) {
      throw new Error(`Sienna-team common outer-loop table is missing ${evidence}: ${commonOuterTable}`)
    }
  }
  const activePowerDelaySummary = await page.getByTestId('sienna-team-active-power-delay-summary').innerText()
  for (const evidence of ['共同延迟模型\n14 状态', '两种端口扫描点\n10', '低频支路位移更显著\n有界支持', '混用功率端口反例 / s⁻¹\n500.0']) {
    if (!activePowerDelaySummary.includes(evidence)) {
      throw new Error(`Sienna-team active-power-delay summary is missing ${evidence}: ${activePowerDelaySummary}`)
    }
  }
  const activePowerDelayTable = await page.getByTestId('sienna-team-active-power-delay-table').innerText()
  for (const evidence of ['滤波电容端', '0.010', '-2.555', '3.366', '195.107', 'PCC', '0.200', '2.027', '1.759', '200.035']) {
    if (!activePowerDelayTable.includes(evidence)) {
      throw new Error(`Sienna-team active-power-delay table is missing ${evidence}: ${activePowerDelayTable}`)
    }
  }
  const activePowerDelayBoundary = await page.getByTestId('sienna-team-active-power-delay-boundary').innerText()
  for (const evidence of ['0.025～0.05 s 之间穿越虚轴', '宽频支路在扫描起点已经失稳', '不是整机 Hopf 稳定裕度', '没有比较调制、PLL 或外部网络动态']) {
    if (!activePowerDelayBoundary.includes(evidence)) {
      throw new Error(`Sienna-team active-power-delay boundary is missing ${evidence}.`)
    }
  }
  const commonPllSummary = await page.getByTestId('sienna-team-common-pll-summary').innerText()
  for (const evidence of ['共同 PLL 中间模型\n18 状态', '方程门\n四组通过', '关闭阻尼负对照\n通过', '测量位置效应结论\n模态待定']) {
    if (!commonPllSummary.includes(evidence)) {
      throw new Error(`Sienna-team common PLL summary is missing ${evidence}: ${commonPllSummary}`)
    }
  }
  const commonPllTable = await page.getByTestId('sienna-team-common-pll-table').innerText()
  for (const evidence of ['滤波电容端', '开启（kd=400）', '-4.899', '0.743', '已追踪', 'PCC', '-3.717', '0.000', '待定（实轴过渡）', '失稳']) {
    if (!commonPllTable.includes(evidence)) {
      throw new Error(`Sienna-team common PLL table is missing ${evidence}: ${commonPllTable}`)
    }
  }
  const commonPllBoundary = await page.getByTestId('sienna-team-common-pll-boundary').innerText()
  for (const evidence of ['测量位置与 VSM—PLL 阻尼开关分开', '构成负对照', '自适应加密追踪', '模态待定', '不以端点最近根替代连续模态身份', '不是整机稳定裕度']) {
    if (!commonPllBoundary.includes(evidence)) {
      throw new Error(`Sienna-team common PLL boundary is missing ${evidence}.`)
    }
  }
  const siennaBoundary = await page.getByTestId('sienna-test08-audit-boundary').innerText()
  for (const evidence of ['六状态 LCL 层', 'η=Kᵢξ', '原始完整内环仍未同构', 'Rfif 电阻压降前馈', '10状态中间算例', '两状态有源阻尼', '仅缺有源阻尼即可改变分类', '不受支持', '不是对有源阻尼一般作用的否定', '约 100 Hz 命名支路', 'X2 是 LCL 网侧滤波电抗', '不构成唯一机理', '功率测量位置不同', '13状态中间算例', '约 3.4 Hz 低频支路', '结构差异而非参数误差', '14状态中间算例', '低频支路在 Tm=0.025～0.05 s 之间过零', '不是整机稳定裕度', '18状态共同 PLL 算例', 'PCC 低频支路发生实轴过渡', '模态待定', '仍不能逐根比较16状态与19状态整机特征值', '没有运行 Julia 或 PSCAD', '论文稳定性充分条件']) {
    if (!siennaBoundary.includes(evidence)) {
      throw new Error(`Sienna Test 08 boundary is missing ${evidence}.`)
    }
  }
  const siennaDownloadPromise = page.waitForEvent('download')
  await page.getByTestId('sienna-test08-audit-export').click()
  const siennaDownload = await siennaDownloadPromise
  if (siennaDownload.suggestedFilename() !== 'sienna-psid-test08-v0.16.2-python-transcription-v1.json') {
    throw new Error('Sienna Test 08 audit JSON export failed.')
  }
  console.log('[browser] Independent Sienna source audit passed.')

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
  await page.getByTestId('mathworks-team-comparison-results').waitFor({ timeout: 15000 })
  const comparisonSummary = await page.getByTestId('mathworks-team-comparison-summary').innerText()
  for (const evidence of ['固定对齐点\n8', '分类一致\n7 / 8', '分类不一致\n1', '定量过渡位置\n未复现']) {
    if (!comparisonSummary.includes(evidence)) {
      throw new Error(`MathWorks-team comparison summary is missing ${evidence}: ${comparisonSummary}`)
    }
  }
  for (const point of ['2.5-0.6', '2.5-1.056', '2.5-2', '2.5-4', '5-0.6', '5-1.056', '5-2', '5-4']) {
    await page.getByTestId(`mathworks-team-row-${point}`).waitFor({ timeout: 15000 })
  }
  const comparisonBoundary = await page.getByTestId('mathworks-team-comparison-boundary').innerText()
  for (const evidence of ['七点分类一致', '定量过渡位置未复现', '并非同一种证据', '不命名为预测误差']) {
    if (!comparisonBoundary.includes(evidence)) {
      throw new Error(`MathWorks-team comparison boundary is missing ${evidence}.`)
    }
  }
  const externalDownloadPromise = page.waitForEvent('download')
  await page.getByTestId('mathworks-team-comparison-export').click()
  const externalDownload = await externalDownloadPromise
  if (externalDownload.suggestedFilename() !== 'mathworks-team-aligned-eight-point-comparison-v1.json') {
    throw new Error('MathWorks-team comparison JSON export failed.')
  }
  await page.getByTestId('average-dq-aligned-step-results').waitFor({ timeout: 15000 })
  const nonlinearStepSummary = await page.getByTestId('average-dq-aligned-step-summary').innerText()
  for (const evidence of ['固定对照点\n3', '双求解器一致\n3 / 3', '原分歧点 D=1.056\n8 秒内收敛', 'D=0.6\n越出诊断范围']) {
    if (!nonlinearStepSummary.includes(evidence)) {
      throw new Error(`Aligned nonlinear-step summary is missing ${evidence}: ${nonlinearStepSummary}`)
    }
  }
  for (const damping of ['0.6', '1.056', '2']) {
    await page.getByTestId(`average-dq-aligned-step-row-${damping}`).waitFor({ timeout: 15000 })
  }
  const nonlinearStepBoundary = await page.getByTestId('average-dq-aligned-step-boundary').innerText()
  for (const evidence of ['不能归结为该团队模型', '不等同于物理失稳', '不是可信 EMT', '论文稳定性充分条件']) {
    if (!nonlinearStepBoundary.includes(evidence)) {
      throw new Error(`Aligned nonlinear-step boundary is missing ${evidence}.`)
    }
  }
  const nonlinearStepDownloadPromise = page.waitForEvent('download')
  await page.getByTestId('average-dq-aligned-step-export').click()
  const nonlinearStepDownload = await nonlinearStepDownloadPromise
  if (nonlinearStepDownload.suggestedFilename() !== 'average-dq-aligned-three-point-nonlinear-step-v1.json') {
    throw new Error('Aligned nonlinear-step JSON export failed.')
  }
  console.log('[browser] MathWorks evidence and aligned nonlinear step passed.')

  await analysisTab.click()
  await page.getByLabel('有功功率给定').fill('0.4')
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
  await page.locator('.parameter-sections details').filter({ hasText: '仿真设置' }).locator('summary').click()
  await page.getByLabel('初始相角扰动').fill('0.2')
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

  await studiesTab.click()
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

  const resultFocus = page.getByRole('navigation', { name: '研究结果切换' })
  if (!(await resultFocus.innerText()).includes('6 / 6 项已有结果')) {
    throw new Error(`Average-dq study completion summary is incomplete: ${await resultFocus.innerText()}`)
  }
  await page.getByTestId('study-select-sienna').click()
  if (!(await page.getByTestId('sienna-test08-audit-results').isVisible())
      || await page.getByTestId('study-result-hierarchy').isVisible()) {
    throw new Error('Average-dq study focus did not isolate the Sienna result without recomputation.')
  }
  await page.getByTestId('study-select-hierarchy').click()
  if (!(await page.getByTestId('study-result-hierarchy').isVisible())
      || await page.getByTestId('sienna-test08-audit-results').isVisible()) {
    throw new Error('Average-dq study focus did not restore the hierarchy result without recomputation.')
  }

  await page.screenshot({ path: screenshotPath, fullPage: true })
  console.log('BROWSER_E2E_SMOKE_OK')
  console.log(`Screenshot: ${screenshotPath}`)
} finally {
  await browser.close()
}
