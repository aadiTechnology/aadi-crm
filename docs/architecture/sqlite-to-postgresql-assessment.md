# SQLite to PostgreSQL assessment

Status: assessment and plan only. No application code, schema, data, or environment file was changed. No production database was contacted. Implementation waits for the decisions in [sqlite-to-postgresql-decision-checklist.md](sqlite-to-postgresql-decision-checklist.md).

Date of inspection: 22 October 2026.

Repository: `aadi-crm`. The CRM database is not the Control Plane database. Authentication, subscriptions, and the audit log stay in the Control Plane.

## Executive summary

The CRM stores its own data in one SQLite file through the Python standard-library `sqlite3` driver. FastAPI route functions are synchronous. Each request that needs CRM data opens one connection, and most of those requests also run the migration runner. SQL is hand-written in store modules. There is no ORM, no connection pool, no `DATABASE_URL`, and no background worker process.

What can be reused:

- The table layout, primary keys, foreign keys, checks, and indexes in migrations `001` through `008`.
- UUID text primary keys. Nothing uses `AUTOINCREMENT` or SQLite `rowid` as an application identifier.
- Application-level tenant and project authorization. It does not need a new database policy language for the first cutover.
- JSON and timestamps stored as text, copied byte for byte, so published form snapshots and reminder idempotency keys stay unchanged.
- The existing pytest suite as the SQLite regression baseline.
- Parameterized queries. A small connection adapter can translate `?` placeholders. The queries themselves do not need an ORM rewrite.

What must change:

- The driver, connection lifecycle, and migration runner. `sqlite3` cannot talk to PostgreSQL.
- Two published-form triggers that use `RAISE(ABORT, ...)`.
- The dashboard expression that turns a follow-up due instant into an Asia/Kolkata calendar date with SQLite `datetime(...)`.
- Reminder claiming. SQLite serializes writers; PostgreSQL needs `FOR UPDATE SKIP LOCKED` so two requests cannot claim the same row.
- Record-number and form-version allocation. `BEGIN IMMEDIATE` plus `MAX(...) + 1` is safe on SQLite because only one writer runs. PostgreSQL needs a transaction-scoped advisory lock, with the existing unique indexes kept as a backstop.
- Integrity errors. Call sites catch `sqlite3.IntegrityError`. PostgreSQL raises a different exception type, and some call sites currently treat every integrity error as one business conflict.
- Tests that open `sqlite3` directly or run migration scripts with `executescript`.
- Configuration. Add a PostgreSQL URL and keep the password out of source, logs, and Git. `.env` is not ignored today.

The local file `backend/data/aadi_crm.sqlite` was opened read-only during this assessment. It is 610,304 bytes, last written 21 October 2026 08:50:50 local time, and `PRAGMA integrity_check` returned `ok`. `PRAGMA foreign_key_check` returned no violations. Those facts are a point-in-time observation, not a frozen baseline and not a backup. Stage 0 must take a restorable copy and recount.

Recommended order: freeze a baseline, prepare a disposable PostgreSQL database, make the application dialect-aware while tests still pass on SQLite, create the PostgreSQL schema, dry-run the copy, reconcile, and only then plan a write freeze and cutover. Do not run two writable databases as sources of truth.

## 1. Current architecture and database access

### 1.1 Runtime versions

Declared in `backend/pyproject.toml`:

| Component | Declared |
| --- | --- |
| Python | `>=3.11` |
| FastAPI | `>=0.115` |
| Uvicorn | `>=0.32` |
| HTTPX | `>=0.27` |
| tzdata | `>=2024.1` |
| pytest (dev) | `>=8` |

Installed in `backend/.venv` at inspection time:

| Component | Installed |
| --- | --- |
| Python | 3.14.3 |
| FastAPI | 0.145.0 |
| Uvicorn | 0.54.0 |
| HTTPX | 0.28.1 |
| pytest | 9.1.1 |
| SQLite library | 3.50.4 (bundled with this Python) |

No database driver other than `sqlite3` is installed. There is no SQLAlchemy, no psycopg, and no async database library. The code calls `sqlite3.Connection.execute`, which Python has provided since 3.12. The package metadata still allows 3.11. That is a pre-existing packaging gap, not a PostgreSQL blocker.

The web app (`frontend/package.json`) is React 19, Vite 7, and React Router 7. It calls the CRM and Control Plane HTTP APIs. It never opens the database.

### 1.2 How connections and transactions are created

`backend/app/db.py` is the only connection factory.

- `CRM_DATABASE_PATH`, when set and non-empty, is the file path. Otherwise the file is `backend/data/aadi_crm.sqlite`.
- A path whose name contains `aadi_platform` is refused, so the CRM process will not open the Control Plane file by that name.
- `connect()` creates the parent directory, opens SQLite with `check_same_thread=False`, sets `row_factory` to `sqlite3.Row`, and runs `PRAGMA foreign_keys = ON`.
- Foreign keys are a connection setting. They are not stored in the file. A raw client that does not run that pragma does not enforce them. The application path does.
- Journal mode is the SQLite default `delete`. WAL is not enabled. `PRAGMA busy_timeout` is not set on the connection factory. It is set to 5000 milliseconds only on the write paths listed in section 3.

`get_connection()` in `backend/app/api/projects.py` is the FastAPI dependency used by projects, forms, records, follow-ups, reminders, imports, reporting, and the audit route. It calls `apply_migrations()`, opens the configured file, yields the connection, and closes it in `finally`. There is no pool. One request owns one connection. Sync route functions run in the FastAPI thread pool, which is why `check_same_thread=False` is set.

The shell routes do not open the CRM database. The audit route opens one and then ignores it: the audit list is loaded from the Control Plane over HTTP. Opening the CRM database on that route still runs migrations as a side effect.

Transactions:

- The SQLite default isolation level is deferred. The first data-changing statement starts a transaction. Store methods call `commit()` or `rollback()` themselves. There is no request-scoped transaction middleware.
- Record create, record update, record archive, form publish, and draft replacement set `isolation_level = None` (autocommit), set a busy timeout, and run `BEGIN IMMEDIATE` so the write lock is taken before `MAX(...) + 1`.
- Import job creation and the start of import commit do the same.
- Follow-up create, form-field create, project create, membership changes, and reminder sync use the default deferred transaction plus an explicit `commit()`.
- Import commit commits the job status `committing` first, then commits each accepted or rejected row separately, and each new record uses its own immediate transaction inside `create_record()`. A crash after `committing` is resumable. A completed job returns the stored result and does not create more records.

### 1.3 Query style

All CRM persistence is parameterized SQL in these modules:

| Module | Responsibility |
| --- | --- |
| `backend/app/db.py` | Projects, memberships, migration runner |
| `backend/app/forms_store.py` | Form drafts and fields |
| `backend/app/form_versions.py` | Immutable published versions |
| `backend/app/records_store.py` | Records, values, record numbers |
| `backend/app/followups_store.py` | Follow-ups, queues, activity timeline |
| `backend/app/reminders_store.py` | Reminder rows, claim, retry, suppression |
| `backend/app/imports_store.py` | Import jobs, row outcomes, export row selection |
| `backend/app/reporting_store.py` | Project KPIs and completed follow-ups |
| `backend/app/api/reminders.py` | One direct read of `records` for labels |

