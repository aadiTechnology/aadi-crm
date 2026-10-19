# CRM-S2 project management explanation

Recording: `docs/sprints/crm-s2/recording.webm` (31.84 seconds, 1280×720).

This narration follows that recording in order. The page is the CRM shell at `http://localhost:5174`. The CRM API answering the page is `http://localhost:8001` (`Aadi CRM`). The API answering `http://localhost:8000` is the local Control Plane (`aadi-control-plane`). The signed-in address is the existing local test identity `playwright-recording@example.com`. The password field stays masked. No session cookie or password is shown.

## Purpose

The recording checks tenant-scoped projects against the running Control Plane and the CRM API. Sign-in uses the platform session cookie. Opening the organization calls product access for the key `crm`. Projects then calls the CRM API, which stores the row in the CRM SQLite file. The captured project is created, edited, found by search, and archived. The row remains.

## Sequence

1. The shell opens signed out, titled CRM, with Email, Password, and Sign in.
2. The email `playwright-recording@example.com` is entered. The password is entered in the masked field. The characters appear as dots.
3. Sign-in opens Organizations. One organization is listed: Bootstrap recording 1792111368748. The signed-in address is shown.
4. Opening that organization shows the CRM shell. The page says "CRM is available in this organization." Leads and Projects links are shown.
5. Projects opens in the same shell. The list is not empty. It shows Recording gate, code S2-REC, status Active, and Harbor gate, code S2-DEMO, status Archived. Those two rows were written while the capture was being prepared. The recording then creates a third project.
6. New project opens. The code `S2-LIVE`, the name Live harbor, and the description North harbor work are entered. Create project opens the detail page. The heading is Live harbor. The code is S2-LIVE. The status is Active. The creator id `54982624-52e6-4e2a-9026-f37fdea126e4` is shown.
7. The name is changed to Live gate and the description to "Updated during the recording." Save project updates the heading and the description. The code stays S2-LIVE.
8. Back to projects, the search box receives Live, and Search is clicked. The list shows Live gate.
9. Opening Live gate and choosing Archive project changes the status to Archived. The page says "This project is archived."
10. Back to projects, the status filter is set to Archived. Live gate remains, with status Archived. Harbor gate is also in that filtered list. Recording gate is Active, so it is not in the archived filter.

## What the browser called

The page host is `localhost`, so the shell calls `localhost` for both APIs.

Signed-out `GET /api/v1/auth/me` returned 401. The development page issued that read twice before login. `POST /api/v1/auth/login` returned 200. `GET /api/v1/auth/me` then returned 200 for `playwright-recording@example.com`. `GET /api/v1/tenants` returned one organization, Bootstrap recording 1792111368748 (`e02812a0-8717-4f5f-be19-57f263daef52`).

Opening the organization called `GET /api/v1/tenants/e02812a0-8717-4f5f-be19-57f263daef52/products/crm/access` and received 200 with `available` true. `GET /api/v1/tenants/{tenant_id}/permissions` returned 200 with one key, `crm.lead_management.read`. `GET /api/v1/tenants/{tenant_id}/configuration` returned 403. The shell stayed on the organization screen.

Projects called `GET http://localhost:8001/api/v1/tenants/{tenant_id}/projects`. The development page issued that list read twice. Create was one `POST` to the same path and returned 201. The new project id was `75904ca1-386f-4e88-9233-2d029870cd7d`. The detail `GET` returned 200. The edit was one `PATCH` to that project and returned 200. Search was a list `GET` with the Live query and returned 200. Archive was `POST .../projects/{project_id}/archive` and returned 200. The archived filter was another list `GET` and returned 200.

Before this recording, both APIs were checked with `Origin: http://localhost:5174`. Each allowed that origin. The browser console reported the signed-out 401 responses, the configuration 403, a 404 for a missing resource, and the Vite connection messages. It did not report a CORS failure. No cookie or password appeared in the console text or the recording.

## Result

The CRM shell signed in through the real Control Plane and opened Bootstrap recording 1792111368748. Projects created Live harbor, saved it as Live gate, found it by search, and archived it. The archived row is still stored for that tenant.
