# Original Roadmap Sprint 11 — KPIs, Follow-up Workload and Audit

Date: 21 October 2026. Written before the Sprint 11 code change. Repository: `aadi-crm` only.

`docs/sprints/crm-s13` is the evidence folder for original roadmap Sprint 11. It is not original roadmap Sprint 13. Original roadmap Sprint 10 is technically closed in `docs/sprints/crm-s12/closure.md`. Paneerwala stays deferred. Original roadmap Sprint 6 stays planned.

## Sources

- PRD v1.0 dated 9 October 2026 is not in this repository. The copy used by the earlier sprint plans is `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`. This sprint uses the requirements already tied to persisted CRM data: TASK-02 queues, the record list, and the AuditEvent read described as Sprint 11 in the Sprint 7 plan.
- Control Plane audit read, inspected and not modified: `GET /api/v1/tenants/{tenant_id}/audit-events`. It requires `audit.read`, returns the newest events up to `limit` (1–100, default 50), and has no actor, action, project, or date filter and no offset. Nothing in the Control Plane or the CRM calls `AuditService.append`. The CRM must not add a second audit table to fill that gap.

## Metrics that can be computed

| Metric | Rule | Drill-down |
|---|---|---|
| Active records | `records.deleted_at IS NULL` in the project, joined to the published form version the same way as the record list. A project member counts only records assigned to them. | Existing record list with no search and no date filter |
| Records created in a period | Same active-record rule, plus the existing `created_from` / `created_to` comparison on the UTC date prefix of `created_at`. The record list already uses that prefix. There is no tenant or project timezone column, so this sprint does not reinterpret record dates as `Asia/Kolkata`. | Existing record list with the same two dates |
| Records by form | Active records grouped by `form_id`. The period is not applied, so the group total matches the active-record count. | Existing record list with that `form_id` |
| Overdue, due today, upcoming | Open follow-ups on active records. The window is `queue_window` in `Asia/Kolkata`: overdue is `due_at` before local midnight, today is that midnight up to but not including the next, upcoming is on or after the next midnight. A follow-up is in one queue. Completed and cancelled rows are excluded. A member sees follow-ups they own on records assigned to them. | Existing `GET .../follow-ups?queue=` |
| Follow-up owner and due date | The same open-follow-up rows, grouped by `owner_user_id` and by the `Asia/Kolkata` civil date. Owner counts for a manager link to the existing owner filter. A single due date is not a clickable KPI because the queue API cannot filter to that date. | Owner cells use `owner_user_id` on the queue page. Date cells are not links |
| Completed follow-ups | `status = completed` on active records, same visibility rule. Cancelled rows are excluded. This is the stored status, not a new state. The count is all completed rows, not a date period. | A list on the KPI page using the same filter. Outcome text is left on the record timeline |

## Metrics that are not computed

- Record status, conversion, or lost. Records have no status column. Original roadmap Sprint 6 owns that lifecycle.
- Trend percentages, targets, and forecasts. There is no stored baseline to compare.
- Follow-up workload by record assignee as a new assignment feature. Record `assignee_user_id` remains the creator and is used only for the existing visibility rule.
- A CRM copy of platform audit events. The platform list is read through the CRM server and is not stored again.

## Audit

The CRM adds a read-only view of `GET /api/v1/tenants/{tenant_id}/audit-events`. The browser calls the CRM. The CRM forwards the session cookie and the path tenant only. `audit.read` stays on the platform. The CRM also requires the existing CRM module check, so this route is not an open proxy.

The response keeps `id`, `occurred_at`, `action`, `resource_type`, `resource_id`, `summary`, `outcome`, and `actor_user_id`. Metadata is dropped so a free-text payload is not shown. Actor, action, project, and date filters are rejected with 422 because the platform cannot apply them. Offset is rejected for the same reason. `limit` is forwarded and capped at 100.

No CRM action currently writes a platform audit event. Record create and edit are not on the platform log. Follow-up history stays on `record_activities` and is not presented as the security audit. An empty audit list means the platform returned no rows. It does not mean those CRM actions were audited.

## Access

Tenant, project membership, and `authorize_record` stay as they are. Counts use the same assignee and owner constraints as the lists. A count must not include a record the caller cannot open.

## File budget

Limit: 20 new files and 10 modified files for this implementation unit. Sprint 10 closure documents are a separate unit. No database migration. No new dependency. The Control Plane repository is not modified.
