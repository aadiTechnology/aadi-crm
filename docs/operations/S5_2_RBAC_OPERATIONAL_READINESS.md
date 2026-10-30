# S5.2 CRM RBAC operational readiness

This note records the S5.2 audit decision, the navigation contract, the retained S5.1 fixtures, and the recovery steps for a later controlled release. It does not authorize a production migration or declare CRM RBAC production-ready.

## Audit architecture

The Control Plane owns audit events. Rows live in `audit_events`. Inserts go through `AuditService.append` inside the caller's transaction. Database triggers reject updates and deletes, so the log is append-only. Tenant readers load events with `GET /api/v1/tenants/{tenant_id}/audit-events`, which requires `audit.read`. The Control Plane audit router has no create, update, or delete route. `AppendAuditEventInput` is a service command, not an HTTP body. Metadata rejects secret-like keys such as passwords, tokens, cookies, and CSRF values.

CRM does not share the Control Plane database. `PlatformClient.list_audit_events` only forwards the authenticated GET and drops metadata before the CRM audit screen renders it. CRM has no local audit table and no write client.

### Decision

S5.2 does not record the seven CRM role and assignment events, and it does not add a CRM audit table. The existing HTTP API cannot accept those events. Inventing a new browser-facing create route, or a second store, would be a new integration contract.

### Smallest later extension

A future sprint can add a server-to-server append that only the CRM process can call. That call must enter the existing `AuditService.append` path and the same `audit_events` table. The server resolves the tenant and the actor. The body carries `action`, `resource_type`, `resource_id`, `summary`, `outcome`, and metadata. Suggested actions:

| Event | Action | Resource | Metadata |
| --- | --- | --- | --- |
| CRM role created | `crm.role.create` | role id | role name |
| CRM role updated | `crm.role.update` | role id | before and after name or description |
| CRM role deactivated | `crm.role.deactivate` | role id | prior status |
| CRM permission granted | `crm.role.permission.grant` | role id | permission key |
| CRM permission removed | `crm.role.permission.remove` | role id | permission key |
| CRM role assigned | `crm.role.assign` | role id | affected user id |
| CRM role assignment revoked | `crm.role.assignment.revoke` | role id | affected user id |

Store no passwords, session tokens, CSRF tokens, or other authentication secrets. Visibility stays on `audit.read`. Until that contract exists, role changes remain without an audit row.

## Navigation contract

`GET /api/v1/shell/tenants/{tenant_id}` now includes `module_permissions`. The CRM backend builds that list with `module_keys_for_member`, then keeps a catalog key only when the current product access entitles its feature. The catalog is `crm.lead_management.read`, `crm.project_management.access`, `crm.project_management.manage`, and `crm.records.access`. `roles.manage`, `users.read`, and `audit.read` are never copied into this list.

The shell uses that list for Leads, Projects, and Records. It still reads Control Plane permissions for `roles.manage`, `users.read`, and `audit.read`. The React shell does not intersect Control Plane CRM keys with role grants. Direct module routes keep their existing checks, so a hidden Leads link still returns 403 when the caller opens the leads API.

Rules that stay in force:

- No CRM assignment rows: Control Plane catalog keys remain, then the feature filter applies.
- Assignment rows exist but none are valid: the four catalog keys are omitted. There is no fallback.
- A missing subscription feature omits that key.
- A missing tenant membership returns 404 from product access and does not include `module_permissions`.
- Project Manager and Project Member checks are unchanged.

## Retained S5.1 fixtures

S5.1 committed rows on the disposable test databases. Do not delete, truncate, or reset `aadi_platform_test` or `aadi_crm_test`. Treat the rows below as retained fixtures. Later cleanup may delete only rows created by that later run, and only after `current_database()` matches the disposable database, the tenant id matches the run, and the row id belongs to the run. Do not delete existing audit events, published form versions, or these retained rows.

Control Plane database `aadi_platform_test`:

- Product `crm`: `b6582971-ad5d-4378-9818-cc5fdada45ca`
- Plan `s51-crm-full`: `b440503b-e8b0-4d31-9f5f-688c753dfe54`
- Plan `s51-crm-no-records`: `8fd73366-613b-45c3-b894-5cd227eddc98`
- Tenant `S51 CRM RBAC Validation`: `c22196b3-3cff-41bc-b4a4-6e239cea8635`
- Tenant `S51 CRM RBAC Limited`: `dcb1d7b7-8d64-46dc-9b73-0fbf43ecce4a`
- Tenant `S51 CRM RBAC Other`: `019dd6dc-ac89-4aa7-91df-29c866dd86eb`
- Tenant `S51 CRM RBAC Unsubscribed`: `d614de8d-c3c5-4fe0-b5cf-1287cdb08e6f`
- `s51.admin@example.test`: `c090b6fa-09ac-4312-b8e3-209b10edf7e8`
- `s51.assigned@example.test`: `e6af4bbb-24fb-4c15-91e6-aff500d8cbf4`
- `s51.unassigned@example.test`: `f74879ab-6c84-4a46-83e6-830883a41ed0`
- `s51.stale@example.test`: `48081b73-0788-4002-9745-8232ff81ead7`
- `s51.inactive@example.test`: `9c91fc85-193e-4d04-850b-cb9d4e9af323`
- `s51.rolesonly@example.test`: `ff268a21-3e20-4a8b-8219-a05a201b6bbd`
- `s51.inactive-member@example.test`: `defde377-7bf7-4ca1-9bc7-4afb5b9ffb1b`
- `s51.limited@example.test`: `434aee8f-7073-448c-bdbe-5cf73beed64f`
- `s51.other@example.test`: `93982615-7449-4633-97f4-f44907abad7f`
- `s51.nosub@example.test`: `4fe1172a-534b-4584-b49e-bdeeb74e293e`

