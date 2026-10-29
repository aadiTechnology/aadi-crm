# CRM-S6 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change was made for this sprint.

This is original Sprint 4: form versioning, preview, and the internal renderer. Evidence is stored under `crm-s6` so `docs/sprints/crm-s4/` stays the membership and record-decision sprint. The sprint is not closed. Owner acceptance is still pending. The later validation pass is `docs/sprints/crm-s6/technical-validation.md`.

## Source of the requirements

The original sprint plan row is "Form versioning, preview & internal renderer". The acceptance line is that published forms render correctly and new versions do not corrupt old records. The plan excludes a public or customer-facing form renderer.

The PRD v1.0 dated 9 October 2026 is still not in this repository. It is on this machine at `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`. FORM-05 is the immutable published version. FORM-06 asks for both an internal preview and a public preview. This sprint implements the internal preview only. The public preview remains an unresolved scope distinction because the sprint plan excludes it. FORM-04 reusable tenant picklists, FORM-07 conditional logic, FORM-08 reporting flags, and FORM-09 historical field removal are not this sprint. DEC-03 recommends that project-manager publish stay configurable and off until an owner approves it. This sprint lets a project manager publish because that role already administers the draft. That is an outstanding owner decision, not a new Control Plane permission.

Sprint 3 form definitions were already present and were safe to build on. Drafts can be read, field keys stay fixed after creation, field order is stored, and project authorization already hides unknown projects. No Sprint 3 redesign was required.

## Data model

`backend/migrations/004_form_versions.sql` is additive.

`form_definitions` remains the mutable draft, still with status `draft`. `form_fields` remains the mutable field list. `form_versions` stores one immutable snapshot per publication:

| Column | Role |
|---|---|
| `id` | Stable id a future CRM record can store as `form_version_id` |
| `tenant_id`, `project_id`, `form_id` | Scope. `form_id` references `form_definitions` |
| `version_number` | Integer, at least 1, unique per form |
| `schema_json` | Complete snapshot: name, description, and fields with keys, labels, types, required rules, defaults, options, order, section, and the supported validation metadata |
| `published_by`, `published_at` | Publisher and timestamp taken from the authenticated user |

`form_definitions.current_published_version_id` points at the latest published row. Version status is derived: `current` when the id matches that pointer, otherwise `published`. Publishing version 2 does not update the version 1 row. There is no `records` table.

Draft edits stay on `form_definitions` and `form_fields`. A published row is a JSON copy, not a foreign key to the live field rows. `BEFORE UPDATE` and `BEFORE DELETE` triggers abort changes to `form_versions`. Ordinary application routes do not update or delete a version. A `PATCH` to a version URL has no handler and returns 405.

Publish runs in `BEGIN IMMEDIATE` with `busy_timeout` of 5000 milliseconds. The next version number is `MAX(version_number) + 1` inside that lock. `(form_id, version_number)` is unique, so a second insert of the same number fails. An identical canonical snapshot returns 409, "This draft is already published." Two concurrent publishes of the same draft produce one version and one duplicate rejection, and the current-version pointer matches that single row.

An empty form, a picklist with no options, or a minimum greater than its maximum returns 422 and inserts nothing. If the transaction fails before commit, the rollback leaves no version row and leaves the current-version pointer null.

Existing Sprint 3 drafts stay drafts. The new column is null until the first successful publish. Projects, memberships, field keys, and field order are not rewritten by the migration.

Replacing the draft copies the current published snapshot back onto the same form. Field ids are new. Keys, order, options, required rules, and validation metadata are copied. The snapshot itself is not updated. Unpublished draft edits are discarded. A form with no published version returns 409.

## API and authorization

No new Control Plane permission was added. Opening the module still requires CRM product access plus `crm.lead_management.read` or `crm.project_management.manage`. A general CRM read permission does not become tenant-wide form administration. Tenant id, project id, and publisher id come from the authenticated context and the path, not from a request body. Publish reads no body. Writes still require the `aadi_csrf` cookie and a matching `X-CSRF-Token` header.

| Action | Project manager | Active project member | Removed, non-member, other project, other tenant |
|---|---|---|---|
| Preview the draft | Yes | No, 403 | No, 404, and the response does not include the form name |
| Publish and replace the draft | Yes | No, 403 | No, 404 |
| List versions and render one version | Yes | Yes | No, 404 |

Archive follows the existing project policy. A manager of an archived project can still publish. A member of an archived project can still render and still cannot publish.

| Method | Path | Success |
|---|---|---|
| `GET` | `.../forms/{form_id}/preview` | `200` draft schema, source `draft` |
| `GET` | `.../forms/{form_id}/versions` | `200` `{ "items" }` |
| `POST` | `.../forms/{form_id}/versions` | `201` new version |
| `GET` | `.../forms/{form_id}/versions/{version_id}` | `200` immutable schema used by the internal renderer |
| `POST` | `.../forms/{form_id}/draft` | `200` draft replaced from the current published snapshot |

Duplicate publish is 409. An invalid draft is 422. A missing form or version is 404.

## Preview and internal renderer

Preview and published rendering use the same field metadata. The preview route is `/tenants/:tenantId/forms/:projectId/:formId/preview`. The published route is `.../versions/:versionId`. Required fields are marked. Check preview validates on the page and states that no CRM record was saved. File upload and auto-number generation are shown as unavailable in this view. They are not simulated. The layout stacks at a narrow width.

## Migration and data safety

