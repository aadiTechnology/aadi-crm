"""Leads list the project records the caller can already open."""

from app.db import connect
from tests.test_followups import _add, _body
from tests.test_projects import (
    LEADS,
    MANAGE,
    OTHER_ID,
    OUTSIDE_ID,
    RECORDS_ACCESS,
    TENANT_A,
    TENANT_B,
    USER_ID,
    FakePlatform,
    _access,
    _allow,
    _become,
    _client,
    _headers,
    _person,
)
from tests.test_records import _create, _ready

OTHER_MEMBERSHIP = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
REPLACEMENT_MEMBERSHIP = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"


def _platform() -> FakePlatform:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
        _person(OUTSIDE_ID, "outside@example.com"),
    ]
    return platform


def _leads(client, tenant_id=TENANT_A):
    return client.get(f"/api/v1/shell/tenants/{tenant_id}/leads", headers=_headers(write=False))


def test_leads_list_visible_records_with_status_and_follow_up(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "North school", "priority": "hot"})
    assert created.status_code == 201
    record_id = created.json()["id"]
    follow_up = _add(
        client,
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}",
    )
    listed = _leads(client)
    assert listed.status_code == 200
    body = listed.json()
    assert body["module"] == "leads"
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == record_id
    assert item["project_id"] == project_id
    assert item["display_name"] == "North school"
    assert item["public_number"] == "N-1-0001"
    assert item["status_label"] == "Priority"
    assert item["status_value"] == "Hot"
    assert item["assignee_user_id"] == USER_ID
    assert item["assignee_email"] == "manager@example.com"
    assert item["next_follow_up_at"] == follow_up["due_at"]
    assert item["source_label"] == "Manual"

    archived = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}/archive",
        headers=_headers(write=True),
        json={"expected_updated_at": created.json()["updated_at"]},
    )
    assert archived.status_code == 200
    after = _leads(client)
    assert after.json()["items"] == []
    assert "North school" not in after.text


def test_leads_hide_records_outside_assignment_follow_up_ownership_and_tenant(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    mine = _create(client, project_id, form_id, {"school_name": "Assigned school", "priority": "hot"})
    hidden = _create(client, project_id, form_id, {"school_name": "Manager school", "priority": "warm"})
    assert mine.status_code == 201
    assert hidden.status_code == 201
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    record_id = mine.json()["id"]
    _add(
        client,
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}",
        owner_user_id=OTHER_ID,
    )
    connection = connect(tmp_path / "projects.sqlite")
    connection.execute(
        "UPDATE records SET assignee_user_id = ? WHERE id = ?",
        (OTHER_ID, record_id),
    )
    connection.commit()
    connection.close()

    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    listed = _leads(client)
    assert listed.status_code == 200
    names = [item["display_name"] for item in listed.json()["items"]]
    assert names == ["Assigned school"]
    assert "Manager school" not in listed.text

    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=REPLACEMENT_MEMBERSHIP)
    revoked = _leads(client)
    assert revoked.json()["items"] == []
    assert "Assigned school" not in revoked.text

    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A)
    foreign = _leads(client, TENANT_B)
    assert foreign.status_code == 200
    assert foreign.json()["items"] == []
    assert "Assigned school" not in foreign.text
    assert "Manager school" not in foreign.text


def test_lead_permission_without_records_access_stays_empty(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "Hidden school", "priority": "hot"})
    assert created.status_code == 201
    _allow(platform, TENANT_A, [LEADS])
    denied_feature = _access(TENANT_A, features=("lead_management", "project_management"))
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS, RECORDS_ACCESS]
    platform.access_by_tenant[str(TENANT_A)] = denied_feature
    missing_feature = _leads(client)
    assert missing_feature.status_code == 200
    assert missing_feature.json() == {"module": "leads", "items": []}
    assert "Hidden school" not in missing_feature.text

    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS]
    missing_permission = _leads(client)
    assert missing_permission.status_code == 200
    assert missing_permission.json() == {"module": "leads", "items": []}
    assert "Hidden school" not in missing_permission.text


def test_tenant_manager_sees_records_without_a_project_membership(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "North school", "priority": "cold"})
    assert created.status_code == 201
    _become(platform, OUTSIDE_ID, "outside@example.com")
    _allow(platform, TENANT_A, [LEADS, RECORDS_ACCESS, MANAGE])
    listed = _leads(client)
    assert listed.status_code == 200
    assert [item["display_name"] for item in listed.json()["items"]] == ["North school"]
    assert listed.json()["items"][0]["status_value"] == "Cold"


def test_manager_can_assign_a_record_and_other_callers_cannot(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "Assigned school", "priority": "hot"})
    assert created.status_code == 201
    record_id = created.json()["id"]
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    assigned = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}/assign",
        headers=_headers(write=True),
        json={"assignee_user_id": OTHER_ID, "expected_updated_at": created.json()["updated_at"]},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assignee_user_id"] == OTHER_ID
    assert assigned.json()["values"]["school_name"] == "Assigned school"

    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    refused = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}/assign",
        headers=_headers(write=True),
        json={"assignee_user_id": USER_ID, "expected_updated_at": assigned.json()["updated_at"]},
    )
    assert refused.status_code == 403
    visible = _leads(client)
    assert [item["display_name"] for item in visible.json()["items"]] == ["Assigned school"]

    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A)
    stale_clock = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}/assign",
        headers=_headers(write=True),
        json={"assignee_user_id": USER_ID, "expected_updated_at": created.json()["updated_at"]},
    )
    assert stale_clock.status_code == 409
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com", membership_id=REPLACEMENT_MEMBERSHIP),
    ]
    second = _create(client, project_id, form_id, {"school_name": "Manager school", "priority": "warm"})
    assert second.status_code == 201
    stale_member = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{second.json()['id']}/assign",
        headers=_headers(write=True),
        json={"assignee_user_id": OTHER_ID, "expected_updated_at": second.json()["updated_at"]},
    )
    assert stale_member.status_code == 422
    assert "Choose an active project member." in stale_member.text
    kept = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{second.json()['id']}",
        headers=_headers(write=False),
    )
    assert kept.json()["assignee_user_id"] == USER_ID

    stale_owner = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{second.json()['id']}/follow-ups",
        headers=_headers(write=True),
        json=_body(owner_user_id=OTHER_ID),
    )
    assert stale_owner.status_code == 422
    assert "active member" in stale_owner.json()["error"]["fields"]["owner_user_id"]
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    hidden = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{second.json()['id']}/assign",
        headers=_headers(write=True),
        json={"assignee_user_id": OTHER_ID, "expected_updated_at": second.json()["updated_at"]},
    )
    assert hidden.status_code == 404
    assert "Manager school" not in hidden.text

