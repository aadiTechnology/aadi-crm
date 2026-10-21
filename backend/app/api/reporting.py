"""Project KPI and completed-follow-up reads.

The counts use the same visibility rule as the record list and the follow-up
queues. This module does not change authorize_record.
"""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.projects import get_connection
from app.api.records import _allowed, _open, _validation
from app.api.shell import get_platform_client
from app.platform_client import PlatformClient
from app.project_access import SCOPE_ASSIGNED
from app.reporting_store import list_completed_follow_ups, project_kpis

router = APIRouter(prefix="/api/v1", tags=["reporting"])

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_KPI_PARAMS = {"created_from", "created_to"}
_COMPLETED_PARAMS = {"limit", "offset"}


def _calendar_date(value: str) -> bool:
    if not _DATE.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _scope(caller, access) -> str | None:
    if access.record_scope() == SCOPE_ASSIGNED:
        return caller.user_id
    return None


@router.get("/tenants/{tenant_id}/projects/{project_id}/kpis")
def read_kpis(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    created_from: str = "",
    created_to: str = "",
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    extra = set(request.query_params) - _KPI_PARAMS
    if extra:
        return _validation("That filter is not part of the project KPIs.")
    if created_from and not _calendar_date(created_from):
        return _validation("Created-from must use YYYY-MM-DD.")
    if created_to and not _calendar_date(created_to):
        return _validation("Created-to must use YYYY-MM-DD.")
    if created_from and created_to and created_from > created_to:
        return _validation("Created-from cannot be after created-to.")
    caller, (_project, access) = opened
    body = project_kpis(
        connection,
        str(tenant_id),
        str(project_id),
        assignee_user_id=_scope(caller, access),
        created_from=created_from,
        created_to=created_to,
    )
    return JSONResponse(status_code=200, content=body)


@router.get("/tenants/{tenant_id}/projects/{project_id}/kpis/completed-follow-ups")
def read_completed_follow_ups(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    extra = set(request.query_params) - _COMPLETED_PARAMS
    if extra:
        return _validation("That filter is not part of the completed follow-up list.")
    caller, (_project, access) = opened
    items, total = list_completed_follow_ups(
        connection,
        str(tenant_id),
        str(project_id),
        assignee_user_id=_scope(caller, access),
        limit=limit,
        offset=offset,
    )
    visible = []
    for item in items:
        assignee = item.get("record_assignee_user_id")
        if not _allowed(connection, str(tenant_id), str(project_id), caller, None if assignee is None else str(assignee)):
            continue
        shown = dict(item)
        shown.pop("record_assignee_user_id", None)
        visible.append(shown)
    return JSONResponse(
        status_code=200,
        content={"items": visible, "total": total, "limit": limit, "offset": offset, "status": "completed"},
    )
