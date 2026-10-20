import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { FormRenderer, type FormValue } from '@/features/forms/FormRenderer'
import { RecordFollowUps } from '@/features/records/FollowUpsPanel'
import { EmptyState, LoadingSkeleton } from '@/ui/chrome'
import {
  ApiError,
  archiveRecord,
  createRecord,
  getFormVersion,
  getProject,
  getRecord,
  listForms,
  listProjects,
  listRecords,
  updateRecord,
  type CrmRecord,
  type FormDefinition,
  type FormVersion,
  type Project,
  type RecordListItem,
  type RecordQuery,
  type RecordValue,
  type RenderField,
} from '@/services/platform'

const PAGE_SIZES = [5, 25, 50] as const
const DEFAULT_PAGE_SIZE = 25
const SOURCES: { value: string; label: string }[] = [
  { value: 'manual', label: 'Manual' },
  { value: 'website', label: 'Website' },
  { value: 'phone_call', label: 'Phone Call' },
  { value: 'justdial', label: 'JustDial' },
  { value: 'meta_ad', label: 'Meta Ad' },
  { value: 'referral', label: 'Referral' },
  { value: 'import', label: 'Import' },
  { value: 'other', label: 'Other' },
]

function formatWhen(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return 'The request could not be completed.'
}

function fieldsFrom(error: unknown): Record<string, string> {
  return error instanceof ApiError ? error.fields : {}
}

function optionLabel(field: RenderField, value: string): string {
  return field.options?.find((option) => option.value === value)?.label ?? value
}

function shownValue(field: RenderField, value: RecordValue | undefined): string {
  if (value === undefined || value === null || value === '') {
    return 'Not entered'
  }
  if (field.field_type === 'checkbox') {
    return value === true ? 'Yes' : 'No'
  }
  if ((field.field_type === 'dropdown' || field.field_type === 'radio') && typeof value === 'string') {
    return optionLabel(field, value)
  }
  if (field.field_type === 'multi_select' && Array.isArray(value)) {
    return value.length > 0 ? value.map((item) => optionLabel(field, item)).join(', ') : 'Not entered'
  }
  return String(value)
}

function formValues(fields: RenderField[], stored: Record<string, RecordValue>): Record<string, FormValue> {
  const values: Record<string, FormValue> = {}
  for (const field of fields) {
    const value = stored[field.field_key]
    if (field.field_type === 'checkbox') {
      values[field.field_key] = value === true
      continue
    }
    if (field.field_type === 'multi_select') {
      values[field.field_key] = Array.isArray(value) ? value : []
      continue
    }
    if (value === undefined || value === null) {
      values[field.field_key] = ''
      continue
    }
    values[field.field_key] = String(value)
  }
  return values
}

function payloadValues(fields: RenderField[], values: Record<string, FormValue>): Record<string, RecordValue> {
  const payload: Record<string, RecordValue> = {}
  for (const field of fields) {
    const value = values[field.field_key]
    if (field.field_type === 'file' || field.field_type === 'auto_number') {
      continue
    }
    if (field.field_type === 'checkbox') {
      payload[field.field_key] = value === true
      continue
    }
    if (field.field_type === 'multi_select') {
      payload[field.field_key] = Array.isArray(value) ? value : []
      continue
    }
    if (field.field_type === 'number' || field.field_type === 'currency') {
      const text = typeof value === 'string' ? value.trim() : ''
      if (!text) {
        continue
      }
      payload[field.field_key] = Number(text)
      continue
    }
    const text = typeof value === 'string' ? value.trim() : ''
    if (!text) {
      continue
    }
    payload[field.field_key] = text
  }
  return payload
}

function filtersActive(query: RecordQuery): boolean {
  return Boolean(query.q || query.formId || query.source || query.createdFrom || query.createdTo)
}

function summaryText(item: RecordListItem): string {
  return item.summary.map((entry) => `${entry.label}: ${entry.value}`).join(' · ')
}

function lastOffset(total: number, limit: number): number {
  if (total <= 0 || limit <= 0) {
    return 0
  }
  return Math.floor((total - 1) / limit) * limit
}

