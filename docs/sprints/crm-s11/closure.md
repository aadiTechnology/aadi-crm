# CRM-S11 closure — original roadmap Sprint 9

Date: 21 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made for this review.

`docs/sprints/crm-s11` is the evidence folder for original roadmap Sprint 9, CSV and XLSX import and export. It is not original roadmap Sprint 11. Original roadmap Sprint 6 stays Planned.

## Decision

**CLOSED** against the technical checks below. Owner review of this closure is still required. This document does not accept the work on the owner's behalf.

No Sprint 9 product code was changed by this review. The previously reported test counts were not reused. The suites were run again on the current tree at `4438f73`.

## Review

The import routes, import store, spreadsheet reader, migration `008_imports.sql`, import tests, and the Sprint 9 documents were read against the current code.

- Upload rejects a non CSV/XLSX file, an empty file, a second worksheet, a blank header, a repeated header, and files over 1 MiB, 500 data rows, 40 columns, or 5,000 characters in one cell. Rows over the limit are rejected rather than truncated.
- Preview calls `validate_values` and does not call `create_record`. Commit calls `validate_values` again.
- Duplicate candidates come from the same project. The candidate payload does not include the other record's contact value. Another project with the same email is not shown.
- The job key is unique on tenant, project, and idempotency key. A completed job returns its stored summary. A repeated commit does not insert the reserved record again.
- Persisted counts use `input_rows = accepted + rejected + skipped + awaiting_review + not_committed`. The header is not a data row.
- Error report and job reads return 404 for a project member who did not create the job, and for another tenant. A write without the CSRF header returns 401.
- Export uses the record-list filters and `authorize_record`. Formula-like values are prefixed on the way out. An XLSX formula cell in an upload is not evaluated.

Sampled frames from `docs/sprints/crm-s11/recording.webm` were extracted with ffmpeg. This was not continuous playback. ffprobe reports VP9, 1280×720, 102.44 seconds, 8,660,995 bytes. The frames that were inspected show:

- Bootstrap recording 1792111368748 signed in as `playwright-recording@example.com`.
- Import with `notes.txt` selected and the message `Upload a .csv or .xlsx file.`
- Mapping for Import capture: School name required, Email, and Notes left unmapped, with the sentence that unmapped columns stay on the import.
- Preview rows for `=Existing lane`, a missing school name, an invalid email, and `=Fresh lane`, including "Possible match on Email with IMP486934-0001" and Skip on row 2.
- Record list for Import gate IMP486934 with the search `=Fresh` and Export CSV / Export XLSX. The result row was still loading in the frame that was captured.
- A later frame that says "Checking access".

The sampled frames do not show the partial-completion sentence, the open error-report file, the finished export-count sentence, the imported record row, the 390-pixel layout, or the member-denial sentence. The explanation script already says those sentences are brief or off the sampled frames. Those checks remain in `frontend/tests/imports.test.tsx` and `backend/tests/test_imports.py`.

## Acceptance checks

| Check | Status | Evidence |
|---|---|---|
| CSV/XLSX format, size, and row/column limits | PASS | `read_table` limits and `test_csv_and_xlsx_parse_limits_and_formula_cells`. The recording shows the `notes.txt` rejection |
| Mapping follows the selected published form | PASS | Mapping is stored on the job and checked against that form version. The recording shows Import capture version fields |
| Preview and dry-run create no records | PASS | `preview_job` does not call `create_record`. `test_preview_does_not_create_records_and_commit_reconciles` |
| Row validation uses the existing rules | PASS | Commit and preview call `validate_values` |
| Duplicate review hides other tenants and other projects | PASS | `test_authorization_duplicate_visibility_and_export_filters` |
| The same logical import is idempotent | PASS | Unique `(tenant_id, project_id, idempotency_key)`. A different file with that key returns 409 |
| A completed retry returns the stored result | PASS | `commit_job` returns the stored job when status is `completed` and does not insert again. A `partial` job can be committed again; already accepted rows stay accepted |
| Accepted, rejected, and skipped counts reconcile | PASS | `input_rows = accepted + rejected + skipped + awaiting_review + not_committed` |
| Error reports are authorized and row-level | PASS | Job owner, project manager, or tenant admin. Another member receives 404. The report lists row, field, and message |
| Filtered CSV/XLSX export matches the authorized rows | PASS | Same filters as the record list, then `authorize_record`. More than 1,000 authorized rows returns 422 |
| Formula-injection mitigation | PASS | XLSX formula cells are rejected and not evaluated. Export prefixes `=`, `+`, `-`, `@`, tab, and carriage return |
| Project membership, `authorize_record`, tenant isolation, and CSRF | PASS | Existing project and record checks. Missing CSRF header returns 401. Cross-tenant import returns 404 |
| Migration `008_imports.sql` | PASS | Additive tables and indexes. No `DROP` or `DELETE`. Pytest applies it on a disposable database |
| Documents agree | PASS | Scope, report, validation, operations, and the explanation script match the code and the sampled frames, including the limits below |
| Documented limits match the code | PASS | 1 MiB, 500 data rows, 40 columns, 5,000 characters, 1,000 export rows. Header excluded. Email and mobile are possible matches, not a uniqueness rule |

No material Sprint 9 defect was found. Exactly-once behavior is not claimed for a second idempotency key or for a future external side effect.

## Commands on this review

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**61 passed**, 1 Starlette `httpx` deprecation warning, in 22.86 seconds.

Frontend, from `frontend`:

`npm test`

**48 passed** (8 files) in 12.57 seconds. jsdom printed `Not implemented: navigation to another Document` in the import download test. The tests still passed.

`npx vite build`

Succeeded in 2.13 seconds. Assets: `dist/assets/index-XPNS2jy0.css` (15.20 kB) and `dist/assets/index-C9mEIzZT.js` (430.47 kB).

`npx tsc --noEmit`

Exited 2. This is not a pass. The errors are the existing baseline:

- `frontend/src/lib/config.ts` TS2559
- `frontend/tests/form-versions.test.tsx` TS2769
- `frontend/vite.config.ts` TS2307 and TS2339

Import sources are not in that list.

## Limitations that remain

- Email and mobile are possible matches in the same project. They are not a uniqueness rule. Name matching is not implemented.
- There is no update-in-place import. A different idempotency key can import the same file again.
- Saved mapping templates, PDF export, Google API access, and a background worker are not included.
- `file` and `auto_number` values cannot be imported.
- The recording review used sampled frames, not continuous playback.

## Confirmation

No commit, push, merge, tag, or deployment was performed. The Control Plane repository was not modified. Original roadmap Sprint 6 was not started.
