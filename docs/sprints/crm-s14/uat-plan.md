# UAT plan — original roadmap Sprint 12

Date: 21 October 2026. Use the synthetic recording organization only if the owner has already approved that account. Do not use a customer extract. Do not reset the database.

Automated tests are not this plan. Results of what was actually done are in `uat-results.md`.

## Platform or tenant administrator

Preconditions: an account with CRM product access and only the administration permissions the owner expects. A second tenant exists.

| ID | Steps | Expected |
|---|---|---|
| UAT-A1 | Sign in and open the authorized organization | The shell shows that organization. The other tenant's name is not shown |
| UAT-A2 | Open projects, members, and branding or configuration if the account is allowed to | Only the permitted controls are available |
| UAT-A3 | Open a project the account does not administer, and open audit without `audit.read` if that is the account's state | The denial message is shown and no foreign record text is shown |

## Project manager

Preconditions: active `project_manager` on one project, a published form, and CRM module access.

| ID | Steps | Expected |
|---|---|---|
| UAT-M1 | Open the project, edit a non-destructive field only if the owner allows, or otherwise open the detail | The project loads. Another project's records are not listed |
| UAT-M2 | Open the form, confirm the published version, and render it | The rendered form is the published snapshot |
| UAT-M3 | Create a synthetic record, then archive it only if the owner allows a new row | The record number is in that project. The archived row leaves the active list |
| UAT-M4 | Add a follow-up and confirm it appears in one queue | The same follow-up is not in a second queue |
| UAT-M5 | Open reminders and, if a failure exists, the failure list | The inbox is the caller's. The failure list is limited to managed projects |
| UAT-M6 | Import a small synthetic CSV, preview, and open the error report | Preview creates no record. The error report is available to this manager |
| UAT-M7 | Export the filtered list | The export row count matches the list |
| UAT-M8 | Open KPIs and audit | KPI counts match the list and queues. Audit is denied or empty according to `audit.read`, and it states that CRM actions are not copied into that log |

## Project member

Preconditions: active `project_member` on one project. One record is assigned to them and one is not.

| ID | Steps | Expected |
|---|---|---|
| UAT-P1 | Open the record list and a follow-up queue | Only assigned records and the member's own follow-ups on those records appear |
| UAT-P2 | Open the other record by URL, and open another member's import job | Both are denied and the body does not include the hidden values |
| UAT-P3 | Open reminders, KPIs, export, and audit | Reminder rows do not reveal an unauthorized record. KPIs and export stay inside the assignment. Audit is denied when `audit.read` is absent |

## Data or operations owner

| ID | Steps | Expected |
|---|---|---|
| UAT-O1 | Read an import reconciliation for a synthetic job | `submitted = accepted + rejected + skipped + awaiting review + not committed` |
| UAT-O2 | Open a reminder failure, if one exists | The failure label is one of the fixed labels, not a provider exception string |
| UAT-O3 | Follow `backup-restore-ownership.md` and `runbook.md` | The owner can name the backup operator, RPO, and RTO, or record that those decisions are still open |

## Execution rule

A case is Pass only when a person in that role has done the steps and the result was recorded. An automated test may be cited as engineering evidence. It does not mark the UAT case passed.
