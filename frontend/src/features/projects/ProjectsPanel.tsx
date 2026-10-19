import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import {
  ApiError,
  archiveProject,
  createProject,
  getProject,
  listProjects,
  updateProject,
  type Project,
} from '@/services/platform'

type ListState =
  | { status: 'loading' }
  | { status: 'ready'; items: Project[] }
  | { status: 'error'; message: string }

type DetailState =
  | { status: 'loading' }
  | { status: 'ready'; project: Project }
  | { status: 'error'; message: string }

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return 'The request could not be completed.'
}

function formatWhen(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export function ProjectsPanel({ tenantId }: { tenantId: string }) {
  const { projectId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const onNew = location.pathname.endsWith('/projects/new')
  const onDetail = Boolean(projectId) && !onNew
  const [query, setQuery] = useState('')
  const [appliedQuery, setAppliedQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [list, setList] = useState<ListState>({ status: 'loading' })
  const [detail, setDetail] = useState<DetailState>({ status: 'loading' })
  const [code, setCode] = useState('')
  const [createName, setCreateName] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setSubmitting(false)
  }, [location.pathname])

  useEffect(() => {
    if (onNew || onDetail) {
      return
    }
    let cancelled = false
    setList({ status: 'loading' })
    listProjects(tenantId, { q: appliedQuery, status: statusFilter })
      .then((result) => {
        if (!cancelled) {
          setList({ status: 'ready', items: result.items })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setList({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [appliedQuery, onDetail, onNew, statusFilter, tenantId])

  useEffect(() => {
    if (!onDetail || !projectId) {
      return
    }
    let cancelled = false
    setDetail({ status: 'loading' })
    getProject(tenantId, projectId)
      .then((project) => {
        if (!cancelled) {
          setDetail({ status: 'ready', project })
          setEditName(project.name)
          setEditDescription(project.description)
          setFormError(null)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [onDetail, projectId, tenantId])

  function onSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAppliedQuery(query.trim())
  }

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextCode = code.trim()
    const nextName = createName.trim()
    if (!nextCode) {
      setFormError('Project code is required.')
      return
    }
    if (!nextName) {
      setFormError('Project name is required.')
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      const created = await createProject(tenantId, {
        code: nextCode,
        name: nextName,
        description: createDescription.trim(),
      })
      navigate(`/tenants/${tenantId}/projects/${created.id}`)
    } catch (error) {
      setFormError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!projectId) {
      return
    }
    const nextName = editName.trim()
    if (!nextName) {
      setFormError('Project name is required.')
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      const updated = await updateProject(tenantId, projectId, {
        name: nextName,
        description: editDescription.trim(),
      })
      setDetail({ status: 'ready', project: updated })
      setSubmitting(false)
    } catch (error) {
      setFormError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onArchive() {
    if (!projectId || detail.status !== 'ready' || detail.project.status === 'archived') {
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      const archived = await archiveProject(tenantId, projectId)
      setDetail({ status: 'ready', project: archived })
      setSubmitting(false)
    } catch (error) {
      setFormError(messageFrom(error))
      setSubmitting(false)
    }
  }

  if (onNew) {
    return (
      <section className="stack" aria-labelledby="project-create-heading">
        <h2 id="project-create-heading">New project</h2>
        <form className="stack" onSubmit={(event) => void onCreate(event)} noValidate>
          <label>
            Project code
            <input name="code" value={code} onChange={(event) => setCode(event.target.value)} />
          </label>
          <label>
            Project name
            <input name="name" value={createName} onChange={(event) => setCreateName(event.target.value)} />
          </label>
          <label>
            Description
            <textarea
              name="description"
              value={createDescription}
              onChange={(event) => setCreateDescription(event.target.value)}
            />
          </label>
          {formError ? (
            <p role="alert" className="alert alert-error">
              {formError}
            </p>
          ) : null}
          <div className="row-actions">
            <button type="submit" disabled={submitting}>
              {submitting ? 'Creating project' : 'Create project'}
            </button>
            <Link to={`/tenants/${tenantId}/projects`}>Back to projects</Link>
          </div>
        </form>
      </section>
    )
  }

  if (onDetail) {
    return (
      <section className="stack" aria-labelledby="project-detail-heading">
        <Link to={`/tenants/${tenantId}/projects`}>Back to projects</Link>
        <h2 id="project-detail-heading">{detail.status === 'ready' ? detail.project.name : 'Project'}</h2>
        {detail.status === 'loading' ? <p role="status">Loading project</p> : null}
        {detail.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {detail.message}
          </p>
        ) : null}
        {detail.status === 'ready' ? (
          <>
            <p>
              Code <strong>{detail.project.code}</strong>
            </p>
            <p>
              Status <strong>{detail.project.status === 'archived' ? 'Archived' : 'Active'}</strong>
            </p>
            <p>{detail.project.description || 'No description.'}</p>
            <p className="muted">Created {formatWhen(detail.project.created_at)}</p>
            <p className="muted">Updated {formatWhen(detail.project.updated_at)}</p>
            {detail.project.created_by ? <p className="muted">Creator {detail.project.created_by}</p> : null}
            <form className="stack" onSubmit={(event) => void onEdit(event)} noValidate>
              <h3>Edit project</h3>
              <label>
                Project name
                <input name="name" value={editName} onChange={(event) => setEditName(event.target.value)} />
              </label>
              <label>
                Description
                <textarea
                  name="description"
                  value={editDescription}
                  onChange={(event) => setEditDescription(event.target.value)}
                />
              </label>
              {formError ? (
                <p role="alert" className="alert alert-error">
                  {formError}
                </p>
              ) : null}
              <button type="submit" disabled={submitting}>
                {submitting ? 'Saving project' : 'Save project'}
              </button>
            </form>
            {detail.project.status === 'active' ? (
              <button type="button" onClick={() => void onArchive()} disabled={submitting}>
                Archive project
              </button>
            ) : (
              <p role="status">This project is archived.</p>
            )}
          </>
        ) : null}
      </section>
    )
  }

  const empty =
    list.status === 'ready' && list.items.length === 0
      ? appliedQuery || statusFilter
        ? 'No projects match this search.'
        : 'No projects are in this organization.'
      : null

  return (
    <section className="stack" aria-labelledby="projects-heading">
      <h2 id="projects-heading">Projects</h2>
      <form className="stack" onSubmit={onSearch}>
        <label>
          Search
          <input name="search" value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <label>
          Status
          <select name="status" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </label>
        <div className="row-actions">
          <button type="submit">Search</button>
          <Link to={`/tenants/${tenantId}/projects/new`}>New project</Link>
        </div>
      </form>
      {list.status === 'loading' ? <p role="status">Loading projects</p> : null}
      {list.status === 'error' ? (
        <p role="alert" className="alert alert-error">
          {list.message}
        </p>
      ) : null}
      {empty ? <p>{empty}</p> : null}
      {list.status === 'ready' && list.items.length > 0 ? (
        <ul className="project-list">
          {list.items.map((project) => (
            <li key={project.id}>
              <Link to={`/tenants/${tenantId}/projects/${project.id}`}>
                <span>
                  {project.name}
                  <span className="muted"> {project.code}</span>
                </span>
                <span>{project.status === 'archived' ? 'Archived' : 'Active'}</span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
