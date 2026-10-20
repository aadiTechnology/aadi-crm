# CRM-S9 technical validation

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made.

`docs/sprints/crm-s9` evidences original roadmap Sprint 7. Original roadmap Sprint 6 remains Planned.

This document records checks. It does not accept the sprint on the owner's behalf.

## Sprint 6 closure

The record-experience checks are recorded in `docs/sprints/crm-s8/technical-acceptance.md` with status CLOSED. CRM-UI-S2 has an implementation report and no recorded owner approval. That UI status is separate from the technical closure.

## Commands

Backend, from `backend`, after the development-copy assertion was updated to compare follow-up counts with the original file:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**48 passed**, 1 Starlette `httpx` deprecation warning, in 10.74 seconds.

Frontend, from `frontend`:

`npm test`

**40 passed** (6 files) in 10.35 seconds.

`npx vite build` completed. `dist/assets/index-TJKSJ3KV.css` is 14.52 kB. `dist/assets/index-DJaLPC65.js` is 410.90 kB.

`npx tsc --noEmit` exited 2 on the baseline files `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. Those three failures were already present before this sprint. The follow-up sources are absent from the error list.

## Follow-up and timeline checks

| Check | Status | Evidence |
|---|---|---|
| Create, list, view, edit, complete, and cancel | PASS | `test_follow_up_lifecycle_timeline_and_queues` |
| No application count cap | PASS | `test_many_follow_ups_have_no_count_cap` creates 26 rows and pages them |
| Task type and call status validation | PASS | A call without a call status is rejected. A non-call with a call status is rejected. |
| Owner must be an active project member | PASS | An outside user id is rejected with 422. A removed member cannot be assigned. |
| Due date and time validated on the server | PASS | Invalid civil dates are rejected. `Asia/Kolkata` midnight maps to `2026-10-20T18:30:00.000000+00:00`. A US Eastern gap and overlap are rejected by the conversion helper. |
| Queue boundaries | PASS | At `2026-10-21 00:00` India Standard Time, one second earlier is overdue, that midnight is today, and the next midnight is upcoming. Completed rows are excluded. The three date queues are disjoint. |
| Timeline order and pagination | PASS | Events are newest first. The lifecycle test pages the timeline and checks the event types. |
| Historical form version | PASS | Creating a follow-up leaves `form_version_id` and the record `updated_at` unchanged. The migration test keeps the seeded form snapshot. |
| Record authorization | PASS | A member receives 404 for another person's record timeline and follow-up, with no payload text. |
| Cross-project and cross-tenant | PASS | Both return 404. The cross-tenant body does not contain the follow-up summary. |
| Removed member | PASS | After removal, the member's follow-up read returns 404. |
| Archive hides follow-ups | PASS | The follow-up list for an archived record returns 404. |
| CSRF | PASS | A write without the CSRF header returns 401. |
| Queue totals do not leak | PASS | An assigned-scope member asking for another owner still receives their own owner id and a total of 0 for a follow-up on a record they cannot see. |
| Migration safety | PASS | Disposable database with an existing record and form version. Development-database copy keeps the original bytes and the same follow-up and activity counts. |

## Browser evidence

`node docs/sprints/crm-s9/record-demo.mjs` exited 0. It logged `RECORD S2-REC-0013` and dates `2026-10-19 2026-10-20 2026-10-21`, then wrote `docs/sprints/crm-s9/recording.webm`.

ffprobe: VP9, 1280×720, duration 89.40 seconds, 6,814,400 bytes.

The recording shows the authorized record, multiple follow-ups, task type, owner, due date and time, the outcome text, the newest-first timeline including the 11:15 reschedule and the completion, the three queue headings, and the member permission denial. The narration in `explanation-script.md` matches those frames and states where the loaded queue tables are only briefly on screen.

A 390-pixel browser pass was not recorded.

## Database

The shared development database was not reset. `006_followups.sql` is additive. The running API applied it on reload. The demo left S2-REC-0013 and cancelled earlier open follow-ups from failed capture attempts.

## Known limitations

- Original Sprint 6 is not started.
- Timezone is `Asia/Kolkata` for this sprint.
- A follow-up owner who is not the record assignee cannot read the record.
- Extra task types, reminders, the automatic sequence, status pause, and restore are not built.
- Queue loading can show the previous count until the new response arrives.
- `npx tsc --noEmit` is not clean.

## Confirmation

No commit, push, merge, tag, or deployment was performed.
