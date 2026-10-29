# Reconciliation report — original roadmap Sprint 10

Date: 21 October 2026. Repository: `aadi-crm` only.

The counts below come from `backend/tests/test_domain_templates.py` on a disposable SQLite file. The shared development database was not opened. The same test writes `docs/sprints/crm-s12/crosswalk.json`. That file has the source row, the numeric source identifier, the import job, the import row, the CRM record id, and the public number. It does not contain names, phone numbers, or email addresses.

The importer's count equation, confirmed on each job, is:

`submitted rows = accepted + rejected + skipped + awaiting review + not committed`

The header is not a submitted row. A data row is a worksheet row after row 1 with at least one non-blank cell. No such row was excluded before import.

The projects were empty before the import. No existing record was a duplicate candidate. The final target count is the accepted count. A second commit of the same job, and a second upload of the same file with the same idempotency key, did not add records.

Key-field comparison uses the accepted records only. A rejected row has no stored values to compare. Blank source cells are excluded from the match counts. `exact` means the stored value equals the source cell text. `normalized` means the stored value equals the documented conversion: Excel serial or `DD/MM/YYYY` to `YYYY-MM-DD`, `2.0` to `2`, numeric phone to its exact integer digits, dropdown label to its option value, or leading and trailing whitespace removed. A mismatch fails the test. There were none.

## Preschool

Source: `CRM.xlsx`, worksheet `Preschool`. Mapping `preschool-source-v1`.

| Count | Value |
|---|---|
| Source data rows | 4 |
| Excluded before import | 0 |
| Submitted | 4 |
| Accepted | 4 |
| Rejected | 0 |
| Skipped | 0 |
| Awaiting review | 0 |
| Not committed | 0 |
| Existing records matched | 0 |
| Target records | 4 |
| Unexplained difference | 0 |

Status: **PASS**.

| Field | Checked | Exact | Normalized | Missing | Mismatch |
|---|---|---|---|---|---|
| Lead ID | 4 | 0 | 4 | 0 | 0 |
| Inquiry Date | 4 | 0 | 4 | 0 | 0 |
| School Name | 4 | 4 | 0 | 0 | 0 |
| Mobile Number | 4 | 0 | 4 | 0 | 0 |
| Email ID | 1 | 1 | 0 | 0 | 0 |
| Follow-up Date | 4 | 0 | 4 | 0 | 0 |
| Connected | 4 | 4 | 0 | 0 | 0 |

The other mapped fields were also checked. Their blank, exact, and normalized counts are in `crosswalk.json`. Lead ID values are distinct. Duplicate review did not fire.

Rejected rows: none.

Recovery: the job key `preschool-source-v1` returns this job. A finished retry does not create the four records again. A different key would be a new import and is not used.

## Paneerwala

Source: `CRM.xlsx`, worksheet `Paneerwala`. No mapping version.

| Count | Value |
|---|---|
| Source data rows | 24 |
| Excluded before import | 24, because the sheet was not submitted |
| Submitted | 0 |
| Accepted | 0 |
| Rejected | 0 |
| Skipped | 0 |
| Awaiting review | 0 |
| Target records | 0 |

Status: **BLOCKED**.

The header row does not describe the cells. The finding is in `mappings/paneerwala-mapping.md`. There is no key-field comparison and no crosswalk. Do not rerun this sheet under a new idempotency key.

## Space View

Source: `CRM.xlsx`, worksheet `Space View`. Mapping `space-view-source-v1`.

| Count | Value |
|---|---|
| Source data rows | 12 |
| Excluded before import | 0 |
| Submitted | 12 |
| Accepted | 11 |
| Rejected | 1 |
| Skipped | 0 |
| Awaiting review | 0 |
| Not committed | 0 |
| Existing records matched | 0 |
| Target records | 11 |
| Unexplained difference | 0 |

Status: **PASS**.

The rejected row is source row 2. Its inquiry-date serial is outside 1–60000. The error report line is `2,inquiry_date,INQUIRY DATE must use YYYY-MM-DD.` The row was not dropped before import and was not given a guessed date.

| Field | Checked | Exact | Normalized | Missing | Mismatch |
|---|---|---|---|---|---|
| SR.NO | 11 | 0 | 11 | 0 | 0 |
| INQUIRY DATE | 11 | 0 | 11 | 0 | 0 |
| NAME | 11 | 11 | 0 | 0 | 0 |
| CONTACT NO. | 11 | 0 | 11 | 0 | 0 |
| LEAD SOURCE | 11 | 10 | 1 | 0 | 0 |
| PRIORITY | 6 | 6 | 0 | 0 | 0 |

`SR.NO` 24 and `SR.NO` 25 each occur twice among the accepted records. Both copies were kept. The rejected row is not one of those pairs. Contact numbers match the exact integers stored in the workbook. They may already differ from a number that the spreadsheet rounded. That is a source-file limit, not a difference between the file and the CRM record.

Recovery: the same job key returns the partial result. The accepted rows stay accepted. The rejected row stays rejected unless the source cell becomes a valid date and the same job is committed again. Starting a new key would risk a second copy of the 11 accepted rows, so that is not the recovery path.

## Hiring

Source: `CRM.xlsx`, worksheet `Hiring`. Mapping `hiring-source-v1`.

| Count | Value |
|---|---|
| Source data rows | 13 |
| Excluded before import | 0 |
| Submitted | 13 |
| Accepted | 13 |
| Rejected | 0 |
| Skipped | 0 |
| Awaiting review | 0 |
| Not committed | 0 |
| Existing records matched | 0 |
| Target records | 13 |
| Unexplained difference | 0 |

Status: **PASS**.

| Field | Checked | Exact | Normalized | Missing | Mismatch |
|---|---|---|---|---|---|
| Lead ID | 13 | 12 | 1 | 0 | 0 |
| Contact Person | 13 | 13 | 0 | 0 | 0 |
| Position | 13 | 0 | 13 | 0 | 0 |
| Mobile No | 13 | 0 | 13 | 0 | 0 |
| Prority | 13 | 13 | 0 | 0 | 0 |
| Call Status | 13 | 13 | 0 | 0 | 0 |
| Final Status | 12 | 0 | 12 | 0 | 0 |
| Closed Date | 12 | 0 | 12 | 0 | 0 |

The one normalized lead id is the plain cell `1.0`. The other 12 are the cached formula integers, stored exactly. Position and final status match by option label, and the record stores the option value. One row has no final status and no closed date. Lead ID values are distinct. Mobiles are distinct after conversion.

Recovery: the job key `hiring-source-v1` returns this completed job and does not create the 13 records again.

## Not claimed

Paneerwala is not reconciled. Follow-up text is reconciled on the record, not as activity-log rows. Phone numbers that were numeric cells are reconciled to the file's integer, not to a recovered original. Owner sign-off is still required.
