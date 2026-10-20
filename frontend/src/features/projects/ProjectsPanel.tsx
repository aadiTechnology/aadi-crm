import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { EmptyState, LoadingSkeleton, StatusBadge } from '@/ui/chrome'
import {
  addProjectMember,
  ApiError,
  archiveProject,
  createProject,
  getProject,
  listEligibleProjectUsers,
  listProjectMembers,
  listProjects,
  removeProjectMember,
  updateProject,
  updateProjectMemberRole,
  type EligibleProjectUser,
  type Project,
  type ProjectMembership,
  type ProjectRole,
} from '@/services/platform'

type ListState =
  | { status: 'loading' }
  | { status: 'ready'; items: Project[] }
  | { status: 'error'; message: string }

type DetailState =
  | { status: 'loading' }
  | { status: 'ready'; project: Project }
  | { status: 'error'; message: string }

type MembersState =
  | { status: 'loading' }
  | { status: 'ready'; items: ProjectMembership[]; directoryAvailable: boolean }
  | { status: 'error'; message: string }

type EligibleState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'ready'; items: EligibleProjectUser[] }
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

function roleLabel(role: ProjectRole): string {
  return role === 'project_manager' ? 'Project manager' : 'Project member'
}

function scopeLabel(scope: 'project' | 'assigned'): string {
  return scope === 'project' ? 'All project records' : 'Assigned records'
}

