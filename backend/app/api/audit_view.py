"""Read-only presentation of the platform audit log.

The CRM does not store a second copy. Filters the platform cannot apply are
rejected here instead of being applied to one page of results.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.projects import _error, _open_module, get_connection
from app.api.records import _validation
from app.api.shell import get_platform_client
from app.platform_client import PlatformCallError, PlatformClient, visible_audit_events

router = APIRouter(prefix="/api/v1", tags=["audit"])

_AUDIT_PARAMS = {"limit"}


@router.get("/tenants/{tenant_id}/audit-events")
def read_audit_events(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    limit: int = Query(default=50, ge=1, le=100),
) -> JSONResponse:
    del connection
    opened = _open_module(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    extra = set(request.query_params) - _AUDIT_PARAMS
    if extra:
        return _validation(
            "The organization audit log cannot be filtered by that field.",
            {name: "This filter is not available." for name in sorted(extra)},
        )
    cookie = request.headers.get("cookie")
    try:
        items = visible_audit_events(platform.list_audit_events(str(tenant_id), cookie, limit=limit))
    except PlatformCallError as exc:
        if exc.status_code in {401, 403, 404}:
            return _error(exc.status_code)
        return _error(502, "The audit log is unavailable.")
    return JSONResponse(
        status_code=200,
        content={"items": items, "limit": limit, "source": "platform"},
    )
