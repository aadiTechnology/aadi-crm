# CRM-S8 technical validation

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made in this pass.

Sprint 5 is closed in `docs/sprints/crm-s7/technical-acceptance.md`. This pass does not replace original roadmap Sprint 6. The overlap decision is `docs/sprints/crm-s8/scope-and-overlap-audit.md`.

Owner acceptance of this pass is pending.

## Checklist

| Check | Result |
|---|---|
| Reuse create and edit on the published snapshot | PASS. No second create path. `test_record_keeps_its_published_version_through_search_edit_and_archive` still passes. |
| Keep `form_version_id` when a newer version exists | PASS. The recording edits S2-REC-0002 on version 1 while Record check's current published label is Campus. The edit screen shows School name. |
| Server controls tenant, project, actor, timestamps, and record number | PASS. Existing create path. The new custom-field test sends `public_number` `FAKE-0009` and stores `N-1-0001`. |
| Custom fields use the published field definitions | PASS. Email, number range, mobile, date, required checkbox, and multi-select are validated in `test_custom_fields_validate_on_the_published_schema_without_consuming_a_number`. File and auto-number are rejected. Unknown keys are rejected. |
| A rejected create does not consume a number | PASS. After several 422 responses the records table is empty and the next success is `N-1-0001`. |
| Concurrent numbers stay unique | PASS. Existing `test_concurrent_creates_receive_distinct_record_numbers`. |
| Filters | PASS. Combined source and created-date filter. Empty search does not hide rows. A future created-from returns an empty page with total 0. Invalid sort, direction, source, form id, dates, limit, and offset return 422. `2026-13-01` is rejected. |
| Sort allowlist and tie-break | PASS. Unknown sort is 422. Equal `created_at` values return in `records.id` order. |
| Pagination | PASS. `limit=1&offset=1` returns the middle number and the full total. `offset=50` returns no items and the same total. The UI sends `limit` 5, 25, or 50 and keeps Previous available when the later page is empty. |
| Soft delete | PASS. A second archive returns 404 and leaves `deleted_at` unchanged. Patch of that row is 404. The form version, public number, and `record_values` remain. Search total for that text is 0. |
| Authorization | PASS. A project member cannot patch another member's record. The member list total is 1 and contains only that member's row. Existing cross-tenant, removed-member, and CSRF tests still pass. |
| No new migration | PASS. `005_records.sql` was not changed. |
| Restore, status, assignee, duplicates | Not implemented. See the audit. |

## Files

Modified (4):

- `backend/app/api/records.py` — created-from and created-to must be real calendar dates
- `backend/tests/test_records.py` — filters, sort, pagination, custom fields, sequence rollback, repeated archive, member edit denial
- `frontend/src/features/records/RecordsPanel.tsx` — page size 5, 25, or 50, default 25; empty later page keeps Previous
- `frontend/tests/records.test.tsx` — empty later page and page size request

New (7):

- `docs/sprints/crm-s7/technical-acceptance.md`
- `docs/sprints/crm-s8/scope-and-overlap-audit.md`
- `docs/sprints/crm-s8/record-demo.mjs`
- `docs/sprints/crm-s8/recording.webm`
- `docs/sprints/crm-s8/explanation-script.md`
- `docs/sprints/crm-s8/implementation-report.md`
- `docs/sprints/crm-s8/technical-validation.md`

That is 4 modified files and 7 new files. The limit is 10 modified and 20 new. `project_access.py` was not changed.

## Tests

Backend, from `backend`, `.\.venv\Scripts\python -m pytest -q --tb=line`:

**42 passed**, 1 Starlette `httpx` deprecation warning, in 8.44 seconds.

Frontend, from `frontend`, `npm test`:

**32 passed** (5 files) in 8.38 seconds. npm warned that `devdir` is an unknown env config.

`npx tsc --noEmit` from `frontend` exited 2. The errors are the existing baseline in `src/lib/config.ts`, `tests/form-versions.test.tsx`, and `vite.config.ts`. They are unchanged from `docs/sprints/crm-s7/technical-acceptance.md`. Vitest does not use this check.

## Database

No migration ran. The shared development file was not reset. The browser and API captures added rows on Recording gate. Read-only check after the successful recording:

| Number | Name | Source | Archived |
|---|---|---|---|
| S2-REC-0001 | North school | manual | no |
| S2-REC-0002 | West campus | manual | no |
| S2-REC-0003 | North campus | manual | yes |
| S2-REC-0004 | North campus | manual | yes |
| S2-REC-0005 | East campus | phone_call | yes |
| S2-REC-0006 | Page lane | website | no |
| S2-REC-0007 | Page row | website | no |
| S2-REC-0008 | Page seat | website | no |
| S2-REC-0009 | East campus | phone_call | yes |
| S2-REC-0010 | Page lane | website | no |
| S2-REC-0011 | Page row | website | no |
| S2-REC-0012 | Page seat | website | no |

S2-REC-0005 through S2-REC-0008 are from the capture attempt that stopped before the member step. S2-REC-0009 through S2-REC-0012 are from the successful recording. S2-REC-0002 was edited from North school to West campus. Projects and memberships were not changed by this pass.

## Authorization

`authorize_record` is unchanged. List, filter, sort, and pagination still apply tenant, project, and assignee scope before rows and counts. A member list total does not include another person's record. Denied detail and edit stay 404 without the record text.

## Browser evidence

- `docs/sprints/crm-s8/recording.webm` — 6,618,082 bytes, VP9, 1280×720, 102.20 seconds
- `docs/sprints/crm-s8/explanation-script.md`
- `docs/sprints/crm-s8/record-demo.mjs`

The successful capture exited 0 and logged `RECORD S2-REC-0009`, `SEEDED S2-REC-0010,S2-REC-0011,S2-REC-0012`, then `filter-and-sort`, `paginate`, `archive`, `member-denied`, and `done`.

Frames confirm version 1 School name on the S2-REC-0002 edit, Record capture version 2 with Campus and East campus, Phone Call plus Record number sort, page size 5 with "Showing 1–5 of 9", the next page including S2-REC-0011 and S2-REC-0012, the search box `S2-REC-0009`, and the sidebar note "Records is not available for this sign-in."

The direct-address permission sentence is not in the extracted frames. The file ends on "Checking access." The empty-result sentence is under the filter form and was not in the sampled frame. Those waits succeeded in the capture script. This validation does not claim they were seen.

## Known limitations

- Original roadmap Sprint 6 is not started.
- There is no restore route and no retention period.
- FORM-08 flags were not added. Custom values remain searchable through `search_text`.
- `npx tsc --noEmit` is not clean.
- The development database now has the extra Recording gate rows listed above.
- The sprint status workbook was not updated.
