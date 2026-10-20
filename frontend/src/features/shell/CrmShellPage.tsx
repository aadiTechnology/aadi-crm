import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { FormsPanel } from '@/features/forms/FormsPanel'
import { ProjectsPanel } from '@/features/projects/ProjectsPanel'
import {
  accessMessage,
  ApiError,
  canManageProjects,
  getLeads,
  getPermissions,
  getProductAccess,
  LEADS_PERMISSION,
  listTenants,
  login,
  logout,
  me,
  readBranding,
  type Identity,
  type LeadsStub,
  type ProductAccess,
  type ShellBranding,
  type TenantSummary,
} from '@/services/platform'

type LeadsView =
  | { status: 'hidden' }
  | { status: 'loading' }
  | { status: 'ready'; leads: LeadsStub }
  | { status: 'denied'; message: string }
  | { status: 'error'; message: string }

type Screen =
  | { status: 'loading' }
  | { status: 'login'; formError: string | null; submitting: boolean }
  | { status: 'tenants'; email: string; tenants: TenantSummary[]; signingOut: boolean }
  | { status: 'unavailable'; email: string; message: string; signingOut: boolean }
  | {
      status: 'shell'
      email: string
      access: ProductAccess
      branding: ShellBranding | null
      canOpenLeads: boolean
      canOpenProjects: boolean
      leads: LeadsView
      signingOut: boolean
    }

const NOT_FOUND = 'The requested resource was not found.'

function failureMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return accessMessage(error.status)
  }
  return 'The request could not be completed.'
}

function leadsAllowed(access: ProductAccess, permissions: string[]): boolean {
  return access.available && permissions.includes(LEADS_PERMISSION)
}

function projectsAllowed(access: ProductAccess, permissions: string[]): boolean {
  return access.available && canManageProjects(permissions)
}

