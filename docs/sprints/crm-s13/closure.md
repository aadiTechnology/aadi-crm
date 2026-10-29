# CRM-S13 closure — original roadmap Sprint 11

Date: 21 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made for this review.

`docs/sprints/crm-s13` is the evidence folder for original roadmap Sprint 11, dashboards, reports, and audit visibility. It is not original roadmap Sprint 13. Original roadmap Sprint 10 remains technically closed in `docs/sprints/crm-s12/closure.md`, still pending owner acceptance. Original roadmap Sprint 6 stays Planned.

## Decision

**CLOSED** against the technical checks below. Owner review of this closure is still required. This document does not accept the work on the owner's behalf.

No Sprint 11 product behavior was changed by this review. Request diagnostics and the Escape key on the mobile menu were added later for original roadmap Sprint 12. They do not change KPI or audit rules.

## Review

The KPI store, KPI routes, audit view, platform audit client, reporting and audit screens, and the Sprint 11 documents were read against the current code.

- Active counts use `deleted_at IS NULL` and the same form-version join as the record list. A project member is limited to `assignee_user_id`.
- Records created use `substr(created_at, 1, 10)` against `created_from` and `created_to`. That is the existing UTC calendar-day filter. The active count does not use that period.
- Records by form count active records only. The response `omitted` list includes `record_status`. No status KPI is rendered.
- Overdue, due today, and upcoming use `queue_window` and open follow-ups on active records. Each open row matches one queue. Completed counts use `status = completed`. Cancelled rows are excluded. Due-date cells are not links.
- The audit route calls `list_audit_events` with the session cookie and the path tenant. Metadata is dropped. Missing `audit.read` becomes 403. Platform failure becomes 502, "The audit log is unavailable." No CRM audit table was added, and no CRM action appends a platform audit event.

## Acceptance checks

| Check | Status | Evidence |
|---|---|---|
| Active counts match the authorized list and exclude archived records | PASS | `test_kpis_match_authorized_lists_and_queue_boundaries` |
| Created counts use the UTC calendar-day filter | PASS | Same test, compared with the record list |
| Records by form use active records | PASS | `reporting_store._records_by_form` and the same test |
| Counts are tenant- and project-scoped | PASS | `test_empty_project_and_cross_tenant_kpis_stay_closed` |
| No record-status KPI | PASS | `omitted` includes `record_status`. The screen has no status card |
| Empty, error, and unavailable states | PASS | Frontend reporting and audit tests. Empty project is in the reporting test |
| Queue counts match the queues and do not double-count | PASS | Owner and due-date sums equal the three queue totals in the reporting test |
| Completed rows are stored `completed` only | PASS | Cancelled fixture row is absent from the four totals |
| Drill-downs use existing routes. Due date is not a link | PASS | `frontend/tests/reporting.test.tsx` |
| Audit page uses the platform audit API | PASS | `platform_client.list_audit_events` |
| Missing `audit.read` is denied | PASS | `test_audit_view_failure_empty_and_permission` |
| A caller without the project or audit permission does not receive protected data | PASS | KPI cross-tenant 404. Audit 403. Member audit denial is in `frontend/tests/audit.test.tsx` |
| Platform unavailability is safe | PASS | 502 message. The secret in the test body is not returned |
| Audit metadata is not shown | PASS | `visible_audit_events` keeps the listed fields only |
| CRM actions do not write platform audit events | PASS | No `AuditService.append` call in this repository. The audit screen states that record and follow-up changes are not copied into the log |

## Commands on this review

Backend, from `backend`, before the Sprint 12 diagnostics tests:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**69 passed**, 1 Starlette `httpx` deprecation warning, in 24.54 seconds.

Frontend, from `frontend`, before the Escape test:

`npm test`

**54 passed** (10 files) in 11.07 seconds.

`npx vite build` succeeded. Assets at that point: `dist/assets/index-p7lKm66a.css` (15.60 kB) and `dist/assets/index-BqG7ObbA.js` (445.27 kB).

`npx tsc --noEmit` exited 2. This is not a pass. The errors are the existing baseline in `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. No Sprint 11 file is in that list.

A later full run, after Sprint 12 diagnostics and the Escape handler, was **71 passed** backend and **55 passed** frontend. Those two extra tests are Sprint 12. TypeScript still failed on the same three baseline files.

## Recording

`ffprobe` reports VP9, 1280×720, duration 86.20 seconds, 7,561,501 bytes. Continuous playback was not done. Frames were extracted with ffmpeg. The frames opened for this review show the signed-in shell for Bootstrap recording 1792111368748 and the project KPI page, including "Loading project KPIs". The numeric cards, the audit denial, and the 390-pixel layout were not visible in the frames that were opened. Those results remain in the original capture log quoted by `technical-validation.md` and in the automated tests. This review did not re-run `record-demo.mjs`.

## Not claimed

Owner acceptance is not claimed. A populated platform audit table was not shown. The running API process on port 8001 was not restarted for this closure.

## Independent re-verification

A later pass on 21 October 2026 re-read the KPI store, the audit view, and the current tests. It did not change Sprint 11 product behavior. The technical closure stands. Owner acceptance is still pending.

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**71 passed**, 1 Starlette `httpx` deprecation warning, in 25.10 seconds. This count includes the two Sprint 12 diagnostics tests.

Frontend, from `frontend`:

`npm test`

**55 passed** (10 files) in 11.89 seconds. This count includes the Sprint 12 Escape test.

`npx vite build` succeeded in 2.37 seconds. Assets: `dist/assets/index-p7lKm66a.css` (15.60 kB) and `dist/assets/index-DTLFABY5.js` (445.49 kB).

`npx tsc --noEmit` exited 2. This is not a pass. The errors remain in `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`.

A headless Chrome pass against the already running page on port 5174 opened the audit route at 1280×720, 768×1024, and 390×844 after the loading status cleared. Each showed "You do not have permission to perform this action." The numeric KPI cards were not read from the page in this pass. One direct open of a project KPI route was still on the access check when its text was captured. The KPI rules remain covered by `backend/tests/test_reporting.py` and `frontend/tests/reporting.test.tsx`. This pass did not re-play `recording.webm` and does not treat the earlier sampled frames as proof of the numeric cards.
