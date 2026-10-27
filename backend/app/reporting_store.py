"""Project KPIs and follow-up workload.

Record counts use the record-list filters. Follow-up counts use the queue
filters. Asia/Kolkata is the follow-up zone because no tenant or project
timezone is stored. Record creation dates stay on the UTC calendar day
already used by the record list.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime

from app import followups_store
from app.db import follow_up_due_date_expr

_RECORD_FROM = """
    FROM records
    JOIN form_versions
      ON form_versions.id = records.form_version_id
     AND form_versions.tenant_id = records.tenant_id
     AND form_versions.project_id = records.project_id
"""
_FOLLOW_FROM = """
    FROM follow_ups
    JOIN records
      ON records.id = follow_ups.record_id
     AND records.tenant_id = follow_ups.tenant_id
     AND records.project_id = follow_ups.project_id
"""
# Asia/Kolkata is UTC+05:30 and does not observe daylight saving.
# The SQL expression is chosen per connection in _by_due_date.


def project_kpis(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    *,
    assignee_user_id: str | None,
    created_from: str,
    created_to: str,
    now: datetime | None = None,
) -> dict[str, object]:
    start, end = followups_store.queue_window(now or followups_store.clock(), followups_store.QUEUE_ZONE)
    active = _count_records(connection, tenant_id, project_id, assignee_user_id, "", "")
    period_applied = bool(created_from or created_to)
    created = (
        _count_records(connection, tenant_id, project_id, assignee_user_id, created_from, created_to)
        if period_applied
        else None
    )
    overdue, today, upcoming = _queue_totals(
        connection,
        tenant_id,
        project_id,
        assignee_user_id,
        start,
        end,
    )
    return {
        "follow_up_timezone": followups_store.QUEUE_ZONE,
        "record_date_boundary": "utc_calendar_day",
        "window_start": start,
        "window_end": end,
        "record_period": {
            "created_from": created_from,
            "created_to": created_to,
            "applied": period_applied,
        },
        "active_records": active,
        "records_created": created,
        "records_by_form": _records_by_form(connection, tenant_id, project_id, assignee_user_id),
        "follow_ups": {
            "overdue": overdue,
            "today": today,
            "upcoming": upcoming,
            "completed": _count_completed(connection, tenant_id, project_id, assignee_user_id),
            "by_owner": _by_owner(connection, tenant_id, project_id, assignee_user_id, start, end),
            "by_due_date": _by_due_date(connection, tenant_id, project_id, assignee_user_id, start, end),
        },
        "omitted": ["record_status", "trends", "targets"],
    }


def list_completed_follow_ups(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    *,
    assignee_user_id: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    clauses, params = _follow_scope(tenant_id, project_id, assignee_user_id, status="completed")
    where = " AND ".join(clauses)
    total = _scalar(connection, f"SELECT COUNT(*) AS count {_FOLLOW_FROM} WHERE {where}", params)
    rows = connection.execute(
        f"""
        SELECT follow_ups.id, follow_ups.record_id, follow_ups.task_type, follow_ups.owner_user_id,
               follow_ups.completed_at, follow_ups.due_at, records.public_number, records.display_name,
               records.assignee_user_id
        {_FOLLOW_FROM}
        WHERE {where}
        ORDER BY follow_ups.completed_at DESC, follow_ups.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    return [_completed_row(row) for row in rows], total


def _count_records(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
    created_from: str,
    created_to: str,
) -> int:
    clauses, params = _record_scope(tenant_id, project_id, assignee_user_id, created_from, created_to)
    where = " AND ".join(clauses)
    return _scalar(connection, f"SELECT COUNT(*) AS count {_RECORD_FROM} WHERE {where}", params)


def _records_by_form(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
) -> list[dict[str, object]]:
    clauses, params = _record_scope(tenant_id, project_id, assignee_user_id, "", "")
    where = " AND ".join(clauses)
    rows = connection.execute(
        f"""
        SELECT records.form_id AS form_id, form_definitions.name AS form_name, COUNT(*) AS count
        {_RECORD_FROM}
        JOIN form_definitions
          ON form_definitions.id = records.form_id
         AND form_definitions.tenant_id = records.tenant_id
         AND form_definitions.project_id = records.project_id
        WHERE {where}
        GROUP BY records.form_id, form_definitions.name
        ORDER BY form_definitions.name, records.form_id
        """,
        params,
    ).fetchall()
    return [
        {"form_id": row["form_id"], "form_name": row["form_name"], "count": int(row["count"])}
        for row in rows
    ]


def _queue_totals(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
    start: str,
    end: str,
) -> tuple[int, int, int]:
    clauses, params = _follow_scope(tenant_id, project_id, assignee_user_id, status="open")
    where = " AND ".join(clauses)
    row = connection.execute(
        f"""
        SELECT
          COALESCE(SUM(CASE WHEN follow_ups.due_at < ? THEN 1 ELSE 0 END), 0) AS overdue,
          COALESCE(SUM(CASE WHEN follow_ups.due_at >= ? AND follow_ups.due_at < ? THEN 1 ELSE 0 END), 0) AS today,
          COALESCE(SUM(CASE WHEN follow_ups.due_at >= ? THEN 1 ELSE 0 END), 0) AS upcoming
        {_FOLLOW_FROM}
        WHERE {where}
        """,
        [start, start, end, end, *params],
    ).fetchone()
    return int(row["overdue"]), int(row["today"]), int(row["upcoming"])


