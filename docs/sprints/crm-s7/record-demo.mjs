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
page.setDefaultTimeout(20000)

async function pause() {
  await page.waitForTimeout(700)
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
  await pause()

  log('create-form')
  await page.getByRole('link', { name: 'Forms' }).click()
  await page.getByRole('link', { name: 'Recording gate' }).click()
  await page.getByRole('link', { name: 'New form' }).click()
  await page.getByLabel('Form name').fill('Record capture')
  await page.getByLabel('Description').fill('Internal record capture')
  await pause()
  await page.getByRole('button', { name: 'Create form' }).click()
  await page.getByRole('heading', { name: 'Record capture' }).waitFor()
  await page.getByLabel('Field label').fill('School name')
  await page.getByLabel('Field identifier').fill('school_name')
  await page.getByLabel('Section').fill('Contact')
  await page.getByRole('checkbox', { name: 'Required' }).check()
  await page.getByRole('button', { name: 'Add field' }).click()
  await page.getByText('school_name').waitFor()
  await page.getByLabel('Field type').selectOption('dropdown')
  await page.getByLabel('Field label').fill('Priority')
  await page.getByLabel('Field identifier').fill('priority')
  await page.getByLabel('Section').fill('Qualification')
  await page.getByLabel('Options').fill('hot|Hot\nwarm|Warm\ncold|Cold')
  await pause()
  await page.getByRole('button', { name: 'Add field' }).click()
  await page.getByText('Hot, Warm, Cold').waitFor()
  await page.getByRole('button', { name: 'Publish version' }).click()
  await pause()
  await page.getByRole('button', { name: 'Confirm publish' }).click()
  await page.getByText('Render version 1').waitFor()
  await pause()

  log('create-record')
  await page.getByRole('link', { name: 'Records' }).click()
  await page.getByRole('link', { name: 'Recording gate' }).click()
  await page.getByRole('link', { name: 'New record' }).click()
  await page.getByLabel('Form').selectOption({ label: 'Record capture · version 1' })
  await page.getByLabel(/School name/).waitFor()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.getByText('School name is required.').waitFor()
  await pause()
  await page.getByLabel(/School name/).fill('North school')
  await page.getByLabel(/Priority/).selectOption('hot')
  await pause()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.locator('#record-detail-heading').waitFor()
  const number = (await page.locator('#record-detail-heading').innerText()).trim()
  console.log(`RECORD ${number}`)
  await page.locator('strong', { hasText: 'School name' }).first().waitFor()
  await page.getByText('North school').first().waitFor()
  await page.getByText(/version 1/).first().waitFor()
  await pause()

  log('publish-version-2')
  await page.getByRole('link', { name: 'Forms' }).click()
  await page.getByRole('link', { name: 'Recording gate' }).click()
  await page.getByRole('link', { name: 'Record capture' }).click()
  await page.getByRole('button', { name: 'Edit School name' }).click()
  await page.getByRole('heading', { name: 'Edit field' }).waitFor()
  await page.getByLabel('Field label').fill('Campus')
  await page.getByRole('button', { name: 'Save field' }).click()
  await page.getByRole('button', { name: 'Edit Campus' }).waitFor()
  await page.getByRole('button', { name: 'Publish version' }).click()
  await pause()
  await page.getByRole('button', { name: 'Confirm publish' }).click()
  await page.getByText('Render version 2').waitFor()
  await pause()

  log('historical-detail')
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}`)
  await page.getByRole('link', { name: new RegExp(number) }).click()
  await page.locator('strong', { hasText: 'School name' }).first().waitFor()
  await page.getByText('North school').first().waitFor()
  if (await page.locator('strong', { hasText: /^Campus$/ }).count()) {
    throw new Error('The record detail showed the newer draft label.')
  }
  await page.getByText(/version 1/).first().waitFor()
  await pause()
  await page.getByRole('link', { name: 'Edit record' }).click()
  await page.getByText('Saving uses this version, not the current draft.').waitFor()
  await page.getByLabel(/School name/).fill('North campus')
  await pause()
  await page.getByRole('button', { name: 'Save record' }).click()
  await page.getByText('North campus').first().waitFor()
  await page.locator('strong', { hasText: 'School name' }).first().waitFor()
  if (await page.locator('strong', { hasText: /^Campus$/ }).count()) {
    throw new Error('The edited record used the newer draft label.')
  }
  await pause()

  log('search-and-archive')
  await page.getByRole('link', { name: 'Recording gate' }).click()
  await page.getByLabel('Search records').fill('North campus')
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('link', { name: new RegExp(number) }).waitFor()
  await pause()
  await page.getByLabel('Search records').fill('zzzz-no-match')
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByText('No matching records').waitFor()
  await pause()
  await page.getByLabel('Search records').fill('')
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('link', { name: new RegExp(number) }).click()
  await page.getByRole('button', { name: 'Archive record' }).click()
  await page.getByRole('heading', { name: 'Recording gate' }).waitFor()
  if (await page.getByRole('link', { name: new RegExp(number) }).count()) {
    throw new Error('The archived record was still in the list.')
  }
  await pause()

  log('member-denied')
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.getByRole('button', { name: 'Sign in' }).waitFor()
  await page.getByLabel('Email').fill(memberEmail)
  await page.getByLabel('Password').fill(memberPassword)
  await pause()
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByText('Records is not available for this sign-in.').waitFor()
  await page.goto(`http://localhost:5174/tenants/${tenantId}/records/${projectId}`)
  await page.getByText('You do not have permission to perform this action.').waitFor()
  await pause()
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
