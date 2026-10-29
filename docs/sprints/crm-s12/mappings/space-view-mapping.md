# Space View mapping — original roadmap Sprint 10

Mapping version: `space-view-source-v1`.

Source file: `C:\Users\lenovo\Downloads\CRM.xlsx`, worksheet `Space View`. Header row 1. Data rows 2–13 (12 rows). No blank data rows, merges, duplicate headers, or formulas. The import file is a one-sheet CSV named `space_view.csv`.

`SR.NO` is not unique. The values 24 and 25 each appear on two rows. Both rows are imported. The number is not a duplicate key. Duplicate review remains email and mobile only, and this sheet has no email column and no repeated mobile after normalization.

The PRD asks Space View to normalize casing in display while preserving the original imported value. This CRM stores one value per field. The original text is stored, including uppercase source and priority. A second normalized copy was not added.

## Rules

The date, number, mobile, and text rules are the same as the Preschool mapping. A serial outside 1–60000 is left as the original cell text so the date field rejects that row. It is not converted to a guessed date and it is not removed before import.

`FOLLOW UP 3` and `FOLLOW UP 4` contain notes, not dates. They are long text. Dates written inside those notes are not parsed.

`REQUIRMENT DETAILS` keeps the source spelling as the field label.

## Columns

| Column | Source header | CRM field | Type | Required | Rule |
|---|---|---|---|---|---|
| A | SR.NO | `sr_no` | number | Yes | Whole number. Not unique. |
| B | INQUIRY DATE | `inquiry_date` | date | No | Serial to ISO, or reject when the serial is out of range. |
| C | NAME | `name` | text | Yes | Record title. Original casing. |
| D | CONTACT NO. | `contact_no` | mobile | No | Exact integer from a numeric cell, then the digit check. |
| E | LOCATION | `location` | text | No | Text. |
| F | REQUIRMENT DETAILS | `requirement_details` | long text | No | Source spelling kept. |
| G | LEAD SOURCE | `lead_source` | text | No | Original text. Not rewritten to the starter picklist. |
| H | PRIORITY | `priority` | text | No | Original casing. |
| I | Follow Up date 1 | `follow_up_date_1` | date | No | Serial to ISO. |
| J | FOLLOW UP 1 - Details | `follow_up_1_details` | long text | No | Text. |
| K | Follow Up date 2 | `follow_up_date_2` | date | No | Serial to ISO. |
| L | FOLLOW UP 2 - Details | `follow_up_2_details` | long text | No | Text. |
| M | FOLLOW UP 3 | `follow_up_3` | long text | No | Notes, not a date. |
| N | FOLLOW UP 4 | `follow_up_4` | long text | No | Present and blank on every row. Kept so the column is not discarded. |

Contact numbers in this sheet are numeric cells. The imported value is the exact integer stored in the workbook. A trailing digit can already be missing in that file. It is not reconstructed.

## Validation outcome

12 rows are submitted. Source row 2 is rejected because its inquiry-date serial is outside 1–60000. The other 11 rows are accepted. See the reconciliation report.
