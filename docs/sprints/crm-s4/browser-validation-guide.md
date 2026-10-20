# CRM-S4 browser validation guide

Date of this inspection: 19 October 2026.

This guide is for a person checking the real Control Plane and CRM membership flow in a browser. It uses the records that already exist. It does not create a tenant, user, project, permission, or membership.

The Control Plane is a separate repository at `C:\Users\lenovo\AadiTech\Product\MultiTenant\Aadi-MultiTenant-Platform`. It is not inside the `aadi-crm` workspace. The running API process on port 8000 is that repository’s backend, and its OpenAPI title is `aadi-control-plane`.

## How to read the evidence labels

| Label | Meaning |
|---|---|
| Live read | Read on 19 October 2026 from the Control Plane database `aadi_platform`, the CRM file `backend/data/aadi_crm.sqlite`, or an unauthenticated HTTP check. No row was changed. No one was signed in for this inspection, because sign-in writes a session. |
| Prior browser run | Shown in a CRM sprint recording or that sprint’s written browser notes. Not repeated in this inspection. |
| Prior report | Written in an earlier sprint report and not rechecked against the live store in this inspection. |
| Code | Read from the current CRM or Control Plane source. |
| Not rechecked | Could not be confirmed in this inspection. |

## 1. Prerequisites and how to start

Use the applications that are already running. Do not apply migrations, reset a database, or create records.

Checked on 19 October 2026:

| Application | Process | Browser address that works |
|---|---|---|
| Control Plane API | `Aadi-MultiTenant-Platform\backend` uvicorn, `--host 127.0.0.1 --port 8000` | `http://localhost:8000` returns health `ok` and ready `ready`. OpenAPI title `aadi-control-plane`. |
| CRM API | `aadi-crm\backend` uvicorn, `--host 127.0.0.1 --port 8001` | `http://localhost:8001/openapi.json` returns title `Aadi CRM`. This API has no `/health` route. |
| CRM web | `aadi-crm\frontend` Vite | `http://localhost:5174` returns the CRM page. |
| Control Plane web | Not running | `http://localhost:5173` refused the connection. |

Both APIs answered `Origin: http://localhost:5174` with `Access-Control-Allow-Origin: http://localhost:5174`. Leave those processes running. A restart that drops that origin will stop the CRM page from signing in. The checked-in Control Plane default allowlist is port 5173 only (`aadi-crm` README). If the Control Plane API must be started again, start it with `CORS_ORIGINS` including `http://localhost:5174` and `http://127.0.0.1:5174`, and do not commit that change.

Start a missing process only from the existing commands:

Control Plane API, from `C:\Users\lenovo\AadiTech\Product\MultiTenant\Aadi-MultiTenant-Platform\backend`:

```text
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Control Plane web, from `C:\Users\lenovo\AadiTech\Product\MultiTenant\Aadi-MultiTenant-Platform\frontend`:

```text
npm run dev
```

The Control Plane frontend defaults to `http://localhost:8000` for its API and to Vite’s port 5173. Its own notes say native Vite listens on `localhost`. Open `http://localhost:5173` after it starts. This web app is required only for the administrator grant in section 6. It is not required to view the current CRM blocker.

CRM API, from `C:\Users\lenovo\AadiTech\Product\aadi-crm\backend`:

```text
.venv\Scripts\uvicorn app.main:app --host localhost --port 8001
```

CRM web, from `C:\Users\lenovo\AadiTech\Product\aadi-crm\frontend`:

```text
npm run dev
```

CRM Vite is configured with `host: 'localhost'` and `port: 5174`. No `VITE_API_BASE_URL` or `VITE_CRM_API_BASE_URL` override is required. The page then uses `http://localhost:8000` and `http://localhost:8001`.

Passwords are not written in this guide. The local test passwords are already stored in:

`C:\Users\lenovo\AadiTech\Product\MultiTenant\Aadi-MultiTenant-Platform\frontend\e2e\.env`

| Sign-in | Variable | Checked |
|---|---|---|
| `playwright-recording@example.com` | `PLAYWRIGHT_RECORDING_USER_PASSWORD` | Non-empty, and the email and user id in that file match the database. |
| `playwright-member@example.com` | `PLAYWRIGHT_MEMBER_PASSWORD` | Non-empty, and the email and user id in that file match the database. |
| `playwright-platform-admin@example.com` | `PLAYWRIGHT_ADMIN_PASSWORD` | Non-empty, and the email in that file matches the database. |

