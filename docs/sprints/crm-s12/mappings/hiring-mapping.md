# Hiring mapping — original roadmap Sprint 10

Mapping version: `hiring-source-v1`.

Source file: `C:\Users\lenovo\Downloads\CRM.xlsx`, worksheet `Hiring`. Header row 1. Data rows 2–14 (13 rows). No blank data rows or merges. The import file is a one-sheet CSV named `hiring.csv`.

Lead ID cell A2 is the number 1, stored as `1.0`. Cells A3:A14 are one shared formula. A3 contains `A2+1`. A4:A14 continue that shared formula. The cached values are the integers 2 through 13. The importer rejects a formula cell and would store it as empty, which would fail the required lead id. The CSV contains those cached integers and no formula. The sequence was not recalculated.

There is no email column and no resume column. A file field was not added, because a file value cannot be imported and the source has no file. Candidate email and mobile are not treated as unique. The 13 mobiles are distinct after the numeric conversion.

## Rules

Dates, whole numbers, mobiles, and text follow the Preschool rules. Position and final status are dropdowns. The importer stores the option value when the cell text equals the option label.

Position options are the four labels present on every row and named in the PRD: Sales Resource, Accountant, Accounting & Sales, Interior Designer.

Final status options are the PRD pair Accepted and Closed. One source row has this cell blank. The field is optional.

`Prority` keeps the source spelling as the field key and the label. The values stay text. They are Hot, Warm, and Cold in the source, and they are not forced into a picklist.

`Call Status` stays text. The source includes `From us not valid`, which is not one of the PRD starter values Connected, Busy, Not connected, Switched off, and Not valid. It is not rewritten.

`Lead Source` stays the original text. It is not rewritten from `Through Meta Add` to `Meta Ad`.

## Columns

| Column | Source header | CRM field | Type | Required | Rule |
|---|---|---|---|---|---|
| A | Lead ID | `lead_id` | number | Yes | `1.0` becomes 1. Formula cells use the cached integer. Not a unique-key rule beyond this file, where the 13 values are distinct. |
| B | Contact Person | `contact_person` | text | Yes | Record title. |
| C | Position | `position` | dropdown | Yes | Label mapped to the option value. |
| D | Mobile No | `mobile_no` | mobile | No | Exact integer from the numeric cell. |
| E | Location | `location` | text | No | Text, including a hyphen placeholder where the source has one. |
| F | Lead Source | `lead_source` | text | No | Original text. |
| G | Prority | `prority` | text | No | Source spelling kept. |
| H | Call Status | `call_status` | text | No | Original text. |
| I | Discussion Summary - 1 | `discussion_summary_1` | long text | No | Text. |
| J | Followup Comments - 2 | `followup_comments_2` | long text | No | Text. |
| K | Followup Comments - 3 | `followup_comments_3` | long text | No | Text. |
| L | Final Status | `final_status` | dropdown | No | Accepted or Closed. One blank. |
| M | Closed Date | `closed_date` | date | No | Excel serial to ISO. One blank, on the same row as the blank final status. |

Follow-up comments stay on the record. They are not activity-log rows.

Mobile numbers are the exact integers in the workbook. A trailing digit can already be missing. It is not reconstructed.

## Validation outcome

All 13 submitted rows pass validation. None are duplicate candidates. See the reconciliation report.
