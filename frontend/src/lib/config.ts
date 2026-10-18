const DEFAULT_PLATFORM_API = 'http://localhost:8000'
const DEFAULT_CRM_API = 'http://localhost:8001'
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1'])

export type FrontendConfig = {
  platformApiBaseUrl: string
  crmApiBaseUrl: string
}

function isHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

/** Keep a development API on the same loopback host as the page. */
export function alignDevelopmentLoopbackApiUrl(apiBaseUrl: string, pageHostname: string | undefined): string {
  if (!pageHostname || !LOOPBACK_HOSTS.has(pageHostname)) {
    return apiBaseUrl
  }
  const parsed = new URL(apiBaseUrl)
  if (!LOOPBACK_HOSTS.has(parsed.hostname) || parsed.hostname === pageHostname) {
    return apiBaseUrl
  }
  parsed.hostname = pageHostname
  const next = parsed.toString()
  if (parsed.pathname === '/' && next.endsWith('/')) {
    return next.slice(0, -1)
  }
  return next
}

export function resolveFrontendConfig(
  env: { VITE_API_BASE_URL?: string; VITE_CRM_API_BASE_URL?: string },
  pageHostname?: string,
): FrontendConfig {
  const platformApiBaseUrl = (env.VITE_API_BASE_URL ?? DEFAULT_PLATFORM_API).trim()
  const crmApiBaseUrl = (env.VITE_CRM_API_BASE_URL ?? DEFAULT_CRM_API).trim()
  if (!isHttpUrl(platformApiBaseUrl) || platformApiBaseUrl.includes('@')) {
    throw new Error('invalid API base URL')
  }
  if (!isHttpUrl(crmApiBaseUrl) || crmApiBaseUrl.includes('@')) {
    throw new Error('invalid API base URL')
  }
  return {
    platformApiBaseUrl: alignDevelopmentLoopbackApiUrl(platformApiBaseUrl, pageHostname),
    crmApiBaseUrl: alignDevelopmentLoopbackApiUrl(crmApiBaseUrl, pageHostname),
  }
}

export function readFrontendConfig(): FrontendConfig {
  const pageHostname = typeof window === 'undefined' ? undefined : window.location.hostname
  return resolveFrontendConfig(import.meta.env, pageHostname)
}
