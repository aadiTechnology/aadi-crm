import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { FormsPanel } from '@/features/forms/FormsPanel'
import { ProjectsPanel } from '@/features/projects/ProjectsPanel'
import { RecordsPanel } from '@/features/records/RecordsPanel'
import { LoadingSkeleton, NavIcon } from '@/ui/chrome'
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
  brandingCssProperties,
  type Identity,
  type LeadsStub,
  type ProductAccess,
  type ShellBranding,
  type TenantSummary,
} from '@/services/platform'

const FAVICON_ID = 'aadi-tenant-favicon'

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

function workspacePage(pathname: string): string {
  if (pathname.includes('/records')) {
    return 'Records'
  }
  if (pathname.includes('/forms')) {
    return 'Forms'
  }
  if (pathname.includes('/projects')) {
    return 'Projects'
  }
  if (pathname.endsWith('/leads')) {
    return 'Leads'
  }
  return 'Overview'
}

export function CrmShellPage() {
  const { tenantId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const onLeads = location.pathname.endsWith('/leads')
  const onForms = location.pathname.includes('/forms')
  const onRecords = location.pathname.includes('/records')
  const onProjects = location.pathname.includes('/projects') && !onForms && !onRecords
  const [sessionVersion, setSessionVersion] = useState(0)
  const [screen, setScreen] = useState<Screen>({ status: 'loading' })
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [navOpen, setNavOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    setNavOpen(false)
  }, [location.pathname])

  const faviconUrl = screen.status === 'shell' ? screen.branding?.faviconUrl : null
  useEffect(() => {
    const existing = document.getElementById(FAVICON_ID)
    if (!faviconUrl) {
      existing?.remove()
      return
    }
    const link = existing instanceof HTMLLinkElement ? existing : document.createElement('link')
    link.id = FAVICON_ID
    link.rel = 'icon'
    link.href = faviconUrl
    if (!existing) {
      document.head.append(link)
    }
    return () => {
      link.remove()
    }
  }, [faviconUrl])

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

  const shellBranding = screen.status === 'shell' ? screen.branding : null
  const brandProperties = brandingCssProperties(shellBranding)
  const shellStyle =
    Object.keys(brandProperties).length > 0 ? (brandProperties as CSSProperties) : undefined
  const headingStyle = shellBranding?.primary ? { color: shellBranding.primary } : undefined
  const title =
    screen.status === 'shell' ? screen.branding?.displayName || screen.access.tenant_name : 'CRM'
  const pageName = screen.status === 'tenants' ? 'Organizations' : workspacePage(location.pathname)
  const signedIn = screen.status === 'shell' || screen.status === 'tenants' || screen.status === 'unavailable'

  if (screen.status === 'loading') {
    return (
      <main className="auth">
        <section className="auth-card">
          <p className="eyebrow">Aadi CRM</p>
          <p role="status">Checking access</p>
          <LoadingSkeleton />
        </section>
      </main>
    )
  }

  if (screen.status === 'login') {
    return (
      <main className="auth">
        <form className="auth-card" onSubmit={(event) => void onSubmit(event)} noValidate>
          <div>
            <p className="eyebrow">Aadi CRM</p>
            <h1>CRM</h1>
          </div>
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
      </main>
    )
  }

  const tenantIdForNav = screen.status === 'shell' ? screen.access.tenant_id : ''

  return (
    <div className={navOpen ? 'app nav-open' : collapsed ? 'app is-collapsed' : 'app'} style={shellStyle}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar" id="workspace-nav">
        <div className="brand">
          {shellBranding?.logoUrl ? (
            <img className="brand-logo" src={shellBranding.logoUrl} alt={shellBranding.logoAlt ?? ''} />
          ) : (
            <span className="brand-mark" aria-hidden="true">
              A
            </span>
          )}
          <span className="brand-text">Aadi CRM</span>
        </div>
        <nav aria-label="Workspace">
          <Link className="nav-link" to="/" aria-current={screen.status === 'tenants' ? 'page' : undefined}>
            <NavIcon name="org" />
            <span className="nav-label">Organizations</span>
          </Link>
          {screen.status === 'shell' ? (
            <Link
              className="nav-link"
              to={`/tenants/${tenantIdForNav}`}
              aria-current={!onLeads && !onProjects && !onForms && !onRecords ? 'page' : undefined}
            >
              <NavIcon name="overview" />
              <span className="nav-label">Overview</span>
            </Link>
          ) : null}
          {screen.status === 'shell' && screen.canOpenLeads ? (
            <Link
              className="nav-link"
              to={`/tenants/${tenantIdForNav}/leads`}
              aria-current={onLeads ? 'page' : undefined}
            >
              <NavIcon name="leads" />
              <span className="nav-label">Leads</span>
            </Link>
          ) : null}
          {screen.status === 'shell' && !screen.canOpenLeads ? (
            <p className="nav-note">Leads is not available for this sign-in.</p>
          ) : null}
          {screen.status === 'shell' && screen.canOpenProjects ? (
            <Link
              className="nav-link"
              to={`/tenants/${tenantIdForNav}/projects`}
              aria-current={onProjects ? 'page' : undefined}
            >
              <NavIcon name="projects" />
              <span className="nav-label">Projects</span>
            </Link>
          ) : null}
          {screen.status === 'shell' && !screen.canOpenProjects ? (
            <p className="nav-note">Projects is not available for this sign-in.</p>
          ) : null}
          {screen.status === 'shell' && screen.canOpenProjects ? (
            <Link
              className="nav-link"
              to={`/tenants/${tenantIdForNav}/forms`}
              aria-current={onForms ? 'page' : undefined}
            >
              <NavIcon name="forms" />
              <span className="nav-label">Forms</span>
            </Link>
          ) : null}
          {screen.status === 'shell' && !screen.canOpenProjects ? (
            <p className="nav-note">Forms is not available for this sign-in.</p>
          ) : null}
          {screen.status === 'shell' && screen.canOpenProjects ? (
            <Link
              className="nav-link"
              to={`/tenants/${tenantIdForNav}/records`}
              aria-current={onRecords ? 'page' : undefined}
            >
              <NavIcon name="records" />
              <span className="nav-label">Records</span>
            </Link>
          ) : null}
          {screen.status === 'shell' && !screen.canOpenProjects ? (
            <p className="nav-note">Records is not available for this sign-in.</p>
          ) : null}
        </nav>
        <button
          type="button"
          className="button-ghost sidebar-toggle"
          aria-pressed={collapsed}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          onClick={() => setCollapsed((current) => !current)}
        >
          <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
            <path
              d={collapsed ? 'M9 6l6 6-6 6' : 'M15 6l-6 6 6 6'}
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span aria-hidden="true">{collapsed ? 'Expand sidebar' : 'Collapse sidebar'}</span>
        </button>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <button
            type="button"
            className="button-ghost menu-button"
            aria-expanded={navOpen}
            aria-controls="workspace-nav"
            onClick={() => setNavOpen((current) => !current)}
          >
            {navOpen ? 'Close navigation' : 'Open navigation'}
          </button>
          <div className="topbar-title">
            <p className="eyebrow">{pageName}</p>
            <h1 style={headingStyle}>{title}</h1>
            {screen.status === 'shell' ? (
              <p className="context-line">
                Organization <strong>{screen.access.tenant_name}</strong>
              </p>
            ) : null}
          </div>
          {signedIn ? (
            <div className="account">
              {screen.email ? <p className="account-email">{screen.email}</p> : null}
              <button type="button" className="button-ghost" onClick={() => void onSignOut()} disabled={screen.signingOut}>
                Sign out
              </button>
            </div>
          ) : null}
        </header>
        <main id="main" className="content stack">
          {screen.status === 'tenants' ? (
            <section className="stack" aria-labelledby="org-heading">
              <div className="page-header">
                <div>
                  <h2 id="org-heading">Organizations</h2>
                  <p className="page-intro">Choose the organization to open.</p>
                </div>
              </div>
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
            <section className="stack" aria-label={screen.access.product_name}>
              {!onProjects && !onForms && !onLeads && !onRecords ? <h2 id="crm-heading">Overview</h2> : null}
              {screen.access.available ? (
                <p className="alert alert-ok" role="status">
                  {screen.access.product_name} is available in this organization.
                </p>
              ) : (
                <p className="alert alert-error" role="status">
                  CRM is not open for this organization.
                </p>
              )}
              {onProjects && screen.canOpenProjects ? <ProjectsPanel tenantId={screen.access.tenant_id} /> : null}
              {onForms && screen.canOpenProjects ? <FormsPanel tenantId={screen.access.tenant_id} /> : null}
              {onRecords && screen.canOpenProjects ? <RecordsPanel tenantId={screen.access.tenant_id} /> : null}
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
              {onRecords && !screen.canOpenProjects ? (
                <p role="alert" className="alert alert-error">
                  You do not have permission to perform this action.
                </p>
              ) : null}
              {onLeads && screen.leads.status === 'ready' ? (
                <section className="stack" aria-labelledby="leads-heading">
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
        </main>
      </div>
    </div>
  )
}
