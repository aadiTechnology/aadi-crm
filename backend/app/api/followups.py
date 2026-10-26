"""Follow-up and activity routes.

Tenant, project, record, and actor come from the authenticated request.
A client cannot supply those values to widen access. Record visibility stays
on authorize_record.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from app.api.projects import _body, _error, _lookup_user, get_connection
from app.api.records import _allowed, _archived, _open, _validation
from app.api.shell import get_platform_client
from app.platform_client import PlatformClient, TenantUserView
from app.db import active_membership
from app.followups_store import (
    QUEUES,
    QUEUE_ZONE,
    TASK_TYPES,
    FollowUpConflict,
    FollowUpValidation,
    cancel_follow_up,
    complete_follow_up,
    create_follow_up,
    get_follow_up,
    list_activities,
    list_follow_ups,
    list_queue,
    update_follow_up,
)
from app.project_access import SCOPE_ASSIGNED
from app.reminders_store import sync_follow_up_reminders
from app.records_store import get_record

router = APIRouter(prefix="/api/v1", tags=["follow-ups"])

_CREATE_FIELDS = {"task_type", "owner_user_id", "due_date", "due_time", "summary", "call_status"}
_UPDATE_FIELDS = _CREATE_FIELDS | {"expected_updated_at"}
_FINISH_FIELDS = {"expected_updated_at", "outcome", "summary"}


def _record(connection, tenant_id: str, project_id: str, record_id: str, caller):
    record = get_record(connection, tenant_id, project_id, record_id)
    if record is None:
        return _error(404)
    if not _allowed(connection, tenant_id, project_id, caller, str(record["assignee_user_id"])):
        return _error(404)
    return record


def _owner(connection, platform: PlatformClient, tenant_id: UUID, project_id: UUID, owner_id: object, request: Request):
    if not isinstance(owner_id, str):
        return _validation("Choose an owner.", {"owner_user_id": "Owner must be an active member of this project."})
    try:
        parsed = str(UUID(owner_id))
    except ValueError:
        return _validation("Choose an owner.", {"owner_user_id": "Owner must be an active member of this project."})
    if active_membership(connection, str(tenant_id), str(project_id), parsed) is None:
        return _validation(
            "Choose an owner.",
            {"owner_user_id": "Owner must be an active member of this project."},
        )
    looked = _lookup_user(platform, tenant_id, parsed, request)
    if isinstance(looked, JSONResponse):
        if looked.status_code == 403:
            return parsed
        if looked.status_code in {404, 422}:
            return _validation(
                "Choose an owner.",
                {"owner_user_id": "Owner must be an active member of this project."},
            )
        return looked
    return parsed


def _text(value: object, field: str) -> str | JSONResponse:
    if not isinstance(value, str):
        return _validation("Request validation failed.", {field: "This value must be text."})
    return value


def _optional_text(payload: dict[str, object], field: str) -> str | None | JSONResponse:
    if field not in payload:
        return None
    return _text(payload[field], field)


def _store_error(exc: FollowUpValidation | FollowUpConflict) -> JSONResponse:
    if isinstance(exc, FollowUpConflict):
        return _error(409, exc.message)
    return _validation(exc.message, exc.fields or None)


def _page(items: list[dict[str, object]], total: int, limit: int, offset: int, **extra: object) -> JSONResponse:
    body: dict[str, object] = {"items": items, "total": total, "limit": limit, "offset": offset}
    body.update(extra)
    return JSONResponse(status_code=200, content=body)


@router.get("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/activities")
def read_activities(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, _loaded = opened
    record = _record(connection, str(tenant_id), str(project_id), str(record_id), caller)
    if isinstance(record, JSONResponse):
        return record
    items, total = list_activities(
        connection,
        str(tenant_id),
        str(project_id),
        str(record_id),
        limit=limit,
        offset=offset,
    )
    visible = [item for item in items if item["record_id"] == str(record_id)]
    return _page(visible, total, limit, offset)


@router.get("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups")
def read_follow_ups(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    task_type: str = "",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, _loaded = opened
    record = _record(connection, str(tenant_id), str(project_id), str(record_id), caller)
    if isinstance(record, JSONResponse):
        return record
    if task_type and task_type not in TASK_TYPES:
        return _validation("Task type is not valid.", {"task_type": "Choose a listed task type."})
    items, total = list_follow_ups(
        connection,
        str(tenant_id),
        str(project_id),
        str(record_id),
        task_type=task_type,
        limit=limit,
        offset=offset,
    )
    visible = [item for item in items if item["record_id"] == str(record_id)]
    return _page(visible, total, limit, offset)


@router.post("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups")
async def post_follow_up(
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
    record = _record(connection, str(tenant_id), str(project_id), str(record_id), caller)
    if isinstance(record, JSONResponse):
        return record
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not set(payload).issubset(_CREATE_FIELDS):
        return _validation("Request validation failed.")
    parsed = _follow_up_body(connection, platform, tenant_id, project_id, payload, request)
    if isinstance(parsed, JSONResponse):
        return parsed
    try:
        created = create_follow_up(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            record_id=str(record_id),
            actor_id=caller.user_id,
            **parsed,
        )
    except FollowUpValidation as exc:
        return _store_error(exc)
    if created is None or created["record_id"] != str(record_id) or created["created_by"] != caller.user_id:
        return _error(404)
    _schedule(connection, platform, tenant_id, caller, request, created)
    return JSONResponse(status_code=201, content=created)


@router.get("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups/{follow_up_id}")
def read_follow_up(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    follow_up_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, _loaded = opened
    follow_up = get_follow_up(connection, str(tenant_id), str(project_id), str(record_id), str(follow_up_id))
    if follow_up is None:
        return _error(404)
    record = get_record(connection, str(tenant_id), str(project_id), str(record_id))
    if record is None:
        return _error(404)
    if not _allowed(connection, str(tenant_id), str(project_id), caller, str(record["assignee_user_id"])):
        if follow_up["owner_user_id"] != caller.user_id or follow_up["status"] != "open":
            return _error(404)
    return JSONResponse(status_code=200, content=follow_up)


@router.patch("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups/{follow_up_id}")
async def patch_follow_up(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    follow_up_id: UUID,
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
    record = _record(connection, str(tenant_id), str(project_id), str(record_id), caller)
    if isinstance(record, JSONResponse):
        return record
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not payload or not set(payload).issubset(_UPDATE_FIELDS) or "expected_updated_at" not in payload:
        return _validation("Reload this follow-up before saving.")
    expected = payload.get("expected_updated_at")
    if not isinstance(expected, str) or not expected.strip():
        return _validation("Reload this follow-up before saving.")
    current = get_follow_up(connection, str(tenant_id), str(project_id), str(record_id), str(follow_up_id))
    if current is None:
        return _error(404)
    merged = {
        "task_type": payload.get("task_type", current["task_type"]),
        "owner_user_id": payload.get("owner_user_id", current["owner_user_id"]),
        "due_date": payload.get("due_date", current["due_date"]),
        "due_time": payload.get("due_time", current["due_time"]),
        "summary": payload.get("summary", current["summary"]),
        "call_status": payload["call_status"] if "call_status" in payload else current["call_status"],
    }
    parsed = _follow_up_body(connection, platform, tenant_id, project_id, merged, request)
    if isinstance(parsed, JSONResponse):
        return parsed
    try:
        updated = update_follow_up(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            record_id=str(record_id),
            follow_up_id=str(follow_up_id),
            actor_id=caller.user_id,
            expected_updated_at=expected,
            **parsed,
        )
    except (FollowUpValidation, FollowUpConflict) as exc:
        return _store_error(exc)
    if updated is None:
        return _error(404)
    _schedule(connection, platform, tenant_id, caller, request, updated)
    return JSONResponse(status_code=200, content=updated)


@router.post("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups/{follow_up_id}/complete")
async def post_complete(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    follow_up_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    return await _post_finish(
        tenant_id,
        project_id,
        record_id,
        follow_up_id,
        request,
        platform,
        connection,
        complete_follow_up,
    )


@router.post("/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups/{follow_up_id}/cancel")
async def post_cancel(
    tenant_id: UUID,
    project_id: UUID,
    record_id: UUID,
    follow_up_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    return await _post_finish(
        tenant_id,
        project_id,
        record_id,
        follow_up_id,
        request,
        platform,
        connection,
        cancel_follow_up,
    )


@router.get("/tenants/{tenant_id}/projects/{project_id}/follow-ups")
def read_queue(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    queue: str = "today",
    owner_user_id: str = "",
    task_type: str = "",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (_project, access) = opened
    if queue not in QUEUES:
        return _validation("Queue is not valid.", {"queue": "Choose Overdue, Today, or Upcoming."})
    if task_type and task_type not in TASK_TYPES:
        return _validation("Task type is not valid.", {"task_type": "Choose a listed task type."})
    owner: str | None
    record_assignee: str | None
    if access.record_scope() == SCOPE_ASSIGNED:
        owner = caller.user_id
        record_assignee = caller.user_id
    else:
        record_assignee = None
        if owner_user_id:
            try:
                owner = str(UUID(owner_user_id))
            except ValueError:
                return _validation("Owner filter is not valid.", {"owner_user_id": "Owner filter is not valid."})
        else:
            owner = None
    items, total, start, end = list_queue(
        connection,
        str(tenant_id),
        str(project_id),
        queue=queue,
        owner_user_id=owner,
        record_assignee_user_id=record_assignee,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )
    visible = []
    for item in items:
        if not _allowed(connection, str(tenant_id), str(project_id), caller, str(item["record_assignee_user_id"])):
            continue
        shown = dict(item)
        shown.pop("record_assignee_user_id", None)
        visible.append(shown)
    return _page(
        visible,
        total,
        limit,
        offset,
        queue=queue,
        timezone=QUEUE_ZONE,
        window_start=start,
        window_end=end,
        owner_user_id=owner,
    )


async def _post_finish(tenant_id, project_id, record_id, follow_up_id, request, platform, connection, action) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, _access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    record = _record(connection, str(tenant_id), str(project_id), str(record_id), caller)
    if isinstance(record, JSONResponse):
        return record
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not set(payload).issubset(_FINISH_FIELDS) or "expected_updated_at" not in payload or "outcome" not in payload:
        return _validation("Reload this follow-up before saving.")
    expected = payload.get("expected_updated_at")
    outcome = payload.get("outcome")
    if not isinstance(expected, str) or not expected.strip() or not isinstance(outcome, str):
        return _validation("Reload this follow-up before saving.")
    summary = _optional_text(payload, "summary")
    if isinstance(summary, JSONResponse):
        return summary
    try:
        finished = action(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            record_id=str(record_id),
            follow_up_id=str(follow_up_id),
            actor_id=caller.user_id,
            expected_updated_at=expected,
            outcome=outcome,
            summary=summary,
        )
    except (FollowUpValidation, FollowUpConflict) as exc:
        return _store_error(exc)
    if finished is None:
        return _error(404)
    _schedule(connection, platform, tenant_id, caller, request, finished)
    return JSONResponse(status_code=200, content=finished)


def _schedule(connection, platform, tenant_id, caller, request, follow_up) -> None:
    """Materialize reminder rows from the saved follow-up. Email comes from the directory."""

    owner = follow_up.get("owner_user_id")
    email = None
    if isinstance(owner, str):
        looked = _lookup_user(platform, tenant_id, owner, request)
        if isinstance(looked, TenantUserView):
            email = looked.email
        elif owner == caller.user_id:
            email = caller.email
    sync_follow_up_reminders(
        connection,
        tenant_id=str(tenant_id),
        follow_up=follow_up,
        recipient_email=email,
    )


def _follow_up_body(connection, platform, tenant_id, project_id, payload, request):
    task_type = payload.get("task_type", "")
    due_date = payload.get("due_date", "")
    due_time = payload.get("due_time", "")
    summary = payload.get("summary", "")
    if not isinstance(task_type, str) or not isinstance(due_date, str) or not isinstance(due_time, str):
        return _validation("Request validation failed.")
    if not isinstance(summary, str):
        return _validation("Request validation failed.", {"summary": "Summary must be text."})
    owner = _owner(connection, platform, tenant_id, project_id, payload.get("owner_user_id", ""), request)
    if isinstance(owner, JSONResponse):
        return owner
    call_status = payload.get("call_status")
    if call_status is not None and not isinstance(call_status, str):
        return _validation("Request validation failed.", {"call_status": "Call status must be text."})
    return {
        "task_type": task_type,
        "owner_user_id": owner,
        "due_date": due_date,
        "due_time": due_time,
        "summary": summary,
        "call_status": call_status,
    }
