"""Record list, search, detail, create, edit, and soft delete.

Tenant, project, and form version come from the authenticated path and the
published form. A client cannot supply those identifiers to widen access.
"""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.projects import _body, _error, _load_project, _lookup_user, _open_module, _user_id, authorize_record, get_connection
from app.api.shell import get_platform_client
from app.db import active_membership
from app.platform_client import PlatformClient
from app.project_access import FEATURE_RECORDS, SCOPE_ASSIGNED, RecordRef
from app.records_store import (
    SOURCES,
    RecordListQuery,
    pipeline_status_param,
    RecordValidation,
    StaleRecord,
    UnpublishedForm,
    archive_record,
    assign_record,
    create_record,
    get_record,
    list_records,
    update_record,
)

router = APIRouter(prefix="/api/v1", tags=["records"])

_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _calendar_date(value: str) -> bool:
    if not _DATE.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _validation(message: str, fields: dict[str, str] | None = None) -> JSONResponse:
    body: dict[str, object] = {"error": {"code": "VALIDATION_ERROR", "message": message}}
    if fields:
        body["error"]["fields"] = fields
    return JSONResponse(status_code=422, content=body)


def _open(tenant_id, project_id, request, platform, connection, *, write: bool):
    opened = _open_module(tenant_id, request, platform, write=write, feature_key=FEATURE_RECORDS)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "access_records")
    if isinstance(loaded, JSONResponse):
        return loaded
    return opened, loaded


def _allowed(
    connection,
    tenant_id: str,
    project_id: str,
    caller,
    assignee_user_id: str | None,
    record_id: str | None = None,
    *,
    include_follow_up_owner: bool = False,
) -> bool:
    decision = authorize_record(
        connection,
        tenant_id=tenant_id,
        project_id=project_id,
        caller=caller,
        record=RecordRef(
            tenant_id=tenant_id,
            project_id=project_id,
            assignee_user_id=assignee_user_id,
        ),
    )
    if decision.allowed:
        return True
    if not include_follow_up_owner or not record_id:
        return False
    owned = connection.execute(
        """
        SELECT id
        FROM follow_ups
        WHERE tenant_id = ? AND project_id = ? AND record_id = ?
          AND owner_user_id = ? AND status = 'open'
        LIMIT 1
        """,
        (tenant_id, project_id, record_id, caller.user_id),
    ).fetchone()
    return owned is not None


def _archived(project) -> JSONResponse | None:
    if project.status == "archived":
        return _error(409, "This project is archived.")
    return None


@router.get("/tenants/{tenant_id}/projects/{project_id}/records")
def read_records(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    q: str = "",
    form_id: str = "",
    source: str = "",
    created_from: str = "",
    created_to: str = "",
    status: str = "",
    sort: str = "created_at",
    direction: str = "desc",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, access) = opened
    del project
    if form_id and not _UUID.fullmatch(form_id):
        return _validation("Form filter is not valid.")
    if source and source not in SOURCES:
        return _validation("Source filter is not valid.")
    if created_from and not _calendar_date(created_from):
        return _validation("Created-from must use YYYY-MM-DD.")
    if created_to and not _calendar_date(created_to):
        return _validation("Created-to must use YYYY-MM-DD.")
    if created_from and created_to and created_from > created_to:
        return _validation("Created-from cannot be after created-to.")
    try:
        status = pipeline_status_param(status)
    except ValueError:
        return _validation("Status filter is not valid.")
    if sort not in {"created_at", "updated_at", "public_number"}:
        return _validation("Sort is not valid.")
    if direction not in {"asc", "desc"}:
        return _validation("Sort direction is not valid.")
    assignee = caller.user_id if access.record_scope() == SCOPE_ASSIGNED else None
    items, total = list_records(
        connection,
        str(tenant_id),
        str(project_id),
        RecordListQuery(
            search=q.strip(),
            form_id=form_id,
            source=source,
            created_from=created_from,
            created_to=created_to,
            status=status,
            sort=sort,
            direction=direction,
            limit=limit,
            offset=offset,
            assignee_user_id=assignee,
        ),
    )
    visible = [
        item
        for item in items
        if _allowed(connection, str(tenant_id), str(project_id), caller, str(item["assignee_user_id"]))
    ]
    return JSONResponse(
        status_code=200,
        content={"items": visible, "total": total, "limit": limit, "offset": offset},
    )


