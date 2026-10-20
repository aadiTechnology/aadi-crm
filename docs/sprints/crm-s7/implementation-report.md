# CRM-S7 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change was made for this sprint.

This is original Sprint 5: CRM records, list, search, and detail. Evidence is stored under `crm-s7` so `docs/sprints/crm-s5/` stays the form-definition sprint and `docs/sprints/crm-s6/` stays form versioning. The sprint is not closed. Owner acceptance is still pending. The validation pass is `docs/sprints/crm-s7/technical-validation.md`.

## Source of the requirements

The original sprint plan row is "CRM records: CRUD, list, search & detail". The acceptance line is that authorized staff manage records only in permitted projects, and that the record number stays unique under concurrent creation. The plan depends on published forms and project authorization. It excludes follow-ups, an advanced pipeline, attachments, document management, and analytics.

The PRD v1.0 dated 9 October 2026 is still not in this repository. It is on this machine at `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`. REC-01 through REC-03, REC-05 search on the fields that exist now, REC-06 sort and pagination, and FORM-05 version retention are in this sprint. REC-04 duplicates, REC-05 status and assignee filters, REC-06 saved views, REC-07 reassignment, REC-08 status, REC-09 terminal reason, and REC-10 attachments stay with later sprints. FORM-09 removal of a field that already has values is enforced here.

Sprint 4 published versions were already present and were safe to build on. A record stores `form_versions.id`. The draft is not the schema for a saved record.

## Data model

`backend/migrations/005_records.sql` is additive.

`records` stores one CRM record:

| Column | Role |
|---|---|
| `id` | Non-guessable primary key |
| `tenant_id`, `project_id` | Scope. `project_id` references `projects` |
| `form_id`, `form_version_id` | The form and the exact published snapshot. Both are foreign keys |
| `public_number`, `sequence` | Human number `{project.code}-{sequence:04d}` and the integer behind it. Each is unique per project. `sequence` is at least 1 |
| `display_name`, `search_text` | First non-empty text value, otherwise the public number. Search text is the lowercased number, name, source, values, and picklist labels, capped at 8000 characters |
| `source` | Set at creation. Starter keys are manual, website, phone_call, justdial, meta_ad, referral, import, and other |
| `assignee_user_id` | The creator. There is no reassignment in this sprint |
| `created_by`, `updated_by`, `created_at`, `updated_at`, `captured_at` | Taken from the authenticated user and the server clock |
| `deleted_at` | Soft delete. Null while the record is listed |

`record_values` stores one JSON value per field key. `(record_id, field_key)` is unique. Values are checked against the snapshot before insert.

List and detail join `form_versions` on the version id and on the same tenant and project. A version id from another project cannot authorize the row.

Create and update run in `BEGIN IMMEDIATE` with `busy_timeout` of 5000 milliseconds. The next sequence is `MAX(sequence) + 1` inside that lock, including archived rows. Update compares `updated_at` with `expected_updated_at` and replaces `record_values` without changing `form_version_id`, `source`, or `public_number`.

## API and authorization

No new Control Plane permission was added. Opening the module still requires CRM product access plus `crm.lead_management.read` or `crm.project_management.manage`. Project access uses the existing `access_records` action and `authorize_record`. A project manager can use records in the project. A project member can use records assigned to them. Denied records return 404 and the response body does not include the record text. Writes still require the `aadi_csrf` cookie and a matching `X-CSRF-Token` header.

| Method | Path | Success |
|---|---|---|
| `GET` | `.../records` | `200` `{ items, total, limit, offset }` |
| `POST` | `.../records` | `201` detail for the current published version |
| `GET` | `.../records/{record_id}` | `200` historical fields, values, and version id |
| `PATCH` | `.../records/{record_id}` | `200` values replaced on the original version |
| `POST` | `.../records/{record_id}/archive` | `200` `{ id, archived: true }` |

