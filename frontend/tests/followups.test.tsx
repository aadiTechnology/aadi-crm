import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { FollowUpQueues, RecordFollowUps } from '../src/features/records/FollowUpsPanel'
import { RecordsPanel } from '../src/features/records/RecordsPanel'
import type { ActivityItem, CrmRecord, FollowUp, Project, ProjectAccess, ProjectMembership } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'
const PROJECT_ID = '33333333-3333-4333-8333-333333333333'
const RECORD_ID = '99999999-9999-4999-8999-999999999999'
const USER_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const VERSION_ID = '88888888-8888-4888-8888-888888888888'

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
    created_by: USER_ID,
    created_at: '2026-10-20T08:00:00.000Z',
    updated_at: '2026-10-20T08:00:00.000Z',
    access: access(),
  }
}

function member(): ProjectMembership {
  return {
    id: '44444444-4444-4444-8444-444444444444',
    tenant_id: TENANT,
    project_id: PROJECT_ID,
    user_id: USER_ID,
    email: 'manager@example.com',
    role: 'project_manager',
    scope_policy: 'project',
    status: 'active',
    created_by: USER_ID,
    updated_by: USER_ID,
    created_at: '2026-10-20T08:00:00.000Z',
    updated_at: '2026-10-20T08:00:00.000Z',
  }
}

function followUp(overrides: Partial<FollowUp> = {}): FollowUp {
  return {
    id: '77777777-7777-4777-8777-777777777777',
    project_id: PROJECT_ID,
    record_id: RECORD_ID,
    task_type: 'call',
    task_type_label: 'Call',
    owner_user_id: USER_ID,
    due_at: '2026-10-20T18:30:00.000000+00:00',
    due_date: '2026-10-21',
    due_time: '00:00',
    timezone: 'Asia/Kolkata',
    status: 'open',
    status_label: 'Open',
    call_status: 'connected',
    call_status_label: 'Connected',
    summary: 'Midnight call',
    outcome: '',
    created_by: USER_ID,
    updated_by: USER_ID,
    created_at: '2026-10-20T08:00:00.000Z',
    updated_at: '2026-10-20T08:00:00.000Z',
    completed_at: null,
    cancelled_at: null,
    public_number: 'N-1-0001',
    display_name: 'North school',
    ...overrides,
  }
}

function activity(id: string, summary: string, occurredAt: string): ActivityItem {
  return {
    id,
    record_id: RECORD_ID,
    follow_up_id: followUp().id,
    actor_id: USER_ID,
    event_type: 'follow_up.created',
    label: 'Follow-up created',
    summary,
    occurred_at: occurredAt,
  }
}

function record(): CrmRecord {
  return {
    id: RECORD_ID,
    project_id: PROJECT_ID,
    form_id: '55555555-5555-4555-8555-555555555555',
    form_version_id: VERSION_ID,
    version_number: 1,
    form_name: 'Site enquiry',
    form_description: '',
    public_number: 'N-1-0001',
    display_name: 'North school',
    source: 'manual',
    source_label: 'Manual',
    created_at: '2026-10-20T10:00:00.000Z',
    updated_at: '2026-10-20T10:00:00.000Z',
    captured_at: '2026-10-20T10:00:00.000Z',
    fields: [
      {
        field_key: 'school_name',
        label: 'School name',
        field_type: 'text',
        required: true,
        help_text: '',
        section_name: 'Contact',
        position: 0,
        max_length: 120,
      },
    ],
    values: { school_name: 'North school' },
    absent_from_draft: [],
    unmapped_values: [],
  }
}

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

function renderFollowUps() {
  return render(
    <MemoryRouter initialEntries={[`/tenants/${TENANT}/records/${PROJECT_ID}/${RECORD_ID}`]}>
      <RecordFollowUps tenantId={TENANT} projectId={PROJECT_ID} recordId={RECORD_ID} readOnly={false} />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  document.cookie = 'aadi_csrf=csrf-token'
})

afterEach(() => {
  cleanup()
})

it('shows the timeline empty state, then an error that can be retried', async () => {
  const user = userEvent.setup()
  let failed = true
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/activities')) {
      if (failed) {
        return json({ error: { message: 'The activity timeline could not be loaded.' } }, 500)
      }
      return json({ items: [], total: 0, limit: 25, offset: 0 })
    }
    if (url.includes('/follow-ups')) {
      return json({ items: [], total: 0, limit: 25, offset: 0 })
    }
    if (url.includes('/members')) {
      return json({ items: [member()], directory_available: true })
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  renderFollowUps()
  expect(await screen.findByRole('alert')).toHaveTextContent('The activity timeline could not be loaded.')
  failed = false
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('No activity has been recorded for this record.')).toBeInTheDocument()
})

