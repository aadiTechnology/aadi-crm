import { useEffect, useState } from 'react'

import { EmptyState, LoadingSkeleton } from '@/ui/chrome'
import { ApiError, accessMessage, listAuditEvents, type AuditEvent } from '@/services/platform'

function failureMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 502) {
      return 'The audit log is unavailable.'
    }
    return error.message || accessMessage(error.status)
  }
  return 'The audit log is unavailable.'
}

export function AuditPanel({ tenantId }: { tenantId: string }) {
  const [items, setItems] = useState<AuditEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    setItems(null)
    setError(null)
    listAuditEvents(tenantId)
      .then((page) => {
        if (!cancelled) {
          setItems(page.items)
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
  }, [tenantId, reload])

  return (
    <section className="stack" aria-labelledby="audit-heading">
      <div className="page-header">
        <div>
          <h2 id="audit-heading">Audit</h2>
          <p className="page-intro">
            This is the organization audit log from the platform. It is not filtered by project, actor, action, or date.
            Follow-up history on a record is a separate timeline.
          </p>
        </div>
      </div>
      {items === null && !error ? <p role="status">Loading audit events</p> : null}
      {items === null && !error ? <LoadingSkeleton /> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}{' '}
          <button type="button" onClick={() => setReload((current) => current + 1)}>
            Retry
          </button>
        </p>
      ) : null}
      {items && items.length === 0 ? (
        <EmptyState
          title="No audit events"
          message="No audit events were returned for this organization. Record and follow-up changes are not copied into this log."
        />
      ) : null}
      {items && items.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table">
            <caption>Latest events returned by the organization audit log.</caption>
            <thead>
              <tr>
                <th>When</th>
                <th>Action</th>
                <th>Resource</th>
                <th>Summary</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.occurred_at}</td>
                  <td>{item.action}</td>
                  <td>
                    {item.resource_type}
                    {item.resource_id ? ` ${item.resource_id}` : ''}
                  </td>
                  <td>{item.summary}</td>
                  <td>{item.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  )
}
