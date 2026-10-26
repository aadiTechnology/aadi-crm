import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ProjectsPanel } from '../src/features/projects/ProjectsPanel'
import { CrmShellPage } from '../src/features/shell/CrmShellPage'
import type { Project, ProjectAccess } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'
const PROJECT_ID = '33333333-3333-4333-8333-333333333333'
const MEMBERSHIP_ID = '44444444-4444-4444-8444-444444444444'
const OTHER_USER = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

function managerAccess(overrides: Partial<ProjectAccess> = {}): ProjectAccess {
  return {
    role: 'project_manager',
    scope_policy: 'project',
    can_manage_project: true,
    can_manage_members: true,
    can_manage_forms: true,
    can_access_records: true,
    record_scope: 'project',
    ...overrides,
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

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: PROJECT_ID,
    tenant_id: TENANT,
    code: 'N-1',
    name: 'North yard',
    description: 'Recording yard',
    status: 'active',
    created_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    created_at: '2026-10-19T08:00:00.000Z',
    updated_at: '2026-10-19T08:00:00.000Z',
    access: managerAccess(),
    ...overrides,
  }
}

function renderPanel(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tenants/:tenantId/projects" element={<ProjectsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/projects/new" element={<ProjectsPanel tenantId={TENANT} />} />
        <Route path="/tenants/:tenantId/projects/:projectId" element={<ProjectsPanel tenantId={TENANT} />} />
      </Routes>
    </MemoryRouter>,
  )
}

