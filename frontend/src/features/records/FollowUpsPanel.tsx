import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'

import { EmptyState, LoadingSkeleton, StatusBadge } from '@/ui/chrome'
import {
  ApiError,
  cancelFollowUp,
  completeFollowUp,
  createFollowUp,
  getProject,
  listActivities,
  listFollowUpQueue,
  listFollowUps,
  listProjectMembers,
  listProjects,
  updateFollowUp,
  type ActivityItem,
  type FollowUp,
  type FollowUpInput,
  type FollowUpQueueName,
  type Project,
  type ProjectMembership,
} from '@/services/platform'

const TASK_TYPES = [
  { value: 'call', label: 'Call' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'email', label: 'Email' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'note', label: 'Note' },
]
const CALL_STATUSES = [
  { value: 'connected', label: 'Connected' },
  { value: 'busy', label: 'Busy' },
  { value: 'not_connected', label: 'Not connected' },
  { value: 'switched_off', label: 'Switched off' },
  { value: 'not_valid', label: 'Not valid' },
]
const QUEUES: { id: FollowUpQueueName; label: string; empty: string }[] = [
  { id: 'overdue', label: 'Overdue', empty: 'No follow-ups are overdue.' },
  { id: 'today', label: 'Today', empty: 'No follow-ups are due today.' },
  { id: 'upcoming', label: 'Upcoming', empty: 'No follow-ups are upcoming.' },
]

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return 'The request could not be completed.'
}

function fieldsFrom(error: unknown): Record<string, string> {
  return error instanceof ApiError ? error.fields : {}
}

function formatWhen(value: string, timeZone: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat('en-IN', { timeZone, dateStyle: 'medium', timeStyle: 'short' }).format(parsed)
}

function ownerLabel(members: ProjectMembership[], userId: string): string {
  const member = members.find((item) => item.user_id === userId && item.status === 'active')
  return member?.email || 'Project member'
}

