"""CRM reminder rows for follow-up owners.

The Control Plane has no notification send API. Email in the default test mode
is recorded and is not delivered. Live mode has no provider, so those rows fail
as not configured. This module does not send from a browser and does not log
addresses or message bodies.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.followups_store import civil_due

STAMP = "%Y-%m-%dT%H:%M:%S.%f+00:00"
MAX_ATTEMPTS = 3
CHANNELS = ("in_app", "email")
KIND_ASSIGNED = "follow_up_assigned"
KIND_DUE = "follow_up_due"
OPEN_STATES = ("pending", "retryable")
_LIVE_BACKOFF = (60, 300, 900)


def clock() -> datetime:
    return datetime.now(UTC)


def email_mode() -> str:
    configured = os.environ.get("CRM_REMINDER_EMAIL_MODE", "test").strip().lower()
    if configured == "live":
        return "live"
    return "test"


def backoff_seconds(attempt: int, mode: str) -> int:
    """Live mode waits. Test mode is eligible on the next run, not twice in one run."""

    if mode != "live":
        return 0
    index = min(max(attempt, 1), len(_LIVE_BACKOFF)) - 1
    return _LIVE_BACKOFF[index]


@dataclass(frozen=True)
class EmailMessage:
    recipient_user_id: str
    recipient_email: str
    subject: str
    body: str


class TestEmailAdapter:
    """Records an intent. It never reports provider delivery."""

    def __init__(self, outcome: str = "recorded") -> None:
        self.outcome = outcome

    def deliver(self, message: EmailMessage) -> str:
        del message
        if self.outcome == "retryable":
            return "retryable"
        if self.outcome == "terminal":
            return "terminal"
        return "recorded"


class UnconfiguredEmailAdapter:
    """Used when live mode is selected and MT-S6 is still absent."""

    def deliver(self, message: EmailMessage) -> str:
        del message
        return "unconfigured"


def build_adapter(mode: str, test_outcome: str | None):
    if mode == "live":
        return UnconfiguredEmailAdapter()
    if test_outcome in {"recorded", "retryable", "terminal"}:
        return TestEmailAdapter(test_outcome)
    return TestEmailAdapter("recorded")


def sync_follow_up_reminders(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    follow_up: dict[str, object],
    recipient_email: str | None,
) -> int:
    """Insert the current logical reminders and suppress rows that no longer apply."""

    now = _stamp(clock())
    follow_up_id = str(follow_up["id"])
    status = str(follow_up["status"])
    if status != "open":
        suppressed = _suppress_follow_up(connection, tenant_id, follow_up_id, "suppressed_follow_up_closed", now)
        connection.commit()
        return suppressed
    owner = str(follow_up["owner_user_id"])
    due_at = str(follow_up["due_at"])
    keys: list[str] = []
    for channel in CHANNELS:
        for kind, eligible_at in ((KIND_ASSIGNED, now), (KIND_DUE, due_at)):
            key = idempotency_key(tenant_id, follow_up_id, owner, kind, channel, due_at)
            keys.append(key)
            _insert(
                connection,
                tenant_id=tenant_id,
                project_id=str(follow_up["project_id"]),
                record_id=str(follow_up["record_id"]),
                follow_up_id=follow_up_id,
                recipient_user_id=owner,
                recipient_email=recipient_email if channel == "email" else None,
                channel=channel,
                kind=kind,
                due_at=due_at,
                eligible_at=eligible_at,
                idempotency_key=key,
                now=now,
            )
    if recipient_email:
        _fill_missing_email(connection, tenant_id, follow_up_id, owner, recipient_email, now)
    suppressed = _suppress_except(connection, tenant_id, follow_up_id, owner, due_at, keys, now)
    connection.commit()
    return suppressed


def process_reminders(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    actor_user_id: str,
    mode: str,
    adapter,
    emails: dict[str, str] | None = None,
    limit: int = 100,
) -> dict[str, int]:
    """Attempt each eligible row at most once during this call."""

    projects = managed_project_ids(connection, tenant_id, actor_user_id)
    known_emails = emails or {}
    suppressed = 0
    if projects:
        suppressed += _refresh_projects(connection, tenant_id, projects, known_emails)
        scope_sql, scope_params = _in_clause("project_id", projects)
    else:
        scope_sql, scope_params = "recipient_user_id = ?", [actor_user_id]
    stats = {
        "claimed": 0,
        "in_app_sent": 0,
        "email_recorded": 0,
        "email_sent": 0,
        "retryable": 0,
        "failed": 0,
        "suppressed": suppressed,
    }
    seen: list[str] = []
    now = _stamp(clock())
    while stats["claimed"] < limit:
        claimed = _claim(connection, tenant_id, now, scope_sql, scope_params, seen)
        if claimed is None:
            break
        seen.append(str(claimed["id"]))
        stats["claimed"] += 1
        state, error, retry_at = _deliver_one(claimed, mode, adapter, now)
        _finish(connection, str(claimed["id"]), state, error, retry_at, _stamp(clock()))
        if state == "sent" and claimed["channel"] == "in_app":
            stats["in_app_sent"] += 1
        elif state == "sent":
            stats["email_sent"] += 1
        elif state == "recorded":
            stats["email_recorded"] += 1
        elif state == "retryable":
            stats["retryable"] += 1
        elif state == "failed":
            stats["failed"] += 1
    return stats


def list_inbox(connection: sqlite3.Connection, tenant_id: str, user_id: str) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT * FROM reminder_deliveries
            WHERE tenant_id = ? AND recipient_user_id = ?
              AND (
                (channel = 'in_app' AND state = 'sent')
                OR (channel = 'email' AND state IN ('recorded', 'sent', 'retryable', 'failed'))
              )
            ORDER BY updated_at DESC, id DESC
            """,
            (tenant_id, user_id),
        )
    )


