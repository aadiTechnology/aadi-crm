# Observability — original roadmap Sprint 12

Date: 21 October 2026. This file records what was verified. `observability-review.md` is the earlier design note. No metrics dashboard or alert rule was found in this repository or on the machine during this review. None are claimed.

## Implementation

`backend/app/main.py` logs with the name `aadi_crm` to standard error at INFO. The formatter is `%(levelname)s aadi_crm %(message)s`.

Startup logs the database file name and whether `PLATFORM_API_BASE_URL` is non-empty. It does not log the directory or the URL.

A client `X-Request-Id` is kept only when it is 8 to 80 characters from `A-Z`, `a-z`, `0-9`, `_`, and `-`. Any other value is replaced with a generated id. The path logged for a request has carriage returns and line feeds removed and is cut at 200 characters. The query string is not logged. Cookies, authorization headers, and exception messages are not written by this middleware. An unhandled exception logs `error_type` as the class name. The client receives `INTERNAL_ERROR` and "The request could not be completed."

Responses at status 400 or above, and responses that take at least 1000 ms, are logged with method, path, status, duration, and request id. Successful fast requests are not logged.

## Live process

Port 8001 was already listening as pid 5148. It was not restarted and was not used as evidence.

A separate process was started with `CRM_DATABASE_PATH` pointing at a new migrated file `crm-s14-log.sqlite` in the temp directory, on `127.0.0.1:8091`. It was stopped after the log was read. Port 8001 was still pid 5148 afterward.

Observed standard error:

`INFO aadi_crm startup database_name=crm-s14-log.sqlite platform_base_configured=True`

An unauthenticated `GET /api/v1/shell/tenants/11111111-1111-4111-8111-111111111111` returned 401 and "Authentication is required."

| Supplied `X-Request-Id` | Result |
|---|---|
| `not-valid` | Kept. It matches the allowed pattern. The log line used that id. Duration 599 ms |
| `bad id` | Rejected. The response and the log used `044479e522474309b7e358b9acc56b0f` |

The second request included `?marker=query-marker-not-for-log`. That marker is not in the log. A header value containing a newline was rejected by the HTTP client before it was sent (`ValueError`). The unit test `test_authentication_denial_is_logged_without_the_session_cookie` covers a cookie and a rejected id inside the test client. This live process was not sent a session cookie.

## What is not in place

| Item | State |
|---|---|
| Health route | Absent. A missing session returns 401. That is the only liveness check this review used |
| Metrics dashboard | Not found |
| Alert rules | Not found |
| Log shipping and retention | **Owner decision required** |
| Who watches the log | **Owner decision required** |
| Slow-request threshold of 1000 ms | Code only. It is not an approved SLO |

## Minimum an owner still has to decide

1. Where CRM standard error is retained, and for how long.
2. Who is notified, and how, when a line shows status 500, status 502, or `duration_ms` at or above 1000.
3. Whether a health check beyond "the process accepts connections" is required before release.

Until those decisions exist, monitoring is not configured. Do not describe alerts as active.
