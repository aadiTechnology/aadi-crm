import { readFrontendConfig } from '@/lib/config'

export const CSRF_COOKIE_NAME = 'aadi_csrf'
export const CSRF_HEADER_NAME = 'X-CSRF-Token'
export const LEADS_PERMISSION = 'crm.lead_management.read'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super(`Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
  }
}

export type Identity = {
  id: string
  email: string
}

export type TenantSummary = {
  id: string
  name: string
  status: string
}

export type ProductAccess = {
  tenant_id: string
  tenant_name: string
  product_key: string
  product_name: string
  available: boolean
}

export type ShellBranding = {
  displayName: string | null
  primary: string | null
}

export type LeadsStub = {
  module: string
  items: unknown[]
}

export function accessMessage(status: number): string {
  if (status === 401) {
    return 'Authentication is required.'
  }
  if (status === 403) {
    return 'You do not have permission to perform this action.'
  }
  if (status === 404) {
    return 'The requested resource was not found.'
  }
  if (status === 422) {
    return 'Request validation failed.'
  }
  return 'The request could not be completed.'
}

export function readCsrfCookie(cookieSource = typeof document === 'undefined' ? '' : document.cookie): string | null {
  for (const part of cookieSource.split(';')) {
    const trimmed = part.trim()
    const separator = trimmed.indexOf('=')
    if (separator <= 0) {
      continue
    }
    if (trimmed.slice(0, separator) === CSRF_COOKIE_NAME) {
      return decodeURIComponent(trimmed.slice(separator + 1))
    }
  }
  return null
}

async function request<T>(baseUrl: string, path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${baseUrl.replace(/\/+$/, '')}${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (!response.ok) {
    throw new ApiError(response.status)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return (await response.json()) as T
}

function platformUrl(): string {
  return readFrontendConfig().platformApiBaseUrl
}

function crmUrl(): string {
  return readFrontendConfig().crmApiBaseUrl
}

export function login(email: string, password: string): Promise<Identity> {
  return request<Identity>(platformUrl(), '/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function me(): Promise<Identity> {
  return request<Identity>(platformUrl(), '/api/v1/auth/me')
}

export function logout(): Promise<void> {
  const headers = new Headers()
  headers.set(CSRF_HEADER_NAME, readCsrfCookie() ?? '')
  return request<void>(platformUrl(), '/api/v1/auth/logout', { method: 'POST', headers })
}

export function listTenants(): Promise<TenantSummary[]> {
  return request<TenantSummary[]>(platformUrl(), '/api/v1/tenants')
}

export function getProductAccess(tenantId: string): Promise<ProductAccess> {
  return request<ProductAccess>(platformUrl(), `/api/v1/tenants/${tenantId}/products/crm/access`)
}

export function getPermissions(tenantId: string): Promise<string[]> {
  return request<string[]>(platformUrl(), `/api/v1/tenants/${tenantId}/permissions`)
}

export async function readBranding(tenantId: string): Promise<ShellBranding | null> {
  try {
    const document = await request<{
      profile?: { display_name?: string }
      branding?: { primary?: string }
    }>(platformUrl(), `/api/v1/tenants/${tenantId}/configuration`)
    const primary = document.branding?.primary
    return {
      displayName: document.profile?.display_name ?? null,
      primary: typeof primary === 'string' && /^#[0-9A-Fa-f]{6}$/.test(primary) ? primary : null,
    }
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return null
    }
    throw error
  }
}

export function getLeads(tenantId: string): Promise<LeadsStub> {
  return request<LeadsStub>(crmUrl(), `/api/v1/shell/tenants/${tenantId}/leads`)
}
