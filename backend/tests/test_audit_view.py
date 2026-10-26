"""The CRM audit view reads the platform log and does not store a copy."""

from tests.test_projects import (
    MODULE_KEYS,
    TENANT_A,
    TENANT_B,
    USER_ID,
    FakePlatform,
    _access,
    _allow,
    _client,
    _headers,
)

AUDIT = "audit.read"
from app.platform_client import PlatformCallError


_SECRET = "super-secret-audit-value"


def _event(event_id: str, *, summary: str = "Project settings were updated.") -> dict:
    return {
        "id": event_id,
        "occurred_at": "2026-10-21T04:00:00+00:00",
        "action": "project.settings.update",
        "resource_type": "project",
        "resource_id": "33333333-3333-4333-8333-333333333333",
        "summary": summary,
        "outcome": "success",
        "actor_user_id": USER_ID,
        "metadata": {"password": _SECRET, "note": "do not show"},
        "email": "person@example.com",
    }


def _permit_audit(platform: FakePlatform, tenant_id) -> None:
    _allow(platform, tenant_id, [*MODULE_KEYS, AUDIT])


def test_project_access_without_audit_read_does_not_open_the_log(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A, [MODULE_KEYS[1]])
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, features=("lead_management",))
    platform.audit_by_tenant[str(TENANT_A)] = [_event("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")]
    client = _client(tmp_path, monkeypatch, platform)
    denied = client.get(f"/api/v1/tenants/{TENANT_A}/audit-events", headers=_headers(write=False))
    assert denied.status_code == 403
    assert platform.audit_calls == []
    assert "Project settings" not in denied.text
    platform.permissions_by_tenant[str(TENANT_A)] = [AUDIT]
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, features=("lead_management",))
    opened = client.get(f"/api/v1/tenants/{TENANT_A}/audit-events", headers=_headers(write=False))
    assert opened.status_code == 200
    assert opened.json()["items"][0]["summary"] == "Project settings were updated."


def test_audit_view_strips_metadata_and_rejects_unsupported_filters(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _permit_audit(platform, TENANT_A)
    _permit_audit(platform, TENANT_B)
    platform.audit_by_tenant[str(TENANT_A)] = [
        _event("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"),
        _event("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2", summary="A second event."),
    ]
    platform.audit_by_tenant[str(TENANT_B)] = [_event("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1", summary="Other organization.")]
    client = _client(tmp_path, monkeypatch, platform)

    denied_filters = client.get(
        f"/api/v1/tenants/{TENANT_A}/audit-events?actor={USER_ID}&action=project.settings.update",
        headers=_headers(write=False),
    )
    assert denied_filters.status_code == 422
    assert platform.audit_calls == []
    offset = client.get(
        f"/api/v1/tenants/{TENANT_A}/audit-events?offset=5",
        headers=_headers(write=False),
    )
    assert offset.status_code == 422
    assert platform.audit_calls == []

    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/audit-events?limit=1",
        headers=_headers(write=False),
    )
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["source"] == "platform"
    assert body["limit"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert set(item) == {
        "id",
        "occurred_at",
        "action",
        "resource_type",
        "resource_id",
        "summary",
        "outcome",
        "actor_user_id",
    }
    assert _SECRET not in listed.text
    assert "metadata" not in item
    assert "person@example.com" not in listed.text
    assert "aadi_session" not in listed.text
    assert platform.audit_calls == [(str(TENANT_A), 1)]

    other = client.get(f"/api/v1/tenants/{TENANT_B}/audit-events", headers=_headers(write=False))
    assert other.status_code == 200
    assert other.json()["items"][0]["summary"] == "Other organization."
    assert "Project settings were updated." not in other.text


def test_audit_view_failure_empty_and_permission(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _permit_audit(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)

    empty = client.get(f"/api/v1/tenants/{TENANT_A}/audit-events", headers=_headers(write=False))
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["source"] == "platform"

    platform.audit_by_tenant[str(TENANT_A)] = PlatformCallError(403)
    forbidden = client.get(f"/api/v1/tenants/{TENANT_A}/audit-events", headers=_headers(write=False))
    assert forbidden.status_code == 403
    assert _SECRET not in forbidden.text

    platform.audit_by_tenant[str(TENANT_A)] = PlatformCallError(503)
    unavailable = client.get(f"/api/v1/tenants/{TENANT_A}/audit-events", headers=_headers(write=False))
    assert unavailable.status_code == 502
    assert unavailable.json()["error"]["message"] == "The audit log is unavailable."
    assert "Traceback" not in unavailable.text

    platform.audit_by_tenant[str(TENANT_A)] = [_event("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")]
    platform.audit_by_tenant[str(TENANT_A)][0].pop("id")
    malformed = client.get(f"/api/v1/tenants/{TENANT_A}/audit-events", headers=_headers(write=False))
    assert malformed.status_code == 502
    assert _SECRET not in malformed.text

    platform.identity_result = PlatformCallError(401)
    signed_out = client.get(f"/api/v1/tenants/{TENANT_A}/audit-events", headers=_headers(write=False))
    assert signed_out.status_code == 401
