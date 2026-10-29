# CRM-S12 operations — original roadmap Sprint 10

Date: 21 October 2026. Repository: `aadi-crm` only.

No schema migration was added. Sprint 9 migration `008_imports.sql` is the import store. Apply the existing CRM migrations on a disposable database. Do not reset `backend/data/aadi_crm.sqlite`.

## Source

The operator workbook is `C:\Users\lenovo\Downloads\CRM.xlsx`. It is not in this repository. It has four worksheets. Upload each publishable sheet only after `prepare_import` has written a one-sheet CSV. Do not upload the original workbook. The importer rejects the extra sheets, the repeated Preschool header, the blank Paneerwala headers, and the Hiring formula cells.

## Publish a template

`backend/app/domain_templates.py` is the field dictionary. Preschool, Space View, and Hiring are publishable. Paneerwala is not.

Create one project per template. Create the form with that template's name, description, and fields, in that order, through the form API. Publish version 1. Do not edit the published version. A later field change is a new draft and a new publish, and an import job bound to the old version will not commit after that publish.

The automated path is `backend/tests/test_domain_templates.py`. It uses a temporary database.

## Import

Use the existing import screen or API.

1. Choose the published form and the prepared CSV.
2. Map every derived header to the field key in the mapping document. Leave nothing unmapped for these three files. The derived headers match the field labels, so the screen's suggestion matches them.
3. Preview. That dry-run creates no records.
4. For a possible email or mobile match, choose Accept as new, Skip, or Reject. No choice leaves the row awaiting review. These three source files had no such match.
5. Import records. Invalid rows are rejected and listed in the error report.
6. Repeat the same import key to confirm the accepted count does not grow.

Idempotency keys for this workbook:

| Template | Key |
|---|---|
| Preschool | `preschool-source-v1` |
| Space View | `space-view-source-v1` |
| Hiring | `hiring-source-v1` |

A different key is a new logical import. Do not use a new key to reprocess a partial file. Commit the same job again. Accepted rows stay accepted.

## Paneerwala

Stop. Do not publish a form and do not import the sheet until the owner confirms which header belongs to which column. The block is in `mappings/paneerwala-mapping.md`.

## Recovery

- Completed job: another commit returns the stored summary.
- Partial job, Space View: source row 2 stays rejected until its inquiry date is a real date. The other 11 rows are already records.
- Formula cells: if the Hiring cache is wrong, replace the cached lead ids in a new file only after the owner accepts that the old job must not be repeated under a new key without a reviewed duplicate decision.
- Dropping import tables is not the recovery path. The migration runner refuses `DROP` and `DELETE`. Records already created would remain.

## Browser demonstration

The recording uses synthetic rows in the Bootstrap recording organization. It does not upload `CRM.xlsx`. Projects created for that recording stay in that organization. They were not deleted.

## Crosswalk

`docs/sprints/crm-s12/crosswalk.json` is rewritten when the domain-template test runs. An authorized operator can join `source_row` and `source_identifier` to the import job and the CRM record id. The file is tenant-scoped to the disposable test tenant, not to the recording organization.
