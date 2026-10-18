"""CRM product API. Session cookies are issued only by the Control Plane."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    application.include_router(shell_router)
    return application


app = create_app()