`backend/app/platform_client.py` uses HTTPX against `PLATFORM_API_BASE_URL` (default `http://localhost:8000`). It does not use SQLite.

`backend/app/spreadsheets.py` parses and writes CSV and XLSX in memory. Those bytes are not a second database.

### 1.4 Functional areas

Projects and memberships live in `projects` and `project_memberships`. Creating a project also inserts an active `project_manager` membership for the creator. Archive sets `status` and keeps the row. Removing a member sets `status` to `removed` and keeps the row. The partial unique index allows one active membership per project and user, and allows another active membership after removal. The last active project manager cannot be removed or demoted. That rule is application code, not a database constraint.

Forms and fields live in `form_definitions` and `form_fields`. `form_definitions.status` is constrained to `draft`. Published state is `current_published_version_id`, not a status value. Field `required` is an integer 0 or 1. The API converts it with `bool(...)`. Field configuration is JSON text.

Published versions live in `form_versions.schema_json`. Publish copies the draft into a new UUID and version number inside an immediate transaction. Publishing the same canonical snapshot again is rejected. Update and delete triggers abort any change to a published row. Replacing the draft from the published version checks that `schema_json` text did not change during the write. Records store `form_version_id` and keep that version when a newer draft is published.

Records use UUID primary keys plus a project-scoped `sequence` and `public_number` of the form `{project_code}-{sequence:04d}`. The next sequence is `COALESCE(MAX(sequence), 0) + 1` inside `BEGIN IMMEDIATE`. Unique indexes on `(project_id, sequence)` and `(project_id, public_number)` are the backstop. Soft delete sets `deleted_at`. Values live in `record_values.value_json`. An update deletes and reinserts that record's values in the same immediate transaction. Search text is lowercased in Python and matched with `LIKE`. List filters use `substr(created_at, 1, 10)` as the UTC calendar day. Sort columns are whitelisted: `created_at`, `updated_at`, `public_number`.

Follow-ups and `record_activities` share one deferred transaction on create, complete, and cancel. Queue membership is calculated from `due_at`, not stored. The zone is `Asia/Kolkata` (`followups_store.QUEUE_ZONE`) because no tenant or project timezone is stored. Due instants are written with the fixed format `%Y-%m-%dT%H:%M:%S.%f+00:00`.

Reminders are rows in `reminder_deliveries`. There is no scheduler and no separate worker. `process_reminders()` runs inside the request that asks for delivery. Insert uses `ON CONFLICT(idempotency_key) DO NOTHING`. The idempotency key includes tenant, follow-up, owner, kind, channel, and the due-instant string. Claim is one `UPDATE ... WHERE id = (SELECT ... ORDER BY eligible_at, id LIMIT 1) RETURNING *`, then a commit, then delivery, then a conditional update from `processing`. Email in the default `test` mode is recorded and is not sent. `live` mode has no provider and fails as not configured. Retry backoff is application code.

Import jobs store parsed rows as JSON text and a SHA-256 of the upload. The original file is not stored. Preview does not allocate record numbers. Commit of a `completed` job returns the stored job. Other statuses resume rows whose outcome is not `accepted`, reusing `import_rows.record_id` when it was reserved. Exports are built in the request and returned as CSV or XLSX, capped at 1000 rows. They are not written to disk.

Dashboards read the same record and follow-up tables. They do not have summary tables. Audit visibility is the Control Plane audit API, filtered by the CRM route. The CRM database has no audit table.

### 1.5 Initialization and migrations

`apply_migrations()` creates `crm_schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)` if needed, lists `backend/migrations/*.sql` in name order, and skips names already stored. It refuses a script whose text contains `drop table` or `delete from`. It runs each script with `executescript`, runs the membership backfill only when `002_project_memberships.sql` is the script just applied, then inserts the version and commits.

`executescript` commits before that version insert. A crash between those steps will apply the script again on the next request. Scripts that are only `CREATE ... IF NOT EXISTS` survive that. `004_form_versions.sql` also runs `ALTER TABLE form_definitions ADD COLUMN ...`, which is not repeatable once the column exists. That hazard exists today.

The membership backfill inserts one active project-manager membership for each project creator who does not already have a membership row. It is not replayed on later startups. A data load into PostgreSQL must happen only after all eight migrations are recorded on an empty database, so the backfill sees no projects and does not invent memberships that differ from the source.

### 1.6 Tests and fixtures

Backend tests are pytest and live in `backend/tests/`. They call `apply_migrations()` on a temporary SQLite file, or execute the SQL files themselves. Several tests copy `backend/data/aadi_crm.sqlite` to a temp file and assert the source file bytes did not change. Frontend tests are Vitest and do not use a database.

No test uses PostgreSQL. Any suite that keeps calling `sqlite3.connect`, `executescript`, or `sqlite3.IntegrityError` will not run unchanged against PostgreSQL.

### 1.7 Processes that touch the database

The CRM API process is the only database client in this repository. Uvicorn is started by hand (`uvicorn app.main:app --host localhost --port 8001`). Reminder delivery, import commit, and report queries are request handlers, not cron jobs or a queue consumer. A write freeze means stopping this API, or otherwise refusing CRM writes. There is no second process to drain.

### 1.8 Persistent data outside the database

| Data | Where it lives |
| --- | --- |
| CRM rows | `backend/data/aadi_crm.sqlite`, or `CRM_DATABASE_PATH` |
| Uploaded spreadsheets | Parsed into `import_rows` JSON. The file bytes are not stored. |
| Generated CSV and XLSX | Response bodies only |
| File form fields | Rejected with "File upload is not available." No upload directory. |
| Domain template workbook | `backend/app/domain_templates.py` points at `c:\Users\lenovo\Downloads\CRM.xlsx` as a developer source for template definitions. It is not the CRM system of record. |
| Control Plane users, sessions, audit | Another service and database, reached by HTTP |

A SQLite backup does not back up the Control Plane, and it does not need to include an upload directory. The template workbook is outside this repository and is not part of the row migration.

### 1.9 Environment variables

| Name | Used by | Purpose |
| --- | --- | --- |
| `CRM_DATABASE_PATH` | `backend/app/db.py` | SQLite file path |
| `PLATFORM_API_BASE_URL` | `backend/app/api/shell.py`, startup log | Control Plane base URL |
| `CRM_REMINDER_EMAIL_MODE` | `backend/app/reminders_store.py` | `test` (default) or `live` |
| `VITE_API_BASE_URL` | `frontend/src/lib/config.ts` | Browser Control Plane URL |
| `VITE_CRM_API_BASE_URL` | `frontend/src/lib/config.ts` | Browser CRM URL |

There is no `.env` or `.env.example` in the repository. No PostgreSQL variable exists yet. Startup logs the SQLite file name, not a connection string. That restraint must remain: never log a URL that could contain a password.

`.gitignore` ignores `backend/data/` and `*.sqlite`. It does not ignore `.env`. `git check-ignore .env` does not match. No `.env` file is present, and no database password was found in source. Add `.env` to `.gitignore` before any PostgreSQL password exists on disk, and add a `.env.example` that contains names and placeholders only.

