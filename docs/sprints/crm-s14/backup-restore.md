# Backup and restore — original roadmap Sprint 12

Date: 21 October 2026. No backup was taken and no restore was run. The shared database was not overwritten. The Control Plane was not modified.

## Data topology

| Item | What was found |
|---|---|
| Database engine | SQLite, opened by `app.db.connect` |
| Default file | `backend/data/aadi_crm.sqlite` unless `CRM_DATABASE_PATH` is set |
| That file on this review | Present. 610,304 bytes. Read-only `PRAGMA integrity_check` returned `ok` |
| Migrations recorded in that file | `001_projects.sql` through `008_imports.sql` |
| Row counts, not contents | 22 projects, 27 form definitions, 34 form versions, 29 records, 25 follow-ups, 76 reminder deliveries, 4 import jobs |
| Uploaded import files | Rows in the same SQLite file. No separate upload directory was found |
| Generated reports | No report file store was found. KPI responses are computed when requested |
| Secrets | Not stored in this file. Sessions stay on the Control Plane |
| Control Plane database | Separate. `database_path` refuses a path whose name contains `aadi_platform` |
| What a consistent CRM restore includes | The SQLite file, including `crm_schema_migrations`, records, forms, follow-ups, reminders, and import rows |
| What it does not include | Control Plane users, sessions, permissions, branding, and audit events |

The earlier note that the default file was absent is out of date. Its presence is not a backup.

## Owner decisions

The PRD text includes "Daily automated backups, 30-day retention and tested restoration" and says a daily backup and a documented restore test are completed before production release. This review did not find an approved operating procedure, a backup artifact, or a named operator. The PRD sentence is not treated as a decision already made for this environment.

| Decision | Value |
|---|---|
| Frequency | **Owner decision required.** The PRD states daily. That has not been confirmed or implemented here |
| Retention | **Owner decision required.** The PRD states 30 days. That has not been confirmed or implemented here |
| Storage location | **Owner decision required** |
| Encryption | **Owner decision required.** The application does not encrypt the SQLite file |
| RPO | **Owner decision required** |
| RTO | **Owner decision required** |
| Backup owner | **Owner decision required** |
| Restore operator | **Owner decision required** |
| Who approves a restore | **Owner decision required** |
| Last restore test | None. **BLOCKED** until a real backup and an approved empty target exist |

## Why restore was not run

A restore needs an approved backup and an isolated target. Copying the live development file and opening the copy would show that the file can be read. It would not be a restore of a backup, and this review does not call it one.

When an owner approves the policy and names the source backup:

1. Copy that backup to a new file. Do not open the source with a write connection.
2. Do not point the command at `backend/data/aadi_crm.sqlite` or at a production file.
3. Set `CRM_DATABASE_PATH` to the copy.
4. Run `PRAGMA integrity_check` and expect `ok`.
5. Confirm `crm_schema_migrations` lists `001` through `008` for this code.
6. Start the API against the copy only. Open one authorized project, record list, follow-up queue, form, reminder inbox, and KPI page.
7. Confirm another tenant cannot open the project.
8. Record the elapsed restore time against the approved RTO, and the data lost against the approved RPO.
9. Stop that process and remove the copy only when the owner says to.

Until that has been done on an approved backup, restore verification is **BLOCKED**.
