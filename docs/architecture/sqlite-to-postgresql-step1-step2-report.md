# SQLite to PostgreSQL — Step 1 and Step 2 report

Date: 22 October 2026.

Repository: `C:\Users\lenovo\AadiTech\Product\aadi-crm`.

HEAD at inspection: `4d543de` on `main`, tracking `origin/main`.

This report covers secure configuration and the decision checklist only. It does not include credential values or environment-variable values.

## 1. Summary of changes

Local secret filenames are now ignored, and `.env.example` is a placeholder template. The decision checklist records what the repository can prove and what an owner still has to accept. SQLite remains the active application database. No PostgreSQL connection, schema migration, data copy, cutover, deployment, or commit was performed.

`CRM_DATABASE_URL` and `CRM_DATABASE_SSLMODE` are proposed names. `backend/app/db.py` does not read them.

## 2. Files created or modified

| Path | Action | Tracked before this task |
| --- | --- | --- |
| `.gitignore` | Modified. Existing rules and comments were kept. Secret patterns were appended. | Yes |
| `.env.example` | Created. Placeholders only. | No |
| `docs/architecture/sqlite-to-postgresql-decision-checklist.md` | Updated in place with evidence and status. | No. The whole `docs/` directory was already untracked. |
| `docs/architecture/sqlite-to-postgresql-step1-step2-report.md` | Created. | No |

Not modified: `docs/architecture/sqlite-to-postgresql-assessment.md`, application code, tests, `backend/pyproject.toml`, and the local notes under `docs/sprints/`.

File count for this task: 2 new files, 1 tracked file modified, 1 already-untracked file edited. That is inside the limit of 20 new files and 10 modified files.

## 3. Git status

Initial status, before edits:

```text
## main...origin/main
?? docs/
```

`git status --short` showed only `?? docs/`. There were no staged changes and no modified tracked files. The untracked `docs/` tree already contained the assessment, the unsigned checklist, and the ignored `docs/sprints/` notes. Those are pre-existing user files. This task did not revert them.

Final status after this task:

```text
## main...origin/main
 M .gitignore
?? .env.example
?? docs/
```

`docs/` remains one untracked directory, so Git does not show a separate line for the checklist edit or this report. The only tracked diff is `.gitignore` (21 insertions). `git diff --name-only -- backend frontend README.md` produced no output.

## 4. Secret-file tracking

Commands used filenames and Git metadata. File contents of secret candidates were not read. No secret candidate was present in the work tree outside ignored dependency directories.

| Path or pattern | On disk in the work tree | Git tracking |
| --- | --- | --- |
| `.env` | Not present | Not tracked |
| `.env.example` | Present, placeholders only | Not tracked. Not ignored. `git add -n -- .env.example` would add it. |
| `.pgpass`, `pgpass.conf` | Not present | Not tracked |
| `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.crt` | Not present | Not tracked |
| `id_rsa`, `id_ed25519`, `id_ecdsa` | Not present | Not tracked |
| `*.sqlite` | `backend/data/aadi_crm.sqlite` exists. It was not opened. | Not tracked. Already ignored by `backend/data/` and `*.sqlite`. |

`git ls-files` for those secret names, and a name filter over the full tracked list, returned no matches. `.gitignore` does not stop Git from tracking a file that is already tracked. No tracked sensitive file was found, so nothing was removed from the index and history was not rewritten. Credential rotation is not indicated by a tracked secret file. A secret committed under a name this search did not cover would still need rotation. This search did not find one.

## 5. Verification

| Check | Result |
| --- | --- |
| `git diff --check` | Passed. The only tracked diff is `.gitignore`. |
| `git check-ignore -q -- .env` | Exit 0. Ignored by `.env`. |
| `git check-ignore -q -- .env.local` | Exit 0. Ignored by `.env.*`. |
| `git check-ignore -q -- .env.example` | Exit 1. Not ignored. The deciding pattern is `!.env.example`. |
| `git check-ignore -q -- backend/.env.example` | Exit 1. Not ignored. |
| `git check-ignore -q -- .pgpass` and `pgpass.conf` | Exit 0. Ignored. |
| `git check-ignore -q -- postgresql.key`, `cert.p12`, `id_rsa` | Exit 0. Ignored. |
| `git check-ignore -q -- public-ca.pem` and `public-ca.crt` | Exit 1. Not ignored. Public CA material was left trackable. |
| `.env.example` contents | The URL line is exactly `postgresql://<USER>:<PASSWORD>@<HOST>:5432/<DATABASE>`. `CRM_DATABASE_SSLMODE=verify-full` and `CRM_DATABASE_PATH=backend/data/aadi_crm.sqlite` are present. No other assignment uses a password. |
| Default database | With the database variables removed inside the check process, `database_path()` returned a path whose file name is `aadi_crm.sqlite` and whose parent directory is `data`. `backend/app/db.py` does not contain `CRM_DATABASE_URL`, `psycopg`, or `postgresql`. The shell did not have those three variables set. |
| Targeted tests | `pytest tests/test_projects.py::test_database_path_refuses_the_control_plane_name` and `test_migration_is_repeatable_and_codes_are_unique_per_tenant`: 2 passed. The migration test uses a temporary SQLite file. |
| Application diff | No tracked application file changed. |

