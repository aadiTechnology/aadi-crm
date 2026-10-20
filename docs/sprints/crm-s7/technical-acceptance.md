# CRM-S7 technical acceptance — original Sprint 5

Date: 20 October 2026. Repository: `aadi-crm` only. Reviewer pass for this document did not commit, push, merge, tag, deploy, or change the Control Plane.

This folder is original Sprint 5 from `Aadi_CRM_Complete_Sprint_Plan.xlsx`: "CRM records: CRUD, list, search & detail". `docs/sprints/crm-s5/` remains form definitions. `docs/sprints/crm-s6/` remains form versioning. The status workbook `C:\Users\lenovo\AadiTech\Product\CRM\Aadi_CRM_Sprint_Plan_Status_Updated_2026-10-20.xlsx` still lists original Sprint 5 as planned. That workbook was not modified.

Decision: **CLOSED** against the checks below. Owner review of this closure is still required. Sprint 6 acceptance is a separate decision.

The implementation was already on `main` at `315c1e3` when this review started. The working tree was clean. Earlier sprint notes said the work was uncommitted. This review did not create that commit and did not make another one.

## Acceptance criteria

| Check | Status | Evidence |
|---|---|---|
| Create a record from a published form | PASS | `POST .../records` loads the form's current published version. An unpublished form returns 409, "Publish this form before creating a record." `test_record_keeps_its_published_version_through_search_edit_and_archive`. |
| Server assigns tenant, project, actor, timestamps, and form version | PASS | Path tenant and project are loaded through the existing module and project checks. `created_by`, `updated_by`, `assignee_user_id`, `captured_at`, `created_at`, and `updated_at` come from the caller and the server clock. Body fields `tenant_id`, `form_version_id`, `created_by`, `assignee_user_id`, and `public_number` do not change the stored row. |
| Record numbers are unique in their project | PASS | Format is `{project.code}-{sequence:04d}`. Unique indexes `uq_records_project_number` and `uq_records_project_sequence`. Allocation uses `BEGIN IMMEDIATE`, `MAX(sequence)+1`, and `busy_timeout` 5000 ms, including archived rows. `test_concurrent_creates_receive_distinct_record_numbers` received `N-1-0001` and `N-1-0002`. Development rows are `S2-REC-0001` through `S2-REC-0004`. |
| List, search, detail, and edit use the existing record policy | PASS | Every route calls `_open_module`, `_load_project(..., "access_records")`, and `authorize_record`. Sort keys are allowlisted. Search uses a parameterized `LIKE`. |
| An assigned project member cannot open another member's record | PASS | `test_record_access_stays_inside_the_project_and_assignment_scope`. The member list for the manager's text is empty and the detail is 404 without the record text. The member can create and list their own record. |
| A project manager can use records in the project | PASS | The same test, after switching back to the manager, lists both `N-1-0001` and `N-1-0002`. |
| Cross-tenant, cross-project, removed-member, and unauthorized requests are denied | PASS | Other project list is empty. Other tenant is 404. Removed member detail is 404 without the record text. `users.read` without a CRM permission is 403. A write without the CSRF pair is 401. |
| Edit uses the record's original form version | PASS | Update loads `form_version_id` already stored on the row. A newer version id in the body is ignored. Required rules from version 1 still apply after version 2 is published. |
| A newer publication does not change existing fields or labels | PASS | After the draft label changes and version 2 is published, the stored record still has the version 1 label "School name" and the same `form_version_id`. The next new record uses version 2. |
| Archive behavior | PASS | `POST .../archive` sets `deleted_at` and does not remove the row or `record_values`. List, search, and detail omit the row (`deleted_at IS NULL`). A later edit cannot load it. The next number still counts the archived sequence. An archived project returns 409 on create and still allows read. |
| Migration `005_records.sql` preserves existing data | PASS | Additive `CREATE TABLE` and indexes only. `test_record_migration_preserves_projects_forms_and_versions` keeps the project, form, and published snapshot and starts with zero records. `test_development_copy_gains_records_without_changing_the_original` copies the development file, applies the migration, and leaves the original bytes unchanged. |
| Backend and frontend suites | PASS | Commands and counts are below. |
| Recording compared with the explanation script | PASS with a visual limit | File inspected. See Recording review. The limit is evidence coverage, not a failed product check. |

No security defect, data-integrity defect, or critical regression was found in this review. Sprint 6 was allowed to start.

## Tests run in this review

Backend, from `backend`, using `.\.venv\Scripts\python -m pytest -q --tb=line`:

**39 passed**, 1 Starlette `httpx` deprecation warning, in 8.74 seconds.

Frontend, from `frontend`, using `npm test`:

**31 passed** (5 files) in 13.39 seconds. npm warned that `devdir` is an unknown env config.

