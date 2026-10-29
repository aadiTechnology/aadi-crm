# Performance report — original roadmap Sprint 12

Date: 21 October 2026.

No latency or throughput SLO was found in the CRM repository. The numbers below are measurements, not approved targets. Load testing was not run. This is not a load-readiness claim.

## Environment

- Machine: local Windows workstation.
- Database: a temporary SQLite file created with `apply_migrations`. It was not `backend/data/aadi_crm.sqlite`. That default file was not in the workspace.
- Dataset: 1 project, 1 form, 1 published version, 200 active records, 200 open follow-ups. Search text was the synthetic word `bench`.
- Import file: a CSV with one header and 500 data rows, which is the existing row limit. The timing helper printed `n=200` for every label because it reused the record count. The CSV itself had 500 data rows.
- Each function was called 5 times in-process. There is no HTTP or browser time in these numbers.

| Workload | Minimum | Maximum |
|---|---|---|
| `project_kpis` for the 200-row project, with a UTC created-date period | 4.03 ms | 31.55 ms |
| `list_records` search, page size 25 | 2.01 ms | 5.28 ms |
| `read_table` on the 500-row CSV | 2.49 ms | 7.54 ms |

The first KPI call was the slow sample. Later calls were near the minimum.

## Query shape

KPI and queue reads are aggregated SQL with tenant and project predicates. They are not per-record round trips. Record list and export stay paged or capped: list limit is at most 100, export rejects more than 1,000 authorized rows, import rejects more than 500 data rows. Existing indexes include `ix_records_scope`, `ix_records_assignee`, and `ix_follow_ups_queue`. No new index was added. There was no measured query on this dataset that justified one.

Completed follow-up and record list pages still call `authorize_record` once per returned row. The page size is capped at 100. That is the existing check, and it was not removed.

## Frontend

Production build after the shell change:

- `dist/assets/index-DTLFABY5.js` — 445.49 kB, gzip 129.87 kB
- `dist/assets/index-p7lKm66a.css` — 15.60 kB, gzip 3.51 kB

One bundle is loaded. Initial page load in a browser was not timed. The KPI screen's project list, KPI request, and member request are three calls, not a polling loop.

## Proposed targets, not approved

For this local dataset only, a useful regression bar would be KPI and list under 500 ms in-process. That bar is **proposed**. It is not an owner SLO, and it says nothing about concurrent users.

## Unverified

Concurrent load, a dataset larger than 200 records, export of 1,000 rows, and the live API on port 8001 were not timed in the first pass. The next section records a later isolated run.

## Isolated load run on 21 October 2026

This run did not open `backend/data/aadi_crm.sqlite`. It applied migrations to a temporary SQLite file, inserted synthetic rows, and called the store functions from four worker threads. Each worker used its own connection. There was no HTTP server and no browser in these timings.

Environment: local Windows workstation, Python 3.14.3, the CRM virtualenv. Dataset: 1 project, 1 published form version, 1,000 active records, 1,000 open follow-ups, and 1,000 sent in-app reminders for one recipient. Search text was the synthetic word `bench`. The CSV was 1 header plus 500 data rows. Each workload ran 80 times (4 workers × 20 rounds). Errors were 0.

| Workload | Minimum | Median | p95 | Maximum | Mean |
|---|---|---|---|---|---|
| `project_kpis` with a UTC created-date period | 13.85 ms | 20.57 ms | 28.68 ms | 77.08 ms | 23.08 ms |
| `list_records` search, page size 25 | 4.26 ms | 6.35 ms | 9.91 ms | 19.82 ms | 6.71 ms |
| `list_inbox` for the 1,000 reminder rows | 16.12 ms | 59.69 ms | 69.26 ms | 76.76 ms | 58.11 ms |
| `read_table` on the 500-row CSV | 1.22 ms | 1.32 ms | 2.63 ms | 3.94 ms | 1.51 ms |

Seeding the 1,000-row file took 144.99 ms. The inbox query has no `LIMIT`. It returned every matching reminder for that user. At this size the tail was still under 80 ms. That is not evidence for a larger inbox.

The PRD asks for record list and detail pages under 2 seconds for up to 50,000 records per project in an agreed environment. This run did not use 50,000 records, did not time page render, and did not time export. No latency SLO in the repository was approved.

Provisional bar, not an owner SLO: on this workstation, KPI, list search, inbox, and the 500-row parse stay under a 500 ms p95 at 1,000 rows and 4 readers. The measurements are inside that bar. The bar is not approved and does not describe production capacity.

Indexes already present include `ix_records_scope`, `ix_records_assignee`, `ix_follow_ups_queue`, and `ix_reminder_inbox`. KPI and list reads are aggregated or paged SQL. Completed follow-up pages still call `authorize_record` once per returned row, with a page cap of 100. No index was added. No query on this dataset was slow enough to justify one.
