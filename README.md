# Aadi CRM

Product shell for CRM-S1. This repository is the CRM product. Authentication, tenant membership, product registration, subscriptions, and entitlement evaluation stay in the Control Plane.

## CRM-S1 boundary

The shell signs in with the Control Plane session cookie. It lists organizations from the caller's active memberships, then opens a tenant only after `GET /api/v1/tenants/{tenant_id}/products/crm/access`. The Leads link is shown when that response has `available: true`, the entitled features include `lead_management`, and `GET /api/v1/tenants/{tenant_id}/permissions` includes `crm.lead_management.read`. The CRM leads route enforces those checks again. The list itself is the project records the caller can already open. It stays empty unless the plan also entitles `records` and the caller has `crm.records.access` or `crm.project_management.manage`. A hidden link is not authorization.

CRM-S1 does not create records, a CRM password store, or a subscription store. CRM-S2 stores projects in the CRM-owned SQLite file `backend/data/aadi_crm.sqlite` when `CRM_DATABASE_URL` is unset. `CRM_DATABASE_PATH` overrides that file. The store is not the Control Plane database.

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

That process uses SQLite. The application reads environment variables only. It does not load `.env`.

To use the local PostgreSQL database `aadi_crm` on the loopback server that has TLS off, export `CRM_DATABASE_URL` and `CRM_DATABASE_SSLMODE` in the same shell, then start the API. `CRM_DATABASE_SSLMODE=disable` is only for that loopback server. Keep the real URL in gitignored `backend/.env`. This command reads those two names from that file and does not print them.

```text
cd backend
Get-Content .env | ForEach-Object {
  if ($_ -match '^(CRM_DATABASE_URL|CRM_DATABASE_SSLMODE)=(.*)$') {
    Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
  }
}
.venv\Scripts\uvicorn app.main:app --host localhost --port 8001
```

The startup log prints `database_name=aadi_crm`. If that URL is set and PostgreSQL cannot be reached, the request fails. The process does not open SQLite instead. Unset `CRM_DATABASE_URL` to return to SQLite.

Apply PostgreSQL migrations only when `crm_schema_migrations` is behind the scripts. The command uses the same two variables from the process environment. It does not open SQLite.

```text
cd backend
Get-Content .env | ForEach-Object {
  if ($_ -match '^(CRM_DATABASE_URL|CRM_DATABASE_SSLMODE)=(.*)$') {
    Set-Item -Path "env:$($Matches[1])" -Value $Matches[2]
  }
}
.venv\Scripts\python.exe -m app.migrate
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

Leave `CRM_DATABASE_URL` unset for that SQLite run. The API tests use temporary SQLite files. If `CRM_DATABASE_URL` is set, those tests write to PostgreSQL instead.

The live PostgreSQL tests are skipped unless `CRM_TEST_DATABASE_URL` is set. For the local loopback server, copy the gitignored URL into that variable and leave `CRM_DATABASE_URL` unset so the rest of the suite stays on SQLite:

```text
cd backend
Get-Content .env | ForEach-Object {
  if ($_ -match '^CRM_DATABASE_URL=(.*)$') {
    Set-Item -Path env:CRM_TEST_DATABASE_URL -Value $Matches[1]
  }
  if ($_ -match '^CRM_DATABASE_SSLMODE=(.*)$') {
    Set-Item -Path env:CRM_TEST_DATABASE_SSLMODE -Value $Matches[1]
  }
}
Remove-Item Env:CRM_DATABASE_URL -ErrorAction SilentlyContinue
.venv\Scripts\python.exe -m pytest tests/test_postgres_support.py
```

```text
cd frontend
npm test
```

Backend shell tests use an in-process platform double and do not write a database. Project tests apply the CRM migration to a temporary SQLite file.

Project routes require CRM product access for the path tenant. Product access alone is not enough. Opening projects requires the `project_management` feature and `crm.project_management.access` or `crm.project_management.manage`. `crm.lead_management.read` opens the Leads page only. That page lists records the caller can already open; it does not grant project administration. A project read or change requires an active CRM project membership bound to the current Control Plane membership, unless the caller holds `crm.project_management.manage`. A project manager can manage that project's membership and assign records. A project member sees records in the assigned scope. Follow-up ownership can open a related record for reading and does not allow edit, archive, or assignment. Platform-only keys do not open projects. Archive keeps the row. Membership rows are kept when a member is removed.