Copy the password from the named variable into the masked password field. Do not paste it into a document, ticket, or chat.

## 2. Hostname

Use `localhost` in the address bar for every page and leave the APIs on `localhost`.

`localhost` and `127.0.0.1` do not share the sign-in cookie. The CRM page also rewrites a development API address onto the same host as the page. Mixing the two names drops the session.

Live check on 19 October 2026:

- `http://localhost:5174` opened the CRM page.
- `http://127.0.0.1:5174` refused the connection.
- `http://localhost:8000` and `http://localhost:8001` answered, even though those API processes were started with `--host 127.0.0.1`.

| Surface | Address to open |
|---|---|
| CRM web | `http://localhost:5174` |
| Control Plane API, as called by CRM | `http://localhost:8000` |
| CRM API, as called by CRM | `http://localhost:8001` |
| Control Plane web, only for the grant below | `http://localhost:5173` |

## 3. Tenant and CRM product

The shared Control Plane database contains many other tenants and many other products whose names include “CRM”. Use only the tenant and product key below.

| Field | Value | Evidence |
|---|---|---|
| Tenant name | Bootstrap recording 1792111368748 | Live read |
| Tenant id | `e02812a0-8717-4f5f-be19-57f263daef52` | Live read |
| Tenant status | `active` | Live read |
| Product key | `crm` | Live read. The CRM shell calls `/api/v1/tenants/{tenant_id}/products/crm/access`. |
| Product name | CRM | Live read |
| Product id | `4fb54c1a-d46d-40e7-80ac-7bb8cba09968` | Live read |
| Registered product permission | `crm.lead_management.read` only | Live read of the `crm` registration |
| `crm.project_management.manage` | Not in the permission catalog and not on the `crm` registration | Live read |
| Plan name | Development | Live read |
| Plan key | `development` | Live read |
| Plan id | `f5f418b4-b353-40a2-9663-a9da8117ff47` | Live read |
| Plan status | `active` | Live read |
| Subscription id | `f632c14a-d4da-4bf5-9c2f-78c8ad14f8db` | Live read |
| Subscription status | `active` | Live read |
| Subscription window | Effective from 2026-10-18 23:38:36 +05:30, no end | Live read |
| Product access `available: true` | Expected from those rows. The access route was not called again in this inspection. | Prior browser run in CRM-S1, CRM-S3, and CRM-S4. The entitlement code treats an active tenant, an active open subscription, and an open date window as entitled. |

In the CRM page, after sign-in, the organization list is a link whose text is the tenant name. Open **Bootstrap recording 1792111368748**. The shell heading is **CRM**. The success line is **CRM is available in this organization.**

`playwright-member@example.com` is also an active tenant administrator of a second organization, **Bootstrap recording 1792111159231** (`74bc3266-ca3e-4c0e-b748-a92983351b31`). The CRM database has no projects for that second tenant. Do not open it for this validation.

## 4. Test users

Control Plane roles and CRM project roles are different. `project_manager` is stored only in CRM.

| Email | User id | Control Plane membership and role | Effective permissions on this tenant | Intended use | Login readiness |
|---|---|---|---|---|---|
| `playwright-recording@example.com` | `54982624-52e6-4e2a-9026-f37fdea126e4` | Active member of Bootstrap recording 1792111368748. Role name **CRM lead reader**, key `crm.lead_reader`, role id `ab585b48-a026-406e-ba0f-558cc19a86a8`. | `crm.lead_management.read` only. Does **not** hold `users.read`. | Sign in to CRM, open Recording gate, and manage project members after the grant in section 6. | Account active and a password hash is stored. Password variable `PLAYWRIGHT_RECORDING_USER_PASSWORD`. Sign-in was shown in the CRM-S4 recording. This inspection did not sign in again. |
| `playwright-member@example.com` | `42141034-df50-46f8-9786-f9c211e72edd` | Active member of this tenant. Role name **Tenant Administrator**, key `tenant_admin`, role id `e2a11d4d-7fb5-4d72-944d-aa7b1423f420`. Also an active tenant administrator of Bootstrap recording 1792111159231. | `configuration.read`, `configuration.update`, `roles.manage`, `roles.read`, `subscription.read`, `users.read`, `users.update`. Does **not** hold `crm.lead_management.read` or `crm.project_management.manage`. | Make the one Control Plane grant below. Also the only other person who can be added to the project. This sign-in is the user who must stay denied for CRM projects until a CRM module permission exists. | Account active and a password hash is stored. Password variable `PLAYWRIGHT_MEMBER_PASSWORD`. Sign-in and the project denial were shown in the CRM-S4 recording. This inspection did not sign in again. |
| `playwright-platform-admin@example.com` | `d18c2315-f9d0-4f71-a7f7-fb28146e903c` | No tenant membership. The Control Plane development settings mark this id as a platform administrator. | Platform administration is not a tenant role and does not grant CRM project access. | Not part of the membership clicks. Do not attach this account to the tenant for this check. | Account active, password hash stored, password variable `PLAYWRIGHT_ADMIN_PASSWORD`. The live administrator check was not called. |

