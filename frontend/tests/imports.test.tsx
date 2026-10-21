import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { ImportsPanel } from '../src/features/imports/ImportsPanel'
import type { ImportJob } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'
const PROJECT = '33333333-3333-4333-8333-333333333333'
const FORM = '44444444-4444-4444-8444-444444444444'
const JOB = '55555555-5555-4555-8555-555555555555'

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function job(overrides: Partial<ImportJob> = {}): ImportJob {
  return {
    id: JOB,
    project_id: PROJECT,
    form_id: FORM,
    form_version_id: '66666666-6666-4666-8666-666666666666',
    filename: 'leads.csv',
    status: 'uploaded',
    headers: ['School name', 'Email', 'Notes'],
    fields: [
      { field_key: 'school_name', label: 'School name', field_type: 'text', required: true, options: [] },
      { field_key: 'email', label: 'Email', field_type: 'email', required: false, options: [] },
    ],
    unimportable_fields: [],
    mapping: null,
    suggested_mapping: { 'School name': 'school_name', Email: 'email', Notes: null },
    unmapped_columns: [],
    rows: [
      {
        row_number: 2,
        source: { 'School name': 'North', Email: 'north@example.com', Notes: 'keep' },
        unmapped: {},
        values: {},
        errors: [],
        candidates: [],
        decision: null,
        outcome: 'stored',
        record_id: null,
      },
      {
        row_number: 3,
        source: { 'School name': '', Email: 'bad', Notes: '' },
        unmapped: {},
        values: {},
        errors: [],
        candidates: [],
        decision: null,
        outcome: 'stored',
        record_id: null,
      },
    ],
    summary: {
      input_rows: 2,
      header_included: false,
      accepted: 0,
      rejected: 0,
      skipped: 0,
      awaiting_review: 0,
      not_committed: 2,
    },
    ...overrides,
  }
}

function renderProject() {
  render(
    <MemoryRouter initialEntries={[`/tenants/${TENANT}/imports/${PROJECT}`]}>
      <Routes>
        <Route path="/tenants/:tenantId/imports/:projectId" element={<ImportsPanel tenantId={TENANT} />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: () => 'blob:import' })
  Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: () => undefined })
  document.cookie = 'aadi_csrf=csrf-token'
})

afterEach(() => {
  cleanup()
})

it('shows a loading state and then no projects', async () => {
  vi.mocked(fetch).mockImplementation(() => json({ items: [] }))
  render(
    <MemoryRouter>
      <ImportsPanel tenantId={TENANT} />
    </MemoryRouter>,
  )
  expect(screen.getByRole('status')).toHaveTextContent('Loading import')
  expect(await screen.findByText('No projects')).toBeInTheDocument()
})