function renderShell(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/tenants/:tenantId" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/leads" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/projects" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/projects/new" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/projects/:projectId" element={<CrmShellPage />} />
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

describe('project screens', () => {
  it('shows a loading state and then an empty organization', async () => {
    let release: ((value: Promise<Response>) => void) | undefined
    asFetch().mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }),
    )
    renderPanel(`/tenants/${TENANT}/projects`)
    expect(screen.getByRole('status').textContent).toBe('Loading projects')
    release?.(json({ items: [] }))
    expect(await screen.findByText('No projects are available for this sign-in.')).toBeInTheDocument()
  })

  it('keeps an empty create form off the API', async () => {
    const user = userEvent.setup()
    asFetch().mockImplementation(() => json({ items: [] }))
    renderPanel(`/tenants/${TENANT}/projects/new`)
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(screen.getByRole('alert').textContent).toBe('Project code is required.')
    expect(asFetch()).not.toHaveBeenCalled()
  })

  it('creates, edits, searches, and archives a project', async () => {
    const user = userEvent.setup()
    const stored = new Map<string, Project>()
    asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      const method = init?.method ?? 'GET'
      if (method === 'POST' && url.pathname.endsWith('/projects')) {
        const body = JSON.parse(String(init?.body)) as { code: string; name: string; description: string }
        const headers = new Headers(init?.headers)
        if (headers.get('X-CSRF-Token') !== 'csrf-token') {
          return json({ error: { code: 'UNAUTHORIZED', message: 'Authentication is required.' } }, 401)
        }
        if ([...stored.values()].some((item) => item.code.toLowerCase() === body.code.toLowerCase())) {
          return json(
            {
              error: {
                code: 'CONFLICT',
                message: 'A project with this code already exists in this organization.',
              },
            },
            409,
          )
        }
        const created = project({
          id: PROJECT_ID,
          code: body.code,
          name: body.name,
          description: body.description,
        })
        stored.set(created.id, created)
        return json(created, 201)
      }
      if (method === 'PATCH') {
        const current = stored.get(PROJECT_ID)
        if (!current) {
          return json({ error: { message: 'The requested resource was not found.' } }, 404)
        }
        const body = JSON.parse(String(init?.body)) as { name: string; description: string }
        const updated = { ...current, name: body.name, description: body.description }
        stored.set(PROJECT_ID, updated)
        return json(updated)
      }
      if (url.pathname.endsWith('/members') && method === 'GET') {
        return json({ items: [], directory_available: true })
      }
      if (url.pathname.endsWith('/eligible-users')) {
        return json({ items: [] })
      }
      if (method === 'POST' && url.pathname.endsWith('/archive')) {
        const current = stored.get(PROJECT_ID)
        if (!current) {
          return json({ error: { message: 'The requested resource was not found.' } }, 404)
        }
        const archived = { ...current, status: 'archived' as const }
        stored.set(PROJECT_ID, archived)
        return json(archived)
      }
      if (url.pathname.endsWith(`/projects/${PROJECT_ID}`)) {
        const current = stored.get(PROJECT_ID)
        return current
          ? json(current)
          : json({ error: { message: 'The requested resource was not found.' } }, 404)
      }
      const q = (url.searchParams.get('q') ?? '').toLowerCase()
      const status = url.searchParams.get('status') ?? ''
      const items = [...stored.values()].filter((item) => {
        const haystack = `${item.code} ${item.name} ${item.description}`.toLowerCase()
        return (!q || haystack.includes(q)) && (!status || item.status === status)
      })
      return json({ items })
    })

    renderPanel(`/tenants/${TENANT}/projects`)
    expect(await screen.findByText('No projects are available for this sign-in.')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'New project' }))
    await user.type(screen.getByLabelText('Project code'), 'N-1')
    await user.type(screen.getByLabelText('Project name'), 'North yard')
    await user.type(screen.getByLabelText('Description'), 'Recording yard')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(await screen.findByRole('heading', { name: 'North yard' })).toBeInTheDocument()
    expect(screen.getByText('N-1')).toBeInTheDocument()
    expect(screen.getByText(/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save project' })).toBeEnabled()

    await user.clear(screen.getByLabelText('Project name'))
    await user.type(screen.getByLabelText('Project name'), 'North gate')
    await user.clear(screen.getByLabelText('Description'))
    await user.type(screen.getByLabelText('Description'), 'Updated yard')
    await user.click(screen.getByRole('button', { name: 'Save project' }))
    expect(await screen.findByRole('heading', { name: 'North gate' })).toBeInTheDocument()
    expect(screen.getByLabelText('Description')).toHaveValue('Updated yard')

    await user.click(screen.getByRole('link', { name: 'Back to projects' }))
    expect(await screen.findByRole('link', { name: /North gate/ })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Search'), 'gate')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByRole('link', { name: /North gate/ })).toBeInTheDocument()
    await user.clear(screen.getByLabelText('Search'))
    await user.type(screen.getByLabelText('Search'), 'missing-yard')
    await user.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText('No projects match this search.')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Search'))
    await user.click(screen.getByRole('button', { name: 'Search' }))
    await user.click(await screen.findByRole('link', { name: /North gate/ }))
    await user.click(await screen.findByRole('button', { name: 'Archive project' }))
    expect(await screen.findByText('This project is archived.')).toBeInTheDocument()
    expect(screen.getByText('Archived')).toBeInTheDocument()
  })

  it('shows a duplicate-code error from the API', async () => {
    const user = userEvent.setup()
    asFetch().mockImplementation(() =>
      json(
        {
          error: {
            code: 'CONFLICT',
            message: 'A project with this code already exists in this organization.',
          },
        },
        409,
      ),
    )
    renderPanel(`/tenants/${TENANT}/projects/new`)
    await user.type(screen.getByLabelText('Project code'), 'N-1')
    await user.type(screen.getByLabelText('Project name'), 'North yard')
    await user.click(screen.getByRole('button', { name: 'Create project' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'A project with this code already exists in this organization.',
    )
  })

  it('shows a list error without project data', async () => {
    asFetch().mockImplementation(() =>
      json({ error: { message: 'The request could not be completed.' }, items: [{ name: 'Hidden project' }] }, 500),
    )
    renderPanel(`/tenants/${TENANT}/projects`)
    expect(await screen.findByRole('alert')).toHaveTextContent('The request could not be completed.')
    expect(screen.queryByText('Hidden project')).not.toBeInTheDocument()
  })
})

describe('shell project entry', () => {
  it('hides projects when the caller only has platform keys', async () => {
    asFetch().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/me')) {
        return json({ id: 'user-1', email: 'member@example.com', created_at: '', updated_at: '' })
      }
      if (url.endsWith('/products/crm/access')) {
        return json({
          tenant_id: TENANT,
          tenant_name: 'Aadi Technology',
          product_key: 'crm',
          product_name: 'CRM',
          available: true,
          features: ['lead_management', 'project_management', 'records'],
        })
      }
      if (url.endsWith('/permissions')) {
        return json(['users.read'])
      }
      if (url.endsWith('/configuration')) {
        return json({}, 403)
      }
      if (url.includes('/projects')) {
        return json({ error: { message: 'Hidden project' }, items: [{ name: 'Hidden project' }] }, 403)
      }
      return json({}, 500)
    })
    renderShell(`/tenants/${TENANT}/projects`)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'You do not have permission to perform this action.',
    )
    expect(screen.getByText('Projects is not available for this sign-in.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Projects' })).not.toBeInTheDocument()
    expect(screen.queryByText('Hidden project')).not.toBeInTheDocument()
  })

  it('opens projects from the shell for project access and hides them for lead read', async () => {
    asFetch().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/me')) {
        return json({ id: 'user-1', email: 'member@example.com', created_at: '', updated_at: '' })
      }
      if (url.endsWith('/products/crm/access')) {
        return json({
          tenant_id: TENANT,
          tenant_name: 'Aadi Technology',
          product_key: 'crm',
          product_name: 'CRM',
          available: true,
          features: ['lead_management', 'project_management', 'records'],
        })
      }
      if (url.endsWith('/permissions')) {
        return json(['crm.lead_management.read'])
      }
      if (url.endsWith('/configuration')) {
        return json({}, 404)
      }
      if (url.includes('/projects')) {
        return json({ items: [{ name: 'Hidden project' }] })
      }
      return json({}, 500)
    })
    renderShell(`/tenants/${TENANT}/projects`)
    expect(await screen.findByText('Projects is not available for this sign-in.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Projects' })).not.toBeInTheDocument()
    expect(screen.queryByText('Hidden project')).not.toBeInTheDocument()

    asFetch().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/me')) {
        return json({ id: 'user-1', email: 'member@example.com', created_at: '', updated_at: '' })
      }
      if (url.endsWith('/products/crm/access')) {
        return json({
          tenant_id: TENANT,
          tenant_name: 'Aadi Technology',
          product_key: 'crm',
          product_name: 'CRM',
          available: true,
          features: ['lead_management', 'project_management', 'records'],
        })
      }
      if (url.endsWith('/permissions')) {
        return json(['crm.project_management.access'])
      }
      if (url.endsWith('/configuration')) {
        return json({}, 404)
      }
      if (url.includes('/projects')) {
        return json({ items: [] })
      }
      return json({}, 500)
    })
    renderShell(`/tenants/${TENANT}`)
    await userClickProjects()
    expect(await screen.findByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(screen.getByText('No projects are available for this sign-in.')).toBeInTheDocument()
  })
})

