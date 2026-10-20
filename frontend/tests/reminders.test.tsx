import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { RemindersPanel } from '../src/features/reminders/RemindersPanel'
import type { ReminderItem } from '../src/services/platform'

const TENANT = '11111111-1111-4111-8111-111111111111'

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function asFetch(): ReturnType<typeof vi.fn> {
  return globalThis.fetch as ReturnType<typeof vi.fn>
}

function reminder(overrides: Partial<ReminderItem> = {}): ReminderItem {
  return {
    id: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
    kind: 'follow_up_due',
    kind_label: 'Follow-up due',
    channel: 'in_app',
    state: 'sent',
    state_label: 'Delivered in the app',
    due_date: '2026-10-21',
    due_time: '10:00',
    timezone: 'Asia/Kolkata',
    read: false,
    attempt_count: 1,
    last_attempt_at: '2026-10-21T05:00:00.000000+00:00',
    next_retry_at: null,
    last_error: null,
    failure_label: null,
    record_available: true,
    project_id: '33333333-3333-4333-8333-333333333333',
    record_id: '99999999-9999-4999-8999-999999999999',
    follow_up_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
    public_number: 'N-1-0007',
    ...overrides,
  }
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
  document.cookie = 'aadi_csrf=csrf-token'
})

afterEach(() => {
  cleanup()
})

it('shows an empty inbox and hides the operator section when failures are forbidden', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/failures')) {
      return json({ error: { message: 'You do not have permission to perform this action.' } }, 403)
    }
    return json({ items: [], total: 0, timezone: 'Asia/Kolkata' })
  })
  render(
    <MemoryRouter>
      <RemindersPanel tenantId={TENANT} />
    </MemoryRouter>,
  )
  expect(screen.getByRole('status')).toHaveTextContent('Loading reminders')
  expect(await screen.findByText('No reminders')).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Email failures for projects you manage' })).not.toBeInTheDocument()
})

it('opens an authorized record, marks a reminder read, and does not render a customer name', async () => {
  const user = userEvent.setup()
  const item = reminder()
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/failures')) {
      return json({ items: [], total: 0 })
    }
    if (url.endsWith('/read') && init?.method === 'POST') {
      return json({ ...item, read: true })
    }
    return json({
      items: [{ ...item, display_name: 'Hidden family' }],
      total: 1,
      timezone: 'Asia/Kolkata',
    })
  })
  render(
    <MemoryRouter>
      <RemindersPanel tenantId={TENANT} />
    </MemoryRouter>,
  )
  expect(await screen.findByRole('link', { name: 'Open record N-1-0007' })).toHaveAttribute(
    'href',
    `/tenants/${TENANT}/records/33333333-3333-4333-8333-333333333333/99999999-9999-4999-8999-999999999999`,
  )
  expect(screen.queryByText('Hidden family')).not.toBeInTheDocument()
  await user.click(screen.getAllByRole('button', { name: 'Mark as read' })[0])
  expect(await screen.findByText('Read')).toBeInTheDocument()
  const readCall = asFetch().mock.calls.find((call) => String(call[0]).endsWith('/read'))
  expect(readCall?.[1]?.headers.get('X-CSRF-Token')).toBe('csrf-token')
})

it('hides the record link when the reminder is no longer authorized', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/failures')) {
      return json({ error: { message: 'You do not have permission to perform this action.' } }, 403)
    }
    return json({
      items: [
        reminder({
          record_available: false,
          project_id: undefined,
          record_id: undefined,
          public_number: undefined,
        }),
      ],
      total: 1,
      timezone: 'Asia/Kolkata',
    })
  })
  render(
    <MemoryRouter>
      <RemindersPanel tenantId={TENANT} />
    </MemoryRouter>,
  )
  expect(await screen.findByText('You cannot open this record with the current access.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Open record/ })).not.toBeInTheDocument()
})

it('shows a test-adapter email result and a terminal failure the manager can retry', async () => {
  const user = userEvent.setup()
  const failed = reminder({
    id: 'ffffffff-ffff-4fff-8fff-ffffffffffff',
    channel: 'email',
    state: 'failed',
    state_label: 'Stopped',
    last_error: 'provider_temporary',
    failure_label: 'The email attempt failed and can be retried.',
    attempt_count: 3,
    next_retry_at: null,
    recipient_email: 'manager@example.com',
    record_available: false,
    public_number: undefined,
  })
  asFetch().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/failures')) {
      return json({ items: [failed], total: 1 })
    }
    if (url.endsWith('/retry') && init?.method === 'POST') {
      return json({ ...failed, state: 'pending' })
    }
    return json({
      items: [
        reminder({
          id: '12121212-1212-4121-8121-121212121212',
          channel: 'email',
          state: 'recorded',
          state_label: 'Recorded by the test adapter. Not delivered.',
          record_available: false,
        }),
      ],
      total: 1,
      timezone: 'Asia/Kolkata',
    })
  })
  render(
    <MemoryRouter>
      <RemindersPanel tenantId={TENANT} />
    </MemoryRouter>,
  )
  expect(await screen.findByText('Recorded by the test adapter. Not delivered.')).toBeInTheDocument()
  expect(screen.getByText('The email attempt failed and can be retried.')).toBeInTheDocument()
  expect(screen.getByText('Record details are hidden.')).toBeInTheDocument()
  expect(screen.getByText('Directory address manager@example.com')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Retry delivery' }))
  expect(await screen.findByText('The same reminder was queued again. A new reminder was not created.')).toBeInTheDocument()
})

it('shows an error and can retry the inbox load', async () => {
  const user = userEvent.setup()
  let failed = true
  asFetch().mockImplementation(() => {
    if (failed) {
      return json({ error: { message: 'Reminders could not be loaded.' } }, 500)
    }
    return json({ items: [], total: 0, timezone: 'Asia/Kolkata' })
  })
  render(
    <MemoryRouter>
      <RemindersPanel tenantId={TENANT} />
    </MemoryRouter>,
  )
  expect(await screen.findByRole('alert')).toHaveTextContent('Reminders could not be loaded.')
  failed = false
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    if (String(input).endsWith('/failures')) {
      return json({ error: { message: 'You do not have permission to perform this action.' } }, 403)
    }
    return json({ items: [], total: 0, timezone: 'Asia/Kolkata' })
  })
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByText('No reminders')).toBeInTheDocument()
})