def list_failures(connection: sqlite3.Connection, tenant_id: str, project_ids: list[str]) -> list[sqlite3.Row]:
    if not project_ids:
        return []
    marks, params = _in_clause("project_id", project_ids)
    return list(
        connection.execute(
            f"""
            SELECT * FROM reminder_deliveries
            WHERE tenant_id = ? AND channel = 'email' AND state IN ('retryable', 'failed')
              AND {marks}
            ORDER BY updated_at DESC, id DESC
            """,
            [tenant_id, *params],
        )
    )


def mark_read(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    user_id: str,
    reminder_id: str,
) -> sqlite3.Row | None:
    now = _stamp(clock())
    connection.execute(
        """
        UPDATE reminder_deliveries
        SET read_at = COALESCE(read_at, ?), updated_at = ?
        WHERE id = ? AND tenant_id = ? AND recipient_user_id = ? AND channel = 'in_app' AND state = 'sent'
        """,
        (now, now, reminder_id, tenant_id, user_id),
    )
    connection.commit()
    return connection.execute(
        """
        SELECT * FROM reminder_deliveries
        WHERE id = ? AND tenant_id = ? AND recipient_user_id = ? AND channel = 'in_app' AND state = 'sent'
        """,
        (reminder_id, tenant_id, user_id),
    ).fetchone()


def retry_delivery(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_ids: list[str],
    reminder_id: str,
) -> sqlite3.Row | None:
    if not project_ids:
        return None
    marks, params = _in_clause("project_id", project_ids)
    now = _stamp(clock())
    connection.execute(
        f"""
        UPDATE reminder_deliveries
        SET state = 'pending', attempt_count = 0, next_retry_at = NULL, last_error = NULL, updated_at = ?
        WHERE id = ? AND tenant_id = ? AND channel = 'email' AND state IN ('retryable', 'failed')
          AND {marks}
        """,
        [now, reminder_id, tenant_id, *params],
    )
    connection.commit()
    return connection.execute(
        f"""
        SELECT * FROM reminder_deliveries
        WHERE id = ? AND tenant_id = ? AND {marks}
        """,
        [reminder_id, tenant_id, *params],
    ).fetchone()


def managed_project_ids(connection: sqlite3.Connection, tenant_id: str, user_id: str) -> list[str]:
    rows = connection.execute(
        """
        SELECT project_id FROM project_memberships
        WHERE tenant_id = ? AND user_id = ? AND role = 'project_manager' AND status = 'active'
        ORDER BY project_id
        """,
        (tenant_id, user_id),
    )
    return [str(row["project_id"]) for row in rows]


def idempotency_key(
    tenant_id: str,
    follow_up_id: str,
    recipient_user_id: str,
    kind: str,
    channel: str,
    due_at: str,
) -> str:
    marker = due_at if kind == KIND_DUE else "-"
    return f"{tenant_id}|{follow_up_id}|{recipient_user_id}|{kind}|{channel}|{marker}"


