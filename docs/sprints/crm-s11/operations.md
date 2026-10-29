# CRM-S11 operations

Date: 20 October 2026. Original roadmap Sprint 9. Repository: `aadi-crm` only.

## Migration

`backend/migrations/007_reminders.sql` must already be applied. The CRM process applies `008_imports.sql` on startup through the existing migration runner. The script creates `import_jobs` and `import_rows` and their indexes. It does not drop a table or delete rows.

The shared development database at `backend/data/aadi_crm.sqlite` already has this migration. It was not reset. Automated tests use a disposable database through `CRM_DATABASE_PATH`.

Rollback is not a downward migration. The runner refuses `DROP` and `DELETE`. Leaving the tables in place is the recovery path. Dropping them outside the runner would remove import history and would not remove CRM records already created from an accepted row.

## Limits

| Limit | Value | Behavior when exceeded |
|---|---|---|
| File size | 1 MiB | The upload is rejected |
| Data rows | 500 | The file is rejected. Rows are not truncated |
| Columns | 40 | The file is rejected |
| Cell length | 5,000 characters | The file is rejected |
| Export rows | 1,000 authorized rows | The request returns 422. A shortened file is not returned |

The header is not a data row. These limits keep the request in memory. There is no background import or export worker.

## How to import

1. Open Import for an active project that has a published form.
2. Choose the form and a `.csv` or `.xlsx` file. Google Sheets are used only after they are exported to one of those files. A workbook with more than one worksheet is rejected.
3. Map every column. Leave a column on Unmapped when its values must stay out of the record. Save mapping.
4. Preview. That dry-run does not create records.
5. For a possible email or mobile match, choose Accept as new, Skip, or Reject. No choice leaves the row awaiting review.
6. Import records. Valid rows are created. Invalid rows are rejected. The summary counts come from the saved job.
7. Download the error report. Repeat this import returns the same job result and does not create the accepted records again.

Email is compared after case folding. Mobile is compared after spaces, parentheses, and hyphens are removed. A leading `+` is kept. There is no default country code and no name match. An existing record is not updated.

`file` and `auto_number` fields cannot be imported. A required field of either type makes the row fail validation.

## How to export

On the record list, set the search and filters and choose Export CSV or Export XLSX. The file uses the submitted filters, not the current page. The status line compares the exported data-row count with the list total.

The same export actions are on the import page for the selected form and search box.

## Recovery

A finished job returns its stored summary when Import records or Repeat this import is used again. If commit stops before every row is decided, run commit again. Rows already accepted stay accepted. Rows that were invalid are validated again and do not become accepted unless they pass. Mapping cannot change after an accepted row exists.

If the published form version changes after the job is created, commit fails with 409. Start a new import for the new version.

## Demo data left in place

The browser capture created projects in organization Bootstrap recording `1792111368748` (`e02812a0-8717-4f5f-be19-57f263daef52`). Earlier projects and records were not deleted. No production customer data was used.

| Project | What remains |
|---|---|
| Import gate IMP483891 | Draft form Import capture. Not published |
| Import gate IMP713107 | Published Import capture version 1. No records |
| Import gate IMP838710 | Published Import capture version 1. No records |
| Import gate IMP135854 | Published form and manual record IMP135854-0001, Existing lane |
| Import gate IMP220385 | IMP220385-0001 Existing lane (manual) and IMP220385-0002 `=Fresh lane` (import). One partial import job |
| Import gate IMP444342 | Published Import capture version 1. No records |
| Import gate IMP486934 | Recording project. IMP486934-0001 Existing lane (manual) and IMP486934-0002 `=Fresh lane` (import). One partial import job: accepted 1, rejected 1, skipped 1, input rows 3 |

Both saved jobs have status `partial` and the same counts. Addresses used were `demo.import@example.com` and `fresh.import@example.com`.
