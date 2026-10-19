# Aadi CRM

Product shell for CRM-S1. This repository is the CRM product. Authentication, tenant membership, product registration, subscriptions, and entitlement evaluation stay in the Control Plane.

## CRM-S1 boundary

The shell signs in with the Control Plane session cookie. It lists organizations from the caller's active memberships, then opens a tenant only after `GET /api/v1/tenants/{tenant_id}/products/crm/access`. The Leads link is shown when that response has `available: true` and `GET /api/v1/tenants/{tenant_id}/permissions` includes `crm.lead_management.read`. The CRM leads route enforces both checks again. A hidden link is not authorization.

CRM-S1 does not create records, a CRM password store, or a subscription store. CRM-S2 stores projects in the CRM-owned SQLite file `backend/data/aadi_crm.sqlite`. `CRM_DATABASE_PATH` overrides that file. The store is not the Control Plane database.

## Local run

Control Plane API: `http://localhost:8000`  
CRM API: `http://localhost:8001`  
CRM web: `http://localhost:5174`

Use the same loopback host for the page and both APIs. `localhost` and `127.0.0.1` do not share the host-only session cookie.

The Control Plane allowlist must include the CRM page origin before a browser on port 5174 can sign in. The checked-in Control Plane default is ports 5173 only. Start the Control Plane process with `CORS_ORIGINS` including `http://localhost:5174` and `http://127.0.0.1:5174`. Do not commit that change to the Control Plane repository.

```text
cd backend
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\uvicorn app.main:app --host localhost --port 8001
```

```text
cd frontend
npm install
npm run dev
```

`PLATFORM_API_BASE_URL` overrides the Control Plane base URL for the CRM API. The web app reads `VITE_API_BASE_URL` and `VITE_CRM_API_BASE_URL`.

## Tests

```text
cd backend
.venv\Scripts\python -m pytest
```

```text
cd frontend
npm test
```

Backend shell tests use an in-process platform double and do not write a database. Project tests apply the CRM migration to a temporary SQLite file.

Project routes require CRM product access for the path tenant. Product access alone is not enough. Opening the project module requires `crm.project_management.manage` or, while that key is absent from the current CRM registration, `crm.lead_management.read`. That module check does not grant every project in the tenant. A project read or change requires an active CRM project membership, unless the caller holds `crm.project_management.manage`. A project manager can manage that project's membership and configuration. A project member can view the project. Platform-only keys do not open projects. Archive keeps the row. Membership rows are kept when a member is removed.
