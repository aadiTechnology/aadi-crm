# CRM-S4 implementation report

Date: 19 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change.

Status: **partially closed — blocked**.

The membership API and role matrix from CRM-S3 are unchanged in behavior. This closure adds the record decision a later record route must call, an invalid-role regression, and a new live recording of the directory blocker. It does not register a permission or grant `users.read`.

## Closed in this sprint

- `decide_record_access` in `backend/app/project_access.py` decides one record from the caller's current project access. `authorize_record` in `backend/app/api/projects.py` loads that access from CRM storage on the call and then decides. There is no membership cache.
- A project manager may use a record in the authorized project, including a record assigned to someone else.
- A project member may use a record in that project only when `assignee_user_id` is the caller.
- An unassigned record, a record assigned to someone else, a removed membership, a missing membership, another project, and another tenant are denied. The denial does not carry the other project's name.
- An invalid role such as `tenant_admin` returns 422 and does not insert a membership.
- The development database was not migrated again and was not reset.

## Still blocked

Live add, role change, and removal of a second user cannot be completed with the current sign-ins.

The approved Control Plane contract is:

- `GET /api/v1/tenants/{tenant_id}/users`
- `GET /api/v1/tenants/{tenant_id}/users/{user_id}`

Both require TenantContext and the existing permission `users.read`. Missing permission is 403. A user who is not a member of that tenant is 404. `GET /api/v1/tenants/{tenant_id}/memberships` returns only the caller and is not a directory.

`playwright-recording@example.com` holds only `crm.lead_management.read`, so those directory calls return 403 and CRM writes nothing. `playwright-member@example.com` holds `users.read` and does not hold a CRM permission, so the project API denies the caller before membership changes.

No existing CRM-visible contract lists other tenant users without `users.read`. Accepting a typed user id without that check would allow an out-of-tenant id. A CRM service account would be a new credential, which this repository does not add.

Owner decision, and the smallest one: grant the existing key `users.read` to the CRM project-manager role, and do not grant `users.update`. Do not invent a new permission. This repository must not make that grant. Until it exists, live assignment stays blocked.

`crm.project_management.manage` is still not registered. Lead read still does not administer every project.

## Record policy versus record endpoints

`RecordRef` is an input value with `tenant_id`, `project_id`, and `assignee_user_id`. CRM does not store records. No record route exists, so production record authorization is not exercised. The first record route must call `authorize_record` on every request and must not keep a copied membership.

## Migration and data

No new migration. After this sprint, `backend/data/aadi_crm.sqlite` still has versions `001_projects.sql` and `002_project_memberships.sql`, projects S2-DEMO archived, S2-LIVE archived, and S2-REC active, and three active `project_manager` rows. The live remove was refused, so those rows stayed.

## Tests

Before this edit:

- Backend `python -m pytest -q` from `backend` → **21 passed**, 1 Starlette `httpx` deprecation warning.
- Frontend `npm test` from `frontend` → **21 passed**.

After this edit:

- Backend `python -m pytest -q` → **22 passed**, same warning. The added test is the invalid role. The record decisions are in the existing scope test and in the membership test's call to `authorize_record` after removal.
- Frontend files were not changed, so the frontend suite was not run again.

Backend tests use an in-process platform double and a temporary SQLite file. They are not the live recording.

## Recording

`docs/sprints/crm-s4/recording.webm` (31.16 seconds, 1280×720). Narration: `docs/sprints/crm-s4/explanation-script.md`.

The browser used the real Control Plane. It shows the manager membership, the directory failure, the last-manager refusal, an unknown project denial, another tenant denial, and the tenant administrator being refused the project. It does not show an added user.

## Files

Modified: `backend/app/project_access.py`, `backend/app/api/projects.py`, `backend/tests/test_projects.py` (3).

New: `docs/sprints/crm-s4/implementation-report.md`, `docs/sprints/crm-s4/explanation-script.md`, `docs/sprints/crm-s4/recording.webm` (3).

`docs/sprints/crm-s2/` and `docs/sprints/crm-s3/` were not edited.
