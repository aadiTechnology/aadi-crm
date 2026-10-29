import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { RolesPanel } from '../src/features/roles/RolesPanel'
import { CrmShellPage } from '../src/features/shell/CrmShellPage'
import { readFrontendConfig } from '../src/lib/config'

const TENANT = '11111111-1111-4111-8111-111111111111'
const ROLE = '22222222-2222-4222-8222-222222222222'
const USER = '33333333-3333-4333-8333-333333333333'
const OTHER_USER = '44444444-4444-4444-8444-444444444444'
const MEMBERSHIP = 'membership-secret-value'
const LEADS = 'crm.lead_management.read'
const PROJECT_ACCESS = 'crm.project_management.access'
const PROJECT_MANAGE = 'crm.project_management.manage'
const RECORDS = 'crm.records.access'
const CATALOG = [LEADS, PROJECT_ACCESS, PROJECT_MANAGE, RECORDS]

const crmApi = readFrontendConfig().crmApiBaseUrl.replace(/\/+$/, '')
const platformApi = readFrontendConfig().platformApiBaseUrl.replace(/\/+$/, '')

type RoleRecord = {
  id: string
  tenant_id: string
  name: string
  description: string
  status: string
  permissions: string[]
  created_at: string
  updated_at: string
}

function roleRecord(overrides: Partial<RoleRecord> = {}): RoleRecord {
  return {
    id: ROLE,
    tenant_id: TENANT,
    name: 'Sales desk',
    description: 'Works the sales queue',
    status: 'active',
    permissions: [LEADS],
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-02T00:00:00Z',
    ...overrides,
  }
}

function directoryUser(id = USER, email = 'ada@example.com') {
  return {
    id,
    email,
    identity_active: true,
    membership_status: 'active',
    membership_id: MEMBERSHIP,
    membership_created_at: '2026-10-01T00:00:00Z',
    membership_updated_at: '2026-10-01T00:00:00Z',
    roles: [{ id: 'cp-role', key: 'tenant_admin', name: 'Platform Tenant Admin' }],
  }
}

function assignment(status: string, userId = USER) {
  return {
    id: status === 'active' ? '55555555-5555-4555-8555-555555555555' : '66666666-6666-4666-8666-666666666666',
    tenant_id: TENANT,
    role_id: ROLE,
    user_id: userId,
    status,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-03T00:00:00Z',
  }
}

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
}

function asFetch(): ReturnType<typeof vi.fn> {
  return vi.mocked(fetch)
}

function requestUrl(call: unknown[]): string {
  return String(call[0])
}

function requestInit(call: unknown[]): RequestInit {
  return (call[1] ?? {}) as RequestInit
}

function methodOf(init: RequestInit): string {
  return (init.method ?? 'GET').toUpperCase()
}

function header(init: RequestInit, name: string): string | null {
  return new Headers(init.headers).get(name)
}

function bodyOf(init: RequestInit): unknown {
  return typeof init.body === 'string' ? JSON.parse(init.body) : undefined
}

function calls(): { url: string; init: RequestInit }[] {
  return asFetch().mock.calls.map((call) => ({ url: requestUrl(call), init: requestInit(call) }))
}

function renderRoles(path: string, canReadUsers = true) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tenants/:tenantId/roles" element={<RolesPanel tenantId={TENANT} canReadUsers={canReadUsers} />} />
        <Route
          path="/tenants/:tenantId/roles/new"
          element={<RolesPanel tenantId={TENANT} canReadUsers={canReadUsers} />}
        />
        <Route
          path="/tenants/:tenantId/roles/:roleId"
          element={<RolesPanel tenantId={TENANT} canReadUsers={canReadUsers} />}
        />
      </Routes>
    </MemoryRouter>,
  )
}

function renderShell(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tenants/:tenantId" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/roles" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/roles/new" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/roles/:roleId" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/projects" element={<CrmShellPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  document.cookie = 'aadi_csrf=csrf-token'
})

afterEach(() => {
  cleanup()
  document.cookie = 'aadi_csrf=; Max-Age=0'
  vi.unstubAllGlobals()
})

