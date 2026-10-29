# CRM-S9 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change was made for this pass.

`docs/sprints/crm-s9` is the evidence folder for original roadmap Sprint 7, activity timeline and follow-ups. It is not original roadmap Sprint 9. The record-experience pass evidenced in `docs/sprints/crm-s8` is closed in `docs/sprints/crm-s8/technical-acceptance.md`. Original roadmap Sprint 6 stays unstarted.

This report does not accept Sprint 7 on the owner's behalf.

## Requirements delivered

- A chronological activity timeline on the CRM record detail, newest first, with a label, timestamp, and actor email when the directory can resolve it.
- Unlimited follow-ups on one record. Pagination is 1 to 100 rows, default 25. There is no application count cap. A test creates 26 follow-ups and reads them as a page of 25 plus the remaining row.
- Task types Call, WhatsApp, Email, Meeting, and Note. Call status is required for Call and rejected for the other types. The call statuses are connected, busy, not_connected, switched_off, and not_valid.
- Owner must be an active member of the same project. The record's `assignee_user_id` is not changed.
- Due date and due time are civil values in `Asia/Kolkata`, stored as a UTC instant. Invalid dates, invalid times, and daylight-saving gaps or ambiguous times are rejected on the server.
- Outcome is free text, at most 500 characters, and is required to complete a follow-up. Summary is at most 2000 characters.
- Create, list, view, edit, complete, and cancel. Completed and cancelled rows cannot be overwritten. Cancel is included because the PRD task actions include it.
- Overdue, Today, and Upcoming are computed in the project queue from the due instant and the open state. They are not stored as a status. Completed and cancelled rows are excluded. A missing due instant cannot be stored.
- Activity entries are written for create, update, reschedule, reassign, complete, and cancel. Older record creates and edits are not backfilled.

## Requirements deferred

- Configurable task types beyond the five PRD types. No approved extra-type store exists.
- Reminders and notifications. Those belong to original Sprint 8.
- The automatic 1, 3, 7, 21, and 90 day sequence. The sprint plan excludes it.
- Pause when a record is converted or lost. That depends on original Sprint 6 statuses.
- Record assignment and reassignment. Original Sprint 6. `authorize_record` was not changed.
- A follow-up owner who is an active project member, and who is not the record assignee, still cannot read that record.
- Admin security audit log and restore.

## File counts

8 modified files and 13 new files. The limit is 10 modified and 20 new.

Modified:

- `backend/app/main.py`
- `backend/pyproject.toml`
- `backend/tests/test_projects.py`
- `frontend/src/main.tsx`
- `frontend/src/features/shell/CrmShellPage.tsx`
- `frontend/src/features/records/RecordsPanel.tsx`
- `frontend/src/services/platform.ts`
- `frontend/src/styles.css`

New:

- `backend/migrations/006_followups.sql`
- `backend/app/followups_store.py`
- `backend/app/api/followups.py`
- `backend/tests/test_followups.py`
- `frontend/src/features/records/FollowUpsPanel.tsx`
- `frontend/tests/followups.test.tsx`
- `docs/sprints/crm-s8/technical-acceptance.md`
- `docs/sprints/crm-s9/scope-and-implementation-plan.md`
- `docs/sprints/crm-s9/record-demo.mjs`
- `docs/sprints/crm-s9/explanation-script.md`
- `docs/sprints/crm-s9/implementation-report.md`
- `docs/sprints/crm-s9/technical-validation.md`
- `docs/sprints/crm-s9/recording.webm`

`backend/app/project_access.py` is unchanged.

## Migration and database safety

`006_followups.sql` adds `follow_ups` and `record_activities` and their indexes. It has no `DROP` or `DELETE`. Foreign keys point at projects, records, and follow-ups.

The migration test builds a disposable database that already contains a record and a published form version, applies `006` twice, and checks that the record number, form version, and display name are unchanged and that both new tables start empty.

The development-copy test copies `backend/data/aadi_crm.sqlite`, applies migrations to the copy, and checks that the original file bytes are unchanged. Follow-up and activity counts on the copy match the original. The shared development database was not reset. The running CRM process applied `006` when it reloaded. The browser demo then added S2-REC-0013 and cancelled earlier open queue follow-ups left by failed capture attempts. Those rows remain in the development database.

## Tests and build

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**48 passed**, 1 Starlette `httpx` deprecation warning, in 10.74 seconds.

Frontend, from `frontend`:

`npm test`

**40 passed** (6 files) in 10.35 seconds. npm warned that `devdir` is an unknown env config.

`npx vite build` from `frontend` completed. Output: `dist/assets/index-TJKSJ3KV.css` 14.52 kB and `dist/assets/index-DJaLPC65.js` 410.90 kB. `frontend/dist` is gitignored.

`npx tsc --noEmit` from `frontend` exited 2. These are the existing baseline errors:

- `frontend/src/lib/config.ts` — `ImportMetaEnv` has no properties in common with the config type
- `frontend/tests/form-versions.test.tsx` — `FormVersion` status is not assignable to `"published"`
- `frontend/vite.config.ts` — cannot find `node:path`; `import.meta.dirname` is missing

The follow-up files are not in that error list.

## Authorization

`authorize_record` is unchanged. Every follow-up and activity route checks the CRM session, product access, project membership, and record access. Writes require the existing CSRF header. Client-supplied tenant, project, record, and actor fields are rejected.

The backend tests cover an authorized timeline, a 404 for a member reading another person's record, a removed member, a cross-project id, a cross-tenant queue, an ineligible owner, a hidden follow-up after archive, and a write without CSRF returning 401. Assigned-scope queue totals are forced to the caller so a member cannot inflate a count by requesting another owner. The live recording shows the member denial sentence and leaves "Overdue check" off that page.

## Evidence

- `docs/sprints/crm-s9/recording.webm`
- `docs/sprints/crm-s9/explanation-script.md`
- `docs/sprints/crm-s9/record-demo.mjs`
- `docs/sprints/crm-s9/technical-validation.md`
- `docs/sprints/crm-s9/scope-and-implementation-plan.md`
- `docs/sprints/crm-s8/technical-acceptance.md`

The status workbook `C:\Users\lenovo\AadiTech\Product\CRM\Aadi_CRM_Sprint_Plan_Status_Updated_2026-10-20.xlsx` now marks original Sprint 7 as implemented and awaiting acceptance. Original Sprint 6 stays Planned. Rows for original Sprints 4 and 5 were left as that workbook already recorded them.

## Known limitations and owner decisions

- Queues and civil due times use `Asia/Kolkata`. Projects and the tenant configuration document the CRM reads do not store a timezone. This is the interpretation recorded in the scope plan.
- A follow-up owner who is not the record assignee cannot open the record. Record assignment remains original Sprint 6.
- While a queue request is in flight, the previous count can remain on screen and the table is hidden. The loaded result replaces that count.
- Before project access returns, the queue page can show the assigned-scope sentence. After the project loads, a manager sees the assignee filter.
- The recording is 1280×720. A 390-pixel viewport was not captured. At 640 pixels and below, follow-up actions and queue tabs use the full width.
- Sampled queue frames mostly show the loading skeleton. The capture script waited for the queue rows and exited 0. The timeline frame shows the completion and the 11:15 reschedule.
- `npx tsc --noEmit` is not clean.
- CRM-UI-S2 has an implementation report and no recorded owner approval.
- S2-REC-0013 and the cancelled leftovers from earlier capture attempts remain on Recording gate.

## Confirmation

No commit, push, merge, tag, or deployment was performed. Sprint 7 is implemented and is not accepted. Original roadmap Sprint 6 was not started.
