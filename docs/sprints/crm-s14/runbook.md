# Runbook — original roadmap Sprint 12

Date: 21 October 2026. Commands below were verified as local developer commands, or they are the documented start commands from `README.md`. This is not a production deploy guide. Nothing was deployed.

## 1. Prerequisites

- Windows or another host with Python 3.11+ and Node.js.
- Control Plane API reachable at `http://localhost:8000` unless `PLATFORM_API_BASE_URL` overrides it.
- CRM API at `http://localhost:8001`.
- CRM web at `http://localhost:5174`.
- Use one loopback host for the page and both APIs. `localhost` and `127.0.0.1` do not share the host-only session cookie.
- The Control Plane allowlist must include the CRM origin. The checked-in Control Plane default in the CRM README is port 5173 only. Starting the Control Plane with extra origins is an operator action. Do not commit that change to the Control Plane.

On this review, listeners were present on 8000, 8001, and 5174. Port 5173 was closed. Those processes were not restarted.

## 2. Configuration

Set these in the process environment. Do not commit values.

| Variable | Purpose |
|---|---|
| `PLATFORM_API_BASE_URL` | Control Plane base URL. Default `http://localhost:8000` |
| `CRM_DATABASE_PATH` | CRM SQLite file. Default `backend/data/aadi_crm.sqlite`. A path containing `aadi_platform` is refused |
| `CRM_REMINDER_EMAIL_MODE` | `test` by default. `live` is not treated as delivered by the test suite unless the adapter reports sent |
| `VITE_API_BASE_URL` | Control Plane URL for the web app |
| `VITE_CRM_API_BASE_URL` | CRM API URL for the web app |

## 3. Local start

From `README.md`:

```text
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\uvicorn app.main:app --host localhost --port 8001
```

```text
cd frontend
npm install
npm run dev
```

The web dev server in this workspace uses port 5174. Confirm the port Vite prints before signing in.

## 4. Migrations

Starting the API does not by itself document a separate migrate command. Tests and `apply_migrations` apply `backend/migrations/*.sql` in order and record `crm_schema_migrations`. Scripts that contain `drop table` or `delete from` are refused. Run migrations against a copy when changing a database that already has data. On 21 October 2026 the default file was present. A read-only integrity check is recorded in `backup-restore.md`. Do not treat that file as a backup.

## 5. Pre-release checks

From `backend`:

```text
.venv\Scripts\python -m pytest -q --tb=line
```

From `frontend`:

```text
npm test
npx vite build
npx tsc --noEmit
```

On 21 October 2026 the results were backend **71 passed**, frontend **55 passed**, Vite build succeeded, and `tsc --noEmit` exited 2. See section 12.

## 6. Authentication smoke

Sign in through the CRM page. Open one organization. A missing session returns 401, "Authentication is required." A tenant mismatch returns 404 without the other tenant's name.

## 7. Form, record, follow-up, and reminder smoke

As a project manager, open a project, a published form, the record list, one follow-up queue, and the reminder inbox. Create data only in a project the owner has approved for tests.

## 8. Import and export smoke

Upload a small CSV or XLSX under the existing limits: 1 MiB, 500 data rows, 40 columns, 5,000 characters in a cell. Preview before commit. Export uses the same filters as the list and stops above 1,000 authorized rows.

## 9. KPI and audit

Open `/tenants/{tenantId}/kpis/{projectId}` and `/tenants/{tenantId}/audit`. KPI counts should match the record list and the follow-up queues for that caller. Audit requires platform `audit.read`. The page states that CRM record and follow-up changes are not copied into that log.

## 10. Backup and restore

There is no verified backup job. The live file `backend/data/aadi_crm.sqlite` was present on 21 October 2026. A read-only `PRAGMA integrity_check` returned `ok`. That is not a backup and it is not a restore. Read `backup-restore.md`. Do not restore onto the shared database.

## 11. Logging

A process started after the diagnostics change logs to standard error under `aadi_crm`. Match `X-Request-Id`. Do not expect cookies, query strings, or record values in the log. The process already listening on port 8001 was not restarted, so its log lines are not evidence of this code. A disposable process on port 8091 was started and stopped for the check in `observability.md`.

## 12. TypeScript baseline

`npx tsc --noEmit` exiting 2 is a failure. The known files are:

- `frontend/src/lib/config.ts` TS2559
- `frontend/tests/form-versions.test.tsx` TS2769
- `frontend/vite.config.ts` TS2307 and TS2339

A new file in the error list is a regression. Vite build can still succeed while `tsc` fails. Do not record `tsc` as passed.

## 13. Rollback

There is no deployment to roll back. Application rollback means running the previous CRM code. Database rollback is not automatic. Migrations 001 through 008 are additive. This application will not run a migration that drops a table or deletes rows. Restoring an older file is an owner decision and must use a copy.

## 14. Post-release verification

Not applicable. No release was deployed. After any future start, repeat sections 6 through 9 on the target the owner named.

## 15. Escalation

| Symptom | First place to look | Owner |
|---|---|---|
| Sign-in or 401/403 | Control Plane session and CRM `aadi_crm` line for that path | **Owner decision required** for the platform operator |
| 502 on audit or shell | Control Plane availability. The CRM log will not contain the upstream body | **Owner decision required** |
| Wrong KPI or queue | Record list and follow-up queue for the same user. Archived rows are excluded | CRM maintainer, then the product owner if the rule is disputed |
| Import or reminder failure | Job or delivery row in the CRM database | Data owner for the file. CRM maintainer for a failed code |
| Restore | `backup-restore.md` | **Owner decision required** |

## 16. Safe restart

Stop only the process you started. On this review, port 8001 was pid 5148 and was left running. A check process on port 8091 was stopped after its log was read. Confirm the listener with the port before stopping it.

## 17. Health

There is no CRM health route. A local check is that the process listens and that a missing session returns 401, "Authentication is required." Database health for the live file is `PRAGMA integrity_check` on a read-only connection. Do not run that against a file you are not allowed to open.

## 18. Migrations and rollback

`apply_migrations` applies `backend/migrations/001` through `008` and records them in `crm_schema_migrations`. Scripts containing `drop table` or `delete from` are refused. Starting the API does not by itself print a migration log. Apply migrations to a copy before changing a database that already has data. There is no automatic down migration. Rollback of a released database is an owner decision and must use a copy.

## 19. Stuck imports and reminder failures

Import limits are 1 MiB, 500 data rows, 40 columns, and 5,000 characters in a cell. A preview does not create records. The job status and the error report are in the CRM database. Reminder `last_error` is a fixed code. Provider exception text is not stored. Email mode defaults to `test`. `live` is not treated as delivered unless the adapter reports sent. Retry is limited to projects the caller currently manages. There is no separate operator retry console beyond those routes.

## 20. Incident and support

Severity, escalation contacts, and named owners are **Owner decision required**. Use `support-ownership.md`. Do not invent an on-call rotation.

## 21. Deployment

No manifest, container, or pipeline is in this repository. Do not deploy from this runbook. See `deployment-readiness.md`.
