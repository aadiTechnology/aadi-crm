import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { FormsPanel } from '../src/features/forms/FormsPanel'
import type { FormDefinition, FormField, FormVersion, Project, ProjectAccess } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'
const PROJECT_ID = '33333333-3333-4333-8333-333333333333'
const FORM_ID = '55555555-5555-4555-8555-555555555555'
const VERSION_1 = '88888888-8888-4888-8888-888888888888'
const VERSION_2 = '99999999-9999-4999-8999-999999999999'

function access(canManage: boolean): ProjectAccess {
  return {
    role: canManage ? 'project_manager' : 'project_member',
    scope_policy: canManage ? 'project' : 'assigned',
    can_manage_project: canManage,
    can_manage_members: canManage,
    can_manage_forms: canManage,
    can_access_records: true,
    record_scope: canManage ? 'project' : 'assigned',
  }
}

function project(canManage = true): Project {
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
    access: access(canManage),
  }
}

function textField(label: string): FormField {
  return {
    id: '66666666-6666-4666-8666-666666666666',
    field_key: 'school_name',
    label,
    field_type: 'text',
    required: true,
    help_text: 'Legal name',
    section_name: 'Contact',
    position: 0,
    max_length: 120,
  }
}

function formDefinition(label: string, versionNumber: number | null = null): FormDefinition {
  return {
    id: FORM_ID,
    tenant_id: TENANT,
    project_id: PROJECT_ID,
    name: 'Enquiry draft',
    description: 'Internal enquiry',
    status: 'draft',
    created_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    updated_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    created_at: '2026-10-20T08:00:00.000Z',
    updated_at: '2026-10-20T08:00:00.000Z',
    current_published_version_id: versionNumber === null ? null : versionNumber === 1 ? VERSION_1 : VERSION_2,
    current_published_version_number: versionNumber,
    fields: [textField(label)],
  }
}

function version(id: string, number: number, label: string, current: boolean): FormVersion {
  const { id: _fieldId, ...field } = textField(label)
  return {
    id,
    tenant_id: TENANT,
    project_id: PROJECT_ID,
    form_id: FORM_ID,
    version_number: number,
    status: current ? 'current' : 'published',
    current,
    published_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    published_at: '2026-10-20T09:00:00.000Z',
    name: 'Enquiry draft',
    description: 'Internal enquiry',
    fields: [field],
  }
}

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function renderForms(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tenants/:tenantId/forms/:projectId/:formId/preview" element={<FormsPanel tenantId={TENANT} />} />
        <Route
          path="/tenants/:tenantId/forms/:projectId/:formId/versions/:versionId"
          element={<FormsPanel tenantId={TENANT} />}
        />
        <Route path="/tenants/:tenantId/forms/:projectId/:formId" element={<FormsPanel tenantId={TENANT} />} />
      </Routes>
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  document.cookie = 'aadi_csrf=; Max-Age=0'
})

beforeEach(() => {
  vi.unstubAllGlobals()
  vi.stubGlobal('fetch', vi.fn())
  document.cookie = 'aadi_csrf=csrf-token'
})

function asFetch() {
  return fetch as unknown as ReturnType<typeof vi.fn>
}

