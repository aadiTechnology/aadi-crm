"""Reminder delivery stays tenant scoped, idempotent, and honest about email."""

from datetime import UTC, datetime

from app.db import connect
from app.reminders_store import MAX_ATTEMPTS, backoff_seconds
from tests.test_followups import _add, _body, _platform
from tests.test_projects import OTHER_ID, TENANT_A, TENANT_B, USER_ID, _become, _headers
from tests.test_records import _create, _ready


def _freeze(monkeypatch) -> None:
    moment = datetime(2026, 10, 21, 5, 0, tzinfo=UTC)
    monkeypatch.setattr("app.reminders_store.clock", lambda: moment)


def _rows(tmp_path):
    connection = connect(tmp_path / "projects.sqlite")
    try:
        return list(connection.execute("SELECT * FROM reminder_deliveries ORDER BY idempotency_key"))
    finally:
        connection.close()


def _setup(tmp_path, monkeypatch):
    _freeze(monkeypatch)
    platform = _platform()
    from tests.test_projects import _client

    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    record = _create(client, project_id, form_id, {"school_name": "Hidden school"}).json()
    base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}"
    return platform, client, project_id, record, base


def _process(client, *, outcome: str | None = None):
    headers = _headers(write=True)
    if outcome:
        headers["x-crm-reminder-test-outcome"] = outcome
    response = client.post(f"/api/v1/tenants/{TENANT_A}/reminders/process", headers=headers)
    assert response.status_code == 200
    assert response.json()["email_provider_confirmed"] is False
    return response.json()


def test_provider_exception_text_is_not_stored(tmp_path, monkeypatch) -> None:
    class Boom:
        def deliver(self, message):
            raise RuntimeError("smtp password=secret-token")

    monkeypatch.setattr("app.api.reminders.build_adapter", lambda mode, outcome: Boom())
    _platform_client, client, _project_id, _record, base = _setup(tmp_path, monkeypatch)
    _add(client, base, summary="Do not leak", task_type="note", call_status=None)
    result = _process(client)
    assert result["retryable"] == 2
    stored = _rows(tmp_path)
    email_rows = [row for row in stored if row["channel"] == "email"]
    assert {row["last_error"] for row in email_rows} == {"provider_temporary"}
    blob = " ".join((row["last_error"] or "") + (row["recipient_email"] or "") for row in stored)
    assert "secret-token" not in blob
    assert "password" not in blob


def test_backoff_is_bounded_and_test_mode_does_not_wait() -> None:
    assert backoff_seconds(1, "live") == 60
    assert backoff_seconds(2, "live") == 300
    assert backoff_seconds(3, "live") == 900
    assert backoff_seconds(1, "test") == 0
    assert MAX_ATTEMPTS == 3


