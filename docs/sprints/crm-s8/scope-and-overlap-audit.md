# CRM-S8 scope and overlap audit

Date: 20 October 2026. Written before the Sprint 6 code change. Repository: `aadi-crm` only.

Sprint 5 is closed in `docs/sprints/crm-s7/technical-acceptance.md`. This audit decides what the owner-requested Sprint 6 execution may change.

## Numbering

Two numbering schemes are in use. This execution does not replace either one.

| Scheme | Where it lives | What "Sprint 6" means |
|---|---|---|
| Original 12-sprint roadmap | `C:\Users\lenovo\Downloads\Aadi_CRM_Complete_Sprint_Plan.xlsx`, row 6. The same row is in `C:\Users\lenovo\AadiTech\Product\CRM\Aadi_CRM_Sprint_Plan_Status_Updated_2026-10-20.xlsx`. | Assignment, statuses, and duplicate detection. |
| Repository evidence folders | `docs/sprints/crm-s5` form definitions, `crm-s6` form versioning, `crm-s7` records. | The next evidence folder for this execution is `docs/sprints/crm-s8`. It is not original roadmap Sprint 8. |

The owner asked this execution to implement create, list, view, edit, custom fields, project record numbers, filters, sorting, pagination, and soft delete. That list is the original roadmap **Sprint 5** scope, which `crm-s7` already delivered. It is not the original roadmap Sprint 6.

Original roadmap Sprint 6 stays planned: assign and reassign to eligible project members, configurable statuses, a project-scoped duplicate warning, and a terminal reason where configured. This execution does not start that work. The status workbook was not modified.

The requested scope does not contradict a mandatory PRD rule and does not need a new authorization policy. It is already implemented, with the gaps listed below. Those gaps are extended. Assignment, status, duplicate detection, restore, and FORM-08 flags are not built in this pass.

## Source used

PRD v1.0 dated 9 October 2026 is not in the repository. The copy read for this audit is `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`.

## Capability map

| Requested capability | Category | Existing implementation | API | Database | UI | Tests before this pass | Missing | Planned change |
|---|---|---|---|---|---|---|---|---|
| Create records from published forms | EXISTS — REUSE | `create_record` uses `current_published_version_id` | `POST /api/v1/tenants/{tenant}/projects/{project}/records` | `records`, `record_values` | `RecordEditor` in `RecordsPanel.tsx` | `test_records.py` unpublished, validation, spoofed body | None for this request | None |
| List and view records | EXISTS — REUSE | `list_records`, `get_record` | `GET` collection and `GET .../{record_id}` | `records` joined to `form_versions` on tenant and project | `RecordList`, `RecordDetail` | List, search, detail, assigned scope | None | None |
| Edit records | EXISTS — REUSE | `update_record` keeps `form_version_id` | `PATCH .../{record_id}` | Replaces `record_values`; does not change version, source, or number | Edit route | Historical required rule, stale `updated_at` | None | None |
| Custom fields from the published schema | EXISTS — REUSE | `validate_values` against the snapshot. Types match the form builder: text, long text, number, mobile, email, URL, date, time, dropdown, multi-select, radio, checkbox, currency. File and auto-number are rejected. | Same create and patch bodies, `values` | `record_values.field_key` + `value_json` | `FormRenderer` on the record's fields | Text, dropdown, and URL removal | Broader type checks are not in the suite | Extend `test_records.py` only |
| Project record numbers | EXISTS — REUSE | `{project.code}-{sequence:04d}` inside `BEGIN IMMEDIATE` | Server-generated `public_number` | Unique `(project_id, public_number)` and `(project_id, sequence)` | Detail heading | Concurrent pair; client number ignored | Failed validation is not asserted to leave the sequence unused | Extend the test |
| Filter records | EXISTS — REUSE | `q`, `form_id`, `source`, `created_from`, `created_to` | Query parameters on the list route | `search_text`, `form_id`, `source`, `created_at` | Search, form, source, created-from, created-to | Search and wildcard escape | Invalid filter parameters and a combined filter are not asserted | Extend the test. Do not add status, assignee, or a second field-definition store. |
| Sort records | EXISTS — REUSE | Allowlist `created_at`, `updated_at`, `public_number`. Direction `asc` or `desc`. Secondary `records.id`. | `sort`, `direction` | Those columns | Newest, oldest, recently updated, record number | `sort=public_number&direction=asc` | Unsupported sort is not asserted. Tie-break on equal timestamps is not asserted. | Extend the test |
| Paginate records | PARTIAL — EXTEND | `{ items, total, limit, offset }`. Limit 1–100, default 25. Offset at least 0. Filters and sort run before `LIMIT`/`OFFSET`. Assignee scope is applied before the count. | `limit`, `offset` | `ix_records_scope` | Previous and Next at a fixed size of 25. An offset past the end hides Previous because the empty state replaces the pager. | `limit=1&offset=0` | Out-of-range page in the UI. Page size is not selectable, so a list under 26 rows cannot move to a next page. | Keep the response shape. Add page sizes 5, 25, and 50, default 25. Show the pager when the offset is past the end. |
| Soft-delete records | EXISTS — REUSE | `archive_record` sets `deleted_at`, `updated_by`, and `updated_at` | `POST .../{record_id}/archive` | `records.deleted_at`. Rows and form versions stay. | Archive record on the detail | Hidden from list and detail after one archive | A second archive and an edit of an archived row are not asserted | Extend the test. No restore route. |

