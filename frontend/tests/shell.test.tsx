import '@testing-library/jest-dom/vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { CrmShellPage } from '../src/features/shell/CrmShellPage'

const TENANT = '11111111-1111-4111-8111-111111111111'
const OTHER = 'Other Org'

function json(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId" element={<CrmShellPage />} />
        <Route path="/tenants/:tenantId/leads" element={<CrmShellPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

function identity() {
  return { id: 'user-1', email: 'member@example.com', created_at: '', updated_at: '' }
}

function access(available: boolean, tenantId = TENANT) {
  return {
    tenant_id: tenantId,
    tenant_name: 'Aadi Technology',
    product_id: 'product-1',
    product_key: 'crm',
    product_name: 'CRM',
    available,
  }
}

afterEach(() => {
  cleanup()
})

beforeEach(() => {
  vi.unstubAllGlobals()
  vi.stubGlobal('fetch', vi.fn())
})

function asFetch() {
  return fetch as unknown as ReturnType<typeof vi.fn>
}

it('shows a loading status before the session check finishes', () => {
  asFetch().mockReturnValue(new Promise(() => undefined))
  renderAt('/')
  expect(screen.getByRole('status').textContent).toBe('Checking access')
})

it('rejects an empty sign-in without calling the platform', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json({ error: { code: 'UNAUTHORIZED' } }, 401)
    }
    return json({}, 500)
  })
  renderAt('/')
  await screen.findByRole('button', { name: 'Sign in' })
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(screen.getByRole('alert').textContent).toBe('Email is required.')
  expect(asFetch().mock.calls.some((call) => String(call[0]).includes('/auth/login'))).toBe(false)
})

it('shows sign-in failed and does not open organizations', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me') || url.endsWith('/api/v1/auth/login')) {
      return json({ error: { message: OTHER } }, 401)
    }
    return json({}, 500)
  })
  renderAt('/')
  await screen.findByLabelText('Email')
  await user.type(screen.getByLabelText('Email'), 'member@example.com')
  await user.type(screen.getByLabelText('Password'), 'secret-value')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Sign-in failed.')
  expect(screen.queryByText(OTHER)).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Organizations' })).not.toBeInTheDocument()
})

it('shows an empty organization list', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.endsWith('/api/v1/tenants')) {
      return json([])
    }
    return json({}, 500)
  })
  renderAt('/')
  expect(await screen.findByText('No organizations are available for this sign-in.')).toBeInTheDocument()
})

it('hides leads when the product is unavailable', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.endsWith('/products/crm/access')) {
      return json(access(false))
    }
    if (url.endsWith('/permissions')) {
      return json(['crm.lead_management.read'])
    }
    if (url.endsWith('/configuration')) {
      return json({ error: { message: OTHER } }, 403)
    }
    return json({}, 500)
  })
  renderAt(`/tenants/${TENANT}`)
  expect(await screen.findByText('CRM is not open for this organization.')).toBeInTheDocument()
  expect(screen.getByText('Leads is not available for this sign-in.')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Leads' })).not.toBeInTheDocument()
  expect(screen.queryByText(OTHER)).not.toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Aadi Technology')
  expect(document.querySelector('.app')).not.toHaveAttribute('style')
})

it('closes the navigation with Escape and returns focus to the menu button', async () => {
  const user = userEvent.setup()
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.endsWith('/products/crm/access')) {
      return json(access(false))
    }
    if (url.endsWith('/permissions')) {
      return json(['crm.lead_management.read'])
    }
    if (url.endsWith('/configuration')) {
      return json({}, 404)
    }
    return json({}, 500)
  })
  renderAt(`/tenants/${TENANT}`)
  const menu = await screen.findByRole('button', { name: 'Open navigation' })
  await user.click(menu)
  expect(screen.getByRole('button', { name: 'Close navigation' })).toHaveAttribute('aria-expanded', 'true')
  await user.keyboard('{Escape}')
  const closed = screen.getByRole('button', { name: 'Open navigation' })
  expect(closed).toHaveAttribute('aria-expanded', 'false')
  expect(closed).toHaveFocus()
})

it('hides leads when the permission is missing and the stub denies a direct visit', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.endsWith('/products/crm/access')) {
      return json(access(true))
    }
    if (url.endsWith('/permissions')) {
      return json(['users.read'])
    }
    if (url.endsWith('/configuration')) {
      return json({}, 404)
    }
    if (url.includes('/leads')) {
      return json({ error: { message: OTHER }, items: [{ name: 'Hidden lead' }] }, 403)
    }
    return json({}, 500)
  })
  renderAt(`/tenants/${TENANT}/leads`)
  expect(await screen.findByRole('alert')).toHaveTextContent('You do not have permission to perform this action.')
  expect(screen.queryByText('Hidden lead')).not.toBeInTheDocument()
  expect(screen.queryByText(OTHER)).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Leads' })).not.toBeInTheDocument()
})