it('previews invalid and duplicate rows, commits the counts, and repeats the same job', async () => {
  const user = userEvent.setup()
  const preview = job({
    status: 'previewed',
    mapping: { 'School name': 'school_name', Email: 'email', Notes: null },
    unmapped_columns: ['Notes'],
    summary: {
      input_rows: 2,
      header_included: false,
      accepted: 0,
      rejected: 0,
      skipped: 0,
      awaiting_review: 0,
      not_committed: 2,
      preview_accepted: 0,
      preview_rejected: 1,
      preview_skipped: 0,
      preview_awaiting_review: 1,
      records_created: 0,
    },
    rows: [
      {
        row_number: 2,
        source: { 'School name': 'North', Email: 'north@example.com', Notes: 'keep' },
        unmapped: { Notes: 'keep' },
        values: { school_name: 'North', email: 'north@example.com' },
        errors: [],
        candidates: [{ kind: 'existing', message: 'Possible match on Email with N-1-0001.', public_number: 'N-1-0001', display_name: 'North' }],
        decision: null,
        outcome: 'stored',
        record_id: null,
      },
      {
        row_number: 3,
        source: { 'School name': '', Email: 'bad', Notes: '' },
        unmapped: {},
        values: {},
        errors: [{ field: 'school_name', message: 'School name is required.' }],
        candidates: [],
        decision: null,
        outcome: 'stored',
        record_id: null,
      },
    ],
  })
  const committed = job({
    ...preview,
    status: 'partial',
    summary: {
      input_rows: 2,
      header_included: false,
      accepted: 0,
      rejected: 1,
      skipped: 1,
      awaiting_review: 0,
      not_committed: 0,
    },
  })
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/forms')) {
      return json({ items: [{ id: FORM, name: 'Site enquiry', current_published_version_id: preview.form_version_id, fields: [] }] })
    }
    if (url.endsWith('/imports') && init?.method === 'POST') {
      return json(job(), 201)
    }
    if (url.endsWith('/mapping')) {
      return json(job({ mapping: preview.mapping, unmapped_columns: ['Notes'] }))
    }
    if (url.endsWith('/preview')) {
      return json(preview)
    }
    if (url.endsWith('/decisions')) {
      return json(preview)
    }
    if (url.endsWith('/commit')) {
      return json(committed)
    }
    if (url.endsWith('/errors')) {
      return Promise.resolve(
        new Response('row_number,field,message\n3,school_name,School name is required.\n', {
          status: 200,
          headers: { 'Content-Disposition': 'attachment; filename="import-errors.csv"' },
        }),
      )
    }
    if (url.includes('/record-exports')) {
      return Promise.resolve(
        new Response('public_number\nN-1-0001\n', {
          status: 200,
          headers: {
            'Content-Disposition': 'attachment; filename="records.csv"',
            'X-CRM-Export-Rows': '1',
          },
        }),
      )
    }
    if (url.includes('/records')) {
      return json({ items: [], total: 1, limit: 1, offset: 0 })
    }
    return json({ error: { message: 'missing' } }, 404)
  })
  renderProject()
  expect(await screen.findByRole('option', { name: 'Site enquiry' })).toBeInTheDocument()
  const file = new File(['School name,Email\nNorth,north@example.com\n'], 'leads.csv', { type: 'text/csv' })
  await user.upload(screen.getByLabelText('CSV or XLSX file'), file)
  await user.click(screen.getByRole('button', { name: 'Upload file' }))
  expect(await screen.findByText('Map School name')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Save mapping' }))
  expect(await screen.findByText(/Unmapped columns kept on this import: Notes/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Preview import' }))
  expect(await screen.findByText(/Dry-run only. No CRM records were created./)).toBeInTheDocument()
  expect(screen.getByText('Possible match on Email with N-1-0001.')).toBeInTheDocument()
  expect(screen.getByText(/School name is required/)).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Decision for row 2'), 'skip')
  await user.click(screen.getByRole('button', { name: 'Import records' }))
  expect(await screen.findByText(/Partially completed. Accepted 0, rejected 1, skipped 1, awaiting review 0/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Repeat this import' }))
  expect(await screen.findByText(/Accepted 0, rejected 1, skipped 1/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Export CSV' }))
  expect(await screen.findByText('Exported 1 data rows. The list reports 1 matching records.')).toBeInTheDocument()
})

it('shows a failure when the upload is rejected', async () => {
  const user = userEvent.setup()
  vi.mocked(fetch).mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/forms')) {
      return json({ items: [{ id: FORM, name: 'Site enquiry', current_published_version_id: 'v', fields: [] }] })
    }
    if (init?.method === 'POST') {
      return json({ error: { message: 'The file has no data rows.' } }, 422)
    }
    return json({ items: [] })
  })
  renderProject()
  await screen.findByRole('option', { name: 'Site enquiry' })
  const file = new File(['only a header'], 'empty.csv', { type: 'text/csv' })
  await user.upload(screen.getByLabelText('CSV or XLSX file'), file)
  await user.click(screen.getByRole('button', { name: 'Upload file' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The file has no data rows.')
})
