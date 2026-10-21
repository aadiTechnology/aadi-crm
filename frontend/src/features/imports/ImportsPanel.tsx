import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { EmptyState, LoadingSkeleton } from '@/ui/chrome'
import {
  ApiError,
  commitImport,
  createImport,
  downloadImportErrors,
  exportRecords,
  listForms,
  listProjects,
  listRecords,
  previewImport,
  saveImportDecisions,
  saveImportMapping,
  type FormDefinition,
  type ImportJob,
  type ImportRow,
  type Project,
} from '@/services/platform'

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return 'The request could not be completed.'
}

function importKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `import-${Date.now()}`
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const value = String(reader.result ?? '')
      const comma = value.indexOf(',')
      resolve(comma >= 0 ? value.slice(comma + 1) : value)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

function summaryText(job: ImportJob): string {
  const summary = job.summary
  const preview = summary.preview_accepted !== undefined
  if (preview && summary.accepted === 0 && summary.not_committed === summary.input_rows) {
    return `Dry-run only. No CRM records were created. Ready ${summary.preview_accepted ?? 0}, rejected ${summary.preview_rejected ?? 0}, skipped ${summary.preview_skipped ?? 0}, awaiting review ${summary.preview_awaiting_review ?? 0}. Input rows ${summary.input_rows}, not counting the header.`
  }
  const state = job.status === 'completed' ? 'Completed' : job.status === 'failed' ? 'Failed' : 'Partially completed'
  return `${state}. Accepted ${summary.accepted}, rejected ${summary.rejected}, skipped ${summary.skipped}, awaiting review ${summary.awaiting_review}. Input rows ${summary.input_rows}, not counting the header.`
}

export function ImportsPanel({ tenantId }: { tenantId: string }) {
  const { projectId } = useParams()
  const [projects, setProjects] = useState<{ status: 'loading' | 'ready' | 'error'; items: Project[] }>({
    status: 'loading',
    items: [],
  })
  const [attempt, setAttempt] = useState(0)

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
  }, [projectId, tenantId, attempt])

  if (!projectId) {
    return (
      <section className="stack" aria-labelledby="import-projects-heading">
        <div className="page-header">
          <div>
            <h2 id="import-projects-heading">Import</h2>
            <p className="page-intro">Choose a project, then import or export its records.</p>
          </div>
        </div>
        {projects.status === 'loading' ? <p role="status">Loading import</p> : null}
        {projects.status === 'loading' ? <LoadingSkeleton /> : null}
        {projects.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            The projects could not be loaded.
            <button type="button" onClick={() => setAttempt((current) => current + 1)}>
              Retry
            </button>
          </p>
        ) : null}
        {projects.status === 'ready' && projects.items.length === 0 ? (
          <EmptyState title="No projects" message="Create a project before importing records." />
        ) : null}
        {projects.status === 'ready' && projects.items.length > 0 ? (
          <ul className="project-list">
            {projects.items.map((project) => (
              <li key={project.id}>
                <Link to={`/tenants/${tenantId}/imports/${project.id}`}>{project.name}</Link>
              </li>
            ))}
          </ul>
        ) : null}
      </section>
    )
  }

  return <ImportWorkspace tenantId={tenantId} projectId={projectId} />
}

