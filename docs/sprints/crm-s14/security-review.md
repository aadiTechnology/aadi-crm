# Security review — original roadmap Sprint 12

Date: 21 October 2026. Repository: `aadi-crm` only. The Control Plane was not modified.

This review covered the CRM route modules: shell, projects, forms, records, follow-ups, reminders, imports, reporting, and audit. Isolated tenants in the existing tests are `TENANT_A` and `TENANT_B` with separate user ids. Those tests use a platform double and a temporary SQLite file.

## Result

No confirmed high-severity defect was found. No authorization check was removed. No new permission key was added.

## Checks

| Required check | Result | Evidence |
|---|---|---|
| Tenant A cannot read or modify Tenant B | PASS | `test_cross_tenant_read_and_mutation_are_hidden`, `test_cross_tenant_leads_call_does_not_use_the_other_tenant`, form, record, follow-up, import, reminder, and KPI tests |
| Project A does not open Project B without access | PASS | Record, form, and import tests deny the other project and omit its text |
| A removed member loses record access | PASS | Membership status must be `active` in `access_for`. Reminder test checks the inbox after removal and does not return the record number |
| A stale reminder, import job, or link does not bypass current authorization | PASS | Import job and error report return 404 for another member. Reminder read is limited to `recipient_user_id`. Retry is limited to projects the caller currently manages. Record links still call `authorize_record` |
| Error reports and exports use the same authorization as records | PASS | `test_authorization_duplicate_visibility_and_export_filters`. A member export of another assignee's records returns zero rows |
| A client tenant or project id does not replace the trusted context | PASS | `test_query_and_body_tenant_ids_do_not_select_the_platform_tenant`. `_open_module` returns 404 when product access `tenant_id` differs from the path. Import comments and tests keep file columns as cell text |
| CSRF on state-changing requests | PASS | `_csrf_matches` uses `compare_digest`. Missing header returns 401 in project, record, form, follow-up, and import tests |
| Authentication and permission denial stay generic | PASS | 401 and 403 bodies use the fixed messages. Foreign names are asserted absent |
| Duplicate and import results do not reveal another tenant or project | PASS | The import authorization test shows one same-project candidate and does not include the other project's name |
| Audit and KPI responses do not leak unauthorized scopes | PASS | KPI cross-tenant response is 404 and omits the project name. A member KPI omits the other assignee's form, title, and owner. Audit metadata is stripped. A caller without `audit.read` receives 403 |

## Residual items

| Severity | Item | Why it remains |
|---|---|---|
| Medium | Organization audit is not project-scoped | The platform route that CRM forwards has no project filter. Anyone with CRM module access and platform `audit.read` can read that tenant's returned events. This is the Sprint 11 design |
| Low | A removed member can still open their reminder rows | The row no longer includes `project_id`, `record_id`, or `public_number` when `authorize_record` fails. The email body says it does not include the customer record. Changing inbox retention is an owner decision |
| Low | Failure review is limited to active `project_manager` rows | `managed_project_ids` does not treat `crm.project_management.manage` alone as a manager of every project. A tenant administrator who is not a project manager gets 403 on the failure list |

## What was not weakened

`authorize_record`, project membership, the module check, and CSRF were not changed to make a test pass.
