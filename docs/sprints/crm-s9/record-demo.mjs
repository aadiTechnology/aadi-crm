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

function envValue(name) {
  const line = envFile.split(/\r?\n/).find((item) => item.startsWith(`${name}=`))
  if (!line) {
    throw new Error(`Missing ${name}`)
  }
  return line.slice(name.length + 1).trim()
}

function isoDate(offset) {
  const date = new Date()
  date.setDate(date.getDate() + offset)
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

const managerEmail = envValue('PLAYWRIGHT_RECORDING_USER_EMAIL')
const managerPassword = envValue('PLAYWRIGHT_RECORDING_USER_PASSWORD')
const memberEmail = envValue('PLAYWRIGHT_MEMBER_EMAIL')
const memberPassword = envValue('PLAYWRIGHT_MEMBER_PASSWORD')
const tenantId = 'e02812a0-8717-4f5f-be19-57f263daef52'
const projectId = '8d0b7f84-d481-45cf-beca-3dd1af92ec97'
const yesterday = isoDate(-1)
const today = isoDate(0)
const tomorrow = isoDate(1)

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
page.setDefaultTimeout(25000)

async function pause(ms = 800) {
  await page.waitForTimeout(ms)
}

async function show(locator) {
  await locator.scrollIntoViewIfNeeded()
  await pause(350)
}

async function chooseOwner() {
  const select = page.getByLabel('Owner')
  const labels = await select.locator('option').allTextContents()
  const match = labels.find((label) => label.toLowerCase().includes(managerEmail.toLowerCase()))
  if (match) {
    await select.selectOption({ label: match })
    return
  }
  const value = await select.locator('option').nth(1).getAttribute('value')
  if (!value) {
    throw new Error('No follow-up owner is available.')
  }
  await select.selectOption(value)
}

async function addFollowUp({ task, date, time, summary, callStatus }) {
  await show(page.getByRole('heading', { name: 'Follow-ups' }))
  await page.getByLabel('Task type', { exact: true }).selectOption(task)
  await chooseOwner()
  await page.getByLabel('Due date').fill(date)
  await page.getByLabel('Due time').fill(time)
  if (callStatus) {
    await page.getByLabel('Call status').selectOption(callStatus)
  }
  await page.getByLabel('Discussion summary').fill(summary)
  await pause()
  const before = await page.getByRole('article').count()
  await page.getByRole('button', { name: 'Add follow-up' }).click()
  const created = page.getByRole('article').nth(before)
  await created.waitFor()
  if ((await created.innerText()).includes('alert') && !(await created.innerText()).includes(summary)) {
    throw new Error(await page.locator('main').innerText())
  }
  await show(created)
}

try {
  log('sign-in')
  await page.goto('http://localhost:5174/')
  await page.getByLabel('Email').fill(managerEmail)
  await page.getByLabel('Password').fill(managerPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /Bootstrap recording/ }).click()
  await page.getByRole('link', { name: 'Records', exact: true }).click()
  await pause()

  log('open-record')
  await page.evaluate(async ({ tenantId, projectId }) => {
    const csrf = document.cookie
      .split(';')
      .map((part) => part.trim())
      .find((part) => part.startsWith('aadi_csrf='))
    if (!csrf) {
      throw new Error('Missing CSRF cookie')
    }
    const token = decodeURIComponent(csrf.slice('aadi_csrf='.length))
    for (const queue of ['overdue', 'today', 'upcoming']) {
      const listed = await fetch(
        `http://localhost:8001/api/v1/tenants/${tenantId}/projects/${projectId}/follow-ups?queue=${queue}&limit=100`,
        { credentials: 'include' },
      )
      const body = await listed.json()
      if (!listed.ok) {
        throw new Error(`Queue read failed ${listed.status}`)
      }
      for (const item of body.items ?? []) {
        const response = await fetch(
          `http://localhost:8001/api/v1/tenants/${tenantId}/projects/${projectId}/records/${item.record_id}/follow-ups/${item.id}/cancel`,
          {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
            body: JSON.stringify({
              expected_updated_at: item.updated_at,
              outcome: 'Cleared before the follow-up demonstration.',
            }),
          },
        )
        if (!response.ok) {
          throw new Error(`Cancel failed ${response.status}`)
        }
      }
    }
  }, { tenantId, projectId })
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}/new`)
  await page.getByLabel('Form').selectOption({ label: 'Record capture · version 2' })
  await page.getByLabel(/Campus/).fill('Timeline lane')
  await page.getByLabel(/Priority/).selectOption('warm')
  await pause()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.locator('#record-detail-heading').waitFor()
  const number = (await page.locator('#record-detail-heading').innerText()).trim()
  console.log(`RECORD ${number}`)
  await page.getByText(/Form version/).first().waitFor()
  await show(page.getByRole('heading', { name: 'Activity' }))
  await pause()

  log('create-follow-ups')
  await addFollowUp({
    task: 'note',
    date: yesterday,
    time: '09:00',
    summary: 'Overdue check',
  })
  await addFollowUp({
    task: 'call',
    date: today,
    time: '12:00',
    summary: 'Call today',
    callStatus: 'connected',
  })
  await addFollowUp({
    task: 'email',
    date: tomorrow,
    time: '09:30',
    summary: 'Upcoming email',
  })
  await show(page.getByText('Follow-up created').first())
  await pause()

  log('edit-and-complete')
  const email = page.getByRole('article', { name: 'Email follow-up' })
  await email.getByRole('button', { name: 'Edit Email' }).click()
  const editor = page.locator('form', { has: page.getByRole('button', { name: 'Save Email' }) })
  await editor.getByLabel('Due time').fill('11:15')
  await editor.getByLabel('Discussion summary').fill('Rescheduled visit')
  await pause()
  await editor.getByRole('button', { name: 'Save Email' }).click()
  await email.filter({ hasText: 'Rescheduled visit' }).waitFor()
  await page.getByRole('button', { name: 'Save Email' }).waitFor({ state: 'hidden' })
  const call = page.getByRole('article', { name: 'Call follow-up' }).filter({ hasText: 'Call today' })
  await show(call)
  await call.getByLabel('Outcome').fill('Spoke with the family')
  await pause()
  await call.getByRole('button', { name: 'Complete Call' }).click()
  await page.getByText('Outcome Spoke with the family').waitFor()
  await show(page.getByText('Follow-up completed').first())
  await pause()

  log('queues')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/follow-ups/${projectId}?queue=overdue`)
  await page.getByRole('heading', { name: 'Overdue follow-ups' }).waitFor()
  await show(page.getByText('Overdue check'))
  await pause()
  await page.getByRole('link', { name: 'Today', exact: true }).click()
  await page.getByRole('heading', { name: 'Follow-ups due today' }).waitFor()
  await page.getByText('No follow-ups are due today.').waitFor()
  await show(page.getByText('No follow-ups are due today.'))
  await pause()
  await page.getByRole('link', { name: 'Upcoming', exact: true }).click()
  await page.getByRole('heading', { name: 'Upcoming follow-ups' }).waitFor()
  await show(page.getByText('Rescheduled visit'))
  await page.getByText(`${tomorrow} 11:15`).waitFor()
  await pause()

  log('unauthorized')
  await page.goto('http://localhost:5174/')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('button', { name: 'Sign in' }).waitFor()
  await page.getByLabel('Email').fill(memberEmail)
  await page.getByLabel('Password').fill(memberPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /1792111368748/ }).click()
  await page.getByText('Follow-ups is not available for this sign-in.').waitFor()
  await show(page.getByText('Follow-ups is not available for this sign-in.'))
  await page.goto(`http://localhost:5174/tenants/${tenantId}/follow-ups/${projectId}`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  await show(page.getByText('You do not have permission to perform this action.'))
  if (await page.getByText('Overdue check').count()) {
    throw new Error('The unauthorized page showed a follow-up.')
  }
  await pause(1200)
  log('done')
  console.log(`DATES ${yesterday} ${today} ${tomorrow}`)
} catch (error) {
  const text = await page.locator('main').innerText().catch(() => '')
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
