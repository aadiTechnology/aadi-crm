# CRM-S10 closure — original roadmap Sprint 8

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made for this review.

`docs/sprints/crm-s10` is the evidence folder for original roadmap Sprint 8, notifications and reminders. It is not original roadmap Sprint 10. Original roadmap Sprint 6 stays Planned.

## Decision

**CLOSED** against the technical checks below. Owner review of this closure is still required. This document does not accept the work on the owner's behalf.

No Sprint 8 code was changed by this review. The previously reported test counts were not reused. The suites were run again on the current tree.

## Review

The reminder store, reminder routes, migration `007_reminders.sql`, tests, and the Sprint 8 documents were read against the code. `authorize_record` is still the record check: the reminder payload calls `_allowed`, and `_allowed` calls `authorize_record`.

Sampled frames from `docs/sprints/crm-s10/recording.webm` were extracted with ffmpeg at about 12-second intervals. This was not continuous playback. ffprobe reports VP9, 1280×720, 122.12 seconds, 10,260,145 bytes. The frames that were inspected show:

- The Reminders page for `playwright-recording@example.com` on Bootstrap recording 1792111368748, including "Loading reminders", India Standard Time, and the sentence that a recorded email has not been delivered.
- A follow-up being saved: Note, owner `playwright-recording@example.com`, 20 October 2026 at 09:00, summary "Morning reminder".
- The delivery result: "The test adapter recorded 2 email reminders. Those emails were not delivered. In-app reminders delivered: 2. Temporary failures: 0. Stopped: 0."
- Record S2-REC-0016, Campus "Reminder lane", Priority Warm.
- The failure section for S2-REC-0016 with the directory address, a retry button, Attempts 1, and later Attempts 3 with "No automatic retry is scheduled."

The sampled frames do not include the empty inbox, the narrow 390-pixel layout, the "same reminder was queued again" notice, or the member denial sentence. The explanation script already says the empty inbox is a component test and that the permission sentence is brief. Those checks remain in `frontend/tests/reminders.test.tsx` and `backend/tests/test_reminders.py`.

## Acceptance checks

| Check | Status | Evidence |
|---|---|---|
| In-app reminders are created for follow-up assignment and due time, and queries include the tenant | PASS | `sync_follow_up_reminders` inserts one in-app and one email row for each kind. List and delivery SQL include `tenant_id` |
| Logical events are idempotent | PASS | Unique `idempotency_key` and `ON CONFLICT DO NOTHING`. `test_delivery_is_idempotent_and_test_adapter_is_not_delivery` |
| A repeated delivery run does not create another logical reminder | PASS | Same test asserts 4 rows after a second run. The recording script's card count is not re-measured here; the test is the current check |
| Retry stops at the configured attempt limit | PASS | `MAX_ATTEMPTS` is 3. The third temporary failure is stored as `failed`. The sampled frame shows Attempts 3 and no automatic retry |
| Provider failures and stopped deliveries stay visible | PASS | Failure list and inbox include `retryable` and `failed` email rows. The recording shows the failure section |
| Manual retry uses the same row | PASS | `retry_delivery` updates that id and resets its attempt count. It does not insert a row |
| Test mode is a test adapter | PASS | Default mode records `recorded` / "Not delivered". `email_provider_confirmed` stays false. The recording states the emails were not delivered |
| Live mode without a provider fails visibly | PASS | `UnconfiguredEmailAdapter` stores `provider_not_configured`. A test-outcome header is ignored when mode is live |
| Record details follow `authorize_record` | PASS | `_item` adds the record number only when `_allowed` is true. The access test expects `record_available` false and no `public_number` |
| Completed and cancelled follow-ups are not sent | PASS | Open-only materialization and `suppressed_follow_up_closed` for pending or retryable rows |
| CSRF, authentication, and cross-tenant access | PASS | Writes use `_open_module(..., write=True)`. The missing CSRF header returns 401. A tenant B inbox is empty |
| Documents agree with the code | PASS | Scope, report, validation, operations, and the explanation script match the store and the sampled frames, including the limits below |
| Migration `007_reminders.sql` | PASS | Additive table and indexes. No `DROP` or `DELETE`. The disposable migration test expects the script and an empty `reminder_deliveries` table |

No material Sprint 8 defect was found. Actual email delivery is not claimed. The test adapter recorded intents. It did not send them.

## Commands on this review

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**54 passed**, 1 Starlette `httpx` deprecation warning, in 12.12 seconds.

Frontend, from `frontend`:

`npm test`

**45 passed** (7 files).

`npx tsc --noEmit` was not run again for this closure because no Sprint 8 source changed. The last recorded TypeScript result remains an unsuccessful exit on the existing baseline files, and that command is not treated as passed.

## Limitations that remain

- There is no platform mail API and no background sender. Test mode is not delivery.
- Exactly-once external delivery is not claimed.
- Record assignment and reassignment remain original Sprint 6. Follow-up owner changes are the assignment this sprint can persist.
- Due times use `Asia/Kolkata`.
- A person must run **Deliver pending reminders**.
- The recording review above used sampled frames, not continuous playback.

## Confirmation

No commit, push, merge, tag, or deployment was performed. Original roadmap Sprint 6 was not started.
