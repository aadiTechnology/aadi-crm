# SQLite to PostgreSQL — Stage 2 report

Date: 25 October 2026.

Repository: `C:\Users\lenovo\AadiTech\Product\aadi-crm`.

This stage created the empty CRM development database and applied the existing PostgreSQL migrations. It did not copy SQLite rows, change the application default, or open a Control Plane database. Nothing was committed, pushed, or deployed.

## Target

| Fact | Result |
| --- | --- |
| Server | PostgreSQL 17.4 |
| Host class | Loopback (`localhost`) |
| TLS on the server | Off |
| Database | `aadi_crm` |
| Existed before this stage | No |
| Created by this stage | Yes, with `CREATE DATABASE aadi_crm` |
| Schemas or tables before migration | None |
| SSL mode used | `CRM_DATABASE_SSLMODE=disable`, because the server is loopback-only and has no TLS |

The CRM application does not read `DATABASE_URL` and does not load `.env`. The migration process was given `CRM_DATABASE_URL` and `CRM_DATABASE_SSLMODE` in its environment only. Those values were not written into source, `.env.example`, or the application default. With `CRM_DATABASE_URL` unset, the application still uses SQLite.

The maintenance database `postgres` was used only to see whether `aadi_crm` existed and to create it. No other database was opened.

## Migration

Command, from `backend`:

```text
.venv\Scripts\python.exe -m app.migrate
```

Result:

```text
PostgreSQL migrations are current for database aadi_crm.
```

Exit code 0. No second migration tool was introduced. The eight scripts recorded in `crm_schema_migrations` are:

1. `001_projects.sql`
2. `002_project_memberships.sql`
3. `003_form_definitions.sql`
4. `004_form_versions.sql`
5. `005_records.sql`
6. `006_followups.sql`
7. `007_reminders.sql`
8. `008_imports.sql`

Before the integration tests, every business table had 0 rows. `crm_schema_migrations` had 8 rows.

## Schema validation

Public tables: `crm_schema_migrations`, `projects`, `project_memberships`, `form_definitions`, `form_fields`, `form_versions`, `records`, `record_values`, `follow_ups`, `record_activities`, `reminder_deliveries`, `import_jobs`, `import_rows`.

Confirmed on this database:

- 21 foreign keys in `public`.
- `form_definitions.current_published_version_id` is nullable text.
- Unique indexes on `lower(code)`, `lower(name)`, `lower(field_key)`, form-field position, form version number, record public number, record sequence, and record value key.
- Partial unique index `uq_project_memberships_one_active_user` includes the active-status predicate.
- Triggers `form_versions_immutable_update` and `form_versions_immutable_delete`.
- An update of a published form version failed with `published form version is immutable`. That check was rolled back. `projects` was still 0 afterward.

## Tests

PostgreSQL, against `aadi_crm`:

```text
19 passed
```

`tests/test_postgres_support.py` was run with `CRM_TEST_DATABASE_URL` pointed at `aadi_crm` and `CRM_DATABASE_SSLMODE=disable`. The 19 tests include configuration selection and the live checks for migrations, foreign keys, immutability, concurrent record numbers, concurrent form-version numbers, reminder claim, and the Kolkata due date. The application path under test used PostgreSQL and did not fall back to SQLite.

SQLite regression, with `CRM_DATABASE_URL` and `CRM_TEST_DATABASE_URL` unset:

```text
84 passed, 6 skipped
```

The six skips are the PostgreSQL integration tests, which are skipped when `CRM_TEST_DATABASE_URL` is unset. One existing Starlette warning about `httpx` was reported. Passing this suite does not prove the PostgreSQL database; the 19 passing tests above are that result.

## Rows left by the PostgreSQL tests

The integration tests commit fixture rows. They were not copied from SQLite. Counts after that run:

| Table | Rows |
| --- | ---: |
| crm_schema_migrations | 8 |
| projects | 4 |
| project_memberships | 4 |
| form_definitions | 4 |
| form_fields | 3 |
| form_versions | 5 |
| records | 3 |
| record_values | 3 |
| follow_ups | 1 |
| record_activities | 1 |
| reminder_deliveries | 4 |
| import_jobs | 0 |
| import_rows | 0 |

The database was not dropped, truncated, or recreated after creation.

## Unchanged

- SQLite file `backend/data/aadi_crm.sqlite`: 610,304 bytes, SHA-256 `b1f1e61969ca38c212dbcf17513899fd2047995da8e95c9167e013c3cda048d5`, the same as before this stage.
- No SQLite rows were copied.
- No Control Plane database was accessed.
- Application code and the default database selection were not changed.

## Remaining blockers

- The running application still uses SQLite until `CRM_DATABASE_URL` is exported in its process. `backend/.env` still has `DATABASE_URL` only, which CRM does not read.
- This loopback server has TLS off. `disable` must not be copied to a remote server; remote PostgreSQL still requires `verify-full`.
- SQLite data has not been migrated.
- Reordering or removing form fields still has no advisory lock. That behavior was left as recorded in the Stage 1 report.
- The fixture rows above are in `aadi_crm`. Clearing them would be a later, explicit choice. This stage did not delete them.

## Next step

To exercise the API against this database, export `CRM_DATABASE_URL` for `aadi_crm` and set `CRM_DATABASE_SSLMODE=disable` for this loopback server only. Do not copy SQLite rows until that is requested separately.
