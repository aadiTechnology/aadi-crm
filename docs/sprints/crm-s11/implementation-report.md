# CRM-S11 implementation report — original roadmap Sprint 9

Date: 20 October 2026. Repository: `aadi-crm` only.

Original roadmap Sprint 8 was technically closed before this work. Owner acceptance of Sprint 8 is still pending. See `docs/sprints/crm-s10/closure.md`.

## What was built

CSV and XLSX import and filtered export for a published form.

- Upload checks the extension, the file bytes, size, headers, and row count. Formula cells in XLSX are rejected. Tenant, project, and user are not read from the file.
- Column mapping is explicit. Unmapped columns stay on the import row.
- Preview is a dry-run. Commit validates again and creates only the rows that are valid and resolved.
- Duplicate review offers accept as new, skip, or reject for a possible email or mobile match in the same project. Existing records are not overwritten.
- The job key and a reserved record id stop a retry from creating the same record again.
- The summary and the error report are stored with the job.
- Export uses the record-list filters and `authorize_record`. Formula-like values are prefixed on the way out.

The plan is `scope-and-implementation-plan.md`. Operating limits are in `operations.md`.

## Files

Sprint 9 stayed in one unit: 15 new files and 8 modified files.

New:

- `backend/migrations/008_imports.sql`
- `backend/app/spreadsheets.py`
- `backend/app/imports_store.py`
- `backend/app/api/imports.py`
- `backend/tests/test_imports.py`
- `frontend/src/features/imports/ImportsPanel.tsx`
- `frontend/tests/imports.test.tsx`
- `docs/sprints/crm-s11/scope-and-implementation-plan.md`
- `docs/sprints/crm-s11/record-demo.mjs`
- `docs/sprints/crm-s11/recording.webm`
- `docs/sprints/crm-s11/explanation-script.md`
- `docs/sprints/crm-s11/implementation-report.md`
- `docs/sprints/crm-s11/technical-validation.md`
- `docs/sprints/crm-s11/technical-acceptance.md`
- `docs/sprints/crm-s11/operations.md`

Modified:

- `backend/app/records_store.py` — `create_record` accepts a reserved `record_id`
- `backend/app/main.py` — import routes and the export-count response header
- `backend/tests/test_projects.py` — migration `008` and the empty import tables
- `frontend/src/services/platform.ts` — import and export client
- `frontend/src/main.tsx` — import routes
- `frontend/src/features/shell/CrmShellPage.tsx` — Import navigation
- `frontend/src/features/records/RecordsPanel.tsx` — filtered export actions
- `frontend/src/styles.css` — import form layout

Sprint 8 closure was a separate unit: new `docs/sprints/crm-s10/closure.md` and an update to `docs/sprints/crm-s10/technical-acceptance.md`. No Sprint 8 product code changed.

## Decisions that stay unresolved as product rules

- Email and mobile are possible matches, not a uniqueness rule. Name matching is not implemented.
- There is no update-in-place import.
- A different idempotency key can import the same file again.
- Saved mapping templates are deferred.
- Import and export do not append to the platform audit log.
- `file` and `auto_number` values cannot be imported.

## Confirmation

The Control Plane repository was not modified. No commit, push, merge, tag, or deployment was made.
