# Observability review — original roadmap Sprint 12

Date: 21 October 2026.

Before this unit, `backend/app` had no logger. Import and reminder failures were stored as status fields and fixed error codes. They were not written to a process log. No metrics exporter, dashboard, or alert rule exists in this repository. None of those are claimed.

The API process already listening on port 8001 was not restarted. Log lines from the change below apply to a process started after this code. They were verified with the in-process test client, not against port 8001.

## What a new process logs

Logger name: `aadi_crm`. Output: standard error. Level: INFO.

Startup, once per process:

`startup database_name=<file name> platform_base_configured=<true or false>`

The directory and the platform URL are not logged. The flag is true only when `PLATFORM_API_BASE_URL` is non-empty.

Each response with status 400 or higher, and each response that takes at least 1000 ms, logs method, path without the query string, status, duration, and request id. A query string can contain a person's name, so it is omitted.

An unhandled exception logs the same fields plus `error_type`, which is the exception class name. The exception message is not logged. The client receives `INTERNAL_ERROR` and "The request could not be completed." The test `test_unhandled_error_hides_the_exception_text` raises `RuntimeError` with a fake cookie string and asserts that string is absent from the body and the log.

`X-Request-Id` is returned. A supplied id is kept only when it is 8 to 80 characters from `A-Z`, `a-z`, `0-9`, `_`, and `-`. Otherwise the server generates one. `test_authentication_denial_is_logged_without_the_session_cookie` sends a cookie and a rejected request id and asserts the cookie is absent from the log.

## What is still not logged

Successful requests under 1000 ms. Passwords, session cookies, CSRF tokens, request bodies, and record field values. Reminder provider exception text. That text was already kept out of the reminder row by `test_provider_exception_text_is_not_stored`.

Import and reminder outcomes remain in SQLite (`import_jobs.status`, `reminder_deliveries.state`, `last_error` as a known code). An operator looks at those rows, or at a 4xx/5xx line for the route, to see which subsystem failed.

## Diagnostic checklist for the local process

1. Confirm the CRM process was started after this code if you need the new lines.
2. Read standard error for `aadi_crm`.
3. For a 401 or 403, match `request_id` to the `X-Request-Id` response header. The line has the path and status, not the cookie.
4. For `status=502` on `/audit-events` or a shell path, treat it as Control Plane unavailability. The upstream body is not copied into the log.
5. For import or reminder failures, read the job or delivery state in the CRM database. Do not expect the customer's cell values in the process log.
6. A line at or above `duration_ms=1000` is a slow-request marker only. It is not an approved SLO.

## Not configured

Alerts, dashboards, uptime checks, and log shipping. Who watches the local process is **Owner decision required**.