it('previews a draft, marks required fields, and does not save a record', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`)) {
      return json(project())
    }
    if (url.pathname.endsWith('/preview')) {
      const { id: _fieldId, ...field } = textField('School name')
      return json({
        form_id: FORM_ID,
        name: 'Enquiry draft',
        description: 'Internal enquiry',
        source: 'draft',
        fields: [
          field,
          {
            ...field,
            field_key: 'packet',
            label: 'Packet',
            field_type: 'file',
            required: false,
            position: 1,
          },
          {
            ...field,
            field_key: 'ref',
            label: 'Reference',
            field_type: 'auto_number',
            required: false,
            position: 2,
            prefix: 'PG',
            pad_width: 4,
          },
        ],
      })
    }
    if (method !== 'GET') {
      return json({ error: { message: 'Unexpected write' } }, 500)
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })

  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}/preview`)
  expect(await screen.findByRole('heading', { name: 'Enquiry draft' })).toBeInTheDocument()
  expect(screen.getByText('Draft preview. Required fields are marked. Nothing is saved.')).toBeInTheDocument()
  expect(screen.getByLabelText(/School name/)).toBeRequired()
  await user.click(screen.getByRole('button', { name: 'Check preview' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('School name is required.')
  expect(screen.getByText('File upload is not available in this view.')).toBeInTheDocument()
  expect(screen.getByText('Auto-number is not generated in this view.')).toBeInTheDocument()
  expect(screen.getByText('Prefix PG')).toBeInTheDocument()
  expect(screen.queryByText('PG-0001')).not.toBeInTheDocument()
  await user.type(screen.getByLabelText(/School name/), 'North school')
  await user.click(screen.getByRole('button', { name: 'Check preview' }))
  expect(await screen.findByRole('status')).toHaveTextContent('No CRM record was saved.')
  expect(asFetch().mock.calls.some((call) => String(call[1]?.method ?? 'GET') !== 'GET')).toBe(false)
})

it('publishes version 2 without changing the rendered version 1 snapshot', async () => {
  const user = userEvent.setup()
  let draft = formDefinition('School name')
  let versions = [] as FormVersion[]
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`)) {
      return json(project())
    }
    if (url.pathname.endsWith('/versions') && method === 'POST') {
      const number = versions.length + 1
      const id = number === 1 ? VERSION_1 : VERSION_2
      const next = version(id, number, draft.fields[0]?.label ?? '', number === versions.length + 1)
      versions = versions.map((item) => ({ ...item, current: false, status: 'published' as const })).concat(next)
      draft = {
        ...draft,
        current_published_version_id: id,
        current_published_version_number: number,
      }
      return json(next, 201)
    }
    if (url.pathname.endsWith(`/versions/${VERSION_1}`)) {
      const stored = versions.find((item) => item.id === VERSION_1)
      return json(stored)
    }
    if (url.pathname.endsWith(`/versions/${VERSION_2}`)) {
      const stored = versions.find((item) => item.id === VERSION_2)
      return json(stored)
    }
    if (url.pathname.endsWith('/versions')) {
      return json({ items: versions })
    }
    if (url.pathname.endsWith(`/fields/${draft.fields[0]?.id}`) && method === 'PATCH') {
      draft = formDefinition('Campus', draft.current_published_version_number)
      return json(draft)
    }
    if (url.pathname.endsWith(`/forms/${FORM_ID}`)) {
      return json(draft)
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })

  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}`)
  expect(await screen.findByText('No published version yet.')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Publish version' }))
  expect(await screen.findByRole('link', { name: /Render version 1/ })).toBeInTheDocument()
  expect(screen.getByText('Current published version 1')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Edit School name' }))
  const label = screen.getByLabelText('Field label')
  await user.clear(label)
  await user.type(label, 'Campus')
  await user.click(screen.getByRole('button', { name: 'Save field' }))
  expect(await screen.findByText('Campus')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Publish version' }))
  expect(await screen.findByRole('link', { name: /Render version 2/ })).toBeInTheDocument()
  cleanup()
  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}/versions/${VERSION_1}`)
  expect(await screen.findByRole('heading', { name: 'Enquiry draft' })).toBeInTheDocument()
  expect(screen.getByText('Published version 1. This schema stays as it was published.')).toBeInTheDocument()
  expect(screen.getByLabelText(/School name/)).toBeInTheDocument()
  expect(screen.queryByLabelText(/Campus/)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Check published form' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('School name is required.')
})

it('lets a project member render a published version and hides publish', async () => {
  const user = userEvent.setup()
  const stored = version(VERSION_1, 1, 'School name', true)
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`)) {
      return json(project(false))
    }
    if (url.pathname.endsWith(`/versions/${VERSION_1}`)) {
      return json(stored)
    }
    if (url.pathname.endsWith('/versions')) {
      return json({ items: [stored] })
    }
    if (url.pathname.endsWith(`/forms/${FORM_ID}`)) {
      return json(formDefinition('Campus', 1))
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })

  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}`)
  expect(await screen.findByText('Campus')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Publish version' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Preview draft' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: /Render version 1/ }))
  expect(await screen.findByLabelText(/School name/)).toBeInTheDocument()
  expect(screen.queryByLabelText(/Campus/)).not.toBeInTheDocument()
})

it('does not reveal a form when a published version is not available', async () => {
  asFetch().mockImplementation(() =>
    json({ error: { message: 'The requested resource was not found.' }, name: 'Secret form' }, 404),
  )
  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}/versions/${VERSION_1}`)
  expect(await screen.findByRole('alert')).toHaveTextContent('The requested resource was not found.')
  expect(screen.queryByText('Secret form')).not.toBeInTheDocument()
})
