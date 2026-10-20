import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  ApiError,
  deliverReminders,
  listReminderFailures,
  listReminders,
  markReminderRead,
  retryReminder,
  type ReminderDeliveryResult,
  type ReminderItem,
} from '@/services/platform'
import { EmptyState, LoadingSkeleton, StatusBadge } from '@/ui/chrome'

function messageFrom(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  return 'The request could not be completed.'
}

function deliverySummary(result: ReminderDeliveryResult): string {
  const email =
    result.email_mode === 'test'
      ? `The test adapter recorded ${result.email_recorded} email reminder${result.email_recorded === 1 ? '' : 's'}. Those emails were not delivered.`
      : `No email provider is configured. ${result.failed} email reminder${result.failed === 1 ? '' : 's'} stopped without being sent.`
  return `${email} In-app reminders delivered: ${result.in_app_sent}. Temporary failures: ${result.retryable}. Stopped: ${result.failed}.`
}

export function RemindersPanel({ tenantId }: { tenantId: string }) {
  const [items, setItems] = useState<ReminderItem[] | null>(null)
  const [failures, setFailures] = useState<ReminderItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listReminders(tenantId)
      .then(async (page) => {
        let operator: ReminderItem[] | null = null
        try {
          operator = (await listReminderFailures(tenantId)).items
        } catch (caught: unknown) {
          if (!(caught instanceof ApiError) || caught.status !== 403) {
            throw caught
          }
        }
        if (!cancelled) {
          setItems(page.items)
          setFailures(operator)
          setLoading(false)
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(messageFrom(caught))
          setItems(null)
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [tenantId, reload])

  async function onDeliver() {
    setPending(true)
    setNotice(null)
    try {
      const result = await deliverReminders(tenantId)
      setNotice(deliverySummary(result))
      setReload((current) => current + 1)
    } catch (caught: unknown) {
      setError(messageFrom(caught))
    } finally {
      setPending(false)
    }
  }

  async function onRead(item: ReminderItem) {
    setPending(true)
    try {
      const updated = await markReminderRead(tenantId, item.id)
      setItems((current) => (current ?? []).map((entry) => (entry.id === updated.id ? updated : entry)))
    } catch (caught: unknown) {
      setError(messageFrom(caught))
    } finally {
      setPending(false)
    }
  }

  async function onRetry(item: ReminderItem) {
    setPending(true)
    try {
      await retryReminder(tenantId, item.id)
      setNotice('The same reminder was queued again. A new reminder was not created.')
      setReload((current) => current + 1)
    } catch (caught: unknown) {
      setError(messageFrom(caught))
    } finally {
      setPending(false)
    }
  }

  const inApp = (items ?? []).filter((item) => item.channel === 'in_app')
  const emails = (items ?? []).filter((item) => item.channel === 'email')

  return (
    <section className="stack" aria-labelledby="reminders-heading">
      <div className="page-header">
        <div>
          <h2 id="reminders-heading">Reminders</h2>
          <p className="page-intro">
            Reminders use India Standard Time. Email from this screen uses the test adapter unless a provider is configured, and a
            recorded email has not been delivered.
          </p>
        </div>
        <button type="button" onClick={() => void onDeliver()} disabled={pending}>
          {pending ? 'Delivering reminders' : 'Deliver pending reminders'}
        </button>
      </div>
      {loading ? <p role="status">Loading reminders</p> : null}
      {loading ? <LoadingSkeleton /> : null}
      {error ? (
        <p role="alert" className="alert alert-error">
          {error}{' '}
          <button type="button" onClick={() => setReload((current) => current + 1)}>
            Retry
          </button>
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="alert alert-ok">
          {notice}
        </p>
      ) : null}
      {!loading && !error && inApp.length === 0 ? (
        <EmptyState title="No reminders" message="Delivered reminders for this sign-in will appear here." />
      ) : null}
      {inApp.length > 0 ? (
        <ul className="reminder-list">
          {inApp.map((item) => (
            <li key={item.id} className="reminder-card">
              <div className="reminder-heading">
                <strong>{item.kind_label}</strong>
                <StatusBadge tone={item.read ? 'neutral' : 'info'}>{item.read ? 'Read' : 'Unread'}</StatusBadge>
              </div>
              <p>
                Due {item.due_date} {item.due_time} India Standard Time.
              </p>
              {item.record_available && item.project_id && item.record_id ? (
                <Link to={`/tenants/${tenantId}/records/${item.project_id}/${item.record_id}`}>
                  Open record {item.public_number}
                </Link>
              ) : (
                <p>You cannot open this record with the current access.</p>
              )}
              <div className="reminder-actions">
                {item.read ? null : (
                  <button type="button" onClick={() => void onRead(item)} disabled={pending}>
                    Mark as read
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {!loading && emails.length > 0 ? (
        <section className="stack" aria-labelledby="email-reminders-heading">
          <h3 id="email-reminders-heading">Your email reminders</h3>
          <ul className="reminder-list">
            {emails.map((item) => (
              <li key={item.id} className="reminder-card">
                <strong>{item.kind_label}</strong>
                <p>{item.state_label}</p>
                <p>
                  Due {item.due_date} {item.due_time}. Attempts {item.attempt_count}.
                  {item.last_attempt_at ? ` Last attempt ${item.last_attempt_at}.` : ''}
                  {item.next_retry_at ? ` Next retry ${item.next_retry_at}.` : ''}
                </p>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {failures ? (
        <section className="stack" aria-labelledby="failure-heading">
          <h3 id="failure-heading">Email failures for projects you manage</h3>
          {failures.length === 0 ? (
            <p>No email reminder is waiting for retry or stopped.</p>
          ) : (
            <ul className="reminder-list">
              {failures.map((item) => (
                <li key={item.id} className="reminder-card">
                  <strong>{item.kind_label}</strong>
                  <p>{item.failure_label ?? item.state_label}</p>
                  <p>
                    Attempts {item.attempt_count}.
                    {item.last_attempt_at ? ` Last attempt ${item.last_attempt_at}.` : ''}
                    {item.next_retry_at ? ` Next retry ${item.next_retry_at}.` : ' No automatic retry is scheduled.'}
                  </p>
                  {item.recipient_email ? <p>Directory address {item.recipient_email}</p> : null}
                  {item.record_available && item.public_number ? <p>Record {item.public_number}</p> : <p>Record details are hidden.</p>}
                  <div className="reminder-actions">
                    <button type="button" onClick={() => void onRetry(item)} disabled={pending}>
                      Retry delivery
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}
    </section>
  )
}
