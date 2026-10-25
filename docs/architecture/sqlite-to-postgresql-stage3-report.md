# SQLite to PostgreSQL — Stage 3 report

Date: 25 October 2026.

Repository: `C:\Users\lenovo\AadiTech\Product\aadi-crm`.

This stage makes the existing PostgreSQL 17.4 database `aadi_crm` selectable for local CRM development. It did not copy SQLite rows, rerun schema migrations, delete fixture rows, or open a Control Plane database. Nothing was committed, pushed, or deployed.

## Configuration

The application still reads process environment variables only. It does not load `.env`. When `CRM_DATABASE_URL` is unset, the database remains SQLite at `backend/data/aadi_crm.sqlite`. That fallback was not changed.

Local settings were added to gitignored `backend/.env`:

| Name | Value recorded here |
| --- | --- |
| `CRM_DATABASE_URL` | Present. Scheme `postgresql`, database `aadi_crm`, loopback host, port 5433. The user, password, and full URL are not recorded. |
| `CRM_DATABASE_SSLMODE` | `disable`, because this server is loopback-only and `SHOW ssl` is `off`. |

`DATABASE_URL` was already in that file and was left in place. CRM does not read it. `.env.example`, production configuration, and the Control Plane repository were not changed.

A process with those two variables exported selected PostgreSQL, logged `startup database_name=aadi_crm`, and `SELECT current_database()` returned `aadi_crm`. An explicit URL to a closed port failed with `SQLite was not used` and did not create a SQLite file. The same password was absent from the error text. A process with `CRM_DATABASE_URL` removed resolved to SQLite and the label `aadi_crm.sqlite` without opening the file.

`crm_schema_migrations` already contained all eight scripts, so `python -m app.migrate` was not run. The integration fixture calls the same migration function and found the schema current: the migration table stayed at 8 rows.

## Tests

PostgreSQL, against `aadi_crm`, with `CRM_TEST_DATABASE_URL` set and `CRM_DATABASE_URL` unset in the parent process:

```text
19 passed in 11.86s
```

`current_database()` was `aadi_crm` before and after that run. The 19 tests cover configuration, rejection of a non-PostgreSQL URL, no SQLite fallback when the connection fails, refusal of an `aadi_platform` database name, no migration on an API connection, schema and triggers, published-version immutability, concurrent record numbers, concurrent form-version numbers, a single reminder claim winner, and the Asia/Kolkata due date.

SQLite regression, with `CRM_DATABASE_URL` and `CRM_TEST_DATABASE_URL` unset:

```text
84 passed, 6 skipped, 1 warning in 31.10s
```

The six skips are the live PostgreSQL tests. The warning is the existing Starlette notice that `httpx` with `starlette.testclient` is deprecated. This suite uses temporary SQLite files. It was not pointed at `aadi_crm`, because `get_connection()` would follow `CRM_DATABASE_URL` and write those tests into the shared fixture database.

Read-only store calls on the existing `tenant-postgres` fixtures, followed by one insert that was rolled back:

| Check | Result |
| --- | --- |
| Database | `aadi_crm` |
| Projects listed for the fixture tenant | 8 |
| Projects listed for another tenant | 0 |
| Forms listed | 8 |
| Field positions strictly increasing within each form | Yes |
| Records listed | 6 |
| Record search by a stored public number | 4 hits |
| Dashboard KPI calls | 8, timezone `Asia/Kolkata` |
| Rolled-back insert left `projects` unchanged | Yes, 8 rows |

## Rows

The PostgreSQL tests commit new fixture rows. They do not delete or truncate existing rows, and they were not copied from SQLite. Counts before this stage's test run were the Stage 2 fixtures. Counts after it:

| Table | Before | After |
| --- | ---: | ---: |
| crm_schema_migrations | 8 | 8 |
| projects | 4 | 8 |
| project_memberships | 4 | 8 |
| form_definitions | 4 | 8 |
| form_fields | 3 | 6 |
| form_versions | 5 | 10 |
| records | 3 | 6 |
| record_values | 3 | 6 |
| follow_ups | 1 | 2 |
| record_activities | 1 | 2 |
| reminder_deliveries | 4 | 8 |
| import_jobs | 0 | 0 |
| import_rows | 0 | 0 |

