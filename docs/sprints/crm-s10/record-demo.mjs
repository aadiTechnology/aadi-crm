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
const today = isoDate(0)
const yesterday = isoDate(-1)

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

async function pause(ms = 900) {
  await page.waitForTimeout(ms)
}

async function show(locator) {
  await locator.scrollIntoViewIfNeeded()
  await pause(400)
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
  await show(created)
}

async function processReminders(outcome) {
  return page.evaluate(
    async ({ tenantId, outcome }) => {
      const csrf = document.cookie
        .split(';')
        .map((part) => part.trim())
        .find((part) => part.startsWith('aadi_csrf='))
      if (!csrf) {
        throw new Error('Missing CSRF cookie')
      }
      const token = decodeURIComponent(csrf.slice('aadi_csrf='.length))
      const headers = { 'Content-Type': 'application/json', 'X-CSRF-Token': token }
      if (outcome) {
        headers['X-CRM-Reminder-Test-Outcome'] = outcome
      }
      const response = await fetch(`http://localhost:8001/api/v1/tenants/${tenantId}/reminders/process`, {
        method: 'POST',
        credentials: 'include',
        headers,
      })
      const body = await response.json()
      if (!response.ok) {
        throw new Error(`Process failed ${response.status} ${JSON.stringify(body)}`)
      }
      return body
    },
    { tenantId, outcome: outcome ?? null },
  )
}

try {
  log('sign-in')
  await page.goto('http://localhost:5174/')
  await page.getByLabel('Email').fill(managerEmail)
  await page.getByLabel('Password').fill(managerPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /Bootstrap recording/ }).click()
  await page.getByRole('link', { name: 'Reminders', exact: true }).click()
  await page.getByRole('heading', { name: 'Reminders', exact: true }).waitFor()
  await page.getByText('Loading reminders').waitFor({ state: 'hidden' })
  const empty = await page.getByText('No reminders').count()
  console.log(`EMPTY ${empty}`)
  await show(page.getByRole('heading', { name: 'Reminders', exact: true }))

  log('create-follow-up')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}/new`)
  await page.getByLabel('Form').selectOption({ label: 'Record capture · version 2' })
  await page.getByLabel(/Campus/).fill('Reminder lane')
  await page.getByLabel(/Priority/).selectOption('warm')
  await pause()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.locator('#record-detail-heading').waitFor()
  const number = (await page.locator('#record-detail-heading').innerText()).trim()
  const recordUrl = page.url()
  console.log(`RECORD ${number}`)
  console.log(`RECORD_URL ${recordUrl}`)
  await addFollowUp({
    task: 'note',
    date: today,
    time: '09:00',
    summary: 'Morning reminder',
  })

  log('deliver')
  await page.getByRole('link', { name: 'Reminders', exact: true }).click()
  await page.getByRole('heading', { name: 'Reminders', exact: true }).waitFor()
  await page.getByRole('button', { name: 'Deliver pending reminders' }).click()
  await page.getByText(/Those emails were not delivered/).waitFor()
  await page.getByText('Loading reminders').waitFor({ state: 'hidden' })
  await page.getByRole('link', { name: `Open record ${number}` }).first().waitFor()
  const populated = await page.locator('.reminder-card').count()
  console.log(`CARDS ${populated}`)
  await show(page.getByRole('link', { name: `Open record ${number}` }).first())
  await pause()

  log('open-record')
  await page.getByRole('link', { name: `Open record ${number}` }).first().click()
  await page.locator('#record-detail-heading', { hasText: number }).waitFor()
  await show(page.getByText('Morning reminder').first())
  await pause()

  log('second-run')
  await page.getByRole('link', { name: 'Reminders', exact: true }).click()
  await page.getByRole('link', { name: `Open record ${number}` }).first().waitFor()
  await page.getByText('Loading reminders').waitFor({ state: 'hidden' })
  await page.getByRole('button', { name: 'Deliver pending reminders' }).click()
  await page.waitForFunction((recordNumber) => {
    const text = document.body.innerText
    return (
      text.includes('The test adapter recorded 0 email reminders.') &&
      text.includes(`Open record ${recordNumber}`) &&
      !text.includes('Loading reminders') &&
      !text.includes('Delivering reminders')
    )
  }, number)
  const afterSecond = await page.locator('.reminder-card').count()
  console.log(`CARDS_AFTER_SECOND ${afterSecond}`)
  if (afterSecond !== populated) {
    throw new Error(`Delivery created extra reminders: ${populated} then ${afterSecond}`)
  }
  await show(page.getByText('The test adapter recorded 0 email reminders.'))
  await pause()

  log('temporary-failure')
  await page.goto(recordUrl)
  await page.locator('#record-detail-heading').waitFor()
  await addFollowUp({
    task: 'email',
    date: yesterday,
    time: '09:30',
    summary: 'Failure sample',
  })
  const temporary = await processReminders('retryable')
  console.log(`TEMPORARY ${JSON.stringify(temporary)}`)
  if (!temporary.retryable) {
    throw new Error('The test adapter did not record a retryable failure.')
  }
  await page.getByRole('link', { name: 'Reminders', exact: true }).click()
  await page.getByRole('heading', { name: 'Email failures for projects you manage' }).waitFor()
  await show(page.getByText('The email attempt failed and can be retried.').first())
  await page.getByText(/Attempts 1/).first().waitFor()
  await pause()

  log('terminal-failure')
  const secondFailure = await processReminders('retryable')
  const thirdFailure = await processReminders('retryable')
  console.log(`RETRY_2 ${JSON.stringify(secondFailure)}`)
  console.log(`RETRY_3 ${JSON.stringify(thirdFailure)}`)
  await page.reload()
  const failures = page.getByRole('region', { name: 'Email failures for projects you manage' })
  await failures.getByText(/Attempts 3/).first().waitFor()
  await show(failures.getByText(/Attempts 3/).first())
  await show(failures.getByText(/Directory address/).first())
  await pause()
  await failures.locator('.reminder-card', { hasText: 'Attempts 3' }).first().getByRole('button', { name: 'Retry delivery' }).click()
  await page.getByText('The same reminder was queued again. A new reminder was not created.').waitFor()
  await pause()

  log('narrow')
  await page.setViewportSize({ width: 390, height: 720 })
  await page.getByRole('heading', { name: 'Reminders', exact: true }).waitFor()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 8)
  console.log(`NARROW_OVERFLOW ${overflow}`)
  await show(page.getByRole('heading', { name: 'Reminders', exact: true }))
  await pause()
  await page.setViewportSize({ width: 1280, height: 720 })

  log('unauthorized')
  await page.goto('http://localhost:5174/')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('button', { name: 'Sign in' }).waitFor()
  await page.getByLabel('Email').fill(memberEmail)
  await page.getByLabel('Password').fill(memberPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /1792111368748/ }).click()
  await page.getByText('Reminders is not available for this sign-in.').waitFor()
  await show(page.getByText('Reminders is not available for this sign-in.'))
  await page.goto(`http://localhost:5174/tenants/${tenantId}/reminders`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  await show(page.getByText('You do not have permission to perform this action.'))
  if (await page.getByText('Morning reminder').count()) {
    throw new Error('The unauthorized page showed reminder content.')
  }
  if (await page.getByText('Failure sample').count()) {
    throw new Error('The unauthorized page showed the failure follow-up.')
  }
  await pause(1200)
  log('done')
  console.log(`DATES ${yesterday} ${today}`)
} catch (error) {
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