### 1.10 Local file observed read-only

This is not a Stage 0 baseline. The file can still change, and no restorable copy was made.

| Fact | Observation |
| --- | --- |
| Path | `backend/data/aadi_crm.sqlite` |
| Size | 610,304 bytes (149 pages × 4096) |
| Last write | 21 October 2026 08:50:50 local |
| Integrity check | `ok` |
| Journal mode | `delete` |
| Foreign-key check | 0 violations |
| Migrations recorded | `001` through `008` |
| Tracked by Git | No |

Row counts at that read:

| Table | Rows |
| --- | ---: |
| crm_schema_migrations | 8 |
| projects | 22 |
| project_memberships | 24 |
| form_definitions | 27 |
| form_fields | 129 |
| form_versions | 34 |
| records | 29 |
| record_values | 60 |
| follow_ups | 25 |
| record_activities | 38 |
| reminder_deliveries | 76 |
| import_jobs | 4 |
| import_rows | 12 |

The raw read-only connection reported `PRAGMA foreign_keys = 0` because that connection did not execute the application's pragma. `foreign_key_check` still walks the declared foreign keys. The application connection factory turns enforcement on.

## 2. Existing migration inventory

Scripts are applied in filename order. All eight are recorded on the local file.

| Script | Creates or alters | Notable constraints |
| --- | --- | --- |
| `001_projects.sql` | `projects` | Status check. `length(trim(code))` and `length(trim(name))`. Unique index on `(tenant_id, lower(code))`. |
| `002_project_memberships.sql` | `project_memberships` | Role and scope checks must match. Foreign key to `projects`. Partial unique index on `(project_id, user_id) WHERE status = 'active'`. Python backfill runs once with this script. |
| `003_form_definitions.sql` | `form_definitions`, `form_fields` | Unique `(project_id, lower(name))`. Field type check. `required` in `(0, 1)`. Unique `(form_id, lower(field_key))` and `(form_id, position)`. |
| `004_form_versions.sql` | `form_versions`, column on `form_definitions`, two triggers | Unique `(form_id, version_number)`. `schema_json` length greater than 2. Nullable `current_published_version_id` references `form_versions`. Triggers abort update and delete. |
| `005_records.sql` | `records`, `record_values` | Foreign keys to project, form, and form version. Unique `(project_id, public_number)` and `(project_id, sequence)`. Unique `(record_id, field_key)`. |
| `006_followups.sql` | `follow_ups`, `record_activities` | Task type, status, and call-status checks. Foreign keys to project, record, and follow-up. `follow_up_id` is nullable. |
| `007_reminders.sql` | `reminder_deliveries` | Channel, kind, and state checks. Unique `idempotency_key`. Foreign keys to project, record, and follow-up. |
| `008_imports.sql` | `import_jobs`, `import_rows` | Status and outcome checks. Unique `(tenant_id, project_id, idempotency_key)`. Unique `(job_id, row_number)`. `record_id` has no foreign key. |

`crm_schema_migrations` is created by Python, not by a SQL file.

No migration uses `AUTOINCREMENT`, `WITHOUT ROWID`, virtual tables, or full-text search. Primary keys are `TEXT`, supplied by `uuid4()` in Python, except `crm_schema_migrations.version`, which is the script filename.

Foreign keys do not declare `ON DELETE CASCADE`. The default is `NO ACTION` on both SQLite and PostgreSQL. Application deletes are limited to replacing `form_fields` for a draft and replacing `record_values` for a record. Published versions cannot be deleted.

Circular reference, which the load order must respect: `form_versions.form_id` references `form_definitions`, and `form_definitions.current_published_version_id` references `form_versions`. The column is nullable. Insert the form with a null published-version id, insert versions, then set the column.

## 3. SQLite-specific compatibility findings

Do not globally replace SQLite tokens with PostgreSQL tokens. Most `CREATE TABLE` text is already valid PostgreSQL. The behaviors below are not.

### 3.1 Driver and connection API

`sqlite3.Connection`, `sqlite3.Row`, `sqlite3.IntegrityError`, `executescript`, `PRAGMA`, and `isolation_level = None` are SQLite-only. PostgreSQL needs a driver. Use psycopg 3 (`psycopg[binary]`) because route handlers are synchronous and psycopg 3 connections expose `execute`, `commit`, `rollback`, and `rowcount`. Confirm that a Python 3.14 wheel exists before locking the dependency. If it does not, use the source build or stay on a Python version the wheel supports. Do not switch the API to async for this migration.

`row_factory = sqlite3.Row` is how every store reads `row["column"]`. The PostgreSQL connection must use a dict-style row (`psycopg.rows.dict_row` or an adapter). A tuple row will break the stores.

`?` placeholders appear throughout the stores. psycopg uses `%s`. Translate placeholders in one adapter. Current SQL does not contain a literal percent sign, so a careful placeholder translation is safe. LIKE patterns put `%` in bound parameters, which is correct for both drivers. Keep that. Do not interpolate search text.

There is no pool. Keep one connection exclusive to one request. A pool is appropriate only if each request checks out its own connection and returns it in `finally`. Sharing one connection across requests is unsafe because store methods change autocommit mode and commit mid-request.

`PRAGMA foreign_keys = ON` has no PostgreSQL equivalent. PostgreSQL enforces foreign keys unless a session deliberately disables them. The migration tool must not disable them.

`PRAGMA busy_timeout = 5000` has no direct equivalent. SQLite returns "database is locked" when a writer waits past the timeout. PostgreSQL waits on row locks until `lock_timeout` or `statement_timeout`. Set an explicit `lock_timeout` (5 seconds is the current intent) on write transactions so a stuck lock fails instead of hanging a request. Do not copy the pragma text into PostgreSQL.

### 3.2 Migration execution

`executescript` runs a whole file and commits. PostgreSQL should run each migration file in one transaction that also inserts the version row, so a failed script leaves no partial objects and no version row. PostgreSQL allows transactional DDL. That removes the current crash window.

`CREATE TRIGGER IF NOT EXISTS` and `SELECT RAISE(ABORT, ...)` are SQLite. They appear only in `004_form_versions.sql`. PostgreSQL needs a function that `RAISE EXCEPTION` and two `BEFORE UPDATE` / `BEFORE DELETE` `FOR EACH ROW` triggers. PostgreSQL does not support `CREATE TRIGGER IF NOT EXISTS`. Create the function with `CREATE OR REPLACE`, and create each trigger only when the migration version has not been recorded. The exception text `published form version is immutable` should stay, because tests and operators can look for it.

`ALTER TABLE ... ADD COLUMN ... REFERENCES ...` in `004` is valid PostgreSQL if `form_versions` already exists. The script order already does that. It is still not idempotent. The version table, not `IF NOT EXISTS`, must prevent a second run.

`CREATE INDEX IF NOT EXISTS`, expression indexes on `lower(...)`, and partial indexes `WHERE status = 'active'` are valid PostgreSQL. `lower(text)` is immutable, so it may be indexed. Keep the partial predicate. Without it, a removed membership would block a later grant.

