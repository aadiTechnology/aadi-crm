import { createRequire } from 'node:module'
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
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

function envValue(name) {
  const line = envFile.split(/\r?\n/).find((item) => item.startsWith(`${name}=`))
  if (!line) {
    throw new Error(`Missing ${name}`)
  }
  return line.slice(name.length + 1).trim()
}

const managerEmail = envValue('PLAYWRIGHT_RECORDING_USER_EMAIL')
const managerPassword = envValue('PLAYWRIGHT_RECORDING_USER_PASSWORD')
const memberEmail = envValue('PLAYWRIGHT_MEMBER_EMAIL')
const memberPassword = envValue('PLAYWRIGHT_MEMBER_PASSWORD')
const tenantId = 'e02812a0-8717-4f5f-be19-57f263daef52'
const code = `IMP${String(Date.now()).slice(-6)}`
const projectName = `Import gate ${code}`

function log(step) {
  console.log(`STEP ${step}`)
}

rmSync(videoDir, { recursive: true, force: true })
mkdirSync(videoDir, { recursive: true })
const csvPath = join(videoDir, 'leads.csv')
const badPath = join(videoDir, 'notes.txt')
writeFileSync(
  csvPath,
  [
    'School name,Email,Notes',
    '=Existing lane,Demo.Import@example.com,kept aside',
    ',not-an-email,bad row',
    '=Fresh lane,fresh.import@example.com,new row',
    '',
  ].join('\n'),
)
writeFileSync(badPath, 'this is not a workbook')

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: videoDir, size: { width: 1280, height: 720 } },
  acceptDownloads: true,
})
const page = await context.newPage()
page.setDefaultTimeout(25000)

async function pause(ms = 800) {
  await page.waitForTimeout(ms)
}

async function show(locator) {
  await locator.scrollIntoViewIfNeeded()
  await pause(400)
}

