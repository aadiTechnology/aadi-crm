import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { RecordsPanel } from '../src/features/records/RecordsPanel'
import type { CrmRecord, FormDefinition, FormVersion, Project, ProjectAccess, RecordPage } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'
const PROJECT_ID = '33333333-3333-4333-8333-333333333333'
const FORM_ID = '55555555-5555-4555-8555-555555555555'
const VERSION_ID = '88888888-8888-4888-8888-888888888888'
const RECORD_ID = '99999999-9999-4999-8999-999999999999'

function access(): ProjectAccess {
  return {
    role: 'project_manager',
    scope_policy: 'project',
    can_manage_project: true,
    can_manage_members: true,
    can_manage_forms: true,
    can_access_records: true,
    record_scope: 'project',
  }
}

function project(): Project {
  return {
    id: PROJECT_ID,
    tenant_id: TENANT,
    code: 'N-1',
    name: 'North yard',
    description: '',
    status: 'active',
    created_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    created_at: '2026-10-20T08:00:00.000Z',
    updated_at: '2026-10-20T08:00:00.000Z',
    access: access(),
  }
}

function formDefinition(): FormDefinition {
  return {
    id: FORM_ID,
    tenant_id: TENANT,
    project_id: PROJECT_ID,
    name: 'Site enquiry',
    description: 'Internal enquiry',
    status: 'draft',
    created_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    updated_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    created_at: '2026-10-20T08:00:00.000Z',
    updated_at: '2026-10-20T09:00:00.000Z',
    current_published_version_id: VERSION_ID,
    current_published_version_number: 1,
    fields: [
      {
        id: '66666666-6666-4666-8666-666666666666',
        field_key: 'school_name',
        label: 'Campus',
        field_type: 'text',
        required: false,
        help_text: '',
        section_name: 'Contact',
        position: 0,
        max_length: 40,
      },
    ],
  }
}

function version(): FormVersion {
  return {
    id: VERSION_ID,
    tenant_id: TENANT,
    project_id: PROJECT_ID,
    form_id: FORM_ID,
    version_number: 1,
    status: 'current',
    current: true,
    published_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    published_at: '2026-10-20T08:30:00.000Z',
    name: 'Site enquiry',
    description: 'Internal enquiry',
    fields: [
      {
        field_key: 'school_name',
        label: 'School name',
        field_type: 'text',
        required: true,
        help_text: 'Legal name',
        section_name: 'Contact',
        position: 0,
        max_length: 120,
      },
    ],
  }
}

function record(name = 'North school'): CrmRecord {
  return {
    id: RECORD_ID,
    project_id: PROJECT_ID,
    form_id: FORM_ID,
    form_version_id: VERSION_ID,
    version_number: 1,
    form_name: 'Site enquiry',
    form_description: 'Internal enquiry',
    public_number: 'N-1-0001',
    display_name: name,
    source: 'manual',
    source_label: 'Manual',
    created_at: '2026-10-20T10:00:00.000Z',
    updated_at: '2026-10-20T10:00:00.000Z',
    captured_at: '2026-10-20T10:00:00.000Z',
    fields: version().fields,
    values: { school_name: name },
    absent_from_draft: [{ field_key: 'school_name', label: 'School name' }],
    unmapped_values: [],
  }
}

function emptyPage(): RecordPage {
  return { items: [], total: 0, limit: 25, offset: 0 }
}

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function renderRecords(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tenants/:tenantId/records" element={<RecordsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/records/:projectId/new" element={<RecordsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/records/:projectId/:recordId/edit" element={<RecordsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/records/:projectId/:recordId" element={<RecordsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/records/:projectId" element={<RecordsPanel tenantId={TENANT} />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.unstubAllGlobals()
  vi.stubGlobal('fetch', vi.fn())
  document.cookie = 'aadi_csrf=csrf-token'
})

afterEach(() => {
  cleanup()
})

it('creates a record from the published version and keeps that label on the detail', async () => {
  const user = userEvent.setup()
  let saved = false
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`) && method === 'GET') {
      return json(project())
    }
    if (url.pathname.endsWith('/forms') && method === 'GET') {
      return json({ items: [formDefinition()] })
    }
    if (url.pathname.endsWith(`/versions/${VERSION_ID}`) && method === 'GET') {
      return json(version())
    }
    if (url.pathname.endsWith('/records') && method === 'GET') {
      return json(saved ? pageWith(record()) : emptyPage())
    }
    if (url.pathname.endsWith('/records') && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as { values: { school_name: string }; form_id: string }
      expect(body.form_id).toBe(FORM_ID)
      expect(body.values.school_name).toBe('North school')
      saved = true
      return json(record(), 201)
    }
    if (url.pathname.endsWith(`/records/${RECORD_ID}`) && method === 'GET') {
      return json(record())
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })

  renderRecords(`/tenants/${TENANT}/records/${PROJECT_ID}`)
  expect(await screen.findByText('No records yet')).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'New record' }))
  expect(await screen.findByLabelText(/School name/)).toBeInTheDocument()
  expect(screen.queryByText('Campus')).not.toBeInTheDocument()
  await user.type(screen.getByLabelText(/School name/), 'North school')
  await user.click(screen.getByRole('button', { name: 'Save record' }))
  expect(await screen.findByRole('heading', { name: 'N-1-0001' })).toBeInTheDocument()
  expect(screen.getByText('School name')).toBeInTheDocument()
  expect(screen.getByText('This field is not in the current draft. This record still uses version 1.')).toBeInTheDocument()
  expect(screen.getByText(/Form version/)).toHaveTextContent(VERSION_ID)
})

it('sends search to the server and can retry a failed list', async () => {
  const user = userEvent.setup()
  let failed = true
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`)) {
      return json(project())
    }
    if (url.pathname.endsWith('/forms')) {
      return json({ items: [] })
    }
    if (url.pathname.endsWith('/records')) {
      if (failed) {
        return json({ error: { message: 'The records could not be loaded.' } }, 500)
      }
      expect(url.searchParams.get('q')).toBe('North')
      return json(pageWith(record()))
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })

  renderRecords(`/tenants/${TENANT}/records/${PROJECT_ID}`)
  expect(await screen.findByText('The records could not be loaded.')).toBeInTheDocument()
  failed = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  await user.type(await screen.findByLabelText('Search records'), 'North')
  await user.click(screen.getByRole('button', { name: 'Search' }))
  expect(await screen.findByRole('link', { name: /N-1-0001/ })).toBeInTheDocument()
})

function pageWith(item: CrmRecord): RecordPage {
  return {
    items: [
      {
        id: item.id,
        public_number: item.public_number,
        form_id: item.form_id,
        form_name: item.form_name,
        form_version_id: item.form_version_id,
        version_number: item.version_number,
        display_name: item.display_name,
        source: item.source,
        source_label: item.source_label,
        created_at: item.created_at,
        updated_at: item.updated_at,
        summary: [{ label: 'School name', value: String(item.values.school_name) }],
      },
    ],
    total: 1,
    limit: 25,
    offset: 0,
  }
}

function asFetch() {
  return fetch as unknown as ReturnType<typeof vi.fn>
}