List query parameters are `q`, `form_id`, `source`, `created_from`, `created_to`, `sort`, `direction`, `limit` (1–100, default 25), and `offset`. Sort is limited to `created_at`, `updated_at`, and `public_number`. Search uses a parameterized `LIKE` with an escape character. A member list adds the assignee filter before rows are returned, and each row is checked with `authorize_record` again.

Create reads `form_id`, optional `source`, and `values`. Tenant, project, form version, public number, actor, and timestamps are not taken from the body. An unpublished form is 409, "Publish this form before creating a record." Validation is 422 and includes a field map. A stale update is 409, "This record was updated. Reload it and try again." An archived project rejects create, update, and archive with 409, "This project is archived."

Detail returns fields in the snapshot order, `absent_from_draft` for snapshot keys missing from the current draft, and `unmapped_values` for stored keys that are not in the snapshot.

Removing a draft field that already has a `record_values` row, including a value on an archived record, returns 409, "This field has saved record values and cannot be removed."

## Screens

Records is a separate nav item. The Leads stub is unchanged.

Routes, more specific first:

- `/tenants/:tenantId/records`
- `/tenants/:tenantId/records/:projectId/new`
- `/tenants/:tenantId/records/:projectId/:recordId/edit`
- `/tenants/:tenantId/records/:projectId/:recordId`
- `/tenants/:tenantId/records/:projectId`

The list loads one project page from the server. It shows the public number, form and version, created and updated times, and up to three summary values. It has loading, empty, error, and retry states. Search, form, source, created-date range, sort, and pagination stay on the server.

New record loads `getFormVersion` for the form's current published version and renders that schema. Edit loads the fields stored on the record. The renderer says "Published version {n}. Saving uses this version, not the current draft." Save is guarded against a second submit while the request is in flight. Source is chosen only on create.

Detail shows the public number, display name, source, timestamps, form name, version number, and form version id. A field missing from the current draft keeps its historical label and says that this record still uses that version. Edit and archive are hidden when the project is archived. A direct visit without project access shows "You do not have permission to perform this action." A sign-in that cannot open projects shows "Records is not available for this sign-in."

## Migration and data safety

Migration checks used temporary databases and a copy of the development file. They did not reset or delete the shared development database.

The running CRM process applied `005_records.sql`. A later read-only query showed migrations `001` through `005`, the same three projects, and the same membership counts: four active project managers and one removed project manager. Enquiry draft is still unpublished. Site enquiry, Version check, and the Closure forms from Sprint 4 are still present.

Browser captures in this session added Record gate, Record check, Record proof, and Record capture on Recording gate, and records S2-REC-0001 through S2-REC-0004. S2-REC-0003 and S2-REC-0004 are archived. The successful recording is Record capture and S2-REC-0004.

Rollback is documented in `technical-validation.md`. No down migration was shipped.

## Tests and recording

Backend: `python -m pytest -q --tb=line` from `backend` → **39 passed**, 1 Starlette `httpx` deprecation warning, in 7.51 seconds.

Frontend: `npm test` from `frontend` → **31 passed** in 8.92 seconds.

Recording: `docs/sprints/crm-s7/recording.webm`, 8,065,302 bytes, VP9, 1280×720, 118.76 seconds. The matching narration is `docs/sprints/crm-s7/explanation-script.md`. The capture script exited 0.

## File counts

9 modified files and 11 new files. The lists are in `technical-validation.md`. Both counts are inside the sprint limit of 10 modified and 20 new.

## Known limitations

- Status, assignee filters, reassignment, duplicate warnings, saved views, attachments, and activity history are later sprints.
- Field history is overwritten on edit. The activity timeline is later work.
- The development database has no active project member, so the recording shows a sign-in without CRM access. Assigned-record behavior is in the backend test.
- Record gate, Record check, and Record proof remain from the capture attempts that stopped early.
- The sprint status workbook was not updated.
- No commit, push, merge, tag, or deployment was performed.
