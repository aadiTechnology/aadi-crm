import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { ReportingPanel } from '../src/features/reporting/ReportingPanel'
import type { Project, ProjectKpis } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'
const PROJECT_ID = '33333333-3333-4333-8333-333333333333'

function project(): Project {
  return {
    id: PROJECT_ID,
    tenant_id: TENANT,
    code: 'N-1',
    name: 'North yard',
    description: '',
    status: 'active',
    created_by: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    created_at: '2026-10-21T00:00:00+00:00',
    updated_at: '2026-10-21T00:00:00+00:00',
    access: {
      role: 'project_manager',
      scope_policy: 'project',
      can_manage_project: true,
      can_manage_members: true,
      can_manage_forms: true,
      can_access_records: true,
      record_scope: 'project',
    },
  }
}

function report(overrides: Partial<ProjectKpis> = {}): ProjectKpis {
  return {
    follow_up_timezone: 'Asia/Kolkata',
    record_date_boundary: 'utc_calendar_day',
    window_start: '2026-10-20T18:30:00.000000+00:00',
    window_end: '2026-10-21T18:30:00.000000+00:00',
    record_period: { created_from: '2026-10-21', created_to: '2026-10-21', applied: true },
    active_records: 2,
    records_created: 1,
    records_by_form: [{ form_id: '55555555-5555-4555-8555-555555555555', form_name: 'Site enquiry', count: 2 }],
    records_by_status: [{ value: 'new', label: 'New', count: 2 }],
    follow_ups: {
      overdue: 1,
      today: 0,
      upcoming: 3,
      completed: 1,
      by_owner: [],
      by_due_date: [{ queue: 'overdue', due_date: '2026-10-20', count: 1 }],
    },
    omitted: ['trends', 'targets'],
    ...overrides,
  }
}

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function asFetch(): ReturnType<typeof vi.fn> {
  return vi.mocked(fetch)
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function renderProject() {
  render(
    <MemoryRouter initialEntries={[`/tenants/${TENANT}/kpis/${PROJECT_ID}`]}>
      <Routes>
        <Route path="/tenants/:tenantId/kpis/:projectId" element={<ReportingPanel tenantId={TENANT} />} />
      </Routes>
    </MemoryRouter>,
  )
}

it('shows KPI counts and drill-down links that use the same period', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/members')) {
      return json({ items: [], directory_available: true })
    }
    if (url.includes('/kpis')) {
      return json(report())
    }
    if (url.includes('/projects/')) {
      return json(project())
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  renderProject()
  expect(await screen.findByRole('heading', { name: 'North yard' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'View active records' })).toHaveAttribute(
    'href',
    `/tenants/${TENANT}/records/${PROJECT_ID}?from=kpis`,
  )
  expect(screen.getByRole('link', { name: 'View records created in this period' }).getAttribute('href')).toContain(
    'created_from=',
  )
  expect(screen.getByRole('link', { name: 'View overdue follow-ups' })).toHaveAttribute(
    'href',
    `/tenants/${TENANT}/follow-ups/${PROJECT_ID}?queue=overdue&from=kpis`,
  )
  expect(screen.getByRole('link', { name: 'View Site enquiry' })).toHaveAttribute(
    'href',
    `/tenants/${TENANT}/records/${PROJECT_ID}?form_id=55555555-5555-4555-8555-555555555555&from=kpis`,
  )
  expect(screen.getByText('2026-10-20')).toBeInTheDocument()
  expect(screen.getByText(/published form field Status/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'View New' })).toHaveAttribute(
    'href',
    `/tenants/${TENANT}/records/${PROJECT_ID}?status=new&status_label=New&from=kpis`,
  )
})

it('shows an empty project and a completed list that reports the same count', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/completed-follow-ups')) {
      return json({
        items: [
          {
            id: '77777777-7777-4777-8777-777777777777',
            record_id: '99999999-9999-4999-8999-999999999999',
            public_number: 'N-1-0001',
            display_name: 'North school',
            task_type: 'call',
            task_type_label: 'Call',
            owner_user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
            completed_at: '2026-10-21T04:00:00.000000+00:00',
            due_date: '2026-10-21',
            due_time: '10:00',
          },
        ],
        total: 1,
        limit: 25,
        offset: 0,
        status: 'completed',
      })
    }
    if (url.includes('/members')) {
      return json({ items: [], directory_available: true })
    }
    if (url.includes('/kpis')) {
      return json(report({
        records_by_form: [],
        records_by_status: [],
        follow_ups: { ...report().follow_ups, by_due_date: [], by_owner: [] },
      }))
    }
    if (url.includes('/projects/')) {
      return json(project())
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  renderProject()
  expect(await screen.findByText('No active records.')).toBeInTheDocument()
  expect(screen.getByText('No records have a pipeline status.')).toBeInTheDocument()
  expect(screen.getAllByText('No open follow-ups in these queues.')).toHaveLength(2)
  await user.click(screen.getByRole('button', { name: 'View completed follow-ups' }))
  expect(await screen.findByText('The list has 1 completed follow-ups. The KPI count is 1.')).toBeInTheDocument()
  expect(screen.getByText('North school')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Back to KPI overview' }))
  expect(screen.queryByText('North school')).not.toBeInTheDocument()
})

it('shows an error and retries the KPI request', async () => {
  const user = userEvent.setup()
  let failed = true
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/members')) {
      return json({ items: [], directory_available: true })
    }
    if (url.includes('/kpis')) {
      if (failed) {
        return json({ error: { message: 'The project KPIs could not be loaded.' } }, 500)
      }
      return json(report())
    }
    if (url.includes('/projects/')) {
      return json(project())
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  renderProject()
  expect(await screen.findByRole('alert')).toHaveTextContent('The project KPIs could not be loaded.')
  failed = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByRole('link', { name: 'View active records' })).toBeInTheDocument()
})
