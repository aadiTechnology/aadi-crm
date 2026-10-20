# CRM-S8 technical acceptance

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made for this closure.

## Numbering

`docs/sprints/crm-s8` is the evidence folder for the record-experience enhancement pass. It is not original roadmap Sprint 8.

| Scheme | Sprint 6 | Sprint 7 |
|---|---|---|
| This execution | Record-experience enhancements, evidenced in `docs/sprints/crm-s8` | Activity timeline and follow-ups, to be evidenced in `docs/sprints/crm-s9` |
| Original 12-sprint roadmap | Assignment, configurable statuses, duplicate detection, and a terminal reason. Not started. | Activity timeline and follow-ups |

Original roadmap Sprint 6 stays unstarted. This closure does not mark it complete.

## Decision

**CLOSED** against the technical checks below. Owner review of this closure is still required. This document does not accept the work on the owner's behalf.

## CRM-UI-S2 design status

CRM-UI-S2 is separate from this technical acceptance. `docs/sprints/crm-ui-s2/implementation-report.md` records the compact records filter panel, the server-paged table, and tenant-configuration branding. No owner-approval record for that UI design was found in the repository. This closure does not treat the implementation report as owner approval.

## Acceptance criteria

| Check | Status | Evidence |
|---|---|---|
| Create, list, view, and edit reuse the existing record paths | PASS | `create_record`, `list_records`, `get_record`, and `update_record` are unchanged as the only record write path. `test_record_keeps_its_published_version_through_search_edit_and_archive` passed. |
| Custom fields stay on the published snapshot | PASS | Existing custom-field test passed in the backend suite. |
| Project record numbers stay server-generated | PASS | Existing concurrent-number test passed. |
| Search, filters, sort, page size, and pagination work together | PASS | `test_list_filters_sort_and_pages_stay_inside_the_project` and the records UI tests passed. |
| Changing filters returns to the first page | PASS | Frontend test `renders a server-paged table and clears only the search filters` asserts offset `0` after search. |
| Clear resets search, form, source, and dates, returns to page 1, and keeps sort and page size | PASS | `onClear` in `RecordsPanel.tsx` and the same frontend test. |
| Created-date validation is server-side | PASS | `_calendar_date` rejects values that are not real calendar days. Invalid dates are covered by the records API tests. |
| Page sizes are 5, 25, and 50, default 25 | PASS | `PAGE_SIZES` and the page-size frontend test. |
| Soft delete preserves the row and hides it from normal results | PASS | Existing repeated-archive test passed. `deleted_at` is set. List and detail exclude the row. |
| Tenant branding reloads with tenant context | PASS | The shell effect loads product access, permissions, and configuration for the path tenant. Branding tests passed. |
| Configuration 403 or 404 keeps the platform palette | PASS | `readBranding` returns null for 403 and 404. The shell test for a configuration 403 leaves `.app` without an inline style. The 404 configuration test does not render the error payload. |
| Record detail, historical form versions, and authorization stay intact | PASS | Detail test still shows version 1 School name. `authorize_record` was not changed. |
| No new tenant or project data leak in list counts | PASS | Existing assigned-scope list test passed. Assignee scope is applied before the count. |

No critical security defect, data-integrity defect, or regression was found. Original roadmap Sprint 6 was not started.

## Tests and build

Commands run on 20 October 2026 against the tree at `476fd6e` before the follow-up work.

Backend, from `backend`:

`.\.venv\Scripts\python -m pytest -q --tb=line`

**42 passed**, 1 Starlette `httpx` deprecation warning, in 15.39 seconds.

Frontend, from `frontend`:

`npm test`

**35 passed** (5 files) in 11.81 seconds. npm warned that `devdir` is an unknown env config.

`npx vite build` from `frontend` completed. Output is under `frontend/dist`, which is gitignored.

`npx tsc --noEmit` from `frontend` exited 2. These are the existing baseline errors, not new regressions:

- `frontend/src/lib/config.ts` — `ImportMetaEnv` has no properties in common with the config type
- `frontend/tests/form-versions.test.tsx` — `FormVersion` status is not assignable to `"published"`
- `frontend/vite.config.ts` — cannot find `node:path`; `import.meta.dirname` is missing

The records, shell, and styling files from the record-experience pass are not in that error list.

## UI and responsive validation

This closure re-ran the automated UI tests. It did not make a new recording. The prior browser evidence remains:

- `docs/sprints/crm-s8/recording.webm`
- `docs/sprints/crm-ui-s2/implementation-report.md` browser check at 1280, 741, and 390 pixels

The records tests cover the compact table, combined filters, clear behavior, page size, and an empty later page.

## Authorization and tenant configuration

`authorize_record` is unchanged. List filters and counts still apply tenant, project, and assignee scope. A configuration 403 or 404 does not replace the platform palette.

## Known limitations

- Original roadmap Sprint 6 (assignment, statuses, duplicate detection, terminal reason) is not started.
- There is no restore route and no retention period.
- FORM-08 searchable flags were not added.
- `npx tsc --noEmit` is not clean.
- The sprint status workbook was not modified by the earlier record-experience pass. This closure does not mark original roadmap Sprint 6 complete. A later update in this same working tree sets original Sprint 7 to implemented and awaiting acceptance. Original Sprint 6 stays Planned.
- CRM-UI-S2 has an implementation report and no recorded owner approval.

## Confirmation

No commit, push, merge, tag, or deployment was performed for this closure.
