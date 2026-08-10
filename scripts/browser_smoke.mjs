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

  await page.getByRole('button', { name: '独立模型' }).click()
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

  await page.screenshot({ path: screenshotPath, fullPage: true })
  console.log('BROWSER_E2E_SMOKE_OK')
  console.log(`Screenshot: ${screenshotPath}`)
} finally {
  await browser.close()
}
