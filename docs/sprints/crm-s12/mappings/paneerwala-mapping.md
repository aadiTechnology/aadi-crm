# Paneerwala mapping — original roadmap Sprint 10

Status: **DEFERRED**. The product owner deferred Paneerwala. It does not block closure of Preschool, Space View, and Hiring. No mapping version is approved. No form is published. No row is imported. The column mismatch below is unchanged.

Source file: `C:\Users\lenovo\Downloads\CRM.xlsx`, worksheet `Paneerwala`. Header row 1. Data rows 2–25 (24 rows). No blank data rows, merges, or formulas. Columns AA–AD have blank headers. The importer rejects a blank header and a repeated header.

## What was counted

| Check | Count |
|---|---|
| Data rows | 24 |
| Column A values that are enquiry timestamps | 24 |
| Column A values that are numeric lead ids | 0 |
| Column D shared-text values that are not dates | 24 |
| Column E numeric values | 24 |
| Non-blank cells in columns S–Z (order, payment, product, quantity, amount, remarks) | 0 |

The header calls column A `Lead ID`, column D `Date`, and column E `Name`. The cells do not match those names: column A is a timestamp, column D is text that is not a date, and column E is a number in the phone-number range.

## Why a shift was not applied

Moving every value one column to the right would line the timestamp up with `Enquiry received`, the date with `Date`, the text with `Name`, and the number with `Phone`. It would also put Warm/Hot under the header `Warm`, and Followup / Converted / Not interested / Not connected under the header `Converted`.

That second pair is not a reliable reading. The PRD says Paneerwala priority must be its own field and must not be stored as requirement type. The headers `Warm` and `Converted` look like sample values used as column titles. Applying the shift would still choose a meaning for those columns.

Duplicate headers `Next Follow-up` (M, O, Q) and `Call Summary Follow up b` (N, P, R) would also have to be renamed before import. Most of those cells are blank. The order columns S–Z are blank on every row, so they cannot confirm a product, quantity, amount, or payment mapping.

## Decision required

Confirm which header belongs to which column, including priority versus requirement type versus status. Until that confirmation, Paneerwala stays out of the catalog and out of the import.

No source cell from this sheet is copied into a CRM record or into the browser recording.