A third tenant role, **Recording viewer** (`recording.viewer`), holds only `subscription.read` and is not assigned to either CRM user. Do not grant `users.read` to that role.

There is no second tenant member who already holds `crm.lead_management.read`.

## 5. Project to open

Use the active project only. Do not create a project. Do not archive or edit one during this check.

| Field | Recording gate | Harbor gate | Live gate |
|---|---|---|---|
| Use for this validation | Yes. This is the only active project. | No. Archived. | No. Archived. |
| Project id | `8d0b7f84-d481-45cf-beca-3dd1af92ec97` | `7dca5eb0-ea44-4e40-9332-e4b7f11b2011` | `75904ca1-386f-4e88-9233-2d029870cd7d` |
| Code | `S2-REC` | `S2-DEMO` | `S2-LIVE` |
| Name | Recording gate | Harbor gate | Live gate |
| Status | `active` | `archived` | `archived` |
| Tenant id | `e02812a0-8717-4f5f-be19-57f263daef52` | same | same |
| Active membership | One: `playwright-recording@example.com` (`54982624-52e6-4e2a-9026-f37fdea126e4`), role `project_manager`, scope `project`, membership id `973edeee-5575-4085-9beb-76bf52fd4bd9` | One active `project_manager` row for the same user | One active `project_manager` row for the same user |
| Removed memberships | None | None | None |

Evidence: live read of `aadi-crm\backend\data\aadi_crm.sqlite`. Applied migration versions are `001_projects.sql` and `002_project_memberships.sql`. The running CRM API was not asked for the project list, because that call requires a sign-in. The same three codes and statuses were reported after CRM-S3 and again in the CRM-S4 report.

Direct address, after the recording user is signed in:

`http://localhost:5174/tenants/e02812a0-8717-4f5f-be19-57f263daef52/projects/8d0b7f84-d481-45cf-beca-3dd1af92ec97`

The project list address is:

`http://localhost:5174/tenants/e02812a0-8717-4f5f-be19-57f263daef52/projects`

## 6. Browser steps

### Blocker before any membership change

`users.read` is not granted to **CRM lead reader**. Live assignment stays blocked until a tenant administrator who already holds `roles.manage` grants that existing catalog key.

Do this in the Control Plane web, not in CRM. The authorized person is `playwright-member@example.com`, because that sign-in holds `roles.manage` on this tenant. Do not grant `users.update`. Do not create a new permission key. Do not register `crm.project_management.manage` from CRM.

1. Open `http://localhost:5173` and sign in as `playwright-member@example.com` with `PLAYWRIGHT_MEMBER_PASSWORD`.
2. Under **Authorized tenants**, open **Bootstrap recording 1792111368748**. Do not open **Bootstrap recording 1792111159231**.
3. Open **Roles**. The address is `http://localhost:5173/tenants/e02812a0-8717-4f5f-be19-57f263daef52/roles`.
4. On **CRM lead reader** (`crm.lead_reader`), choose **Permissions**.
5. On the row `users.read`, choose **Grant**. Leave `users.update` as **Not assigned**.
6. Return to the CRM page, still signed in as `playwright-recording@example.com`, and reload Recording gate. The permissions read is evaluated from the database on that request. If the directory message is still there, sign out of CRM and sign in again.

Until that grant is present, the steps marked **BLOCKED** below fail closed. CRM writes no membership when the directory returns 403. Do not type a user id into another tool to get around that.

