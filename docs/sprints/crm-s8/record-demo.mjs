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

const managerEmail = envValue('PLAYWRIGHT_RECORDING_USER_EMAIL')
const managerPassword = envValue('PLAYWRIGHT_RECORDING_USER_PASSWORD')
const memberEmail = envValue('PLAYWRIGHT_MEMBER_EMAIL')
const memberPassword = envValue('PLAYWRIGHT_MEMBER_PASSWORD')
const tenantId = 'e02812a0-8717-4f5f-be19-57f263daef52'
const projectId = '8d0b7f84-d481-45cf-beca-3dd1af92ec97'
const captureFormId = '44cd01db-2480-4c57-a890-14777848c96e'

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

try {
  log('sign-in')
  await page.goto('http://localhost:5174/')
  await page.getByLabel('Email').fill(managerEmail)
  await page.getByLabel('Password').fill(managerPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /Bootstrap recording/ }).click()
  await page.getByRole('link', { name: 'Records' }).click()
  await pause()

  log('open-project')
  await page.getByRole('link', { name: 'Recording gate' }).click()
  await page.getByRole('heading', { name: 'Recording gate' }).waitFor()
  const historical = page.getByRole('link', { name: /S2-REC-0002/ })
  await show(historical)
  await pause()

  log('historical-detail')
  await historical.click()
  await page.locator('#record-detail-heading').waitFor()
  await page.locator('strong', { hasText: 'School name' }).first().waitFor()
  await page.getByText(/version 1/).first().waitFor()
  if (await page.locator('strong', { hasText: /^Campus$/ }).count()) {
    throw new Error('The stored record showed the newer Campus label.')
  }
  await show(page.locator('strong', { hasText: 'School name' }).first())
  await pause()
  await page.getByRole('link', { name: 'Edit record' }).click()
  await page.getByText('Saving uses this version, not the current draft.').waitFor()
  await page.getByLabel(/School name/).fill('West campus')
  await pause()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.getByText('West campus').first().waitFor()
  await page.locator('strong', { hasText: 'School name' }).first().waitFor()
  if (await page.locator('strong', { hasText: /^Campus$/ }).count()) {
    throw new Error('The edited record used the newer Campus label.')
  }
  await pause()

  log('create-record')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}/new`)
  await page.getByLabel('Form').selectOption({ label: 'Record capture · version 2' })
  await page.getByLabel(/Campus/).waitFor()
  await page.getByLabel('Source').selectOption('phone_call')
  await page.getByLabel(/Campus/).fill('East campus')
  await page.getByLabel(/Priority/).selectOption('hot')
  await pause()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.locator('#record-detail-heading').waitFor()
  const number = (await page.locator('#record-detail-heading').innerText()).trim()
  const recordId = new URL(page.url()).pathname.split('/').filter(Boolean).at(-1)
  console.log(`RECORD ${number}`)
  await page.getByText('East campus').first().waitFor()
  await page.locator('strong', { hasText: 'Campus' }).first().waitFor()
  await pause()

  log('seed-pages')
  const seeded = await page.evaluate(
    async ({ tenantId, projectId, captureFormId }) => {
      const csrf = document.cookie
        .split(';')
        .map((part) => part.trim())
        .find((part) => part.startsWith('aadi_csrf='))
      if (!csrf) {
        throw new Error('Missing CSRF cookie')
      }
      const token = decodeURIComponent(csrf.slice('aadi_csrf='.length))
      const names = ['Page lane', 'Page row', 'Page seat']
      const numbers = []
      for (const name of names) {
        const response = await fetch(
          `http://localhost:8001/api/v1/tenants/${tenantId}/projects/${projectId}/records`,
          {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
            body: JSON.stringify({
              form_id: captureFormId,
              source: 'website',
              values: { school_name: name, priority: 'warm' },
            }),
          },
        )
        const body = await response.json()
        if (!response.ok) {
          throw new Error(`Seed failed ${response.status}`)
        }
        numbers.push(body.public_number)
      }
      return numbers
    },
    { tenantId, projectId, captureFormId },
  )
  console.log(`SEEDED ${seeded.join(',')}`)

  log('filter-and-sort')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}`)
  await page.getByRole('heading', { name: 'Recording gate' }).waitFor()
  await page.getByLabel('Source').selectOption('phone_call')
  await page.getByLabel('Sort').selectOption('public_number:asc')
  await page.getByRole('button', { name: 'Search' }).click()
  const createdLink = page.getByRole('link', { name: new RegExp(number) })
  await show(createdLink)
  await pause()
  await page.getByLabel('Search records').fill('zzzz-no-match')
  await page.getByRole('button', { name: 'Search' }).click()
  await show(page.getByText('No matching records'))
  await pause()

  log('paginate')
  await page.getByLabel('Search records').fill('')
  await page.getByLabel('Source').selectOption('')
  await page.getByLabel('Page size').selectOption('5')
  await page.getByRole('button', { name: 'Search' }).click()
  await show(page.getByRole('button', { name: 'Next' }))
  await page.getByRole('button', { name: 'Next' }).click()
  await page.getByText(/Showing/).waitFor()
  await show(page.getByRole('button', { name: 'Previous' }))
  await pause()
  await page.getByRole('button', { name: 'Previous' }).click()
  await show(page.getByRole('link', { name: /S2-REC-0001/ }))
  await pause()

  log('archive')
  await page.getByLabel('Search records').fill(number)
  await page.getByRole('button', { name: 'Search' }).click()
  await show(createdLink)
  await createdLink.click()
  await page.getByRole('button', { name: 'Archive record' }).click()
  await page.getByRole('heading', { name: 'Recording gate' }).waitFor()
  await page.getByLabel('Search records').fill(number)
  await page.getByRole('button', { name: 'Search' }).click()
  await show(page.getByText('No matching records'))
  if (await page.getByRole('link', { name: new RegExp(number) }).count()) {
    throw new Error('The archived record was still in the list.')
  }
  await pause()
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}/${recordId}`)
  await page.getByText('The requested resource was not found.').waitFor()
  await pause()

  log('member-denied')
  await page.goto('http://localhost:5174/')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('button', { name: 'Sign in' }).waitFor()
  await page.getByLabel('Email').fill(memberEmail)
  await page.getByLabel('Password').fill(memberPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('link', { name: /1792111368748/ }).click()
  await page.getByText('Records is not available for this sign-in.').waitFor()
  await show(page.getByText('Records is not available for this sign-in.'))
  await pause(1500)
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  await show(page.getByText('You do not have permission to perform this action.'))
  await pause(2000)
  log('done')
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
