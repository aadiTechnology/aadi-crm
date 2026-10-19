# CRM-S1 real Control Plane integration verification

Date: 19 October 2026. Repository: `aadi-crm` only. No commit, push, or Control Plane source change.

The 18 October browser run stopped before Leads because product access for the key `crm` returned 404. This run is the browser acceptance after that access was in place. The recording from 18 October is replaced by the recording described here.

## Result

The CRM browser signed in through the real Control Plane, opened Bootstrap recording 1792111368748, and loaded Leads from the CRM API. The leads response was 200. The page shows an empty Leads shell. It does not show a permission error.

## What the browser called

| Concern | Observed in this run |
|---|---|
| CRM page | `http://localhost:5174`. The running Vite process accepts `localhost` and does not accept `http://127.0.0.1:5174`. |
| Control Plane web | `http://localhost:5173`, started for this run. The recording stays on the CRM page. |
| Control Plane API | Browser calls `http://localhost:8000`. The same process answers `http://127.0.0.1:8000`. `/health` is `ok`, `/ready` is `ready`, and the OpenAPI title is `aadi-control-plane`. |
| CRM API | Browser calls `http://localhost:8001`. The same process answers `http://127.0.0.1:8001`. The OpenAPI title is `Aadi CRM`. |
| Session | Signed-out `GET /api/v1/auth/me` returned 401. `POST /api/v1/auth/login` returned 200. The following `GET /api/v1/auth/me` returned 200 for `playwright-recording@example.com`. |
| Tenant | `GET /api/v1/tenants` returned one organization, Bootstrap recording 1792111368748 (`e02812a0-8717-4f5f-be19-57f263daef52`). |
| Product access | `GET /api/v1/tenants/{tenant_id}/products/crm/access` returned 200 with `available: true`, `product_key` `crm`, and `product_name` `CRM`. |
| Permission | `GET /api/v1/tenants/{tenant_id}/permissions` returned 200. The only key was `crm.lead_management.read`. |
| Branding | `GET /api/v1/tenants/{tenant_id}/configuration` returned 403. The shell remained usable. |
| Leads | `GET http://localhost:8001/api/v1/shell/tenants/{tenant_id}/leads` returned 200 `{ "module": "leads", "items": [] }`. |
| CORS | Platform and CRM responses included `Access-Control-Allow-Origin: http://localhost:5174`. Platform responses included a correlation id. The CRM leads response did not. |

The development page repeats the signed-out session read and the shell reads. Leads was requested once.

## Browser flow

Recording: `docs/sprints/crm-s1/recording.webm` (8.96 seconds, 1280×720).

The password field is masked. The console reported the expected 401 and configuration 403 responses, plus a 404 for `/favicon.ico`. It did not report a CORS error, and no cookie or password appeared.

1. Signed-out CRM form at `http://localhost:5174`.
2. Email entered and password masked.
3. Organizations lists Bootstrap recording 1792111368748.
4. The CRM shell says CRM is available and shows the Leads link.
5. Leads shows "No leads are open in this shell."

## Evidence

- `docs/sprints/crm-s1/recording.webm`
- `docs/sprints/crm-s1/explanation-script.md`
- This report