it('shows leads only after both checks and an empty stub', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.endsWith('/products/crm/access')) {
      return json(access(true))
    }
    if (url.endsWith('/permissions')) {
      return json(['crm.lead_management.read'])
    }
    if (url.endsWith('/configuration')) {
      return json({ profile: { display_name: 'Aadi Studio' }, branding: { primary: '#0f766e' } })
    }
    if (url.includes('/leads')) {
      return json({ module: 'leads', items: [] })
    }
    return json({}, 500)
  })
  renderAt(`/tenants/${TENANT}`)
  expect(await screen.findByRole('link', { name: 'Leads' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Aadi Studio')
  expect(shellStyle().getPropertyValue('--color-primary')).toBe('#0f766e')
})

it('lets branding colors win over brand tokens and keeps an unreadable pair off the shell', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.endsWith('/products/crm/access')) {
      return json(access(true))
    }
    if (url.endsWith('/permissions')) {
      return json(['crm.lead_management.read'])
    }
    if (url.endsWith('/configuration')) {
      return json({
        profile: { display_name: 'North Studio' },
        branding: { primary: '#112233', secondary: '#445566' },
        logo: { url: 'https://cdn.example/logo.png', alt_text: 'North mark' },
        favicon: { url: 'https://cdn.example/favicon.png' },
        brand_tokens: {
          primary_color: '#ABCDEF',
          background_color: '#FFFFFF',
          text_color: '#111827',
        },
      })
    }
    return json({}, 500)
  })
  renderAt(`/tenants/${TENANT}`)
  expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('North Studio')
  expect(screen.getByRole('img', { name: 'North mark' })).toHaveAttribute('src', 'https://cdn.example/logo.png')
  await waitFor(() =>
    expect(document.getElementById('aadi-tenant-favicon')).toHaveAttribute('href', 'https://cdn.example/favicon.png'),
  )
  const style = shellStyle()
  expect(style.getPropertyValue('--color-primary')).toBe('#112233')
  expect(style.getPropertyValue('--color-secondary')).toBe('#445566')
  expect(style.getPropertyValue('--color-bg')).toBe('#FFFFFF')
  expect(style.getPropertyValue('--color-text')).toBe('#111827')
  expect(style.getPropertyValue('--color-primary')).not.toBe('#ABCDEF')
})

it('uses a brand token primary and ignores text that fails on its background', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.endsWith('/products/crm/access')) {
      return json(access(true))
    }
    if (url.endsWith('/permissions')) {
      return json(['crm.lead_management.read'])
    }
    if (url.endsWith('/configuration')) {
      return json({
        brand_tokens: {
          primary_color: '#ABCDEF',
          background_color: '#FFFFFF',
          text_color: '#EEEEEE',
        },
      })
    }
    return json({}, 500)
  })
  renderAt(`/tenants/${TENANT}`)
  expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Aadi Technology')
  const style = shellStyle()
  expect(style.getPropertyValue('--color-primary')).toBe('#ABCDEF')
  expect(style.getPropertyValue('--color-bg')).toBe('')
  expect(style.getPropertyValue('--color-text')).toBe('')
})

function shellStyle(): CSSStyleDeclaration {
  const app = document.querySelector('.app')
  if (!(app instanceof HTMLElement)) {
    throw new Error('missing shell')
  }
  return app.style
}

it('does not render another tenant returned for this url', async () => {
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      return json(identity())
    }
    if (url.includes('/products/crm/access')) {
      return json({ ...access(true, '22222222-2222-4222-8222-222222222222'), tenant_name: OTHER })
    }
    return json({}, 500)
  })
  renderAt(`/tenants/${TENANT}`)
  expect(await screen.findByRole('alert')).toHaveTextContent('The requested resource was not found.')
  expect(screen.queryByText(OTHER)).not.toBeInTheDocument()
})

it('opens the organization list after a successful sign-in', async () => {
  const user = userEvent.setup()
  let sessionReads = 0
  asFetch().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/api/v1/auth/me')) {
      sessionReads += 1
      return sessionReads === 1 ? json({}, 401) : json(identity())
    }
    if (url.endsWith('/api/v1/auth/login')) {
      return json(identity())
    }
    if (url.endsWith('/api/v1/tenants')) {
      return json([{ id: TENANT, name: 'Northwind', status: 'active', created_at: '', updated_at: '' }])
    }
    return json({}, 500)
  })
  renderAt('/')
  await screen.findByLabelText('Email')
  await user.type(screen.getByLabelText('Email'), 'member@example.com')
  await user.type(screen.getByLabelText('Password'), 'correct-horse')
  await user.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(await screen.findByRole('link', { name: 'Northwind' })).toBeInTheDocument()
})

describe('sign-in control', () => {
  it('disables the sign-in button while the request is in flight', async () => {
    const user = userEvent.setup()
    let release: (() => void) | undefined
    asFetch().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/me')) {
        return json({}, 401)
      }
      if (url.endsWith('/api/v1/auth/login')) {
        return new Promise((resolve) => {
          release = () => resolve(json(identity()))
        })
      }
      return json({}, 500)
    })
    renderAt('/')
    await screen.findByLabelText('Email')
    await user.type(screen.getByLabelText('Email'), 'member@example.com')
    await user.type(screen.getByLabelText('Password'), 'secret-value')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Signing in' })).toBeDisabled())
    const loginCalls = asFetch().mock.calls.filter((call) => String(call[0]).includes('/auth/login'))
    expect(loginCalls).toHaveLength(1)
    release?.()
  })
})