@router.post("/tenants/{tenant_id}/projects/{project_id}/records")
async def post_record(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, _access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    form_id = payload.get("form_id")
    if not isinstance(form_id, str) or not _UUID.fullmatch(form_id):
        return _validation("Choose a published form.")
    source = payload.get("source", "manual")
    if not isinstance(source, str) or source not in SOURCES:
        return _validation("Source is not one of the listed values.")
    raw_values = payload.get("values", {})
    if not isinstance(raw_values, dict):
        return _validation("Record values must be an object.")
    if not _allowed(connection, str(tenant_id), str(project_id), caller, caller.user_id):
        return _error(403)
    try:
        created = create_record(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            project_code=project.code,
            form_id=form_id,
            actor_id=caller.user_id,
            source=source,
            values=raw_values,
        )
    except UnpublishedForm as exc:
        return _error(409, exc.message)
    except RecordValidation as exc:
        return _validation(exc.message, exc.fields)
    if created is None:
        return _error(404)
    if created["created_by"] != caller.user_id or created["form_id"] != form_id:
        return _error(404)
    return JSONResponse(status_code=201, content=created)


@router.get("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}")
def read_record(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, _loaded = opened
    record = get_record(connection, str(tenant_id), str(project_id), str(record_id))
    if record is None:
        return _error(404)
    if not _allowed(
        connection,
        str(tenant_id),
        str(project_id),
        caller,
        str(record["assignee_user_id"]),
        str(record_id),
        include_follow_up_owner=True,
    ):
        return _error(404)
    return JSONResponse(status_code=200, content=record)


@router.patch("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}")
async def patch_record(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, _access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    current = get_record(connection, str(tenant_id), str(project_id), str(record_id))
    if current is None:
        return _error(404)
    if not _allowed(connection, str(tenant_id), str(project_id), caller, str(current["assignee_user_id"])):
        return _error(404)
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    expected = payload.get("expected_updated_at")
    if not isinstance(expected, str) or not expected.strip():
        return _validation("Reload this record before saving.")
    raw_values = payload.get("values")
    if not isinstance(raw_values, dict):
        return _validation("Record values must be an object.")
    version_id = current["form_version_id"]
    try:
        updated = update_record(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            record_id=str(record_id),
            actor_id=caller.user_id,
            expected_updated_at=expected,
            values=raw_values,
        )
    except StaleRecord as exc:
        return _error(409, exc.message)
    except RecordValidation as exc:
        return _validation(exc.message, exc.fields)
    if updated is None or updated["form_version_id"] != version_id:
        return _error(404)
    return JSONResponse(status_code=200, content=updated)


@router.post("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/assign")
async def post_assign_record(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    current = get_record(connection, str(tenant_id), str(project_id), str(record_id))
    if current is None:
        return _error(404)
    if not _allowed(connection, str(tenant_id), str(project_id), caller, str(current["assignee_user_id"])):
        return _error(404)
    if not access.allows("add_member"):
        return _error(403)
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not set(payload).issubset({"assignee_user_id", "expected_updated_at"}):
        return _validation("Request validation failed.")
    expected = payload.get("expected_updated_at")
    if not isinstance(expected, str) or not expected.strip():
        return _validation("Reload this record before saving.")
    assignee = _user_id(payload.get("assignee_user_id", ""))
    if isinstance(assignee, JSONResponse):
        return assignee
    user = _lookup_user(platform, tenant_id, assignee, request)
    if isinstance(user, JSONResponse):
        return user
    membership = active_membership(connection, str(tenant_id), str(project_id), assignee)
    bound = "" if membership is None else (membership.tenant_membership_id or "").strip()
    if membership is None or not bound or bound != user.membership_id.strip():
        return _validation("Choose an active project member.")
    try:
        updated = assign_record(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            record_id=str(record_id),
            actor_id=caller.user_id,
            assignee_user_id=assignee,
            expected_updated_at=expected,
        )
    except StaleRecord as exc:
        return _error(409, exc.message)
    if updated is None:
        return _error(404)
    return JSONResponse(status_code=200, content=updated)


@router.post("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/archive")
async def post_archive_record(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, _access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    current = get_record(connection, str(tenant_id), str(project_id), str(record_id))
    if current is None:
        return _error(404)
    if not _allowed(connection, str(tenant_id), str(project_id), caller, str(current["assignee_user_id"])):
        return _error(404)
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    expected = payload.get("expected_updated_at")
    if not isinstance(expected, str) or not expected.strip():
        return _validation("Reload this record before archiving.")
    try:
        archived_row = archive_record(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            record_id=str(record_id),
            actor_id=caller.user_id,
            expected_updated_at=expected,
        )
    except StaleRecord as exc:
        return _error(409, exc.message)
    if not archived_row:
        return _error(404)
    return JSONResponse(status_code=200, content={"id": str(record_id), "archived": True})
