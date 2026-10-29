# Operations — original roadmap Sprint 11

No database migration is required. Restart the CRM API process after pulling this code so `/kpis` and `/audit-events` are registered. Do not reset `backend/data/aadi_crm.sqlite`.

## Pages

- Project KPIs: `/tenants/{tenantId}/kpis` and `/tenants/{tenantId}/kpis/{projectId}`
- Audit: `/tenants/{tenantId}/audit`

Both pages use the existing CRM sign-in and the CRM project-module check. The audit page then asks the Control Plane for `audit.read`. A user without that permission sees a denial and no events.

## How the numbers are defined

Follow-up queues use Asia/Kolkata, because no tenant or project timezone is stored. Overdue is before local midnight, today is that local day, and upcoming starts at the next local midnight. Only open follow-ups on active records are counted, and each one is in one queue.

Record creation dates use the UTC calendar day already used by the record list. Changing the period changes "Records created" and its drill-down. It does not change the active-record count or the follow-up queues.

Completed follow-ups are rows whose status is already `completed`. Cancelled rows are not counted as completed.

## Audit

The CRM reads `GET /api/v1/tenants/{tenant_id}/audit-events` and does not store a copy. The screen shows id, time, action, resource, summary, outcome, and actor id when the platform returns them. It does not show metadata. Actor, action, project, and date filters are not available. If the platform cannot be reached, the page says the audit log is unavailable.

CRM record edits and follow-up changes are not currently written to that log. An empty or denied audit page does not mean those actions were audited. Follow-up history stays on the record timeline.

## What this sprint does not operate

There is no status KPI, no target, and no trend. There is no new assignment workflow. Paneerwala is not configured.
