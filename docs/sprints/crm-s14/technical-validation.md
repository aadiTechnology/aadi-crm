# Technical validation — original roadmap Sprint 12

Date: 21 October 2026. Commands were run on the current tree after the diagnostics middleware and the Escape handler.

## Commands

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**71 passed**, 1 Starlette `httpx` deprecation warning, in 29.73 seconds. The two new shell tests are included.

Frontend, from `frontend`:

`npm test`

**55 passed** (10 files) in 13.83 seconds. The new shell test is included. jsdom printed `Not implemented: navigation to another Document` in the existing import download test. The tests still passed.

`npx vite build`

Succeeded in 2.60 seconds. Assets: `dist/assets/index-p7lKm66a.css` (15.60 kB) and `dist/assets/index-DTLFABY5.js` (445.49 kB, gzip 129.87 kB).

`npx tsc --noEmit`

Exited 2. This is not a pass. The errors are the existing baseline:

- `frontend/src/lib/config.ts` TS2559
- `frontend/tests/form-versions.test.tsx` TS2769
- `frontend/vite.config.ts` TS2307 and TS2339

No Sprint 12 file is in that list.

## Other checks

| Check | Result |
|---|---|
| Denial log omits the cookie and rejects a malformed request id | `test_authentication_denial_is_logged_without_the_session_cookie` |
| Unhandled error body and log omit the exception text | `test_unhandled_error_hides_the_exception_text` |
| Escape closes the menu and restores focus | `frontend/tests/shell.test.tsx` and browser log `ESCAPE expanded=false` |
| Page overflow at 1280, 768, and 390 | 0 for the routes in `responsive-validation.md` |
| KPI, list, and 500-row CSV timings | `performance-report.md` |
| Default SQLite file integrity | Not run. `backend/data/aadi_crm.sqlite` was not in the workspace |
| Restore | Not run |
| Load test | Not run |
| Human UAT | Not passed. See `uat-results.md` |
| Live process on port 8001 | Already listening. Not restarted and not used to prove the new log |

## Recording

`node docs/sprints/crm-s14/record-demo.mjs` exited 0. `ffprobe` reports VP9, 1280×720, 15.16 seconds, 1,295,429 bytes. Sampled frames show the narrow import and records pages. Continuous playback was not done.

## Not claimed

`tsc --noEmit` did not pass. Backup, restore, monitoring, and human UAT did not pass. Owner acceptance is not claimed.

## Later validation on 21 October 2026

The same commands were run again on the current tree. No application source file was changed in that pass.

| Command | Result |
|---|---|
| `backend`: `.\.venv\Scripts\python -m pytest -q --tb=line` | **71 passed**, 1 Starlette warning, 25.10 seconds |
| `frontend`: `npm test` | **55 passed** (10 files), 11.89 seconds |
| `frontend`: `npx vite build` | Succeeded in 2.37 seconds. `index-p7lKm66a.css` 15.60 kB, `index-DTLFABY5.js` 445.49 kB |
| `frontend`: `npx tsc --noEmit` | Exit 2. Same three baseline files. This is a failure |
| Isolated load test | See `performance-report.md`. 1,000-row temporary SQLite, 4 readers, 0 errors |
| Headless layout and axe | See `responsive-validation.md` and `accessibility-review.md` |
| Live log process | A new process on port 8091. Port 8001, pid 5148, was not restarted. See `observability.md` |
| `PRAGMA integrity_check` on `backend/data/aadi_crm.sqlite` | `ok`. Read-only. Migrations `001` through `008`. This is not a restore |
| Restore | Not run |
| Human UAT | Not passed |

Python 3.14.3. Node v22.13.1. No new recording was made. The existing `recording.webm` was not replayed continuously.
