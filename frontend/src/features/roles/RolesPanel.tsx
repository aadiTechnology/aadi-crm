import { useEffect, useState, type FormEvent } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { EmptyState, LoadingSkeleton, StatusBadge } from '@/ui/chrome'
import {
  ApiError,
  assignTenantCrmRole,
  createTenantCrmRole,
  deactivateTenantCrmRole,
  grantTenantCrmRolePermission,
  listCrmPermissionCatalog,
  listTenantCrmRoleAssignments,
  listTenantCrmRolePermissions,
  listTenantCrmRoles,
  listTenantDirectoryUsers,
  removeTenantCrmRolePermission,
  revokeTenantCrmRoleAssignment,
  updateTenantCrmRole,
  type TenantCrmRole,
  type TenantCrmRoleAssignment,
  type TenantDirectoryUser,
} from '@/services/platform'

const NAME_MAX = 120
const DESCRIPTION_MAX = 2000
const BLOCKED_PERMISSIONS = new Set(['roles.manage', 'users.read', 'audit.read'])

/** Readable labels for keys the permission API returns. Unknown keys stay as returned. */
const PERMISSION_LABELS: Record<string, string> = {
  'crm.lead_management.read': 'Read leads',
  'crm.project_management.access': 'Open projects',
  'crm.project_management.manage': 'Manage projects',
  'crm.records.access': 'Open records',
}

type ListState =
  | { status: 'loading' }
  | { status: 'ready'; items: TenantCrmRole[] }
  | { status: 'error'; message: string }

type DetailState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; role: TenantCrmRole; catalog: string[]; granted: string[] }

type AssignmentState =
  | { status: 'hidden' }
  | { status: 'loading' }
  | { status: 'ready'; items: TenantCrmRoleAssignment[] }
  | { status: 'error'; message: string }

type DirectoryState =
  | { status: 'hidden' }
  | { status: 'loading' }
  | { status: 'ready'; users: TenantDirectoryUser[] }
  | { status: 'unavailable'; message: string; tone: 'info' | 'error' }

type RoleTab = 'details' | 'permissions' | 'people'

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return 'The request could not be completed.'
}

function directoryMessage(error: unknown): { message: string; tone: 'info' | 'error' } {
  if (error instanceof ApiError && error.status === 404) {
    return {
      tone: 'info',
      message:
        'A member list is not available in CRM. People already assigned stay visible from the assignment record. Choosing someone new needs that member list, and this page will not ask for an id.',
    }
  }
  if (error instanceof ApiError) {
    return { tone: 'error', message: error.message }
  }
  return {
    tone: 'error',
    message: 'The member list could not be loaded. This page will not ask for an id.',
  }
}

