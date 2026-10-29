# Original Roadmap Sprint 9 — Import/Export

Date: 20 October 2026. Repository: `aadi-crm` only.

`docs/sprints/crm-s11` is the evidence folder for original roadmap Sprint 9. It is not original roadmap Sprint 11. `docs/sprints/crm-s9` remains the evidence folder for original Sprint 7, and `docs/sprints/crm-s10` remains the evidence folder for original Sprint 8.

This plan was the scope used for the implementation. Saved reusable mappings, PDF export, Google API access, and original roadmap Sprint 6 were not added.

## Goal

A project manager can import CSV or XLSX rows into a published form, review mapping, validation, and possible duplicates, commit the valid rows, download an error report, and export the authorized filtered record list.

## Data model used

Records stay bound to the published form version selected when the import job is created. Field values stay in `record_values.value_json`. Row checks call the existing `validate_values` function. There is no second field validator and no fixed column list apart from the published form.

Import history is stored in `import_jobs` and `import_rows` (`backend/migrations/008_imports.sql`) so a retry, an error report, and the accepted/rejected/skipped counts come from the database.

## File rules

CSV uses the Python standard library. XLSX is read and written as zip XML. No spreadsheet package was added. Formula cells in an uploaded XLSX file are rejected and are not evaluated. CSV text is data, including text that starts with `=`, `+`, `-`, or `@`.

Limits, chosen so one request stays in memory and is not truncated:

- 1 MiB file
- 500 data rows
- 40 columns
- 5,000 characters in one cell

The header is row 1 and is not a data row. Spreadsheet data rows start at 2. A file over a limit is rejected. Empty files, blank headers, duplicate headers, extra cells, a second worksheet, macros, encryption, and non-UTF-8 CSV are rejected.

The upload body is JSON: `form_id`, `idempotency_key`, `filename`, and `content_base64`. Tenant, project, and user come from the authenticated session and the project route, not from the file.

## Mapping, preview, and commit

Every header must be mapped or explicitly left unmapped. One source column can target one field. `file` and `auto_number` cannot be mapped. Unmapped values stay on the import row and are not copied onto the CRM record. Mapping is frozen after a row is accepted. Reusable saved mappings are deferred.

Preview writes validation and candidate columns. It does not call `create_record` and does not allocate a record sequence. Commit validates again. If the form's current published version is no longer the version stored on the job, commit returns 409.

A valid row with no unresolved duplicate is created with `source=import`. An invalid row is rejected. `skip` skips the row. `reject` rejects it. A possible duplicate with no `accept_new` decision stays `awaiting_review` and is not created. One invalid row does not change the outcome of another row.

The job is `completed` only when every data row is accepted. Otherwise a finished commit is `partial`. Counts reconcile as:

`input_rows = accepted + rejected + skipped + awaiting_review + not_committed`

The header is excluded. Preview counts are stored separately as `preview_*` and are not the persisted accepted count.

## Duplicates

The PRD does not define one universal duplicate key, and email or mobile is not treated as unique. A possible match is a normalized email or mobile already present on an authorized record in the same project, or on another row in the same file. Name matching is not implemented. The candidate shows the record id, public number, display name, and a message. It does not show the other record's contact value. Records in another project or tenant are excluded.

The reviewer can accept the row as new, skip it, or reject it. An existing record is not overwritten.

## Idempotency

The job key is unique on tenant, project, and idempotency key. The same key, file hash, and form returns the existing job. A different file or form with that key returns 409. Commit reserves the record id on the import row before insert. A repeated commit of a finished job returns the stored summary. A concurrent commit shares that primary key. Exactly-once processing is not claimed for a future external side effect. The record insert is protected by the reserved id.

## Export

`GET /api/v1/tenants/{tenant}/projects/{project}/record-exports` uses the same search and filters as the record list: `q`, `form_id`, `source`, `created_from`, `created_to`, `sort`, and `direction`. The page window is ignored. Each row still passes `authorize_record`. More than 1,000 authorized rows returns 422 instead of a shortened file. Zero rows returns headers only.

With a form selected, columns are record metadata plus the current published field labels. Without a form, the file contains metadata only. Values that start with a formula prefix are written with a leading `'`.

## Authorization

Import and export use the existing project membership and record authorization. There is no new permission. The job creator, a project manager, or a tenant admin can read the job and the error report. Another member receives 404. An archived project can export and cannot import. Writes keep the existing CSRF check.

## Out of scope

Original roadmap Sprint 6, PDF export, a Google Sheets API, a background import worker, platform audit append, and reusable mapping templates.