export function RecordFollowUps({
  tenantId,
  projectId,
  recordId,
  readOnly,
}: {
  tenantId: string
  projectId: string
  recordId: string
  readOnly: boolean
}) {
  const [reload, setReload] = useState(0)
  const [activityState, setActivityState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [activities, setActivities] = useState<ActivityItem[]>([])
  const [activityError, setActivityError] = useState<string | null>(null)
  const [followState, setFollowState] = useState<'loading' | 'ready' | 'error'>('loading')
  const [followUps, setFollowUps] = useState<FollowUp[]>([])
  const [followError, setFollowError] = useState<string | null>(null)
  const [members, setMembers] = useState<ProjectMembership[]>([])
  const [taskType, setTaskType] = useState('')

  useEffect(() => {
    let cancelled = false
    setActivityState('loading')
    setActivityError(null)
    listActivities(tenantId, projectId, recordId, { limit: 25, offset: 0 })
      .then((page) => {
        if (!cancelled) {
          setActivities(page.items)
          setActivityState('ready')
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setActivityError(messageFrom(caught))
          setActivityState('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId, recordId, reload])

  useEffect(() => {
    let cancelled = false
    setFollowState('loading')
    setFollowError(null)
    Promise.all([
      listFollowUps(tenantId, projectId, recordId, { taskType, limit: 25, offset: 0 }),
      listProjectMembers(tenantId, projectId),
    ])
      .then(([page, membership]) => {
        if (!cancelled) {
          setFollowUps(page.items)
          setMembers(membership.items.filter((item) => item.status === 'active'))
          setFollowState('ready')
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setFollowError(messageFrom(caught))
          setFollowState('error')
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId, recordId, taskType, reload])

  return (
    <div className="stack">
      <section className="stack" aria-labelledby="activity-heading">
        <h3 id="activity-heading">Activity</h3>
        {activityState === 'loading' ? <p role="status">Loading activity</p> : null}
        {activityState === 'loading' ? <LoadingSkeleton /> : null}
        {activityError ? (
          <p role="alert" className="alert alert-error">
            {activityError}{' '}
            <button type="button" onClick={() => setReload((current) => current + 1)}>
              Retry
            </button>
          </p>
        ) : null}
        {activityState === 'ready' && activities.length === 0 ? (
          <EmptyState title="No activity yet" message="No activity has been recorded for this record." />
        ) : null}
        {activityState === 'ready' && activities.length > 0 ? (
          <ol className="timeline">
            {activities.map((item) => (
              <li key={item.id} className="timeline-item">
                <p>
                  <strong>{item.label}</strong>
                </p>
                <p>{formatWhen(item.occurred_at, 'Asia/Kolkata')}</p>
                <p>By {ownerLabel(members, item.actor_id)}</p>
                <p>{item.summary}</p>
              </li>
            ))}
          </ol>
        ) : null}
      </section>
      <section className="stack" aria-labelledby="follow-ups-heading">
        <h3 id="follow-ups-heading">Follow-ups</h3>
        <label>
          Show task type
          <select aria-label="Show task type" value={taskType} onChange={(event) => setTaskType(event.target.value)}>
            <option value="">All types</option>
            {TASK_TYPES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {followState === 'loading' ? <p role="status">Loading follow-ups</p> : null}
        {followError ? (
          <p role="alert" className="alert alert-error">
            {followError}{' '}
            <button type="button" onClick={() => setReload((current) => current + 1)}>
              Retry follow-ups
            </button>
          </p>
        ) : null}
        {followState === 'ready' && followUps.length === 0 ? (
          <EmptyState title="No follow-ups" message="Add a follow-up for this record. There is no fixed number of follow-ups." />
        ) : null}
        {followUps.map((item) => (
          <FollowUpCard
            key={item.id}
            tenantId={tenantId}
            projectId={projectId}
            recordId={recordId}
            item={item}
            members={members}
            readOnly={readOnly}
            onChanged={() => setReload((current) => current + 1)}
          />
        ))}
        {readOnly || followState !== 'ready' ? null : (
          <FollowUpEditor
            members={members}
            submitLabel="Add follow-up"
            onSubmit={(input) => createFollowUp(tenantId, projectId, recordId, input)}
            onSaved={() => setReload((current) => current + 1)}
          />
        )}
      </section>
    </div>
  )
}

function FollowUpCard({
  tenantId,
  projectId,
  recordId,
  item,
  members,
  readOnly,
  onChanged,
}: {
  tenantId: string
  projectId: string
  recordId: string
  item: FollowUp
  members: ProjectMembership[]
  readOnly: boolean
  onChanged: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [outcome, setOutcome] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const tone = item.status === 'completed' ? 'ok' : item.status === 'cancelled' ? 'neutral' : 'info'

  async function finish(action: 'complete' | 'cancel') {
    if (pending) {
      return
    }
    setPending(true)
    setError(null)
    try {
      const input = { expected_updated_at: item.updated_at, outcome }
      if (action === 'complete') {
        await completeFollowUp(tenantId, projectId, recordId, item.id, input)
      } else {
        await cancelFollowUp(tenantId, projectId, recordId, item.id, input)
      }
      setOutcome('')
      onChanged()
    } catch (caught) {
      setError(messageFrom(caught))
      setPending(false)
    }
  }

  return (
    <article className="timeline-item" aria-label={`${item.task_type_label} follow-up`}>
      <p>
        <strong>{item.task_type_label}</strong> <StatusBadge tone={tone}>{item.status_label}</StatusBadge>
      </p>
      <p>
        Due {item.due_date} {item.due_time} India Standard Time. Owner {ownerLabel(members, item.owner_user_id)}.
      </p>
      {item.call_status_label ? <p>Call status {item.call_status_label}.</p> : null}
      {item.summary ? <p>{item.summary}</p> : null}
      {item.outcome ? <p>Outcome {item.outcome}</p> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}
        </p>
      ) : null}
      {readOnly || item.status !== 'open' ? null : (
        <div className="follow-up-actions">
          <button type="button" onClick={() => setEditing((current) => !current)}>
            {editing ? 'Close editor' : `Edit ${item.task_type_label}`}
          </button>
          <button type="button" onClick={() => void finish('cancel')} disabled={pending}>
            Cancel {item.task_type_label}
          </button>
        </div>
      )}
      {editing && item.status === 'open' ? (
        <FollowUpEditor
          members={members}
          initial={item}
          submitLabel={`Save ${item.task_type_label}`}
          onSubmit={(input) =>
            updateFollowUp(tenantId, projectId, recordId, item.id, {
              ...input,
              expected_updated_at: item.updated_at,
            })
          }
          onSaved={() => {
            setEditing(false)
            onChanged()
          }}
        />
      ) : null}
      {readOnly || item.status !== 'open' ? null : (
        <form
          className="follow-up-form"
          onSubmit={(event) => {
            event.preventDefault()
            void finish('complete')
          }}
        >
          <label>
            Outcome
            <textarea aria-label="Outcome" value={outcome} onChange={(event) => setOutcome(event.target.value)} required maxLength={500} />
          </label>
          <button type="submit" disabled={pending}>
            Complete {item.task_type_label}
          </button>
        </form>
      )}
    </article>
  )
}

function FollowUpEditor({
  members,
  initial,
  submitLabel,
  onSubmit,
  onSaved,
}: {
  members: ProjectMembership[]
  initial?: FollowUp
  submitLabel: string
  onSubmit: (input: FollowUpInput) => Promise<FollowUp>
  onSaved: () => void
}) {
  const [taskType, setTaskType] = useState(initial?.task_type ?? 'call')
  const [ownerId, setOwnerId] = useState(initial?.owner_user_id ?? members[0]?.user_id ?? '')
  const [dueDate, setDueDate] = useState(initial?.due_date ?? '')
  const [dueTime, setDueTime] = useState(initial?.due_time ?? '')
  const [summary, setSummary] = useState(initial?.summary ?? '')
  const [callStatus, setCallStatus] = useState(initial?.call_status ?? 'connected')
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [pending, setPending] = useState(false)

  async function onSubmitForm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (pending) {
      return
    }
    setPending(true)
    setError(null)
    setFieldErrors({})
    try {
      await onSubmit({
        task_type: taskType,
        owner_user_id: ownerId,
        due_date: dueDate,
        due_time: dueTime,
        summary,
        call_status: taskType === 'call' ? callStatus : null,
      })
      if (!initial) {
        setSummary('')
        setDueDate('')
        setDueTime('')
      }
      onSaved()
    } catch (caught) {
      setError(messageFrom(caught))
      setFieldErrors(fieldsFrom(caught))
      setPending(false)
    }
  }

  return (
    <form className="follow-up-form" onSubmit={(event) => void onSubmitForm(event)}>
      <p>Due date and time use India Standard Time.</p>
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}
        </p>
      ) : null}
      <label>
        Task type
        <select aria-label="Task type" value={taskType} onChange={(event) => setTaskType(event.target.value)} required>
          {TASK_TYPES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        Owner
        <select aria-label="Owner" value={ownerId} onChange={(event) => setOwnerId(event.target.value)} required>
          <option value="">Choose an owner</option>
          {members.map((member) => (
            <option key={member.user_id} value={member.user_id}>
              {member.email || 'Project member'}
            </option>
          ))}
        </select>
      </label>
      {fieldErrors.owner_user_id ? <p role="alert">{fieldErrors.owner_user_id}</p> : null}
      <label>
        Due date
        <input aria-label="Due date" type="date" value={dueDate} onChange={(event) => setDueDate(event.target.value)} required />
      </label>
      {fieldErrors.due_date ? <p role="alert">{fieldErrors.due_date}</p> : null}
      <label>
        Due time
        <input aria-label="Due time" type="time" value={dueTime} onChange={(event) => setDueTime(event.target.value)} required />
      </label>
      {fieldErrors.due_time ? <p role="alert">{fieldErrors.due_time}</p> : null}
      {taskType === 'call' ? (
        <label>
          Call status
          <select aria-label="Call status" value={callStatus} onChange={(event) => setCallStatus(event.target.value)} required>
            {CALL_STATUSES.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      <label>
        Discussion summary
        <textarea aria-label="Discussion summary" value={summary} onChange={(event) => setSummary(event.target.value)} maxLength={2000} />
      </label>
      <button type="submit" disabled={pending || members.length === 0}>
        {pending ? 'Saving follow-up' : submitLabel}
      </button>
    </form>
  )
}

export function FollowUpQueues({ tenantId }: { tenantId: string }) {
  const { projectId } = useParams()
  const [params] = useSearchParams()
  const requested = params.get('queue')
  const queue: FollowUpQueueName = requested === 'overdue' || requested === 'upcoming' ? requested : 'today'
  const fromKpis = params.get('from') === 'kpis'
  const ownerParam = params.get('owner_user_id') ?? ''
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [project, setProject] = useState<Project | null>(null)
  const [members, setMembers] = useState<ProjectMembership[]>([])
  const [ownerUserId, setOwnerUserId] = useState(ownerParam)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [items, setItems] = useState<FollowUp[]>([])
  const [total, setTotal] = useState(0)
  const [reload, setReload] = useState(0)
  const selected = QUEUES.find((item) => item.id === queue) ?? QUEUES[1]

  useEffect(() => {
    setOwnerUserId(ownerParam)
  }, [ownerParam])

  useEffect(() => {
    setOffset(0)
  }, [queue, ownerUserId, projectId])

  useEffect(() => {
    if (projectId) {
      return
    }
    let cancelled = false
    setLoading(true)
    listProjects(tenantId, { q: '', status: '' })
      .then((page) => {
        if (!cancelled) {
          setProjects(page.items)
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
  }, [projectId, tenantId, reload])

  useEffect(() => {
    if (!projectId) {
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    const requests: Promise<unknown>[] = [
      getProject(tenantId, projectId),
      listFollowUpQueue(tenantId, projectId, {
        queue,
        ownerUserId: ownerUserId || undefined,
        limit: 25,
        offset,
      }),
      listProjectMembers(tenantId, projectId).catch(() => ({ items: [] })),
    ]
    Promise.all(requests)
      .then((loaded) => {
        if (cancelled) {
          return
        }
        setProject(loaded[0] as Project)
        const page = loaded[1] as { items: FollowUp[]; total: number }
        setItems(page.items)
        setTotal(page.total)
        setMembers(((loaded[2] as { items: ProjectMembership[] }).items ?? []).filter((item) => item.status === 'active'))
        setLoading(false)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(messageFrom(caught))
          setItems([])
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId, queue, ownerUserId, offset, reload])

  if (!projectId) {
    return (
      <section className="stack" aria-labelledby="follow-up-projects-heading">
        <h2 id="follow-up-projects-heading">Follow-ups</h2>
        <p className="page-intro">Choose a project to see Overdue, Today, and Upcoming follow-ups.</p>
        {loading ? <p role="status">Loading follow-ups</p> : null}
        {error ? (
          <p role="alert" className="alert alert-error">
            {error}
          </p>
        ) : null}
        {projects && projects.length === 0 ? (
          <EmptyState title="No projects" message="Create a project before reviewing follow-ups." />
        ) : null}
        <ul className="project-list">
          {(projects ?? []).map((item) => (
            <li key={item.id}>
              <Link to={`/tenants/${tenantId}/follow-ups/${item.id}`}>{item.name}</Link>
            </li>
          ))}
        </ul>
      </section>
    )
  }

  const canFilterOwner = project?.access.record_scope === 'project'

  return (
    <section className="stack" aria-labelledby="queue-heading">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/tenants/${tenantId}/follow-ups`}>Follow-ups</Link>
        <span aria-hidden="true">/</span>
        <span>{project?.name ?? 'Project'}</span>
      </nav>
      {fromKpis ? (
        <p>
          <Link to={`/tenants/${tenantId}/kpis/${projectId}`}>Back to project KPIs</Link>
        </p>
      ) : null}
      <h2 id="queue-heading">{selected.id === 'today' ? 'Follow-ups due today' : `${selected.label} follow-ups`}</h2>
      <p>Queues use India Standard Time. A follow-up is in one queue only.</p>
      <div className="queue-tabs" role="navigation" aria-label="Follow-up queues">
        {QUEUES.map((item) => (
          <Link
            key={item.id}
            to={queueTabHref(tenantId, projectId, item.id, fromKpis, ownerUserId)}
            aria-current={item.id === queue ? 'page' : undefined}
          >
            {item.label}
          </Link>
        ))}
      </div>
      {canFilterOwner ? (
        <label>
          Assignee
          <select aria-label="Assignee" value={ownerUserId} onChange={(event) => setOwnerUserId(event.target.value)}>
            <option value="">All owners</option>
            {members.map((member) => (
              <option key={member.user_id} value={member.user_id}>
                {member.email || 'Project member'}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <p>Showing your follow-ups on records assigned to you.</p>
      )}
      {loading ? <p role="status">Loading follow-ups</p> : null}
      {loading ? <LoadingSkeleton /> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}{' '}
          <button type="button" onClick={() => setReload((current) => current + 1)}>
            Retry
          </button>
        </p>
      ) : null}
      {!loading && !error && items.length === 0 ? <EmptyState title={selected.label} message={selected.empty} /> : null}
      {!loading && items.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Record</th>
                <th scope="col">Task</th>
                <th scope="col">Owner</th>
                <th scope="col">Due</th>
                <th scope="col" className="col-extra">
                  Summary
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link to={`/tenants/${tenantId}/records/${projectId}/${item.record_id}`}>
                      {item.public_number ?? 'Open record'}
                    </Link>
                    <div>{item.display_name}</div>
                  </td>
                  <td>
                    {item.task_type_label}{' '}
                    <StatusBadge tone={queue === 'overdue' ? 'warn' : queue === 'today' ? 'info' : 'neutral'}>
                      {selected.label}
                    </StatusBadge>
                  </td>
                  <td>{ownerLabel(members, item.owner_user_id)}</td>
                  <td>
                    {item.due_date} {item.due_time}
                  </td>
                  <td className="col-extra">{item.summary || 'No summary'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <p>
        Showing {items.length} of {total}
      </p>
      <div className="pager-controls">
        <button type="button" onClick={() => setOffset((current) => Math.max(0, current - 25))} disabled={offset === 0}>
          Previous
        </button>
        <button type="button" onClick={() => setOffset((current) => current + 25)} disabled={offset + 25 >= total}>
          Next
        </button>
      </div>
    </section>
  )
}

function queueTabHref(tenantId: string, projectId: string, queue: string, fromKpis: boolean, ownerUserId: string): string {
  const params = new URLSearchParams({ queue })
  if (fromKpis) {
    params.set('from', 'kpis')
  }
  if (ownerUserId) {
    params.set('owner_user_id', ownerUserId)
  }
  return `/tenants/${tenantId}/follow-ups/${projectId}?${params}`
}