The Control Plane web was not running during this inspection, so this grant was not performed and was not clicked.

### A. View project members — ready to repeat

Already shown in `docs/sprints/crm-s4/recording.webm`.

1. Open `http://localhost:5174`.
2. Sign in as `playwright-recording@example.com`.
3. Open **Bootstrap recording 1792111368748**.
4. Confirm **CRM is available in this organization.** Confirm **Leads** and **Projects** are links.
5. Open **Projects**.
6. Open **Recording gate**. Confirm code **S2-REC**, status **Active**, role **Project manager**, and record scope **All project records.**
7. In **Members**, confirm one row: `playwright-recording@example.com`, role **Project manager**, status **Active**, record scope **All project records.**

Expected now: there is no **Add member** form. The page says **You cannot look up organization members with this sign-in.**

Choosing **Remove** for this only manager shows **This project needs an active project manager.** The row stays **Active**. Do not keep clicking Remove. This refusal was shown in the CRM-S4 recording and is still the expected result while this person is the only active project manager.

### B. Add an eligible tenant user — BLOCKED

The only other active member of this tenant is `playwright-member@example.com`.

Expected now: the add form is absent and the directory message in step A is shown. No membership row is created.

After the `users.read` grant, and only then:

1. Stay on Recording gate as `playwright-recording@example.com`.
2. Under **Add member**, choose **Organization member** `playwright-member@example.com`.
3. Set **Project role** to **Project member**. Do not choose **Project manager** for the first add. The original manager must remain.
4. Choose **Add member**.

Expected after the grant: the new row shows `playwright-member@example.com`, role **Project member**, status **Active**, record scope **Assigned records.** The recording user remains **Project manager**.

If the list says **No other active organization members are available to add**, stop. Do not create a user.

### C. Change that user’s project role — BLOCKED

Depends on step B.

Expected now: there is no second member, so there is no role to change.

After step B:

1. On the new member’s row, change **Project role** from **Project member** to **Project manager**.
2. Choose **Save role for playwright-member@example.com**.

Expected after the grant and the add: that row becomes **Project manager** with record scope **All project records.** The recording user is still a project manager, so the project still has a manager.

Do not change the recording user to **Project member** while they are the only manager. That is refused with **This project needs an active project manager.**

### D. Sign in as the added user and check project access — BLOCKED, and still blocked after `users.read`

Depends on step B. It also cannot succeed with the current second user.

`playwright-member@example.com` does not hold `crm.lead_management.read`. CRM checks that module permission before it checks project membership. Product access and `users.read` do not open Projects. `crm.project_management.manage` is not registered, so it cannot be granted.

Expected now, and still expected after this person is added as a project member:

1. Sign out of CRM. The sign-in form is empty.
2. Sign in as `playwright-member@example.com`.
3. Open **Bootstrap recording 1792111368748**, not the other Bootstrap recording organization.
4. Confirm **CRM is available in this organization.**
5. Confirm the page says **Leads is not available for this sign-in.** and **Projects is not available for this sign-in.**
6. Open the Recording gate address directly.

Expected page: the project name is not shown. The page says **You do not have permission to perform this action.**

That is the current denial. It does not prove a project membership, and a later membership will not remove this denial. No existing second user holds the CRM module permission, so this guide has no live sign-in that can both be added and then see Recording gate. Do not create an identity or grant `crm.lead_management.read` as part of this check. Automated tests cover a member who already holds the module permission; those tests use a temporary database, not this tenant.

### E. Remove that user — BLOCKED

Depends on step B. Do not remove `playwright-recording@example.com`.

After a second active member exists:

1. Sign back in as `playwright-recording@example.com`.
2. Open Recording gate.
3. On `playwright-member@example.com`, choose **Remove**.

Expected after the grant and the add: that row becomes status **Removed**. The recording user stays **Active** and **Project manager**. The removed row remains; CRM does not delete it.

Expected now: Remove on the only manager is refused, as in step A.

### F. Confirm a fresh request is denied after removal — BLOCKED

Depends on step E, and it is not visible with `playwright-member@example.com`.

That sign-in is denied by the module check whether or not a project membership exists. After removal, the same **Projects is not available** and **You do not have permission to perform this action.** messages still appear. They do not show the difference between “never allowed into the module” and “membership removed”.