## Decisions that stay unresolved

These are not implemented in this pass.

- **Original roadmap Sprint 6** (assignment, configurable statuses, duplicate detection, terminal reason) remains future scope. REC-04, REC-07, REC-08, and REC-09 are not started. Adding them would be a different sprint and would need eligibility and audit rules that are not in the current record policy.
- **Restore.** PRD section 9.2 says a soft-deleted record stays recoverable by an authorised role under the retention policy. The PRD open questions say the retention period is not defined. No restore route and no retention period are added.
- **FORM-08 flags.** Fields have no searchable, filterable, or sortable configuration. Stored values are already included in `search_text`. A separate custom-field filter parameter is not added.
- **Status and assignee filters.** There is no status column and no reassignment. Those filters are not invented. `assignee_user_id` remains the creator so the existing assigned-record rule works.

## Sprint 6 checklist

Create and edit:

- Reuse create and edit.
- Server validation stays on the published snapshot used for that write.
- `form_version_id` on an existing record does not change when a newer version is published.
- Tenant, project, actor, timestamps, and record number stay server-controlled.
- `authorize_record` stays the record policy.

Custom fields:

- Field definitions on the published snapshot remain the only definition source.
- Required rules, options, field keys, and position stay on that snapshot.
- Historical records keep their own snapshot.
- No attachments, conditional logic, calculations, or new field types.

Record number:

- Keep `{project.code}-{sequence:04d}`.
- Clients cannot set it.
- Concurrent creates stay unique.
- A rejected create does not consume a number.

Filtering:

- Keep server filters for search, form, source, and created date.
- Empty filters mean no extra constraint.
- Invalid values return 422.
- Authorization is applied before rows and counts.

Sorting:

- Keep the allowlist and the `records.id` tie-break.
- Reject an unknown sort key with 422.

Pagination:

- Keep `{ items, total, limit, offset }`.
- Apply filters and sort before the page.
- The UI shows an empty later page and can return to the previous page.
- Page size 5, 25, or 50, default 25, sent as `limit`.

Soft delete:

- Keep `deleted_at` and the archive route.
- Exclude archived rows from list, search, filter, and count.
- A second archive does not change `deleted_at`.
- Detail and edit of an archived row stay 404.
- Do not physically delete the row or the form version.

## File budget before coding

Limit: 20 new files, 10 modified files. No migration. `project_access.py` stays unchanged.

Modified (3):

- `frontend/src/features/records/RecordsPanel.tsx` — page size and an out-of-range page.
- `frontend/tests/records.test.tsx` — those UI states.
- `backend/tests/test_records.py` — invalid filters and sorts, pagination stability, custom-field validation, sequence rollback, repeated archive.

New (6, plus the recording file produced later):

- `docs/sprints/crm-s7/technical-acceptance.md`
- `docs/sprints/crm-s8/scope-and-overlap-audit.md`
- `docs/sprints/crm-s8/record-demo.mjs`
- `docs/sprints/crm-s8/explanation-script.md`
- `docs/sprints/crm-s8/implementation-report.md`
- `docs/sprints/crm-s8/technical-validation.md`
- `docs/sprints/crm-s8/recording.webm`

That plan is 3 modified files and 7 new files. It is inside the limit. If the recording cannot be produced, the report will say so and the webm will not be claimed.

## Result after implementation

The plan above was followed. One extra modified file was required: `backend/app/api/records.py` now rejects a created-date filter that is not a real calendar day. The pre-coding list did not include it. The delivered set is 4 modified files and 7 new files, still inside the limit. No migration was added. Details are in `implementation-report.md`.
