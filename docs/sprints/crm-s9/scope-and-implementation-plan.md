# CRM-S9 scope and implementation plan

Date: 20 October 2026. Written before the follow-up code change. Repository: `aadi-crm` only.

`docs/sprints/crm-s9` is the evidence folder for this execution's activity timeline and follow-ups. It is not original roadmap Sprint 9. Original roadmap Sprint 7 is this scope. Original roadmap Sprint 6 (assignment, statuses, duplicate detection, terminal reason) stays unstarted.

## Source

PRD v1.0 dated 9 October 2026 is not in the repository. The copy read for this plan is `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`. The sprint row is original roadmap Sprint 7 in `C:\Users\lenovo\Downloads\Aadi_CRM_Complete_Sprint_Plan.xlsx`.

## Requirement map

| Requirement | PRD / plan | Existing implementation | This sprint |
|---|---|---|---|
| Chronological record timeline | REC-11, Activity entity | No activity table or timeline UI | Add `record_activities` and show it on record detail, newest first |
| Unlimited follow-ups | TASK-01, acceptance 13.1 | No follow-up table | Add `follow_ups` with no application count cap, indexes, and pagination |
| Task type | TASK-03: Call, WhatsApp, Email, Meeting, Note, plus configurable extras | No task-type store | Use those five PRD types. No new configuration system, so extra types are deferred |
| Owner | TASK-01 user, TASK-04 reassign | Active project membership and `authorize_record` | Owner must be an active project member. Record assignee is not changed |
| Due date and time | TASK-01, TASK-02 timezone | UTC timestamps in CRM. No project or tenant timezone column. Tenant configuration read by the CRM has no timezone | Store a UTC instant. Civil date and time are India Standard Time (`Asia/Kolkata`) |
| Outcome and summary | TASK-01 discussion summary; data model `outcome` and `summary` | None | Summary on the follow-up. Outcome required to complete. Timeline keeps the completion text |
| Complete, reschedule, cancel, reassign | TASK-04 | None | Allowed while the follow-up is open. Completed and cancelled rows cannot be overwritten |
| Overdue, Today, Upcoming | TASK-02 | None | Computed from `due_at`, completion state, and `Asia/Kolkata`. Not stored as a status |
| Reminders | TASK-05, original Sprint 8 | None | Deferred. Sprint 8 owns notifications |
| Automatic 1/3/7/21/90 sequence | TASK-06, Sprint 7 exclusion | None | Not built |
| Pause when converted or lost | TASK-07 | No record status | Deferred with original Sprint 6 |
| Record assignment | REC-07, original Sprint 6 | Creator is stored as `assignee_user_id`. No reassignment | Not built. `authorize_record` stays as it is |
| Security audit log | AuditEvent, Sprint 11 | Not in the CRM timeline | Not exposed here. The timeline is only follow-up activity recorded by this sprint |

## Queue and timezone interpretation

TASK-02 says each user sees Overdue, Today, and Upcoming, and a manager can filter by assignee and project. Due state uses project or tenant timezone rules. Neither `projects` nor the tenant configuration document the CRM already reads stores a timezone.

Interpretation used for this sprint:

- Queues are opened inside one project. A manager may filter by owner. A member with assigned record scope sees only follow-ups they own on records assigned to them.
- A follow-up with no due instant cannot be stored. It cannot appear in a queue.
- Open follow-ups are classified from the UTC instant. Completed and cancelled follow-ups are excluded.
- Overdue means due before the start of the current `Asia/Kolkata` calendar day. Today means due from that midnight up to, but not including, the next midnight. Upcoming means due on or after the next midnight.
- The browser sends a calendar date and a clock time. The server treats both as `Asia/Kolkata` and converts them to UTC. It does not store the browser's local clock as UTC.
- A civil time that does not exist, or that occurs twice because of a daylight-saving transition, is rejected. `Asia/Kolkata` does not observe daylight saving. The conversion helper still rejects those transitions for zones used in tests.
- A follow-up owner who is an active project member, but who is not the record assignee, still cannot read that record. This sprint does not widen `authorize_record` and does not implement record reassignment.

## Activity types recorded

Only events written by follow-up operations in this sprint:

- `follow_up.created`
- `follow_up.updated`
- `follow_up.rescheduled`
- `follow_up.reassigned`
- `follow_up.completed`
- `follow_up.cancelled`

Older record creates and edits are not backfilled. Internal security logs are not shown.

## API

These routes do not exist yet:

- `GET /api/v1/tenants/{tenant}/projects/{project}/records/{record}/activities`
- `GET /api/v1/tenants/{tenant}/projects/{project}/records/{record}/follow-ups`
- `POST` the same collection
- `GET` and `PATCH /api/v1/tenants/{tenant}/projects/{project}/records/{record}/follow-ups/{follow_up}`
- `POST .../follow-ups/{follow_up}/complete`
- `POST .../follow-ups/{follow_up}/cancel`
- `GET /api/v1/tenants/{tenant}/projects/{project}/follow-ups?queue=overdue|today|upcoming`

Every route uses the existing CRM session, product access, project membership, and `authorize_record`. Writes keep the existing CSRF check. Client-supplied tenant, project, record, and actor values are not trusted.

## File budget

Limit: 20 new files and 10 modified files.

Modified (7):

- `backend/pyproject.toml` — depend on `tzdata` so civil-time conversion works on Windows
- `backend/app/main.py` — register the follow-up router
- `frontend/src/main.tsx` — follow-up queue routes
- `frontend/src/features/shell/CrmShellPage.tsx` — queue navigation inside the existing shell
- `frontend/src/features/records/RecordsPanel.tsx` — timeline and follow-ups on record detail
- `frontend/src/services/platform.ts` — CRM client calls
- `frontend/src/styles.css` — timeline, form, and queue layout
- `backend/tests/test_projects.py` — expect the additive follow-up migration and an empty follow-up table

New (13, including the recording produced after the tests):

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

That is 8 modified files and 13 new files. `project_access.py` and `authorize_record` stay unchanged.