SQLite `lower()` folds ASCII letters only. PostgreSQL `lower()` uses the database collation and can fold more Unicode characters. Project codes are restricted to ASCII by the API. Form names and field keys are not. During the dry run, compare `lower()` of every value covered by an expression unique index. If the two functions disagree, stop and report the key. Do not pick a winner silently. For a new database, set `LC_COLLATE` to `C` or another collation chosen in Stage 1 and record it. Collation cannot be casually changed after unique indexes exist.

`length()` and `trim()` in check constraints exist in both databases and count characters for text. Keep them.

`GROUP BY 1, 2` in `reporting_store._by_due_date` is valid PostgreSQL. `SUM(...)` returns `numeric` in PostgreSQL and an integer in SQLite. The reporting code already wraps those values in `int()`. Keep that cast. Do not assume the driver returns a Python `int` for a sum.

### 3.3 Identifiers, integers, booleans, time, and JSON

There is no `AUTOINCREMENT`. Do not introduce identity columns for existing tables. Copy the UUID strings unchanged. Keep the columns as `TEXT`, not PostgreSQL `uuid`. A `uuid` column would come back as a UUID object and break string comparisons and JSON responses unless every reader changed.

SQLite `INTEGER` can hold 64-bit values. PostgreSQL `INTEGER` is 32-bit. The integer columns in this schema are sequence numbers, positions, version numbers, attempt counts, and row numbers. The current data is far below 2^31. Use `INTEGER` and keep the checks. A later overflow would raise a constraint or numeric error instead of wrapping. That is acceptable for this schema. Do not widen types in the first migration unless the dry run finds a value outside the 32-bit range.

`form_fields.required` is `INTEGER NOT NULL CHECK (required IN (0, 1))`. Inserts use Python `1` and `0`. Reads use `bool(row["required"])`. Keep the integer column. A PostgreSQL `boolean` column would force every insert and the check constraint to change, and `bool` already works for 0 and 1.

Timestamps are text, not SQLite date affinities. Two writers exist:

- `datetime.now(UTC).isoformat()` for projects, forms, records, and imports. Microseconds are omitted when they are zero.
- `strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")` for follow-ups and reminders. The fractional seconds are always present.

These differences are load-bearing:

- Record and dashboard date filters use `substr(created_at, 1, 10)`.
- Follow-up queue order is lexicographic on `due_at`. The fixed stamp sorts in time order. A reformatted instant might not.
- `civil_due()` parses `due_at` with that exact stamp.
- Reminder idempotency keys include the due-instant string.
- Draft replacement compares `schema_json` as raw text, not as a reparsed object.

Copy every timestamp and every JSON column as exact text. Do not convert them to `timestamptz` or `jsonb` in this migration. A later type migration is a separate project: it would change filters, queue boundaries, idempotency keys, and snapshot equality. `json.loads` is applied to text in Python. If the driver returned a dict from `jsonb`, those calls would fail.

JSON columns, all text: `form_fields.config_json`, `form_versions.schema_json`, `record_values.value_json`, `import_jobs.mapping_json`, `import_jobs.summary_json`, `import_rows.source_json`, `import_rows.parse_errors_json`, `import_rows.errors_json`, `import_rows.candidates_json`, `import_rows.values_json`.

### 3.4 The dashboard date expression

`reporting_store._DUE_DATE` is:

```text
date(datetime(replace(substr(follow_ups.due_at, 1, 19), 'T', ' '), '+330 minutes'))
```

SQLite takes the first 19 characters (`YYYY-MM-DDTHH:MM:SS`), replaces `T` with a space, adds 330 minutes, and returns a date. 330 minutes is UTC+05:30, which matches Asia/Kolkata because that zone has no daylight saving. PostgreSQL has no `datetime(text, modifier)` function. Replace this one expression with an equivalent cast on the same 19-character prefix, added as `interval '330 minutes'`, then cast to `date`. Keep the 19-character prefix so a longer fractional suffix cannot change the result. Apply it only in the PostgreSQL dialect. Leave the SQLite expression in place while both dialects are supported.

`substr` in the record date filters is valid PostgreSQL (`substring(text from 1 for 10)` is the other spelling; `substr(text, 1, 10)` also exists in PostgreSQL). Keep `substr` if the chosen PostgreSQL version accepts it. Verify that in Stage 3 rather than rewriting every filter in advance.

### 3.5 Locking and allocation

`BEGIN IMMEDIATE` takes the SQLite reserved lock before any read of `MAX(sequence)` or `MAX(version_number)`. A second writer blocks, then reads the committed maximum. That is why concurrent record creates and concurrent publishes in the tests get distinct numbers.

PostgreSQL `BEGIN` does not do that. Under `READ COMMITTED` or `REPEATABLE READ`, two transactions can read the same maximum and insert the same next number. The unique index then rejects one of them. Today:

- `create_record()` does not catch that integrity error. The request fails and the number is not retried.
- `publish_form()` turns any integrity error into "duplicate publish", which would be the wrong error for a version-number race.
- `add_field()` turns any integrity error into "duplicate field key", including a collision on `(form_id, position)`. Field position uses `MAX(position) + 1` without `BEGIN IMMEDIATE`. SQLite's single writer hides most of that race. PostgreSQL will not.

Required behavior, not a text substitution:

- Before allocating a record sequence, take `pg_advisory_xact_lock` on a 64-bit key derived from the project id. Then read `MAX(sequence)` and insert. The lock releases at commit. Keep both unique indexes.
- Before allocating a form version number, take an advisory lock derived from the form id.
- Before allocating a field position, take an advisory lock derived from the form id, and catch the position unique index separately from the field-key unique index.
- SQLite keeps `BEGIN IMMEDIATE`. The adapter should expose one `begin_write(lock_key)` operation that does the SQLite immediate transaction or the PostgreSQL advisory lock.
- Do not add a counter table in the first migration. It would be a new source of truth that also has to be migrated and can drift from `MAX(sequence)`.

Import commit uses `BEGIN IMMEDIATE` so two requests cannot both move a job into `committing` and then both create records. The job status update must be conditional, and the transaction must lock the job row (`SELECT ... FOR UPDATE`) on PostgreSQL. The completed-job short circuit must stay: status `completed` returns the stored body and allocates nothing. Rows already `accepted` stay accepted. A reserved `record_id` is reused.

Reminder claim must become:

```text
UPDATE reminder_deliveries
SET state = 'processing', attempt_count = attempt_count + 1, ...
WHERE id = (
    SELECT id
    FROM reminder_deliveries
    WHERE <same eligibility predicates>
    ORDER BY eligible_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *
```

The eligibility predicates, the attempt increment, the later update that only finishes a `processing` row, and `ON CONFLICT(idempotency_key) DO NOTHING` stay. SQLite does not support `SKIP LOCKED`, so this statement is dialect-specific. The SQLite statement can stay as it is because the database writer lock makes the current claim atomic.

`ON CONFLICT(idempotency_key) DO NOTHING` is valid PostgreSQL against the unique constraint on that column. Keep it. Do not switch it to `DO UPDATE`. An existing reminder must not be overwritten by a second insert.

