# CRM-S7 technical validation — records, list, search, and detail

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made in this pass.

This is original Sprint 5 from the sprint plan: CRM records, list, search, and detail. Evidence stays in `docs/sprints/crm-s7/`. `docs/sprints/crm-s5/` remains form definitions. `docs/sprints/crm-s6/` remains form versioning. Those folders were not replaced.

Owner acceptance is pending. Nothing in this sprint was committed.

## Requirements checklist

The PRD v1.0 dated 9 October 2026 is not in this repository. The source copy used is `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`. The sprint plan row is "CRM records: CRUD, list, search & detail" in `Aadi_CRM_Complete_Sprint_Plan.xlsx`.

| Requirement | Planned surface | Result |
|---|---|---|
| REC-01 create, view, edit, and soft-delete from the active published form | `POST`, `GET`, `PATCH`, and `POST .../archive` under `/api/v1/tenants/{tenant}/projects/{project}/records`; Records screens | Delivered. Writes use the published snapshot. Soft delete sets `deleted_at`. |
| REC-02 project record number plus a non-guessable id | `public_number` `{project.code}-{sequence:04d}` and UUID `id` | Delivered. Concurrent creates in one project receive distinct numbers. |
| REC-03 system timestamps and actor | `created_at`, `created_by`, `updated_at`, `updated_by`, `captured_at`, `source` | Delivered. The client cannot set the actor, the timestamps, the public number, the tenant, the project, or the form version. |
| REC-04 duplicate detection | Later sprint | Recorded as a Sprint 6 dependency. No substitute warning was added. |
| REC-05 search and filters | Server `q`, `form_id`, `source`, `created_from`, `created_to` | Delivered for record number, stored values, form, source, and created date. Status and assignee filters wait for Sprint 6. FORM-08 searchable flags are not on fields, so they were not invented. |
| REC-06 sort and pagination | `sort`, `direction`, `limit`, `offset` | Delivered. Saved views are deferred. |
| REC-07 assignment, REC-08 status, REC-09 terminal reason, REC-10 attachments | Later sprints | Out of this sprint. A new record stores the creator as `assignee_user_id` so the existing assigned-record rule can authorize that creator. There is no reassignment control. |
| FORM-05 retain the form version used at creation | `records.form_version_id` | Delivered. Edit validates against that snapshot. A newer publish does not move the record. |
| FORM-09 do not remove a field that already has values | Forms field removal | Delivered. Removal returns 409, "This field has saved record values and cannot be removed." |
| Authorized staff only, including tenant and project isolation | Existing `authorize_record` and project membership | Delivered. See the authorization section. |
| Sprint plan exclusion: follow-ups, pipeline, attachments, analytics | None | Left out. |

## Policy used for this sprint

These choices follow the sprint plan and the existing record-access decision. They are recorded here for owner review.

- A new record uses the form's current published version. An unpublished draft cannot be the stored schema.
- Edit and archive keep `form_version_id`. Values are checked against that snapshot.
- The creator is stored as the assignee. A project member can open records they create. A member cannot open another person's record. Reassignment is Sprint 6.
- Source is set at creation from the PRD starter keys and defaults to `manual`. Later edits do not change it.
- Archive sets `deleted_at`. List and detail hide that record. There is no restore route. The next number uses `MAX(sequence)`, including archived rows.
- An archived project rejects create, update, and archive with 409, "This project is archived." Reading an existing record stays available.
- Update and archive require `expected_updated_at`. A mismatch returns 409, "This record was updated. Reload it and try again."
- File and auto-number values are not stored. A required field of either type fails with a clear validation message.

## Files

Modified (9):

- `backend/app/main.py` — records router
- `backend/app/api/forms.py` — block removal of a field that has saved values
- `backend/tests/test_projects.py` — migration list includes `005_records.sql`
- `backend/tests/test_form_versions.py` — version tests expect an empty records table after migration
- `frontend/src/main.tsx` — records routes
- `frontend/src/services/platform.ts` — record types and API calls
- `frontend/src/features/shell/CrmShellPage.tsx` — Records navigation
- `frontend/src/features/forms/FormRenderer.tsx` — record mode on the published schema
- `frontend/src/ui/chrome.tsx` — records icon

New (11):

- `backend/migrations/005_records.sql`
- `backend/app/records_store.py`
- `backend/app/api/records.py`
- `backend/tests/test_records.py`
- `frontend/src/features/records/RecordsPanel.tsx`
- `frontend/tests/records.test.tsx`
- `docs/sprints/crm-s7/record-demo.mjs`
- `docs/sprints/crm-s7/recording.webm`
- `docs/sprints/crm-s7/explanation-script.md`
- `docs/sprints/crm-s7/technical-validation.md`
- `docs/sprints/crm-s7/implementation-report.md`

