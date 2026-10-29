import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(
  'C:/Users/lenovo/AadiTech/Product/MultiTenant/Aadi-MultiTenant-Platform/frontend/package.json',
)
const { chromium } = require('playwright')

const here = dirname(fileURLToPath(import.meta.url))
const videoDir = join(here, 'video-tmp')
const envFile = readFileSync(
  'C:/Users/lenovo/AadiTech/Product/MultiTenant/Aadi-MultiTenant-Platform/frontend/e2e/.env',
  'utf8',
)
const tenantId = 'e02812a0-8717-4f5f-be19-57f263daef52'

function envValue(name) {
  const line = envFile.split(/\r?\n/).find((item) => item.startsWith(`${name}=`))
  if (!line) {
    throw new Error(`Missing ${name}`)
  }
  return line.slice(name.length + 1).trim()
}

const managerEmail = envValue('PLAYWRIGHT_RECORDING_USER_EMAIL')
const managerPassword = envValue('PLAYWRIGHT_RECORDING_USER_PASSWORD')

function log(step) {
  console.log(`STEP ${step}`)
}

rmSync(videoDir, { recursive: true, force: true })
mkdirSync(videoDir, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: videoDir, size: { width: 1280, height: 720 } },
})
const page = await context.newPage()
page.setDefaultTimeout(30000)

async function pause(ms = 500) {
  await page.waitForTimeout(ms)
}

async function metrics() {
  return page.evaluate(() => ({
    doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    body: document.body.scrollWidth - document.body.clientWidth,
    heading: document.querySelector('h1')?.textContent?.trim() || '',
  }))
}

const routes = [
  ['projects', `/tenants/${tenantId}/projects`],
  ['records', `/tenants/${tenantId}/records`],
  ['follow-ups', `/tenants/${tenantId}/follow-ups`],
  ['reminders', `/tenants/${tenantId}/reminders`],
  ['imports', `/tenants/${tenantId}/imports`],
  ['kpis', `/tenants/${tenantId}/kpis`],
  ['audit', `/tenants/${tenantId}/audit`],
]

try {
  log('sign-in')
  await page.goto('http://localhost:5174/')
  await page.getByLabel('Email').fill(managerEmail)
  await page.getByLabel('Password').fill(managerPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /1792111368748/ }).click()
  await page.getByText('CRM is available in this organization.').waitFor()

  for (const [name, path] of routes) {
    log(`desktop-${name}`)
    await page.goto(`http://localhost:5174${path}`)
    await page.locator('h1').waitFor()
    await pause()
    const reading = await metrics()
    console.log(`DESKTOP ${name} overflow_doc=${reading.doc} overflow_body=${reading.body}`)
  }

  log('narrow')
  await page.setViewportSize({ width: 390, height: 844 })
  for (const [name, path] of routes) {
    log(`narrow-${name}`)
    await page.goto(`http://localhost:5174${path}`)
    await page.locator('h1').waitFor()
    await pause(300)
    const reading = await metrics()
    console.log(`NARROW ${name} overflow_doc=${reading.doc} overflow_body=${reading.body}`)
  }

  log('escape')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/projects`)
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await pause()
  await page.keyboard.press('Escape')
  const expanded = await page.getByRole('button', { name: 'Open navigation' }).getAttribute('aria-expanded')
  console.log(`ESCAPE expanded=${expanded}`)
  if (expanded !== 'false') {
    throw new Error('Escape did not close navigation')
  }

  log('tablet')
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records`)
  await page.locator('h1').waitFor()
  await pause()
  const tablet = await metrics()
  console.log(`TABLET records overflow_doc=${tablet.doc} overflow_body=${tablet.body}`)
} finally {
  await context.close()
  await browser.close()
}