### 3.6 Case, pagination, and search

Project search lowercases the column in SQL and the term in Python, then uses `LIKE ... ESCAPE`. Record search lowercases text before it is stored. PostgreSQL `LIKE` is case-sensitive, which matches this pattern because both sides are already lowercased. SQLite `LIKE` is case-insensitive for ASCII, but the application does not rely on that for these queries.

`ESCAPE '\'` is already what both engines should receive from the current Python string. Verify one search for `%` and `_` on PostgreSQL in Stage 7. Do not rewrite the escape clause unless that test fails.

`LIMIT` and `OFFSET` are valid in both. Sort columns stay whitelisted.

### 3.7 Startup races

Every CRM request currently attempts to migrate. Two processes can both decide a script is pending. On PostgreSQL that can run `ALTER TABLE` twice or create a trigger twice. For PostgreSQL, stop migrating inside `get_connection()`. Provide a command, for example `python -m app.migrate`, and make application startup fail with a clear message when `crm_schema_migrations` is behind the files on disk. SQLite may keep the current auto-migrate behavior until cutover so local development does not change in the same step. That split is an owner decision in the checklist.

### 3.8 What is already compatible

These do not need a semantic change: UUID text keys, check constraints, inner joins, `CASE`, `COALESCE`, `COUNT(*)`, bound parameters, `INSERT ... ON CONFLICT DO NOTHING` on `idempotency_key`, `UPDATE ... RETURNING` once the claim lock is added, partial unique indexes, expression unique indexes, and foreign keys with default `NO ACTION`.

## 4. Table-by-table data migration

Source and target names are the same. Copy columns by name, not by ordinal. Insert every column explicitly so database defaults cannot fill a historical null. Preserve nulls. Do not recompute `public_number`, `sequence`, version numbers, UUIDs, idempotency keys, or JSON.

If a row violates a target constraint, stop that table, write the primary key and the constraint name to the reconciliation report, and leave the source untouched. Do not drop the row. Do not generate a new id.

Load a disposable database created by the PostgreSQL migrations. Do not load into a database that already contains CRM rows unless the run is an explicit resume and every existing primary key is identical to the source. The default dry-run recovery is to drop the disposable database and start again.

### 4.1 Load order

1. `projects`
2. `project_memberships`
3. `form_definitions` with `current_published_version_id` forced null on insert
4. `form_fields`
5. `form_versions`
6. Update `form_definitions.current_published_version_id` from the source value
7. `records`
8. `record_values`
9. `follow_ups`
10. `record_activities`
11. `reminder_deliveries`
12. `import_jobs`
13. `import_rows`

Do not copy `crm_schema_migrations`. The schema command records `001` through `008` while creating an empty database. After the load, assert those eight names are present. `applied_at` may differ.

Do not run the membership backfill against a populated `projects` table.

`import_rows.record_id` has no foreign key. After the load, report any non-null `record_id` that is absent from `records`. Keep the row. Do not add a foreign key in this project to "clean it up".

The immutability triggers block `UPDATE` and `DELETE` on `form_versions`. The load only inserts, so the triggers stay enabled. Do not disable triggers or foreign keys.

### 4.2 Column plan

Conversion for every column below is exact text or exact integer, null stays null, and defaults are not applied on copy. "Stable id" means the application and other tables store that value and it must not be regenerated.

`projects`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. Primary key. |
| tenant_id | TEXT | no | Tenant isolation. Copied as stored. |
| code | TEXT | no | Part of `public_number`. Do not renorm case. |
| name, description, status | TEXT | no | `description` default `''` only for future inserts. |
| created_by | TEXT | yes | |
| created_at, updated_at | TEXT | no | Exact ISO text. |

`project_memberships`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. |
| tenant_id, project_id, user_id | TEXT | no | `project_id` must exist in `projects`. |
| role, scope_policy, status | TEXT | no | Checks must match the source pairs. |
| created_by, updated_by | TEXT | yes | |
| created_at, updated_at | TEXT | no | Exact text. |

`form_definitions`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. |
| tenant_id, project_id, name | TEXT | no | |
| description, status | TEXT | no | Status is `draft` even when a version is published. |
| created_by, updated_by | TEXT | yes | |
| created_at, updated_at | TEXT | no | |
| current_published_version_id | TEXT | yes | Set in step 6, after `form_versions`. Stable version id. |

`form_fields`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. Not copied into the published snapshot body. |
| tenant_id, project_id, form_id, field_key, label, field_type | TEXT | no | |
| required | INTEGER | no | 0 or 1 only. |
| help_text, section_name | TEXT | no | |
| position | INTEGER | no | Preserve. Do not renumber. |
| config_json | TEXT | no | Exact text, default `'{}'` is not reapplied. |
| created_at, updated_at | TEXT | no | |

`form_versions`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. Records and imports point here. |
| tenant_id, project_id, form_id | TEXT | no | |
| version_number | INTEGER | no | Preserve. Do not recompute from publish order. |
| schema_json | TEXT | no | Exact snapshot text. |
| published_by, published_at | TEXT | no | |

`records`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. Import rows and follow-ups point here. |
| tenant_id, project_id, form_id, form_version_id | TEXT | no | Version id stays on the historical snapshot. |
| public_number | TEXT | no | Stable display number. |
| sequence | INTEGER | no | Must remain unique per project and consistent with `public_number`. |
| display_name, search_text, source | TEXT | no | `search_text` is already lowercased by the application. |
| assignee_user_id, created_by, updated_by | TEXT | no | |
| created_at, updated_at, captured_at | TEXT | no | Exact text. Date filters depend on the first 10 characters. |
| deleted_at | TEXT | yes | Null means active. Do not clear archived rows. |

`record_values`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. |
| record_id, tenant_id, project_id, field_key | TEXT | no | |
| value_json | TEXT | no | Exact JSON text, including field values. |

`follow_ups`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. Reminder keys are derived from it plus `due_at`. |
| tenant_id, project_id, record_id, task_type, owner_user_id | TEXT | no | |
| due_at | TEXT | no | Exact stamp. Do not shift timezone. |
| status | TEXT | no | |
| call_status | TEXT | yes | |
| summary, outcome, created_by, updated_by | TEXT | no | |
| created_at, updated_at | TEXT | no | |
| completed_at, cancelled_at | TEXT | yes | |

`record_activities`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. |
| tenant_id, project_id, record_id, actor_id, event_type, summary, occurred_at | TEXT | no | |
| follow_up_id | TEXT | yes | Null when the event is not a follow-up. |

`reminder_deliveries`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. |
| tenant_id, project_id, record_id, follow_up_id, recipient_user_id | TEXT | no | |
| recipient_email | TEXT | yes | Copied as stored. The report must not print it. |
| channel, kind, due_at, eligible_at, idempotency_key, state | TEXT | no | Idempotency key is unique and stable. |
| attempt_count | INTEGER | no | Preserve. Do not reset retries. |
| last_attempt_at, last_error, next_retry_at, read_at | TEXT | yes | |
| created_at, updated_at | TEXT | no | |