def open_owner_ids(connection: sqlite3.Connection, tenant_id: str, project_ids: list[str]) -> list[str]:
    if not project_ids:
        return []
    marks, params = _in_clause("project_id", project_ids)
    rows = connection.execute(
        f"""
        SELECT DISTINCT owner_user_id FROM follow_ups
        WHERE tenant_id = ? AND status = 'open' AND {marks}
        """,
        [tenant_id, *params],
    )
    return [str(row["owner_user_id"]) for row in rows]


def _refresh_projects(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_ids: list[str],
    emails: dict[str, str],
) -> int:
    marks, params = _in_clause("project_id", project_ids)
    suppressed = 0
    open_rows = connection.execute(
        f"""
        SELECT id, project_id, record_id, owner_user_id, due_at, status
        FROM follow_ups
        WHERE tenant_id = ? AND status = 'open' AND {marks}
        """,
        [tenant_id, *params],
    ).fetchall()
    for row in open_rows:
        known = emails.get(str(row["owner_user_id"]))
        if not known:
            email_row = connection.execute(
                """
                SELECT recipient_email FROM reminder_deliveries
                WHERE tenant_id = ? AND follow_up_id = ? AND recipient_user_id = ? AND channel = 'email'
                  AND recipient_email IS NOT NULL
                LIMIT 1
                """,
                (tenant_id, row["id"], row["owner_user_id"]),
            ).fetchone()
            known = None if email_row is None else email_row["recipient_email"]
        suppressed += sync_follow_up_reminders(
            connection,
            tenant_id=tenant_id,
            follow_up={
                "id": row["id"],
                "project_id": row["project_id"],
                "record_id": row["record_id"],
                "owner_user_id": row["owner_user_id"],
                "due_at": row["due_at"],
                "status": row["status"],
            },
            recipient_email=known,
        )
    closed = connection.execute(
        f"""
        SELECT id, project_id, record_id, owner_user_id, due_at, status
        FROM follow_ups
        WHERE tenant_id = ? AND status != 'open' AND {marks}
          AND id IN (
            SELECT follow_up_id FROM reminder_deliveries
            WHERE tenant_id = ? AND state IN ('pending', 'retryable')
          )
        """,
        [tenant_id, *params, tenant_id],
    ).fetchall()
    for row in closed:
        suppressed += sync_follow_up_reminders(
            connection,
            tenant_id=tenant_id,
            follow_up={
                "id": row["id"],
                "project_id": row["project_id"],
                "record_id": row["record_id"],
                "owner_user_id": row["owner_user_id"],
                "due_at": row["due_at"],
                "status": row["status"],
            },
            recipient_email=None,
        )
    return suppressed


def _claim(connection, tenant_id, now, scope_sql, scope_params, seen: list[str]):
    exclude = ""
    exclude_params: list[str] = []
    if seen:
        exclude = f" AND id NOT IN ({', '.join('?' for _ in seen)})"
        exclude_params = list(seen)
    locking = ""
    if not isinstance(connection, sqlite3.Connection):
        locking = "FOR UPDATE SKIP LOCKED\n            "
    row = connection.execute(
        f"""
        UPDATE reminder_deliveries
        SET state = 'processing', attempt_count = attempt_count + 1, last_attempt_at = ?, updated_at = ?
        WHERE id = (
            SELECT id FROM reminder_deliveries
            WHERE tenant_id = ?
              AND state IN ('pending', 'retryable')
              AND eligible_at <= ?
              AND (next_retry_at IS NULL OR next_retry_at <= ?)
              AND {scope_sql}
              {exclude}
            ORDER BY eligible_at, id
            {locking}LIMIT 1
        )
        RETURNING *
        """,
        [now, now, tenant_id, now, now, *scope_params, *exclude_params],
    ).fetchone()
    connection.commit()
    return row


def _deliver_one(row, mode: str, adapter, now: str) -> tuple[str, str | None, str | None]:
    if row["channel"] == "in_app":
        return "sent", None, None
    email = row["recipient_email"]
    if not isinstance(email, str) or "@" not in email:
        return "failed", "recipient_email_unavailable", None
    due_date, due_time = civil_due(str(row["due_at"]))
    label = "assigned follow-up" if row["kind"] == KIND_ASSIGNED else "due follow-up"
    message = EmailMessage(
        recipient_user_id=str(row["recipient_user_id"]),
        recipient_email=email,
        subject="CRM reminder",
        body=(
            f"You have a {label} due {due_date} {due_time} India Standard Time. "
            "Sign in to CRM to review it. This message does not include the customer record."
        ),
    )
    try:
        outcome = adapter.deliver(message)
    except Exception:
        outcome = "retryable"
    if outcome == "recorded" or (outcome == "sent" and mode != "live"):
        return "recorded", "test_adapter_recorded", None
    if outcome == "sent":
        return "sent", None, None
    if outcome == "unconfigured":
        return "failed", "provider_not_configured", None
    if outcome == "terminal":
        return "failed", "provider_rejected", None
    attempt = int(row["attempt_count"])
    if attempt >= MAX_ATTEMPTS:
        return "failed", "provider_temporary", None
    delay = backoff_seconds(attempt, mode)
    retry_at = now if delay == 0 else _stamp(clock() + timedelta(seconds=delay))
    return "retryable", "provider_temporary", retry_at