try {
  log('sign-in')
  await page.goto('http://localhost:5174/')
  await page.getByLabel('Email').fill(managerEmail)
  await page.getByLabel('Password').fill(managerPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /1792111368748/ }).click()
  await page.getByRole('link', { name: 'Projects', exact: true }).click()
  log('create-project')
  await page.getByRole('link', { name: 'New project' }).click()
  await page.getByLabel('Project code').fill(code)
  await page.getByLabel('Project name').fill(projectName)
  await pause()
  await page.getByRole('button', { name: 'Create project' }).click()
  await page.getByRole('heading', { name: projectName }).waitFor()
  log('create-form')
  await page.getByRole('link', { name: 'Forms', exact: true }).click()
  await page.getByRole('link', { name: projectName }).click()
  await page.getByRole('link', { name: 'New form' }).click()
  await page.getByLabel('Form name').fill('Import capture')
  await page.getByLabel('Description').fill('Import demo form')
  await page.getByRole('button', { name: 'Create form' }).click()
  await page.getByRole('heading', { name: 'Import capture' }).waitFor()
  await page.getByLabel('Field label').fill('School name')
  await page.getByLabel('Field identifier').fill('school_name')
  await page.getByLabel('Section').fill('Contact')
  await page.getByRole('checkbox', { name: 'Required' }).check()
  await page.getByRole('button', { name: 'Add field' }).click()
  await page.getByText('school_name').waitFor()
  await page.getByLabel('Field type').selectOption('email')
  await page.getByLabel('Field label').fill('Email')
  await page.getByLabel('Field identifier').fill('email')
  await page.getByLabel('Section').fill('Contact')
  await page.getByRole('button', { name: 'Add field' }).click()
  await page.getByRole('button', { name: 'Edit Email' }).waitFor()
  await page.getByRole('button', { name: 'Publish version' }).click()
  await pause()
  await page.getByRole('button', { name: 'Confirm publish' }).click()
  await page.getByText('Render version 1').waitFor()
  log('seed-record')
  await page.getByRole('link', { name: 'Records', exact: true }).click()
  await page.getByRole('heading', { name: 'Records', exact: true }).waitFor()
  await page.getByRole('link', { name: projectName }).click()
  await page.getByRole('heading', { name: projectName }).waitFor()
  await page.getByRole('link', { name: 'New record' }).click()
  await page.getByRole('heading', { name: 'New record' }).waitFor()
  console.log(`EDITOR ${page.url()}`)
  await page.getByLabel('Form').waitFor()
  await page.getByLabel('Form').selectOption({ label: 'Import capture · version 1' })
  await page.getByLabel(/School name/).waitFor()
  await page.getByLabel(/School name/).fill('Existing lane')
  await page.getByLabel(/^Email/).fill('demo.import@example.com')
  await pause()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.locator('#record-detail-heading').waitFor()
  const seeded = (await page.locator('#record-detail-heading').innerText()).trim()
  console.log(`SEEDED ${seeded}`)
  log('reject-file')
  await page.getByRole('link', { name: 'Import', exact: true }).click()
  if (await page.getByText('Loading import').count()) {
    console.log('LOADING_SEEN')
  }
  await page.getByRole('link', { name: projectName }).click()
  await page.getByLabel('Published form').waitFor()
  await page.getByLabel('CSV or XLSX file').setInputFiles(badPath)
  await page.getByRole('button', { name: 'Upload file' }).click()
  await page.getByRole('alert').waitFor()
  await show(page.getByRole('alert'))
  console.log(`REJECTED ${(await page.getByRole('alert').innerText()).replace(/\s+/g, ' ')}`)
  log('upload-map-preview')
  await page.getByLabel('CSV or XLSX file').setInputFiles(csvPath)
  await page.getByRole('button', { name: 'Upload file' }).click()
  await page.getByLabel('Map School name').waitFor()
  await page.getByLabel('Map School name').selectOption('school_name')
  await page.getByLabel('Map Email').selectOption('email')
  await page.getByLabel('Map Notes').selectOption('')
  await pause()
  await page.getByRole('button', { name: 'Save mapping' }).click()
  await page.getByText('Unmapped columns kept on this import: Notes.').waitFor()
  await show(page.getByText('Unmapped columns kept on this import: Notes.'))
  await page.getByRole('button', { name: 'Preview import' }).click()
  await page.getByText(/Dry-run only/).waitFor()
  await show(page.getByText(/Dry-run only/))
  await page.getByText(/Possible match on Email/).waitFor()
  await page.getByText('School name is required.').waitFor()
  log('commit')
  await page.getByLabel('Decision for row 2').selectOption('skip')
  await pause()
  await page.getByRole('button', { name: 'Import records' }).click()
  await page.getByText(/Partially completed\. Accepted 1, rejected 1, skipped 1/).waitFor()
  await show(page.getByText(/Partially completed/))
  const [errorDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download error report' }).click(),
  ])
  const errorText = readFileSync(await errorDownload.path(), 'utf8')
  console.log(`ERROR_REPORT ${errorText.replace(/\s+/g, ' ').slice(0, 400)}`)
  if (errorText.toLowerCase().includes('password') || errorText.includes(managerPassword)) {
    throw new Error('The error report included a secret.')
  }
  log('repeat')
  await page.getByRole('button', { name: 'Repeat this import' }).click()
  await page.getByText(/Accepted 1, rejected 1, skipped 1/).waitFor()
  await pause()
  log('export')
  await page.getByRole('link', { name: 'Records', exact: true }).click()
  await page.getByRole('link', { name: projectName }).click()
  await page.getByRole('heading', { name: /Records \(2\)/ }).waitFor()
  await page.getByLabel('Search records').fill('=Fresh')
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('heading', { name: 'Records (1)' }).waitFor()
  const [exportDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Export CSV' }).click(),
  ])
  await page.getByText('Exported 1 data rows. The list reports 1 matching records.').waitFor()
  const exported = readFileSync(await exportDownload.path(), 'utf8')
  console.log(`EXPORT_MATCH ${exported.includes("'=Fresh lane")}`)
  console.log(`EXPORT_OTHER ${exported.includes('Existing lane')}`)
  await show(page.getByText('Exported 1 data rows. The list reports 1 matching records.'))
  log('narrow')
  await page.setViewportSize({ width: 390, height: 720 })
  await pause()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
  console.log(`NARROW_OVERFLOW ${overflow}`)
  await page.setViewportSize({ width: 1280, height: 720 })
  log('unauthorized')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('button', { name: 'Sign in' }).waitFor()
  await page.getByLabel('Email').fill(memberEmail)
  await page.getByLabel('Password').fill(memberPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  const opened = page.getByText('Import is not available for this sign-in.')
  const chooser = page.getByRole('link', { name: /1792111368748/ })
  await Promise.race([opened.waitFor(), chooser.waitFor()])
  if ((await chooser.count()) > 0) {
    await chooser.click()
  }
  await opened.waitFor()
  await show(page.getByText('Import is not available for this sign-in.'))
  await page.goto(`http://localhost:5174/tenants/${tenantId}/imports`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  if (await page.getByText('=Fresh lane').count()) {
    throw new Error('The unauthorized page showed imported data.')
  }
  if (await page.getByText('demo.import@example.com').count()) {
    throw new Error('The unauthorized page showed the seeded email.')
  }
  await pause(1000)
  log('done')
  console.log(`PROJECT ${code} ${projectName}`)
  console.log(`SEEDED_NUMBER ${seeded}`)
} catch (error) {
  console.log(`FAILED_URL ${page.url()}`)
  const text = await page.locator('body').innerText().catch(() => '')
  console.log('PAGE_TEXT_START')
  console.log(text.slice(0, 3000))
  console.log('PAGE_TEXT_END')
  throw error
} finally {
  const video = page.video()
  await context.close()
  await browser.close()
  if (video) {
    const source = await video.path()
    copyFileSync(source, join(here, 'recording.webm'))
    rmSync(videoDir, { recursive: true, force: true })
    console.log('WROTE recording.webm')
  }
}
