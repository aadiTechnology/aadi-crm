# CRM-UI-S1 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. Branch: `main`. No commit, push, merge, tag, deploy, Control Plane change, database migration, or backend contract change.

Technical acceptance is recorded in `docs/sprints/crm-ui-s1/technical-acceptance.md`. The owner had already approved the screen design in `recording.webm`. CRM-UI-S1 is closed. A later form-versioning pass added a publish review on the form builder; that change is Sprint 4 scope and is not part of this UI closure.

## Summary

The CRM shell, project screens, and form builder were restyled as one workspace. The frontend does not include Material UI. React 19, TypeScript, Vite, and React Router 7 were already in use, so the design system is CSS custom properties and a small shared component module. No dependency was added.

Colors, type, spacing, radii, focus, and reduced-motion rules live in `frontend/src/styles.css`. Primary actions use `#2563EB`. Surfaces, text, borders, and status colors follow the sprint palette. The existing Segoe UI font remains, with Inter and system-ui as fallbacks.

## Routes and screens

Existing routes in `frontend/src/main.tsx` were not changed.

Updated presentation:

- Sign-in and the access check
- Organization list
- Workspace overview, including the existing leads entry
- Project list, search, create, detail, edit, archive, and membership
- Form project list, form list, create, builder, preview, and published render

Preview and published version controls were kept because they already work. No new versioning behavior was added.

## Shell

Signed-in pages use a left navigation column and a top bar. The top bar shows the page name, the organization display name, the organization line, the signed-in address, and Sign out. Leads, Projects, and Forms stay hidden unless the existing permission checks allow them. There is no global search box and no notification control, because the app has no global search or notification API. Project search remains on the projects page.

The sidebar collapses on a wide window. Below 960 pixels it becomes an off-canvas drawer opened with Open navigation. Overview is the tenant home. It does not invent dashboard metrics.

## Projects

Project list items are cards with the name, code, description, and an Active or Archived badge. Search and the status filter still call `listProjects` with the same arguments. Create and edit validation messages are unchanged. Archive is still one click for a manager of an active project. A second confirmation dialog was not added, because the current workflow and tests treat archive as that single action. Search text and the status filter stay in the mounted projects panel when a project is opened and the user returns.

## Form builder

On a wide window the builder is three regions:

- Field palette, grouped as Text, Contact, Value, Choice, and Definition only
- Form canvas, in the existing field order, with required and selected styling
- Field properties, using the existing add and edit form

Choosing a palette type sets the field type on the add form. Reordering still uses Move up and Move down. Field identifiers stay immutable after creation. Dropdown, multi-select, and radio still use `value|label` lines. File and auto-number fields say that upload and number generation are not available. Below 960 pixels the three regions stack. Drag and drop was not added.

Form name and description show "Unsaved form details" when they differ from the loaded draft. Saving a field, the form details, or a version shows a short success message. Server validation is unchanged.

## Components

Created: `frontend/src/ui/chrome.tsx` (`StatusBadge`, `EmptyState`, `LoadingSkeleton`, `NavIcon`).

Reused: `CrmShellPage`, `ProjectsPanel`, `FormsPanel`, `FormRenderer`, and the existing platform client. `FormRenderer` was not modified.

## Files

New source: `frontend/src/ui/chrome.tsx` (1).

New evidence: `docs/sprints/crm-ui-s1/recording.webm`, `docs/sprints/crm-ui-s1/explanation-script.md`, `docs/sprints/crm-ui-s1/implementation-report.md` (3).

Modified: `frontend/src/styles.css`, `frontend/src/features/shell/CrmShellPage.tsx`, `frontend/src/features/projects/ProjectsPanel.tsx`, `frontend/src/features/forms/FormsPanel.tsx` (4).

Total new files: 4. Total modified files: 4. The limit was 20 new and 10 modified.

## Tests

Baseline, before edits, from `frontend`:

`npm test` → **29 passed** (10 shell, 11 project, 4 form, 4 form-version).

Final, after the last source edit, from `frontend`:

`npm test` → **29 passed** (same files).

`npx tsc --noEmit` was also run. It reports existing errors in `frontend/src/lib/config.ts`, `frontend/tests/form-versions.test.tsx`, and `frontend/vite.config.ts`. Those files were not part of this sprint. The project test script is `vitest run`, and that passed.

Backend tests were not run. No backend file was changed.

## Browser verification

Desktop frames were checked at 1280×720. A mobile frame was checked at 390×720. The checked flows were sign-in, the organization shell, sidebar collapse, project search, the empty search result, create-project validation, Recording gate, the Enquiry draft builder, a palette type change, a saved and then restored help text, the stacked narrow layout, and the return to Overview. One Tab after that return focused the Leads link.

The recording is `docs/sprints/crm-ui-s1/recording.webm`. `ffprobe` reports duration 36.12 seconds and size 2,894,439 bytes. The file header is the WebM EBML marker. The capture script exited 0. Narration: `docs/sprints/crm-ui-s1/explanation-script.md`.

## Authorization and contracts

Frontend routes, API functions, CSRF headers, and permission gates were not changed. Projects and Forms links are still omitted when `canOpenProjects` is false. The existing denial copy remains. Field payloads are still built by the previous `buildFieldInput` function. No new endpoint, permission, or migration was added.

## Known limitations

- CRM-UI-S1 is closed in `technical-acceptance.md`. `npx tsc --noEmit` is still not clean.
- Overview is sparse because the product has no dashboard data.
- The availability line is repeated on later pages.
- Archive does not ask for a second confirmation.
- Field reordering is still by button, not drag and drop.
- The unsaved hint covers form name and description, not a half-finished field draft, and navigation is not blocked.
- File and auto-number fields can be configured and still do not upload a file or issue a number.
- Search and filter state is kept in the open projects panel, not in the address.
- `npx tsc --noEmit` still fails on the pre-existing files named above.
- No commit, push, merge, or deployment was performed.
