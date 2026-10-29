# Preschool mapping — original roadmap Sprint 10

Mapping version: `preschool-source-v1`.

Source file: `C:\Users\lenovo\Downloads\CRM.xlsx`, worksheet `Preschool`. Header row 1. Data rows 2–5 (4 rows). No blank data rows, merges, or formulas. The workbook has four worksheets, so it is not uploaded directly. The import file is a one-sheet CSV named `preschool.csv`.

Duplicate header `Followup Comments` appears in columns S and T, including the trailing space. The importer strips headers and then rejects the repeated name. The CSV renames them `Followup Comments 1` and `Followup Comments 2`. Both columns are mapped. Nothing is dropped.

Headers with a trailing space (`Website `, `Selling Point `) are stripped only in the CSV header. The cell text is unchanged except for the rules below.

## Rules

- A whole-number cell such as `2.0` is written as the integer text `2`. The CRM field type is number.
- An Excel serial with a `.0` suffix is not a date to the importer. Serials from 1 through 60000 become `YYYY-MM-DD` with the same epoch the importer uses for an integer serial (`1899-12-30` plus the serial). `46362` is `2026-12-06`.
- A text date `DD/MM/YYYY` becomes `YYYY-MM-DD`. Every follow-up date in this sheet is `21/07/2026`, which cannot be month-first.
- Mobile text is left for the importer, which removes spaces, parentheses, hyphens, and dots before the 8-to-15 digit check.
- Email is lower-cased by the importer. URL text must already start with `http://` or `https://`.
- Text is stored after the validator strips the ends. A difference that is only leading or trailing whitespace is a normalized match.
- Blank optional cells are omitted. They are not filled with a default.
- Email and mobile are possible duplicate matches in the same project. They are not unique keys. This sheet has no repeated mobile or email after normalization.

`Student Strength` and `No of Branches` are numbers because the PRD lists them as counts. Every source cell is blank, so the type is not confirmed by a value. A non-numeric value will be rejected.

`Lead Source` and `Priority` stay text. The PRD starter lists are not applied. This sheet has no lead-source values, and the only priority text is the single observed value. Forcing the starter list would invent a closed set.

## Columns

| Column | Source header | CRM field | Type | Required | Rule |
|---|---|---|---|---|---|
| A | Lead ID | `lead_id` | number | Yes | Whole number. Source identifier, not the project record number. |
| B | Inquiry Date | `inquiry_date` | date | No | Excel serial to ISO. |
| C | School Name | `school_name` | text | Yes | Record title. |
| D | Contact Person | `contact_person` | text | No | Text. |
| E | Mobile Number | `mobile_number` | mobile | No | Importer digit normalization. |
| F | Email ID | `email` | email | No | Format check. |
| G | Website | `website` | url | No | Must start with http or https. |
| H | City | `city` | text | No | Text. |
| I | Selling Point | `selling_point` | long text | No | Text. |
| J | Lead Source | `lead_source` | text | No | Original text. All four cells are blank. |
| K | Interested Product | `interested_product` | text | No | All four cells are blank. |
| L | Requirement Details | `requirement_details` | long text | No | All four cells are blank. |
| M | Student Strength | `student_strength` | number | No | All four cells are blank. |
| N | No of Branches | `branch_count` | number | No | All four cells are blank. |
| O | Priority | `priority` | text | No | Original text. |
| P | Follow-up Date | `follow_up_date` | date | No | `DD/MM/YYYY` to ISO. |
| Q | Connected | `connected` | text | No | Not a boolean. |
| R | Discussion Summary | `discussion_summary` | long text | No | Text. |
| S | Followup Comments | `followup_comments_1` | long text | No | First of the two repeated headers. |
| T | Followup Comments | `followup_comments_2` | long text | No | Second of the two repeated headers. |

Follow-up comments stay on the record. They are not split into activity-log rows. The PRD prefers an activity log, and these cells do not contain a separate owner or a reliable due time.

## Validation outcome

All 4 submitted rows pass validation. None are duplicates of each other. See the reconciliation report.