Whitespace check on `.env.example` and the checklist found no trailing whitespace and no conflict markers. This report was checked the same way after it was written.

## 6. Decision checklist

Full records are in [sqlite-to-postgresql-decision-checklist.md](sqlite-to-postgresql-decision-checklist.md). Status here matches that file.

| Item | Status | Evidence | Owner follow-up |
| --- | --- | --- | --- |
| 2.1 PostgreSQL version | Proposed — owner confirmation required | No version in `backend/pyproject.toml`, Docker, CI, or application code. Assessment recommends 16 or 17. | CRM product owner and the provisioning owner choose 16 or 17 after checking the host. |
| 2.2 Declared and installed Python | Confirmed | Declared `>=3.11`. Local venv is CPython 3.14.3, `win-amd64`. That install is not a mandate. | Decide whether the declared floor should move above 3.11. The assessment notes `sqlite3.Connection.execute` needs 3.12. |
| 2.2 psycopg 3 adoption | Proposed — owner confirmation required | Not installed. No lock file. PyPI on 22 October 2026: `psycopg` 3.3.6 requires Python `>=3.10`. `psycopg-binary` 3.3.6 publishes `psycopg_binary-3.3.6-cp314-cp314-win_amd64.whl`. The wheel was not imported. | Confirm the pin immediately before any later install. Re-check the wheel. Do not install it under this report. |
| 2.3 Target environment | Proposed — owner confirmation required | Local loopback only. No staging, CI, or production database is named. | Approve a dedicated disposable non-production database. Name who provisions it. |
| 2.4 TLS | Proposed — owner confirmation required | Host, remote-or-local, and CA are unknown. Template shows `verify-full` as a proposed value the application does not read. | Name the host class. Supply and validate the CA before any remote connection. `disable` only for approved loopback. |
| 2.5 Ownership and privileges | Proposed — owner confirmation required | No person is named. `support-ownership.md` also leaves these roles open. | Accept a non-superuser runtime role, separate from DDL before any shared environment. Name secret storage and support. |
| 2.6 Backup and restore | Blocked | Integrity check is not a backup. Sprint 14 notes and this filename search found no backup artifact, no approved retention policy, no restore test, and no RPO or RTO. | Name owners and approve backup, retention, storage, a restore test, RPO, and RTO before any data migration. |
| 2.7 Rollback | Proposed — owner confirmation required | Staged approach is documented. Window, decision-maker, and post-write recovery are not approved. | Name the decision-maker and the recovery rule. This is not a completed control. |
| 2.8 CRM-only boundary | Confirmed | CRM store is separate from the Control Plane in code, README, and the assessment. | Control Plane owner must run a separate assessment before that database changes. Not applicable to this checklist. |
| Ignore rules and template | Confirmed | `.gitignore` and `.env.example` as verified above. | Keep real passwords out of Git. Confirm the real URL shape under 2.3 and 2.4. |
| Stage 0, Stage 1, Stage 8, SQLite retirement | Blocked | Backup is missing and the sign-off block is unsigned. | Do not start those stages from this report. |

Assessment defaults that remain proposed, not signed: text timestamps and JSON, advisory locks, `python -m app.migrate`, SQLite auto-migrate until cutover, SQLite pytest as the fast default, no row-level security, copy-tool refusal rules, stop on unmatched rows, and published-version immutability.

## 7. Unresolved blockers

- No verified SQLite backup or immutable snapshot.
- No documented PostgreSQL backup method, retention policy, or secure storage location.
- No successful restore test.
- No named operational owner.
- No agreed RPO or RTO.
- No signed Stage 1 approval.
- Stage 8 cutover and SQLite retirement are not approved.

## 8. SQLite remains active

`backend/app/db.py` still opens SQLite through `CRM_DATABASE_PATH`, or `backend/data/aadi_crm.sqlite` when that variable is empty. The default-path check and the two targeted tests passed. The application was not switched to PostgreSQL.

## 9. What was not done

No PostgreSQL connection was opened. No database or role was created. No schema was migrated. No data was copied. No cutover, deployment, commit, push, merge, tag, or file deletion was performed. No package was installed or upgraded. The live SQLite file was not opened, copied, or modified. History was not rewritten.

## 10. Recommended next step

Do not connect to PostgreSQL and do not migrate data under this report.

The next step is an owner decision, not an implementation step: accept or replace the proposed items in sections 2.1, 2.3, 2.4, 2.5, and 2.7, and clear the blocked backup prerequisites in section 2.6. After that approval, the first implementation stage is a verified restorable copy of the source SQLite database, with the live file left unchanged. That stage needs a separate instruction.