it('renders timeline entries newest first and keeps the historical record version', async () => {
  const newer = activity('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'Newest follow-up', '2026-10-21T04:00:00.000Z')
  const older = activity('cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'Older follow-up', '2026-10-20T04:00:00.000Z')
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith(`/projects/${PROJECT_ID}`)) {
      return json(project())
    }
    if (url.endsWith(`/records/${RECORD_ID}`)) {
      return json(record())
    }
    if (url.includes('/activities')) {
      return json({ items: [newer, older], total: 2, limit: 25, offset: 0 })
    }
    if (url.includes('/follow-ups')) {
      return json({ items: [], total: 0, limit: 25, offset: 0 })
    }
    if (url.includes('/members')) {
      return json({ items: [member()], directory_available: true })
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  render(
    <MemoryRouter initialEntries={[`/tenants/${TENANT}/records/${PROJECT_ID}/${RECORD_ID}`]}>
      <Routes>
        <Route path="/tenants/:tenantId/records/:projectId/:recordId" element={<RecordsPanel tenantId={TENANT} />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByRole('heading', { name: 'N-1-0001' })).toBeInTheDocument()
  expect(screen.getByText(/Form version/)).toHaveTextContent(VERSION_ID)
  expect(screen.getByText('School name')).toBeInTheDocument()
  const first = await screen.findByText('Newest follow-up')
  const second = screen.getByText('Older follow-up')
  expect(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getAllByText('By manager@example.com').length).toBeGreaterThan(0)
})

it('creates, edits, and completes a follow-up without sending a tenant id', async () => {
  const user = userEvent.setup()
  let saved = followUp()
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://localhost')
    const method = init?.method ?? 'GET'
    if (url.pathname.includes('/activities')) {
      return json({ items: [], total: 0, limit: 25, offset: 0 })
    }
    if (url.pathname.includes('/members')) {
      return json({ items: [member()], directory_available: true })
    }
    if (url.pathname.endsWith('/follow-ups') && method === 'GET') {
      const created = saved.summary !== 'Midnight call'
      return json({ items: created ? [saved] : [], total: created ? 1 : 0, limit: 25, offset: 0 })
    }
    if (url.pathname.endsWith('/follow-ups') && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as Record<string, unknown>
      expect(body.tenant_id).toBeUndefined()
      expect(body.task_type).toBe('note')
      expect(body.owner_user_id).toBe(USER_ID)
      expect(body.due_date).toBe('2026-10-22')
      expect(body.due_time).toBe('09:30')
      expect(body.call_status).toBeNull()
      saved = followUp({
        task_type: 'note',
        task_type_label: 'Note',
        due_date: '2026-10-22',
        due_time: '09:30',
        summary: 'Send the note',
        call_status: null,
        call_status_label: null,
      })
      return json(saved, 201)
    }
    if (url.pathname.endsWith(`/follow-ups/${saved.id}`) && method === 'PATCH') {
      const body = JSON.parse(String(init?.body)) as { summary: string; expected_updated_at: string }
      expect(body.expected_updated_at).toBe(saved.updated_at)
      saved = { ...saved, summary: body.summary, updated_at: '2026-10-20T09:00:00.000Z' }
      return json(saved)
    }
    if (url.pathname.endsWith('/complete') && method === 'POST') {
      const body = JSON.parse(String(init?.body)) as { outcome: string }
      expect(body.outcome).toBe('Left a message')
      saved = { ...saved, status: 'completed', status_label: 'Completed', outcome: body.outcome }
      return json(saved)
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  renderFollowUps()
  expect(await screen.findByRole('button', { name: 'Add follow-up' })).toBeInTheDocument()
  expect(screen.getByLabelText('Due date')).toHaveAttribute('type', 'date')
  expect(screen.getByLabelText('Due time')).toHaveAttribute('type', 'time')
  await user.selectOptions(screen.getByLabelText('Task type'), 'note')
  await user.selectOptions(screen.getByLabelText('Owner'), USER_ID)
  await user.type(screen.getByLabelText('Due date'), '2026-10-22')
  await user.type(screen.getByLabelText('Due time'), '09:30')
  await user.type(screen.getByLabelText('Discussion summary'), 'Send the note')
  await user.click(screen.getByRole('button', { name: 'Add follow-up' }))
  expect(await screen.findByText('Send the note')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Edit Note' }))
  const editor = screen.getByRole('button', { name: 'Save Note' }).closest('form')
  if (!(editor instanceof HTMLFormElement)) {
    throw new Error('missing editor')
  }
  await user.clear(within(editor).getByLabelText('Discussion summary'))
  await user.type(within(editor).getByLabelText('Discussion summary'), 'Updated note')
  await user.click(within(editor).getByRole('button', { name: 'Save Note' }))
  expect(await screen.findByText('Updated note')).toBeInTheDocument()
  await user.type(screen.getByLabelText('Outcome'), 'Left a message')
  await user.click(screen.getByRole('button', { name: 'Complete Note' }))
  expect(await screen.findByText('Outcome Left a message')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Complete Note' })).not.toBeInTheDocument()
})

it('shows an owner validation error and hides an unauthorized follow-up payload', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/activities')) {
      return json({ error: { message: 'The requested resource was not found.' }, summary: 'Secret note' }, 404)
    }
    if (url.includes('/members')) {
      return json({ items: [member()], directory_available: true })
    }
    if (url.includes('/follow-ups') && method === 'GET') {
      return json({ items: [], total: 0, limit: 25, offset: 0 })
    }
    if (method === 'POST') {
      return json(
        { error: { message: 'Choose an owner.', fields: { owner_user_id: 'Owner must be an active member of this project.' } } },
        422,
      )
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  const user = userEvent.setup()
  renderFollowUps()
  expect(await screen.findByRole('alert')).toHaveTextContent('The requested resource was not found.')
  expect(screen.queryByText('Secret note')).not.toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Task type'), 'note')
  await user.selectOptions(screen.getByLabelText('Owner'), USER_ID)
  await user.type(screen.getByLabelText('Due date'), '2026-10-22')
  await user.type(screen.getByLabelText('Due time'), '09:30')
  await user.click(screen.getByRole('button', { name: 'Add follow-up' }))
  expect(await screen.findByText('Owner must be an active member of this project.')).toBeInTheDocument()
})

it('moves between Overdue, Today, and Upcoming without repeating a follow-up', async () => {
  const user = userEvent.setup()
  const queues: string[] = []
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')
    if (url.pathname.endsWith(`/projects/${PROJECT_ID}`) && !url.pathname.includes('/follow-ups')) {
      return json(project())
    }
    if (url.pathname.endsWith('/members')) {
      return json({ items: [member()], directory_available: true })
    }
    if (url.pathname.endsWith('/follow-ups')) {
      const queue = url.searchParams.get('queue') ?? ''
      queues.push(queue)
      if (queue === 'today') {
        return json({
          items: [followUp()],
          total: 1,
          limit: 25,
          offset: 0,
          queue: 'today',
          timezone: 'Asia/Kolkata',
          window_start: '2026-10-20T18:30:00.000000+00:00',
          window_end: '2026-10-21T18:30:00.000000+00:00',
          owner_user_id: null,
        })
      }
      return json({
        items: [],
        total: 0,
        limit: 25,
        offset: 0,
        queue,
        timezone: 'Asia/Kolkata',
        window_start: '2026-10-20T18:30:00.000000+00:00',
        window_end: '2026-10-21T18:30:00.000000+00:00',
        owner_user_id: url.searchParams.get('owner_user_id'),
      })
    }
    return json({ error: { message: 'Unexpected request' } }, 500)
  })
  render(
    <MemoryRouter initialEntries={[`/tenants/${TENANT}/follow-ups/${PROJECT_ID}?queue=today`]}>
      <Routes>
        <Route path="/tenants/:tenantId/follow-ups/:projectId" element={<FollowUpQueues tenantId={TENANT} />} />
      </Routes>
    </MemoryRouter>,
  )
  expect(await screen.findByRole('link', { name: 'N-1-0001' })).toBeInTheDocument()
  expect(screen.getByText('2026-10-21 00:00')).toBeInTheDocument()
  expect(screen.getAllByText('Today').length).toBeGreaterThan(0)
  await user.click(screen.getByRole('link', { name: 'Upcoming' }))
  expect(await screen.findByText('No follow-ups are upcoming.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'N-1-0001' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('link', { name: 'Overdue' }))
  expect(await screen.findByText('No follow-ups are overdue.')).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Assignee'), USER_ID)
  expect(queues).toContain('today')
  expect(queues).toContain('upcoming')
  expect(queues).toContain('overdue')
})

function asFetch() {
  return fetch as unknown as ReturnType<typeof vi.fn>
}
