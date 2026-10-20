# CRM-S5 implementation report

Date: 20 October 2026. Repository: `aadi-crm` only. No commit, push, merge, tag, deploy, or Control Plane source or database change.

This is original Sprint 3: form definitions and fields. Evidence is stored under `crm-s5` so `docs/sprints/crm-s2/`, `docs/sprints/crm-s3/`, and `docs/sprints/crm-s4/` stay untouched. The sprint is not closed. It is waiting for review.

## Source of the requirements

The original sprint plan row is "Form builder: definitions & fields": draft forms, stable field keys, ordering and sections, required rules, supported field types, and configurable picklists. Public forms, a customer portal, OTP, and advanced conditional logic are excluded. Versioning, preview, and publishing are the next feature sprint. Records are later.

The PRD v1.0 file is still not in this repository. It is on this machine at `C:\Users\lenovo\Downloads\Aadi_Technology_Multi_Tenant_CRM_PRD_v1.0 (1).docx`. FORM-02 lists the field types implemented here. FORM-05, FORM-06, and FORM-07 are later or excluded. FORM-04's reusable tenant picklists are not implemented. Each picklist is stored on its field.

## Authorization

No new Control Plane permission was added. `crm.lead_management.read` was not broadened.

Opening the form module uses the existing project-module gate: CRM product access plus `crm.lead_management.read` or `crm.project_management.manage`. `users.read` alone is denied. `crm.project_management.manage` is still not registered. If a later registration grants it, that key remains the only tenant-wide project administration key, and it can administer forms through the existing tenant-admin path.

Inside a project:

| Action | Project manager | Project member | No active membership |
|---|---|---|---|
| List and read form definitions | Yes | Yes | No, hidden as 404 |
| Create or update a form | Yes | No | No |
| Add, edit, reorder, or remove a field | Yes | No | No |

A cross-project or cross-tenant read returns 404 and does not include the form name or field label. Writes require the `aadi_csrf` cookie and a matching `X-CSRF-Token` header.

Archive follows the current project policy. Archiving does not remove the manager role and does not block project updates, so it does not block form administration either. A project member of an archived project can still read forms and still cannot change them.

## Data model

`backend/migrations/003_form_definitions.sql` adds `form_definitions` and `form_fields`. Both rows carry `tenant_id` and `project_id`. A form name is unique per project without regard to case. A field identifier is unique per form without regard to case. Field position is unique per form and starts at 0. There is no form-version table.

Supported field types are `text`, `long_text`, `number`, `mobile`, `email`, `url`, `date`, `time`, `dropdown`, `multi_select`, `radio`, `checkbox`, `currency`, `file`, and `auto_number`. Dropdown, multi-select, and radio require at least one option with a stable value. The field identifier is set at creation and cannot be changed. File and auto-number rows store definition settings only. This sprint does not upload a file or generate a number.

Removing a field deletes that row and renumbers the remaining positions. No CRM record exists yet, so the PRD rule about historical values cannot be enforced here. A later record sprint has to stop removal of a field that already has values.

## API

Every route checks the path tenant through Control Plane product access and permissions, then project membership.

| Method | Path | Success |
|---|---|---|
| `GET` | `/api/v1/tenants/{tenant_id}/projects/{project_id}/forms` | `200` `{ "items" }` |
| `POST` | same | `201` draft form |
| `GET` | `.../forms/{form_id}` | `200` |
| `PATCH` | `.../forms/{form_id}` | `200` name and description |
| `POST` | `.../forms/{form_id}/fields` | `201` form with the new field appended |
| `PATCH` | `.../fields/{field_id}` | `200` form. The identifier is rejected if sent. |
| `POST` | `.../fields/reorder` | `200` form. The body must list each field once. |
| `POST` | `.../fields/{field_id}/remove` | `200` form. Remaining positions are packed from 0. |

Duplicate form names and duplicate field identifiers return 409. Invalid types, empty picklists, and a minimum greater than a maximum return 422.

## Migration and data safety

The migration was applied twice to a disposable database that already had an active project, an archived project, an active manager membership, and a removed member membership. Both project rows, both statuses, and both membership rows stayed. The form tables were empty. A second apply did not insert another version row.

The same check was run against a copy of `backend/data/aadi_crm.sqlite`. The copy gained `003_form_definitions.sql`. The original file's project rows, membership rows, and version list were unchanged by that copy. The running CRM process uses `--reload` and then applied the additive migration to the development file on its own startup path. After that apply the development file still has versions `001_projects.sql`, `002_project_memberships.sql`, and `003_form_definitions.sql`, three projects (S2-DEMO Harbor gate archived, S2-LIVE Live gate archived, S2-REC Recording gate active), and five membership rows. No project or membership row was deleted.

The browser recording then created two draft forms on Recording gate: Enquiry draft, from an incomplete first pass, and Site enquiry, from the recording. Projects and memberships were not changed.

## Tests actually run

Backend, from `backend` with the project virtualenv:

`python -m pytest -q` → **27 passed**, 1 warning. The warning is Starlette's deprecation notice that `httpx` with `starlette.testclient` should move to `httpx2`.

Frontend, from `frontend`:

`npm test` → **25 passed** (10 shell, 11 project, 4 form). npm also printed an environment notice that `devdir` is an unknown env config. That is not a test failure.

Backend tests use an in-process platform double and a temporary SQLite file. They cover create, update, field add, edit, reorder, reload, removal, duplicate identifiers, invalid types, empty picklists, an invalid number range, a project member refused administration, a non-member 404, another project, another tenant, `users.read` without a CRM permission, missing CSRF, and form writes on an archived project. The existing project and membership tests still pass, including preservation of an archived project across the new migration. They are not the live recording.

## Recording

`docs/sprints/crm-s5/recording.webm` (47 seconds, 1280×720). Narration: `docs/sprints/crm-s5/explanation-script.md`.

The browser used the running Control Plane and the running CRM shell. It shows sign-in, the organization, creation of Site enquiry, a required text field, a dropdown, reorder, the duplicate-identifier error, the same order after reload, and an unknown project id returning not found.

## Files

New: `backend/migrations/003_form_definitions.sql`, `backend/app/forms_store.py`, `backend/app/api/forms.py`, `backend/tests/test_forms.py`, `frontend/src/features/forms/FormsPanel.tsx`, `frontend/tests/forms.test.tsx`, and the three files in `docs/sprints/crm-s5/` (9).

Modified: `backend/app/project_access.py`, `backend/app/main.py`, `backend/tests/test_projects.py`, `frontend/src/main.tsx`, `frontend/src/features/shell/CrmShellPage.tsx`, `frontend/src/services/platform.ts`, `frontend/tests/projects.test.tsx` (7).

## Known limitations

- The sprint is not closed.
- Form versioning, preview, publishing, and CRM records are not in this sprint.
- Reusable tenant-level picklists, conditional fields, reporting flags, and public forms are not implemented.
- File and auto-number fields can be defined. They do not upload a file or issue a number.
- Field removal is allowed because no record values exist.
- `crm.project_management.manage` is still not registered.
- The development database now contains Enquiry draft and Site enquiry on Recording gate. Memberships were not edited.
- The 19 October status workbook was open in Excel and could not be overwritten. The updated tracker is `C:\Users\lenovo\AadiTech\Product\CRM\Aadi_CRM_Sprint_Plan_Status_Updated_2026-10-20.xlsx`.