it('shows a loading state and then an empty role list', async () => {
  let release: (value: Response) => void = () => undefined
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === `${crmApi}/api/v1/tenants/${TENANT}/roles`) {
      return new Promise<Response>((resolve) => {
        release = resolve
      })
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles`)
  expect(screen.getByRole('status')).toHaveTextContent('Loading CRM roles')
  release(await json({ items: [] }))
  expect(await screen.findByText('No CRM roles yet')).toBeInTheDocument()
  expect(screen.getByText(/different from a project role/)).toBeInTheDocument()
})

it('creates and edits a role for the active tenant', async () => {
  const user = userEvent.setup()
  let current = roleRecord()
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = methodOf(init ?? {})
    if (url === `${crmApi}/api/v1/tenants/${TENANT}/roles` && method === 'POST') {
      const body = bodyOf(init ?? {}) as { name: string; description: string }
      current = roleRecord({ name: body.name, description: body.description, permissions: [] })
      return json(current, 201)
    }
    if (url === `${crmApi}/api/v1/tenants/${TENANT}/roles/${ROLE}` && method === 'PATCH') {
      const body = bodyOf(init ?? {}) as { name: string; description: string }
      current = { ...current, name: body.name, description: body.description }
      return json(current)
    }
    if (url === `${crmApi}/api/v1/tenants/${TENANT}/roles`) {
      return json({ items: current.name === 'Sales desk' && method === 'GET' ? [] : [current] })
    }
    if (url.endsWith('/crm-permissions')) {
      return json({ items: CATALOG })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [] })
    }
    if (url.endsWith(`/roles/${ROLE}/assignments`)) {
      return json({ items: [] })
    }
    if (url === `${platformApi}/api/v1/tenants/${TENANT}/users`) {
      return json([])
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles`)
  expect(await screen.findByText('No CRM roles yet')).toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'New CRM role' }))
  await user.type(screen.getByLabelText('Role name'), 'Desk lead')
  await user.type(screen.getByLabelText('Description'), 'Owns the queue')
  await user.click(screen.getByRole('button', { name: 'Create role' }))
  expect(await screen.findByText('Role created.')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: 'Desk lead' })).toBeInTheDocument()
  const createCall = calls().find((call) => call.url.endsWith('/roles') && methodOf(call.init) === 'POST')
  expect(createCall?.url).toBe(`${crmApi}/api/v1/tenants/${TENANT}/roles`)
  expect(createCall?.init.credentials).toBe('include')
  expect(header(createCall?.init ?? {}, 'X-CSRF-Token')).toBe('csrf-token')
  expect(bodyOf(createCall?.init ?? {})).toEqual({ name: 'Desk lead', description: 'Owns the queue' })
  await user.clear(screen.getByLabelText('Role name'))
  await user.type(screen.getByLabelText('Role name'), 'Desk captain')
  await user.click(screen.getByRole('button', { name: 'Save role' }))
  expect(await screen.findByText('Role saved.')).toBeInTheDocument()
  const updateCall = calls().find((call) => methodOf(call.init) === 'PATCH')
  expect(updateCall?.url).toBe(`${crmApi}/api/v1/tenants/${TENANT}/roles/${ROLE}`)
  expect(header(updateCall?.init ?? {}, 'X-CSRF-Token')).toBe('csrf-token')
  expect(bodyOf(updateCall?.init ?? {})).toEqual({ name: 'Desk captain', description: 'Owns the queue' })
})

it('deactivates a role without deleting it', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = methodOf(init ?? {})
    if (url.endsWith('/deactivate') && method === 'POST') {
      return json(roleRecord({ status: 'inactive' }))
    }
    if (url.endsWith('/crm-permissions')) {
      return json({ items: CATALOG })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [LEADS] })
    }
    if (url.endsWith(`/roles/${ROLE}/assignments`)) {
      return json({ items: [] })
    }
    if (url.endsWith('/users')) {
      return json([])
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord()] })
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`)
  expect(await screen.findByRole('heading', { name: 'Sales desk' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Deactivate role' }))
  expect(screen.getByText(/not a delete/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Confirm deactivation' }))
  expect(await screen.findByText(/Role deactivated/)).toBeInTheDocument()
  expect(screen.getAllByText('Inactive').length).toBeGreaterThan(0)
  const deactivateCall = calls().find((call) => call.url.endsWith('/deactivate'))
  expect(deactivateCall?.url).toBe(`${crmApi}/api/v1/tenants/${TENANT}/roles/${ROLE}/deactivate`)
  expect(methodOf(deactivateCall?.init ?? {})).toBe('POST')
  expect(deactivateCall?.init.body).toBeUndefined()
  expect(header(deactivateCall?.init ?? {}, 'X-CSRF-Token')).toBe('csrf-token')
  expect(calls().some((call) => methodOf(call.init) === 'DELETE')).toBe(false)
})

it('shows only the permissions returned by the API', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/crm-permissions')) {
      return json({ items: [RECORDS, 'roles.manage', 'users.read', 'audit.read'] })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [RECORDS] })
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord({ permissions: [RECORDS] })] })
    }
    if (url.endsWith('/assignments')) {
      return json({ items: [] })
    }
    if (url.endsWith('/users')) {
      return json([])
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`)
  await user.click(await screen.findByRole('tab', { name: 'Permissions' }))
  expect(screen.getByRole('checkbox', { name: /Open records/ })).toBeChecked()
  expect(screen.getByText(RECORDS)).toBeInTheDocument()
  expect(screen.queryByText(LEADS)).not.toBeInTheDocument()
  expect(screen.queryByText('roles.manage')).not.toBeInTheDocument()
  expect(screen.queryByText('users.read')).not.toBeInTheDocument()
  expect(screen.queryByText('audit.read')).not.toBeInTheDocument()
  expect(screen.queryByText(MEMBERSHIP)).not.toBeInTheDocument()
})

