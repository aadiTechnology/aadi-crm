# Backup and restore ownership — original roadmap Sprint 12

Date: 21 October 2026. This document separates what was found from what an owner still has to decide.

No backup artifact, backup job, restore log, or hosted database configuration was found in `aadi-crm`. No restore was executed. The shared development database was not overwritten.

## Confirmed

| Item | Evidence |
|---|---|
| CRM data store | SQLite, opened by `app.db`. This is not the Control Plane database. `database_path` refuses a path whose name contains `aadi_platform` |
| Default file | `backend/data/aadi_crm.sqlite`, unless `CRM_DATABASE_PATH` is set |
| That default file during this review | **Not present** in the workspace. Integrity of a live file was therefore not checked |
| Migrations | `backend/migrations/001` through `008`. `apply_migrations` skips scripts that contain `drop table` or `delete from`. Tests apply them to a temporary file |
| Uploaded import files | Stored as rows in `import_jobs` / `import_rows` in the same SQLite file. No separate object store was found |
| Secrets | Not stored in the CRM database. Sessions stay on the Control Plane. `CRM_REMINDER_EMAIL_MODE` defaults to `test` |
| Who ran a restore test | Nobody in this review |

## Owner decision required

| Item | Value |
|---|---|
| Database owner/operator | **Owner decision required.** Locally it is whoever starts the CRM process and chooses `CRM_DATABASE_PATH` |
| Application owner/operator | **Owner decision required.** The repository only documents a local `uvicorn` process |
| Who configures and monitors backups | **Owner decision required** |
| Backup frequency | **Owner decision required** |
| Retention | **Owner decision required** |
| Where backups are stored and who can read them | **Owner decision required** |
| Encryption at rest | **Owner decision required.** SQLite encryption was not found in the application |
| Who can initiate a restore | **Owner decision required** |
| Who approves a restore | **Owner decision required** |
| RPO | **Owner decision required** |
| RTO | **Owner decision required** |
| Last restore test | **None found** |

## What a later restore must include

The SQLite file and the migration history in `crm_schema_migrations` have to match the application code. Control Plane users, sessions, permissions, and audit events are outside this file. Restoring only the CRM file does not restore sign-in. There is no attachment directory to restore.

## Restore-validation checklist

Use a copy. Do not point the command at the shared or production file.

1. Confirm the owner has approved the source backup and the empty target.
2. Copy the backup to a new file. Do not open the source with a write connection.
3. Set `CRM_DATABASE_PATH` to that copy.
4. Run `PRAGMA integrity_check` and expect `ok`.
5. Start the CRM API against that copy. Confirm `crm_schema_migrations` lists `001` through `008` before serving traffic for this code.
6. Sign in through the Control Plane and open one authorized project, record list, follow-up queue, and KPI page.
7. Confirm a user from another tenant cannot open the project.
8. Stop the process and remove the copy when the owner says to.

Until that checklist has been executed on an approved backup, restore is **not verified**.