Reminder states moved from `processing=1, sent=3` to `processing=2, sent=6`. There were no pending rows for the test to rewrite. No fixture row was deleted.

## Local development

Start the API on PostgreSQL from `backend`. This reads the two CRM names from gitignored `.env` and does not print them:

```text
Get-Content .env | ForEach-Object {
  if ($_ -match '^(CRM_DATABASE_URL|CRM_DATABASE_SSLMODE)=(.*)$') {
    Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
  }
}
.venv\Scripts\uvicorn app.main:app --host localhost --port 8001
```

The startup log should show `database_name=aadi_crm`. Unset `CRM_DATABASE_URL` before starting the process to use SQLite. Editing `.env` does not change a process that is already running.

Frontend, from `frontend`:

```text
npm install
npm run dev
```

PostgreSQL integration tests, from `backend`. Leave `CRM_DATABASE_URL` unset:

```text
Get-Content .env | ForEach-Object {
  if ($_ -match '^CRM_DATABASE_URL=(.*)$') {
    Set-Item -Path env:CRM_TEST_DATABASE_URL -Value $Matches[1]
  }
  if ($_ -match '^CRM_DATABASE_SSLMODE=(.*)$') {
    Set-Item -Path env:CRM_TEST_DATABASE_SSLMODE -Value $Matches[1]
  }
}
Remove-Item Env:CRM_DATABASE_URL -ErrorAction SilentlyContinue
.venv\Scripts\python.exe -m pytest tests/test_postgres_support.py
```

SQLite regression, from `backend`, with both URL variables unset:

```text
.venv\Scripts\python.exe -m pytest
```

PostgreSQL migrations, only when `crm_schema_migrations` is behind the scripts. Export the same two variables first, then from `backend`:

```text
.venv\Scripts\python.exe -m app.migrate
```

That command was not needed in this stage.

## Workflow coverage

Exercised on PostgreSQL `aadi_crm`:

- Process startup and a live connection to `aadi_crm`.
- Invalid PostgreSQL configuration fails without using SQLite.
- Unset `CRM_DATABASE_URL` still selects SQLite.
- Published form versions reject update and delete.
- Record numbers and form version numbers stay unique under concurrent inserts.
- One concurrent reminder claim wins.
- Due dates use the fixed 330-minute Asia/Kolkata offset.
- Listing projects, forms, and records; searching records; field order; dashboard KPI SQL; a rolled-back insert.

Still required before treating the HTTP product as proven on PostgreSQL:

- Signed-in browser session. The CRM page needs the Control Plane on port 8000 and a Control Plane process whose CORS allowlist includes `http://localhost:5174`. That repository was not modified.
- Project and membership HTTP authorization, form field reorder and removal, record update and archive, reminder retry and delivery idempotency, import preview and commit, and CSV or XLSX export. Those tests passed on temporary SQLite files. They were not run against `aadi_crm`.
- Reorder and removal of form fields still have no PostgreSQL advisory lock. The unique position index remains the backstop.

## Readiness

The CRM API is ready for PostgreSQL-based local development when the process environment contains `CRM_DATABASE_URL` for `aadi_crm` and `CRM_DATABASE_SSLMODE=disable`. The startup log and `current_database()` both identified that database. SQLite remains the database when the URL is unset, and the existing regression suite passed in that mode.

`disable` belongs only on this loopback server. A remote server still requires `verify-full`.

## Unchanged

- SQLite file `backend/data/aadi_crm.sqlite`: 610,304 bytes, SHA-256 `b1f1e61969ca38c212dbcf17513899fd2047995da8e95c9167e013c3cda048d5`, before and after this stage.
- No SQLite rows were copied.
- No Control Plane database was accessed. The only connected database reported by `current_database()` was `aadi_crm`.
- Application selection code was not changed. No new configuration loader was added.
- The Stage 2 report was left untracked and unmodified.
