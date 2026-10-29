# CRM-S12 implementation report — original roadmap Sprint 10

Date: 21 October 2026. Repository: `aadi-crm` only.

Original roadmap Sprint 9 was technically closed first. Owner acceptance of Sprint 9 is still pending. See `docs/sprints/crm-s11/closure.md`. Original roadmap Sprint 6 stays Planned.

## What was built

A field dictionary for the four worksheets in `C:\Users\lenovo\Downloads\CRM.xlsx`, published through the existing form API for the three sheets whose headers describe their cells.

- Preschool, Space View, and Hiring each have their own project, form, and published version 1.
- Column mapping is per form. There is no shared column schema.
- The original workbook is not imported. A one-sheet CSV is prepared so the existing importer can read it. Dates, whole numbers, and numeric phones are normalized before upload. The importer still runs `validate_values`.
- Hiring formula cells A3:A14 are replaced by their cached integers. The formula is not evaluated again.
- Paneerwala is not published and not imported. The header row does not describe the cells.
- Reconciliation counts and key-field results are in `reconciliation-report.md`. The crosswalk is `crosswalk.json`.

No schema migration was added. Import idempotency, duplicate review, CSRF, project membership, and `authorize_record` are unchanged.

## Files

Sprint 10 is one unit: 16 new files and no modified product files. The Sprint 9 closure was a separate unit.

New:

- `backend/app/domain_templates.py`
- `backend/tests/test_domain_templates.py`
- `docs/sprints/crm-s12/scope-and-migration-plan.md`
- `docs/sprints/crm-s12/mappings/preschool-mapping.md`
- `docs/sprints/crm-s12/mappings/paneerwala-mapping.md`
- `docs/sprints/crm-s12/mappings/space-view-mapping.md`
- `docs/sprints/crm-s12/mappings/hiring-mapping.md`
- `docs/sprints/crm-s12/reconciliation-report.md`
- `docs/sprints/crm-s12/crosswalk.json`
- `docs/sprints/crm-s12/record-demo.mjs`
- `docs/sprints/crm-s12/recording.webm`
- `docs/sprints/crm-s12/explanation-script.md`
- `docs/sprints/crm-s12/implementation-report.md`
- `docs/sprints/crm-s12/technical-validation.md`
- `docs/sprints/crm-s12/technical-acceptance.md`
- `docs/sprints/crm-s12/operations.md`

Sprint 9 closure, separate unit:

- `docs/sprints/crm-s11/closure.md`
- `docs/sprints/crm-s11/technical-acceptance.md`

## Decisions left for the owner

- Paneerwala column alignment, including priority versus requirement type versus status.
- Whether follow-up comment columns should later become activity-log rows. They are stored as text so the source is not discarded.
- Whether numeric phone cells should stay as the workbook's exact integer. A trailing digit may already be missing in the file. It was not reconstructed.
- Whether `Student Strength` and `No of Branches` should remain numbers. Every source cell is blank.
- Owner sign-off of the three reconciled datasets. This report does not accept them.

## Confirmation

The Control Plane repository was not modified. The Control Plane process was started with a process environment variable for the CRM page origin. That value was not written into the Control Plane repository. No commit, push, merge, tag, or deployment was made.