function formatWhen(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

function statusLabel(status: string): string {
  if (status === 'active') {
    return 'Active'
  }
  if (status === 'inactive') {
    return 'Inactive'
  }
  return status
}

function assignmentStatusLabel(status: string): string {
  if (status === 'active') {
    return 'Active'
  }
  if (status === 'revoked') {
    return 'Revoked'
  }
  return status
}

function permissionLabel(key: string): string {
  return PERMISSION_LABELS[key] ?? key
}

function permissionRows(catalog: string[], granted: string[]): string[] {
  const rows: string[] = []
  const seen = new Set<string>()
  for (const key of [...catalog, ...granted]) {
    if (!key || seen.has(key) || BLOCKED_PERMISSIONS.has(key)) {
      continue
    }
    seen.add(key)
    rows.push(key)
  }
  return rows
}

function sameKeys(left: Iterable<string>, right: Iterable<string>): boolean {
  const first = [...left].sort()
  const second = [...right].sort()
  return first.length === second.length && first.every((key, index) => key === second[index])
}

function routeNotice(state: unknown): string | null {
  if (!state || typeof state !== 'object' || !('notice' in state)) {
    return null
  }
  const value = (state as { notice?: unknown }).notice
  return typeof value === 'string' && value.trim() ? value : null
}

function RoleAccessNote() {
  return (
    <p className="page-intro">
      CRM roles control CRM access in this organization. They are separate from project manager and project member
      roles. A CRM role cannot grant role administration, user administration, or the audit log, and it cannot open a
      feature this organization has not purchased. People who have never been assigned a CRM role keep their existing
      access. Assigning a role does not, by itself, guarantee access.
    </p>
  )
}

function personLabel(userId: string, users: TenantDirectoryUser[]): string {
  return users.find((user) => user.id === userId)?.email ?? userId
}

export function RolesPanel({ tenantId, canReadUsers }: { tenantId: string; canReadUsers: boolean }) {
  const { roleId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const onNew = location.pathname.endsWith('/roles/new')
  const onDetail = Boolean(roleId) && !onNew
  const [list, setList] = useState<ListState>({ status: 'loading' })
  const [listVersion, setListVersion] = useState(0)
  const [detail, setDetail] = useState<DetailState>({ status: 'loading' })
  const [detailVersion, setDetailVersion] = useState(0)
  const [assignments, setAssignments] = useState<AssignmentState>({ status: 'hidden' })
  const [directory, setDirectory] = useState<DirectoryState>({ status: 'hidden' })
  const [assignmentVersion, setAssignmentVersion] = useState(0)
  const [tab, setTab] = useState<RoleTab>('details')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [draft, setDraft] = useState<Set<string>>(new Set())
  const [memberUserId, setMemberUserId] = useState('')
  const [confirmDeactivate, setConfirmDeactivate] = useState(false)
  const [confirmRevokeUserId, setConfirmRevokeUserId] = useState<string | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    setSubmitting(false)
    setFormError(null)
    setNotice(null)
    setConfirmDeactivate(false)
    setConfirmRevokeUserId(null)
    setTab('details')
    setMemberUserId('')
    if (onNew) {
      setName('')
      setDescription('')
    }
    if (onDetail) {
      setDetail({ status: 'loading' })
    }
  }, [location.pathname, onDetail, onNew])

  useEffect(() => {
    if (onNew || onDetail) {
      return
    }
    let cancelled = false
    setList({ status: 'loading' })
    listTenantCrmRoles(tenantId)
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
  }, [listVersion, onDetail, onNew, tenantId])

  useEffect(() => {
    if (!onDetail || !roleId) {
      return
    }
    let cancelled = false
    setDetail({ status: 'loading' })
    setAssignments(canReadUsers ? { status: 'loading' } : { status: 'hidden' })
    setDirectory(canReadUsers ? { status: 'loading' } : { status: 'hidden' })
    Promise.all([
      listTenantCrmRoles(tenantId),
      listCrmPermissionCatalog(tenantId),
      listTenantCrmRolePermissions(tenantId, roleId),
    ])
      .then(([listed, catalog, permissions]) => {
        if (cancelled) {
          return
        }
        const role = listed.items.find((item) => item.id === roleId)
        if (!role) {
          setDetail({ status: 'error', message: 'The requested resource was not found.' })
          return
        }
        const granted = permissions.items.filter((key) => !BLOCKED_PERMISSIONS.has(key))
        setDetail({
          status: 'ready',
          role,
          catalog: catalog.items.filter((key) => !BLOCKED_PERMISSIONS.has(key)),
          granted,
        })
        setName(role.name)
        setDescription(role.description)
        setDraft(new Set(granted))
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDetail({ status: 'error', message: messageFrom(error) })
        }
      })
    return () => {
      cancelled = true
    }
  }, [canReadUsers, detailVersion, onDetail, roleId, tenantId])

  const readyRoleId = detail.status === 'ready' ? detail.role.id : null

  useEffect(() => {
    if (!onDetail || !roleId || readyRoleId !== roleId) {
      return
    }
    if (!canReadUsers) {
      setAssignments({ status: 'hidden' })
      setDirectory({ status: 'hidden' })
      return
    }
    let cancelled = false
    setAssignments({ status: 'loading' })
    setDirectory({ status: 'loading' })
    listTenantCrmRoleAssignments(tenantId, roleId)
      .then((result) => {
        if (!cancelled) {
          setAssignments({ status: 'ready', items: result.items })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setAssignments({ status: 'error', message: messageFrom(error) })
        }
      })
    listTenantDirectoryUsers(tenantId)
      .then((users) => {
        if (!cancelled) {
          setDirectory({ status: 'ready', users })
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          const unavailable = directoryMessage(error)
          setDirectory({ status: 'unavailable', message: unavailable.message, tone: unavailable.tone })
        }
      })
    return () => {
      cancelled = true
    }
  }, [assignmentVersion, canReadUsers, onDetail, readyRoleId, roleId, tenantId])

  function validateRole(nextName: string, nextDescription: string): string | null {
    if (!nextName) {
      return 'Role name is required.'
    }
    if (nextName.length > NAME_MAX) {
      return 'Role name is too long.'
    }
    if (nextDescription.length > DESCRIPTION_MAX) {
      return 'Description is too long.'
    }
    return null
  }

  async function onCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting) {
      return
    }
    const nextName = name.trim()
    const nextDescription = description.trim()
    const validation = validateRole(nextName, nextDescription)
    if (validation) {
      setFormError(validation)
      return
    }
    setSubmitting(true)
    setFormError(null)
    try {
      const created = await createTenantCrmRole(tenantId, { name: nextName, description: nextDescription })
      navigate(`/tenants/${tenantId}/roles/${created.id}`, { state: { notice: 'Role created.' } })
    } catch (error: unknown) {
      setFormError(messageFrom(error))
      setSubmitting(false)
    }
  }

  async function onSaveRole(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || detail.status !== 'ready' || !roleId) {
      return
    }
    const nextName = name.trim()
    const nextDescription = description.trim()
    const validation = validateRole(nextName, nextDescription)
    if (validation) {
      setFormError(validation)
      return
    }
    if (nextName === detail.role.name && nextDescription === detail.role.description) {
      setNotice('No role changes to save.')
      setFormError(null)
      return
    }
    setSubmitting(true)
    setFormError(null)
    setNotice(null)
    try {
      const updated = await updateTenantCrmRole(tenantId, roleId, {
        name: nextName,
        description: nextDescription,
      })
      setDetail((current) => (current.status === 'ready' ? { ...current, role: updated } : current))
      setName(updated.name)
      setDescription(updated.description)
      setNotice('Role saved.')
    } catch (error: unknown) {
      setFormError(messageFrom(error))
    } finally {
      setSubmitting(false)
    }
  }

  async function onDeactivate() {
    if (submitting || detail.status !== 'ready' || !roleId || detail.role.status !== 'active') {
      return
    }
    setSubmitting(true)
    setFormError(null)
    setNotice(null)
    try {
      const updated = await deactivateTenantCrmRole(tenantId, roleId)
      setDetail((current) => (current.status === 'ready' ? { ...current, role: updated } : current))
      setConfirmDeactivate(false)
      setNotice('Role deactivated. The role record and its assignment history remain.')
    } catch (error: unknown) {
      setFormError(messageFrom(error))
    } finally {
      setSubmitting(false)
    }
  }

  async function onSavePermissions(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || detail.status !== 'ready' || !roleId || detail.role.status !== 'active') {
      return
    }
    const granted = new Set(detail.granted)
    const desired = new Set([...draft].filter((key) => !BLOCKED_PERMISSIONS.has(key)))
    const toRemove = [...granted].filter((key) => !desired.has(key))
    const toAdd = [...desired].filter((key) => !granted.has(key))
    if (toRemove.length === 0 && toAdd.length === 0) {
      setNotice('No permission changes to save.')
      setFormError(null)
      return
    }
    setSubmitting(true)
    setFormError(null)
    setNotice(null)
    try {
      for (const key of toRemove) {
        await removeTenantCrmRolePermission(tenantId, roleId, key)
      }
      for (const key of toAdd) {
        await grantTenantCrmRolePermission(tenantId, roleId, key)
      }
      const confirmed = await listTenantCrmRolePermissions(tenantId, roleId)
      const nextGranted = confirmed.items.filter((key) => !BLOCKED_PERMISSIONS.has(key))
      setDetail((current) => (current.status === 'ready' ? { ...current, granted: nextGranted } : current))
      setDraft(new Set(nextGranted))
      setNotice('Permissions saved.')
    } catch (error: unknown) {
      setFormError(messageFrom(error))
      try {
        const confirmed = await listTenantCrmRolePermissions(tenantId, roleId)
        const nextGranted = confirmed.items.filter((key) => !BLOCKED_PERMISSIONS.has(key))
        setDetail((current) =>
          current.status === 'ready' ? { ...current, granted: nextGranted } : current,
        )
        setDraft(new Set(nextGranted))
      } catch {
        // Keep the save error. The next visit reloads the permission list.
      }
    } finally {
      setSubmitting(false)
    }
  }

  async function onAssign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting || detail.status !== 'ready' || !roleId || detail.role.status !== 'active') {
      return
    }
    if (!memberUserId) {
      setFormError('Select a person.')
      return
    }
    setSubmitting(true)
    setFormError(null)
    setNotice(null)
    try {
      await assignTenantCrmRole(tenantId, roleId, memberUserId)
      setMemberUserId('')
      setAssignmentVersion((current) => current + 1)
      setNotice('Role assigned.')
    } catch (error: unknown) {
      setFormError(messageFrom(error))
    } finally {
      setSubmitting(false)
    }
  }

  async function onRevoke(userId: string) {
    if (submitting || detail.status !== 'ready' || !roleId || detail.role.status !== 'active') {
      return
    }
    setSubmitting(true)
    setFormError(null)
    setNotice(null)
    try {
      await revokeTenantCrmRoleAssignment(tenantId, roleId, userId)
      setConfirmRevokeUserId(null)
      setAssignmentVersion((current) => current + 1)
      setNotice('Role revoked. The assignment record stays in the list.')
    } catch (error: unknown) {
      setFormError(messageFrom(error))
    } finally {
      setSubmitting(false)
    }
  }

  const displayedNotice = notice ?? routeNotice(location.state)
  const directoryUsers = directory.status === 'ready' ? directory.users : []

  if (onNew) {
    return (
      <section className="stack" aria-labelledby="role-create-heading">
        <p className="crumbs">
          <Link to={`/tenants/${tenantId}/roles`}>CRM roles</Link>
          <span aria-hidden="true">/</span>
          <span>New role</span>
        </p>
        <div>
          <h2 id="role-create-heading">New CRM role</h2>
          <RoleAccessNote />
        </div>
        <form className="panel stack" onSubmit={(event) => void onCreate(event)} noValidate>
          <label>
            Role name
            <input
              name="name"
              value={name}
              maxLength={NAME_MAX}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Description
            <textarea
              name="description"
              value={description}
              maxLength={DESCRIPTION_MAX}
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>
          {formError ? (
            <p role="alert" className="alert alert-error">
              {formError}
            </p>
          ) : null}
          <button type="submit" disabled={submitting}>
            {submitting ? 'Creating role' : 'Create role'}
          </button>
        </form>
      </section>
    )
  }

  if (onDetail) {
    const role = detail.status === 'ready' ? detail.role : null
    const activeRole = role?.status === 'active'
    const rows = role ? permissionRows(detail.status === 'ready' ? detail.catalog : [], detail.status === 'ready' ? detail.granted : []) : []
    const dirty = detail.status === 'ready' && !sameKeys(draft, detail.granted)
    const activeAssigned = new Set(
      assignments.status === 'ready'
        ? assignments.items.filter((item) => item.status === 'active').map((item) => item.user_id)
        : [],
    )
    const choices =
      directory.status === 'ready'
        ? directory.users.filter(
            (user) => user.identityActive && user.membershipStatus === 'active' && !activeAssigned.has(user.id),
          )
        : []

    return (
      <section className="stack" aria-labelledby="role-detail-heading">
        <p className="crumbs">
          <Link to={`/tenants/${tenantId}/roles`}>CRM roles</Link>
          <span aria-hidden="true">/</span>
          <span>{role?.name ?? 'Role'}</span>
        </p>
        {detail.status === 'loading' ? (
          <>
            <p role="status">Loading CRM role</p>
            <LoadingSkeleton />
          </>
        ) : null}
        {detail.status === 'error' ? (
          <p role="alert" className="alert alert-error">
            {detail.message}{' '}
            <button type="button" onClick={() => setDetailVersion((current) => current + 1)}>
              Retry
            </button>
          </p>
        ) : null}
        {role ? (
          <>
            <div className="page-header">
              <div>
                <h2 id="role-detail-heading">{role.name}</h2>
                <RoleAccessNote />
              </div>
              <StatusBadge tone={role.status === 'active' ? 'ok' : 'neutral'}>{statusLabel(role.status)}</StatusBadge>
            </div>
            {displayedNotice ? (
              <p role="status" className="alert alert-ok">
                {displayedNotice}
              </p>
            ) : null}
            {formError ? (
              <p role="alert" className="alert alert-error">
                {formError}
              </p>
            ) : null}
            <div className="row-actions" role="tablist" aria-label="CRM role sections">
              <button
                type="button"
                role="tab"
                id="role-tab-details"
                className={tab === 'details' ? undefined : 'button-secondary'}
                aria-selected={tab === 'details'}
                aria-controls="role-panel-details"
                onClick={() => setTab('details')}
              >
                Details
              </button>
              <button
                type="button"
                role="tab"
                id="role-tab-permissions"
                className={tab === 'permissions' ? undefined : 'button-secondary'}
                aria-selected={tab === 'permissions'}
                aria-controls="role-panel-permissions"
                onClick={() => setTab('permissions')}
              >
                Permissions
              </button>
              <button
                type="button"
                role="tab"
                id="role-tab-people"
                className={tab === 'people' ? undefined : 'button-secondary'}
                aria-selected={tab === 'people'}
                aria-controls="role-panel-people"
                onClick={() => setTab('people')}
              >
                People
              </button>
            </div>
            <div role="tabpanel" id="role-panel-details" aria-labelledby="role-tab-details" hidden={tab !== 'details'}>
              <form className="panel stack" onSubmit={(event) => void onSaveRole(event)} noValidate>
                <dl className="meta-grid">
                  <div>
                    <dt>Status</dt>
                    <dd>{statusLabel(role.status)}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{formatWhen(role.updated_at)}</dd>
                  </div>
                </dl>
                <label>
                  Role name
                  <input name="name" value={name} maxLength={NAME_MAX} onChange={(event) => setName(event.target.value)} />
                </label>
                <label>
                  Description
                  <textarea
                    name="description"
                    value={description}
                    maxLength={DESCRIPTION_MAX}
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </label>
                <div className="row-actions">
                  <button type="submit" disabled={submitting}>
                    {submitting ? 'Saving role' : 'Save role'}
                  </button>
                  {activeRole && !confirmDeactivate ? (
                    <button
                      type="button"
                      className="button-danger"
                      disabled={submitting}
                      onClick={() => setConfirmDeactivate(true)}
                    >
                      Deactivate role
                    </button>
                  ) : null}
                </div>
                {activeRole && confirmDeactivate ? (
                  <div className="stack">
                    <p>
                      Deactivating keeps this role and its assignment history. It is not a delete. An inactive role
                      cannot receive new people or new permissions, and it does not grant its CRM permissions.
                    </p>
                    <div className="row-actions">
                      <button type="button" className="button-danger" disabled={submitting} onClick={() => void onDeactivate()}>
                        {submitting ? 'Deactivating role' : 'Confirm deactivation'}
                      </button>
                      <button
                        type="button"
                        className="button-secondary"
                        disabled={submitting}
                        onClick={() => setConfirmDeactivate(false)}
                      >
                        Keep role active
                      </button>
                    </div>
                  </div>
                ) : null}
                {!activeRole ? (
                  <p>This role is inactive. You can still rename it. Deactivation is not a delete.</p>
                ) : null}
              </form>
            </div>
            <div
              role="tabpanel"
              id="role-panel-permissions"
              aria-labelledby="role-tab-permissions"
              hidden={tab !== 'permissions'}
            >
              <form className="panel stack" onSubmit={(event) => void onSavePermissions(event)}>
                <p className="page-intro">
                  Permissions come from this organization&apos;s CRM permission list. Saving adds or removes only the
                  permissions you change.
                </p>
                {rows.length === 0 ? (
                  <EmptyState
                    title="No CRM permissions"
                    message="The permission list did not include any CRM permissions that can be assigned to a role."
                  />
                ) : (
                  <ul className="field-list">
                    {rows.map((key) => (
                      <li key={key}>
                        <label>
                          <input
                            type="checkbox"
                            checked={draft.has(key)}
                            disabled={!activeRole || submitting}
                            onChange={() => {
                              setDraft((current) => {
                                const next = new Set(current)
                                if (next.has(key)) {
                                  next.delete(key)
                                } else {
                                  next.add(key)
                                }
                                return next
                              })
                            }}
                          />
                          <span>
                            {permissionLabel(key)} <span className="muted">{key}</span>
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
                {activeRole ? (
                  <button type="submit" disabled={submitting || !dirty}>
                    {submitting ? 'Saving permissions' : 'Save permissions'}
                  </button>
                ) : (
                  <p>This role is inactive, so its permissions cannot be changed.</p>
                )}
              </form>
            </div>
            <div role="tabpanel" id="role-panel-people" aria-labelledby="role-tab-people" hidden={tab !== 'people'}>
              <div className="panel stack">
                <h3>People with this role</h3>
                {!canReadUsers || assignments.status === 'hidden' ? (
                  <p>
                    Viewing and changing who has this role requires permission to read organization users. Managing CRM
                    roles does not include that permission.
                  </p>
                ) : null}
                {assignments.status === 'loading' ? <p role="status">Loading assignments</p> : null}
                {assignments.status === 'error' ? (
                  <p role="alert" className="alert alert-error">
                    {assignments.message}{' '}
                    <button type="button" onClick={() => setAssignmentVersion((current) => current + 1)}>
                      Retry
                    </button>
                  </p>
                ) : null}
                {assignments.status === 'ready' && assignments.items.length === 0 ? (
                  <EmptyState
                    title="No assignments"
                    message={
                      activeRole
                        ? 'Nobody has this CRM role yet. Assigning it does not open a feature this organization has not purchased.'
                        : 'Nobody has this role. An inactive role cannot be assigned.'
                    }
                  />
                ) : null}
                {assignments.status === 'ready' && assignments.items.length > 0 ? (
                  <div className="table-wrap">
                    <table className="data-table">
                      <caption>Assignment history for this CRM role. Revoked rows stay visible.</caption>
                      <thead>
                        <tr>
                          <th scope="col">Person</th>
                          <th scope="col">Status</th>
                          <th scope="col">Updated</th>
                          <th scope="col">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {assignments.items.map((item) => {
                          const label = personLabel(item.user_id, directoryUsers)
                          const canRevoke = activeRole && item.status === 'active'
                          return (
                            <tr key={item.id}>
                              <td>{label}</td>
                              <td>
                                <StatusBadge tone={item.status === 'active' ? 'ok' : item.status === 'revoked' ? 'warn' : 'neutral'}>
                                  {assignmentStatusLabel(item.status)}
                                </StatusBadge>
                              </td>
                              <td>{formatWhen(item.updated_at)}</td>
                              <td>
                                {canRevoke && confirmRevokeUserId !== item.user_id ? (
                                  <button
                                    type="button"
                                    className="button-danger"
                                    disabled={submitting}
                                    onClick={() => setConfirmRevokeUserId(item.user_id)}
                                  >
                                    Revoke role for {label}
                                  </button>
                                ) : null}
                                {canRevoke && confirmRevokeUserId === item.user_id ? (
                                  <div className="stack">
                                    <p>
                                      Revoke this CRM role for {label}? The assignment record stays. This does not
                                      remove the person from the organization.
                                    </p>
                                    <div className="row-actions">
                                      <button
                                        type="button"
                                        className="button-danger"
                                        disabled={submitting}
                                        onClick={() => void onRevoke(item.user_id)}
                                      >
                                        {submitting ? 'Revoking role' : `Confirm revoke for ${label}`}
                                      </button>
                                      <button
                                        type="button"
                                        className="button-secondary"
                                        disabled={submitting}
                                        onClick={() => setConfirmRevokeUserId(null)}
                                      >
                                        Cancel revoke
                                      </button>
                                    </div>
                                  </div>
                                ) : null}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                {!activeRole && canReadUsers ? (
                  <p>This role is inactive, so people cannot be assigned or removed here.</p>
                ) : null}
                {activeRole && canReadUsers && directory.status === 'loading' ? (
                  <p role="status">Loading organization members</p>
                ) : null}
                {activeRole && canReadUsers && directory.status === 'unavailable' ? (
                  <p role={directory.tone === 'error' ? 'alert' : 'status'} className={directory.tone === 'error' ? 'alert alert-error' : 'panel'}>
                    {directory.message}
                  </p>
                ) : null}
                {activeRole && canReadUsers && directory.status === 'ready' ? (
                  <form className="stack" onSubmit={(event) => void onAssign(event)} noValidate>
                    <h3>Assign this role</h3>
                    {choices.length === 0 ? (
                      <p>No other active organization members are available to assign.</p>
                    ) : (
                      <>
                        <label>
                          Organization member
                          <select
                            name="member"
                            value={memberUserId}
                            onChange={(event) => setMemberUserId(event.target.value)}
                          >
                            <option value="">Select a person</option>
                            {choices.map((user) => (
                              <option key={user.id} value={user.id}>
                                {user.email}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button type="submit" disabled={submitting || !memberUserId}>
                          {submitting ? 'Assigning role' : 'Assign role'}
                        </button>
                      </>
                    )}
                  </form>
                ) : null}
              </div>
            </div>
          </>
        ) : null}
      </section>
    )
  }

  return (
    <section className="stack" aria-labelledby="roles-heading">
      <div className="page-header">
        <div>
          <h2 id="roles-heading">CRM roles</h2>
          <RoleAccessNote />
        </div>
        <Link className="button-link" to={`/tenants/${tenantId}/roles/new`}>
          New CRM role
        </Link>
      </div>
      {displayedNotice ? (
        <p role="status" className="alert alert-ok">
          {displayedNotice}
        </p>
      ) : null}
      {list.status === 'loading' ? (
        <>
          <p role="status">Loading CRM roles</p>
          <LoadingSkeleton />
        </>
      ) : null}
      {list.status === 'error' ? (
        <p role="alert" className="alert alert-error">
          {list.message}{' '}
          <button type="button" onClick={() => setListVersion((current) => current + 1)}>
            Retry
          </button>
        </p>
      ) : null}
      {list.status === 'ready' && list.items.length === 0 ? (
        <EmptyState
          title="No CRM roles yet"
          message="Create a role when someone needs CRM access that is different from a project role."
        />
      ) : null}
      {list.status === 'ready' && list.items.length > 0 ? (
        <ul className="project-list">
          {list.items.map((item) => (
            <li key={item.id}>
              <Link to={`/tenants/${tenantId}/roles/${item.id}`}>
                <span className="card-title">{item.name}</span>
                {item.description ? <span>{item.description}</span> : null}
                <StatusBadge tone={item.status === 'active' ? 'ok' : 'neutral'}>{statusLabel(item.status)}</StatusBadge>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}