`import_jobs`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. |
| tenant_id, project_id, form_id, form_version_id, actor_user_id | TEXT | no | Version id is the published snapshot used for that job. |
| idempotency_key, filename, content_sha256, status | TEXT | no | Unique with tenant and project. |
| mapping_json, summary_json | TEXT | yes | Exact text. |
| created_at, updated_at | TEXT | no | |

`import_rows`

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| id | TEXT | no | Stable id. |
| job_id, tenant_id, project_id | TEXT | no | |
| row_number | INTEGER | no | Unique per job. |
| source_json, parse_errors_json, errors_json, candidates_json | TEXT | no | Exact text. Source cells live here. |
| decision | TEXT | yes | |
| outcome | TEXT | no | Preserve `accepted`, `working`, and terminal outcomes. |
| values_json | TEXT | yes | |
| record_id | TEXT | yes | Preserve. Dangling ids are reported, not deleted. |

### 4.3 Extra checks after the copy

- Row count equal for every business table.
- Set of primary keys equal for every business table.
- Every foreign key column value exists, except nullable columns and `import_rows.record_id`, which is reported rather than required by the schema.
- For each project, `MAX(sequence)` equals the count of distinct sequences, and every `public_number` matches the stored code and sequence using the same zero-padding rules. A mismatch is a report item, not a rewrite.
- For each form, version numbers are a unique set and `current_published_version_id` is null or points at a version of that form.
- `schema_json` and `value_json` checksums use the raw bytes, not a reparsed document.
- No `form_versions` row was updated. A second checksum of `schema_json` after the load must match the first.
- Reminder `idempotency_key` values are unique and equal to the source set.
- Import jobs in `completed` stay `completed`. Their accepted rows still point at the same record ids.
- `lower()` disagreements on the three expression unique indexes are listed before any cutover.

### 4.4 Restart

The tool reads a SQLite snapshot opened read-only and writes only to the named disposable PostgreSQL database. It refuses a target whose database name or host is on an explicit deny list agreed in Stage 1. It refuses to run when the target already has CRM rows unless `--resume` is passed. Resume inserts a row only when that primary key is absent, and aborts when the primary key exists with different stored values. It never updates or deletes source rows. It never updates a published `form_versions` row.

## 5. PostgreSQL environment and configuration

Nothing in the repository chooses a PostgreSQL version, host, database name, or TLS mode. Do not invent a password. Do not point this work at a production instance.

Recommended target for the first implementation: PostgreSQL 16 or 17, one new database used only by CRM, owned by a login role that is not a superuser and is not the owner of any other application database. Schema `public` in that dedicated database is enough. A separate schema adds `search_path` risk without a current multi-tenant database design. Tenant isolation stays in the SQL `tenant_id` predicates and the Python authorization checks.

The role needs `CONNECT` on the database, `USAGE` and `CREATE` on the schema during migrations, and `SELECT`, `INSERT`, `UPDATE`, `DELETE` on the CRM tables at runtime. It does not need `CREATEDB`, `CREATEROLE`, or `BYPASSRLS`. Migration and runtime can be the same role for the first local environment. Split them before a shared environment if operations wants the application unable to run DDL.

Proposed variables, names only:

| Name | Format |
| --- | --- |
| `CRM_DATABASE_URL` | `postgresql://USER@HOST:PORT/DATABASE` |
| `CRM_DATABASE_SSLMODE` | `disable` for a local socket or loopback, `verify-full` for any remote host |
| `PGPASSWORD` | Supplied by the process environment or a local `pgpass` file, never by source code |

Keep `CRM_DATABASE_PATH` for SQLite. Select the dialect from the URL scheme when `CRM_DATABASE_URL` is set. When it is unset, keep today's SQLite path. Refuse a URL whose database name contains `aadi_platform`, matching the current Control Plane guard.

Do not put the password in `CRM_DATABASE_URL`. Process lists and error messages can expose a URL. The startup log must continue to print a database name only.

TLS: require verification for any host that is not loopback. Stage 1 records the host class and the sslmode actually negotiated. Do not disable certificate checks to make a remote connection succeed.

This assessment did not create a database, a role, or a container.

## 6. Backup and restore prerequisites

Stage 0 produces the backup. This assessment did not.

SQLite backup procedure:

1. Stop CRM writers, or use the SQLite online backup API / `VACUUM INTO` so the copy is consistent. A filesystem copy of a file opened by a writer is not a verified backup.
2. Write the copy to a path outside the repository, for example a dated file next to operator backups. Do not put it in `backend/data/` where the application could open it, and do not commit it.
3. Open the copy read-only, run `PRAGMA integrity_check`, and compare table counts with the source.
4. Restore drill: point a disposable `CRM_DATABASE_PATH` at a second copy and run the existing pytest module that reads a migrated database, or run `apply_migrations()` and the row-count query. A backup that has not been opened is not verified.
5. Keep the original file unmodified. The application must not be given a path that overwrites it.

Also copy `backend/app` and `backend/migrations` as they were at the baseline, because the SQL files are the schema definition. The Git revision is the right record. Do not invent a tag unless the owner asks.

PostgreSQL restore, after cutover backups exist, is `pg_dump` custom format of the CRM database only, restored with `pg_restore` into an empty database. That dump is a post-cutover concern. It is not a substitute for the SQLite snapshot taken before the copy.

Related assets: there is no upload directory to include. The Control Plane database is out of scope and must not be dumped by this project.

## 7. Staged plan

Each stage starts only after the previous stage's acceptance criteria are met and, where noted, the owner has approved the next stage.

### Stage 0 — Baseline and backup

Dependencies: none. Read-only on the source. No PostgreSQL writes.

Work: record the Git revision, the SQLite file path, size, last write time, integrity check, journal mode, migration versions, and row counts. Take a restorable copy by the procedure in section 6 and prove it opens. Run `backend/.venv\Scripts\python.exe -m pytest` and record the result. Run the frontend Vitest suite if the owner wants the full product baseline. Recount immediately before the eventual final copy. Do not delete, vacuum, or migrate the live file.

Acceptance: a restorable copy exists, integrity is `ok`, counts are written down, and the current test suites have a recorded result. The original file's size and checksum match the values taken before the tests that only read it.

### Stage 1 — PostgreSQL environment

Dependencies: Stage 0 recommended, owner decision on version and host.

Work: install or start the agreed non-production PostgreSQL. Create the empty database and role. Confirm connectivity with `sslmode` recorded. Confirm the psycopg wheel imports on the CRM virtualenv's Python. Confirm `SELECT version()` and the collation. Do not create production infrastructure and do not open the SQLite file for writing.

Acceptance: a throwaway query succeeds as the CRM role, the role is not a superuser, and no password was written into the repository.

### Stage 2 — Dialect adapter and SQL compatibility

Dependencies: Stage 1 driver check. Owner approval of advisory locks, text timestamps, text JSON, and migration-on-request behavior.

