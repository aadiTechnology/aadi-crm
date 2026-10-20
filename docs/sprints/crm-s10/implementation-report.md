# CRM-S10 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change was made.

`docs/sprints/crm-s10` is the evidence folder for **original roadmap Sprint 8**, notifications and reminders. It is not original roadmap Sprint 10. `docs/sprints/crm-s8` was not renamed or overwritten. Original roadmap Sprint 6 stays Planned.

This report does not accept Sprint 8 on the owner's behalf. Sprint 7's technical closure is `docs/sprints/crm-s9/closure.md`.

## What was found before coding

The Control Plane audit API can list events. It cannot append them. MT-S6, the notification port, is not implemented. `NoOpPasswordResetNotifier` discards a password-reset secret and is not a mail API. CRM therefore does not call a platform sender and does not add SMTP.

Follow-up create, update, complete, and cancel are the persisted assignment operations. Changing `owner_user_id` is a follow-up reassignment. `records.assignee_user_id` is still the creator, with no reassignment API. Record-level assignment reminders were not built.

## What was implemented

- Saving a follow-up materializes one in-app row and one email row for assignment, and the same pair for the due instant.
- The idempotency key is unique in `reminder_deliveries`. A second save or a second delivery run does not insert another row for the same key.
- Delivery is explicit. **Deliver pending reminders** claims each due row once per run.
- In-app success is `sent` after the local row commit. Email in the default test mode is `recorded`, which the screen describes as not delivered. Live mode, with no provider, is `failed` / `provider_not_configured`.
- Temporary email failure retries up to 3 times. Test mode does not wait between runs. Live mode waits 60, 300, then 900 seconds. The fourth automatic attempt is not made.
- A project manager sees stopped and retryable email rows for projects they manage and can retry the same row.
- Record number and the record link are returned only when `authorize_record` allows the record on that request.
- Email addresses come from the platform directory, or from the signed-in identity when the recipient is the caller. The client cannot submit a destination.

## File counts

7 modified files and 15 new files. The limit is 10 modified and 20 new.

Modified:

- `backend/app/main.py`
- `backend/app/api/followups.py`
- `backend/tests/test_projects.py`
- `frontend/src/main.tsx`
- `frontend/src/features/shell/CrmShellPage.tsx`
- `frontend/src/services/platform.ts`
- `frontend/src/styles.css`

New:

- `backend/migrations/007_reminders.sql`
- `backend/app/reminders_store.py`
- `backend/app/api/reminders.py`
- `backend/tests/test_reminders.py`
- `frontend/src/features/reminders/RemindersPanel.tsx`
- `frontend/tests/reminders.test.tsx`
- `docs/sprints/crm-s9/closure.md`
- `docs/sprints/crm-s10/scope-and-implementation-plan.md`
- `docs/sprints/crm-s10/record-demo.mjs`
- `docs/sprints/crm-s10/recording.webm`
- `docs/sprints/crm-s10/explanation-script.md`
- `docs/sprints/crm-s10/implementation-report.md`
- `docs/sprints/crm-s10/technical-validation.md`
- `docs/sprints/crm-s10/technical-acceptance.md`
- `docs/sprints/crm-s10/operations.md`

`authorize_record` and the Control Plane repository were not changed.

## Migration

`007_reminders.sql` adds `reminder_deliveries` and three indexes. It has no `DROP` or `DELETE`. The migration test expects `007_reminders.sql` after `006_followups.sql` and an empty reminder table on a disposable database. The shared development database was not reset. The running API applied the script when it reloaded. The browser capture then added S2-REC-0014, S2-REC-0015, and S2-REC-0016, plus reminder rows for those follow-ups and for older open follow-ups on Recording gate.

## Tests and build

Backend, from `backend`, after the reminder tests:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**54 passed**, 1 Starlette `httpx` deprecation warning, in 10.61 seconds.

Frontend, from `frontend`:

`npm test`

**45 passed** (7 files).

`npx vite build` completed. `dist/assets/index-CqGp1exI.css` is 14.93 kB. `dist/assets/index-xJ0SABkN.js` is 416.87 kB.

`npx tsc --noEmit` exited 2. The errors are the existing baseline in `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. Reminder sources are not in that list. TypeScript validation did not pass.

## Known limitations

- There is no platform notification port and no live mailbox. Test mode must not be described as delivery.
- Exactly-once external delivery is not claimed. See `operations.md`.
- Record assignment and reassignment remain original Sprint 6.
- Due times use `Asia/Kolkata`.
- A person must run **Deliver pending reminders**. Nothing sends on a timer.
- The first capture attempt stored some S2-REC-0013 email rows without a directory address. Those rows are stopped with `recipient_email_unavailable`. Later delivery resolves an address when the directory or the caller's own identity can supply one. A manager can retry a stopped row.
- The successful recording does not show an empty inbox. The component test does.
- The recording frame is 1280×720. The 390-pixel check is the left portion of that frame. The script reported no horizontal overflow.
- Platform audit remains read-only, so these failures are visible in CRM rather than in the platform audit list.

## Confirmation

No commit, push, merge, tag, or deployment was performed. Sprint 8 is implemented and is not accepted. Original roadmap Sprint 6 was not started.
