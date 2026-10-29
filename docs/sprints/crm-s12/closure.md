# CRM-S12 closure — original roadmap Sprint 10

Date: 21 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made for this review.

`docs/sprints/crm-s12` is the evidence folder for original roadmap Sprint 10, templates and source migration. It is not original roadmap Sprint 12. Original roadmap Sprint 9 remains technically closed in `docs/sprints/crm-s11/closure.md`, still pending owner acceptance. Original roadmap Sprint 6 stays Planned.

## Decision

**CLOSED** for the required in-scope templates. Owner review of this closure is still required. This document does not accept the work on the owner's behalf.

**Paneerwala is Deferred.** It is not complete. It was not configured, migrated, or reconciled. The product owner deferred it, so it does not block this closure.

## What was verified again

`backend/tests/test_domain_templates.py` was run on the current tree. **4 passed** in 4.18 seconds. The test imports Preschool, Space View, and Hiring through the existing preview, commit, authorization, and idempotency paths on a temporary SQLite file. It does not open `backend/data/aadi_crm.sqlite`.

The same run rewrote `crosswalk.json`. Counts:

| Dataset | Configured | Migrated | Reconciled | Submitted | Accepted | Rejected | Skipped | Unexplained difference |
|---|---|---|---|---|---|---|---|---|
| Preschool | Yes. Published form version on project `PRESCHOOL` | Yes | Yes | 4 | 4 | 0 | 0 | 0 |
| Space View | Yes. Published form version on project `SPACE-VIEW` | Yes | Yes | 12 | 11 | 1 | 0 | 0 |
| Hiring | Yes. Published form version on project `HIRING` | Yes | Yes | 13 | 13 | 0 | 0 | 0 |
| Paneerwala | No | No | No | 0 | 0 | 0 | 0 | Not claimed |

The equation `submitted = accepted + rejected + skipped + awaiting review + not committed` holds for the three imported datasets. Awaiting review and not committed are 0. Key-field comparison reported no mismatches. The Space View rejection is source row 2, inquiry date outside the accepted window. Duplicate `SR.NO` values 24 and 25 were kept. Hiring formula cells were stored as their cached integers. A repeated commit and the same idempotency key did not add records.

No source names, phone numbers, or email addresses are repeated in this closure.

## Not claimed

Paneerwala was not migrated. A second idempotency key is not an exactly-once retry. Numeric phone cells are the workbook integers, not a reconstructed original. Follow-up comment columns are text on the record, not activity-log rows. Owner acceptance is not claimed.
