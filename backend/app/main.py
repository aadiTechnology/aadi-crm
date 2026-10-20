"""CRM product API. Session cookies are issued only by the Control Plane."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.followups import router as followups_router
from app.api.reminders import router as reminders_router
from app.api.forms import router as forms_router
from app.api.projects import router as projects_router
from app.api.records import router as records_router
from app.api.shell import router as shell_router

_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]


def create_app() -> FastAPI:
    application = FastAPI(title="Aadi CRM", version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-CRM-Reminder-Test-Outcome"],
    )
    application.include_router(shell_router)
    application.include_router(projects_router)
    application.include_router(forms_router)
    application.include_router(records_router)
    application.include_router(followups_router)
    application.include_router(reminders_router)
    return application


app = create_app()
