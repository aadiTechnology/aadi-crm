# SQLite to PostgreSQL — owner decision checklist

Assessment: [sqlite-to-postgresql-assessment.md](sqlite-to-postgresql-assessment.md).

Scope: this checklist covers the CRM repository only. It does not authorize a database connection, schema change, data copy, cutover, or any change to the MultiTenant Control Plane.

Status values:

| Status | Meaning |
| --- | --- |
| Confirmed | Established by repository evidence or by a preparation step completed in this repository. |
| Proposed — owner confirmation required | A recommendation exists. No owner has accepted it. |
| Blocked | A prerequisite or approval is missing. Do not proceed. |
| Not applicable | The item is outside this checklist's authority. |

No person is named below. A role is the party who must confirm the item. No role has accepted ownership in this repository.

The active application database remains SQLite through `backend/app/db.py`. `CRM_DATABASE_URL` and `CRM_DATABASE_SSLMODE` are proposed names. The application does not read them.

## 2.1 PostgreSQL version

| Field | Record |
| --- | --- |
| Status | Proposed — owner confirmation required |
| Evidence | `backend/pyproject.toml` declares Python, FastAPI, Uvicorn, HTTPX, tzdata, and pytest. It does not mention PostgreSQL. There is no Dockerfile, Compose file, CI workflow, or lock file that pins a server version. Application code imports `sqlite3` only. The assessment, section 5 and section 10.3, states that nothing in the repository chooses a PostgreSQL version and recommends 16 or 17. |
| Decision | Recommend PostgreSQL 16 or 17 for the first non-production database, subject to hosting support and a later compatibility check. Do not treat either version as selected. |
| Owner | CRM product owner, with the person who will provision the database. |
| Prerequisite or risk | Choosing a version the host cannot run, or assuming a managed major version that was never agreed. Re-check the chosen major version before any install. |

## 2.2 Python runtime and driver compatibility

### Declared and installed runtimes

| Field | Record |
| --- | --- |
| Status | Confirmed |
| Evidence | Declared: `requires-python = ">=3.11"` in `backend/pyproject.toml`. Installed in `backend/.venv` at this inspection: CPython 3.14.3, platform tag `win-amd64`, bundled SQLite 3.50.4. `docs/sprints/crm-s14/deployment-readiness.md` records the same declared floor and the same local interpreter on 21 October 2026. No `.python-version`, runtime file, CI workflow, or Python lock file pins an exact interpreter. The installed version is a local observation, not a project mandate. |
| Decision | Keep the declared floor at `>=3.11` until an owner decides otherwise. Do not treat 3.14.3 as the required runtime. |
| Owner | CRM product owner, if the declared floor should change. |
| Prerequisite or risk | The assessment, section 1.1, records that store code calls `sqlite3.Connection.execute`, which Python has provided since 3.12, while packaging still allows 3.11. That gap predates this checklist. It is not a reason to install a PostgreSQL driver now. |

### psycopg 3

| Field | Record |
| --- | --- |
| Status | Proposed — owner confirmation required |
| Evidence | Local: `psycopg` does not import in `backend/.venv`. `backend/pyproject.toml` does not depend on it. There is no Python lock file. Public PyPI metadata read on 22 October 2026, without installing anything: `psycopg` 3.3.6 requires Python `>=3.10` and publishes `psycopg-3.3.6-py3-none-any.whl`. `psycopg-binary` 3.3.6 requires Python `>=3.10` and publishes `psycopg_binary-3.3.6-cp314-cp314-win_amd64.whl`, which matches this venv's platform tag. The assessment, section 3.1, recommends `psycopg[binary]` and says to confirm a Python 3.14 wheel before locking the dependency. This checklist did not import the wheel. |
| Decision | A published Windows wheel for CPython 3.14 exists for psycopg-binary 3.3.6. Adopting and pinning that driver is not approved. Re-read the wheel metadata immediately before any future install. If that wheel is gone, stop and choose a Python version the available wheel supports. Do not switch the API to async for this migration. |
| Owner | CRM product owner. |
| Prerequisite or risk | Metadata can change. An import was not tested. The pure-Python `psycopg` wheel still needs libpq or the binary extra. Installing the driver is a later stage. |

## 2.3 Target environment

| Field | Record |
| --- | --- |
| Status | Proposed — owner confirmation required |
| Evidence | README local run is a loopback CRM API on port 8001 and a loopback Control Plane on port 8000. No CI service, staging host, production host, or database name is configured. `docs/sprints/crm-s14/deployment-readiness.md` (local, ignored by `docs/sprints/`) records the same local ports and states that nothing was deployed. The assessment, section 5, says the first implementation target is one new non-production CRM database and that this work must not point at production. No database was created by the assessment or by this checklist. |
| Decision | Use a dedicated disposable non-production database for the first PostgreSQL test. Prefer the local developer environment until an owner names another environment. It must not be the Control Plane database and must not be a production database. |
| Owner | CRM product owner approves the environment. The provisioning owner creates it and controls access. Neither role has been accepted. |
| Prerequisite or risk | Provisioning is not part of this checklist. A shared or production target would make later experiments unsafe. |