function visiblePages(current: number, count: number): number[] {
  if (count <= 0) {
    return []
  }
  const safeCurrent = Math.min(Math.max(current, 1), count)
  if (count <= 7) {
    return Array.from({ length: count }, (_, index) => index + 1)
  }
  const start = Math.max(1, Math.min(safeCurrent - 2, count - 4))
  return Array.from({ length: 5 }, (_, index) => start + index)
}

export function RecordsPanel({ tenantId }: { tenantId: string }) {
  const { projectId, recordId } = useParams()
  const location = useLocation()
  const onNew = location.pathname.endsWith('/new')
  const onEdit = Boolean(recordId) && location.pathname.endsWith('/edit')
  const [projectAttempt, setProjectAttempt] = useState(0)
  const [projects, setProjects] = useState<{ status: 'loading' | 'ready' | 'error'; items: Project[] }>({
    status: 'loading',
    items: [],
  })

  useEffect(() => {
    if (projectId) {
      return
    }
    let cancelled = false
    setProjects({ status: 'loading', items: [] })
    listProjects(tenantId, { q: '', status: '' })
      .then((page) => {
        if (!cancelled) {
          setProjects({ status: 'ready', items: page.items })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setProjects({ status: 'error', items: [] })
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, tenantId, projectAttempt])

  if (!projectId) {
    return (
      <section className="stack" aria-labelledby="records-projects-heading">
        <div className="page-header">
          <div>
            <h2 id="records-projects-heading">Records</h2>
            <p className="page-intro">Choose a project, then work with its records.</p>
          </div>
        </div>
        {projects.status === 'loading' ? <LoadingSkeleton /> : null}
        {projects.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            The projects could not be loaded.
            <button type="button" onClick={() => setProjectAttempt((current) => current + 1)}>
              Retry
            </button>
          </p>
        ) : null}
        {projects.status === 'ready' && projects.items.length === 0 ? (
          <EmptyState title="No projects" message="Create a project before adding records." />
        ) : null}
        {projects.status === 'ready' && projects.items.length > 0 ? (
          <ul className="project-list">
            {projects.items.map((project) => (
              <li key={project.id}>
                <Link to={`/tenants/${tenantId}/records/${project.id}`}>{project.name}</Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    )
  }

  if (onNew) {
    return <RecordEditor tenantId={tenantId} projectId={projectId} />
  }
  if (onEdit && recordId) {
    return <RecordEditor tenantId={tenantId} projectId={projectId} recordId={recordId} />
  }
  if (recordId) {
    return <RecordDetail tenantId={tenantId} projectId={projectId} recordId={recordId} />
  }
  return <RecordList tenantId={tenantId} projectId={projectId} />
}

function RecordList({ tenantId, projectId }: { tenantId: string; projectId: string }) {
  const [project, setProject] = useState<Project | null>(null)
  const [projectError, setProjectError] = useState<string | null>(null)
  const [forms, setForms] = useState<FormDefinition[]>([])
  const [page, setPage] = useState<{
    status: 'loading' | 'ready' | 'error'
    items: RecordListItem[]
    total: number
    limit: number
    offset: number
  }>({
    status: 'loading',
    items: [],
    total: 0,
    limit: DEFAULT_PAGE_SIZE,
    offset: 0,
  })
  const [draft, setDraft] = useState({ q: '', formId: '', source: '', createdFrom: '', createdTo: '' })
  const [query, setQuery] = useState<RecordQuery>({
    sort: 'created_at',
    direction: 'desc',
    limit: DEFAULT_PAGE_SIZE,
    offset: 0,
  })
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    getProject(tenantId, projectId)
      .then((loaded) => {
        if (!cancelled) {
          setProject(loaded)
          setProjectError(null)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setProjectError(messageFrom(error))
        }
      })
    listForms(tenantId, projectId)
      .then((loaded) => {
        if (!cancelled) {
          setForms(loaded.items)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setForms([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId])

  useEffect(() => {
    let cancelled = false
    setPage((current) => ({ ...current, status: 'loading' }))
    listRecords(tenantId, projectId, query)
      .then((loaded) => {
        if (!cancelled) {
          setPage({
            status: 'ready',
            items: loaded.items,
            total: loaded.total,
            limit: loaded.limit,
            offset: loaded.offset,
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPage({ status: 'error', items: [], total: 0, limit: DEFAULT_PAGE_SIZE, offset: 0 })
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId, query, reload])

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const next = {
      q: draft.q.trim(),
      formId: draft.formId,
      source: draft.source,
      createdFrom: draft.createdFrom,
      createdTo: draft.createdTo,
    }
    setQuery((current) => {
      if (
        (current.q ?? '') === next.q &&
        (current.formId ?? '') === next.formId &&
        (current.source ?? '') === next.source &&
        (current.createdFrom ?? '') === next.createdFrom &&
        (current.createdTo ?? '') === next.createdTo &&
        (current.offset ?? 0) === 0
      ) {
        return current
      }
      return { ...current, ...next, offset: 0 }
    })
  }

  function onClear() {
    setDraft({ q: '', formId: '', source: '', createdFrom: '', createdTo: '' })
    setQuery((current) => {
      if (!filtersActive(current)) {
        return current
      }
      return {
        ...current,
        q: undefined,
        formId: undefined,
        source: undefined,
        createdFrom: undefined,
        createdTo: undefined,
        offset: 0,
      }
    })
  }

  const archived = project?.status === 'archived'
  const offset = query.offset ?? 0
  const limit = query.limit ?? DEFAULT_PAGE_SIZE
  const from = page.total === 0 ? 0 : page.offset + 1
  const to = page.total === 0 ? 0 : page.offset + page.items.length
  const showPager = page.status === 'ready' && (page.items.length > 0 || page.offset > 0)
  const pageCount = page.total > 0 ? Math.ceil(page.total / limit) : 0
  const currentPage = Math.floor(offset / limit) + 1
  const endOffset = lastOffset(page.total, limit)

  return (
    <section className="stack" aria-labelledby="record-list-heading">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/tenants/${tenantId}/records`}>Records</Link>
        <span aria-hidden="true">/</span>
        <span>{project?.name ?? 'Project'}</span>
      </nav>
      <div className="page-header">
        <div>
          <h2 id="record-list-heading">{project?.name ?? 'Records'}</h2>
          <p className="page-intro">Records in this project. Search runs on the server.</p>
        </div>
        {archived ? null : (
          <Link className="button-link" to={`/tenants/${tenantId}/records/${projectId}/new`}>
            New record
          </Link>
        )}
      </div>
      {projectError ? (
        <p role="alert" className="alert alert-error">
          {projectError}
        </p>
      ) : null}
      {archived ? <p>This project is archived. Existing records can still be read.</p> : null}
      <form className="panel record-filters" onSubmit={onSearch}>
        <label className="filter-search">
          Search records
          <input value={draft.q} onChange={(event) => setDraft((current) => ({ ...current, q: event.target.value }))} />
        </label>
        <label className="filter-form">
          Form
          <select
            value={draft.formId}
            onChange={(event) => setDraft((current) => ({ ...current, formId: event.target.value }))}
          >
            <option value="">All forms</option>
            {forms.map((form) => (
              <option key={form.id} value={form.id}>
                {form.name}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-source">
          Source
          <select
            value={draft.source}
            onChange={(event) => setDraft((current) => ({ ...current, source: event.target.value }))}
          >
            <option value="">All sources</option>
            {SOURCES.map((source) => (
              <option key={source.value} value={source.value}>
                {source.label}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-from">
          Created from
          <input
            type="date"
            value={draft.createdFrom}
            onChange={(event) => setDraft((current) => ({ ...current, createdFrom: event.target.value }))}
          />
        </label>
        <label className="filter-to">
          Created to
          <input
            type="date"
            value={draft.createdTo}
            onChange={(event) => setDraft((current) => ({ ...current, createdTo: event.target.value }))}
          />
        </label>
        <label className="filter-sort">
          Sort
          <select
            value={`${query.sort ?? 'created_at'}:${query.direction ?? 'desc'}`}
            onChange={(event) => {
              const [sort, direction] = event.target.value.split(':')
              setQuery((current) => {
                if (current.sort === sort && current.direction === direction && (current.offset ?? 0) === 0) {
                  return current
                }
                return {
                  ...current,
                  sort: sort as RecordQuery['sort'],
                  direction: direction as RecordQuery['direction'],
                  offset: 0,
                }
              })
            }}
          >
            <option value="created_at:desc">Newest</option>
            <option value="created_at:asc">Oldest</option>
            <option value="updated_at:desc">Recently updated</option>
            <option value="public_number:asc">Record number</option>
          </select>
        </label>
        <label className="filter-size">
          Page size
          <select
            value={String(limit)}
            onChange={(event) => {
              const nextLimit = Number(event.target.value)
              setQuery((current) => {
                if (current.limit === nextLimit && (current.offset ?? 0) === 0) {
                  return current
                }
                return { ...current, limit: nextLimit, offset: 0 }
              })
            }}
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <div className="filter-actions">
          <button type="submit">Search</button>
          <button type="button" className="button-secondary" onClick={onClear}>
            Clear
          </button>
        </div>
      </form>
      {page.status === 'loading' ? <LoadingSkeleton /> : null}
      {page.status === 'error' ? (
        <p role="alert" className="alert alert-error">
          The records could not be loaded.
          <button type="button" onClick={() => setReload((current) => current + 1)}>
            Retry
          </button>
        </p>
      ) : null}
      {page.status === 'ready' && page.items.length === 0 && offset === 0 ? (
        <EmptyState
          title={filtersActive(query) ? 'No matching records' : 'No records yet'}
          message={
            filtersActive(query)
              ? 'Try a different search or clear the filters.'
              : 'Create a record from a published form.'
          }
        />
      ) : null}
      {page.status === 'ready' && page.items.length === 0 && page.offset > 0 ? (
        <EmptyState title="No records on this page" message="Go back to see the records that match." />
      ) : null}
      {page.status === 'ready' ? (
        <div className="results-header">
          <h3 id="record-results-heading">Records ({page.total})</h3>
        </div>
      ) : null}
      {page.status === 'ready' && page.items.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table" aria-labelledby="record-results-heading">
            <thead>
              <tr>
                <th scope="col">Record ID</th>
                <th scope="col">Name</th>
                <th scope="col" className="col-extra">Form</th>
                <th scope="col" className="col-extra">Source</th>
                <th scope="col">Created</th>
                <th scope="col" className="col-extra">Updated</th>
                <th scope="col" className="col-extra">Details</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((item) => {
                const details = summaryText(item)
                const created = formatWhen(item.created_at)
                const updated = formatWhen(item.updated_at)
                return (
                  <tr key={item.id}>
                    <td>
                      <Link to={`/tenants/${tenantId}/records/${projectId}/${item.id}`}>{item.public_number}</Link>
                    </td>
                    <td>
                      <span className="clip" title={item.display_name}>
                        {item.display_name}
                      </span>
                    </td>
                    <td className="col-extra">
                      <span className="clip" title={item.form_name}>
                        {item.form_name}
                      </span>
                    </td>
                    <td className="col-extra">{item.source_label}</td>
                    <td>
                      <span className="clip" title={item.created_at}>
                        {created}
                      </span>
                    </td>
                    <td className="col-extra">
                      <span className="clip" title={item.updated_at}>
                        {updated}
                      </span>
                    </td>
                    <td className="col-extra">
                      <span className="clip" title={details || undefined}>
                        {details || '—'}
                      </span>
                    </td>
                    <td>
                      <Link
                        className="table-action"
                        to={`/tenants/${tenantId}/records/${projectId}/${item.id}`}
                        aria-label={`Open ${item.public_number}`}
                      >
                        Open
                      </Link>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
      {showPager ? (
        <div className="pager">
          <p>
            Showing {from}–{to} of {page.total} records
          </p>
          <div className="pager-controls">
            <label>
              Rows per page
              <select
                value={String(limit)}
                onChange={(event) => {
                  const nextLimit = Number(event.target.value)
                  setQuery((current) => {
                    if (current.limit === nextLimit && (current.offset ?? 0) === 0) {
                      return current
                    }
                    return { ...current, limit: nextLimit, offset: 0 }
                  })
                }}
              >
                {PAGE_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => setQuery((current) => ((current.offset ?? 0) === 0 ? current : { ...current, offset: 0 }))}
            >
              First
            </button>
            <button
              type="button"
              disabled={offset === 0}
              onClick={() =>
                setQuery((current) => ({ ...current, offset: Math.max(0, offset - limit) }))
              }
            >
              Previous
            </button>
            {visiblePages(currentPage, pageCount).map((pageNumber) => (
              <button
                key={pageNumber}
                type="button"
                aria-label={`Page ${pageNumber}`}
                aria-current={pageNumber === currentPage ? 'page' : undefined}
                onClick={() => {
                  const nextOffset = (pageNumber - 1) * limit
                  setQuery((current) =>
                    (current.offset ?? 0) === nextOffset ? current : { ...current, offset: nextOffset },
                  )
                }}
              >
                {pageNumber}
              </button>
            ))}
            <button
              type="button"
              disabled={offset + limit >= page.total}
              onClick={() => setQuery((current) => ({ ...current, offset: offset + limit }))}
            >
              Next
            </button>
            <button
              type="button"
              disabled={offset >= endOffset}
              onClick={() =>
                setQuery((current) => ((current.offset ?? 0) === endOffset ? current : { ...current, offset: endOffset }))
              }
            >
              Last
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}

function RecordDetail({ tenantId, projectId, recordId }: { tenantId: string; projectId: string; recordId: string }) {
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [record, setRecord] = useState<CrmRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([getProject(tenantId, projectId), getRecord(tenantId, projectId, recordId)])
      .then(([loadedProject, loadedRecord]) => {
        if (!cancelled) {
          setProject(loadedProject)
          setRecord(loadedRecord)
          setLoading(false)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(messageFrom(caught))
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId, recordId, reload])

  async function onArchive() {
    if (!record || submitting) {
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await archiveRecord(tenantId, projectId, record.id, record.updated_at)
      navigate(`/tenants/${tenantId}/records/${projectId}`)
    } catch (caught) {
      setError(messageFrom(caught))
      setSubmitting(false)
    }
  }

  const archived = project?.status === 'archived'
  const absent = new Set(record?.absent_from_draft.map((item) => item.field_key) ?? [])

  return (
    <section className="stack" aria-labelledby="record-detail-heading">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/tenants/${tenantId}/records`}>Records</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/tenants/${tenantId}/records/${projectId}`}>{project?.name ?? 'Project'}</Link>
        <span aria-hidden="true">/</span>
        <span>{record?.public_number ?? 'Record'}</span>
      </nav>
      {loading ? <LoadingSkeleton /> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}{' '}
          <button type="button" onClick={() => setReload((current) => current + 1)}>
            Retry
          </button>
        </p>
      ) : null}
      {record ? (
        <>
          <div className="page-header">
            <div>
              <h2 id="record-detail-heading">{record.public_number}</h2>
              <p className="page-intro">{record.display_name}</p>
            </div>
            {archived ? null : (
              <Link className="button-link" to={`/tenants/${tenantId}/records/${projectId}/${record.id}/edit`}>
                Edit record
              </Link>
            )}
          </div>
          <p>
            Form {record.form_name}, version {record.version_number}. Form version {record.form_version_id}.
          </p>
          <p>Source {record.source_label}.</p>
          <p>Created {formatWhen(record.created_at)}.</p>
          <p>Updated {formatWhen(record.updated_at)}.</p>
          {archived ? <p>This project is archived. This record can still be read.</p> : null}
          {record.fields.map((field) => (
            <div key={field.field_key}>
              <p>
                <strong>{field.label}</strong>
              </p>
              <p>{shownValue(field, record.values[field.field_key])}</p>
              {absent.has(field.field_key) ? (
                <p>This field is not in the current draft. This record still uses version {record.version_number}.</p>
              ) : null}
            </div>
          ))}
          {record.unmapped_values.length > 0 ? (
            <div>
              <h3>Stored values without a field in this version</h3>
              {record.unmapped_values.map((item) => (
                <p key={item.field_key}>
                  {item.field_key}: {item.value === null ? 'Not entered' : String(item.value)}
                </p>
              ))}
            </div>
          ) : null}
          <RecordFollowUps
            tenantId={tenantId}
            projectId={projectId}
            recordId={record.id}
            readOnly={Boolean(archived)}
          />
          {archived ? null : (
            <button type="button" onClick={() => void onArchive()} disabled={submitting}>
              {submitting ? 'Archiving record' : 'Archive record'}
            </button>
          )}
        </>
      ) : null}
    </section>
  )
}

function RecordEditor({
  tenantId,
  projectId,
  recordId,
}: {
  tenantId: string
  projectId: string
  recordId?: string
}) {
  const navigate = useNavigate()
  const saving = useRef(false)
  const [project, setProject] = useState<Project | null>(null)
  const [forms, setForms] = useState<FormDefinition[]>([])
  const [formId, setFormId] = useState('')
  const [published, setPublished] = useState<FormVersion | null>(null)
  const [record, setRecord] = useState<CrmRecord | null>(null)
  const [source, setSource] = useState('manual')
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const requests: Promise<unknown>[] = [getProject(tenantId, projectId)]
    if (recordId) {
      requests.push(getRecord(tenantId, projectId, recordId))
    } else {
      requests.push(listForms(tenantId, projectId))
    }
    Promise.all(requests)
      .then((loaded) => {
        if (cancelled) {
          return
        }
        setProject(loaded[0] as Project)
        if (recordId) {
          const existing = loaded[1] as CrmRecord
          setRecord(existing)
          setFormId(existing.form_id)
          setSource(existing.source)
        } else {
          const published = ((loaded[1] as { items: FormDefinition[] }).items ?? []).filter(
            (form) => form.current_published_version_id,
          )
          setForms(published)
          setFormId(published[0]?.id ?? '')
        }
        setLoading(false)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(messageFrom(caught))
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId, recordId])

  const selected = forms.find((form) => form.id === formId) ?? null

  useEffect(() => {
    if (recordId || !selected?.current_published_version_id) {
      return
    }
    let cancelled = false
    setPublished(null)
    getFormVersion(tenantId, projectId, selected.id, selected.current_published_version_id)
      .then((version) => {
        if (!cancelled) {
          setPublished(version)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(messageFrom(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [recordId, selected, tenantId, projectId])

  const fields = record?.fields ?? published?.fields ?? []
  const versionNumber = record?.version_number ?? published?.version_number
  const versionName = record?.form_name ?? published?.name ?? ''
  const versionDescription = record?.form_description ?? published?.description ?? ''
  const archived = project?.status === 'archived'

  async function onSave(values: Record<string, FormValue>) {
    if (saving.current || archived) {
      return
    }
    saving.current = true
    setSubmitting(true)
    setError(null)
    setFieldErrors({})
    try {
      const payload = payloadValues(fields, values)
      const saved = record
        ? await updateRecord(tenantId, projectId, record.id, {
            expected_updated_at: record.updated_at,
            values: payload,
          })
        : await createRecord(tenantId, projectId, { form_id: formId, source, values: payload })
      navigate(`/tenants/${tenantId}/records/${projectId}/${saved.id}`)
    } catch (caught) {
      setError(messageFrom(caught))
      setFieldErrors(fieldsFrom(caught))
      setSubmitting(false)
      saving.current = false
    }
  }

  return (
    <section className="stack" aria-labelledby="record-editor-heading">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/tenants/${tenantId}/records`}>Records</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/tenants/${tenantId}/records/${projectId}`}>{project?.name ?? 'Project'}</Link>
        <span aria-hidden="true">/</span>
        <span>{record ? record.public_number : 'New record'}</span>
      </nav>
      <h2 id="record-editor-heading">{record ? `Edit ${record.public_number}` : 'New record'}</h2>
      {loading ? <LoadingSkeleton /> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}
        </p>
      ) : null}
      {archived ? <p>This project is archived. Records cannot be changed.</p> : null}
      {!loading && !record && forms.length === 0 ? (
        <EmptyState title="No published form" message="Publish a form in this project before adding a record." />
      ) : null}
      {!loading && !archived && !record && forms.length > 0 ? (
        <>
          <label>
            Form
            <select value={formId} onChange={(event) => setFormId(event.target.value)}>
              {forms.map((form) => (
                <option key={form.id} value={form.id}>
                  {form.name} · version {form.current_published_version_number}
                </option>
              ))}
            </select>
          </label>
          <label>
            Source
            <select value={source} onChange={(event) => setSource(event.target.value)}>
              {SOURCES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </>
      ) : null}
      {!loading && !archived && fields.length > 0 && (record || published) ? (
        <FormRenderer
          key={record ? record.form_version_id : published?.id}
          name={versionName}
          description={versionDescription}
          fields={fields}
          mode="record"
          versionNumber={versionNumber ?? undefined}
          initialValues={record ? formValues(record.fields, record.values) : undefined}
          externalErrors={fieldErrors}
          submitting={submitting}
          onSave={onSave}
        />
      ) : null}
    </section>
  )
}
