"""CRM product API. Session cookies are issued only by the Control Plane."""

import logging
import os
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.audit_view import router as audit_router
from app.api.followups import router as followups_router
from app.api.imports import router as imports_router
from app.api.reporting import router as reporting_router
from app.api.reminders import router as reminders_router
from app.api.forms import router as forms_router
from app.api.projects import router as projects_router
from app.api.records import router as records_router
from app.api.shell import router as shell_router
from app.db import resolve_database

_LOG = logging.getLogger("aadi_crm")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
_SLOW_MS = 1000

_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]


def _logger() -> logging.Logger:
    if not _LOG.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s aadi_crm %(message)s"))
        _LOG.addHandler(handler)
        _LOG.setLevel(logging.INFO)
        _LOG.propagate = False
    return _LOG


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "")
    if _REQUEST_ID.fullmatch(supplied):
        return supplied
    return uuid4().hex


def _safe_path(path: str) -> str:
    cleaned = path.replace("\r", "").replace("\n", "")
    return cleaned[:200]


def create_app() -> FastAPI:
    application = FastAPI(title="Aadi CRM", version="0.1.0")
    log = _logger()
    log.info(
        "startup database_name=%s platform_base_configured=%s",
        resolve_database().label,
        bool(os.environ.get("PLATFORM_API_BASE_URL", "").strip()),
    )

    @application.middleware("http")
    async def diagnostics(request: Request, call_next):
        request_id = _request_id(request)
        path = _safe_path(request.url.path)
        started = time.perf_counter()
        failed = False
        try:
            response = await call_next(request)
        except Exception as exc:
            failed = True
            log.error(
                "unhandled method=%s path=%s status=500 duration_ms=%s request_id=%s error_type=%s",
                request.method,
                path,
                int((time.perf_counter() - started) * 1000),
                request_id,
                type(exc).__name__,
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "The request could not be completed.",
                    }
                },
            )
        duration_ms = int((time.perf_counter() - started) * 1000)
        if not failed and (response.status_code >= 400 or duration_ms >= _SLOW_MS):
            log.warning(
                "request method=%s path=%s status=%s duration_ms=%s request_id=%s",
                request.method,
                path,
                response.status_code,
                duration_ms,
                request_id,
            )
        response.headers["X-Request-Id"] = request_id
        return response

    application.add_middleware(
        CORSMiddleware,
        allow_origins=_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-CRM-Reminder-Test-Outcome", "X-Request-Id"],
        expose_headers=["X-CRM-Export-Rows", "X-Request-Id"],
    )
    application.include_router(shell_router)
    application.include_router(projects_router)
    application.include_router(forms_router)
    application.include_router(records_router)
    application.include_router(followups_router)
    application.include_router(reminders_router)
    application.include_router(imports_router)
    application.include_router(reporting_router)
    application.include_router(audit_router)
    return application


app = create_app()
