# Original Roadmap Sprint 10 — Templates and Data Migration

Date: 21 October 2026. Repository: `aadi-crm` only.

`docs/sprints/crm-s12` is the evidence folder for original roadmap Sprint 10. It is not original roadmap Sprint 12. `docs/sprints/crm-s10` remains the evidence folder for original Sprint 8. `docs/sprints/crm-s11` remains the evidence folder for original Sprint 9.

Original roadmap Sprint 9 was technically closed before this work. Owner acceptance of Sprint 9 is still pending. See `docs/sprints/crm-s11/closure.md`. Original roadmap Sprint 6 stays Planned.

## Goal

Configure a published form for each business worksheet that can be mapped safely, import those rows through the existing import workflow, and reconcile the result. Do not invent a second validator or a global column list.

## Sources read

- PRD v1.0, `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`, sections 3.1, 7.9, 8.2, 8.3, and 8.4, and decision DEC-06.
- Original plan row 10 in `C:\Users\lenovo\Downloads\Aadi_CRM_Complete_Sprint_Plan.xlsx`: configure Preschool, Paneerwala, Space View, and Hiring; map the source spreadsheets; reconcile counts and key fields. No invented mappings and no silent row drops.
- The workbook attached for this run: `C:\Users\lenovo\Downloads\CRM.xlsx`.

The PRD is not in this repository. The workbook is not copied into this repository because it contains personal and customer details.

## What the workbook contains

One file, four visible worksheets, no merged cells. The header is row 1. A data row is any later row with at least one non-blank cell. There are no blank data rows.

| Worksheet | Header row | Data rows | Columns | Notes |
|---|---|---|---|---|
| Preschool | 1 | 4 | 20 | Duplicate header `Followup Comments` in columns S and T. Some headers have a trailing space. Inquiry dates are Excel serials stored as `46362.0`. Follow-up dates are text `DD/MM/YYYY`. No formulas. |
| Paneerwala | 1 | 24 | 30 | Headers do not describe the cells in the same columns. Duplicate headers. Four blank header cells. No formulas. |
| Space View | 1 | 12 | 14 | Unique headers. One inquiry-date serial is outside the importer's date window. `SR.NO` 24 and 25 each appear twice. No formulas. |
| Hiring | 1 | 13 | 13 | Lead ID cells A3:A14 are one shared formula with cached integers 2 through 13. The header `Prority` is spelled that way. No merged cells. |

The existing importer rejects a workbook with more than one worksheet, a repeated header, a blank header, and an XLSX formula cell. `CRM.xlsx` cannot be uploaded as it is. Each publishable sheet is prepared as its own CSV. The preparation rules are in the mapping documents. The importer still validates every row.

## Tenant and project

The workbook does not name a tenant. PRD section 3.1 treats Preschool, Paneerwala, Space View, and Hiring as separate projects inside one tenant. Aadi Technology is the internal tenant in that section. This migration does not put the four sheets in one project.

The automated migration uses the disposable test tenant already used by the CRM tests, with one project per publishable template. It does not open `backend/data/aadi_crm.sqlite`. The browser demonstration uses the existing Bootstrap recording organization and synthetic rows only.

## Templates

| Template | Published | Reason |
|---|---|---|
| Preschool | Yes | Headers match the cells. Follow-up comments stay on the record as text. |
| Paneerwala | No | Column alignment is unresolved. See the Paneerwala mapping. |
| Space View | Yes | Headers match the cells. Original casing is stored as entered. |
| Hiring | Yes | Headers match the cells. Position and final status use the PRD options that the source actually contains. |

Project status workflow, assignment, and duplicate detection from original Sprint 6 are not implemented here. Source status text is a form field. Email and mobile remain possible matches, not unique keys.

Follow-up columns are not turned into activity-log rows. The cells are unstructured comments, and inventing an owner or a due time would be a new business rule. The text is preserved on the record and reconciled there.

## Out of scope

A resume file field, a Paneerwala import, an update-in-place import, a change to import coercion, a schema migration, and any Control Plane change.