describe('project membership screens', () => {
  it('adds an organization member and shows the assigned role', async () => {
    const user = userEvent.setup()
    let added = false
    asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      const method = init?.method ?? 'GET'
      if (url.pathname.endsWith('/eligible-users')) {
        return json({ items: added ? [] : [{ id: OTHER_USER, email: 'member@example.com' }] })
      }
      if (method === 'POST' && url.pathname.endsWith('/members')) {
        added = true
        return json(
          {
            id: MEMBERSHIP_ID,
            user_id: OTHER_USER,
            email: 'member@example.com',
            role: 'project_member',
            scope_policy: 'assigned',
            status: 'active',
          },
          201,
        )
      }
      if (url.pathname.endsWith('/members')) {
        const items = [
          {
            id: '55555555-5555-4555-8555-555555555555',
            user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
            email: 'manager@example.com',
            role: 'project_manager',
            scope_policy: 'project',
            status: 'active',
          },
        ]
        if (added) {
          items.push({
            id: MEMBERSHIP_ID,
            user_id: OTHER_USER,
            email: 'member@example.com',
            role: 'project_member',
            scope_policy: 'assigned',
            status: 'active',
          })
        }
        return json({ items, directory_available: true })
      }
      return json(project())
    })
    renderPanel(`/tenants/${TENANT}/projects/${PROJECT_ID}`)
    expect(await screen.findByRole('button', { name: 'Remove manager@example.com' })).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Organization member'), OTHER_USER)
    await user.selectOptions(screen.getByLabelText('Project role'), 'project_member')
    await user.click(screen.getByRole('button', { name: 'Add member' }))
    expect(await screen.findByRole('button', { name: 'Remove member@example.com' })).toBeInTheDocument()
    expect(screen.getAllByText('Project member').length).toBeGreaterThan(0)
  })

  it('keeps an empty member choice off the API', async () => {
    const user = userEvent.setup()
    asFetch().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname.endsWith('/eligible-users')) {
        return json({ items: [{ id: OTHER_USER, email: 'member@example.com' }] })
      }
      if (url.pathname.endsWith('/members')) {
        return json({ items: [], directory_available: true })
      }
      return json(project())
    })
    renderPanel(`/tenants/${TENANT}/projects/${PROJECT_ID}`)
    await user.click(await screen.findByRole('button', { name: 'Add member' }))
    expect(screen.getByRole('alert').textContent).toBe('Choose an organization member.')
    expect(asFetch().mock.calls.some((call) => String(call[1]?.method) === 'POST')).toBe(false)
  })

  it('hides membership management and project edits for a project member', async () => {
    asFetch().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(String(input), 'http://localhost')
      if (url.pathname.endsWith('/members')) {
        return json({
          items: [
            {
              id: MEMBERSHIP_ID,
              user_id: OTHER_USER,
              email: 'member@example.com',
              role: 'project_member',
              scope_policy: 'assigned',
              status: 'active',
            },
          ],
          directory_available: false,
        })
      }
      return json(
        project({
          access: managerAccess({
            role: 'project_member',
            scope_policy: 'assigned',
            can_manage_project: false,
            can_manage_members: false,
            can_manage_forms: false,
            record_scope: 'assigned',
          }),
        }),
      )
    })
    renderPanel(`/tenants/${TENANT}/projects/${PROJECT_ID}`)
    expect(await screen.findByText('member@example.com')).toBeInTheDocument()
    expect(screen.getAllByText('Assigned records').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Save project' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Archive project' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add member' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Remove / })).not.toBeInTheDocument()
  })

  it('shows the organization lookup error and a removal error', async () => {
    const user = userEvent.setup()
    asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), 'http://localhost')
      const method = init?.method ?? 'GET'
      if (url.pathname.endsWith('/eligible-users')) {
        return json(
          { error: { message: 'You cannot look up organization members with this sign-in.' } },
          403,
        )
      }
      if (method === 'POST' && url.pathname.endsWith('/remove')) {
        return json({ error: { message: 'This project needs an active project manager.' } }, 409)
      }
      if (url.pathname.endsWith('/members')) {
        return json({
          items: [
            {
              id: MEMBERSHIP_ID,
              user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
              email: 'manager@example.com',
              role: 'project_manager',
              scope_policy: 'project',
              status: 'active',
            },
          ],
          directory_available: false,
        })
      }
      return json(project())
    })
    renderPanel(`/tenants/${TENANT}/projects/${PROJECT_ID}`)
    expect(
      await screen.findByText('You cannot look up organization members with this sign-in.'),
    ).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove manager@example.com' }))
    expect(await screen.findByText('This project needs an active project manager.')).toBeInTheDocument()
  })
})

async function userClickProjects() {
  const user = userEvent.setup()
  await user.click(await screen.findByRole('link', { name: 'Projects' }))
}