def test_delivery_is_idempotent_and_test_adapter_is_not_delivery(tmp_path, monkeypatch) -> None:
    captured: list[object] = []

    class Capture:
        def deliver(self, message):
            captured.append(message)
            return "recorded"

    monkeypatch.setattr("app.api.reminders.build_adapter", lambda mode, outcome: Capture())
    _platform_client, client, _project_id, record, base = _setup(tmp_path, monkeypatch)
    created = _add(client, base, summary="Hidden school visit", task_type="note", call_status=None)
    first = _rows(tmp_path)
    assert len(first) == 4
    assert {row["state"] for row in first} == {"pending"}
    edited = client.patch(
        f"{base}/follow-ups/{created['id']}",
        headers=_headers(write=True),
        json={"expected_updated_at": created["updated_at"], "summary": "Hidden school visit again"},
    )
    assert edited.status_code == 200
    assert len(_rows(tmp_path)) == 4
    poisoned = client.post(
        f"/api/v1/tenants/{TENANT_A}/reminders/process",
        headers=_headers(write=True),
        json={"recipient_email": "evil@example.com"},
    )
    assert poisoned.status_code == 200
    assert poisoned.json()["email_mode"] == "test"
    assert poisoned.json()["email_recorded"] == 2
    assert poisoned.json()["in_app_sent"] == 2
    again = _process(client)
    assert again["claimed"] == 0
    stored = _rows(tmp_path)
    assert len(stored) == 4
    assert {row["recipient_email"] for row in stored if row["channel"] == "email"} == {"manager@example.com"}
    assert all("evil@example.com" not in (row["recipient_email"] or "") for row in stored)
    assert captured
    for message in captured:
        assert message.subject == "CRM reminder"
        assert "Hidden school" not in message.body
        assert "visit" not in message.body
    inbox = client.get(f"/api/v1/tenants/{TENANT_A}/reminders", headers=_headers(write=False))
    assert inbox.status_code == 200
    body = inbox.json()
    assert body["total"] == 4
    assigned = next(item for item in body["items"] if item["kind"] == "follow_up_assigned" and item["channel"] == "in_app")
    assert assigned["record_available"] is True
    assert assigned["public_number"] == record["public_number"]
    assert assigned["read"] is False
    email_row = next(item for item in body["items"] if item["channel"] == "email")
    assert email_row["state"] == "recorded"
    assert "Not delivered" in email_row["state_label"]
    assert "Hidden school" not in inbox.text
    marked = client.post(
        f"/api/v1/tenants/{TENANT_A}/reminders/{assigned['id']}/read",
        headers=_headers(write=True),
    )
    assert marked.status_code == 200
    assert marked.json()["read"] is True
    connection = connect(tmp_path / "projects.sqlite")
    connection.execute(
        """
        UPDATE reminder_deliveries
        SET recipient_email = NULL, state = 'pending', attempt_count = 0, next_retry_at = NULL, last_error = NULL
        WHERE channel = 'email'
        """
    )
    connection.commit()
    connection.close()
    resolved = _process(client)
    assert resolved["email_recorded"] == 2
    stored = _rows(tmp_path)
    assert {row["recipient_email"] for row in stored if row["channel"] == "email"} == {"manager@example.com"}


def test_retry_limit_terminal_failure_and_manual_retry(tmp_path, monkeypatch) -> None:
    platform, client, project_id, _record, base = _setup(tmp_path, monkeypatch)
    _add(client, base, summary="Retry target", task_type="note", call_status=None)
    first = _process(client, outcome="retryable")
    assert first["retryable"] == 2
    assert first["failed"] == 0
    second = _process(client, outcome="retryable")
    assert second["retryable"] == 2
    third = _process(client, outcome="retryable")
    assert third["failed"] == 2
    assert third["email_recorded"] == 0
    fourth = _process(client, outcome="retryable")
    assert fourth["claimed"] == 0
    assert fourth["in_app_sent"] == 0
    failures = client.get(f"/api/v1/tenants/{TENANT_A}/reminders/failures", headers=_headers(write=False))
    assert failures.status_code == 200
    failed = failures.json()["items"]
    assert len(failed) == 2
    assert {item["last_error"] for item in failed} == {"provider_temporary"}
    assert {item["attempt_count"] for item in failed} == {3}
    assert "secret" not in failures.text
    reminder_id = failed[0]["id"]
    retried = client.post(
        f"/api/v1/tenants/{TENANT_A}/reminders/{reminder_id}/retry",
        headers=_headers(write=True),
    )
    assert retried.status_code == 200
    assert retried.json()["id"] == reminder_id
    assert retried.json()["state"] == "pending"
    delivered = _process(client)
    assert delivered["email_recorded"] == 1
    assert len(_rows(tmp_path)) == 4
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    denied = client.get(f"/api/v1/tenants/{TENANT_A}/reminders/failures", headers=_headers(write=False))
    assert denied.status_code == 403
    assert reminder_id not in denied.text
    blocked = client.post(
        f"/api/v1/tenants/{TENANT_A}/reminders/{reminder_id}/retry",
        headers=_headers(write=True),
    )
    assert blocked.status_code == 403