function ImportWorkspace({ tenantId, projectId }: { tenantId: string; projectId: string }) {
  const [forms, setForms] = useState<FormDefinition[]>([])
  const [formId, setFormId] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [key, setKey] = useState(importKey)
  const [job, setJob] = useState<ImportJob | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [decisions, setDecisions] = useState<Record<number, 'accept_new' | 'skip' | 'reject' | ''>>({})
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [exportNote, setExportNote] = useState<string | null>(null)
  const [formsState, setFormsState] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    setFormsState('loading')
    listForms(tenantId, projectId)
      .then((page) => {
        if (!cancelled) {
          const published = page.items.filter((form) => form.current_published_version_id)
          setForms(published)
          setFormId(published[0]?.id ?? '')
          setFormsState('ready')
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFormsState('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId])

  function applyJob(next: ImportJob) {
    setJob(next)
    const initial: Record<string, string> = {}
    for (const header of next.headers) {
      initial[header] = next.mapping?.[header] ?? next.suggested_mapping?.[header] ?? ''
    }
    setMapping(initial)
    const chosen: Record<number, 'accept_new' | 'skip' | 'reject' | ''> = {}
    for (const row of next.rows) {
      chosen[row.row_number] = row.decision ?? ''
    }
    setDecisions(chosen)
  }

  async function onUpload(event: FormEvent) {
    event.preventDefault()
    if (!file || !formId) {
      setError('Choose a published form and a CSV or XLSX file.')
      return
    }
    setBusy('Uploading file')
    setError(null)
    try {
      const content = await fileToBase64(file)
      const created = await createImport(tenantId, projectId, {
        form_id: formId,
        idempotency_key: key,
        filename: file.name,
        content_base64: content,
      })
      applyJob(created)
      setNotice('The file is uploaded. Map every column before preview. Unmapped columns stay on the import and are not copied into records.')
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusy(null)
    }
  }

  async function onMap() {
    if (!job) {
      return
    }
    const columns: Record<string, string | null> = {}
    const used = new Set<string>()
    for (const header of job.headers) {
      const target = mapping[header] || null
      if (target) {
        if (used.has(target)) {
          setError('Each CRM field can be selected once.')
          return
        }
        used.add(target)
      }
      columns[header] = target
    }
    setBusy('Saving mapping')
    setError(null)
    try {
      applyJob(await saveImportMapping(tenantId, projectId, job.id, columns))
      setNotice('Mapping saved. Preview checks the rows and does not create records.')
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusy(null)
    }
  }

  async function onPreview() {
    if (!job) {
      return
    }
    setBusy('Previewing import')
    setError(null)
    try {
      const previewed = await previewImport(tenantId, projectId, job.id)
      applyJob(previewed)
      setNotice(summaryText(previewed))
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusy(null)
    }
  }

  async function onCommit() {
    if (!job) {
      return
    }
    setBusy('Importing records')
    setError(null)
    try {
      const pending = job.rows
        .filter((row) => decisions[row.row_number])
        .map((row) => ({
          row_number: row.row_number,
          decision: decisions[row.row_number] as 'accept_new' | 'skip' | 'reject',
        }))
      if (pending.length > 0) {
        await saveImportDecisions(tenantId, projectId, job.id, pending)
      }
      const committed = await commitImport(tenantId, projectId, job.id)
      applyJob(committed)
      setNotice(summaryText(committed))
    } catch (caught) {
      setError(messageFrom(caught))
    } finally {
      setBusy(null)
    }
  }

  async function onErrors() {
    if (!job) {
      return
    }
    setError(null)
    try {
      await downloadImportErrors(tenantId, projectId, job.id)
    } catch (caught) {
      setError(messageFrom(caught))
    }
  }

  async function onExport(format: 'csv' | 'xlsx') {
    setExportNote('Preparing the export')
    setError(null)
    try {
      const listed = await listRecords(tenantId, projectId, { q: search, formId, limit: 1 })
      const exported = await exportRecords(tenantId, projectId, format, { q: search, formId })
      setExportNote(
        exported.rows === listed.total
          ? `Exported ${exported.rows} data rows. The list reports ${listed.total} matching records.`
          : `Exported ${exported.rows} data rows. The list reports ${listed.total} matching records.`,
      )
    } catch (caught) {
      setExportNote(null)
      setError(messageFrom(caught))
    }
  }

  const published = forms.find((form) => form.id === formId)

  return (
    <section className="stack" aria-labelledby="import-heading">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/tenants/${tenantId}/imports`}>Import</Link>
        <span aria-hidden="true">/</span>
        <span>{published?.name ?? 'Project'}</span>
      </nav>
      <div className="page-header">
        <div>
          <h2 id="import-heading">Import and export</h2>
          <p className="page-intro">
            CSV and XLSX files are limited to 1 MB and 500 data rows. The header is not counted. A dry-run does not
            create records.
          </p>
        </div>
      </div>
      {formsState === 'loading' ? <p role="status">Loading import</p> : null}
      {formsState === 'loading' ? <LoadingSkeleton /> : null}
      {formsState === 'error' ? (
        <p role="alert" className="alert alert-error">
          The forms could not be loaded.
        </p>
      ) : null}
      {formsState === 'ready' && forms.length === 0 ? (
        <EmptyState title="No published form" message="Publish a form before importing records." />
      ) : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="alert alert-ok">
          {notice}
        </p>
      ) : null}
      {busy ? <p role="status">{busy}</p> : null}
      {formsState === 'ready' && forms.length > 0 ? (
        <form className="panel import-form" onSubmit={(event) => void onUpload(event)}>
          <label>
            Published form
            <select value={formId} onChange={(event) => setFormId(event.target.value)}>
              {forms.map((form) => (
                <option key={form.id} value={form.id}>
                  {form.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            CSV or XLSX file
            <input
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setKey(importKey())
                setJob(null)
              }}
            />
          </label>
          <button type="submit" disabled={busy !== null}>
            Upload file
          </button>
        </form>
      ) : null}
      {job ? (
        <div className="stack">
          <h3>Column mapping</h3>
          <p>Required fields are marked. Leave a column unmapped when its values should stay out of the CRM record.</p>
          {job.unimportable_fields.length > 0 ? (
            <p>
              These fields cannot be imported: {job.unimportable_fields.map((field) => field.label).join(', ')}.
            </p>
          ) : null}
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Source column</th>
                  <th>CRM field</th>
                </tr>
              </thead>
              <tbody>
                {job.headers.map((header) => (
                  <tr key={header}>
                    <td>{header}</td>
                    <td>
                      <label>
                        Map {header}
                        <select
                          value={mapping[header] ?? ''}
                          onChange={(event) =>
                            setMapping((current) => ({ ...current, [header]: event.target.value }))
                          }
                        >
                          <option value="">Unmapped</option>
                          {job.fields.map((field) => (
                            <option key={field.field_key} value={field.field_key}>
                              {field.label}
                              {field.required ? ' (required)' : ''}
                            </option>
                          ))}
                        </select>
                      </label>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {job.unmapped_columns.length > 0 ? (
            <p>Unmapped columns kept on this import: {job.unmapped_columns.join(', ')}.</p>
          ) : null}
          <div className="import-actions">
            <button type="button" onClick={() => void onMap()} disabled={busy !== null}>
              Save mapping
            </button>
            <button type="button" className="button-secondary" onClick={() => void onPreview()} disabled={busy !== null}>
              Preview import
            </button>
            <button type="button" onClick={() => void onCommit()} disabled={busy !== null}>
              Import records
            </button>
            <button type="button" className="button-secondary" onClick={() => void onErrors()}>
              Download error report
            </button>
            <button type="button" className="button-secondary" onClick={() => void onCommit()} disabled={busy !== null}>
              Repeat this import
            </button>
          </div>
          <PreviewTable rows={job.rows} decisions={decisions} onDecision={(rowNumber, decision) => setDecisions((current) => ({ ...current, [rowNumber]: decision }))} />
        </div>
      ) : null}
      <form
        className="panel import-form"
        onSubmit={(event) => {
          event.preventDefault()
          void onExport('csv')
        }}
      >
        <h3>Export the current filter</h3>
        <p>Export uses the search and the selected form. It includes every matching record you can see, not only one page.</p>
        <label>
          Search records
          <input value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
        <div className="import-actions">
          <button type="submit">Export CSV</button>
          <button type="button" className="button-secondary" onClick={() => void onExport('xlsx')}>
            Export XLSX
          </button>
        </div>
        {exportNote ? <p role="status">{exportNote}</p> : null}
      </form>
    </section>
  )
}

function PreviewTable({
  rows,
  decisions,
  onDecision,
}: {
  rows: ImportRow[]
  decisions: Record<number, 'accept_new' | 'skip' | 'reject' | ''>
  onDecision: (rowNumber: number, decision: 'accept_new' | 'skip' | 'reject' | '') => void
}) {
  if (rows.length === 0) {
    return null
  }
  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption>Preview rows</caption>
        <thead>
          <tr>
            <th>Row</th>
            <th>Values</th>
            <th>Result</th>
            <th>Duplicate review</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_number}>
              <td>{row.row_number}</td>
              <td>
                {Object.entries(row.values).map(([key, value]) => (
                  <span key={key}>
                    {key}: {String(value)}{' '}
                  </span>
                ))}
                {Object.keys(row.unmapped).length > 0 ? <span>Unmapped: {Object.keys(row.unmapped).join(', ')}</span> : null}
              </td>
              <td>
                {row.errors.length === 0 ? row.outcome : null}
                {row.errors.map((item, index) => (
                  <p key={`${row.row_number}-${index}`}>
                    {item.field || item.column || 'Row'}: {item.message}
                  </p>
                ))}
              </td>
              <td>
                {row.candidates.length === 0 ? <span>No possible match</span> : null}
                {row.candidates.map((candidate, index) => (
                  <p key={`${row.row_number}-match-${index}`}>{candidate.message}</p>
                ))}
                <label>
                  Decision for row {row.row_number}
                  <select
                    value={decisions[row.row_number] ?? ''}
                    onChange={(event) =>
                      onDecision(row.row_number, event.target.value as 'accept_new' | 'skip' | 'reject' | '')
                    }
                  >
                    <option value="">No decision</option>
                    <option value="accept_new">Accept as new</option>
                    <option value="skip">Skip</option>
                    <option value="reject">Reject</option>
                  </select>
                </label>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
