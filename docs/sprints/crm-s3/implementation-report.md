# CRM-S3 implementation report

Date: 19 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change.

This is the membership sprint. Evidence is stored under `crm-s3` because the completed project-management work already uses `docs/sprints/crm-s2/`. Those files were not overwritten. Closure of that earlier deliverable is `docs/sprints/crm-s2/closure.md`.

## Authorization decision

`crm.project_management.manage` is still not registered in the Control Plane. It was not created from this repository.

The previous rule treated `crm.lead_management.read` as permission to manage every project in the tenant. That rule is no longer the project authorization model.

- Opening the project module, and creating a project, still requires CRM product access plus `crm.lead_management.read` or `crm.project_management.manage`. Product access alone is denied. Platform keys such as `users.read` are denied.
- `crm.lead_management.read` does not administer projects the caller is not a member of.
- `crm.project_management.manage`, if a later Control Plane registration grants it, is the only tenant-wide project administration key. No current CRM sign-in has it.
- The creator of a project becomes its project manager. Existing project rows were given that membership once, when migration `002_project_memberships.sql` was applied. A later removal is not restored on the next process start.
- Adding a member calls the existing Control Plane directory `GET /api/v1/tenants/{tenant_id}/users/{user_id}`. Listing eligible users calls `GET /api/v1/tenants/{tenant_id}/users`. Both require `users.read`. A 403 fails closed and does not write a membership. CRM does not attach identities or change tenant membership.

The live test identity `playwright-recording@example.com` has only `crm.lead_management.read`. The live tenant administrator `playwright-member@example.com` has `users.read` and does not have a CRM permission. No current sign-in can both pass the CRM project check and read the organization directory. That is a Control Plane grant gap, not a second authorization system in CRM.

## Roles

Stored roles are `project_manager` and `project_member`. Scope is stored with the role: `project` for a manager and `assigned` for a member. There is no role builder.

| Action | Project manager | Project member | No active membership | `crm.project_management.manage` |
|---|---|---|---|---|
| View project | Yes | Yes | No, hidden as 404 | Yes |
| List members | Yes | Yes | No | Yes |
| Add member | Yes | No | No | Yes |
| Remove member | Yes | No | No | Yes |
| Change role | Yes | No | No | Yes |
| Update or archive project | Yes | No | No | Yes |
| Future record access | All records in the project | Assigned records only | No | All records in the project |

Record routes are not implemented. `record_access_for_project` is the helper a later record route must call. It reads membership from CRM storage on that request. Membership is not cached in the CRM process.

A project must keep one active project manager. Removing or demoting the last one returns 409 and leaves the row unchanged. Removal sets `status` to `removed` and keeps the row. Adding the same user again inserts a new active row. The removed row stays.

## API

Every route still checks the path tenant through Control Plane product access and permissions, then the caller identity. A body `tenant_id` is rejected. Writes require the `aadi_csrf` cookie and a matching `X-CSRF-Token` header.

| Method | Path | Success |
|---|---|---|
| `GET` | `/api/v1/tenants/{tenant_id}/projects` | `200`. Items are limited to the caller's active memberships unless the caller holds `crm.project_management.manage`. |
| `POST` | `/api/v1/tenants/{tenant_id}/projects` | `201`. The caller is stored as project manager. |
| `GET` | `/api/v1/tenants/{tenant_id}/projects/{project_id}` | `200` for a member. `404` with no project name for a non-member. |
| `PATCH` | `/api/v1/tenants/{tenant_id}/projects/{project_id}` | `200` for a manager. `403` for a member. |
| `POST` | `/api/v1/tenants/{tenant_id}/projects/{project_id}/archive` | `200` for a manager. The row remains. |
| `GET` | `.../members` | `200` `{ "items", "directory_available" }`. The caller's own email is shown. Other emails are included only when the directory read succeeds. |
| `GET` | `.../eligible-users` | `200` for a manager who can read the directory. Active tenant users who are not already active members. |
| `POST` | `.../members` | `201`. Body `user_id` and `role`. |
| `PATCH` | `.../members/{membership_id}` | `200`. Body `role`. |
| `POST` | `.../members/{membership_id}/remove` | `200`. The row remains with status `removed`. |

Project responses include `access.role`, `access.scope_policy`, `access.can_manage_project`, `access.can_manage_members`, `access.can_access_records`, and `access.record_scope`. The UI hides edit, archive, and member changes from those flags. The API checks the same actions again.

## Migration and data safety

`backend/migrations/002_project_memberships.sql` creates `project_memberships`, the partial unique index `uq_project_memberships_one_active_user`, and two lookup indexes. It does not drop a table or delete rows.

The same migration was applied twice to a copy of the development database. The copy kept 3 project rows and their archive states, recorded `002_project_memberships.sql`, and gained 3 active project-manager memberships.

It was then applied to `backend/data/aadi_crm.sqlite`. Before: version `001_projects.sql`, 3 projects (S2-DEMO archived, S2-LIVE archived, S2-REC active). After: versions `001_projects.sql` and `002_project_memberships.sql`, the same 3 projects and statuses, and 3 active project-manager memberships for the existing creator. No project row was deleted.

## Tests actually run

Closure baseline, before these edits, 19 October 2026:

- Backend: `python -m pytest -q` from `backend` → **17 passed**, 1 Starlette `httpx` deprecation warning.
- Frontend: `npm test` from `frontend` → **17 passed**.

After this sprint, same commands:

- Backend: `python -m pytest -q` → **21 passed**, 1 Starlette `httpx` deprecation warning.
- Frontend: `npm test` → **21 passed** (10 shell tests and 11 project tests).

The new backend tests cover the record-scope helper, migration preservation of an archived project, membership add, duplicate active membership, inactive and out-of-tenant users, member denial of edit, archive, and member changes, removal with the removed row kept, immediate 404 after removal, last-manager protection, directory 403 without a write, and the difference between lead read and `crm.project_management.manage`. Existing create, search, archive, cross-tenant, and leads-stub tests still pass. Backend tests use an in-process platform double and a temporary SQLite file. They do not call the Control Plane.

A separate live check, after the development migration, called the running CRM API with the recording identity. Project list returned S2-DEMO, S2-LIVE, and S2-REC, each with role `project_manager`. Members for S2-REC returned one active project manager. Eligible users returned 403 with "You cannot look up organization members with this sign-in." An unknown project id returned 404. Another tenant id returned 404.

## Recording

`docs/sprints/crm-s3/recording.webm` (32.64 seconds, 1280×720). Narration: `docs/sprints/crm-s3/explanation-script.md`.

The browser used the running Control Plane and the running CRM shell. It did not use the test double. It shows the manager membership, the directory denial, the last-manager refusal, an unknown project denial, another tenant denial, and the tenant administrator being refused Projects even though CRM is available. It does not show a successful add, because no live identity can both manage the project and read the user directory.

## Known limitations

- `crm.project_management.manage` is not registered, so no live caller has tenant-wide project administration.
- Adding a member requires the caller to hold Control Plane `users.read`. The CRM test identity does not. This repository does not grant that key.
- Business type, time zone, logo, start date, clone, and reactivate remain unimplemented.
- Archive still does not block future records. Records, forms, follow-ups, and dashboards are not in this sprint.
- The PRD v1.0 file is still not in this repository.
- Membership history keeps removed rows. It is not a separate event log.
- The CRM store remains SQLite.
