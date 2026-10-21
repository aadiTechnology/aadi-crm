import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { AuditPanel } from '../src/features/audit/AuditPanel'

const TENANT = '11111111-1111-4111-8111-111111111111'

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

it('shows audit metadata fields and hides values that are not part of the row', async () => {
  asFetch().mockResolvedValue(
    json({
      items: [
        {
          id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1',
          occurred_at: '2026-10-21T04:00:00+00:00',
          action: 'project.settings.update',
          resource_type: 'project',
          resource_id: '33333333-3333-4333-8333-333333333333',
          summary: 'Project settings were updated.',
          outcome: 'success',
          actor_user_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
          metadata: { password: 'super-secret-audit-value' },
        },
      ],
      limit: 50,
      source: 'platform',
    }),
  )
  render(<AuditPanel tenantId={TENANT} />)
  expect(await screen.findByText('Project settings were updated.')).toBeInTheDocument()
  expect(screen.getByText('project.settings.update')).toBeInTheDocument()
  expect(screen.queryByText('super-secret-audit-value')).not.toBeInTheDocument()
  expect(screen.queryByText(/metadata/i)).not.toBeInTheDocument()
})

it('shows an empty audit log', async () => {
  asFetch().mockResolvedValue(json({ items: [], limit: 50, source: 'platform' }))
  render(<AuditPanel tenantId={TENANT} />)
  expect(await screen.findByText('No audit events')).toBeInTheDocument()
  expect(screen.getByText(/not copied into this log/)).toBeInTheDocument()
})

it('shows permission and unavailable states', async () => {
  const user = userEvent.setup()
  let denied = true
  asFetch().mockImplementation(() => {
    if (denied) {
      return json({ error: { message: 'You do not have permission to perform this action.' } }, 403)
    }
    return json({ error: { message: 'The audit log is unavailable.' } }, 502)
  })
  const { rerender } = render(<AuditPanel tenantId={TENANT} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('You do not have permission to perform this action.')
  denied = false
  rerender(<AuditPanel tenantId={`${TENANT}`} />)
  await user.click(screen.getByRole('button', { name: 'Retry' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('The audit log is unavailable.')
})