Migration checks used temporary databases and a copy of the development file. They did not reset or delete the shared development database. The tests confirm that a database already on migrations 001 through 003 keeps its draft, gains `004_form_versions.sql`, and has an empty `form_versions` table and a null current-version pointer. A copy of the development file gains the same migration while the original file's snapshot is unchanged by that copy.

The running CRM process uses `--reload` and applied `004_form_versions.sql` on its own startup path. A later read-only query of `backend/data/aadi_crm.sqlite` showed:

- Migrations `001_projects.sql`, `002_project_memberships.sql`, `003_form_definitions.sql`, and `004_form_versions.sql`.
- Tables `projects`, `project_memberships`, `form_definitions`, `form_fields`, `form_versions`, and `crm_schema_migrations`. No records table.
- Projects unchanged: Harbor gate archived, Live gate archived, Recording gate active.
- Memberships unchanged: four active project managers and one removed project manager. No active project member row.
- Enquiry draft still unpublished, with Priority then School name.
- Site enquiry, left by an earlier incomplete browser pass in this session: version 1 is Priority then School name, version 2 is Priority then Campus and is current. The draft label is Campus.
- Version check, created by the successful recording: version 1 is School name then Priority, version 2 is Campus then Priority and is current. The draft label is Campus.

## Tests actually run

Backend, from `backend` with the project virtualenv:

`python -m pytest -q` → **34 passed**, 1 warning, in 24.73 seconds. The warning is Starlette's deprecation notice that `httpx` with `starlette.testclient` should move to `httpx2`.

Frontend, from `frontend`:

`npm test` → **29 passed** (10 shell, 11 project, 4 form, 4 form version) in 30.14 seconds. npm also printed an environment notice that `devdir` is an unknown env config. That is not a test failure.

An earlier frontend run failed two tests at the default 5 second limit, and one following form test then saw a stale field type. The create-form screen now loads versions as well as the draft, and that test took 10.8 seconds on the passing run. `frontend/vite.config.ts` sets `testTimeout` to 20 seconds. The passing run above is the result after that change.

Backend tests use an in-process platform double and a temporary SQLite file. They cover version 1, an unchanged version 1 after a draft edit and after version 2, a draft replaced from the published schema, duplicate and concurrent publish, invalid drafts, a failed transaction with no partial version, manager preview and publish, member render without publish or preview, removed and non-member and cross-project and cross-tenant 404 responses, archive behavior, missing CSRF, and the future `form_version_id` column being available without a records table. The existing project and form tests still pass.

## Recording

`docs/sprints/crm-s6/recording.webm` is 2,737,483 bytes, captured at 1280×720 by a headless Chromium session against the running CRM shell, CRM API, and Control Plane. Narration: `docs/sprints/crm-s6/explanation-script.md`. The capturing script logged every step in that script and exited 0. A separate media probe of the duration was not run, so no duration is stated here.

The recording shows a project manager opening Recording gate, creating Version check, previewing the required School name field, confirming that a typed value is not saved, publishing version 1, changing the draft label to Campus, publishing version 2, and rendering version 1 with School name still present. It then signs in as `playwright-member@example.com`. That identity does not have CRM forms access. Forms is unavailable, and opening the existing Site enquiry address shows "You do not have permission to perform this action." Publish version is not shown.

The recording does not show an active project member rendering a published version. The development database has no active project member. That path passed in `backend/tests/test_form_versions.py` and `frontend/tests/form-versions.test.tsx`.

## Files

New (8): `backend/migrations/004_form_versions.sql`, `backend/app/form_versions.py`, `backend/tests/test_form_versions.py`, `frontend/src/features/forms/FormRenderer.tsx`, `frontend/tests/form-versions.test.tsx`, `docs/sprints/crm-s6/implementation-report.md`, `docs/sprints/crm-s6/explanation-script.md`, `docs/sprints/crm-s6/recording.webm`.

Modified (10): `backend/app/api/forms.py`, `backend/app/forms_store.py`, `backend/app/project_access.py`, `backend/tests/test_projects.py`, `frontend/src/features/forms/FormsPanel.tsx`, `frontend/src/main.tsx`, `frontend/src/services/platform.ts`, `frontend/src/styles.css`, `frontend/tests/forms.test.tsx`, `frontend/vite.config.ts`.

The budget is 20 new files and 10 modified files. This sprint is at 8 new and 10 modified.

## Acceptance

| Criterion | Result |
|---|---|
| Preview a draft before publication | PASS |
| Publish an immutable numbered version | PASS |
| View published versions and status | PASS |
| Create a new draft from the current published definition | PASS in the API and tests. The recording does not click Replace draft |
| Render a selected published version for an authorized internal user | PASS. The recording renders as the project manager. Member rendering passed in tests |
| Keep a historical `form_version_id` for future records | PASS as a schema contract. No record table was created |
| Published snapshot does not change when the draft changes or a newer version is published | PASS |
| Existing Sprint 3 drafts, projects, and memberships remain | PASS |
| Public or customer-facing renderer | Not implemented. Unresolved against FORM-06 |

## Known limitations

- The sprint is not closed and is not claimed ready for production.
- CRM record create, read, update, and delete are not implemented.
- Public preview, public submission, OTP, attachments, conditional logic, calculations, dashboards, and import/export are not implemented.
- File upload and auto-number generation are indicated as unavailable. They do not run.
- Replacing the draft discards unpublished draft edits on that same form. It does not create a second form definition.
- `crm.project_management.manage` is still not registered.
- Whether project-manager publish should be separately configurable and off by default (DEC-03) needs an owner decision.
- The development database now contains published Site enquiry and Version check on Recording gate, from this session's browser passes. Memberships were not edited.
