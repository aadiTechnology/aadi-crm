# CRM-S2 implementation report

Date: 19 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change.

## Scope kept and scope not taken

The task asked for a minimal tenant-scoped project: id, tenant id, code, name, description, status (`active` or `archived`), timestamps, and creator identity. List, create, detail, edit of name and description, search, status filter, archive without deleting the row, required-field validation, and duplicate codes rejected inside one tenant.

The sprint plan's CRM-S2-01 also names reactivate, business type, time zone, and, if they fit, logo and start date. CRM-S2-02 is clone and is Should. Those were not built. An archived project cannot yet reject new records, because records are a later sprint. There is no project membership, project role, form, follow-up, dashboard, or import/export.

The PRD v1.0 file named in the decision log (`Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`, 09 October 2026) is not in this repository. The sprint plan and decision log were the documents used. The v1.1 audit's project field list is wider than this task, and that wider list was not implemented.

## Persistence

The CRM repository had no database and no migration framework. CRM projects are stored in a CRM-owned SQLite file, `backend/data/aadi_crm.sqlite`. `CRM_DATABASE_PATH` overrides that path. A path whose name contains `aadi_platform` is refused. The file is gitignored. It is not the Control Plane database `aadi_platform`.

Migration `backend/migrations/001_projects.sql` creates `projects` and two indexes. It does not drop a table or delete rows. `crm_schema_migrations` records the applied script. The script was applied twice to a disposable file, which was then deleted. The same script was then applied to the development file. The development file has tables `crm_schema_migrations` and `projects`, version `001_projects.sql`, unique index `uq_projects_tenant_lower_code`, and index `ix_projects_tenant_status`.

After the recording, that file holds three rows for tenant `e02812a0-8717-4f5f-be19-57f263daef52`:

| Code | Name | Status |
|---|---|---|
| S2-DEMO | Harbor gate | archived |
| S2-LIVE | Live gate | archived |
| S2-REC | Recording gate | active |

S2-REC and S2-DEMO were written while the capture was being prepared. S2-LIVE is the project in the recording. There is no delete route. `DELETE` on a project returns 405, and the row remains.

## Authorization

Every project route forwards the caller cookie to the Control Plane. The path tenant id is only a selector.

1. `GET /api/v1/tenants/{tenant_id}/products/crm/access` must return that same tenant id and `available: true`. A membership or product-access failure stays 401 or 404. Unavailable CRM stays 403. A tenant id in a query string or body does not select a different tenant. A body `tenant_id` is rejected as an unknown field.
2. Product access is not enough. `GET /api/v1/tenants/{tenant_id}/permissions` must allow project administration.
3. Every read and write includes `tenant_id` from that authorized path. A project id from another tenant returns 404 and does not include the other tenant's name or the project name.
4. Create also calls `GET /api/v1/auth/me` and stores that identity id as `created_by`.
5. Writes require the `aadi_csrf` cookie and a matching `X-CSRF-Token` header. A missing or different token is 401 and does not call the Control Plane. The CRM process does not hold the Control Plane auth secret, so it does not recompute the platform CSRF hash. The session is still checked by the Control Plane calls above.

The sprint plan names `crm.project_management.manage`. The current CRM registration declares only `crm.lead_management.read`, so the project key cannot be granted without a Control Plane registration change. This sprint does not change the Control Plane. Callers who hold `crm.project_management.manage` are allowed. Callers who hold the registered key `crm.lead_management.read` are also allowed. Callers with only platform keys such as `users.read` or `roles.manage` are denied. Product access alone is denied.

That is a real privilege gap: a lead reader can manage every project in the tenant. Project membership is not in this sprint, so there is no per-project denial inside the tenant. When the Control Plane registration includes `crm.project_management.manage` and lead read should stop opening projects, the fallback in `project_management_allowed` has to be removed.

The recording identity has only `crm.lead_management.read`, and CRM product access for the organization is `available: true`. That is why Projects is shown and the create call succeeds.

## API

| Method | Path | Success |
|---|---|---|
| `GET` | `/api/v1/tenants/{tenant_id}/projects` | `200` `{ "items": [...] }`. `q` searches code, name, and description. `status` is `active`, `archived`, or omitted. |
| `POST` | `/api/v1/tenants/{tenant_id}/projects` | `201`. Body `code`, `name`, and optional `description`. Status starts `active`. |
| `GET` | `/api/v1/tenants/{tenant_id}/projects/{project_id}` | `200` |
| `PATCH` | `/api/v1/tenants/{tenant_id}/projects/{project_id}` | `200`. Name and description only. |
| `POST` | `/api/v1/tenants/{tenant_id}/projects/{project_id}/archive` | `200`. Sets `archived`. A second archive returns the same row. |

Duplicate codes in one tenant compare case-insensitively and return 409. The leads route is unchanged and still returns `{ "module": "leads", "items": [] }` when the caller may open leads.

## Tests actually run

Backend, 19 October 2026, from `backend` with the project virtualenv:

`python -m pytest -q` → **17 passed**, 1 warning. The warning is Starlette's deprecation notice that `httpx` with `starlette.testclient` should move to `httpx2`. It is not an assertion failure.

Those 17 tests are the existing shell isolation tests plus the new project tests: migration and unique code, refusal of an `aadi_platform` path, permission policy, CSRF and unknown fields, create/list/edit/archive/search, duplicate code, cross-tenant read and mutation, authentication and unavailable product access, the unchanged leads stub, and validation.

Frontend, the same day, from `frontend`:

`npm test` → **17 passed** (10 existing shell tests and 7 project tests). The project tests cover loading, empty list, client validation, create/edit/search/archive, a duplicate-code error, a list error that does not render a payload, a hidden Projects link for platform-only keys, and opening Projects with `crm.lead_management.read`.

Backend project tests use an in-process platform double and a temporary SQLite file. They do not call the Control Plane. The browser recording does. It uses the running Control Plane and the running CRM API, not the test double.

## Recording

`docs/sprints/crm-s2/recording.webm` (31.84 seconds, 1280×720). Narration: `docs/sprints/crm-s2/explanation-script.md`.

## Changed files

Modified for this sprint:

- `.gitignore`
- `README.md`
- `backend/app/main.py`
- `backend/app/platform_client.py`
- `frontend/src/main.tsx`
- `frontend/src/features/shell/CrmShellPage.tsx`
- `frontend/src/services/platform.ts`
- `frontend/src/styles.css`

New:

- `backend/app/db.py`
- `backend/app/api/projects.py`
- `backend/migrations/001_projects.sql`
- `backend/tests/test_projects.py`
- `frontend/src/features/projects/ProjectsPanel.tsx`
- `frontend/tests/projects.test.tsx`
- `docs/sprints/crm-s2/recording.webm`
- `docs/sprints/crm-s2/explanation-script.md`
- `docs/sprints/crm-s2/implementation-report.md`

`docs/sprints/crm-s1/` was already modified in the working tree before this sprint and was not edited here.

## Unresolved

- `crm.project_management.manage` is not on the current CRM registration. Lead read is the temporary grant for project administration.
- Reactivate, business type, time zone, logo, start date, and clone are not in this implementation.
- Archive does not yet block future records, because records are not implemented.
- The CRM store is SQLite, not a separate Postgres database.
