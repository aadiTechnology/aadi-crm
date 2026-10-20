# CRM-S9 closure — original roadmap Sprint 7

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made for this review.

`docs/sprints/crm-s9` is the evidence folder for original roadmap Sprint 7, activity timeline and follow-ups. It is not original roadmap Sprint 9. Original roadmap Sprint 6 stays Planned.

## Decision

**CLOSED** against the technical checks below. Owner review of this closure is still required. This document does not accept the work on the owner's behalf.

## Review

The follow-up code, tests, and `docs/sprints/crm-s9` were read. The reported test counts were not treated as proof. The suite was run again on the current tree before reminder work began.

Sampled frames from `docs/sprints/crm-s9/recording.webm` were extracted with ffmpeg. This was not continuous playback. The frames show the recording user on Recording gate, record S2-REC-0013, a Note due 2026-10-19 09:00 India Standard Time with summary "Overdue check", a Call due 2026-10-20 12:00, and the Today queue while it is still loading with the previous "Showing 1 of 1" line. That matches the explanation script, including the documented queue-loading limitation. The completion timeline and the member denial sentence were not in the sampled frames. The script and `backend/tests/test_followups.py` cover those checks. ffprobe reports VP9, 1280×720, 89.40 seconds, 6,814,400 bytes.

## Acceptance checks

| Check | Status | Evidence |
|---|---|---|
| Create and show follow-ups on an authorized record | PASS | Lifecycle test and the S2-REC-0013 frames |
| Type, owner, due date/time, and outcome are stored and shown | PASS | Lifecycle test. The Note frame shows type, owner, due time, and summary. Outcome is required to complete and is covered by the test |
| Timeline order | PASS | Newest-first test |
| Overdue, Today, and Upcoming stay distinct | PASS | Queue-boundary test. The Today heading is in the recording |
| Tenant, project, record, and membership limits remain | PASS | Authorization test. `authorize_record` was not changed |
| Another user's protected record or follow-up is not returned | PASS | 404 with no summary text in the authorization test |
| Date and time handling | PASS | `Asia/Kolkata` conversion and invalid civil times are rejected. Projects do not store a timezone |
| Loading, empty, error, and populated queue states | PASS | Frontend follow-up tests. The recording shows the loading skeleton. Empty and error are in the component tests |
| Tests, build, and the recording agree | PASS | Commands below. The recording and script agree on the visible path and on the queue-loading limitation |
| Known limitations stay accurate | PASS | Assignment is still original Sprint 6. Timezone is `Asia/Kolkata`. The queue can keep the previous count while loading. The recording is 1280×720 and does not include a 390-pixel pass |

No material Sprint 7 defect was found. No Sprint 7 code was changed by this closure.

## Commands before reminder work

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**48 passed**, 1 Starlette `httpx` deprecation warning, in 8.24 seconds.

Frontend, from `frontend`:

`npm test`

**40 passed** (6 files).

`npx vite build` completed. `dist/assets/index-TJKSJ3KV.css` is 14.52 kB. `dist/assets/index-DJaLPC65.js` is 410.90 kB.

`npx tsc --noEmit` exited 2 on the existing files `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. The follow-up sources are not in that list.

## Limitations that remain

- Queues and civil due times use `Asia/Kolkata`.
- A follow-up owner who is not the record assignee cannot open that record. Record assignment is original Sprint 6.
- While a queue request is in flight, the previous count can remain on screen.
- The recording is 1280×720. A 390-pixel pass was not captured for Sprint 7.
- `npx tsc --noEmit` is not clean.
- S2-REC-0013 and cancelled leftovers from the Sprint 7 capture remain on Recording gate.

## Confirmation

No commit, push, merge, tag, or deployment was performed. Original roadmap Sprint 6 was not started.