it('adds and removes role permissions with one key per request', async () => {
  const user = userEvent.setup()
  let granted = [LEADS]
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = methodOf(init ?? {})
    if (url.endsWith('/permissions/remove') && method === 'POST') {
      granted = granted.filter((key) => key !== (bodyOf(init ?? {}) as { permission_key: string }).permission_key)
      return json({ items: granted })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`) && method === 'POST') {
      granted = [...granted, (bodyOf(init ?? {}) as { permission_key: string }).permission_key]
      return json({ items: granted })
    }
    if (url.endsWith('/crm-permissions')) {
      return json({ items: CATALOG })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: granted })
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord()] })
    }
    if (url.endsWith('/assignments')) {
      return json({ items: [] })
    }
    if (url.endsWith('/users')) {
      return json([directoryUser()])
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`)
  await user.click(await screen.findByRole('tab', { name: 'Permissions' }))
  await user.click(screen.getByRole('checkbox', { name: /Open projects/ }))
  await user.click(screen.getByRole('checkbox', { name: /Read leads/ }))
  await user.click(screen.getByRole('button', { name: 'Save permissions' }))
  expect(await screen.findByText('Permissions saved.')).toBeInTheDocument()
  const writes = calls().filter((call) => methodOf(call.init) === 'POST' && call.url.includes('/permissions'))
  expect(writes.map((call) => call.url)).toEqual([
    `${crmApi}/api/v1/tenants/${TENANT}/roles/${ROLE}/permissions/remove`,
    `${crmApi}/api/v1/tenants/${TENANT}/roles/${ROLE}/permissions`,
  ])
  expect(writes.every((call) => header(call.init, 'X-CSRF-Token') === 'csrf-token')).toBe(true)
  expect(writes.every((call) => call.init.credentials === 'include')).toBe(true)
  expect(bodyOf(writes[0]?.init ?? {})).toEqual({ permission_key: LEADS })
  expect(bodyOf(writes[1]?.init ?? {})).toEqual({ permission_key: PROJECT_ACCESS })
  expect(screen.getByRole('checkbox', { name: /Open projects/ })).toBeChecked()
  expect(screen.getByRole('checkbox', { name: /Read leads/ })).not.toBeChecked()
})

