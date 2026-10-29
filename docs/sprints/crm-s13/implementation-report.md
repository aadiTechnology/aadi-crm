# CRM-S13 implementation report — original roadmap Sprint 11

Date: 21 October 2026. Repository: `aadi-crm` only.

Original roadmap Sprint 10 was technically closed first. Paneerwala is Deferred and was not required for that closure. See `docs/sprints/crm-s12/closure.md`. Original roadmap Sprint 6 stays Planned.

## What was built

A project KPI page and a read-only organization audit page.

KPIs are counted in SQLite with the same filters as the record list and the follow-up queues:

- Active records exclude archived records. A project member counts only records assigned to them.
- Records created in a period use `created_from` and `created_to` on the UTC date prefix of `created_at`. That is the existing record-list rule. The page defaults the period to the UTC calendar day.
- Records by form are active records grouped by form, without the created-date period. There is no record status column, so no status KPI is shown.
- Overdue, due today, and upcoming count open follow-ups on active records. The window is the existing Asia/Kolkata queue window. Each open follow-up is in one queue. Completed and cancelled rows are excluded from those three counts.
- Owner rows use `follow_ups.owner_user_id`. A member's row is only their own follow-ups on records assigned to them. A manager can open a queue filtered by that owner.
- Due-date rows use the Asia/Kolkata civil date. They are not links, because the queue API cannot filter to one date.
- Completed follow-ups count `status = completed` on active records. The list is on the KPI page and omits outcome text. Cancelled rows are not included.

The audit page calls the CRM, and the CRM calls `GET /api/v1/tenants/{tenant_id}/audit-events` with the session cookie. Metadata, email, and any other extra field are dropped. Actor, action, project, date, and offset filters are rejected with 422. `limit` is forwarded and capped at 100. A platform failure becomes "The audit log is unavailable." No CRM table stores audit events. No CRM action appends one. The follow-up timeline remains a separate history.

## Files

Sprint 11 product unit: 9 new files and 9 modified files.

New:

- `backend/app/reporting_store.py`
- `backend/app/api/reporting.py`
- `backend/app/api/audit_view.py`
- `backend/tests/test_reporting.py`
- `backend/tests/test_audit_view.py`
- `frontend/src/features/reporting/ReportingPanel.tsx`
- `frontend/src/features/audit/AuditPanel.tsx`
- `frontend/tests/reporting.test.tsx`
- `frontend/tests/audit.test.tsx`

Modified:

- `backend/app/main.py`
- `backend/app/platform_client.py`
- `backend/tests/test_projects.py`
- `frontend/src/main.tsx`
- `frontend/src/services/platform.ts`
- `frontend/src/features/shell/CrmShellPage.tsx`
- `frontend/src/features/records/RecordsPanel.tsx`
- `frontend/src/features/records/FollowUpsPanel.tsx`
- `frontend/src/styles.css`

Evidence files in `docs/sprints/crm-s13/` are a separate documentation set. Sprint 10 closure documents were updated before this unit. No migration was added.

## Routes

- `GET /api/v1/tenants/{tenant_id}/projects/{project_id}/kpis`
- `GET /api/v1/tenants/{tenant_id}/projects/{project_id}/kpis/completed-follow-ups`
- `GET /api/v1/tenants/{tenant_id}/audit-events`

Pages: `/tenants/{tenantId}/kpis`, `/tenants/{tenantId}/kpis/{projectId}`, and `/tenants/{tenantId}/audit`.

## Confirmation

The Control Plane repository was not modified. No commit, push, merge, tag, or deployment was made. The local CRM API process was restarted so the browser demo could call the new routes.
