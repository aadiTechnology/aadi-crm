# Implementation report — original roadmap Sprint 12

Date: 21 October 2026. Repository: `aadi-crm` only.

Original roadmap Sprint 11 was technically closed first. See `docs/sprints/crm-s13/closure.md`. Owner acceptance of that closure is still pending. Original roadmap Sprint 6 stays planned.

## What changed

Two product changes, both from the baseline review:

- The API assigns an `X-Request-Id`, logs startup, logs responses at status 400 or higher and responses that take at least 1000 ms, and turns an unhandled exception into a generic 500. The log omits the query string, cookies, and the exception message.
- The mobile navigation closes on Escape and returns focus to "Open navigation".

No authorization rule, schema, or dependency was changed. No index was added.

## Files in this unit

New product files: none.

New evidence files are under `docs/sprints/crm-s14/`, plus `docs/sprints/crm-s13/closure.md`.

Modified product files:

- `backend/app/main.py`
- `backend/tests/test_shell_isolation.py`
- `frontend/src/features/shell/CrmShellPage.tsx`
- `frontend/tests/shell.test.tsx`

`docs/sprints/crm-s13/technical-acceptance.md` was updated to record technical closure. Sprint 11's other product files were already in the working tree and were not rewritten.

The Sprint 11 product unit remains 9 new files and 9 modified files, as listed in `docs/sprints/crm-s13/implementation-report.md`. This Sprint 12 unit stays inside 20 new files and 10 modified files.

## Confirmation

The Control Plane repository was not modified. No commit, push, merge, tag, or deployment was made. The API process already listening on port 8001 was not restarted, so it was not used as evidence for the new log lines.