The CRM-S3 automated test covers an immediate not-found response after removal for a caller who can still open the module. That test is not this browser flow. There is no live user on this tenant who can demonstrate that distinction.

### G. Confirm a user without CRM project authorization stays denied — ready to repeat

This is the same sign-in as step D, and it does not require the grant or a membership change. It was shown in the CRM-S4 recording.

1. Sign in at `http://localhost:5174` as `playwright-member@example.com`.
2. Open **Bootstrap recording 1792111368748**.
3. Confirm CRM is available and Projects is not a link.
4. Open `http://localhost:5174/tenants/e02812a0-8717-4f5f-be19-57f263daef52/projects/8d0b7f84-d481-45cf-beca-3dd1af92ec97`.

Expected: **Projects is not available for this sign-in.** and **You do not have permission to perform this action.** The name Recording gate is not shown.

## 7. Expected outcomes and blockers

| Step | Outcome today | Blocker |
|---|---|---|
| A. View members | One active project manager, the recording user. Directory message is shown. Removing that only manager is refused. | None for viewing. |
| B. Add member | No add form. No membership is written. | `users.read` is missing on **CRM lead reader**. |
| C. Change role | No second member to change. | Same grant, then step B. |
| D. Added user opens the project | The tenant administrator cannot open Projects. | Same grant, then step B, and this user still lacks `crm.lead_management.read`. The module denial remains after a membership exists. |
| E. Remove the added user | Cannot be done. Removing the only manager is refused. | Same grant, then step B. |
| F. Denial after removal | Cannot be distinguished in the browser with the current second user. | No live user both passes the CRM module check and is eligible to add. |
| G. User without CRM authorization | Denied, including on the direct Recording gate address. | None. This is the expected denial. |

## 8. Already shown, versus still needing a live check

Already shown in the browser against the real Control Plane, in `docs/sprints/crm-s4/recording.webm` and `docs/sprints/crm-s4/explanation-script.md`:

- Recording user signs in and opens Bootstrap recording 1792111368748.
- CRM is available. Leads and Projects are shown.
- Recording gate shows one active project manager.
- The directory message is shown. No member is added.
- Removing the only manager is refused and the member stays active.
- An unknown project address and a different tenant address show **The requested resource was not found.** Those exact addresses were not written down, so this guide does not repeat them.
- `playwright-member@example.com` has CRM available and cannot open Projects or Recording gate.

Shown by automated tests only, on a temporary database and an in-process platform double, not in the browser:

- Successful add, role change, and removal.
- Not-found on the next request after removal for a caller who can still open the module.
- Record decisions for a manager, a member, and a removed member. CRM does not store records yet, so a browser record check does not exist.

Still needing a live browser check after the Control Plane grant:

- Add member, change that member’s project role, and remove that member, without removing the recording user.
- The added user’s own view of Recording gate. With the only eligible user, the honest expected result is still the module denial in step D, not a successful open.

## 9. Checklist

Mark the live workflow complete only when every line is true. Do not mark a blocked line complete because an automated test passed.

- [ ] CRM is open at `http://localhost:5174`, and both APIs are the `localhost` addresses in section 2.
- [ ] The organization is Bootstrap recording 1792111368748, tenant `e02812a0-8717-4f5f-be19-57f263daef52`.
- [ ] The shell says CRM is available.
- [ ] The project is Recording gate, code `S2-REC`, id `8d0b7f84-d481-45cf-beca-3dd1af92ec97`, status Active.
- [ ] Members shows `playwright-recording@example.com` as an active project manager.
- [ ] A tenant administrator has granted the existing key `users.read` to role **CRM lead reader** (`crm.lead_reader`) and has not granted `users.update`.
- [ ] After that grant, the recording user sees **Add member** and can select `playwright-member@example.com`.
- [ ] That user is added as **Project member**, then saved as **Project manager**, while the recording user remains an active project manager.
- [ ] The added row is then removed and remains visible with status **Removed**.
- [ ] `playwright-recording@example.com` is still an active project manager on Recording gate.
- [ ] `playwright-member@example.com` is still denied on the direct Recording gate address.
- [ ] Harbor gate and Live gate were not used, and no new user, tenant, project, or permission was created.

The line for “the added user opens Recording gate and sees the project” stays unchecked with the current identities. Step D explains why.