That is 9 modified files and 11 new files. The limit for this sprint is 10 modified and 20 new. `project_access.py` was left unchanged. The temporary PRD extracts under `docs/sprints/` were removed and are not part of the deliverable.

## Migration and database

`005_records.sql` is additive. It creates `records` and `record_values`, unique indexes on `(project_id, public_number)` and `(project_id, sequence)`, and scope indexes. It does not drop a table or delete rows. It does not touch Control Plane tables.

Disposable-database coverage is `test_record_migration_preserves_projects_forms_and_versions` and `test_development_copy_gains_records_without_changing_the_original` in `backend/tests/test_records.py`. A database already on migrations 001 through 004 keeps its project, form, and published snapshot, gains `005_records.sql`, and starts with an empty `records` table. A copy of the development file gains the same migration while the original file bytes stay unchanged during that copy.

The running CRM process applied `005_records.sql`. A later read-only query of `backend/data/aadi_crm.sqlite` showed migrations `001` through `005`. Projects are unchanged: Harbor gate archived, Live gate archived, Recording gate active. Memberships are unchanged: four active project managers and one removed project manager. Enquiry draft is still unpublished.

The shared development database was not reset. The browser captures added rows on Recording gate:

| Form | Versions | Record |
|---|---|---|
| Record gate | 1, current | S2-REC-0001, North school, version 1, still listed |
| Record check | 1 and 2, version 2 current | S2-REC-0002, North school, version 1, still listed |
| Record proof | 1 and 2, version 2 current | S2-REC-0003, North campus, version 1, archived |
| Record capture | 1 and 2, version 2 current | S2-REC-0004, North campus, version 1, archived |

Record capture and S2-REC-0004 are the successful recording. The other three forms are from capture attempts that stopped before the member denial. No membership row was changed.

Rollback, if an owner asks for it later, is to drop `record_values` and `records` and delete the `005_records.sql` row from `crm_schema_migrations`. That removes record data. Project, membership, form, and version rows are not rewritten by this migration. No down script was added.

## Tests

Backend, from `backend` with the project virtualenv, after the recording:

`python -m pytest -q --tb=line` → **39 passed**, 1 Starlette `httpx` deprecation warning, in 7.51 seconds.

Frontend, from `frontend`, after the Records navigation note:

`npm test` → **31 passed** (10 shell, 11 project, 4 form, 4 form-version, 2 record) in 8.92 seconds. npm warned that the env config `devdir` is unknown.

The record tests cover create, validation, historical version retention, search, edit, archive, assigned-record scope, archived-project writes, a removed member, another project, another tenant, `users.read` without a CRM permission, a missing CSRF token, concurrent record numbers, and both migration paths.

## Authorization

Every list, search, create, detail, update, and archive request uses the existing module open, project load, and `authorize_record`. Tenant and project come from the path and the authenticated context. A form version id in the body is ignored. A version that belongs to another project cannot be selected, because the published version is loaded inside the same tenant and project.

| Action | Project manager | Project member | Removed, non-member, other project, other tenant |
|---|---|---|---|
| List and search | Records in the project | Records assigned to that member | Empty list, or 404 for another tenant, without the record text |
| Detail | Any record in the project | Own assigned record. Another person's record is 404 | 404, without the record text |
| Create, edit, archive | Yes, while the project is active | Yes for a record assigned to that member | 404. An archived project returns 409 for writes and still allows a read |

`users.read` without a CRM permission is 403. A write without the CSRF cookie and matching `X-CSRF-Token` is 401.

The live recording shows the project manager creating and archiving S2-REC-0004, then `playwright-member@example.com` being told Records is not available, then "You do not have permission to perform this action." on the Recording gate records address.

## Browser evidence

- `docs/sprints/crm-s7/recording.webm` — 8,065,302 bytes, VP9, 1280×720, 118.76 seconds
- `docs/sprints/crm-s7/explanation-script.md`
- `docs/sprints/crm-s7/record-demo.mjs`

The capture script exited 0 and logged `RECORD S2-REC-0004`, then `publish-version-2`, `historical-detail`, `search-and-archive`, `member-denied`, and `done`.

## Known limitations

- Owner review is still required. This sprint is not closed and was not committed.
- Status, assignee filters, reassignment, duplicate warnings, saved views, attachments, and activity history are later work.
- The field-missing-from-draft sentence is covered by the frontend test. The recording shows the historical label instead, because the field identifier was kept.
- Record gate, Record check, and Record proof remain on Recording gate from the failed capture attempts.
- The sprint status workbook was not updated.
