"""Reminder inbox, delivery, and failure review.

Tenant and actor come from the authenticated request. Record labels are added
only after authorize_record allows the record on this request.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.projects import _error, _lookup_user, _open_module, get_connection
from app.api.records import _allowed
from app.api.shell import get_platform_client
from app.followups_store import QUEUE_ZONE, civil_due
from app.platform_client import PlatformClient, TenantUserView
from app.project_access import FEATURE_RECORDS
from app.reminders_store import (
    build_adapter,
    email_mode,
    list_failures,
    list_inbox,
    managed_project_ids,
    mark_read,
    open_owner_ids,
    process_reminders,
    retry_delivery,
)

router = APIRouter(prefix="/api/v1", tags=["reminders"])

_KIND_LABELS = {
    "follow_up_assigned": "Follow-up assigned",
    "follow_up_due": "Follow-up due",
}
_STATE_LABELS = {
    "pending": "Pending",
    "processing": "Processing",
    "sent": "Delivered in the app",
    "recorded": "Recorded by the test adapter. Not delivered.",
    "retryable": "Waiting for retry",
    "failed": "Stopped",
    "suppressed": "Not sent",
}
_ERROR_LABELS = {
    "test_adapter_recorded": "Recorded by the test adapter. Not delivered.",
    "provider_temporary": "The email attempt failed and can be retried.",
    "provider_rejected": "The email provider rejected the reminder.",
    "provider_not_configured": "No email provider is configured. The reminder was not sent.",
    "recipient_email_unavailable": "The organization directory did not provide an email for this person.",
    "suppressed_follow_up_closed": "The follow-up was completed or cancelled before delivery.",
    "suppressed_owner_changed": "The follow-up owner changed before delivery.",
    "suppressed_due_changed": "The follow-up due time changed before delivery.",
    "suppressed_not_current": "This reminder is no longer current.",
}


def _test_outcome(request: Request) -> str | None:
    if email_mode() != "test":
        return None
    value = request.headers.get("x-crm-reminder-test-outcome", "")
    if value in {"recorded", "retryable", "terminal"}:
        return value
    return None


def _safe_error(value: object) -> str | None:
    if isinstance(value, str) and value in _ERROR_LABELS:
        return value
    return None


def _record(connection, tenant_id: str, project_id: str, record_id: str):
    return connection.execute(
        """
        SELECT public_number, assignee_user_id, deleted_at
        FROM records
        WHERE tenant_id = ? AND project_id = ? AND id = ?
        """,
        (tenant_id, project_id, record_id),
    ).fetchone()


def _item(connection, caller, row, *, include_recipient: bool) -> dict[str, object]:
    due_date, due_time = civil_due(str(row["due_at"]))
    record = _record(connection, str(row["tenant_id"]), str(row["project_id"]), str(row["record_id"]))
    available = (
        record is not None
        and record["deleted_at"] is None
        and _allowed(connection, str(row["tenant_id"]), str(row["project_id"]), caller, record["assignee_user_id"])
    )
    error = _safe_error(row["last_error"])
    body: dict[str, object] = {
        "id": row["id"],
        "kind": row["kind"],
        "kind_label": _KIND_LABELS.get(str(row["kind"]), "Reminder"),
        "channel": row["channel"],
        "state": row["state"],
        "state_label": _STATE_LABELS.get(str(row["state"]), "Reminder"),
        "due_date": due_date,
        "due_time": due_time,
        "timezone": QUEUE_ZONE,
        "read": row["read_at"] is not None,
        "attempt_count": row["attempt_count"],
        "last_attempt_at": row["last_attempt_at"],
        "next_retry_at": row["next_retry_at"],
        "last_error": error,
        "failure_label": None if error is None else _ERROR_LABELS[error],
        "record_available": available,
    }
    if available and record is not None:
        body["project_id"] = row["project_id"]
        body["record_id"] = row["record_id"]
        body["follow_up_id"] = row["follow_up_id"]
        body["public_number"] = record["public_number"]
    if include_recipient:
        body["recipient_user_id"] = row["recipient_user_id"]
        body["recipient_email"] = row["recipient_email"]
    return body


@router.get("/tenants/{tenant_id}/reminders")
def read_reminders(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=False, feature_key=FEATURE_RECORDS)
    if isinstance(opened, JSONResponse):
        return opened
    rows = list_inbox(connection, str(tenant_id), opened.user_id)
    items = [_item(connection, opened, row, include_recipient=False) for row in rows]
    return JSONResponse(status_code=200, content={"items": items, "total": len(items), "timezone": QUEUE_ZONE})


@router.get("/tenants/{tenant_id}/reminders/failures")
def read_failures(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=False, feature_key=FEATURE_RECORDS)
    if isinstance(opened, JSONResponse):
        return opened
    projects = managed_project_ids(
        connection, str(tenant_id), opened.user_id, opened.tenant_membership_id
    )
    if not projects:
        return _error(403, "You do not have permission to perform this action.")
    rows = list_failures(connection, str(tenant_id), projects)
    items = [_item(connection, opened, row, include_recipient=True) for row in rows]
    return JSONResponse(status_code=200, content={"items": items, "total": len(items)})


@router.post("/tenants/{tenant_id}/reminders/process")
def post_process(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True, feature_key=FEATURE_RECORDS)
    if isinstance(opened, JSONResponse):
        return opened
    mode = email_mode()
    projects = managed_project_ids(
        connection, str(tenant_id), opened.user_id, opened.tenant_membership_id
    )
    resolved: dict[str, str] = {}
    for owner in open_owner_ids(connection, str(tenant_id), projects):
        looked = _lookup_user(platform, tenant_id, owner, request)
        if isinstance(looked, TenantUserView):
            resolved[owner] = looked.email
        elif owner == opened.user_id and opened.email:
            resolved[owner] = opened.email
    stats = process_reminders(
        connection,
        tenant_id=str(tenant_id),
        actor_user_id=opened.user_id,
        tenant_membership_id=opened.tenant_membership_id,
        mode=mode,
        adapter=build_adapter(mode, _test_outcome(request)),
        emails=resolved,
    )
    return JSONResponse(
        status_code=200,
        content={
            **stats,
            "email_mode": mode,
            "email_provider_confirmed": mode == "live" and stats["email_sent"] > 0,
        },
    )


@router.post("/tenants/{tenant_id}/reminders/{reminder_id}/read")
def post_read(
    tenant_id: UUID,
    reminder_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True, feature_key=FEATURE_RECORDS)
    if isinstance(opened, JSONResponse):
        return opened
    row = mark_read(connection, tenant_id=str(tenant_id), user_id=opened.user_id, reminder_id=str(reminder_id))
    if row is None:
        return _error(404)
    return JSONResponse(status_code=200, content=_item(connection, opened, row, include_recipient=False))


@router.post("/tenants/{tenant_id}/reminders/{reminder_id}/retry")
def post_retry(
    tenant_id: UUID,
    reminder_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True, feature_key=FEATURE_RECORDS)
    if isinstance(opened, JSONResponse):
        return opened
    projects = managed_project_ids(
        connection, str(tenant_id), opened.user_id, opened.tenant_membership_id
    )
    if not projects:
        return _error(403, "You do not have permission to perform this action.")
    row = retry_delivery(
        connection,
        tenant_id=str(tenant_id),
        project_ids=projects,
        reminder_id=str(reminder_id),
    )
    if row is None or row["state"] not in {"pending", "retryable", "failed"}:
        return _error(404)
    return JSONResponse(status_code=200, content=_item(connection, opened, row, include_recipient=True))