def _by_owner(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
    start: str,
    end: str,
) -> list[dict[str, object]]:
    clauses, params = _follow_scope(tenant_id, project_id, assignee_user_id, status="open")
    where = " AND ".join(clauses)
    rows = connection.execute(
        f"""
        SELECT follow_ups.owner_user_id AS owner_user_id,
          COALESCE(SUM(CASE WHEN follow_ups.due_at < ? THEN 1 ELSE 0 END), 0) AS overdue,
          COALESCE(SUM(CASE WHEN follow_ups.due_at >= ? AND follow_ups.due_at < ? THEN 1 ELSE 0 END), 0) AS today,
          COALESCE(SUM(CASE WHEN follow_ups.due_at >= ? THEN 1 ELSE 0 END), 0) AS upcoming
        {_FOLLOW_FROM}
        WHERE {where}
        GROUP BY follow_ups.owner_user_id
        ORDER BY follow_ups.owner_user_id
        """,
        [start, start, end, end, *params],
    ).fetchall()
    return [
        {
            "owner_user_id": row["owner_user_id"],
            "overdue": int(row["overdue"]),
            "today": int(row["today"]),
            "upcoming": int(row["upcoming"]),
        }
        for row in rows
    ]


def _by_due_date(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
    start: str,
    end: str,
) -> list[dict[str, object]]:
    clauses, params = _follow_scope(tenant_id, project_id, assignee_user_id, status="open")
    where = " AND ".join(clauses)
    rows = connection.execute(
        f"""
        SELECT
          CASE
            WHEN follow_ups.due_at < ? THEN 'overdue'
            WHEN follow_ups.due_at < ? THEN 'today'
            ELSE 'upcoming'
          END AS queue,
          {follow_up_due_date_expr(connection)} AS due_date,
          COUNT(*) AS count
        {_FOLLOW_FROM}
        WHERE {where}
        GROUP BY 1, 2
        ORDER BY due_date, queue
        """,
        [start, end, *params],
    ).fetchall()
    return [
        {"queue": row["queue"], "due_date": _civil_day(row["due_date"]), "count": int(row["count"])}
        for row in rows
    ]


def _count_completed(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
) -> int:
    clauses, params = _follow_scope(tenant_id, project_id, assignee_user_id, status="completed")
    where = " AND ".join(clauses)
    return _scalar(connection, f"SELECT COUNT(*) AS count {_FOLLOW_FROM} WHERE {where}", params)


def _record_scope(
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
    created_from: str,
    created_to: str,
) -> tuple[list[str], list[object]]:
    clauses = ["records.tenant_id = ?", "records.project_id = ?", "records.deleted_at IS NULL"]
    params: list[object] = [tenant_id, project_id]
    if assignee_user_id is not None:
        clauses.append("records.assignee_user_id = ?")
        params.append(assignee_user_id)
    if created_from:
        clauses.append("substr(records.created_at, 1, 10) >= ?")
        params.append(created_from)
    if created_to:
        clauses.append("substr(records.created_at, 1, 10) <= ?")
        params.append(created_to)
    return clauses, params


def _follow_scope(
    tenant_id: str,
    project_id: str,
    assignee_user_id: str | None,
    *,
    status: str,
) -> tuple[list[str], list[object]]:
    clauses = [
        "follow_ups.tenant_id = ?",
        "follow_ups.project_id = ?",
        "follow_ups.status = ?",
        "records.deleted_at IS NULL",
    ]
    params: list[object] = [tenant_id, project_id, status]
    if assignee_user_id is not None:
        clauses.append("follow_ups.owner_user_id = ?")
        params.append(assignee_user_id)
    return clauses, params


def _completed_row(row: sqlite3.Row) -> dict[str, object]:
    due_date, due_time = followups_store.civil_due(row["due_at"])
    return {
        "id": row["id"],
        "record_id": row["record_id"],
        "public_number": row["public_number"],
        "display_name": row["display_name"],
        "task_type": row["task_type"],
        "task_type_label": followups_store.TASK_LABELS[row["task_type"]],
        "owner_user_id": row["owner_user_id"],
        "completed_at": row["completed_at"],
        "due_date": due_date,
        "due_time": due_time,
        "record_assignee_user_id": row["assignee_user_id"],
    }


def _civil_day(value: object) -> str:
    """Return YYYY-MM-DD. PostgreSQL can hand back a date; SQLite hands back text."""

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _scalar(connection: sqlite3.Connection, sql: str, params: list[object]) -> int:
    row = connection.execute(sql, params).fetchone()
    if row is None:
        return 0
    return int(row["count"])