## 2.4 TLS

| Field | Record |
| --- | --- |
| Status | Proposed — owner confirmation required |
| Evidence | No PostgreSQL host is configured, so it is not known whether the first server will be local or remote, whether that host requires TLS, or which CA would validate it. `backend/app/db.py` has no `sslmode` setting. `.env.example` shows `CRM_DATABASE_SSLMODE=verify-full` as a proposed placeholder. The application does not read it. The assessment, section 5, says `disable` only for loopback and `verify-full` for any other host. |
| Decision | Pending until the host class is named. Recommend `verify-full` for remote PostgreSQL when the server certificate and hostname can be validated. The trusted CA must be supplied by the provisioning owner and checked before use. `disable` is acceptable only for explicitly approved loopback-only development. Do not disable TLS for remote PostgreSQL. Do not weaken certificate checks to force a connection. |
| Owner | CRM product owner for the host class. Provisioning owner for the certificate and CA. |
| Prerequisite or risk | `verify-full` fails closed until the CA and hostname are right. That is the intended outcome. A remote server with `disable`, or with certificate verification turned off, is not an acceptable fallback. |

## 2.5 Database ownership and privileges

| Field | Record |
| --- | --- |
| Status | Proposed — owner confirmation required |
| Evidence | The repository separates CRM rows from Control Plane data: `backend/app/db.py` refuses a path containing `aadi_platform`, and `backend/app/platform_client.py` calls the Control Plane over HTTP. README states that authentication, tenant membership, and subscriptions stay in the Control Plane. No PostgreSQL role, database owner, secret store, or on-call owner is named. `docs/sprints/crm-s14/support-ownership.md` (local, ignored by `docs/sprints/`) leaves database, backup, restore, deployment, and support owners as "Owner decision required" and does not name a person. The assessment, section 5, recommends a dedicated CRM database, a non-superuser role, and splitting migration DDL from runtime DML before any shared environment. |
| Decision | Recommend the separation in the table below. No assignment has been accepted. |
| Owner | CRM product owner accepts the role split. Provisioning owner creates the roles. Operations owner accepts support. |
| Prerequisite or risk | Using a superuser for the application, or reusing Control Plane credentials, would break the least-privilege recommendation and the repository boundary. |

| Responsibility | Recommendation |
| --- | --- |
| PostgreSQL instance or service | Provisioning owner. Not the CRM application role. |
| CRM database and schema | A database dedicated to CRM. Not the Control Plane database. Schema `public` in that database is enough for the first test, per the assessment. |
| Application runtime credentials | A role that is not a superuser and does not have `CREATEDB`, `CREATEROLE`, or `BYPASSRLS`. Runtime privileges are `CONNECT` plus DML on CRM tables. |
| Migration and DDL credentials | A separate role where feasible. The assessment allows one role for the first local disposable database and recommends the split before a shared environment. |
| Secret storage and access | Process environment or a local gitignored `pgpass` file. Not Git, logs, or a real password inside `CRM_DATABASE_URL`. |
| Operational support | An operations owner named before any shared environment or backup retention rule. |

## 2.6 Backup and restore prerequisites

| Field | Record |
| --- | --- |
| Status | Blocked |
| Evidence | The assessment, section 1.10 and section 6, records a read-only SQLite integrity check and states that the check is not a backup and not a frozen baseline. No restorable copy was made. Local notes ignored by `docs/sprints/` reach the same conclusion: `docs/sprints/crm-s14/backup-restore.md` and `backup-restore-ownership.md` (21 October 2026) record no backup artifact, no backup job, and no restore test. `release-readiness-checklist.md` marks backup owner, schedule, RPO, and RTO as not approved. A PRD sentence about daily backups and 30-day retention is quoted there as text that has not been confirmed for this environment. The PRD file itself was not found in this repository. This preparation did not open the SQLite file and did not create or delete a backup. A filename search found `backend/data/aadi_crm.sqlite` and those notes, not a dump or snapshot database. `PRAGMA integrity_check` does not prove a file can be restored. |
| Decision | Do not migrate data until every prerequisite below is done and an owner has accepted it. |
| Owner | Operations owner for backup, retention, restore test, RPO, and RTO. CRM product owner approves starting that work. |
| Prerequisite or risk | There is no backup artifact and no approved restore process. Data migration stays blocked. An integrity check must not be described as a backup. |

Required before any data migration:

- A verified backup or immutable snapshot of the source SQLite database.
- A documented backup method for the target PostgreSQL database.
- An approved retention and secure storage policy.
- A successful restore test to a disposable target.
- Named operational owner(s).
- Agreed recovery point objective (RPO) and recovery time objective (RTO).

The assessment's SQLite procedure, which has not been executed, is: stop writers or use the SQLite online backup API / `VACUUM INTO`, store the copy outside the repository, check integrity and counts on the copy, and prove the copy opens. A PostgreSQL `pg_dump` after cutover does not replace the SQLite snapshot taken before the copy. The Control Plane database is out of scope.

## 2.7 Rollback approach

| Field | Record |
| --- | --- |
| Status | Proposed — owner confirmation required |
| Evidence | The assessment, section 10.2, describes cutover and rollback. No maintenance window, rollback owner, or observation window is recorded. This checklist does not perform cutover. Current code writes only to the SQLite path from `database_path()`. |
| Decision | Use the staged approach below. Unresolved names, windows, and loss decisions stay owner decisions. They are not completed controls. |
| Owner | CRM product owner names the decision-maker and approves the window. Operations owner accepts the recovery procedure. |
| Prerequisite or risk | Section 2.6 is blocked, so there is no snapshot to roll back to. Treating this section as an approved runbook would overstate the control. |

- Before cutover: SQLite remains authoritative. Aborting preparation requires no database rollback.
- During future migration testing: use an isolated PostgreSQL target and leave the SQLite source unchanged.
- Before cutover: validate row counts, primary-key sets, foreign keys, checksums, and application behavior. Any unexplained difference stops the cutover.
- At cutover: require a controlled maintenance window, a verified final SQLite snapshot, an approved switch procedure, and a named decision-maker. Those are not yet approved.
- After PostgreSQL accepts writes: switching back to an older SQLite snapshot is not safe, because newer writes would be lost. Require a documented write freeze, a reverse-sync or reconciliation plan, or an explicit recovery decision before any rollback. The copy tool must not be pointed back at SQLite to synchronize the two databases.
- This task does not perform cutover.

Still unresolved: the maintenance window, the named decision-maker, the observation window, RPO, RTO, and whether a post-cutover rollback accepts lost PostgreSQL writes or replays them by primary key.

## 2.8 Cross-project dependency

| Field | Record |
| --- | --- |
| Status | Confirmed |
| Evidence | This file is in the CRM repository. `backend/app/db.py` documents that the CRM store is not the Control Plane database and refuses a path containing `aadi_platform`. `backend/app/platform_client.py` uses HTTPX and does not open that database. README keeps authentication, tenant membership, product registration, subscriptions, and entitlement evaluation in the Control Plane. The assessment states the same boundary. |
| Decision | This checklist covers the CRM repository only. The MultiTenant Control Plane is a separate dependent project. It needs its own assessment, decision checklist, test plan, and migration approval before its database changes. Do not assume both projects share a database, schema, credentials, or migration sequence. The CRM migration must preserve existing authentication, tenant isolation, authorization, and platform API contracts. |
| Owner | CRM product owner for the CRM sequence. Control Plane owner for any Control Plane database work. |
| Prerequisite or risk | Changing shared platform contracts, or migrating the Control Plane as a side effect of the CRM work, is outside this repository. Control Plane execution is not applicable to this checklist. |

Control Plane migration status on this checklist: Not applicable.

## Preparation completed with this checklist

| Item | Status | Evidence | Decision | Owner | Prerequisite or risk |
| --- | --- | --- | --- | --- | --- |
| Ignore `.env` and local `pgpass` files before a password exists | Confirmed | `.gitignore` ignores `.env`, `.env.*`, `.pgpass`, and `pgpass.conf`, and keeps `.env.example` trackable. `git ls-files` did not list those secret names. | Local secret filenames are ignored when untracked. Ignore rules do not untrack a file Git already tracks. None of these names were tracked. | No further owner action for the ignore rule. Credential rotation is not indicated by a tracked secret file. | A secret committed under a different name would still need rotation. This search did not find one. |
| Placeholder environment template | Confirmed | `.env.example` contains placeholders only. `CRM_DATABASE_URL` and `CRM_DATABASE_SSLMODE` are labeled as proposed. | The template does not switch the application off SQLite. | CRM product owner still confirms the real URL shape and TLS mode under sections 2.3 and 2.4. | A real password must not be copied into the template or into Git. |

## Assessment defaults still awaiting an owner

These recommendations come from the assessment, sections 5, 7, and 10.3. None are implemented here. None are signed.

