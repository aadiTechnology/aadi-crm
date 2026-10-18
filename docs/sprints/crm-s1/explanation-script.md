# CRM-S1 real integration explanation

Recording: `docs/sprints/crm-s1/recording.webm` (14.64 seconds, 1280×720).

This narration follows that recording in order. The page is the CRM shell at `http://127.0.0.1:5174`. The CRM API is on `http://127.0.0.1:8001`. The API answering port 8000 is the local Control Plane (`aadi-control-plane`), not the earlier stand-in. The signed-in address is the existing local test identity `playwright-recording@example.com`. The password field stays masked. No session cookie or password is shown.

## Purpose

The recording checks the CRM shell against the running Control Plane. Sign-in uses the platform session cookie. The organization list comes from that session. Opening an organization calls product access for the key `crm`. This run does not reach a Leads link, because that access call returns not found.

## Sequence

1. The shell opens signed out, titled CRM, with Email, Password, and Sign in.
2. Sign in with both fields empty shows "Email is required." The platform login route is not called.
3. `playwright-recording@example.com` with a wrong password shows "Sign-in failed." The Control Plane login route returns 401. Organizations do not appear.
4. The same email with the existing local password opens Organizations. One organization is listed: Bootstrap recording 1792111368748. The signed-in address is shown. Sign out is available.
5. Opening that organization shows "The requested resource was not found." The Control Plane product-access route for key `crm` returns 404. The page does not show a CRM availability message or a Leads link.
6. Opening that organization's leads address directly shows the same not-found message. Product access fails before the page requests the CRM leads route.
7. An unknown organization id shows the same not-found message. The real organization name is not shown on that screen.
8. Sign out returns to the empty sign-in form.

## What the Control Plane returned

Successful login set the host-only cookies `aadi_session` and `aadi_csrf`. `GET /api/v1/auth/me` then returned 200 for this identity. `GET /api/v1/tenants` returned the one organization named above. `GET /api/v1/tenants/{tenant_id}/products/crm/access` returned 404. Each of those responses carried `Access-Control-Allow-Origin: http://127.0.0.1:5174` and a correlation id. The browser console reported the expected 401 and 404 resource failures. It did not report a CORS failure.

The shell does not ask for permissions after product access returns 404, so this recording does not show `crm.lead_management.read`. A separate authenticated call for this same identity and organization, made before the recording and then signed out, returned 200 with no `crm.` permission keys.

The CRM API on port 8001, called with the same session, returned 404 `RESOURCE_NOT_FOUND` for both the shell and leads routes. The Control Plane log shows those calls forwarded as product-access requests. An unauthenticated CRM shell call returned 401 and was forwarded the same way.

## Result

Authentication against the real Control Plane succeeded for this identity. CRM product access did not. The registry has no product whose key is exactly `crm`, so the shell cannot open, and the Leads permission check is not reached in the page.