Work: add the driver. Introduce a connection adapter used by the stores. Translate placeholders, row mapping, integrity errors, `begin_write`, and the three dialect-specific statements (form-version triggers, due-date expression, reminder claim). Add PostgreSQL migration files for `001` through `008`, identical in structure, with triggers rewritten. Keep SQLite files working. Add `python -m app.migrate`. Change PostgreSQL startup so it checks versions and does not apply them per request. Map unique violations by constraint name for publish, field insert, project code, and membership. Add `.env` to `.gitignore` and add `.env.example` with placeholders.

Acceptance: the existing SQLite pytest suite passes without a PostgreSQL server. A focused PostgreSQL test, against the disposable database only, covers one project create, one publish, one record create, and one rejected form-version update.

### Stage 3 — Schema on a fresh database

Dependencies: Stage 2.

Work: drop and create the disposable database, run `python -m app.migrate` twice, and compare catalogs to the migration files: tables, columns, types, nullability, defaults, checks, primary keys, foreign keys, unique indexes, partial indexes, expression indexes, and both triggers. Prove the second run changes nothing.

Acceptance: catalog checklist matches section 2, the second run is a no-op, and the SQLite file checksum is unchanged.

### Stage 4 — Copy tool

Dependencies: Stage 3 and the column plan in section 4. This stage writes the tool. It does not perform the production cutover.

Work: implement the read-only snapshot reader, the ordered load, the two-phase published-version update, the refusal rules, and the reconciliation report. The report contains counts, key sets, constraint names, and checksums. It must not contain emails, record values, or credentials.

Acceptance: unit tests of the refusal rules pass, including a refusal to touch a database name containing `aadi_platform`, and a refusal to update the SQLite source.

### Stage 5 — Dry run

Dependencies: Stage 4 and a fresh Stage 0 snapshot.

Work: run the tool from the snapshot into an empty disposable database. Compare counts and checksums. Attempt an update and a delete of one published version and expect both to fail. Rerun into a second empty database and compare checksums. Attempt resume onto a matching copy and onto a copy with one altered row. The altered row must abort the resume.

Acceptance: counts match, foreign keys hold, checksums match, immutability holds, and the source snapshot checksum is unchanged. Every unexplained difference blocks cutover.

### Stage 6 — Application against PostgreSQL

Dependencies: Stage 5 accepted.

Work: configure the disposable database through the environment. Exercise the API against it. Confirm authorization still filters by tenant and membership in Python. Confirm record numbers, import resume, and reminder claim under two concurrent requests. Confirm migrations are not applied by an ordinary request. Tests that still use SQLite keep using temporary files. Add an optional PostgreSQL test database setting so a developer can run the integration suite without touching the dry-run database.

Acceptance: concurrent record creates receive distinct sequences, a completed import retry creates no extra record, two reminder workers do not both return the same claimed id, and a cross-tenant read still returns not found.

### Stage 7 — Reconciliation suite

Dependencies: Stage 6.

Work: run the test list in section 8 on SQLite and on PostgreSQL. Produce the source-to-target report from a new dry run of the latest snapshot.

Acceptance: both suites pass, or every failure has a written cause and a fix. The report has no unexplained difference.

### Stage 8 — Cutover and rollback

Dependencies: explicit owner approval after Stage 7. Not part of the current task.

Work: follow section 10.2. Do not start this stage from this assessment alone.

Acceptance: smoke checks pass on PostgreSQL, the SQLite file is still present and unchanged since the final snapshot, and the running process has a single writable CRM database.

## 8. Test and reconciliation strategy

SQLite tests stay the fast default. PostgreSQL tests run against a database created for the test run, dropped afterwards, and selected only when `CRM_TEST_DATABASE_URL` is set. They must refuse the cutover database and any name containing `aadi_platform`.

| Area | What to prove |
| --- | --- |
| Schema | Migrations apply once, the second run is a no-op, catalog matches section 2, triggers abort update and delete, insert still works. |
| Projects | Create, duplicate code, archive keeps the row, last manager cannot be removed, removed member can be granted again. |
| Authorization | A member of another tenant, and a user without a project membership, cannot read or write. Platform-only keys do not open projects. |
| Forms | Draft changes do not change `form_versions`. Identical republish is rejected. Version numbers stay gap-free under two concurrent publishes. |
| Records | Create, update, stale `updated_at`, soft delete, search, UTC day filters, sort whitelist. Two concurrent creates get two sequences and two public numbers. |
| Follow-ups | Create writes a follow-up and an activity. Queue boundaries follow Asia/Kolkata. Complete and cancel keep the row. |
| Reminders | Same idempotency key does not add a row. Claim is single-winner. Retry moves `retryable` according to the existing attempt rules. Closed follow-ups suppress pending rows. |
| Imports | Preview creates no record. Commit is idempotent for `completed`. A `working` row keeps its reserved record id. Duplicate commit does not double-allocate. |
| Exports | Filtered CSV and XLSX match the record query and stay within the 1000-row cap. |
| Dashboards | KPI and queue counts match the record and follow-up queries for the same filters, including the Kolkata due date. |
| Audit | The CRM route still reads the platform audit API and still rejects unsupported filters. It does not read a CRM audit table. |
| Failures | A thrown error during record update leaves the previous values in place. A failed migration does not record its version. |

Reconciliation for every business table: source count, target count, primary-key set equality, and a checksum of the ordered raw column values. Investigate any difference. Known acceptable differences are only `crm_schema_migrations.applied_at` and the absence of that table's rows in the data load. No other difference is acceptable by default.

Checksums must be computed by the tool, not by eye, and the report must omit customer field values. An operator should be able to see which primary key failed a foreign key or checksum without seeing the stored email or note.

## 9. Effort

One engineer who already knows this repository, PostgreSQL 16 or 17 available locally, text timestamps and text JSON retained, no ORM, no row-level security, and a data size on the order of the current file (under one megabyte). Larger data does not change the design, but it changes the dry-run time.

| Stage | Effort | Notes |
| --- | ---: | --- |
| 0 Baseline and backup | 0.5 day | Includes a full backend pytest run. |
| 1 PostgreSQL environment | 0.5 day | Longer if the host or TLS design is undecided. |
| 2 Adapter and dialect SQL | 4 to 6 days | Largest code stage. SQLite suite must stay green. |
| 3 Schema verification | 0.5 to 1 day | |
| 4 Copy tool | 2 to 3 days | |
| 5 Dry run and fix-up | 1 to 2 days | Depends on `lower()` and constraint surprises. |
| 6 Application integration | 2 to 3 days | Concurrency tests are the bulk. |
| 7 Full reconciliation | 2 to 3 days | |
| 8 Cutover window | 0.5 day of procedure, plus a short maintenance window | Excludes waiting for approval. |

Total: about 13 to 19 engineering days, plus owner review between stages. Stage 2 is the critical path. Stages 4 and 5 can be designed in parallel with the later part of Stage 2 only after the PostgreSQL migration SQL is stable.

## 10. Risks, decisions, and rollback

### 10.1 Risks

