import { createRequire } from 'node:module'
import { copyFileSync, mkdirSync, readFileSync, rmSync } from 'node:fs'
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

async function pause(ms = 700) {
  await page.waitForTimeout(ms)
}

async function show(locator) {
  await locator.scrollIntoViewIfNeeded()
  await pause(400)
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
      payload = { raw: text.slice(0, 300) }
    }
    return { status: response.status, payload }
  }, { method, path, body })
}

async function cardValue(title) {
  const card = page.locator('article.kpi-card', { has: page.getByRole('heading', { name: title, exact: true }) })
  return (await card.locator('.kpi-value').innerText()).trim()
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

  log('create-project')
  const project = await crm('POST', `/api/v1/tenants/${tenantId}/projects`, {
    code: `KPI${stamp}`.slice(0, 40),
    name: `KPI yard ${stamp}`,
    description: 'Synthetic Sprint 11 demonstration project.',
  })
  if (project.status !== 201) {
    throw new Error(`Project was not created (${project.status})`)
  }
  const projectId = project.payload.id
  const form = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${projectId}/forms`, {
    name: 'KPI capture',
    description: 'Synthetic form for the KPI demonstration.',
  })
  if (form.status !== 201) {
    throw new Error(`Form was not created (${form.status})`)
  }
  const field = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${projectId}/forms/${form.payload.id}/fields`, {
    field_key: 'school_name',
    label: 'School name',
    field_type: 'text',
    required: true,
    help_text: '',
    section_name: 'Identity',
    max_length: 120,
  })
  if (field.status !== 201) {
    throw new Error(`Field was not added (${field.status})`)
  }
  const published = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${projectId}/forms/${form.payload.id}/versions`, {})
  if (published.status !== 201) {
    throw new Error(`Form was not published (${published.status})`)
  }
  const north = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${projectId}/records`, {
    form_id: form.payload.id,
    source: 'manual',
    values: { school_name: `KPI North ${stamp}` },
  })
  const south = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${projectId}/records`, {
    form_id: form.payload.id,
    source: 'manual',
    values: { school_name: `KPI South ${stamp}` },
  })
  if (north.status !== 201 || south.status !== 201) {
    throw new Error(`Records were not created (${north.status}, ${south.status})`)
  }
  const recordId = north.payload.id
  async function followUp(dueDate, dueTime, summary) {
    const created = await crm('POST', `/api/v1/tenants/${tenantId}/projects/${projectId}/records/${recordId}/follow-ups`, {
      task_type: 'call',
      owner_user_id: north.payload.created_by,
      due_date: dueDate,
      due_time: dueTime,
      summary,
      call_status: 'connected',
    })
    if (created.status !== 201) {
      throw new Error(`Follow-up was not created (${created.status}) ${created.payload?.error?.message || ''}`)
    }
    return created.payload
  }
  await followUp('2026-10-20', '09:00', 'Synthetic overdue call')
  await followUp('2026-10-21', '15:00', 'Synthetic call due today')
  await followUp('2026-10-22', '11:00', 'Synthetic upcoming call')
  const done = await followUp('2026-10-21', '16:00', 'Synthetic completed call')
  const completed = await crm(
    'POST',
    `/api/v1/tenants/${tenantId}/projects/${projectId}/records/${recordId}/follow-ups/${done.id}/complete`,
    { expected_updated_at: done.updated_at, outcome: 'Synthetic outcome' },
  )
  if (completed.status !== 200) {
    throw new Error(`Follow-up was not completed (${completed.status})`)
  }

  const empty = await crm('POST', `/api/v1/tenants/${tenantId}/projects`, {
    code: `EMPTY${stamp}`.slice(0, 40),
    name: `KPI empty ${stamp}`,
    description: '',
  })
  if (empty.status !== 201) {
    throw new Error(`Empty project was not created (${empty.status})`)
  }

  log('kpis')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/kpis/${projectId}`)
  await page.getByRole('heading', { name: `KPI yard ${stamp}` }).waitFor()
  await page.getByRole('link', { name: 'View active records' }).waitFor()
  const active = await cardValue('Active records')
  const createdCount = await cardValue('Records created')
  const overdue = await cardValue('Overdue')
  const today = await cardValue('Due today')
  const upcoming = await cardValue('Upcoming')
  const completedCount = await cardValue('Completed follow-ups')
  console.log(`KPI active=${active} created=${createdCount} overdue=${overdue} today=${today} upcoming=${upcoming} completed=${completedCount}`)
  if (active !== '2' || overdue !== '1' || today !== '1' || upcoming !== '1' || completedCount !== '1') {
    throw new Error('KPI cards did not match the synthetic rows.')
  }
  await show(page.getByRole('heading', { name: 'Follow-up workload' }))
  await show(page.getByRole('heading', { name: 'Open follow-ups by due date' }))

  log('created-period')
  await page.getByLabel('Records created from').fill('2020-01-01')
  await page.getByLabel('Records created to').fill('2020-01-02')
  await page.getByRole('button', { name: 'Apply period' }).click()
  await page.getByText('UTC dates 2020-01-01 through 2020-01-02.').waitFor()
  if ((await cardValue('Records created')) !== '0' || (await cardValue('Active records')) !== '2') {
    throw new Error('The created-date period changed the active record count.')
  }
  await page.getByRole('link', { name: 'View records created in this period' }).click()
  await page.getByRole('heading', { name: 'Records (0)' }).waitFor()
  await page.getByText('No matching records').waitFor()
  await page.getByRole('link', { name: 'Back to project KPIs' }).click()
  await page.getByRole('heading', { name: `KPI yard ${stamp}` }).waitFor()

  log('active-records')
  await page.getByLabel('Records created from').fill('2026-10-21')
  await page.getByLabel('Records created to').fill('2026-10-21')
  await page.getByRole('button', { name: 'Apply period' }).click()
  await page.getByText('UTC dates 2026-10-21 through 2026-10-21.').waitFor()
  const createdToday = await cardValue('Records created')
  console.log(`KPI created_today=${createdToday}`)
  await page.getByRole('link', { name: 'View active records' }).click()
  await page.getByRole('heading', { name: 'Records (2)' }).waitFor()
  await page.getByText(`KPI North ${stamp}`, { exact: true }).waitFor()
  await page.getByText(`KPI South ${stamp}`, { exact: true }).waitFor()
  await page.getByRole('link', { name: 'Back to project KPIs' }).click()

  log('overdue')
  await page.getByRole('link', { name: 'View overdue follow-ups' }).click()
  await page.getByRole('heading', { name: 'Overdue follow-ups' }).waitFor()
  await page.getByText('Showing 1 of 1').waitFor()
  await page.getByText(`KPI North ${stamp}`, { exact: true }).waitFor()
  if (await page.getByText(`KPI South ${stamp}`, { exact: true }).count()) {
    throw new Error('The overdue list included a record with no overdue follow-up.')
  }
  await page.getByRole('link', { name: 'Back to project KPIs' }).click()

  log('upcoming')
  await page.getByRole('link', { name: 'View upcoming follow-ups' }).click()
  await page.getByRole('heading', { name: 'Upcoming follow-ups' }).waitFor()
  await page.getByText('Showing 1 of 1').waitFor()
  await page.getByRole('link', { name: 'Back to project KPIs' }).click()

  log('completed')
  await page.getByRole('button', { name: 'View completed follow-ups' }).click()
  await page.getByText('The list has 1 completed follow-ups. The KPI count is 1.').waitFor()
  await show(page.locator('#completed-heading'))
  await page.getByRole('button', { name: 'Back to KPI overview' }).click()

  log('empty')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/kpis/${empty.payload.id}`)
  await page.getByRole('heading', { name: `KPI empty ${stamp}` }).waitFor()
  if ((await cardValue('Active records')) !== '0' || (await cardValue('Overdue')) !== '0') {
    throw new Error('The empty project showed records or follow-ups.')
  }
  await page.getByText('No active records.').waitFor()
  await page.getByText('No open follow-ups in these queues.').first().waitFor()

  log('audit')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/audit`)
  await page.getByRole('heading', { name: 'Audit' }).waitFor()
  const auditMain = page.locator('main')
  await Promise.race([
    page.getByText('No audit events').waitFor(),
    page.getByRole('alert').waitFor(),
    page.locator('table tbody tr').first().waitFor(),
  ])
  const auditText = await auditMain.innerText()
  const auditRows = await page.locator('table tbody tr').count()
  let auditState = 'rows'
  if (auditText.includes('No audit events')) {
    auditState = 'empty'
  } else if (auditText.includes('unavailable')) {
    auditState = 'unavailable'
  } else if (auditText.includes('permission')) {
    auditState = 'denied'
  }
  console.log(`AUDIT_STATE ${auditState}`)
  console.log(`AUDIT_ROWS ${auditRows}`)
  if (auditText.toLowerCase().includes('password') || auditText.includes('aadi_session')) {
    throw new Error('The audit page showed a credential.')
  }
  await show(page.getByRole('heading', { name: 'Audit' }))

  log('narrow')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/kpis/${projectId}`)
  await page.getByRole('link', { name: 'View active records' }).waitFor()
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
  const chooser = page.getByRole('link', { name: /1792111368748/ })
  const deniedNav = page.getByText('Projects is not available for this sign-in.')
  await Promise.race([chooser.waitFor(), deniedNav.waitFor()])
  if ((await chooser.count()) > 0) {
    await chooser.click()
  }
  await page.goto(`http://localhost:5174/tenants/${tenantId}/kpis/${projectId}`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  if (await page.getByText(`KPI North ${stamp}`, { exact: true }).count()) {
    throw new Error('The unauthorized page showed a project record.')
  }
  await page.goto(`http://localhost:5174/tenants/${tenantId}/audit`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  const memberAudit = await page.locator('main').innerText()
  if (memberAudit.includes(`KPI North ${stamp}`) || memberAudit.toLowerCase().includes('password')) {
    throw new Error('The member audit page showed project or credential data.')
  }
  console.log('MEMBER_AUDIT denied')
  await pause(800)
  log('done')
  console.log(`STAMP ${stamp}`)
  console.log(`PROJECT ${projectId}`)
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
