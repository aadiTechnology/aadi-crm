# CRM-S8 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change was made for this pass.

Sprint 5 is formally closed in `docs/sprints/crm-s7/technical-acceptance.md`. This pass is not accepted. Owner review is still required.

## Scope

The owner asked this execution to implement create, list, view, edit, custom fields, project record numbers, filters, sorting, pagination, and soft delete.

That list is original roadmap Sprint 5, already delivered under `docs/sprints/crm-s7`. It is not original roadmap Sprint 6. Original roadmap Sprint 6 remains assignment, configurable statuses, duplicate detection, and a terminal reason. It was not started. The status workbook was not modified. The discrepancy is recorded in `docs/sprints/crm-s8/scope-and-overlap-audit.md`.

Reused without a new path: create, list, detail, edit, published-schema custom fields, `{project.code}-{sequence:04d}`, search, form, source, and created-date filters, the sort allowlist, `{ items, total, limit, offset }`, and archive through `deleted_at`.

Extended:

- Created-date filters reject a value that matches `YYYY-MM-DD` but is not a real day.
- The list can request page size 5, 25, or 50. The default stays 25.
- An empty later page shows "No records on this page" and still offers Previous.
- Tests cover invalid filters and sorts, pagination past the end, equal-timestamp ordering, custom-field validation, a rejected create that does not consume a number, a second archive, and a member who cannot edit another person's record.

Deferred: restore, retention period, FORM-08 flags, status filters, assignee filters, saved views, assignment, statuses, and duplicate detection.

## File counts

4 modified files and 7 new files. The limit is 10 modified and 20 new. The lists are in `technical-validation.md`.

## Migration and database safety

No migration was added. `005_records.sql` was not edited. The shared development database was not reset. Disposable tests still use temporary SQLite files. The recording added rows on Recording gate, listed in `technical-validation.md`. Projects and memberships were not changed.

## Tests

Backend: `.\.venv\Scripts\python -m pytest -q --tb=line` from `backend` → **42 passed**, 1 Starlette `httpx` deprecation warning, in 8.44 seconds.

Frontend: `npm test` from `frontend` → **32 passed** in 8.38 seconds.

`npx tsc --noEmit` from `frontend` exited 2 on the existing baseline in `src/lib/config.ts`, `tests/form-versions.test.tsx`, and `vite.config.ts`. Those failures remain visible.

## Authorization

`authorize_record` was not changed and was not weakened. Filters, sort, and pagination run after tenant, project, and assignee scope. A member's list total does not include another person's record. Cross-tenant, removed-member, and missing-CSRF cases remain in the existing tests.

## Evidence

- `docs/sprints/crm-s8/recording.webm`
- `docs/sprints/crm-s8/explanation-script.md`
- `docs/sprints/crm-s8/record-demo.mjs`
- `docs/sprints/crm-s8/technical-validation.md`
- `docs/sprints/crm-s8/scope-and-overlap-audit.md`
- `docs/sprints/crm-s7/technical-acceptance.md`

## Known limitations

- The direct-address permission sentence is not visible in the extracted recording frames. The file ends on "Checking access." The capture script waited for the sentence and exited 0.
- "No matching records." sits under the filter form and was not in the sampled frame.
- S2-REC-0005 through S2-REC-0012 and the West campus edit of S2-REC-0002 remain on Recording gate.
- There is no restore route. The PRD retention period is still undefined.
- `npx tsc --noEmit` is not clean.
- The sprint status workbook was not updated.

## Confirmation

Sprint 5 was closed against its acceptance checks. Sprint 6 in the sense of this execution is implemented only as reuse plus the extensions above, and it is not accepted. Original roadmap Sprint 6 was not started.

No commit, push, merge, tag, or deployment was performed in this pass. The Sprint 5 implementation was already on `main` at `315c1e3` before this review. This pass did not create that commit.
