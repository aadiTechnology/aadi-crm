# CRM-S10 technical validation

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made.

`docs/sprints/crm-s10` evidences original roadmap Sprint 8. Original roadmap Sprint 6 remains Planned. Sprint 7's technical closure is `docs/sprints/crm-s9/closure.md`.

This document records checks. It does not accept the sprint on the owner's behalf.

## Commands

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**54 passed**, 1 Starlette `httpx` deprecation warning, in 10.61 seconds.

Frontend, from `frontend`:

`npm test`

**45 passed** (7 files).

`npx vite build` completed. `dist/assets/index-CqGp1exI.css` is 14.93 kB. `dist/assets/index-xJ0SABkN.js` is 416.87 kB.

`npx tsc --noEmit` exited 2. The errors are confined to the baseline files `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. That command did not pass.

The migration expectation in `test_membership_migration_preserves_archived_projects` includes `007_reminders.sql` and an empty `reminder_deliveries` table on the disposable database. The development-copy follow-up test still leaves the original database bytes unchanged.

## Reminder checks

| Check | Status | Evidence |
|---|---|---|
| Follow-up assignment and due reminders are created once | PASS | `test_delivery_is_idempotent_and_test_adapter_is_not_delivery` |
| A second delivery run adds no row | PASS | Same test, and the recording log `CARDS 27` then `CARDS_AFTER_SECOND 27` |
| Test adapter is not provider delivery | PASS | State `recorded`, `email_provider_confirmed` false, subject `CRM reminder`, summary and school name absent from the message |
| Client cannot choose the destination | PASS | A posted `recipient_email` of `evil@example.com` is ignored. The stored address is the directory address |
| Directory lookup fills a missing address on a later run | PASS | Email rows cleared to null are recorded as `manager@example.com` after process |
| Three temporary failures then stop | PASS | `test_retry_limit_terminal_failure_and_manual_retry` |
| Manual retry keeps the same row | PASS | Retry returns the same id in `pending`, then one recorded email, still 4 rows |
| A member cannot read or retry the failure list | PASS | Both calls return 403 |
| Completed and cancelled follow-ups are not sent | PASS | All of those rows are `suppressed` |
| Live mode without a provider is a terminal configuration failure | PASS | `provider_not_configured`, and a test outcome header does not turn it into a recording |
| A write without CSRF is rejected | PASS | Process without the header returns 401 |
| Cross-tenant inbox is empty and does not contain the record number or summary | PASS | Tenant B list is empty |
| A reminder does not reveal a record the caller cannot open | PASS | Assigned-scope member receives `record_available` false and no `public_number`. The same remains true after membership removal |
| A manager does not see another user's in-app reminder | PASS | The other owner's follow-up id is absent from the manager inbox |
| Exception text is not stored | PASS | `test_provider_exception_text_is_not_stored`. A raising adapter is stored as `provider_temporary`. `secret-token` and `password` are absent |
| Live backoff | PASS | `test_backoff_is_bounded_and_test_mode_does_not_wait`. Live waits are 60, 300, and 900 seconds. Test mode is 0 |

## Browser evidence

`node docs/sprints/crm-s10/record-demo.mjs` exited 0. It logged record S2-REC-0016, card counts 27 and 27, a retryable response, a failed response, `NARROW_OVERFLOW false`, and dates `2026-10-19` and `2026-10-20`.

ffprobe: VP9, 1280×720, duration 122.12 seconds, 10,260,145 bytes.

Sampled frames show the Reminders page and its loading state, S2-REC-0016, the test-adapter sentence that 2 emails were not delivered, the failure section for S2-REC-0016 with the directory address and a retry button, the narrow viewport with "The same reminder was queued again", and `playwright-member@example.com` with "Reminders is not available for this sign-in." The direct-address permission sentence was confirmed by the script and is brief. The empty inbox is not in this recording.

## Security notes

No new platform permission was added. Routes use the existing session, product access, and CSRF checks. Reminder queries include the tenant from that check. Email bodies built in the test do not include the follow-up summary.

## Confirmation

No commit, push, merge, tag, or deployment was performed.
