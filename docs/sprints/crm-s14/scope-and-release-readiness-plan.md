# Original Roadmap Sprint 12 — Hardening and Release Readiness

Date: 21 October 2026. Repository: `aadi-crm` only.

`docs/sprints/crm-s14` is the evidence folder for original roadmap Sprint 12. It is not original roadmap Sprint 14. Original roadmap Sprint 11 is technically closed in `docs/sprints/crm-s13/closure.md` and still needs owner acceptance. Original roadmap Sprint 6 stays planned. Paneerwala stays deferred.

The PRD file is not in this repository. No numeric latency, RPO, or RTO target was found in the CRM documents that were read. Targets below that are not already implemented are marked **proposed** and are not owner-approved.

No deployment manifest, Dockerfile, or GitHub workflow is in this repository. The verified run path is the local procedure in `README.md`.

## Baseline findings

| Area | Finding | Class | Severity | Remediation in this unit |
|---|---|---|---|---|
| Request diagnostics | The API had no log of failures, slow requests, or unhandled exceptions | Confirmed gap | Medium | Request id, status log, and a generic 500 response were added |
| Mobile navigation | The menu button did not close on Escape | Confirmed defect | Medium | Escape closes it and returns focus |
| Mobile navigation | There is no focus trap or backdrop | Limitation | Medium | Deferred. Escape is the keyboard exit |
| Cross-tenant and project checks | Existing routes keep tenant, membership, `authorize_record`, and CSRF | Reviewed, no high defect | — | No permission model change |
| Audit scope | The platform audit list is tenant-wide and has no project filter | Limitation of the current platform API | Medium | Not changed. The screen already says it is not filtered by project |
| Reminder inbox after removal | A removed member can still see their own reminder rows. Record identifiers stay hidden | Existing tested behavior | Low | Not changed |
| Accessibility contrast | `#64748b` on `#f8fafc` calculates to 4.55:1 | Calculated pass for normal text | — | No palette change |
| Performance | 200-row local SQLite queries were a few tens of milliseconds. No load test exists | Measurement and unverified load | — | No new index |
| Backup and restore | No backup schedule, owner, RPO, RTO, or restore evidence is in this repository. `backend/data/aadi_crm.sqlite` was not present during this review | Unverified | High for release | Documented. No restore was run |
| Monitoring | No metrics dashboard or alert configuration was found | Unverified | High for release | Logging only. Alerts are not claimed |
| UAT | Role walkthroughs were not executed by those roles | Not executed | High for release | Plan and partial engineer results are recorded |
| TypeScript | `tsc --noEmit` fails on the known baseline | Confirmed, pre-existing | Medium | Left as a failure |
| Live API | Port 8001 was already listening and was not restarted | Unverified for the new log lines | Low | Tests cover the new process. The running process was not assumed to have it |

## Out of scope

Assignment, record status, and duplicate detection stay with original roadmap Sprint 6. The Control Plane permission model was not changed. No production deploy, database reset, or restore into a shared database was performed.
