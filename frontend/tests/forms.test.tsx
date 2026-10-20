import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { FormsPanel } from '../src/features/forms/FormsPanel'
import type { FormDefinition, FormField, Project, ProjectAccess } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'
const PROJECT_ID = '33333333-3333-4333-8333-333333333333'
const FORM_ID = '55555555-5555-4555-8555-555555555555'
const FIELD_A = '66666666-6666-4666-8666-666666666666'
const FIELD_B = '77777777-7777-4777-8777-777777777777'

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

function field(overrides: Partial<FormField> = {}): FormField {
  return {
    id: FIELD_A,
    field_key: 'school_name',
    label: 'School name',
    field_type: 'text',
    required: true,
    help_text: 'Legal name',
    section_name: 'Contact',
    position: 0,
    max_length: 120,
    ...overrides,
  }
}

function formDefinition(fields: FormField[], name = 'Enquiry draft'): FormDefinition {
  return {
    id: FORM_ID,
    tenant_id: TENANT,
    project_id: PROJECT_ID,
    name,
    description: 'Internal enquiry',
    status: 'draft',
    created_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    updated_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    created_at: '2026-10-20T08:00:00.000Z',
    updated_at: '2026-10-20T08:00:00.000Z',
    fields,
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
        <Route path="/tenants/:tenantId/forms" element={<FormsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/forms/:projectId" element={<FormsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/forms/:projectId/new" element={<FormsPanel tenantId={TENANT} />} />
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

it('creates a form, saves fields, reorders them, and shows the same order after reload', async () => {
  const user = userEvent.setup()
  let stored = formDefinition([])
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    if (url.pathname.endsWith('/projects') && method === 'GET') {
      return json({ items: [project()] })
    }
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`) && method === 'GET') {
      return json(project())
    }
    if (url.pathname.endsWith('/forms') && method === 'GET') {
      return json({ items: stored.fields.length === 0 && stored.name === 'Enquiry draft' ? [] : [stored] })
    }
    if (url.pathname.endsWith('/forms') && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as { name: string; description: string }
      stored = formDefinition([], body.name)
      stored.description = body.description
      return json(stored, 201)
    }
    if (url.pathname.endsWith('/fields') && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as FormField
      const next = field({
        id: stored.fields.length === 0 ? FIELD_A : FIELD_B,
        field_key: body.field_key,
        label: body.label,
        field_type: body.field_type,
        required: body.required,
        section_name: body.section_name ?? '',
        help_text: body.help_text ?? '',
        position: stored.fields.length,
        options: body.options,
      })
      stored = { ...stored, fields: [...stored.fields, next] }
      return json(stored, 201)
    }
    if (url.pathname.endsWith('/fields/reorder') && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as { field_ids: string[] }
      const byId = new Map(stored.fields.map((item) => [item.id, item]))
      stored = {
        ...stored,
        fields: body.field_ids.map((id, position) => ({ ...byId.get(id)!, position })),
      }
      return json(stored)
    }
    if (url.pathname.endsWith(`/forms/${FORM_ID}`) && method === 'GET') {
      return json(stored)
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })

  renderForms(`/tenants/${TENANT}/forms`)
  await user.click(await screen.findByRole('link', { name: 'North yard' }))
  expect(await screen.findByText('No form definitions yet.')).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'New form' }))
  await user.type(await screen.findByLabelText('Form name'), 'Enquiry draft')
  await user.type(screen.getByLabelText('Description'), 'Internal enquiry')
  await user.click(screen.getByRole('button', { name: 'Create form' }))

  expect(await screen.findByRole('heading', { name: 'Enquiry draft' })).toBeInTheDocument()
  await user.type(screen.getByLabelText('Field label'), 'School name')
  await user.type(screen.getByLabelText('Field identifier'), 'school_name')
  await user.click(screen.getByRole('checkbox', { name: 'Required' }))
  await user.type(screen.getByLabelText('Section'), 'Contact')
  await user.click(screen.getByRole('button', { name: 'Add field' }))
  expect(await screen.findByText('School name')).toBeInTheDocument()

  await user.selectOptions(screen.getByLabelText('Field type'), 'dropdown')
  await user.type(screen.getByLabelText('Field label'), 'Priority')
  await user.type(screen.getByLabelText('Field identifier'), 'priority')
  await user.type(screen.getByLabelText('Options'), 'hot|Hot\nwarm|Warm')
  await user.click(screen.getByRole('button', { name: 'Add field' }))
  expect(await screen.findByText('Hot, Warm')).toBeInTheDocument()

  const list = screen.getByRole('list')
  expect(within(list).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
    expect.stringContaining('School name'),
    expect.stringContaining('Priority'),
  ])
  await user.click(screen.getByRole('button', { name: 'Move Priority up' }))
  const reordered = await screen.findByRole('list')
  expect(within(reordered).getAllByRole('listitem')[0]).toHaveTextContent('Priority')
  expect(within(reordered).getAllByRole('listitem')[1]).toHaveTextContent('School name')

  cleanup()
  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}`)
  const reloaded = await screen.findByRole('list')
  expect(within(reloaded).getAllByRole('listitem')[0]).toHaveTextContent('Priority')
  expect(within(reloaded).getAllByRole('listitem')[1]).toHaveTextContent('school_name')
  const createCall = asFetch().mock.calls.find((call) => String(call[1]?.method) === 'POST' && String(call[0]).endsWith('/forms'))
  expect(String(createCall?.[1]?.headers?.get?.('X-CSRF-Token') ?? createCall?.[1]?.headers?.['X-CSRF-Token'] ?? '')).not.toBe('')
})

it('shows a duplicate identifier error and keeps a project member from editing', async () => {
  const user = userEvent.setup()
  const stored = formDefinition([field()])
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`) && method === 'GET') {
      return json(project())
    }
    if (url.pathname.endsWith(`/forms/${FORM_ID}`) && method === 'GET') {
      return json(stored)
    }
    if (url.pathname.endsWith('/fields') && method === 'POST') {
      return json({ error: { message: 'Field identifier is already used on this form.' } }, 409)
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })

  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}`)
  expect(await screen.findByText('School name')).toBeInTheDocument()
  await user.type(screen.getByLabelText('Field label'), 'Other name')
  await user.type(screen.getByLabelText('Field identifier'), 'school_name')
  await user.click(screen.getByRole('button', { name: 'Add field' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Field identifier is already used on this form.')

  cleanup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`)) {
      return json(project(false))
    }
    if (url.pathname.endsWith('/forms') && !url.pathname.endsWith(`/forms/${FORM_ID}`)) {
      return json({ items: [stored] })
    }
    if (url.pathname.endsWith(`/forms/${FORM_ID}`)) {
      return json(stored)
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}`)
  expect(await screen.findByRole('link', { name: /Enquiry draft/ })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'New form' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: /Enquiry draft/ }))
  expect(await screen.findByText('School name')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Add field' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save form' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Remove School name' })).not.toBeInTheDocument()
})

it('shows an authorization failure without revealing another form', async () => {
  asFetch().mockImplementation(() =>
    json({ error: { message: 'The requested resource was not found.' }, name: 'Secret form' }, 404),
  )
  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}`)
  expect(await screen.findByRole('alert')).toHaveTextContent('The requested resource was not found.')
  expect(screen.queryByText('Secret form')).not.toBeInTheDocument()
})

it('blocks an empty picklist before saving', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`)) {
      return json(project())
    }
    if (url.pathname.endsWith(`/forms/${FORM_ID}`)) {
      return json(formDefinition([]))
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  renderForms(`/tenants/${TENANT}/forms/${PROJECT_ID}/${FORM_ID}`)
  await screen.findByRole('heading', { name: 'Enquiry draft' })
  await user.selectOptions(screen.getByLabelText('Field type'), 'dropdown')
  await user.type(screen.getByLabelText('Field label'), 'Priority')
  await user.type(screen.getByLabelText('Field identifier'), 'priority')
  await user.click(screen.getByRole('button', { name: 'Add field' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Each option needs a value and a label, separated by |.')
  expect(asFetch().mock.calls.some((call) => String(call[0]).includes('/fields'))).toBe(false)
})
