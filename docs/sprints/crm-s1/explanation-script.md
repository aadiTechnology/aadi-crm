# CRM-S1 real integration explanation

Recording: `docs/sprints/crm-s1/recording.webm` (8.96 seconds, 1280×720).

This narration follows that recording in order. The page is the CRM shell at `http://localhost:5174`. The CRM API answering the page is `http://localhost:8001` (`Aadi CRM`). The API answering `http://localhost:8000` is the local Control Plane (`aadi-control-plane`). The Control Plane web is running at `http://localhost:5173` and is not part of this recording. The signed-in address is the existing local test identity `playwright-recording@example.com`. The password field stays masked. No session cookie or password is shown.

## Purpose

The recording checks the CRM browser against the running Control Plane and CRM API. Sign-in uses the platform session cookie. The organization list comes from that session. Opening the organization calls product access for the key `crm`. The shell then offers Leads, and opening Leads calls the CRM API. That leads call returns 200.

## Sequence

1. The shell opens signed out, titled CRM, with Email, Password, and Sign in.
2. The email `playwright-recording@example.com` is entered. The password is entered in the masked field. The characters appear as dots.
3. Sign-in opens Organizations. One organization is listed: Bootstrap recording 1792111368748. The signed-in address is shown. Sign out is available.
4. Opening that organization shows the CRM shell. The heading is the organization name. The page says "CRM is available in this organization." A Leads link is shown. The Leads section is not open yet.
5. The page briefly shows "Checking access" while the Leads address loads.
6. Leads opens in the same shell. The page still says CRM is available, shows the Leads heading, and says "No leads are open in this shell." It does not say that permission was denied.

## What the browser called

The page host is `localhost`, so the shell calls `localhost` for both APIs. Those calls are the processes already listening on ports 8000 and 8001.

Signed-out `GET http://localhost:8000/api/v1/auth/me` returned 401. The development page issued that read twice before login. `POST http://localhost:8000/api/v1/auth/login` then returned 200. `GET /api/v1/auth/me` returned 200 for `playwright-recording@example.com`. `GET /api/v1/tenants` returned one organization.

Opening the organization called `GET /api/v1/tenants/e02812a0-8717-4f5f-be19-57f263daef52/products/crm/access` and received 200. The body has `product_key` `crm`, `product_name` `CRM`, `tenant_name` Bootstrap recording 1792111368748, and `available` true. `GET /api/v1/tenants/{tenant_id}/permissions` returned 200 with one key, `crm.lead_management.read`. `GET /api/v1/tenants/{tenant_id}/configuration` returned 403. The shell stays on the organization screen after that branding read. Opening Leads repeats the access, permissions, and configuration reads. The development page issued the shell reads twice.

Leads itself is one browser call: `GET http://localhost:8001/api/v1/shell/tenants/e02812a0-8717-4f5f-be19-57f263daef52/leads`. It returned 200 with `module` `leads` and an empty `items` list. That response is not 403.

Each Control Plane response in the flow included `Access-Control-Allow-Origin: http://localhost:5174` and a correlation id. The CRM leads response allowed the same origin and did not include a correlation id. The browser console reported the signed-out 401 responses, the configuration 403 responses, and a 404 for `/favicon.ico`. It did not report a CORS failure. No cookie or password appeared in the console text or the recording.

## Result

Authentication against the real Control Plane succeeded. The CRM shell opened for Bootstrap recording 1792111368748 because product access for `crm` was available and the permission list included `crm.lead_management.read`. Leads loaded from the CRM API without a 403.