it('loads active and revoked assignments', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/crm-permissions')) {
      return json({ items: CATALOG })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [] })
    }
    if (url.endsWith('/assignments')) {
      return json({ items: [assignment('active', USER), assignment('revoked', OTHER_USER)] })
    }
    if (url.endsWith('/users')) {
      return json([directoryUser(USER, 'ada@example.com'), directoryUser(OTHER_USER, 'ben@example.com')])
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord({ permissions: [] })] })
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`)
  await user.click(await screen.findByRole('tab', { name: 'People' }))
  expect((await screen.findAllByText('ada@example.com')).length).toBeGreaterThan(0)
  expect(screen.getAllByText('ben@example.com').length).toBeGreaterThan(0)
  expect(screen.getAllByText('Active').length).toBeGreaterThan(0)
  expect(screen.getByText('Revoked')).toBeInTheDocument()
  expect(screen.queryByText(MEMBERSHIP)).not.toBeInTheDocument()
  expect(screen.queryByText('Platform Tenant Admin')).not.toBeInTheDocument()
})

it('assigns and revokes a role, and ignores a second click while saving', async () => {
  const user = userEvent.setup()
  let items = [assignment('revoked', OTHER_USER)]
  let releaseAssign: (value: Response) => void = () => undefined
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = methodOf(init ?? {})
    if (url.endsWith('/assignments/remove') && method === 'POST') {
      items = items.map((item) => (item.user_id === USER ? { ...item, status: 'revoked' } : item))
      return json(items.find((item) => item.user_id === USER))
    }
    if (url.endsWith(`/roles/${ROLE}/assignments`) && method === 'POST') {
      return new Promise<Response>((resolve) => {
        releaseAssign = resolve
      })
    }
    if (url.endsWith('/crm-permissions')) {
      return json({ items: CATALOG })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [] })
    }
    if (url.endsWith('/assignments')) {
      return json({ items })
    }
    if (url.endsWith('/users')) {
      return json([directoryUser(), directoryUser(OTHER_USER, 'ben@example.com')])
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord({ permissions: [] })] })
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`)
  await user.click(await screen.findByRole('tab', { name: 'People' }))
  expect((await screen.findAllByText('ben@example.com')).length).toBeGreaterThan(0)
  await user.selectOptions(screen.getByLabelText('Organization member'), USER)
  await user.click(screen.getByRole('button', { name: 'Assign role' }))
  const pending = screen.getByRole('button', { name: 'Assigning role' })
  expect(pending).toBeDisabled()
  await user.click(pending)
  const assignPosts = () =>
    calls().filter((call) => call.url.endsWith(`/roles/${ROLE}/assignments`) && methodOf(call.init) === 'POST')
  expect(assignPosts()).toHaveLength(1)
  items = [assignment('active', USER), assignment('revoked', OTHER_USER)]
  releaseAssign(
    new Response(JSON.stringify(assignment('active', USER)), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
  expect(await screen.findByRole('button', { name: 'Revoke role for ada@example.com' })).toBeInTheDocument()
  expect(screen.getByText('Role assigned.')).toBeInTheDocument()
  const assignCall = assignPosts()[0]
  expect(assignCall?.url).toBe(`${crmApi}/api/v1/tenants/${TENANT}/roles/${ROLE}/assignments`)
  expect(header(assignCall?.init ?? {}, 'X-CSRF-Token')).toBe('csrf-token')
  expect(assignCall?.init.credentials).toBe('include')
  expect(bodyOf(assignCall?.init ?? {})).toEqual({ user_id: USER })
  expect(calls().filter((call) => call.url.endsWith(`/roles/${ROLE}/assignments`) && methodOf(call.init) === 'GET')).toHaveLength(2)
  await user.click(screen.getByRole('button', { name: 'Revoke role for ada@example.com' }))
  await user.click(screen.getByRole('button', { name: 'Confirm revoke for ada@example.com' }))
  expect(await screen.findByText(/Role revoked/)).toBeInTheDocument()
  const revokeCall = calls().find((call) => call.url.endsWith('/assignments/remove'))
  expect(revokeCall?.url).toBe(`${crmApi}/api/v1/tenants/${TENANT}/roles/${ROLE}/assignments/remove`)
  expect(header(revokeCall?.init ?? {}, 'X-CSRF-Token')).toBe('csrf-token')
  expect(bodyOf(revokeCall?.init ?? {})).toEqual({ user_id: USER })
})

