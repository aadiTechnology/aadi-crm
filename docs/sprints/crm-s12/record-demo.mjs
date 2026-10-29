import { createRequire } from 'node:module'
import { copyFileSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
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
const stamp = String(Date.now()).slice(-6)

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

const catalogRun = spawnSync(
  'C:/Users/lenovo/AadiTech/Product/aadi-crm/backend/.venv/Scripts/python.exe',
  ['-c', 'import json; from app.domain_templates import browser_catalog; print(json.dumps(browser_catalog()))'],
  { cwd: 'C:/Users/lenovo/AadiTech/Product/aadi-crm/backend', encoding: 'utf8' },
)
if (catalogRun.status !== 0) {
  throw new Error(catalogRun.stderr || 'The template catalog could not be read.')
}
const catalog = JSON.parse(catalogRun.stdout)
if (catalog.some((item) => item.form_name === 'Paneerwala')) {
  throw new Error('Paneerwala must not be in the publishable catalog.')
}

function log(step) {
  console.log(`STEP ${step}`)
}

rmSync(videoDir, { recursive: true, force: true })
mkdirSync(videoDir, { recursive: true })
const badPath = join(videoDir, 'notes.txt')
const csvPath = join(videoDir, 'synthetic-preschool.csv')
writeFileSync(badPath, 'this is not a workbook')
const headers = catalog[0].fields.map((field) => field.label)
function csvRow(values) {
  const base = Object.fromEntries(headers.map((header) => [header, '']))
  Object.assign(base, values)
  return headers.map((header) => {
    const value = base[header] ?? ''
    return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value
  }).join(',')
}
writeFileSync(
  csvPath,
  [
    headers.join(','),
    csvRow({
      'Lead ID': '1',
      'Inquiry Date': '2026-10-01',
      'School Name': 'Example North',
      'Mobile Number': '919800000099',
      Email: 'ada@example.com',
      'Email ID': 'ada@example.com',
      'Selling Point': '=Example note',
    }),
    csvRow({
      'Lead ID': '2',
      'Inquiry Date': '7351093.0',
      'School Name': 'Example South',
      'Email ID': 'not-an-email',
    }),
    csvRow({
      'Lead ID': '3',
      'Inquiry Date': '2026-10-02',
      'School Name': 'Example West',
      'Mobile Number': '919800000099',
      'Email ID': 'west@example.com',
    }),
  ].join('\r\n'),
)

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({
  viewport: { width: 1280, height: 720 },
  recordVideo: { dir: videoDir, size: { width: 1280, height: 720 } },
  acceptDownloads: true,
})
const page = await context.newPage()
page.setDefaultTimeout(30000)

async function pause(ms = 700) {
  await page.waitForTimeout(ms)
}

async function show(locator) {
  await locator.scrollIntoViewIfNeeded()
  await pause(350)
}

async function crm(method, path, body) {
  return page.evaluate(async ({ method, path, body }) => {
    const pair = document.cookie.split('; ').find((item) => item.startsWith('aadi_csrf='))
    const token = pair ? decodeURIComponent(pair.slice('aadi_csrf='.length)) : ''
    const response = await fetch(`http://localhost:8001${path}`, {
      method,
      credentials: 'include',
      headers: {
        'content-type': 'application/json',
        'x-csrf-token': token,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    const text = await response.text()
    let payload = null
    try {
      payload = text ? JSON.parse(text) : null
    } catch {
      payload = null
    }
    return {
      status: response.status,
      id: payload && typeof payload.id === 'string' ? payload.id : '',
      message: payload?.error?.message || '',
    }
  }, { method, path, body })
}

try {
  log('sign-in')
  await page.goto('http://localhost:5174/')
  await page.getByLabel('Email').fill(managerEmail)
  await page.getByLabel('Password').fill(managerPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /1792111368748/ }).click()
  await page.getByText('CRM is available in this organization.').waitFor()
  const created = []
  for (const template of catalog) {
    log(`create-${template.key}`)
    const code = `${template.project_code}-${stamp}`.slice(0, 40)
    const project = await crm('POST', `/api/v1/tenants/${tenantId}/projects`, {
      code,
      name: `${template.project_name} ${stamp}`,
      description: '',
    })
    if (project.status !== 201) {
      throw new Error(`Project ${template.form_name} was not created (${project.status}) ${project.message}`)
    }
    const form = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${project.id}/forms`, {
      name: template.form_name,
      description: template.description,
    })
    if (form.status !== 201) {
      throw new Error(`Form ${template.form_name} was not created (${form.status}) ${form.message}`)
    }
    for (const field of template.fields) {
      const added = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${project.id}/forms/${form.id}/fields`, field)
      if (added.status !== 201) {
        throw new Error(`Field ${field.field_key} was not added (${added.status}) ${added.message}`)
      }
    }
    const published = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${project.id}/forms/${form.id}/versions`, {})
    if (published.status !== 201) {
      throw new Error(`Form ${template.form_name} was not published (${published.status}) ${published.message}`)
    }
    created.push({ ...template, projectId: project.id, formId: form.id, code })
    console.log(`PUBLISHED ${template.form_name} ${code}`)
  }
  for (const template of created) {
    log(`show-${template.key}`)
    await page.goto(`http://localhost:5174/tenants/${tenantId}/forms/${template.projectId}/${template.formId}`)
    await page.getByRole('heading', { name: template.form_name, exact: true }).waitFor()
    await page.getByText('Render version 1').waitFor()
    await show(page.getByText(template.fields[0].label).first())
    await show(page.getByText(template.fields.at(-1).label).first())
  }
  const preschool = created[0]
  log('reject-file')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/imports/${preschool.projectId}`)
  await page.getByRole('heading', { name: 'Import and export' }).waitFor()
  await page.locator('input[type=file]').setInputFiles(badPath)
  await page.getByRole('button', { name: 'Upload file' }).click()
  await page.getByText('Upload a .csv or .xlsx file.').waitFor()
  await show(page.getByText('Upload a .csv or .xlsx file.'))
  log('upload')
  await page.locator('input[type=file]').setInputFiles(csvPath)
  await page.getByRole('button', { name: 'Upload file' }).click()
  await page.getByText('The file is uploaded.').waitFor()
  await show(page.getByLabel('Map School Name'))
  await page.getByRole('button', { name: 'Save mapping' }).click()
  await page.getByText('Mapping saved. Preview checks the rows and does not create records.').waitFor()
  log('preview')
  await page.getByRole('button', { name: 'Preview import' }).click()
  await page.getByText('Dry-run only. No CRM records were created. Ready 0, rejected 1, skipped 0, awaiting review 2. Input rows 3, not counting the header.').waitFor()
  await show(page.getByText('Inquiry Date must use YYYY-MM-DD.'))
  await page.getByLabel('Decision for row 2').selectOption('accept_new')
  await page.getByLabel('Decision for row 4').selectOption('skip')
  await pause()
  log('commit')
  await page.getByRole('button', { name: 'Import records' }).click()
  await page.getByText('Partially completed. Accepted 1, rejected 1, skipped 1, awaiting review 0. Input rows 3, not counting the header.').waitFor()
  const [errorDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download error report' }).click(),
  ])
  const errorText = readFileSync(await errorDownload.path(), 'utf8')
  console.log(`ERROR_HAS_DATE ${errorText.includes('YYYY-MM-DD')}`)
  console.log(`ERROR_HAS_SKIP ${errorText.includes('Skipped during duplicate review.')}`)
  log('repeat')
  await page.getByRole('button', { name: 'Repeat this import' }).click()
  await page.getByText('Partially completed. Accepted 1, rejected 1, skipped 1, awaiting review 0. Input rows 3, not counting the header.').waitFor()
  log('record')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${preschool.projectId}`)
  await page.getByRole('heading', { name: 'Records (1)' }).waitFor()
  await page.getByRole('link', { name: /-0001$/ }).first().click()
  await page.getByRole('heading', { name: /-0001$/ }).waitFor()
  await page.getByText('Example North').first().waitFor()
  await show(page.getByText('Preschool').first())
  if (await page.getByText('Example West').count()) {
    throw new Error('The skipped synthetic row was opened as a record.')
  }
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
  await page.goto(`http://localhost:5174/tenants/${tenantId}/imports/${preschool.projectId}`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  if (await page.getByText('Example North').count()) {
    throw new Error('The unauthorized page showed the synthetic record.')
  }
  await pause(800)
  log('done')
  console.log(`STAMP ${stamp}`)
} catch (error) {
  console.log(`FAILED_URL ${page.url()}`)
  const text = await page.locator('body').innerText().catch(() => '')
  console.log('PAGE_TEXT_START')
  console.log(text.slice(0, 2500))
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