| Item | Status | Evidence | Decision | Owner | Prerequisite or risk |
| --- | --- | --- | --- | --- | --- |
| Timestamps and JSON stay text | Proposed — owner confirmation required | Assessment sections 3 and 10.3. Columns are text in the SQLite migrations. | Copy exact text. `timestamptz` and `jsonb` are a later project. | CRM product owner | Reformatting would change snapshots, queues, and reminder keys. |
| Record and form version numbers use a transaction advisory lock | Proposed — owner confirmation required | Assessment sections 3 and 10.3. SQLite uses `BEGIN IMMEDIATE` and `MAX(...) + 1`. | Advisory lock plus the existing unique indexes. No new counter table. | CRM product owner | A plain `BEGIN` can duplicate numbers. |
| PostgreSQL schema updates run through `python -m app.migrate` | Proposed — owner confirmation required | `backend/app/migrate.py` does not exist. Requests call `apply_migrations()` in `backend/app/db.py`. | Ordinary API requests do not migrate PostgreSQL. SQLite auto-migrate stays until cutover. | CRM product owner | Per-request DDL on PostgreSQL races if two processes start together. |
| Existing SQLite pytest suite stays the fast default | Proposed — owner confirmation required | Tests live in `backend/tests/` and use temporary SQLite files. No test uses PostgreSQL. | Add a disposable PostgreSQL suite, selected only by a test URL, before cutover. | CRM product owner | A suite that opens the developer SQLite file can change local data. |
| Tenant isolation stays in application queries | Proposed — owner confirmation required | Project and tenant checks are in Python. The assessment, section 10.1, does not recommend row-level security for the first migration. | Do not add row-level security in this migration. | CRM product owner | A mistaken policy would change authorization the tests already cover. |
| Copy tool writes only to the named disposable database | Proposed — owner confirmation required | The copy tool does not exist. Assessment section 4.4. | The tool must not update or delete SQLite rows. | CRM product owner | A tool pointed at the wrong database, or at SQLite, can destroy the source. |
| Unmatched rows, `lower()` disagreements, and dangling `import_rows.record_id` stop for review | Proposed — owner confirmation required | Assessment sections 4.3 and 10.1. | Do not discard or rewrite those rows. | CRM product owner | Silent repair would hide data loss. |
| Published form versions stay immutable and triggers stay enabled | Proposed — owner confirmation required | `004_form_versions.sql` and `backend/app/form_versions.py`. | Load with triggers enabled. Do not update a published row. | CRM product owner | Disabling triggers would allow published snapshots to change. |

## Stage gates

| Gate | Status | Evidence | Decision | Owner | Prerequisite or risk |
| --- | --- | --- | --- | --- | --- |
| Stage 0 baseline and restorable copy | Blocked | Assessment section 7. Section 2.6 of this checklist. | May record a baseline and take a restorable copy only after an owner approves the procedure. Must not change the live file. Not started. | CRM product owner and operations owner | No backup exists. |
| Stage 1 create the non-production database and role | Blocked | Sections 2.1, 2.3, 2.4, 2.5, and the unsigned sign-off below. | May create only the named non-production database and role. May not change application code. Not started. | CRM product owner | Version, host, TLS, and role split are unconfirmed. |
| Stage 2 application dialect work | Blocked | Assessment section 7. Stage 1 has not been approved. | SQLite tests must pass before later PostgreSQL work. Not started. | CRM product owner | Starting here would change the database layer without the Stage 1 decisions. |
| Stage 5 dry run | Blocked | Depends on Stages 0 through 4, which have not run. | A clean reconciliation report is required before the API is pointed at PostgreSQL. | CRM product owner | An unexplained difference blocks cutover. |
| Stage 8 cutover | Blocked | Assessment section 7 and section 10.2. | Not approved by this checklist. Approve it separately after Stage 7. | Named cutover decision-maker, not yet assigned | Cutover is irreversible once PostgreSQL accepts writes, unless a separate recovery decision exists. |
| SQLite retirement | Blocked | Assessment section 10.2. | Not approved. The original file stays until a later decision. | CRM product owner | Deleting the file in the cutover window removes the rollback source. |

## Cutover conditions to accept later

These are not accepted now.

| Condition | Status | Owner |
| --- | --- | --- |
| One maintenance window with CRM writes stopped | Proposed — owner confirmation required | CRM product owner |
| One final verified SQLite snapshot, kept as the rollback database | Blocked until section 2.6 is satisfied | Operations owner |
| One writable database after the switch | Proposed — owner confirmation required | CRM product owner |
| Named rollback owner | Proposed — owner confirmation required | CRM product owner |
| Rollback procedure for the window before PostgreSQL accepts writes | Proposed — owner confirmation required | Operations owner |
| Explicit recovery decision after PostgreSQL accepts writes | Proposed — owner confirmation required | Named rollback owner |
| Observation window | Proposed — owner confirmation required | CRM product owner |

## Sign-off

Stage 1 is not approved. Stages 2 through 8 remain stopped. The signature lines are empty on purpose.

- [ ] I have read the assessment.
- [ ] The proposed defaults I did not change are accepted.
- [ ] Stage 1 may start.

Name: ________

Role: ________

Date: ________