export function CrmShellPage() {
  const { tenantId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const onLeads = location.pathname.endsWith('/leads')
  const onForms = location.pathname.includes('/forms')
  const onProjects = location.pathname.includes('/projects') && !onForms
  const [sessionVersion, setSessionVersion] = useState(0)
  const [screen, setScreen] = useState<Screen>({ status: 'loading' })
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  useEffect(() => {
    let cancelled = false

    async function load() {
      setScreen({ status: 'loading' })
      let identity: Identity
      try {
        identity = await me()
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && error.status === 401) {
            setScreen({ status: 'login', formError: null, submitting: false })
          } else {
            setScreen({ status: 'unavailable', email: '', message: failureMessage(error), signingOut: false })
          }
        }
        return
      }

      if (!tenantId) {
        try {
          const tenants = await listTenants()
          if (!cancelled) {
            setScreen({ status: 'tenants', email: identity.email, tenants, signingOut: false })
          }
        } catch (error) {
          if (!cancelled) {
            setScreen({
              status: 'unavailable',
              email: identity.email,
              message: failureMessage(error),
              signingOut: false,
            })
          }
        }
        return
      }

      try {
        const access = await getProductAccess(tenantId)
        if (access.tenant_id !== tenantId || access.product_key !== 'crm') {
          if (!cancelled) {
            setScreen({ status: 'unavailable', email: identity.email, message: NOT_FOUND, signingOut: false })
          }
          return
        }
        const permissions = await getPermissions(tenantId)
        const branding = await readBranding(tenantId)
        const canOpenLeads = leadsAllowed(access, permissions)
        const canOpenProjects = projectsAllowed(access, permissions)
        let leads: LeadsView = { status: 'hidden' }
        if (onLeads) {
          try {
            const stub = await getLeads(tenantId)
            leads = { status: 'ready', leads: stub }
          } catch (error) {
            if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
              leads = { status: 'denied', message: accessMessage(error.status) }
            } else {
              leads = { status: 'error', message: failureMessage(error) }
            }
          }
        }
        if (!cancelled) {
          setScreen({
            status: 'shell',
            email: identity.email,
            access,
            branding,
            canOpenLeads,
            canOpenProjects,
            leads,
            signingOut: false,
          })
        }
      } catch (error) {
        if (!cancelled) {
          const message = failureMessage(error)
          if (error instanceof ApiError && error.status === 401) {
            setScreen({ status: 'login', formError: message, submitting: false })
          } else {
            setScreen({ status: 'unavailable', email: identity.email, message, signingOut: false })
          }
        }
      }
    }

    void load()
    return () => {
      cancelled = true
    }
  }, [onLeads, sessionVersion, tenantId])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = email.trim()
    if (!normalized) {
      setScreen({ status: 'login', formError: 'Email is required.', submitting: false })
      return
    }
    if (!normalized.includes('@')) {
      setScreen({ status: 'login', formError: 'A valid email is required.', submitting: false })
      return
    }
    if (!password) {
      setScreen({ status: 'login', formError: 'Password is required.', submitting: false })
      return
    }
    setScreen({ status: 'login', formError: null, submitting: true })
    try {
      await login(normalized, password)
      setPassword('')
      setSessionVersion((value) => value + 1)
      if (tenantId) {
        navigate(`/tenants/${tenantId}`)
      }
    } catch (error) {
      setScreen({
        status: 'login',
        formError: error instanceof ApiError && error.status === 401 ? 'Sign-in failed.' : failureMessage(error),
        submitting: false,
      })
    }
  }

  async function onSignOut() {
    setScreen((current) =>
      current.status === 'login' || current.status === 'loading' ? current : { ...current, signingOut: true },
    )
    try {
      await logout()
    } catch {
      setScreen((current) =>
        current.status === 'login' || current.status === 'loading'
          ? current
          : { ...current, signingOut: false },
      )
      return
    }
    setScreen({ status: 'login', formError: null, submitting: false })
  }

  const headingStyle =
    screen.status === 'shell' && screen.branding?.primary
      ? { color: screen.branding.primary }
      : undefined

  return (
    <main className="shell stack">
      <header className="stack">
        <p className="muted">Aadi CRM</p>
        <h1 style={headingStyle}>
          {screen.status === 'shell'
            ? screen.branding?.displayName || screen.access.tenant_name
            : 'CRM'}
        </h1>
        {screen.status === 'shell' ? (
          <p>
            Organization <strong>{screen.access.tenant_name}</strong>
          </p>
        ) : null}
        {screen.status === 'shell' || screen.status === 'unavailable' ? (
          <Link to="/">Organizations</Link>
        ) : null}
        {screen.status === 'shell' || screen.status === 'tenants' || screen.status === 'unavailable' ? (
          <p className="muted">{screen.email}</p>
        ) : null}
      </header>

      {screen.status === 'loading' ? (
        <p role="status">Checking access</p>
      ) : null}

      {screen.status === 'login' ? (
        <form className="stack" onSubmit={(event) => void onSubmit(event)} noValidate>
          <label>
            Email
            <input
              name="email"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {screen.formError ? (
            <p role="alert" className="alert alert-error">
              {screen.formError}
            </p>
          ) : null}
          <button type="submit" disabled={screen.submitting}>
            {screen.submitting ? 'Signing in' : 'Sign in'}
          </button>
        </form>
      ) : null}

      {screen.status === 'tenants' ? (
        <section className="stack" aria-labelledby="org-heading">
          <h2 id="org-heading">Organizations</h2>
          {screen.tenants.length === 0 ? (
            <p>No organizations are available for this sign-in.</p>
          ) : (
            <ul className="tenant-list">
              {screen.tenants.map((tenant) => (
                <li key={tenant.id}>
                  <Link to={`/tenants/${tenant.id}`}>{tenant.name}</Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {screen.status === 'unavailable' ? (
        <p role="alert" className="alert alert-error">
          {screen.message}
        </p>
      ) : null}

      {screen.status === 'shell' ? (
        <section className="stack" aria-labelledby="crm-heading">
          <h2 id="crm-heading">{screen.access.product_name}</h2>
          {screen.access.available ? (
            <p className="alert alert-ok" role="status">
              {screen.access.product_name} is available in this organization.
            </p>
          ) : (
            <p className="alert alert-error" role="status">
              CRM is not open for this organization.
            </p>
          )}
          {screen.canOpenLeads ? (
            <Link to={`/tenants/${screen.access.tenant_id}/leads`}>Leads</Link>
          ) : (
            <p>Leads is not available for this sign-in.</p>
          )}
          {screen.canOpenProjects ? (
            <Link to={`/tenants/${screen.access.tenant_id}/projects`}>Projects</Link>
          ) : (
            <p>Projects is not available for this sign-in.</p>
          )}
          {screen.canOpenProjects ? (
            <Link to={`/tenants/${screen.access.tenant_id}/forms`}>Forms</Link>
          ) : (
            <p>Forms is not available for this sign-in.</p>
          )}
          {onProjects && screen.canOpenProjects ? <ProjectsPanel tenantId={screen.access.tenant_id} /> : null}
          {onForms && screen.canOpenProjects ? <FormsPanel tenantId={screen.access.tenant_id} /> : null}
          {onProjects && !screen.canOpenProjects ? (
            <p role="alert" className="alert alert-error">
              You do not have permission to perform this action.
            </p>
          ) : null}
          {onForms && !screen.canOpenProjects ? (
            <p role="alert" className="alert alert-error">
              You do not have permission to perform this action.
            </p>
          ) : null}
          {onLeads && screen.leads.status === 'ready' ? (
            <section aria-labelledby="leads-heading">
              <h2 id="leads-heading">Leads</h2>
              {screen.leads.leads.items.length === 0 ? <p>No leads are open in this shell.</p> : null}
            </section>
          ) : null}
          {onLeads && (screen.leads.status === 'denied' || screen.leads.status === 'error') ? (
            <p role="alert" className="alert alert-error">
              {screen.leads.message}
            </p>
          ) : null}
        </section>
      ) : null}

      {screen.status !== 'login' && screen.status !== 'loading' ? (
        <button type="button" onClick={() => void onSignOut()} disabled={screen.signingOut}>
          Sign out
        </button>
      ) : null}
    </main>
  )
}
