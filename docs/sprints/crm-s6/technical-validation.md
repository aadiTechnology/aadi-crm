# CRM-S6 technical validation — form versioning, preview, and internal renderer

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane change was made in this pass.

This is original Sprint 4. Evidence stays in `docs/sprints/crm-s6/`. `docs/sprints/crm-s4/` is the earlier membership and record-decision sprint, including its recording and implementation report. Those files were not replaced.

The implementation was already on `main` in `6670c59`. This pass checked it against the PRD and the sprint scope, added the missing publish review, re-ran the suites, and recorded the current workspace.

Owner acceptance of Sprint 4 is still pending.

## Requirements checklist

The PRD v1.0 dated 9 October 2026 is not in this repository. The source copy used is `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`.

| Requirement | This sprint |
|---|---|
| Stable form identity, with draft edits on `form_definitions` and `form_fields` | Delivered |
| Monotonic version number and immutable `schema_json` snapshot | Delivered. Database triggers abort update and delete of `form_versions` |
| `current_published_version_id` points at the latest published row | Delivered |
| Publisher and timestamp stored from the authenticated user | Delivered |
| Tenant and project ownership on every version | Delivered |
| Future records can store `form_versions.id` as `form_version_id` | Documented on the migration. No record table was created |
| Draft edit does not change version 1. Version 2 does not change version 1 | Delivered and tested |
| Re-publishing an unchanged draft returns 409 and does not insert a row | Delivered |
| Concurrent publishes cannot share a version number | Delivered |
| A failed publish leaves the previous version in place | Delivered |
| Empty forms, missing options, and invalid ranges are rejected with 422 | Delivered |
| Internal draft preview does not publish, save a record, or change the schema | Delivered |
| Publish is a server action with a review step that explains immutability | Delivered in this pass. Confirm publish sends the request. Cancel publish does not |
| Authorized internal render uses the frozen snapshot | Delivered |
| Historical version read stays available after a newer publish | Delivered |
| Public preview, public submission, record CRUD, workflow, conditional logic, reusable tenant picklists | Not this sprint |

FORM-06 asks for an internal preview and a public preview. The approved sprint scope excludes a public or customer-facing renderer. Public preview was not added. FORM-05's record retention is the `form_version_id` contract only. DEC-03 says project-manager publish should be configurable and off until an owner approves it. This sprint still lets a project manager publish, because that role already administers the draft. That remains an owner decision. No Control Plane permission was added.

## Files in this pass

Modified (4):

- `frontend/src/features/forms/FormsPanel.tsx` — publish review before the existing publish call
- `frontend/tests/form-versions.test.tsx` — cancel does not post; confirm publishes version 1 and version 2
- `docs/sprints/crm-ui-s1/implementation-report.md` — closure pointer only
- `docs/sprints/crm-s6/implementation-report.md` — pointer to this validation

New (4):

- `docs/sprints/crm-ui-s1/technical-acceptance.md`
- `docs/sprints/crm-s6/technical-validation.md`
- `docs/sprints/crm-s6/acceptance-explanation-script.md`
- `docs/sprints/crm-s6/recording-acceptance.webm`

The original Sprint 4 commit remains 8 new files and 10 modified files. This pass did not add an eleventh product source file. No dependency was added.

## Migration and database

`004_form_versions.sql` was already applied. This pass did not add a migration and did not reset `backend/data/aadi_crm.sqlite`.

A read-only check showed migrations `001` through `004`. Recording gate, Harbor gate, Live gate, Enquiry draft, Site enquiry, and Version check were still present. Enquiry draft is still unpublished.

The browser capture created four additional forms on Recording gate: Closure check, Closure review, Closure evidence, and Closure gate. The first three are from capture attempts that failed before the member denial. Closure gate is the form in `recording-acceptance.webm`. Version 1 of Closure gate snapshots the School name label. Version 2 snapshots the Campus label. No membership row was changed.

## Tests

Backend, from `backend` with the project virtualenv, before the frontend-only publish review:

`python -m pytest -q --tb=line` → **34 passed**, 1 Starlette `httpx` deprecation warning, in 5.98 seconds. No backend file changed after that run.

Frontend, from `frontend`, after the publish review:

`npm test` → **29 passed** (10 shell, 11 project, 4 form, 4 form-version) in 7.97 seconds.

`npx tsc --noEmit` still fails on `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. The classification is in `docs/sprints/crm-ui-s1/technical-acceptance.md`. Those failures are not a clean build and are not hidden here. They do not fail Vitest.

The backend version tests cover numbering, snapshot immutability, draft versus published separation, validation failures, authorization and cross-scope 404 responses, duplicate and concurrent publication, internal retrieval, and migration compatibility with existing drafts.

## Authorization

Unchanged from the Sprint 4 matrix:

| Action | Project manager | Active project member | Removed, non-member, other project, other tenant |
|---|---|---|---|
| Preview and publish | Yes | No, 403 for an active member | No, 404, without the form name |
| List and render a version | Yes | Yes | No, 404 |

The live recording shows the project manager publishing Closure gate and `playwright-member@example.com` being told Forms is not available, then "You do not have permission to perform this action." on the Closure gate address. Publish version is not shown for that sign-in.

## Browser evidence

- `docs/sprints/crm-s6/recording-acceptance.webm`
- `docs/sprints/crm-s6/acceptance-explanation-script.md`

The earlier `docs/sprints/crm-s6/recording.webm` remains the pre-redesign capture. It does not show the publish review.

## Known limitations

- Sprint 4 is not closed. Owner review is still required.
- Public preview and record storage are not implemented.
- DEC-03 project-manager publish configuration is unresolved.
- `tsc --noEmit` is not clean.
- Closure check, Closure review, and Closure evidence remain on Recording gate from the failed capture attempts.
- No commit, push, merge, or deployment was performed.