| Risk | Why it matters | Mitigation |
| --- | --- | --- |
| `BEGIN IMMEDIATE` replaced by a plain `BEGIN` | Duplicate record numbers or a version race reported as a duplicate publish | Advisory locks plus the existing unique indexes, with concurrency tests |
| Reminder claim left unchanged | Two requests deliver one reminder | `FOR UPDATE SKIP LOCKED` and a two-worker test |
| JSON or timestamps reformatted | Snapshot inequality, queue misclassification, reminder key splits | Exact text copy. Type changes are out of scope. |
| Expression `lower()` differs for non-ASCII names | Unique index rejects a row SQLite accepted, or two names collapse | Dry-run comparison. Stop on disagreement. |
| Per-request migrations on PostgreSQL | Two API processes apply one `ALTER` | Separate migrate command for PostgreSQL |
| Integrity errors mapped too broadly | Position races surface as duplicate field keys | Catch named constraints |
| `.env` not ignored | A future password gets committed | Ignore `.env` before credentials exist |
| Circular foreign key loaded in one insert | Load fails or the published pointer is lost | Two-phase load in section 4.1 |
| Both databases writable | Split history that cannot be merged | One writable target. SQLite is read-only after the final snapshot. |
| Tests open the developer SQLite file | A migration experiment changes local data | PostgreSQL tests use a URL guard. Existing copy tests already assert the source bytes. |
| Python 3.14 driver wheel missing | Stage 1 cannot install psycopg | Check the wheel before writing the adapter. Fall back to a supported Python if needed. |
| Local file is not the file that will be cut over | Counts in this document go stale | Stage 0 and the final snapshot recount the file that operators name. |

Row-level security is not recommended in the first migration. A mistaken policy would change authorization that the Python code already tests. Revisit it only after the cutover is stable.

### 10.2 Cutover and rollback

Preconditions: Stages 0 through 7 accepted, a named maintenance window, and a written rollback owner.

1. Stop CRM writes. Stop the API process. Confirm no second process has `CRM_DATABASE_PATH` or the PostgreSQL URL.
2. Take the final SQLite snapshot and verify integrity and counts. This snapshot is the rollback database.
3. Run the migration into a new empty PostgreSQL database. Run reconciliation. Any unexplained difference aborts the cutover. The application stays stopped and SQLite remains the source of truth.
4. Set `CRM_DATABASE_URL` for the API process only. Do not leave `CRM_DATABASE_PATH` pointing at a file the process will also write. The PostgreSQL process must ignore the SQLite path.
5. Start one API process. Run smoke checks: sign-in through the Control Plane, open one tenant, list projects, open one record, open one follow-up queue, open reminders, and read one report. Compare those counts with the reconciliation report.
6. Watch error logs and request duration for the agreed observation window. The application already logs status, duration, and request id without row contents.
7. Keep the SQLite file and the final snapshot until the owner approves retirement. Do not delete them in the cutover window.

Rollback trigger: reconciliation failure before traffic returns, smoke-check failure, a write error that the SQLite suite did not show, or the rollback owner's call during the observation window.

Rollback procedure: stop the API, unset `CRM_DATABASE_URL`, restore `CRM_DATABASE_PATH` to the final snapshot, start the API, and repeat the smoke checks against SQLite. Discard the PostgreSQL database or keep it for diagnosis, but do not serve traffic from it.

Writes after the snapshot: if the API stayed stopped, there are none. If a write reached SQLite after the snapshot and before the switch, the cutover is invalid. Stop, take a new snapshot, and migrate again. If a write reached PostgreSQL after the switch, rolling back to SQLite loses that write. The rollback owner must decide whether to accept that loss or to extract those PostgreSQL rows by primary key and replay them manually. The copy tool must not be pointed back at SQLite to "sync" the two. There is no bidirectional replication in this plan.

Do not retire the SQLite file until a later explicit approval. Retirement means moving the file and its snapshot to offline retention, not deleting them on the same day as cutover.

### 10.3 Unresolved decisions

These are copied into the checklist. The recommended default is in parentheses.

- PostgreSQL major version and host (16 or 17, local non-production first).
- Database name and role name (dedicated CRM database, non-superuser role).
- TLS mode (`disable` only for loopback, otherwise `verify-full`).
- Keep text timestamps and text JSON for this migration (yes).
- Sequence allocation by advisory lock rather than a new counter table (yes).
- PostgreSQL migrations as a separate command, SQLite auto-migrate unchanged until cutover (yes).
- CI runs the PostgreSQL suite before cutover (yes, on a disposable service).
- Who may approve Stage 1, Stage 8, and later SQLite retirement.

## 11. Files expected to change

No file in this list should change before the corresponding stage is approved. This assessment adds only the two documents named at the top.

### Stage 1

No repository file is required if the database is created outside the repo. Optional notes stay in the operator's environment, not in source.

### Stage 2

| File | Change |
| --- | --- |
| `backend/pyproject.toml` | Add psycopg. Pin it after the wheel check. |
| `backend/app/db.py` | Dialect selection, adapter, transactional PostgreSQL migrate, SQLite path preserved. |
| `backend/app/migrate.py` | New module entry for `python -m app.migrate`. |
| `backend/app/api/projects.py` | `get_connection()` uses the adapter and stops auto-migrating PostgreSQL. |
| `backend/app/forms_store.py` | Constraint-specific errors, position lock through the adapter. |
| `backend/app/form_versions.py` | Version-number lock. Duplicate-publish only for the snapshot conflict. |
| `backend/app/records_store.py` | Sequence lock through `begin_write`. |
| `backend/app/imports_store.py` | Job-row lock instead of a bare immediate transaction. |
| `backend/app/reminders_store.py` | Dialect-specific claim statement. |
| `backend/app/reporting_store.py` | Dialect-specific due-date expression. |
| `backend/app/main.py` | Log the database name only. Fail startup when PostgreSQL migrations are behind. |
| `backend/migrations/postgres/001` through `008` | New SQL. Triggers rewritten in `004`. |
| `backend/tests/test_projects.py`, `test_forms.py`, `test_form_versions.py`, `test_records.py`, `test_followups.py`, `test_imports.py`, `test_reminders.py`, `test_reporting.py` | Keep SQLite coverage. Add adapter seams where they execute SQL scripts directly. |
| `.gitignore` | Ignore `.env` and local `pgpass` files. |
| `.env.example` | Names and placeholders only. |
| `README.md` | Document the migrate command and the two configuration modes. |

Store modules that only need the adapter's connection type, and no SQL change, still need their type hints updated: `followups_store.py` and `api/reminders.py`.

### Stage 3

No additional application file if Stage 2 created the SQL. The stage produces a catalog checklist, kept with the operator notes or added under `docs/architecture/` if the owner wants it versioned.

### Stage 4 and 5

| File | Change |
| --- | --- |
| `backend/app/sqlite_copy.py` or `backend/tools/sqlite_to_postgres.py` | New copy and reconciliation tool. |
| `backend/tests/test_sqlite_copy.py` | Refusal rules and fixture copy into disposable PostgreSQL. |

### Stage 6 and 7

Tests listed in Stage 2 gain PostgreSQL cases. No frontend file is expected. The browser does not choose the database.

### Stage 8

Deployment environment outside the repository, plus a short cutover note if the owner asks for one. No schema change is part of the cutover itself.

## Stop

This document is the Stage 0 through Stage 8 plan. It is not permission to start Stage 1. The next step is the owner's decision checklist.
