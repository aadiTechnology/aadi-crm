"""Follow-ups and the user-facing record timeline.

Timestamps are UTC. Civil due dates are interpreted in Asia/Kolkata because
the CRM project and the tenant configuration document do not store a timezone.
Queue names are calculated from the due instant. They are not stored.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

QUEUE_ZONE = "Asia/Kolkata"
TASK_TYPES = ("call", "whatsapp", "email", "meeting", "note")
CALL_STATUSES = ("connected", "busy", "not_connected", "switched_off", "not_valid")
QUEUES = ("overdue", "today", "upcoming")
SUMMARY_MAX = 2000
OUTCOME_MAX = 500
_STAMP = "%Y-%m-%dT%H:%M:%S.%f+00:00"

TASK_LABELS = {
    "call": "Call",
    "whatsapp": "WhatsApp",
    "email": "Email",
    "meeting": "Meeting",
    "note": "Note",
}
CALL_LABELS = {
    "connected": "Connected",
    "busy": "Busy",
    "not_connected": "Not connected",
    "switched_off": "Switched off",
    "not_valid": "Not valid",
}
STATUS_LABELS = {"open": "Open", "completed": "Completed", "cancelled": "Cancelled"}
EVENT_LABELS = {
    "follow_up.created": "Follow-up created",
    "follow_up.updated": "Follow-up updated",
    "follow_up.rescheduled": "Follow-up rescheduled",
    "follow_up.reassigned": "Follow-up reassigned",
    "follow_up.completed": "Follow-up completed",
    "follow_up.cancelled": "Follow-up cancelled",
}


class FollowUpValidation(Exception):
    def __init__(self, message: str, fields: dict[str, str] | None = None) -> None:
        self.message = message
        self.fields = fields or {}


class FollowUpConflict(Exception):
    def __init__(self, message: str) -> None:
        self.message = message


def clock() -> datetime:
    return datetime.now(UTC)


def utc_due(due_date: str, due_time: str, timezone_name: str) -> str:
    """Convert a civil date and time to a UTC instant.

    A time that falls in a daylight-saving gap or that occurs twice is rejected.
    """

    _calendar_date(due_date)
    _clock_time(due_time)
    zone = _zone(timezone_name)
    local = datetime.strptime(f"{due_date} {due_time}", "%Y-%m-%d %H:%M")
    return stamp(_attach(local, zone))


def queue_window(now: datetime, timezone_name: str = QUEUE_ZONE) -> tuple[str, str]:
    """Start of the local calendar day and the start of the next day, in UTC."""

    zone = _zone(timezone_name)
    local = now.astimezone(zone)
    start_naive = datetime(local.year, local.month, local.day)
    start = _attach(start_naive, zone)
    next_day = start_naive.date() + timedelta(days=1)
    end = _attach(datetime(next_day.year, next_day.month, next_day.day), zone)
    return stamp(start), stamp(end)


def queue_for(due_at: str, start: str, end: str, status: str) -> str | None:
    if status != "open":
        return None
    if due_at < start:
        return "overdue"
    if due_at < end:
        return "today"
    return "upcoming"


def create_follow_up(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    actor_id: str,
    task_type: str,
    owner_user_id: str,
    due_date: str,
    due_time: str,
    summary: str,
    call_status: str | None,
) -> dict[str, object] | None:
    if _live_record(connection, tenant_id, project_id, record_id) is None:
        return None
    fields = _checked(task_type, due_date, due_time, summary, call_status)
    follow_up_id = str(uuid4())
    now = clock()
    created_at = stamp(now)
    _insert_follow_up(
        connection,
        follow_up_id=follow_up_id,
        tenant_id=tenant_id,
        project_id=project_id,
        record_id=record_id,
        task_type=fields["task_type"],
        owner_user_id=owner_user_id,
        due_at=fields["due_at"],
        call_status=fields["call_status"],
        summary=fields["summary"],
        actor_id=actor_id,
        created_at=created_at,
    )
    _activity(
        connection,
        tenant_id=tenant_id,
        project_id=project_id,
        record_id=record_id,
        follow_up_id=follow_up_id,
        actor_id=actor_id,
        event_type="follow_up.created",
        summary=_created_summary(fields["task_type"], fields["due_at"]),
        occurred_at=created_at,
    )
    connection.commit()
    return get_follow_up(connection, tenant_id, project_id, record_id, follow_up_id)


def list_follow_ups(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    record_id: str,
    *,
    task_type: str,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    clauses = ["tenant_id = ?", "project_id = ?", "record_id = ?"]
    params: list[object] = [tenant_id, project_id, record_id]
    if task_type:
        clauses.append("task_type = ?")
        params.append(task_type)
    where = " AND ".join(clauses)
    total = _count(connection, f"SELECT COUNT(*) AS count FROM follow_ups WHERE {where}", params)
    rows = connection.execute(
        f"""
        SELECT * FROM follow_ups
        WHERE {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return [_follow_up(row) for row in rows], total


def get_follow_up(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    record_id: str,
    follow_up_id: str,
) -> dict[str, object] | None:
    row = connection.execute(
        """
        SELECT * FROM follow_ups
        WHERE tenant_id = ? AND project_id = ? AND record_id = ? AND id = ?
        """,
        (tenant_id, project_id, record_id, follow_up_id),
    ).fetchone()
    if row is None:
        return None
    return _follow_up(row)


def update_follow_up(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    follow_up_id: str,
    actor_id: str,
    expected_updated_at: str,
    task_type: str,
    owner_user_id: str,
    due_date: str,
    due_time: str,
    summary: str,
    call_status: str | None,
) -> dict[str, object] | None:
    current = get_follow_up(connection, tenant_id, project_id, record_id, follow_up_id)
    if current is None:
        return None
    _open_for_change(current, expected_updated_at)
    fields = _checked(task_type, due_date, due_time, summary, call_status)
    events: list[tuple[str, str]] = []
    if fields["task_type"] != current["task_type"] or fields["summary"] != current["summary"] or fields["call_status"] != current["call_status"]:
        events.append(("follow_up.updated", f"{TASK_LABELS[fields['task_type']]} follow-up was updated."))
    if fields["due_at"] != current["due_at"]:
        events.append(("follow_up.rescheduled", _rescheduled_summary(fields["task_type"], fields["due_at"])))
    if owner_user_id != current["owner_user_id"]:
        events.append(("follow_up.reassigned", f"{TASK_LABELS[fields['task_type']]} follow-up owner was changed."))
    if not events:
        return current
    now = clock()
    updated_at = stamp(now)
    connection.execute(
        """
        UPDATE follow_ups
        SET task_type = ?, owner_user_id = ?, due_at = ?, call_status = ?, summary = ?,
            updated_by = ?, updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND record_id = ? AND id = ?
          AND status = 'open' AND updated_at = ?
        """,
        (
            fields["task_type"],
            owner_user_id,
            fields["due_at"],
            fields["call_status"],
            fields["summary"],
            actor_id,
            updated_at,
            tenant_id,
            project_id,
            record_id,
            follow_up_id,
            expected_updated_at,
        ),
    )
    if connection.execute("SELECT changes()").fetchone()[0] == 0:
        connection.rollback()
        raise FollowUpConflict("Reload this follow-up before saving.")
    for index, (event_type, text) in enumerate(events):
        _activity(
            connection,
            tenant_id=tenant_id,
            project_id=project_id,
            record_id=record_id,
            follow_up_id=follow_up_id,
            actor_id=actor_id,
            event_type=event_type,
            summary=text,
            occurred_at=stamp(now + timedelta(microseconds=index)),
        )
    connection.commit()
    return get_follow_up(connection, tenant_id, project_id, record_id, follow_up_id)


def complete_follow_up(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    follow_up_id: str,
    actor_id: str,
    expected_updated_at: str,
    outcome: str,
    summary: str | None,
) -> dict[str, object] | None:
    return _finish(
        connection,
        tenant_id=tenant_id,
        project_id=project_id,
        record_id=record_id,
        follow_up_id=follow_up_id,
        actor_id=actor_id,
        expected_updated_at=expected_updated_at,
        outcome=_outcome(outcome),
        summary=summary,
        status="completed",
        event_type="follow_up.completed",
    )


def cancel_follow_up(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    follow_up_id: str,
    actor_id: str,
    expected_updated_at: str,
    outcome: str,
    summary: str | None,
) -> dict[str, object] | None:
    return _finish(
        connection,
        tenant_id=tenant_id,
        project_id=project_id,
        record_id=record_id,
        follow_up_id=follow_up_id,
        actor_id=actor_id,
        expected_updated_at=expected_updated_at,
        outcome=_optional_outcome(outcome),
        summary=summary,
        status="cancelled",
        event_type="follow_up.cancelled",
    )


def list_activities(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    record_id: str,
    *,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    params: list[object] = [tenant_id, project_id, record_id]
    where = "tenant_id = ? AND project_id = ? AND record_id = ?"
    total = _count(connection, f"SELECT COUNT(*) AS count FROM record_activities WHERE {where}", params)
    rows = connection.execute(
        f"""
        SELECT * FROM record_activities
        WHERE {where}
        ORDER BY occurred_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return [_activity_row(row) for row in rows], total


def list_queue(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    *,
    queue: str,
    owner_user_id: str | None,
    record_assignee_user_id: str | None,
    task_type: str,
    limit: int,
    offset: int,
    now: datetime | None = None,
) -> tuple[list[dict[str, object]], int, str, str]:
    start, end = queue_window(now or clock(), QUEUE_ZONE)
    clauses = [
        "follow_ups.tenant_id = ?",
        "follow_ups.project_id = ?",
        "follow_ups.status = 'open'",
        "records.deleted_at IS NULL",
    ]
    params: list[object] = [tenant_id, project_id]
    if queue == "overdue":
        clauses.append("follow_ups.due_at < ?")
        params.append(start)
    elif queue == "today":
        clauses.append("follow_ups.due_at >= ? AND follow_ups.due_at < ?")
        params.extend([start, end])
    elif queue == "upcoming":
        clauses.append("follow_ups.due_at >= ?")
        params.append(end)
    else:
        raise FollowUpValidation("Queue is not valid.", {"queue": "Choose Overdue, Today, or Upcoming."})
    if owner_user_id is not None:
        clauses.append("follow_ups.owner_user_id = ?")
        params.append(owner_user_id)
    if record_assignee_user_id is not None:
        clauses.append("records.assignee_user_id = ?")
        params.append(record_assignee_user_id)
    if task_type:
        clauses.append("follow_ups.task_type = ?")
        params.append(task_type)
    where = " AND ".join(clauses)
    joined = f"""
        FROM follow_ups
        JOIN records
          ON records.id = follow_ups.record_id
         AND records.tenant_id = follow_ups.tenant_id
         AND records.project_id = follow_ups.project_id
        WHERE {where}
    """
    total = _count(connection, f"SELECT COUNT(*) AS count {joined}", params)
    rows = connection.execute(
        f"""
        SELECT follow_ups.*, records.public_number, records.display_name, records.assignee_user_id
        {joined}
        ORDER BY follow_ups.due_at ASC, follow_ups.id ASC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return [_queue_row(row) for row in rows], total, start, end


def stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime(_STAMP)


def civil_due(due_at: str) -> tuple[str, str]:
    parsed = datetime.strptime(due_at, _STAMP).replace(tzinfo=UTC)
    local = parsed.astimezone(ZoneInfo(QUEUE_ZONE))
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def _finish(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    follow_up_id: str,
    actor_id: str,
    expected_updated_at: str,
    outcome: str,
    summary: str | None,
    status: str,
    event_type: str,
) -> dict[str, object] | None:
    current = get_follow_up(connection, tenant_id, project_id, record_id, follow_up_id)
    if current is None:
        return None
    _open_for_change(current, expected_updated_at)
    next_summary = current["summary"] if summary is None else _summary(summary)
    now = clock()
    moment = stamp(now)
    column = "completed_at" if status == "completed" else "cancelled_at"
    connection.execute(
        f"""
        UPDATE follow_ups
        SET status = ?, outcome = ?, summary = ?, updated_by = ?, updated_at = ?, {column} = ?
        WHERE tenant_id = ? AND project_id = ? AND record_id = ? AND id = ?
          AND status = 'open' AND updated_at = ?
        """,
        (
            status,
            outcome,
            next_summary,
            actor_id,
            moment,
            moment,
            tenant_id,
            project_id,
            record_id,
            follow_up_id,
            expected_updated_at,
        ),
    )
    if connection.execute("SELECT changes()").fetchone()[0] == 0:
        connection.rollback()
        raise FollowUpConflict("Reload this follow-up before saving.")
    label = TASK_LABELS[str(current["task_type"])]
    text = f"{label} follow-up was completed. Outcome: {outcome}" if status == "completed" else f"{label} follow-up was cancelled."
    if status == "cancelled" and outcome:
        text = f"{text} Outcome: {outcome}"
    _activity(
        connection,
        tenant_id=tenant_id,
        project_id=project_id,
        record_id=record_id,
        follow_up_id=follow_up_id,
        actor_id=actor_id,
        event_type=event_type,
        summary=text,
        occurred_at=moment,
    )
    connection.commit()
    return get_follow_up(connection, tenant_id, project_id, record_id, follow_up_id)


def _open_for_change(current: dict[str, object], expected_updated_at: str) -> None:
    if current["status"] != "open":
        raise FollowUpConflict("This follow-up is already finished and was not changed.")
    if current["updated_at"] != expected_updated_at:
        raise FollowUpConflict("Reload this follow-up before saving.")


def _checked(
    task_type: str,
    due_date: str,
    due_time: str,
    summary: str,
    call_status: str | None,
) -> dict[str, str | None]:
    fields: dict[str, str] = {}
    if task_type not in TASK_TYPES:
        fields["task_type"] = "Choose Call, WhatsApp, Email, Meeting, or Note."
    if call_status in ("", None):
        normalized_call: str | None = None
    else:
        normalized_call = call_status
    if task_type == "call":
        if normalized_call not in CALL_STATUSES:
            fields["call_status"] = "Choose a call status."
    elif normalized_call is not None:
        fields["call_status"] = "Call status applies only to a call."
    try:
        due_at = utc_due(due_date, due_time, QUEUE_ZONE)
    except FollowUpValidation as exc:
        fields.update(exc.fields)
        due_at = ""
    try:
        clean_summary = _summary(summary)
    except FollowUpValidation as exc:
        fields.update(exc.fields)
        clean_summary = ""
    if fields:
        raise FollowUpValidation("Request validation failed.", fields)
    return {
        "task_type": task_type,
        "due_at": due_at,
        "summary": clean_summary,
        "call_status": normalized_call,
    }


def _summary(value: str) -> str:
    if not isinstance(value, str):
        raise FollowUpValidation("Request validation failed.", {"summary": "Summary must be text."})
    text = value.strip()
    if len(text) > SUMMARY_MAX:
        raise FollowUpValidation("Request validation failed.", {"summary": "Summary is too long."})
    return text


def _outcome(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FollowUpValidation("Request validation failed.", {"outcome": "Outcome is required."})
    text = value.strip()
    if len(text) > OUTCOME_MAX:
        raise FollowUpValidation("Request validation failed.", {"outcome": "Outcome is too long."})
    return text


def _optional_outcome(value: str) -> str:
    if not isinstance(value, str):
        raise FollowUpValidation("Request validation failed.", {"outcome": "Outcome must be text."})
    text = value.strip()
    if len(text) > OUTCOME_MAX:
        raise FollowUpValidation("Request validation failed.", {"outcome": "Outcome is too long."})
    return text


def _calendar_date(value: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise FollowUpValidation("Request validation failed.", {"due_date": "Due date must be a real calendar day."}) from None


def _clock_time(value: str) -> None:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        raise FollowUpValidation("Request validation failed.", {"due_time": "Due time must use HH:MM."}) from None
    if parsed.strftime("%H:%M") != value:
        raise FollowUpValidation("Request validation failed.", {"due_time": "Due time must use HH:MM."})


def _zone(timezone_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        raise FollowUpValidation("Request validation failed.", {"timezone": "Timezone is not valid."}) from None


def _attach(local: datetime, zone: ZoneInfo) -> datetime:
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    utc_first = first.astimezone(UTC)
    utc_second = second.astimezone(UTC)
    back_first = utc_first.astimezone(zone).replace(tzinfo=None)
    back_second = utc_second.astimezone(zone).replace(tzinfo=None)
    if back_first != local and back_second != local:
        raise FollowUpValidation(
            "Request validation failed.",
            {"due_time": "That time does not exist in this timezone."},
        )
    if back_first == local and back_second == local and utc_first != utc_second:
        raise FollowUpValidation(
            "Request validation failed.",
            {"due_time": "That time is ambiguous in this timezone."},
        )
    if back_first == local:
        return utc_first
    return utc_second


def _live_record(connection: sqlite3.Connection, tenant_id: str, project_id: str, record_id: str) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT id FROM records
        WHERE tenant_id = ? AND project_id = ? AND id = ? AND deleted_at IS NULL
        """,
        (tenant_id, project_id, record_id),
    ).fetchone()


def _insert_follow_up(
    connection: sqlite3.Connection,
    *,
    follow_up_id: str,
    tenant_id: str,
    project_id: str,
    record_id: str,
    task_type: str,
    owner_user_id: str,
    due_at: str,
    call_status: str | None,
    summary: str,
    actor_id: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO follow_ups (
            id, tenant_id, project_id, record_id, task_type, owner_user_id, due_at, status,
            call_status, summary, outcome, created_by, updated_by, created_at, updated_at,
            completed_at, cancelled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, '', ?, ?, ?, ?, NULL, NULL)
        """,
        (
            follow_up_id,
            tenant_id,
            project_id,
            record_id,
            task_type,
            owner_user_id,
            due_at,
            call_status,
            summary,
            actor_id,
            actor_id,
            created_at,
            created_at,
        ),
    )


def _activity(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    follow_up_id: str,
    actor_id: str,
    event_type: str,
    summary: str,
    occurred_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO record_activities (
            id, tenant_id, project_id, record_id, follow_up_id, actor_id, event_type, summary, occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid4()), tenant_id, project_id, record_id, follow_up_id, actor_id, event_type, summary, occurred_at),
    )


def _created_summary(task_type: str, due_at: str) -> str:
    due_date, due_time = civil_due(due_at)
    return f"{TASK_LABELS[task_type]} follow-up created. Due {due_date} {due_time} India Standard Time."


def _rescheduled_summary(task_type: str, due_at: str) -> str:
    due_date, due_time = civil_due(due_at)
    return f"{TASK_LABELS[task_type]} follow-up was rescheduled to {due_date} {due_time} India Standard Time."


def _follow_up(row: sqlite3.Row) -> dict[str, object]:
    due_date, due_time = civil_due(row["due_at"])
    call_status = row["call_status"]
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "record_id": row["record_id"],
        "task_type": row["task_type"],
        "task_type_label": TASK_LABELS[row["task_type"]],
        "owner_user_id": row["owner_user_id"],
        "due_at": row["due_at"],
        "due_date": due_date,
        "due_time": due_time,
        "timezone": QUEUE_ZONE,
        "status": row["status"],
        "status_label": STATUS_LABELS[row["status"]],
        "call_status": call_status,
        "call_status_label": None if call_status is None else CALL_LABELS[call_status],
        "summary": row["summary"],
        "outcome": row["outcome"],
        "created_by": row["created_by"],
        "updated_by": row["updated_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "cancelled_at": row["cancelled_at"],
    }


def _queue_row(row: sqlite3.Row) -> dict[str, object]:
    body = _follow_up(row)
    body["public_number"] = row["public_number"]
    body["display_name"] = row["display_name"]
    body["record_assignee_user_id"] = row["assignee_user_id"]
    return body


def _activity_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "record_id": row["record_id"],
        "follow_up_id": row["follow_up_id"],
        "actor_id": row["actor_id"],
        "event_type": row["event_type"],
        "label": EVENT_LABELS.get(row["event_type"], "Activity"),
        "summary": row["summary"],
        "occurred_at": row["occurred_at"],
    }


def _count(connection: sqlite3.Connection, sql: str, params: list[object]) -> int:
    row = connection.execute(sql, params).fetchone()
    if row is None:
        return 0
    return int(row["count"])