it('shows validation errors and server errors', async () => {
  const user = userEvent.setup()
  let denyList = true
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = methodOf(init ?? {})
    if (url.endsWith('/roles') && method === 'GET' && denyList) {
      return json({ error: { code: 'FORBIDDEN', message: 'You do not have permission to perform this action.' } }, 403)
    }
    if (url.endsWith('/roles') && method === 'GET') {
      return json({ error: { code: 'INTERNAL_ERROR', message: 'The platform request could not be completed.' } }, 502)
    }
    if (url.endsWith('/roles') && method === 'POST') {
      return json({ error: { code: 'CONFLICT', message: 'A role with this name already exists in this organization.' } }, 409)
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles`)
  expect(await screen.findByRole('alert')).toHaveTextContent('You do not have permission to perform this action.')
  denyList = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The platform request could not be completed.')
  cleanup()
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = methodOf(init ?? {})
    if (url.endsWith('/roles') && method === 'POST') {
      return json({ error: { code: 'CONFLICT', message: 'A role with this name already exists in this organization.' } }, 409)
    }
    if (url.endsWith('/roles')) {
      return json({ items: [] })
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/new`)
  await user.click(screen.getByRole('button', { name: 'Create role' }))
  expect(screen.getByRole('alert')).toHaveTextContent('Role name is required.')
  expect(calls().some((call) => methodOf(call.init) === 'POST')).toBe(false)
  await user.type(screen.getByLabelText('Role name'), 'Sales desk')
  await user.click(screen.getByRole('button', { name: 'Create role' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('A role with this name already exists in this organization.')
})

it('keeps assignment actions off an inactive role', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/crm-permissions')) {
      return json({ items: [LEADS] })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [LEADS] })
    }
    if (url.endsWith('/assignments')) {
      return json({ items: [assignment('active')] })
    }
    if (url.endsWith('/users')) {
      return json([directoryUser()])
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord({ status: 'inactive' })] })
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`)
  expect((await screen.findAllByText('Inactive')).length).toBeGreaterThan(0)
  await user.click(screen.getByRole('tab', { name: 'People' }))
  expect(await screen.findByText('ada@example.com')).toBeInTheDocument()
  expect(screen.getByText(/cannot be assigned or removed/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Assign role' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Revoke role/ })).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Organization member')).not.toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: 'Permissions' }))
  expect(screen.getByRole('checkbox', { name: /Read leads/ })).toBeDisabled()
  expect(screen.getByText(/permissions cannot be changed/)).toBeInTheDocument()
})

it('does not invent a user directory when the member list is missing', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url === `${platformApi}/api/v1/tenants/${TENANT}/users`) {
      return json({ error: { code: 'RESOURCE_NOT_FOUND', message: 'The requested resource was not found.' } }, 404)
    }
    if (url.endsWith('/crm-permissions')) {
      return json({ items: [] })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [] })
    }
    if (url.endsWith('/assignments')) {
      return json({ items: [assignment('active')] })
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord({ permissions: [] })] })
    }
    return json({}, 500)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`)
  await user.click(await screen.findByRole('tab', { name: 'People' }))
  expect(await screen.findByText(/will not ask for an id/)).toBeInTheDocument()
  expect(screen.getByText(USER)).toBeInTheDocument()
  expect(screen.queryByLabelText('Organization member')).not.toBeInTheDocument()
  expect(screen.queryByRole('textbox', { name: /user id/i })).not.toBeInTheDocument()
  const urls = calls().map((call) => call.url)
  expect(urls.filter((url) => url.startsWith(crmApi) && url.includes('/users'))).toEqual([])
  expect(urls.filter((url) => url.includes('eligible-users') || url.includes('crm-users'))).toEqual([])
  expect(urls.filter((url) => url === `${platformApi}/api/v1/tenants/${TENANT}/users`)).toHaveLength(1)
})

it('does not call assignment APIs without permission to read users', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/crm-permissions')) {
      return json({ items: [] })
    }
    if (url.endsWith(`/roles/${ROLE}/permissions`)) {
      return json({ items: [] })
    }
    if (url.endsWith('/roles')) {
      return json({ items: [roleRecord({ permissions: [] })] })
    }
    return json({ items: [{ user_id: 'hidden-user' }] }, 200)
  })
  renderRoles(`/tenants/${TENANT}/roles/${ROLE}`, false)
  await user.click(await screen.findByRole('tab', { name: 'People' }))
  expect(screen.getByText(/requires permission to read organization users/)).toBeInTheDocument()
  expect(screen.queryByText('hidden-user')).not.toBeInTheDocument()
  expect(calls().some((call) => call.url.includes('/assignments') || call.url.endsWith('/users'))).toBe(false)
})

it('shows CRM roles in the shell only when roles.manage is present', async () => {
  const user = userEvent.setup()
  let allowRoles = false
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json({ id: USER, email: 'admin@example.com' })
    }
    if (url.endsWith('/products/crm/access')) {
      return json({
        tenant_id: TENANT,
        tenant_name: 'Aadi Technology',
        product_key: 'crm',
        product_name: 'CRM',
        available: true,
        features: ['project_management'],
      })
    }
    if (url.endsWith('/configuration')) {
      return json({}, 404)
    }
    if (url.endsWith('/crm-permissions')) {
      return json({ items: [] })
    }
    if (url.includes('/roles')) {
      return json({ items: [roleRecord()] })
    }
    if (url.endsWith('/permissions')) {
      return json(
        allowRoles
          ? ['roles.manage', 'users.read', 'crm.project_management.access']
          : ['crm.project_management.access'],
      )
    }
    return json({}, 500)
  })
  renderShell(`/tenants/${TENANT}/roles`)
  expect(await screen.findByRole('alert')).toHaveTextContent('You do not have permission to perform this action.')
  expect(screen.queryByRole('link', { name: 'CRM roles' })).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Projects' })).toBeInTheDocument()
  expect(calls().some((call) => call.url.includes('/roles'))).toBe(false)
  cleanup()
  allowRoles = true
  renderShell(`/tenants/${TENANT}`)
  await user.click(await screen.findByRole('link', { name: 'CRM roles' }))
  expect(await screen.findByRole('link', { name: /Sales desk/ })).toBeInTheDocument()
  expect(calls().some((call) => call.url === `${crmApi}/api/v1/tenants/${TENANT}/roles`)).toBe(true)
  expect(screen.getByRole('link', { name: 'Projects' })).toBeInTheDocument()
})
