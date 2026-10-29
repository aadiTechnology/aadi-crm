# CRM-UI-S1 technical acceptance

Date: 20 October 2026. Repository: `aadi-crm`. Branch: `main`, up to date with `origin/main` at the start of this pass (`acf4228`).

## Working tree

`git status --short` was empty before this pass. The CRM-UI-S1 files were already in commit `acf4228` (`Enhance UI components and styling for forms and projects`). Nothing was discarded, reset, stashed, or reformatted to clear them.

That commit contains the four new and four modified files named in the implementation report:

New:

- `frontend/src/ui/chrome.tsx`
- `docs/sprints/crm-ui-s1/recording.webm`
- `docs/sprints/crm-ui-s1/explanation-script.md`
- `docs/sprints/crm-ui-s1/implementation-report.md`

Modified:

- `frontend/src/styles.css`
- `frontend/src/features/shell/CrmShellPage.tsx`
- `frontend/src/features/projects/ProjectsPanel.tsx`
- `frontend/src/features/forms/FormsPanel.tsx`

## Owner visual approval

The owner reviewed `docs/sprints/crm-ui-s1/recording.webm` and confirmed that the screen design looks good. This pass records that approval. It does not ask for another visual review. Narration: `docs/sprints/crm-ui-s1/explanation-script.md`. `ffprobe` on the committed file reports 36.12 seconds. The file is 2,894,439 bytes.

## Commands and results

From `frontend`, 20 October 2026:

`npm test` → **29 passed** (4 files: 10 shell, 11 project, 4 form, 4 form-version) in 8.68 seconds.

From `backend`, with `backend\.venv`:

`python -m pytest -q --tb=line` → **34 passed**, 1 warning, in 5.98 seconds. The warning is Starlette's deprecation notice that `httpx` with `starlette.testclient` should move to `httpx2`. It is not a failure.

From `frontend`:

`npx tsc --noEmit` → exit 2. The errors are listed under TypeScript below. Vitest does not use that check.

## Authorization and isolation

No backend file changed in CRM-UI-S1. The live and automated checks below are the acceptance evidence.

Backend:

- `test_publish_permissions_follow_project_role`: a project manager may preview, publish, and render. An active project member may render and may not preview or publish. A caller with no project role may not render.
- `test_render_is_limited_to_the_authorized_project`: removed members, non-members, another project, and another tenant receive 404 without the form name.
- `test_manager_and_member_form_permissions` and `test_member_archived_and_scope_boundaries`: form administration stays with the project manager. Members and out-of-scope callers do not edit forms.
- `test_create_requires_csrf_and_rejects_invalid_fields` and the form-version publish route: writes still require the CSRF cookie and matching header. Publish ignores a publisher id sent in the body.
- `test_cross_tenant_read_and_mutation_are_hidden` and `test_authentication_and_permission_boundaries`: cross-tenant project access stays hidden.

Frontend:

- `shows a duplicate identifier error and keeps a project member from editing`
- `shows an authorization failure without revealing another form`
- `lets a project member render a published version and hides publish`
- `does not reveal a form when a published version is not available`

Project and form field behavior that the redesign had to keep:

- `creates a form, saves fields, reorders them, and shows the same order after reload`
- `blocks an empty picklist before saving`
- `test_create_fields_reorder_reload_and_validation`

Live browser, signed in as `playwright-recording@example.com` against `http://localhost:5174`, the CRM API on port 8001, and the Control Plane on port 8000:

- Search `missing-ui-s1` shows "No projects match this search."
- Create project with empty fields shows "Project code is required." and creates nothing.
- Enquiry draft still shows "No published version yet." Preview shows "Draft preview. Required fields are marked. Nothing is saved." The preview read returned 200. No publish request was sent.
- Version check version 1 shows "Published version 1. This schema stays as it was published."
- An unknown project id shows "The requested resource was not found." The CRM API returned 404. The response text on the page does not include another project's name.

## Console and API noise

The live pass logged two repeated console errors, both pre-existing:

- `GET /favicon.ico` returns 404. The redesign did not add a favicon request of its own. Browsers request that path by default.
- `GET /api/v1/tenants/{tenant_id}/configuration` returns 403. `readBranding` has caught 403 and 404 since the first commit and returns no branding. The overview still shows "CRM is available in this organization."

CRM API calls for the opened project, the Enquiry draft, its version list, and its preview returned 200. The unknown-project 404 is the expected denial, not a new failed contract.

## TypeScript

`npx tsc --noEmit` still fails. None of these files are in the CRM-UI-S1 diff. They do not fail `npm test`, and they do not block the Sprint 4 runtime.

| File | Error | Classification |
|---|---|---|
| `frontend/src/lib/config.ts` line 56 | TS2559: `ImportMetaEnv` has no properties in common with the config env argument | Pre-existing. Not introduced by CRM-UI-S1 or by the form-version commit. |
| `frontend/tests/form-versions.test.tsx` line 206 | TS2769: a version `status` of `"current" \| "published"` is not assignable to the narrowed `"published"` literal inside the test double | Introduced with the Sprint 4 test in `6670c59`. Not introduced by CRM-UI-S1. Vitest passes. |
| `frontend/vite.config.ts` lines 1 and 9 | TS2307: cannot find `node:path`. TS2339: `ImportMeta.dirname` is missing | The Sprint 4 commit added only `testTimeout`. The module and `dirname` errors are the missing Node types around the existing Vite config. Not introduced by CRM-UI-S1. Vitest runs. |

Accepted exception: these three type-check failures stay visible. They were not patched in this pass. This is not a clean `tsc` build.

## Defects

No release-blocking authorization, contract, or redesign regression was found.

Remaining, non-blocking:

- `tsc --noEmit` fails as classified above.
- Favicon 404 and the handled configuration 403 still appear in the browser console.
- Overview remains sparse. Archive is still one action. Field order is still by button. Those limits are already in the implementation report.

## Decision

CRM-UI-S1 acceptance criteria passed. The sprint is closed.
