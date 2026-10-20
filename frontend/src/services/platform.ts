import { readFrontendConfig } from '@/lib/config'

export const CSRF_COOKIE_NAME = 'aadi_csrf'
export const CSRF_HEADER_NAME = 'X-CSRF-Token'
export const LEADS_PERMISSION = 'crm.lead_management.read'
export const PROJECT_MANAGE_PERMISSION = 'crm.project_management.manage'

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

export function canManageProjects(permissions: string[]): boolean {
  return permissions.includes(PROJECT_MANAGE_PERMISSION) || permissions.includes(LEADS_PERMISSION)
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
