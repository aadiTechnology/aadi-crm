# CRM-S10 scope and implementation plan

Date: 20 October 2026. Written before the reminder code change. Repository: `aadi-crm` only.

This folder is **Original Roadmap Sprint 8: Notifications & reminders**. It is not original roadmap Sprint 10. `docs/sprints/crm-s8` stays the record-experience evidence and is not overwritten. Original roadmap Sprint 6 (record assignment, statuses, duplicate detection) stays unstarted.

## Sources

- Original plan row 8 in `C:\Users\lenovo\Downloads\Aadi_CRM_Complete_Sprint_Plan.xlsx`: in-app and email reminders for assignments and due follow-ups, with idempotency, retry, and failure visibility, reusing the platform notification foundation.
- PRD task reminder intent, read from `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx` via the Sprint 7 plan. TASK-05 is the reminder requirement. TASK-06 sequences stay out.
- Control Plane plan `docs/planning/MULTITENANT_RBAC_CRM_SPRINT_PLAN.md` in the Control Plane repository. MT-S4 audit read exists. MT-S6 notification port is NOT STARTED. `NoOpPasswordResetNotifier` is not a send API.

## Current CRM event sources

- Follow-up create, update, complete, and cancel are persisted in `follow_ups`. Update can change the owner and the due instant. Those are the only assignment operations that exist today.
- `record_activities` records follow-up events. It is not a delivery queue.
- `records.assignee_user_id` is the creator. There is no assignment or reassignment API and no assignment event table. Record-level assignment reminders depend on original roadmap Sprint 6 and are not built here.

## Platform capabilities that actually exist

| Capability | What the code exposes | Sprint 8 use |
|---|---|---|
| Session, tenant, permissions | Existing CRM `PlatformClient` | Unchanged. Reminder routes use the same session, product access, and CSRF checks. |
| Tenant user directory | `GET /api/v1/tenants/{id}/users/{user_id}` | Server-side email lookup while the caller's session is present. The client cannot submit a destination address. |
| Audit read | `GET /api/v1/tenants/{id}/audit-events` requires `audit.read` | Not used. The route cannot append events. |
| Notification or email port | Not implemented. MT-S6 is not started. | No platform send call exists to reuse. |
| Password reset notifier | `NoOpPasswordResetNotifier` discards a reset secret | Not a general mail API. CRM does not call it. |

## Gap and the smallest integration

The Control Plane has no notification contract and no email provider. This sprint does not add SMTP, a second identity store, or a CRM audit product.

CRM stores its own reminder rows and delivers them through a CRM port:

- `test` mode, the default, records the email intent in CRM and marks the row `recorded`. The screen says the test adapter recorded it and that it was not delivered.
- `live` mode does not send either. It marks the email `failed` with `provider_not_configured`, because no provider is configured. That state is not described as a successful send.

A real provider waits for MT-S6. CRM will not claim provider delivery in this sprint.

## Identity and tenancy

The tenant, actor, and recipient user id come from the authenticated CRM request and the stored follow-up. Path tenant id is checked the same way as the other CRM routes. Email is copied from the platform directory response, or from the signed-in identity when the recipient is the caller and the directory denies the lookup. No request field named email is accepted.

## Scheduling

There is no separate operating-system scheduler in this sprint. Saving a follow-up materializes reminder rows. A project manager, or the recipient for their own rows, runs **Deliver pending reminders**. One run attempts each due row once.

- Follow-up assigned: one in-app row and one email row per follow-up and owner. Eligible immediately while the follow-up is open.
- Follow-up due: one in-app row and one email row per follow-up, owner, and due instant. Eligible at that instant. A later run does not create another row for the same instant.
- Overdue follow-ups receive that one due reminder the first time delivery runs at or after the due instant. They are not emailed again on every run.
- Completed or cancelled follow-ups suppress rows that are still pending or waiting for retry. Those states already exist. No new follow-up status is added.
- Reassignment suppresses the previous owner's unsent rows and creates rows for the new owner.
- Civil due times stay `Asia/Kolkata`. Projects and the tenant configuration document do not store a timezone.

## Idempotency, retry, and failure visibility

Idempotency key: `{tenant}|{follow-up}|{recipient}|{kind}|{channel}|{due instant or "-"}`. The database unique constraint is on that key.

States: `pending`, `processing`, `sent`, `recorded`, `retryable`, `failed`, `suppressed`.

`sent` means the local in-app inbox commit succeeded, or a live provider confirmed. The test adapter cannot produce `sent`. `recorded` is not success of an external provider.

Automatic email retry runs at most 3 attempts. Live mode waits 60, 300, then 900 seconds. Test mode records the next retry immediately so a later run can retry without waiting, but one run does not attempt the same row twice. The fourth automatic attempt is not made. A project manager can retry the same row. That resets the attempt count and does not insert a second row.

Attempt count, last attempt, last error code, and next retry time are stored. Error values are fixed codes, not provider payloads.

Exactly-once external delivery is not claimed. If a future provider accepts a message and the process stops before the `sent` commit, a later run can attempt that message again.

## Authorization

- Inbox reads return only the signed-in user's rows in the path tenant.
- Record number and the link are included only when `authorize_record` allows the record on this request. A removed member or an assigned-scope user who does not own the record gets the reminder without the record number.
- Failure review and manual retry require an active project-manager membership on that project. No new platform permission is registered.
- Delivery for a manager covers projects they manage. A member who manages none can deliver only rows addressed to them.

## Migration

`007_reminders.sql` adds `reminder_deliveries` and indexes. It does not drop or delete. The existing migration runner applies it once and records the script name.

## Tests and browser demo

Backend tests cover duplicate materialization, a second delivery run, retry exhaustion, provider-not-configured, test-adapter recording, completed and cancelled follow-ups, cross-tenant reads, another user's inbox, and a reminder that no longer opens the record.

The browser demo uses the recording users already present for CRM captures, the test adapter, and no live mailbox.

## Out of scope

- Original roadmap Sprint 6 record assignment, statuses, and duplicate detection.
- WhatsApp, SMS, and campaign sending.
- The 1, 3, 7, 21, and 90 day sequence.
- A platform notification service, SMTP provider, or Control Plane code change.
- A general notification administration product.
- Appending to the platform audit log. That API is read-only.
