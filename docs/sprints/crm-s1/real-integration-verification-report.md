# CRM-S1 real Control Plane integration verification

Date: 18 October 2026. Repository: `aadi-crm` only. No commit, push, or Control Plane source change.

## Result

Real Control Plane authentication succeeded for an existing local identity. CRM product access did not succeed. The permission check `crm.lead_management.read` was not reached in the browser, and a direct permissions read for that identity did not include the key.

The blocker is Control Plane data, not the CRM shell. The product registry has no row whose key is exactly `crm`. Until that key exists, is entitled for a tenant the test identity belongs to, and that identity holds `crm.lead_management.read`, the shell cannot show Leads.

## What the CRM code actually calls

Confirmed from the current CRM source, not from the README alone.

| Concern | Actual behavior |
|---|---|
| Control Plane base URL | Frontend default `http://localhost:8000` (`VITE_API_BASE_URL`). On a loopback page it rewrites the host to match the page. This run used `http://127.0.0.1:8000`. |
| CRM API base URL | Frontend default `http://localhost:8001` (`VITE_CRM_API_BASE_URL`), rewritten to `http://127.0.0.1:8001`. Backend default `PLATFORM_API_BASE_URL` is `http://localhost:8000`. The running CRM API process was started with `http://127.0.0.1:8000`. |
| Session | Browser sends credentials on every platform and CRM call. Login is `POST /api/v1/auth/login`. Session read is `GET /api/v1/auth/me`. Logout is `POST /api/v1/auth/logout` with header `X-CSRF-Token` copied from the `aadi_csrf` cookie. The Control Plane sets host-only `aadi_session` (HttpOnly) and `aadi_csrf` (not HttpOnly), `SameSite=Lax`, path `/`. |
| Tenant context | `GET /api/v1/tenants` lists the caller's memberships. The path tenant id is only a selector. The shell rejects a product-access body whose `tenant_id` or `product_key` does not match the request. |
| Product access | `GET /api/v1/tenants/{tenant_id}/products/crm/access`. The CRM server repeats this call and forwards the cookie. |
| Permission | `GET /api/v1/tenants/{tenant_id}/permissions`. Leads is offered only when `available` is true and the list contains `crm.lead_management.read`. The CRM leads route enforces both again. |
| Branding | `GET /api/v1/tenants/{tenant_id}/configuration`. A 403 or 404 leaves the shell usable. This run never reached it. |
| CORS | CRM API allows `http://localhost:5174` and `http://127.0.0.1:5174` with credentials. The Control Plane allowlist is whatever process environment it started with. Login also rejects an `Origin` that is not on that allowlist. |
| Ports in this run | CRM web `127.0.0.1:5174`. CRM API `127.0.0.1:8001`. Control Plane API `127.0.0.1:8000`. Control Plane web port `5173` was not listening. PostgreSQL service `postgresql-x64-17` was listening on port `5433`. Docker was not running. |

## Prerequisites found

Port 8000 was occupied by the earlier CRM stand-in (`platform_stub` from a temporary file, OpenAPI title `FastAPI`, no `/health`). That process was stopped. The real Control Plane was then started from its existing backend environment with a process-only CORS override:

`CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174`

That value was not written into the Control Plane repository or its `.env`. Checked-in defaults, and the local Control Plane `.env` as previously documented, list only ports `5173`.

After startup:

- `GET /health` returned 200 `{"status":"ok"}`.
- `GET /ready` returned 200 `{"status":"ready"}`.
- OpenAPI title was `aadi-control-plane`.
- A preflight from origin `http://127.0.0.1:5174` returned `Access-Control-Allow-Origin: http://127.0.0.1:5174` and `Access-Control-Allow-Credentials: true`.

Platform admin product list: 68 products. None has key `crm`. Many keys look like `crm-` plus a suffix. Those do not satisfy the CRM client, which requests the key `crm`.

Identities already present, checked through the login route and then signed out:

| Identity | Login | Memberships | CRM access |
|---|---|---|---|
| `playwright-recording@example.com` | 200 | One active organization, Bootstrap recording 1792111368748 (`e02812a0-8717-4f5f-be19-57f263daef52`) | Product access 404. Permissions 200 and did not include `crm.lead_management.read`. |
| `playwright-platform-admin@example.com` | 200 | None | Product access cannot be evaluated without a membership. |
| `playwright-member@example.com` | 401 | Not reached | Not used. |

No product, subscription, grant, user, or tenant was created. Login created a session and logout removed it.

## Browser flow

Recording: `docs/sprints/crm-s1/recording.webm`.

The page at `http://127.0.0.1:5174` talked to `http://127.0.0.1:8000`. Observed responses:

- Signed-out `GET /api/v1/auth/me`: 401.
- Empty sign-in: "Email is required." No login request.
- Wrong password: `POST /api/v1/auth/login` 401, no `Set-Cookie`, page text "Sign-in failed."
- Valid sign-in: login 200, then `GET /api/v1/auth/me` 200 and `GET /api/v1/tenants` 200. The only organization is Bootstrap recording 1792111368748.
- Opening that organization: `GET /api/v1/tenants/{id}/products/crm/access` 404. Page text "The requested resource was not found."
- Leads URL and an unknown organization id: the same not-found page. The unknown id was `00000000-0000-4000-8000-000000000099`.
- Sign out: `POST /api/v1/auth/logout` 204, then the empty sign-in form.

Every platform response in that flow included a correlation id and allowed origin `http://127.0.0.1:5174`. Console messages were the browser's failed-resource lines for those 401 and 404 responses. No CORS error, and no cookie or password appeared in the console text or the recording. The password field is masked.

The CRM API, using the same session, returned 404 `RESOURCE_NOT_FOUND` for `/api/v1/shell/tenants/{id}` and `/api/v1/shell/tenants/{id}/leads`. The Control Plane log shows the matching forwarded `products/crm/access` requests. A later unauthenticated CRM shell call returned 401, and the Control Plane log shows that forward as 401. The CRM error body has `code` and `message` only. It does not copy the platform correlation id.

## Negative cases

Shown without changing shared data:

- Missing authentication: 401 on `GET /api/v1/auth/me` and on the CRM shell.
- Wrong password: 401, no session cookie, organizations stay hidden.
- Unknown organization id: 404, and the real organization name is not rendered.
- Missing product registration: 404 for key `crm` on the caller's real organization.

Not shown, because producing them would require Control Plane data changes:

- A registered CRM product with `available: false`.
- A registered and entitled CRM product whose caller lacks `crm.lead_management.read`. The permissions read above shows the key is absent, but the page never requests permissions while product access is 404.

## Tests

From `backend/`:

`.venv\Scripts\python.exe -m pytest`

Result: 8 passed, 1 warning (`StarletteDeprecationWarning` from FastAPI's test client). These tests use an in-process platform double. They do not call the live Control Plane.

From `frontend/`:

`npm test`

Result: 10 passed (`vitest` 3.2.7). These tests stub `fetch`. They do not call the live Control Plane.

No application test was added. The live gap is missing Control Plane registration, not a CRM assertion that a double can cover.

## Follow-up required in the Control Plane

Do not commit these. Approval is required before anyone changes Control Plane data or configuration.

1. Keep the CRM origins on the process that serves port 8000: `http://127.0.0.1:5174` and `http://localhost:5174`, alongside the existing `5173` origins. A restart that loads only the checked-in allowlist will reject CRM browser login. The login handler returns 401 for an origin that is not allowed.
2. Register one product whose key is exactly `crm`.
3. Entitle the chosen test tenant for that product so product access returns 200 with `available: true`.
4. Grant `crm.lead_management.read` to the test identity in that tenant.
5. Leave CRM projects, CRM records, and CRM schemas out of the Control Plane.

## Evidence

- `docs/sprints/crm-s1/recording.webm`
- `docs/sprints/crm-s1/explanation-script.md`
- This report
