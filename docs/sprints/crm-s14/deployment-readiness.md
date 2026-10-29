# Deployment readiness — original roadmap Sprint 12

Date: 21 October 2026. Nothing was deployed. This document is a plan for a later, separately authorized deployment. It is not permission to deploy.

## Current state

No Dockerfile, compose file, or GitHub workflow was found in this repository. The only verified run path is local: Control Plane API on port 8000, CRM API on port 8001, CRM web on port 5174. Those listeners were already present. They were not restarted, except for a disposable CRM process on port 8091 that was created and then stopped.

## Environment the operator must confirm

| Item | Requirement |
|---|---|
| Python | 3.11 or newer. This review used 3.14.3 |
| Node | Needed for the web build. This review used v22.13.1 |
| `PLATFORM_API_BASE_URL` | Control Plane base URL. Do not commit it |
| `CRM_DATABASE_PATH` | SQLite file. A path containing `aadi_platform` is refused |
| `CRM_REMINDER_EMAIL_MODE` | `test` unless the owner has approved live sending |
| `VITE_API_BASE_URL` and `VITE_CRM_API_BASE_URL` | Web app API origins. Use one loopback host for the page and both APIs |
| Control Plane CORS | The CRM origin must be allowed. Do not commit that change to the Control Plane |
| Secrets | Process environment only. They are not in the CRM database |

## Migration sequence, when a deploy is later authorized

1. Take an approved backup first. That backup does not exist yet. See `backup-restore.md`.
2. Deploy the CRM code without switching traffic, or stop only the CRM process the owner named.
3. Point `CRM_DATABASE_PATH` at a copy and run the application migrations there. Confirm `crm_schema_migrations` lists `001` through `008`.
4. Apply the same migrations to the approved target only after the copy succeeded.
5. Start the CRM API and the web build the owner named.
6. Do not migrate or restart the Control Plane as part of this CRM sprint.

There is no down migration. Rollback is to the previous CRM code and, if the owner approves, a restore of the backup onto a new file. Do not delete the current file to prove rollback.

## Smoke tests after a future start

Use an account the owner has approved for the target.

1. Sign in and open the authorized organization. A missing session returns 401.
2. Open one project, a published form, the record list, one follow-up queue, and the reminder inbox.
3. Open KPI and audit. Audit shows data only when the account has `audit.read`. Otherwise it shows the permission denial.
4. Preview a small import. Do not commit it unless the owner approved new rows.
5. Read one `aadi_crm` log line and match `X-Request-Id`.

## Readiness

**NOT READY.** Backup, restore, human UAT, TypeScript, monitoring, and named owners are unresolved. Deployment remains a separate authorization.