def _finish(connection, reminder_id: str, state: str, error: str | None, retry_at: str | None, now: str) -> None:
    connection.execute(
        """
        UPDATE reminder_deliveries
        SET state = ?, last_error = ?, next_retry_at = ?, updated_at = ?
        WHERE id = ? AND state = 'processing'
        """,
        (state, error, retry_at, now, reminder_id),
    )
    connection.commit()


def _insert(connection, **values) -> None:
    connection.execute(
        """
        INSERT INTO reminder_deliveries (
            id, tenant_id, project_id, record_id, follow_up_id, recipient_user_id, recipient_email,
            channel, kind, due_at, eligible_at, idempotency_key, state, attempt_count,
            last_attempt_at, last_error, next_retry_at, read_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, NULL, NULL, NULL, NULL, ?, ?)
        ON CONFLICT(idempotency_key) DO NOTHING
        """,
        (
            str(uuid4()),
            values["tenant_id"],
            values["project_id"],
            values["record_id"],
            values["follow_up_id"],
            values["recipient_user_id"],
            values["recipient_email"],
            values["channel"],
            values["kind"],
            values["due_at"],
            values["eligible_at"],
            values["idempotency_key"],
            values["now"],
            values["now"],
        ),
    )
    if values["kind"] == KIND_ASSIGNED:
        connection.execute(
            """
            UPDATE reminder_deliveries
            SET due_at = ?, updated_at = ?
            WHERE idempotency_key = ? AND state IN ('pending', 'retryable')
            """,
            (values["due_at"], values["now"], values["idempotency_key"]),
        )


def _fill_missing_email(connection, tenant_id, follow_up_id, owner, email, now) -> None:
    connection.execute(
        """
        UPDATE reminder_deliveries
        SET recipient_email = ?, updated_at = ?
        WHERE tenant_id = ? AND follow_up_id = ? AND recipient_user_id = ? AND channel = 'email'
          AND state IN ('pending', 'retryable') AND recipient_email IS NULL
        """,
        (email, now, tenant_id, follow_up_id, owner),
    )


def _suppress_follow_up(connection, tenant_id, follow_up_id, reason: str, now: str) -> int:
    cursor = connection.execute(
        """
        UPDATE reminder_deliveries
        SET state = 'suppressed', last_error = ?, next_retry_at = NULL, updated_at = ?
        WHERE tenant_id = ? AND follow_up_id = ? AND state IN ('pending', 'retryable')
        """,
        (reason, now, tenant_id, follow_up_id),
    )
    return int(cursor.rowcount)


def _suppress_except(connection, tenant_id, follow_up_id, owner, due_at, keys: list[str], now: str) -> int:
    rows = connection.execute(
        """
        SELECT id, idempotency_key, recipient_user_id, kind, due_at
        FROM reminder_deliveries
        WHERE tenant_id = ? AND follow_up_id = ? AND state IN ('pending', 'retryable')
        """,
        (tenant_id, follow_up_id),
    ).fetchall()
    count = 0
    for row in rows:
        if row["idempotency_key"] in keys:
            continue
        if row["recipient_user_id"] != owner:
            reason = "suppressed_owner_changed"
        elif row["kind"] == KIND_DUE and row["due_at"] != due_at:
            reason = "suppressed_due_changed"
        else:
            reason = "suppressed_not_current"
        cursor = connection.execute(
            """
            UPDATE reminder_deliveries
            SET state = 'suppressed', last_error = ?, next_retry_at = NULL, updated_at = ?
            WHERE id = ? AND state IN ('pending', 'retryable')
            """,
            (reason, now, row["id"]),
        )
        count += int(cursor.rowcount)
    return count


def _in_clause(column: str, values: list[str]) -> tuple[str, list[str]]:
    marks = ", ".join("?" for _ in values)
    return f"{column} IN ({marks})", list(values)


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime(STAMP)
