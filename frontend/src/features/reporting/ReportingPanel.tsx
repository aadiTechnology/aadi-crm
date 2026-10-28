import { useEffect, useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { EmptyState, LoadingSkeleton } from '@/ui/chrome'
import {
  ApiError,
  accessMessage,
  getProject,
  listCompletedFollowUps,
  listProjectMembers,
  listProjects,
  projectKpis,
  type CompletedFollowUp,
  type Project,
  type ProjectKpis,
  type ProjectMembership,
} from '@/services/platform'

function utcDay(): string {
  return new Date().toISOString().slice(0, 10)
}

function failureMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message || accessMessage(error.status)
  }
  return 'The project KPIs could not be loaded.'
}

export function ReportingPanel({ tenantId }: { tenantId: string }) {
  const { projectId } = useParams()
  if (!projectId) {
    return <ProjectPicker tenantId={tenantId} />
  }
  return <ProjectKpiView tenantId={tenantId} projectId={projectId} />
}

function ProjectPicker({ tenantId }: { tenantId: string }) {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listProjects(tenantId, { q: '', status: '' })
      .then((page) => {
        if (!cancelled) {
          setProjects(page.items)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(failureMessage(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId])

  return (
    <section className="stack" aria-labelledby="kpi-projects-heading">
      <h2 id="kpi-projects-heading">Project KPIs</h2>
      <p className="page-intro">Choose a project to see record counts and follow-up workload.</p>
      {projects === null && !error ? <p role="status">Loading projects</p> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}
        </p>
      ) : null}
      {projects && projects.length === 0 ? (
        <EmptyState title="No projects" message="Create a project before reviewing KPIs." />
      ) : null}
      <ul className="project-list">
        {(projects ?? []).map((project) => (
          <li key={project.id}>
            <Link to={`/tenants/${tenantId}/kpis/${project.id}`}>{project.name}</Link>
          </li>
        ))}
      </ul>
    </section>
  )
}

function ProjectKpiView({ tenantId, projectId }: { tenantId: string; projectId: string }) {
  const today = utcDay()
  const [draftFrom, setDraftFrom] = useState(today)
  const [draftTo, setDraftTo] = useState(today)
  const [applied, setApplied] = useState({ from: today, to: today })
  const [project, setProject] = useState<Project | null>(null)
  const [members, setMembers] = useState<ProjectMembership[]>([])
  const [report, setReport] = useState<ProjectKpis | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [completedOpen, setCompletedOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      getProject(tenantId, projectId),
      projectKpis(tenantId, projectId, { createdFrom: applied.from, createdTo: applied.to }),
      listProjectMembers(tenantId, projectId).catch(() => ({ items: [] as ProjectMembership[] })),
    ])
      .then(([loadedProject, loadedReport, membership]) => {
        if (cancelled) {
          return
        }
        setProject(loadedProject)
        setReport(loadedReport)
        setMembers(membership.items.filter((item) => item.status === 'active'))
        setLoading(false)
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setReport(null)
          setError(failureMessage(caught))
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId, applied, reload])

  function onApply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setCompletedOpen(false)
    setApplied({ from: draftFrom, to: draftTo })
  }

  const emails = new Map(members.map((member) => [member.user_id, member.email]))

  return (
    <section className="stack" aria-labelledby="kpi-heading">
      <nav className="crumbs" aria-label="Breadcrumb">
        <Link to={`/tenants/${tenantId}/kpis`}>Project KPIs</Link>
        <span aria-hidden="true">/</span>
        <span>{project?.name ?? 'Project'}</span>
      </nav>
      <div className="page-header">
        <div>
          <h2 id="kpi-heading">{project?.name ?? 'Project KPIs'}</h2>
          <p className="page-intro">
            Active records use the record list. Follow-up queues use India Standard Time and count each open follow-up once.
          </p>
        </div>
      </div>
      <form className="panel record-filters" onSubmit={onApply}>
        <label>
          Records created from
          <input type="date" value={draftFrom} onChange={(event) => setDraftFrom(event.target.value)} />
        </label>
        <label>
          Records created to
          <input type="date" value={draftTo} onChange={(event) => setDraftTo(event.target.value)} />
        </label>
        <button type="submit">Apply period</button>
      </form>
      <p>Record dates use the UTC calendar day. Follow-up dates use Asia/Kolkata. There is no stored project timezone.</p>
      {loading ? <p role="status">Loading project KPIs</p> : null}
      {loading ? <LoadingSkeleton /> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}{' '}
          <button type="button" onClick={() => setReload((current) => current + 1)}>
            Retry
          </button>
        </p>
      ) : null}
      {report && !loading ? (
        <>
          <div className="kpi-grid">
            <KpiCard
              title="Active records"
              value={report.active_records}
              detail="Archived records are excluded."
              href={`/tenants/${tenantId}/records/${projectId}?from=kpis`}
              action="View active records"
            />
            {report.record_period.applied && report.records_created !== null ? (
              <KpiCard
                title="Records created"
                value={report.records_created}
                detail={periodLabel(report.record_period.created_from, report.record_period.created_to)}
                href={recordPeriodHref(tenantId, projectId, report.record_period.created_from, report.record_period.created_to)}
                action="View records created in this period"
              />
            ) : (
              <article className="kpi-card">
                <h3>Records created</h3>
                <p>Choose a start or end date to count records created in a period.</p>
              </article>
            )}
            <KpiCard
              title="Overdue"
              value={report.follow_ups.overdue}
              detail="Open follow-ups due before today in Asia/Kolkata."
              href={queueHref(tenantId, projectId, 'overdue')}
              action="View overdue follow-ups"
            />
            <KpiCard
              title="Due today"
              value={report.follow_ups.today}
              detail="Open follow-ups due today in Asia/Kolkata."
              href={queueHref(tenantId, projectId, 'today')}
              action="View follow-ups due today"
            />
            <KpiCard
              title="Upcoming"
              value={report.follow_ups.upcoming}
              detail="Open follow-ups due after today in Asia/Kolkata."
              href={queueHref(tenantId, projectId, 'upcoming')}
              action="View upcoming follow-ups"
            />
            <article className="kpi-card">
              <h3>Completed follow-ups</h3>
              <p className="kpi-value">{report.follow_ups.completed}</p>
              <p>Status is completed. Cancelled follow-ups are not included.</p>
              <button type="button" onClick={() => setCompletedOpen(true)}>
                View completed follow-ups
              </button>
            </article>
          </div>
          <section className="stack" aria-labelledby="form-kpi-heading">
            <h3 id="form-kpi-heading">Records by form</h3>
            <p>These counts are active records, without the created-date period.</p>
            {report.records_by_form.length === 0 ? <p>No active records.</p> : null}
            {report.records_by_form.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Form</th>
                      <th>Records</th>
                      <th>List</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.records_by_form.map((item) => (
                      <tr key={item.form_id}>
                        <td>{item.form_name}</td>
                        <td>{item.count}</td>
                        <td>
                          <Link to={`/tenants/${tenantId}/records/${projectId}?form_id=${item.form_id}&from=kpis`}>
                            View {item.form_name}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
          <section className="stack" aria-labelledby="status-kpi-heading">
            <h3 id="status-kpi-heading">Records by status</h3>
            <p>
              These counts use the published form field Status. Records without that field are not included. Priority,
              lead source, and follow-up status stay separate.
            </p>
            {report.records_by_status.length === 0 ? <p>No records have a pipeline status.</p> : null}
            {report.records_by_status.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Records</th>
                      <th>List</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.records_by_status.map((item) => (
                      <tr key={item.value}>
                        <td>{item.label}</td>
                        <td>{item.count}</td>
                        <td>
                          <Link
                            to={`/tenants/${tenantId}/records/${projectId}?status=${encodeURIComponent(item.value)}&status_label=${encodeURIComponent(item.label)}&from=kpis`}
                          >
                            View {item.label}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
          <section className="stack" aria-labelledby="owner-kpi-heading">
            <h3 id="owner-kpi-heading">Follow-up workload</h3>
            <p>Each open follow-up is in one queue. The owner is the follow-up owner already stored on the row.</p>
            {report.follow_ups.by_owner.length === 0 ? <p>No open follow-ups in these queues.</p> : null}
            {report.follow_ups.by_owner.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Owner</th>
                      <th>Overdue</th>
                      <th>Due today</th>
                      <th>Upcoming</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.follow_ups.by_owner.map((item) => (
                      <tr key={item.owner_user_id}>
                        <td>{emails.get(item.owner_user_id) || 'Follow-up owner'}</td>
                        <td>
                          <Link to={queueHref(tenantId, projectId, 'overdue', item.owner_user_id)}>{item.overdue}</Link>
                        </td>
                        <td>
                          <Link to={queueHref(tenantId, projectId, 'today', item.owner_user_id)}>{item.today}</Link>
                        </td>
                        <td>
                          <Link to={queueHref(tenantId, projectId, 'upcoming', item.owner_user_id)}>{item.upcoming}</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
          <section className="stack" aria-labelledby="date-kpi-heading">
            <h3 id="date-kpi-heading">Open follow-ups by due date</h3>
            <p>Dates are Asia/Kolkata civil dates. A single date is not a separate list because the queue page cannot filter to one date.</p>
            {report.follow_ups.by_due_date.length === 0 ? <p>No open follow-ups in these queues.</p> : null}
            {report.follow_ups.by_due_date.length > 0 ? (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Queue</th>
                      <th>Due date</th>
                      <th>Follow-ups</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.follow_ups.by_due_date.map((item) => (
                      <tr key={`${item.queue}-${item.due_date}`}>
                        <td>{queueLabel(item.queue)}</td>
                        <td>{item.due_date}</td>
                        <td>{item.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
          {completedOpen ? (
            <CompletedList
              tenantId={tenantId}
              projectId={projectId}
              expected={report.follow_ups.completed}
              onClose={() => setCompletedOpen(false)}
            />
          ) : null}
        </>
      ) : null}
    </section>
  )
}

function KpiCard({
  title,
  value,
  detail,
  href,
  action,
}: {
  title: string
  value: number
  detail: string
  href: string
  action: string
}) {
  return (
    <article className="kpi-card">
      <h3>{title}</h3>
      <p className="kpi-value">{value}</p>
      <p>{detail}</p>
      <Link to={href}>{action}</Link>
    </article>
  )
}

function CompletedList({
  tenantId,
  projectId,
  expected,
  onClose,
}: {
  tenantId: string
  projectId: string
  expected: number
  onClose: () => void
}) {
  const [items, setItems] = useState<CompletedFollowUp[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listCompletedFollowUps(tenantId, projectId)
      .then((page) => {
        if (!cancelled) {
          setItems(page.items)
          setTotal(page.total)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(failureMessage(caught))
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, projectId])

  return (
    <section className="stack" aria-labelledby="completed-heading">
      <h3 id="completed-heading">Completed follow-ups</h3>
      <p>
        <button type="button" onClick={onClose}>
          Back to KPI overview
        </button>
      </p>
      {items === null && !error ? <p role="status">Loading completed follow-ups</p> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}
        </p>
      ) : null}
      {items && items.length === 0 ? <p>No completed follow-ups.</p> : null}
      {items && items.length > 0 ? (
        <>
          <p>
            The list has {total} completed follow-ups. The KPI count is {expected}.
          </p>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Record</th>
                  <th>Type</th>
                  <th>Due</th>
                  <th>Completed</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link to={`/tenants/${tenantId}/records/${projectId}/${item.record_id}`}>{item.public_number}</Link>
                      <div>{item.display_name}</div>
                    </td>
                    <td>{item.task_type_label}</td>
                    <td>
                      {item.due_date} {item.due_time}
                    </td>
                    <td>{item.completed_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </section>
  )
}

function periodLabel(createdFrom: string, createdTo: string): string {
  if (createdFrom && createdTo) {
    return `UTC dates ${createdFrom} through ${createdTo}.`
  }
  if (createdFrom) {
    return `UTC dates from ${createdFrom}.`
  }
  return `UTC dates through ${createdTo}.`
}

function recordPeriodHref(tenantId: string, projectId: string, createdFrom: string, createdTo: string): string {
  const params = new URLSearchParams({ from: 'kpis' })
  if (createdFrom) {
    params.set('created_from', createdFrom)
  }
  if (createdTo) {
    params.set('created_to', createdTo)
  }
  return `/tenants/${tenantId}/records/${projectId}?${params}`
}

function queueHref(tenantId: string, projectId: string, queue: string, ownerUserId = ''): string {
  const params = new URLSearchParams({ queue, from: 'kpis' })
  if (ownerUserId) {
    params.set('owner_user_id', ownerUserId)
  }
  return `/tenants/${tenantId}/follow-ups/${projectId}?${params}`
}

function queueLabel(queue: string): string {
  if (queue === 'overdue') {
    return 'Overdue'
  }
  if (queue === 'today') {
    return 'Due today'
  }
  if (queue === 'upcoming') {
    return 'Upcoming'
  }
  return queue
}