function memberLabel(member: ProjectMembership): string {
  return member.email?.trim() || member.user_id
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
  const [members, setMembers] = useState<MembersState>({ status: 'loading' })
  const [eligible, setEligible] = useState<EligibleState>({ status: 'idle' })
  const [code, setCode] = useState('')
  const [createName, setCreateName] = useState('')
  const [createDescription, setCreateDescription] = useState('')
  const [editName, setEditName] = useState('')
  const [editDescription, setEditDescription] = useState('')
  const [memberUserId, setMemberUserId] = useState('')
  const [memberRole, setMemberRole] = useState<ProjectRole>('project_member')
  const [roleDrafts, setRoleDrafts] = useState<Record<string, ProjectRole>>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [memberError, setMemberError] = useState<string | null>(null)
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
    setMembers({ status: 'loading' })
    setEligible({ status: 'idle' })
    setMemberError(null)
    getProject(tenantId, projectId)
      .then(async (project) => {
        if (cancelled) {
          return
        }
        setDetail({ status: 'ready', project })
        setEditName(project.name)
        setEditDescription(project.description)
        setFormError(null)
        const listed = await listProjectMembers(tenantId, projectId)
        if (cancelled) {
          return
        }
        setMembers({
          status: 'ready',
          items: listed.items,
          directoryAvailable: listed.directory_available,
        })
        setRoleDrafts(
          Object.fromEntries(listed.items.map((member) => [member.id, member.role])),
        )
        if (!project.access.can_manage_members) {
          return
        }
        setEligible({ status: 'loading' })
        try {
          const directory = await listEligibleProjectUsers(tenantId, projectId)
          if (!cancelled) {
            setEligible({ status: 'ready', items: directory.items })
          }
        } catch (error: unknown) {
          if (!cancelled) {
            setEligible({ status: 'error', message: messageFrom(error) })
          }
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail({ status: 'error', message: messageFrom(error) })
          setMembers({ status: 'error', message: messageFrom(error) })
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

  async function refreshMembers(project: Project) {
    if (!projectId) {
      return
    }
    const listed = await listProjectMembers(tenantId, projectId)
    setMembers({
      status: 'ready',
      items: listed.items,
      directoryAvailable: listed.directory_available,
    })
    setRoleDrafts(Object.fromEntries(listed.items.map((member) => [member.id, member.role])))
    if (!project.access.can_manage_members) {
      setEligible({ status: 'idle' })
      return
    }
    const directory = await listEligibleProjectUsers(tenantId, projectId)
    setEligible({ status: 'ready', items: directory.items })
  }

  async function onAddMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!projectId || detail.status !== 'ready') {
      return
    }
    if (!memberUserId) {
      setMemberError('Choose an organization member.')
      return
    }
    setSubmitting(true)
    setMemberError(null)
    try {
      await addProjectMember(tenantId, projectId, { user_id: memberUserId, role: memberRole })
      const project = await getProject(tenantId, projectId)
      setDetail({ status: 'ready', project })
      await refreshMembers(project)
      setMemberUserId('')
      setMemberRole('project_member')
      setSubmitting(false)
    } catch (error) {
      setMemberError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onSaveRole(member: ProjectMembership) {
    if (!projectId || detail.status !== 'ready') {
      return
    }
    const role = roleDrafts[member.id] ?? member.role
    setSubmitting(true)
    setMemberError(null)
    try {
      await updateProjectMemberRole(tenantId, projectId, member.id, role)
      const project = await getProject(tenantId, projectId)
      setDetail({ status: 'ready', project })
      await refreshMembers(project)
      setSubmitting(false)
    } catch (error) {
      setMemberError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onRemove(member: ProjectMembership) {
    if (!projectId || detail.status !== 'ready') {
      return
    }
    setSubmitting(true)
    setMemberError(null)
    try {
      await removeProjectMember(tenantId, projectId, member.id)
      const project = await getProject(tenantId, projectId)
      setDetail({ status: 'ready', project })
      await refreshMembers(project)
      setSubmitting(false)
    } catch (error) {
      setMemberError(messageFrom(error))
      setSubmitting(false)
    }
  }

  if (onNew) {
    return (
      <section className="stack" aria-labelledby="project-create-heading">
        <nav className="crumbs" aria-label="Breadcrumb">
          <Link to={`/tenants/${tenantId}/projects`}>Projects</Link>
          <span aria-hidden="true">/</span>
          <span>New project</span>
        </nav>
        <div className="page-header">
          <div>
            <h2 id="project-create-heading">New project</h2>
            <p className="page-intro">Create a project inside this organization.</p>
          </div>
        </div>
        <form className="panel stack" onSubmit={(event) => void onCreate(event)} noValidate>
          <label className="required-field">
            Project code
            <input name="code" value={code} onChange={(event) => setCode(event.target.value)} />
          </label>
          <label className="required-field">
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
    const canManageProject = detail.status === 'ready' && detail.project.access.can_manage_project
    const canManageMembers = detail.status === 'ready' && detail.project.access.can_manage_members
    return (
      <section className="stack" aria-labelledby="project-detail-heading">
        <nav className="crumbs" aria-label="Breadcrumb">
          <Link to={`/tenants/${tenantId}/projects`}>Projects</Link>
          <span aria-hidden="true">/</span>
          <span>{detail.status === 'ready' ? detail.project.name : 'Project'}</span>
        </nav>
        <div className="page-header">
          <div>
            <h2 id="project-detail-heading">{detail.status === 'ready' ? detail.project.name : 'Project'}</h2>
            <p className="page-intro">
              <Link to={`/tenants/${tenantId}/projects`}>Back to projects</Link>
            </p>
          </div>
          {detail.status === 'ready' ? (
            <StatusBadge tone={detail.project.status === 'archived' ? 'warn' : 'ok'}>
              {detail.project.status === 'archived' ? 'Archived' : 'Active'}
            </StatusBadge>
          ) : null}
        </div>
        {detail.status === 'loading' ? (
          <>
            <p role="status">Loading project</p>
            <LoadingSkeleton />
          </>
        ) : null}
        {detail.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {detail.message}
          </p>
        ) : null}
        {detail.status === 'ready' ? (
          <>
            <dl className="meta-grid">
              <div>
                <dt>Code</dt>
                <dd>{detail.project.code}</dd>
              </div>
              <div>
                <dt>Your role</dt>
                <dd>
                  {detail.project.access.role
                    ? roleLabel(detail.project.access.role)
                    : canManageProject
                      ? 'Project administrator'
                      : 'No project role'}
                </dd>
              </div>
              {detail.project.access.record_scope ? (
                <div>
                  <dt>Record scope</dt>
                  <dd>{scopeLabel(detail.project.access.record_scope)}</dd>
                </div>
              ) : null}
            </dl>
            <p>{detail.project.description || 'No description.'}</p>
            <p className="muted">Created {formatWhen(detail.project.created_at)}</p>
            <p className="muted">Updated {formatWhen(detail.project.updated_at)}</p>
            {detail.project.created_by ? <p className="muted">Creator {detail.project.created_by}</p> : null}
            {canManageProject ? (
              <form className="panel stack" onSubmit={(event) => void onEdit(event)} noValidate>
                <h3>Edit project</h3>
                <label className="required-field">
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
            ) : null}
            {canManageProject && detail.project.status === 'active' ? (
              <button type="button" className="button-danger" onClick={() => void onArchive()} disabled={submitting}>
                Archive project
              </button>
            ) : null}
            {detail.project.status === 'archived' ? <p role="status">This project is archived.</p> : null}
            <section className="panel stack" aria-labelledby="project-members-heading">
              <h3 id="project-members-heading">Members</h3>
              {members.status === 'loading' ? (
                <>
                  <p role="status">Loading members</p>
                  <LoadingSkeleton />
                </>
              ) : null}
              {members.status === 'error' ? (
                <p role="alert" className="alert alert-error">
                  {members.message}
                </p>
              ) : null}
              {members.status === 'ready' && members.items.length === 0 ? (
                <EmptyState title="No members" message="No members are on this project." />
              ) : null}
              {members.status === 'ready' && members.items.length > 0 ? (
                <ul className="member-list">
                  {members.items.map((member) => {
                    const label = memberLabel(member)
                    return (
                      <li key={member.id}>
                        <p>
                          <strong>{label}</strong>
                        </p>
                        <p>
                          Role <strong>{roleLabel(member.role)}</strong>
                        </p>
                        <p>
                          Status <strong>{member.status === 'active' ? 'Active' : 'Removed'}</strong>
                        </p>
                        <p className="muted">Record scope {scopeLabel(member.scope_policy)}</p>
                        {canManageMembers && member.status === 'active' ? (
                          <div className="stack">
                            <label>
                              Project role for {label}
                              <select
                                aria-label={`Project role for ${label}`}
                                value={roleDrafts[member.id] ?? member.role}
                                onChange={(event) =>
                                  setRoleDrafts((current) => ({
                                    ...current,
                                    [member.id]: event.target.value as ProjectRole,
                                  }))
                                }
                              >
                                <option value="project_manager">Project manager</option>
                                <option value="project_member">Project member</option>
                              </select>
                            </label>
                            <div className="row-actions">
                              <button
                                type="button"
                                className="button-secondary"
                                onClick={() => void onSaveRole(member)}
                                disabled={submitting}
                              >
                                Save role for {label}
                              </button>
                              <button
                                type="button"
                                className="button-danger"
                                onClick={() => void onRemove(member)}
                                disabled={submitting}
                              >
                                Remove {label}
                              </button>
                            </div>
                          </div>
                        ) : null}
                      </li>
                    )
                  })}
                </ul>
              ) : null}
              {memberError ? (
                <p role="alert" className="alert alert-error">
                  {memberError}
                </p>
              ) : null}
              {canManageMembers && eligible.status === 'error' ? (
                <p role="alert" className="alert alert-error">
                  {eligible.message}
                </p>
              ) : null}
              {canManageMembers && eligible.status === 'loading' ? <p role="status">Loading organization members</p> : null}
              {canManageMembers && eligible.status === 'ready' ? (
                <form className="stack" onSubmit={(event) => void onAddMember(event)} noValidate>
                  <h3>Add member</h3>
                  {eligible.items.length === 0 ? (
                    <p>No other active organization members are available to add.</p>
                  ) : (
                    <>
                      <label>
                        Organization member
                        <select
                          name="member"
                          value={memberUserId}
                          onChange={(event) => setMemberUserId(event.target.value)}
                        >
                          <option value="">Select a member</option>
                          {eligible.items.map((user) => (
                            <option key={user.id} value={user.id}>
                              {user.email}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Project role
                        <select
                          name="role"
                          value={memberRole}
                          onChange={(event) => setMemberRole(event.target.value as ProjectRole)}
                        >
                          <option value="project_member">Project member</option>
                          <option value="project_manager">Project manager</option>
                        </select>
                      </label>
                      <button type="submit" disabled={submitting}>
                        {submitting ? 'Adding member' : 'Add member'}
                      </button>
                    </>
                  )}
                </form>
              ) : null}
            </section>
          </>
        ) : null}
      </section>
    )
  }

  const empty =
    list.status === 'ready' && list.items.length === 0
      ? appliedQuery || statusFilter
        ? 'No projects match this search.'
        : 'No projects are available for this sign-in.'
      : null

  return (
    <section className="stack" aria-labelledby="projects-heading">
      <div className="page-header">
        <div>
          <h2 id="projects-heading">Projects</h2>
          <p className="page-intro">Search and open the projects available to this sign-in.</p>
        </div>
        <Link className="button-link" to={`/tenants/${tenantId}/projects/new`}>
          New project
        </Link>
      </div>
      <form className="panel filters" onSubmit={onSearch}>
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
        <button type="submit">Search</button>
      </form>
      {list.status === 'loading' ? (
        <>
          <p role="status">Loading projects</p>
          <LoadingSkeleton />
        </>
      ) : null}
      {list.status === 'error' ? (
        <p role="alert" className="alert alert-error">
          {list.message}
        </p>
      ) : null}
      {empty ? (
        <EmptyState title={appliedQuery || statusFilter ? 'No matching projects' : 'No projects yet'} message={empty} />
      ) : null}
      {list.status === 'ready' && list.items.length > 0 ? (
        <ul className="project-list">
          {list.items.map((project) => (
            <li key={project.id}>
              <Link to={`/tenants/${tenantId}/projects/${project.id}`}>
                <span className="card-title">{project.name}</span>
                <span className="muted">{project.code}</span>
                {project.description ? <span>{project.description}</span> : null}
                <StatusBadge tone={project.status === 'archived' ? 'warn' : 'ok'}>
                  {project.status === 'archived' ? 'Archived' : 'Active'}
                </StatusBadge>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