`npx tsc --noEmit` from `frontend` exited 2. The failures are the existing baseline:

- `src/lib/config.ts` — `ImportMetaEnv` has no properties in common with the config argument type.
- `tests/form-versions.test.tsx` — `FormVersion` is not assignable in a spread of published versions.
- `vite.config.ts` — cannot find `node:path`; `ImportMeta.dirname` is missing.

These files were not changed for records. Vitest does not use this check. The failures stay visible.

## Database and migration

Read-only query of `backend/data/aadi_crm.sqlite` during this review. The file was not reset or written by the review.

Migrations present: `001_projects.sql`, `002_project_memberships.sql`, `003_form_definitions.sql`, `004_form_versions.sql`, `005_records.sql`.

Projects: Harbor gate `S2-DEMO` archived, Live gate `S2-LIVE` archived, Recording gate `S2-REC` active.

Memberships: 4 active project managers, 1 removed project manager.

Forms: 11. Published versions: 19. Records: `S2-REC-0001` and `S2-REC-0002` listed; `S2-REC-0003` and `S2-REC-0004` archived. Unique indexes `uq_records_project_number` and `uq_records_project_sequence` are present.

`005_records.sql` does not drop a table, delete a row, or alter projects, memberships, forms, or form versions.

## Authorization

`authorize_record` in `backend/app/project_access.py` was not changed. A project manager, and a tenant admin with `crm.project_management.manage`, receives project scope. A project member receives assigned scope and must match `assignee_user_id`. Another tenant, another project, a removed membership, and a missing membership are denied. Denied detail responses are 404 and do not include the record text. List applies the assignee constraint before rows are returned, then checks `authorize_record` again.

A new record stores the creator as `assignee_user_id`. There is no reassignment control.

## Recording review

`docs/sprints/crm-s7/recording.webm` was inspected with ffprobe and frame extracts. It is VP9, 1280×720, 8,065,302 bytes, duration 118.76 seconds. Creation time in the file is 2026-10-20T10:27:35Z.

Frames match the explanation script for: sign-in as `playwright-recording@example.com`, Records navigation, form "Record capture", required School name, Priority dropdown, new record on published version 1 with "North school" and Hot, draft label changed to Campus, publication while version 1 is still current, search text "North campus", sign-out, and the masked sign-in for `playwright-member@example.com`.

These script claims were not visible in the sampled frames:

- The detail heading `S2-REC-0004`.
- The stored label "School name" after version 2.
- "No matching records."
- The list after archive.
- "Records is not available for this sign-in."
- "You do not have permission to perform this action."

The list filters fill the 720px viewport, so result rows sit below the fold. The file ends on "Checking access" during the second sign-in. The database still has archived `S2-REC-0004` on Record capture version 1. The denied-access cases are in `backend/tests/test_records.py`. This review does not claim those ending screens were seen.

## Known defects and limitations

- `npx tsc --noEmit` is not clean. The three baseline errors above remain.
- Status, assignee filters, reassignment, duplicate warnings, saved views, attachments, and the activity timeline are later roadmap work.
- Edit replaces `record_values`. It does not keep a field-history row.
- File and auto-number values are rejected. A required field of either type cannot be saved.
- Dates in the list use `toLocaleString()`, not a fixed DD-MM-YYYY formatter.
- Restore of an archived record is not implemented. The PRD says soft-deleted records remain recoverable under a retention policy, and the retention period is still an open PRD question. No retention rule was invented here.
- Record gate, Record check, Record proof, and Record capture remain on Recording gate from the earlier capture.
- The sprint status workbook was not updated.
- The recording does not show the permission-denial sentence on screen.

## Deviations from PRD v1.0 (9 October 2026)

The PRD file is not in this repository. The copy used is `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`.

- REC-01 through REC-03, REC-05 for source, created date, form, and stored-value search, REC-06 sort and pagination, and FORM-05 version retention are in this sprint. REC-06 saved views are not.
- REC-04 duplicate detection, REC-05 status and assignee filters, REC-07 assignment, REC-08 status, REC-09 terminal reason, REC-10 attachments, and REC-11 timeline stay on the original later sprints.
- FORM-08 searchable and filterable flags are not stored on fields. Search uses the stored number, name, source, values, and picklist labels. Those flags were not invented.
- FORM-09 blocks removal of a field that already has a `record_values` row, including a value on an archived record.
- The human number is `{project.code}-{sequence:04d}` rather than a separate prefix such as `PRE-0001`. The project code is the prefix. `S2-REC-0004` is that format.
- Soft delete is `deleted_at` through `POST .../archive`. There is no restore route.

## Confirmation

This review did not commit, push, merge, tag, deploy, or modify Control Plane code or the Control Plane database. The shared CRM development database was only read.
