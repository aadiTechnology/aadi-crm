import { readFrontendConfig } from '@/lib/config'

export const CSRF_COOKIE_NAME = 'aadi_csrf'
export const CSRF_HEADER_NAME = 'X-CSRF-Token'
export const LEADS_PERMISSION = 'crm.lead_management.read'
export const PROJECT_ACCESS_PERMISSION = 'crm.project_management.access'
export const RECORDS_ACCESS_PERMISSION = 'crm.records.access'
export const PROJECT_MANAGE_PERMISSION = 'crm.project_management.manage'
export const AUDIT_PERMISSION = 'audit.read'
export const FEATURE_LEADS = 'lead_management'
export const FEATURE_PROJECTS = 'project_management'
export const FEATURE_RECORDS = 'records'

export class ApiError extends Error {
  readonly status: number
  readonly fields: Record<string, string>

  constructor(status: number, message?: string, fields?: Record<string, string>) {
    super(message ?? `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.fields = fields ?? {}
  }
}

export function canOpenProjects(permissions: string[]): boolean {
  return (
    permissions.includes(PROJECT_MANAGE_PERMISSION) || permissions.includes(PROJECT_ACCESS_PERMISSION)
  )
}

export function canOpenRecords(permissions: string[]): boolean {
  return (
    permissions.includes(PROJECT_MANAGE_PERMISSION) || permissions.includes(RECORDS_ACCESS_PERMISSION)
  )
}

export function canOpenAudit(permissions: string[]): boolean {
  return permissions.includes(AUDIT_PERMISSION)
}

export function featureEntitled(access: ProductAccess, key: string): boolean {
  return access.available && access.features.includes(key)
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
  features: string[]
}

export type ShellBranding = {
  displayName: string | null
  primary: string | null
  secondary: string | null
  background: string | null
  surface: string | null
  text: string | null
  muted: string | null
  border: string | null
  logoUrl: string | null
  logoAlt: string | null
  faviconUrl: string | null
}

export type LeadsStub = {
  module: string
  items: unknown[]
}

export type ProjectRole = 'project_manager' | 'project_member'

export type ProjectAccess = {
  role: ProjectRole | null
  scope_policy: 'project' | 'assigned' | null
  can_manage_project: boolean
  can_manage_members: boolean
  can_manage_forms: boolean
  can_access_records: boolean
  record_scope: 'project' | 'assigned' | null
}

export type Project = {
  id: string
  tenant_id: string
  code: string
  name: string
  description: string
  status: 'active' | 'archived'
  created_by: string | null
  created_at: string
  updated_at: string
  access: ProjectAccess
}

export type ProjectMembership = {
  id: string
  tenant_id: string
  project_id: string
  user_id: string
  email: string | null
  role: ProjectRole
  scope_policy: 'project' | 'assigned'
  status: 'active' | 'removed'
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
}

export type EligibleProjectUser = {
  id: string
  email: string
}

export type ProjectInput = {
  code: string
  name: string
  description: string
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
    let message = accessMessage(response.status)
    let fields: Record<string, string> = {}
    try {
      const body = (await response.json()) as { error?: { message?: string; fields?: unknown } }
      if (typeof body.error?.message === 'string' && body.error.message.trim()) {
        message = body.error.message
      }
      fields = readErrorFields(body.error?.fields)
    } catch {
      // Keep the status message when the body is empty or not JSON.
    }
    throw new ApiError(response.status, message, fields)
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

const BRAND_HEX = /^#[0-9A-Fa-f]{6}$/
const PLATFORM_TEXT = '#3D4458'
const PLATFORM_BACKGROUND = '#F7F8FB'

type ConfigurationDocument = {
  profile?: { display_name?: unknown }
  branding?: { primary?: unknown; secondary?: unknown }
  logo?: { url?: unknown; alt_text?: unknown }
  favicon?: { url?: unknown }
  brand_tokens?: {
    primary_color?: unknown
    secondary_color?: unknown
    background_color?: unknown
    surface_color?: unknown
    text_color?: unknown
    muted_text_color?: unknown
    border_color?: unknown
  }
}

function brandColor(value: unknown): string | null {
  return typeof value === 'string' && BRAND_HEX.test(value) ? value : null
}

function httpUrl(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  if (!trimmed || trimmed.length > 2048 || /\s/.test(trimmed)) {
    return null
  }
  try {
    const url = new URL(trimmed)
    if ((url.protocol === 'http:' || url.protocol === 'https:') && url.hostname) {
      return trimmed
    }
  } catch {
    return null
  }
  return null
}

function relativeLuminance(hex: string): number {
  const channels = [hex.slice(1, 3), hex.slice(3, 5), hex.slice(5, 7)].map((channel) => {
    const value = Number.parseInt(channel, 16) / 255
    return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * (channels[0] ?? 0) + 0.7152 * (channels[1] ?? 0) + 0.0722 * (channels[2] ?? 0)
}

function contrastRatio(first: string, second: string): number {
  const lighter = Math.max(relativeLuminance(first), relativeLuminance(second))
  const darker = Math.min(relativeLuminance(first), relativeLuminance(second))
  return (lighter + 0.05) / (darker + 0.05)
}

function readablePair(background: string, text: string): boolean {
  return contrastRatio(background, text) >= 4.5
}

export function readableOnColor(background: string): string {
  const light = '#FFFFFF'
  const dark = '#1A1A1A'
  return contrastRatio(background, light) >= contrastRatio(background, dark) ? light : dark
}

function mixColor(hex: string, toward: string, weight: number): string {
  const channel = (source: string, index: number) => Number.parseInt(source.slice(1 + index * 2, 3 + index * 2), 16)
  const parts = [0, 1, 2].map((index) => {
    const value = Math.round(channel(hex, index) * weight + channel(toward, index) * (1 - weight))
    return Math.max(0, Math.min(255, value)).toString(16).padStart(2, '0')
  })
  return `#${parts.join('')}`
}

/**
 * Maps one tenant configuration document onto the CRM shell.
 * Color precedence matches the Control Plane: branding.primary wins over
 * brand_tokens.primary_color, and branding.secondary wins over secondary_color.
 * Surface colors come only from brand_tokens, and text is applied only when
 * it stays readable on the paired background.
 */
export function brandingFromConfiguration(document: unknown): ShellBranding {
  const source = document && typeof document === 'object' ? (document as ConfigurationDocument) : {}
  const tokens = source.brand_tokens
  const primary = brandColor(source.branding?.primary) ?? brandColor(tokens?.primary_color)
  const secondary = brandColor(source.branding?.secondary) ?? brandColor(tokens?.secondary_color)
  const background = brandColor(tokens?.background_color)
  const text = brandColor(tokens?.text_color)
  const surface = brandColor(tokens?.surface_color)
  const muted = brandColor(tokens?.muted_text_color)
  const border = brandColor(tokens?.border_color)
  const textApplied = Boolean(background && text && readablePair(background, text))
  const textOnSurface = textApplied && text ? text : PLATFORM_TEXT
  const pageBackground = textApplied && background ? background : PLATFORM_BACKGROUND
  const displayName = source.profile?.display_name
  const alt = source.logo?.alt_text
  return {
    displayName: typeof displayName === 'string' && displayName.trim() ? displayName.trim() : null,
    primary,
    secondary,
    background: textApplied ? background : null,
    surface: surface && readablePair(surface, textOnSurface) ? surface : null,
    text: textApplied ? text : null,
    muted: muted && readablePair(pageBackground, muted) ? muted : null,
    border,
    logoUrl: httpUrl(source.logo?.url),
    logoAlt: typeof alt === 'string' ? alt.trim() : null,
    faviconUrl: httpUrl(source.favicon?.url),
  }
}

export function brandingCssProperties(branding: ShellBranding | null): Record<string, string> {
  if (!branding) {
    return {}
  }
  const style: Record<string, string> = {}
  if (branding.primary) {
    style['--color-primary'] = branding.primary
    style['--color-primary-hover'] = mixColor(branding.primary, '#000000', 0.88)
    style['--color-primary-soft'] = mixColor(branding.primary, '#ffffff', 0.12)
    style['--color-on-primary'] = readableOnColor(branding.primary)
    style['--color-nav-border'] = mixColor(branding.primary, '#ffffff', 0.28)
  }
  if (branding.secondary) {
    style['--color-secondary'] = branding.secondary
  }
  if (branding.background) {
    style['--color-bg'] = branding.background
  }
  if (branding.surface) {
    style['--color-surface'] = branding.surface
  }
  if (branding.text) {
    style['--color-text'] = branding.text
  }
  if (branding.muted) {
    style['--color-muted'] = branding.muted
  }
  if (branding.border) {
    style['--color-border'] = branding.border
  }
  return style
}

export async function readBranding(tenantId: string): Promise<ShellBranding | null> {
  try {
    const document = await request<unknown>(platformUrl(), `/api/v1/tenants/${tenantId}/configuration`)
    return brandingFromConfiguration(document)
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

function projectPath(tenantId: string, projectId?: string): string {
  const base = `/api/v1/tenants/${tenantId}/projects`
  return projectId ? `${base}/${projectId}` : base
}

function readErrorFields(value: unknown): Record<string, string> {
  if (!value || typeof value !== 'object') {
    return {}
  }
  const fields: Record<string, string> = {}
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === 'string') {
      fields[key] = item
    }
  }
  return fields
}

function mutationHeaders(): Headers {
  const headers = new Headers()
  headers.set(CSRF_HEADER_NAME, readCsrfCookie() ?? '')
  return headers
}

export function listProjects(
  tenantId: string,
  search: { q: string; status: string },
): Promise<{ items: Project[] }> {
  const params = new URLSearchParams()
  if (search.q.trim()) {
    params.set('q', search.q.trim())
  }
  if (search.status) {
    params.set('status', search.status)
  }
  const query = params.toString()
  const path = query ? `${projectPath(tenantId)}?${query}` : projectPath(tenantId)
  return request<{ items: Project[] }>(crmUrl(), path)
}

export function createProject(tenantId: string, input: ProjectInput): Promise<Project> {
  return request<Project>(crmUrl(), projectPath(tenantId), {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function getProject(tenantId: string, projectId: string): Promise<Project> {
  return request<Project>(crmUrl(), projectPath(tenantId, projectId))
}

export function updateProject(
  tenantId: string,
  projectId: string,
  input: { name: string; description: string },
): Promise<Project> {
  return request<Project>(crmUrl(), projectPath(tenantId, projectId), {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function archiveProject(tenantId: string, projectId: string): Promise<Project> {
  return request<Project>(crmUrl(), `${projectPath(tenantId, projectId)}/archive`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export function listProjectMembers(
  tenantId: string,
  projectId: string,
): Promise<{ items: ProjectMembership[]; directory_available: boolean }> {
  return request(crmUrl(), `${projectPath(tenantId, projectId)}/members`)
}

export function listEligibleProjectUsers(
  tenantId: string,
  projectId: string,
): Promise<{ items: EligibleProjectUser[] }> {
  return request(crmUrl(), `${projectPath(tenantId, projectId)}/eligible-users`)
}

export function addProjectMember(
  tenantId: string,
  projectId: string,
  input: { user_id: string; role: ProjectRole },
): Promise<ProjectMembership> {
  return request(crmUrl(), `${projectPath(tenantId, projectId)}/members`, {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function updateProjectMemberRole(
  tenantId: string,
  projectId: string,
  membershipId: string,
  role: ProjectRole,
): Promise<ProjectMembership> {
  return request(crmUrl(), `${projectPath(tenantId, projectId)}/members/${membershipId}`, {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify({ role }),
  })
}

export function removeProjectMember(
  tenantId: string,
  projectId: string,
  membershipId: string,
): Promise<ProjectMembership> {
  return request(crmUrl(), `${projectPath(tenantId, projectId)}/members/${membershipId}/remove`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export type FormFieldType =
  | 'text'
  | 'long_text'
  | 'number'
  | 'mobile'
  | 'email'
  | 'url'
  | 'date'
  | 'time'
  | 'dropdown'
  | 'multi_select'
  | 'radio'
  | 'checkbox'
  | 'currency'
  | 'file'
  | 'auto_number'

export type FormOption = {
  value: string
  label: string
}

export type FormField = {
  id: string
  field_key: string
  label: string
  field_type: FormFieldType
  required: boolean
  help_text: string
  section_name: string
  position: number
  default_value?: string | number | boolean | null
  max_length?: number
  min_value?: number
  max_value?: number
  options?: FormOption[]
  currency_code?: string
  max_size_mb?: number
  extensions?: string[]
  prefix?: string
  pad_width?: number
}

export type RenderField = Omit<FormField, 'id'> & { id?: string }

export type FormDefinition = {
  id: string
  tenant_id: string
  project_id: string
  name: string
  description: string
  status: 'draft'
  created_by: string | null
  updated_by: string | null
  created_at: string
  updated_at: string
  current_published_version_id?: string | null
  current_published_version_number?: number | null
  fields: FormField[]
}

export type FormPreview = {
  form_id: string
  name: string
  description: string
  source: 'draft'
  fields: RenderField[]
}

export type FormVersion = {
  id: string
  tenant_id: string
  project_id: string
  form_id: string
  version_number: number
  status: 'current' | 'published'
  current: boolean
  published_by: string
  published_at: string
  name: string
  description: string
  fields: RenderField[]
}

export type FormFieldInput = {
  field_key?: string
  label: string
  field_type: FormFieldType
  required: boolean
  help_text?: string
  section_name?: string
  default_value?: string | number | boolean | null
  max_length?: number
  min_value?: number
  max_value?: number
  options?: FormOption[]
  currency_code?: string
  max_size_mb?: number
  extensions?: string[]
  prefix?: string
  pad_width?: number
}

function formCollectionPath(tenantId: string, projectId: string): string {
  return `${projectPath(tenantId, projectId)}/forms`
}

export function listForms(tenantId: string, projectId: string): Promise<{ items: FormDefinition[] }> {
  return request(crmUrl(), formCollectionPath(tenantId, projectId))
}

export function createForm(
  tenantId: string,
  projectId: string,
  input: { name: string; description: string },
): Promise<FormDefinition> {
  return request(crmUrl(), formCollectionPath(tenantId, projectId), {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function getForm(tenantId: string, projectId: string, formId: string): Promise<FormDefinition> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}`)
}

export function updateForm(
  tenantId: string,
  projectId: string,
  formId: string,
  input: { name: string; description: string },
): Promise<FormDefinition> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}`, {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function addFormField(
  tenantId: string,
  projectId: string,
  formId: string,
  input: FormFieldInput,
): Promise<FormDefinition> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/fields`, {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function updateFormField(
  tenantId: string,
  projectId: string,
  formId: string,
  fieldId: string,
  input: FormFieldInput,
): Promise<FormDefinition> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/fields/${fieldId}`, {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function reorderFormFields(
  tenantId: string,
  projectId: string,
  formId: string,
  fieldIds: string[],
): Promise<FormDefinition> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/fields/reorder`, {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify({ field_ids: fieldIds }),
  })
}

export function removeFormField(
  tenantId: string,
  projectId: string,
  formId: string,
  fieldId: string,
): Promise<FormDefinition> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/fields/${fieldId}/remove`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export function previewForm(tenantId: string, projectId: string, formId: string): Promise<FormPreview> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/preview`)
}

export function listFormVersions(
  tenantId: string,
  projectId: string,
  formId: string,
): Promise<{ items: FormVersion[] }> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/versions`)
}

export function publishForm(tenantId: string, projectId: string, formId: string): Promise<FormVersion> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/versions`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export function getFormVersion(
  tenantId: string,
  projectId: string,
  formId: string,
  versionId: string,
): Promise<FormVersion> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/versions/${versionId}`)
}

export function replaceDraftFromPublished(
  tenantId: string,
  projectId: string,
  formId: string,
): Promise<FormDefinition> {
  return request(crmUrl(), `${formCollectionPath(tenantId, projectId)}/${formId}/draft`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export type RecordSummaryValue = {
  label: string
  value: string
}

export type RecordListItem = {
  id: string
  public_number: string
  form_id: string
  form_name: string
  form_version_id: string
  version_number: number
  display_name: string
  source: string
  source_label: string
  created_at: string
  updated_at: string
  summary: RecordSummaryValue[]
}

export type RecordPage = {
  items: RecordListItem[]
  total: number
  limit: number
  offset: number
}

export type RecordValue = string | number | boolean | string[] | null

export type CrmRecord = {
  id: string
  project_id: string
  form_id: string
  form_version_id: string
  version_number: number
  form_name: string
  form_description: string
  public_number: string
  display_name: string
  source: string
  source_label: string
  assignee_user_id: string | null
  created_at: string
  updated_at: string
  captured_at: string
  fields: RenderField[]
  values: Record<string, RecordValue>
  absent_from_draft: { field_key: string; label: string }[]
  unmapped_values: { field_key: string; value: RecordValue }[]
}

export type RecordQuery = {
  q?: string
  formId?: string
  source?: string
  createdFrom?: string
  createdTo?: string
  sort?: 'created_at' | 'updated_at' | 'public_number'
  direction?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

function recordPath(tenantId: string, projectId: string, recordId?: string): string {
  const base = `${projectPath(tenantId, projectId)}/records`
  return recordId ? `${base}/${recordId}` : base
}

export function listRecords(tenantId: string, projectId: string, query: RecordQuery = {}): Promise<RecordPage> {
  const params = new URLSearchParams()
  if (query.q) {
    params.set('q', query.q)
  }
  if (query.formId) {
    params.set('form_id', query.formId)
  }
  if (query.source) {
    params.set('source', query.source)
  }
  if (query.createdFrom) {
    params.set('created_from', query.createdFrom)
  }
  if (query.createdTo) {
    params.set('created_to', query.createdTo)
  }
  if (query.sort) {
    params.set('sort', query.sort)
  }
  if (query.direction) {
    params.set('direction', query.direction)
  }
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit))
  }
  if (query.offset !== undefined) {
    params.set('offset', String(query.offset))
  }
  const search = params.toString()
  return request(crmUrl(), `${recordPath(tenantId, projectId)}${search ? `?${search}` : ''}`)
}

export function createRecord(
  tenantId: string,
  projectId: string,
  input: { form_id: string; source: string; values: Record<string, RecordValue> },
): Promise<CrmRecord> {
  return request(crmUrl(), recordPath(tenantId, projectId), {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function getRecord(tenantId: string, projectId: string, recordId: string): Promise<CrmRecord> {
  return request(crmUrl(), recordPath(tenantId, projectId, recordId))
}

export function updateRecord(
  tenantId: string,
  projectId: string,
  recordId: string,
  input: { expected_updated_at: string; values: Record<string, RecordValue> },
): Promise<CrmRecord> {
  return request(crmUrl(), recordPath(tenantId, projectId, recordId), {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function archiveRecord(
  tenantId: string,
  projectId: string,
  recordId: string,
  expectedUpdatedAt: string,
): Promise<{ id: string; archived: boolean }> {
  return request(crmUrl(), `${recordPath(tenantId, projectId, recordId)}/archive`, {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify({ expected_updated_at: expectedUpdatedAt }),
  })
}

export type FollowUpStatus = 'open' | 'completed' | 'cancelled'
export type FollowUpQueueName = 'overdue' | 'today' | 'upcoming'

export type FollowUpInput = {
  task_type: string
  owner_user_id: string
  due_date: string
  due_time: string
  summary: string
  call_status: string | null
}

export type FollowUp = FollowUpInput & {
  id: string
  project_id: string
  record_id: string
  task_type_label: string
  due_at: string
  timezone: string
  status: FollowUpStatus
  status_label: string
  call_status_label: string | null
  outcome: string
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
  completed_at: string | null
  cancelled_at: string | null
  public_number?: string
  display_name?: string
}

export type ActivityItem = {
  id: string
  record_id: string
  follow_up_id: string | null
  actor_id: string
  event_type: string
  label: string
  summary: string
  occurred_at: string
}

export type FollowUpPage = {
  items: FollowUp[]
  total: number
  limit: number
  offset: number
}

export type ActivityPage = {
  items: ActivityItem[]
  total: number
  limit: number
  offset: number
}

export type FollowUpQueuePage = FollowUpPage & {
  queue: FollowUpQueueName
  timezone: string
  window_start: string
  window_end: string
  owner_user_id: string | null
}

function followUpPath(tenantId: string, projectId: string, recordId: string, followUpId?: string): string {
  const base = `${recordPath(tenantId, projectId, recordId)}/follow-ups`
  return followUpId ? `${base}/${followUpId}` : base
}

export function listActivities(
  tenantId: string,
  projectId: string,
  recordId: string,
  query: { limit?: number; offset?: number } = {},
): Promise<ActivityPage> {
  const params = new URLSearchParams()
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit))
  }
  if (query.offset !== undefined) {
    params.set('offset', String(query.offset))
  }
  const search = params.toString()
  return request(crmUrl(), `${recordPath(tenantId, projectId, recordId)}/activities${search ? `?${search}` : ''}`)
}

export function listFollowUps(
  tenantId: string,
  projectId: string,
  recordId: string,
  query: { taskType?: string; limit?: number; offset?: number } = {},
): Promise<FollowUpPage> {
  const params = new URLSearchParams()
  if (query.taskType) {
    params.set('task_type', query.taskType)
  }
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit))
  }
  if (query.offset !== undefined) {
    params.set('offset', String(query.offset))
  }
  const search = params.toString()
  return request(crmUrl(), `${followUpPath(tenantId, projectId, recordId)}${search ? `?${search}` : ''}`)
}

export function createFollowUp(
  tenantId: string,
  projectId: string,
  recordId: string,
  input: FollowUpInput,
): Promise<FollowUp> {
  return request(crmUrl(), followUpPath(tenantId, projectId, recordId), {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function updateFollowUp(
  tenantId: string,
  projectId: string,
  recordId: string,
  followUpId: string,
  input: FollowUpInput & { expected_updated_at: string },
): Promise<FollowUp> {
  return request(crmUrl(), followUpPath(tenantId, projectId, recordId, followUpId), {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function completeFollowUp(
  tenantId: string,
  projectId: string,
  recordId: string,
  followUpId: string,
  input: { expected_updated_at: string; outcome: string },
): Promise<FollowUp> {
  return request(crmUrl(), `${followUpPath(tenantId, projectId, recordId, followUpId)}/complete`, {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function cancelFollowUp(
  tenantId: string,
  projectId: string,
  recordId: string,
  followUpId: string,
  input: { expected_updated_at: string; outcome: string },
): Promise<FollowUp> {
  return request(crmUrl(), `${followUpPath(tenantId, projectId, recordId, followUpId)}/cancel`, {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function listFollowUpQueue(
  tenantId: string,
  projectId: string,
  query: { queue: FollowUpQueueName; ownerUserId?: string; taskType?: string; limit?: number; offset?: number },
): Promise<FollowUpQueuePage> {
  const params = new URLSearchParams()
  params.set('queue', query.queue)
  if (query.ownerUserId) {
    params.set('owner_user_id', query.ownerUserId)
  }
  if (query.taskType) {
    params.set('task_type', query.taskType)
  }
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit))
  }
  if (query.offset !== undefined) {
    params.set('offset', String(query.offset))
  }
  return request(crmUrl(), `${projectPath(tenantId, projectId)}/follow-ups?${params.toString()}`)
}

export type ReminderItem = {
  id: string
  kind: string
  kind_label: string
  channel: 'in_app' | 'email'
  state: string
  state_label: string
  due_date: string
  due_time: string
  timezone: string
  read: boolean
  attempt_count: number
  last_attempt_at: string | null
  next_retry_at: string | null
  last_error: string | null
  failure_label: string | null
  record_available: boolean
  project_id?: string
  record_id?: string
  follow_up_id?: string
  public_number?: string
  recipient_user_id?: string
  recipient_email?: string
}

export type ReminderDeliveryResult = {
  claimed: number
  in_app_sent: number
  email_recorded: number
  email_sent: number
  retryable: number
  failed: number
  suppressed: number
  email_mode: 'test' | 'live'
  email_provider_confirmed: boolean
}

export function listReminders(tenantId: string): Promise<{ items: ReminderItem[]; total: number; timezone: string }> {
  return request(crmUrl(), `/api/v1/tenants/${tenantId}/reminders`)
}

export function listReminderFailures(tenantId: string): Promise<{ items: ReminderItem[]; total: number }> {
  return request(crmUrl(), `/api/v1/tenants/${tenantId}/reminders/failures`)
}

export function deliverReminders(tenantId: string): Promise<ReminderDeliveryResult> {
  return request(crmUrl(), `/api/v1/tenants/${tenantId}/reminders/process`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export function markReminderRead(tenantId: string, reminderId: string): Promise<ReminderItem> {
  return request(crmUrl(), `/api/v1/tenants/${tenantId}/reminders/${reminderId}/read`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export function retryReminder(tenantId: string, reminderId: string): Promise<ReminderItem> {
  return request(crmUrl(), `/api/v1/tenants/${tenantId}/reminders/${reminderId}/retry`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export type ImportField = {
  field_key: string
  label: string
  field_type: string
  required: boolean
  options: { value: string; label: string }[]
}

export type ImportCandidate = {
  kind: string
  message: string
  public_number?: string
  display_name?: string
  record_id?: string
  row_number?: string
  field_label?: string
}

export type ImportRow = {
  row_number: number
  source: Record<string, string>
  unmapped: Record<string, string>
  values: Record<string, unknown>
  errors: { field?: string; column?: string; message?: string }[]
  candidates: ImportCandidate[]
  decision: 'accept_new' | 'skip' | 'reject' | null
  outcome: string
  record_id: string | null
}

export type ImportSummary = {
  input_rows: number
  header_included: boolean
  accepted: number
  rejected: number
  skipped: number
  awaiting_review: number
  not_committed: number
  preview_accepted?: number
  preview_rejected?: number
  preview_skipped?: number
  preview_awaiting_review?: number
  records_created?: number
}

export type ImportJob = {
  id: string
  project_id: string
  form_id: string
  form_version_id: string
  filename: string
  status: string
  headers: string[]
  fields: ImportField[]
  unimportable_fields: { field_key: string; label: string; field_type: string }[]
  mapping: Record<string, string | null> | null
  suggested_mapping: Record<string, string | null>
  unmapped_columns: string[]
  rows: ImportRow[]
  summary: ImportSummary
}

function importPath(tenantId: string, projectId: string, jobId?: string): string {
  const base = `${projectPath(tenantId, projectId)}/imports`
  return jobId ? `${base}/${jobId}` : base
}

export function createImport(
  tenantId: string,
  projectId: string,
  input: { form_id: string; idempotency_key: string; filename: string; content_base64: string },
): Promise<ImportJob> {
  return request(crmUrl(), importPath(tenantId, projectId), {
    method: 'POST',
    headers: mutationHeaders(),
    body: JSON.stringify(input),
  })
}

export function saveImportMapping(
  tenantId: string,
  projectId: string,
  jobId: string,
  columns: Record<string, string | null>,
): Promise<ImportJob> {
  return request(crmUrl(), `${importPath(tenantId, projectId, jobId)}/mapping`, {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify({ columns }),
  })
}

export function previewImport(tenantId: string, projectId: string, jobId: string): Promise<ImportJob> {
  return request(crmUrl(), `${importPath(tenantId, projectId, jobId)}/preview`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export function saveImportDecisions(
  tenantId: string,
  projectId: string,
  jobId: string,
  rows: { row_number: number; decision: 'accept_new' | 'skip' | 'reject' }[],
): Promise<ImportJob> {
  return request(crmUrl(), `${importPath(tenantId, projectId, jobId)}/decisions`, {
    method: 'PATCH',
    headers: mutationHeaders(),
    body: JSON.stringify({ rows }),
  })
}

export function commitImport(tenantId: string, projectId: string, jobId: string): Promise<ImportJob> {
  return request(crmUrl(), `${importPath(tenantId, projectId, jobId)}/commit`, {
    method: 'POST',
    headers: mutationHeaders(),
  })
}

export async function downloadImportErrors(tenantId: string, projectId: string, jobId: string): Promise<void> {
  await downloadCrmFile(`${importPath(tenantId, projectId, jobId)}/errors`, 'import-errors.csv')
}

export async function exportRecords(
  tenantId: string,
  projectId: string,
  format: 'csv' | 'xlsx',
  query: RecordQuery = {},
): Promise<{ rows: number }> {
  const params = new URLSearchParams()
  params.set('format', format)
  if (query.q) {
    params.set('q', query.q)
  }
  if (query.formId) {
    params.set('form_id', query.formId)
  }
  if (query.source) {
    params.set('source', query.source)
  }
  if (query.createdFrom) {
    params.set('created_from', query.createdFrom)
  }
  if (query.createdTo) {
    params.set('created_to', query.createdTo)
  }
  if (query.sort) {
    params.set('sort', query.sort)
  }
  if (query.direction) {
    params.set('direction', query.direction)
  }
  return downloadCrmFile(`${projectPath(tenantId, projectId)}/record-exports?${params.toString()}`, `records.${format}`)
}

async function downloadCrmFile(path: string, fallbackName: string): Promise<{ rows: number }> {
  const response = await fetch(`${crmUrl().replace(/\/+$/, '')}${path}`, { credentials: 'include' })
  if (!response.ok) {
    let message = accessMessage(response.status)
    try {
      const body = (await response.json()) as { error?: { message?: string } }
      if (typeof body.error?.message === 'string' && body.error.message.trim()) {
        message = body.error.message
      }
    } catch {
      // The file response may be empty.
    }
    throw new ApiError(response.status, message)
  }
  const blob = await response.blob()
  const header = response.headers.get('Content-Disposition') ?? ''
  const matched = /filename="([^"]+)"/.exec(header)
  const filename = matched?.[1] || fallbackName
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
  const counted = Number(response.headers.get('X-CRM-Export-Rows'))
  return { rows: Number.isFinite(counted) ? counted : 0 }
}

export type ProjectKpis = {
  follow_up_timezone: string
  record_date_boundary: string
  window_start: string
  window_end: string
  record_period: { created_from: string; created_to: string; applied: boolean }
  active_records: number
  records_created: number | null
  records_by_form: { form_id: string; form_name: string; count: number }[]
  follow_ups: {
    overdue: number
    today: number
    upcoming: number
    completed: number
    by_owner: { owner_user_id: string; overdue: number; today: number; upcoming: number }[]
    by_due_date: { queue: string; due_date: string; count: number }[]
  }
  omitted: string[]
}

export type CompletedFollowUp = {
  id: string
  record_id: string
  public_number: string
  display_name: string
  task_type: string
  task_type_label: string
  owner_user_id: string
  completed_at: string
  due_date: string
  due_time: string
}

export type AuditEvent = {
  id: string
  occurred_at: string
  action: string
  resource_type: string
  resource_id: string | null
  summary: string
  outcome: 'success' | 'failure'
  actor_user_id: string | null
}

export function projectKpis(
  tenantId: string,
  projectId: string,
  query: { createdFrom?: string; createdTo?: string } = {},
): Promise<ProjectKpis> {
  const params = new URLSearchParams()
  if (query.createdFrom) {
    params.set('created_from', query.createdFrom)
  }
  if (query.createdTo) {
    params.set('created_to', query.createdTo)
  }
  const search = params.toString()
  return request(crmUrl(), `${projectPath(tenantId, projectId)}/kpis${search ? `?${search}` : ''}`)
}

export function listCompletedFollowUps(
  tenantId: string,
  projectId: string,
  query: { limit?: number; offset?: number } = {},
): Promise<{ items: CompletedFollowUp[]; total: number; limit: number; offset: number; status: 'completed' }> {
  const params = new URLSearchParams()
  if (query.limit !== undefined) {
    params.set('limit', String(query.limit))
  }
  if (query.offset !== undefined) {
    params.set('offset', String(query.offset))
  }
  const search = params.toString()
  return request(
    crmUrl(),
    `${projectPath(tenantId, projectId)}/kpis/completed-follow-ups${search ? `?${search}` : ''}`,
  )
}

export function listAuditEvents(
  tenantId: string,
  limit = 50,
): Promise<{ items: AuditEvent[]; limit: number; source: string }> {
  return request(crmUrl(), `/api/v1/tenants/${tenantId}/audit-events?limit=${limit}`)
}
