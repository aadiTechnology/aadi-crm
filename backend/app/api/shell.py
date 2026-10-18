"""CRM shell routes. Path tenant id is a selector. Product access is the authority."""

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.platform_client import PlatformCallError, PlatformClient

LEADS_PERMISSION = "crm.lead_management.read"

router = APIRouter(prefix="/api/v1/shell", tags=["shell"])

_ERRORS = {
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have permission to perform this action."),
    404: ("RESOURCE_NOT_FOUND", "The requested resource was not found."),
    422: ("VALIDATION_ERROR", "Request validation failed."),
}


def get_platform_client() -> PlatformClient:
    base_url = os.environ.get("PLATFORM_API_BASE_URL", "http://localhost:8000")
    return PlatformClient(base_url)


def _error(status_code: int) -> JSONResponse:
    if status_code in _ERRORS:
        code, message = _ERRORS[status_code]
        http_status = status_code
    else:
        code, message = ("INTERNAL_ERROR", "The platform request could not be completed.")
        http_status = 502
    return JSONResponse(status_code=http_status, content={"error": {"code": code, "message": message}})


def _cookie(request: Request) -> str | None:
    header = request.headers.get("cookie")
    if header is None or not header.strip():
        return None
    return header


def _load_access(tenant_id: UUID, request: Request, platform: PlatformClient):
    try:
        access = platform.product_access(str(tenant_id), _cookie(request))
    except PlatformCallError as exc:
        return None, _error(exc.status_code)
    if access.tenant_id != str(tenant_id):
        return None, _error(404)
    return access, None


@router.get("/tenants/{tenant_id}")
def read_shell(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
) -> JSONResponse:
    access, failure = _load_access(tenant_id, request, platform)
    if failure is not None or access is None:
        return failure if failure is not None else _error(404)
    return JSONResponse(
        status_code=200,
        content={
            "tenant_id": access.tenant_id,
            "tenant_name": access.tenant_name,
            "product_name": access.product_name,
            "available": access.available,
        },
    )


@router.get("/tenants/{tenant_id}/leads")
def read_leads(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
) -> JSONResponse:
    access, failure = _load_access(tenant_id, request, platform)
    if failure is not None or access is None:
        return failure if failure is not None else _error(404)
    try:
        keys = platform.permissions(str(tenant_id), _cookie(request))
    except PlatformCallError as exc:
        return _error(exc.status_code)
    if not access.available or LEADS_PERMISSION not in keys:
        return _error(403)
    return JSONResponse(status_code=200, content={"module": "leads", "items": []})
