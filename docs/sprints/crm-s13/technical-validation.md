# CRM-S13 technical validation — original roadmap Sprint 11

Date: 21 October 2026. Commands were run on the current tree after the KPI and audit code was in place.

## Commands

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**69 passed**, 1 Starlette `httpx` deprecation warning, in 25.75 seconds. The new files contributed 4 tests. The Sprint 10 domain-template file was also run on its own earlier the same day: **4 passed** in 4.18 seconds.

Frontend, from `frontend`:

`npm test`

**54 passed** (10 files) in 12.11 seconds. The new files contributed 6 tests. jsdom printed `Not implemented: navigation to another Document` in the existing import download test. The tests still passed.

`npx vite build`

Succeeded in 2.14 seconds. Assets: `dist/assets/index-p7lKm66a.css` (15.60 kB) and `dist/assets/index-BqG7ObbA.js` (445.27 kB).

`npx tsc --noEmit`

Exited 2. This is not a pass. The errors are the existing baseline:

- `frontend/src/lib/config.ts` TS2559
- `frontend/tests/form-versions.test.tsx` TS2769
- `frontend/vite.config.ts` TS2307 and TS2339

No Sprint 11 file is in that list.

## Database

No migration was added. KPI queries use the existing record and follow-up indexes. The reporting tests apply the current migrations to a temporary SQLite file. They do not open `backend/data/aadi_crm.sqlite`. The browser demo did create synthetic projects in the shared development database. That file was not reset.

The KPI request in the reporting test returned in under 2 seconds on the small fixture. That is a ceiling check, not a load benchmark.

## Checks

| Check | Result |
|---|---|
| Active, created, and form counts match the record list | `test_kpis_match_authorized_lists_and_queue_boundaries` |
| Queue counts match `GET .../follow-ups` | Same test. Overdue 2, today 2, upcoming 2 before archive. Owner splits match the owner filter |
| One open follow-up is in one queue | Owner and due-date sums equal the three queue totals |
| Asia/Kolkata boundaries | Window `2026-10-20T18:30:00Z` through `2026-10-21T18:30:00Z`. Due dates `2026-10-20`, `2026-10-21`, and `2026-10-22` |
| Completed count matches its list | Total 1, and the row has no summary or outcome |
| Cancelled follow-up is in none of the counts | Included in the fixture and absent from the four totals |
| Archived record leaves the counts | Active, open queues, and completed drop that record |
| Created-date period does not change the active count | UTC day filter compared with the record list |
| Unknown KPI filter | `q` returns 422 |
| Member cannot see another assignee's records or follow-ups | Member active count 1. Today count 0. Response does not contain the other form name, record title, or owner id |
| Cross-tenant and non-member | 404, and the project name is not in the body |
| Empty project | All counts 0 |
| Audit metadata and email dropped | `test_audit_view_strips_metadata_and_rejects_unsupported_filters` |
| Unsupported audit filters and offset | 422, and the platform method is not called |
| Audit limit | `limit=1` returns one event and is forwarded |
| Other tenant | Returns that tenant's event only |
| Empty audit list | 200 and `items: []` |
| Missing `audit.read` | 403 |
| Platform failure and malformed event | 502, message "The audit log is unavailable.", secret not in the body |
| Signed-out audit read | 401 |
| Frontend drill-down links, empty copy, completed list, retry | `frontend/tests/reporting.test.tsx` |
| Frontend audit empty, denial, unavailable, hidden secret | `frontend/tests/audit.test.tsx` |

## Browser

`node docs/sprints/crm-s13/record-demo.mjs` exited 0. The recording is 86.20 seconds. The capture log for stamp `830912` showed active 2, created 2, overdue 1, today 1, upcoming 1, completed 1, created-today 2, `AUDIT_STATE denied`, `AUDIT_ROWS 0`, `NARROW_OVERFLOW false`, and `MEMBER_AUDIT denied`.

An earlier capture with stamp `624532` stopped while waiting for a record name that appeared twice on the list. Stamp `690266` completed the path but read the member audit page before it settled. Those recordings were replaced. The successful file is `recording.webm`.

## Not claimed

The recording does not show audit rows or an unavailable platform. `tsc --noEmit` did not pass. Owner acceptance is not claimed.
