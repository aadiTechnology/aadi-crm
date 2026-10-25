# SQLite to PostgreSQL — Stage 1 report

Date: 22 October 2026.

Repository: `C:\Users\lenovo\AadiTech\Product\aadi-crm`.

This stage adds PostgreSQL 17 connection support and an explicit schema command. It does not copy rows, switch the running application to PostgreSQL, or change the Control Plane. Nothing was committed, pushed, merged, tagged, or deployed.

## Result

SQLite remains the database when `CRM_DATABASE_URL` is unset. Setting that variable selects PostgreSQL and fails clearly if the URL is invalid or the connection fails. Migrations for PostgreSQL run only through `python -m app.migrate`.

PostgreSQL 17.4 was available locally. The database named by the existing local `DATABASE_URL` does not exist, and CRM code does not read `DATABASE_URL`. Integration tests ran on a temporary database created for that run and dropped afterward. `python -m app.migrate` was not pointed at any existing database.

The SQLite file is unchanged: 610,304 bytes, SHA-256 `b1f1e61969ca38c212dbcf17513899fd2047995da8e95c9167e013c3cda048d5`.

## Files

Tracked files modified in this stage (10):

| File | Change |
| --- | --- |
| `backend/pyproject.toml` | Add `psycopg[binary]>=3.2,<4`. Python floor stays `>=3.11`. |
| `backend/app/db.py` | Dialect selection, PostgreSQL connection wrapper, locks, and migration runner. |
| `backend/app/main.py` | Startup log uses the database name only. Invalid PostgreSQL configuration fails at startup. |
| `backend/app/api/projects.py` | SQLite requests still migrate. PostgreSQL requests connect and do not migrate. |
| `backend/app/records_store.py` | Record-number allocation takes a PostgreSQL advisory lock. |
| `backend/app/form_versions.py` | Version-number allocation takes an advisory lock. |
| `backend/app/forms_store.py` | New field positions take an advisory lock. |
| `backend/app/imports_store.py` | Import create and commit take advisory locks. |
| `backend/app/reminders_store.py` | PostgreSQL claim uses `FOR UPDATE SKIP LOCKED`. |
| `backend/app/reporting_store.py` | Due-date SQL is chosen for the open connection. |

`backend/app/migrate.py` is untracked, so the tracked modification count is 10. `.gitignore` was already modified before this stage and was not edited again. `.env` and `.pgpass` were already ignored. No tracked secret file was found, and nothing was removed from the index.

New files:

| Path | Purpose |
| --- | --- |
| `backend/app/migrate.py` | Explicit migration command |
| `backend/migrations/postgres/001_projects.sql` through `008_imports.sql` | PostgreSQL schema |
| `backend/tests/test_postgres_support.py` | Configuration tests and optional PostgreSQL tests |
| `.env.example` | Placeholders only. This file already existed untracked and was updated. |
| `docs/architecture/sqlite-to-postgresql-stage1-report.md` | This report |

No ORM and no connection pool were added.

## Configuration and command

The application reads the process environment. It does not load `.env`.

| Variable | Behavior |
| --- | --- |
| `CRM_DATABASE_PATH` | SQLite file. Used only when `CRM_DATABASE_URL` is unset or empty. |
| `CRM_DATABASE_URL` | `postgresql://USER:PASSWORD@HOST:5432/DATABASE`. When set, PostgreSQL is required. |
| `CRM_DATABASE_SSLMODE` | Default `verify-full`. `disable` is accepted only when set explicitly and the host is `localhost`, `127.0.0.1`, or `::1`. |

`DATABASE_URL` is ignored, including a SQLAlchemy `postgresql+psycopg://` URL. A database name containing `aadi_platform` is refused. Connection errors do not include the URL. The startup log prints the SQLite file name or the PostgreSQL database name, not the user, password, or host.

Apply the schema from the `backend` directory:

```text
.venv\Scripts\python.exe -m app.migrate
```

The command exits if `CRM_DATABASE_URL` is unset. It does not open SQLite and does not copy rows. A second run skips scripts already recorded in `crm_schema_migrations`.

Psycopg 3.3.6 is installed in `backend/.venv`, including the Windows CPython 3.14 binary wheel. The declared Python floor is still `>=3.11`. Unrelated dependencies were not upgraded.

## Schema

The eight PostgreSQL scripts follow the SQLite scripts. Primary keys remain text UUIDs. JSON and timestamps remain text. Checks, foreign keys, the partial active-membership index, and the `lower(...)` unique indexes are preserved. `form_definitions.current_published_version_id` is added after `form_versions` exists and stays nullable, so forms can be inserted before their first published version.

Published versions reject update and delete through `crm_form_versions_immutable()`, with the same error text as SQLite: `published form version is immutable`. Inserts are allowed. There is no row-level security. Authorization is unchanged in the application.

Record numbers and form version numbers still use `MAX(...) + 1` inside the write transaction. On PostgreSQL that transaction also takes `pg_advisory_xact_lock` for the project or form. The unique indexes remain the backstop. SQLite still uses `BEGIN IMMEDIATE`. Reminder claim on PostgreSQL locks the selected row with `FOR UPDATE SKIP LOCKED` in the same statement that marks it `processing`. The dashboard date still takes the first 19 characters of the UTC stamp and adds 330 minutes.

The membership backfill from SQLite migration `002` also runs when that PostgreSQL script is first applied. On an empty database it inserts nothing.

## Tests

SQLite regression, with `CRM_DATABASE_URL` and `CRM_TEST_DATABASE_URL` unset:

```text
84 passed, 6 skipped
```

The six skips are the PostgreSQL integration tests in `tests/test_postgres_support.py`. The 84 passing tests include the existing suite and the new configuration tests. One existing Starlette warning about `httpx` was reported. No test opened `backend/data/aadi_crm.sqlite`.

PostgreSQL 17.4 integration, on a temporary database named `aadi_crm_stage1_test`:

```text
19 passed
```

That run covered migration tracking, foreign keys, the partial and expression indexes, form-version immutability, concurrent record numbers, concurrent form-version numbers, a single winner for concurrent reminder claim, and the Kolkata due-date expression. The temporary database was dropped after the run. No existing local database received these migrations.

Passing SQLite tests do not by themselves prove the PostgreSQL path. The 19 passing tests above are the PostgreSQL result.

## Unresolved behavior

- Reordering or removing form fields still computes positions from `MAX(position)` without an advisory lock. The unique `(form_id, position)` index rejects a collision. Adding a field does take the lock.
- PostgreSQL startup checks the URL and SSL mode but does not open a connection. A refused connection surfaces on the first request that needs the database, and that request does not fall back to SQLite.
- Local PostgreSQL without TLS cannot use the default `verify-full` mode. Loopback development must set `CRM_DATABASE_SSLMODE=disable` explicitly.
- The configured database name `aadi_crm` is not created yet, so the migration command has not been run for ongoing development use.
- Data copy, cutover, and SQLite retirement are not part of this stage.

## Next step

Create a dedicated non-production CRM database, export `CRM_DATABASE_URL` for that database only, and set `CRM_DATABASE_SSLMODE=disable` if the server is loopback and has no TLS. From `backend`, run:

```text
.venv\Scripts\python.exe -m app.migrate
```

Do not point that URL at a Control Plane database. Do not copy SQLite rows until that step is requested separately. Leave `backend/data/aadi_crm.sqlite` in place.