def test_closed_follow_ups_are_not_sent_and_live_mode_is_not_delivery(tmp_path, monkeypatch) -> None:
    _platform_client, client, _project_id, _record, base = _setup(tmp_path, monkeypatch)
    completed = _add(client, base, summary="Finished before delivery", task_type="note", call_status=None)
    finished = client.post(
        f"{base}/follow-ups/{completed['id']}/complete",
        headers=_headers(write=True),
        json={"expected_updated_at": completed["updated_at"], "outcome": "Spoke already"},
    )
    assert finished.status_code == 200
    cancelled = _add(client, base, summary="Cancelled before delivery", task_type="note", call_status=None)
    stopped = client.post(
        f"{base}/follow-ups/{cancelled['id']}/cancel",
        headers=_headers(write=True),
        json={"expected_updated_at": cancelled["updated_at"], "outcome": "No longer needed"},
    )
    assert stopped.status_code == 200
    result = _process(client)
    assert result["email_recorded"] == 0
    assert result["in_app_sent"] == 0
    assert {row["state"] for row in _rows(tmp_path)} == {"suppressed"}
    monkeypatch.setenv("CRM_REMINDER_EMAIL_MODE", "live")
    open_follow_up = _add(client, base, summary="Needs a provider", task_type="note", call_status=None)
    live = _process(client, outcome="recorded")
    assert live["email_mode"] == "live"
    assert live["email_provider_confirmed"] is False
    assert live["email_recorded"] == 0
    assert live["failed"] == 2
    inbox = client.get(f"/api/v1/tenants/{TENANT_A}/reminders", headers=_headers(write=False)).json()
    email_items = [item for item in inbox["items"] if item["channel"] == "email"]
    assert {item["last_error"] for item in email_items} == {"provider_not_configured"}
    assert open_follow_up["id"]
    missing = client.post(f"/api/v1/tenants/{TENANT_A}/reminders/process", headers={"cookie": "aadi_session=member"})
    assert missing.status_code == 401


def test_reminders_do_not_cross_tenants_or_bypass_record_access(tmp_path, monkeypatch) -> None:
    platform, client, project_id, record, base = _setup(tmp_path, monkeypatch)
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    owned = _add(
        client,
        base,
        summary="Only the owner should read this",
        task_type="note",
        call_status=None,
        owner_user_id=OTHER_ID,
    )
    _process(client)
    _become(platform, OTHER_ID, "member@example.com")
    inbox = client.get(f"/api/v1/tenants/{TENANT_A}/reminders", headers=_headers(write=False))
    assert inbox.status_code == 200
    items = inbox.json()["items"]
    assert items
    assert all(item["record_available"] is False for item in items)
    assert all("public_number" not in item for item in items)
    assert record["public_number"] not in inbox.text
    assert "Only the owner should read this" not in inbox.text
    assert "Hidden school" not in inbox.text
    _become(platform, USER_ID, "manager@example.com")
    manager_inbox = client.get(f"/api/v1/tenants/{TENANT_A}/reminders", headers=_headers(write=False))
    assert owned["id"] not in {item.get("follow_up_id") for item in manager_inbox.json()["items"]}
    _become(platform, OTHER_ID, "member@example.com")
    other_tenant = client.get(f"/api/v1/tenants/{TENANT_B}/reminders", headers=_headers(write=False))
    assert other_tenant.status_code == 200
    assert other_tenant.json()["items"] == []
    assert record["public_number"] not in other_tenant.text
    assert "Only the owner should read this" not in other_tenant.text
    denied_remove = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{added.json()['id']}/remove",
        headers=_headers(write=True),
    )
    assert denied_remove.status_code == 403
    _become(platform, USER_ID, "manager@example.com")
    removed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{added.json()['id']}/remove",
        headers=_headers(write=True),
    )
    assert removed.status_code == 200
    _become(platform, OTHER_ID, "member@example.com")
    after = client.get(f"/api/v1/tenants/{TENANT_A}/reminders", headers=_headers(write=False))
    assert after.status_code == 200
    assert after.json()["items"]
    assert all(item["record_available"] is False for item in after.json()["items"])
    assert record["public_number"] not in after.text