CRM database `aadi_crm_test`, validation tenant `c22196b3-3cff-41bc-b4a4-6e239cea8635`:

- Role `S51 Leads only`: `b89b121f-ad6e-42ef-99a9-76ce6544a0f1` (inactive)
- Role `S51 Project and records`: `6c6ecaa7-6961-436b-b806-1104f46bba53`
- Projects `s51val` and `s51mgr`, one published form version for `S51 enquiry`, and the record whose school name is `S51 North`

Those CRM rows include assignment history. Leave the published form version in place. Form versions are immutable.

## Test-data isolation

CRM PostgreSQL tests run only when `CRM_TEST_DATABASE_URL` names `aadi_crm_test` on loopback port 5433 with role `aadi_crm_migrator`. `assert_disposable_test_database` refuses `aadi_platform`, `aadi_platform_test`, `aadi_crm`, and `aadi_crm_dev`. Each test uses a fresh tenant UUID and deletes only that tenant's role, assignment, project, and membership rows after confirming the connection is still `aadi_crm_test`. Those tests do not publish forms, because published versions cannot be deleted.

Control Plane tests install `DATABASE_URL` from `CONTROL_PLANE_TEST_APP_DATABASE_URL`. Most cases roll back. A committed test may delete only its own ids when the email matches the bootstrap, last-admin, or audit example domains, or the tenant name is on that test's allowlist. Audit cleanup refuses to run when any current audit row was not created by that test. A read-only check during S5.2 found `audit_events` empty on `aadi_platform_test`. If a later run leaves audit rows, that cleanup raises `Refusing to clear audit rows that this test did not create` instead of deleting them. Leave those rows. Do not truncate `audit_events` to make the suite pass.

Development databases `aadi_platform` and `aadi_crm_dev` stay closed during this work.

## Migrations

Apply CRM scripts in filename order from `backend/migrations/postgres`:

1. `001_projects.sql`
2. `002_project_memberships.sql`
3. `003_form_definitions.sql`
4. `004_form_versions.sql`
5. `005_records.sql`
6. `006_followups.sql`
7. `007_reminders.sql`
8. `008_imports.sql`
9. `009_tenant_roles.sql`
10. `010_tenant_role_assignments.sql`

`009` and `010` are additive. Do not edit them to reactivate roles. From `Product/aadi-crm/backend`, with `CRM_DATABASE_URL` set to the intended database:

```text
python -m app.migrate
```

The command prints the database name it migrated. It does not open SQLite. `CRM_DATABASE_SSLMODE=disable` is valid only for a loopback host. Any other host stays on `verify-full`. Confirm `current_database()` before running the command. Take a logical backup of that database first, and restore that backup if a script stops midway. Do not point this command at `aadi_platform` or a production CRM database from a workstation session.

Control Plane schema changes use Alembic from `MultiTenant/Aadi-MultiTenant-Platform/backend`:

```text
alembic upgrade head
```

S5.2 does not add a Control Plane revision. Do not run Alembic against a production URL as part of this sprint.

## Environment names

Set these in the process environment. Do not commit values.

CRM backend:

- `CRM_DATABASE_URL`
- `CRM_DATABASE_SSLMODE`
- `CRM_DATABASE_PATH` (SQLite only, when `CRM_DATABASE_URL` is unset)
- `PLATFORM_API_BASE_URL`
- `CRM_REMINDER_EMAIL_MODE`

CRM frontend:

- `VITE_API_BASE_URL`
- `VITE_CRM_API_BASE_URL`

CRM PostgreSQL tests:

- `CRM_TEST_DATABASE_URL`
- `CRM_TEST_DATABASE_SSLMODE`

Control Plane:

- `APP_NAME`
- `ENVIRONMENT`
- `LOG_LEVEL`
- `DATABASE_URL`
- `CORS_ORIGINS`
- `AUTH_SECRET_KEY`
- `AUTH_SESSION_TTL_SECONDS`
- `AUTH_PASSWORD_RESET_TTL_SECONDS`
- `ENTITLEMENT_SIGNING_SECRET`
- `ENTITLEMENT_SIGNATURE_TTL_SECONDS`
- `PLATFORM_ADMIN_USER_IDS`

Control Plane tests:

- `CONTROL_PLANE_TEST_APP_DATABASE_URL`
- `CONTROL_PLANE_TEST_MIGRATOR_DATABASE_URL`

## Tests

CRM frontend, from `Product/aadi-crm/frontend`:

```text
npm test
```

CRM backend, from `Product/aadi-crm/backend`. Include `CRM_TEST_DATABASE_URL` only when the disposable CRM test database should run. Leave it unset to skip PostgreSQL cases.

```text
python -m pytest
```

Control Plane, from `MultiTenant/Aadi-MultiTenant-Platform/backend`. The suite uses the disposable platform test database when the test URLs above are set. Do not point `DATABASE_URL` at `aadi_platform` for this run.

```text
python -m pytest
```

## Authorization responses

| Status | Usual cause |
| --- | --- |
| 401 | Missing session, or the `aadi_csrf` cookie does not match `X-CSRF-Token` on a write. |
| 403 | The caller is signed in, but product access, a feature entitlement, or `module_keys_for_member` denies the action. |
| 404 | The tenant membership is missing or inactive, the path tenant does not match product access, or a record is outside the caller's project or assigned scope. |
| 502 | The CRM process could not complete the Control Plane call, or the Control Plane payload was missing required fields. |

Role and assignment audit rows are not written in S5.2. There is nothing to query for those seven actions until the server-to-server append exists. Existing Control Plane events remain visible to a caller with `audit.read` through the CRM audit screen.
