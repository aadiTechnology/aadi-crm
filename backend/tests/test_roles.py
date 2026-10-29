"""Tenant role administration. Project Manager and Member stay project roles."""

from uuid import uuid4

from app.db import connect, database_path
from app.platform_client import PlatformCallError
from app.project_access import (
    ACTIONS,
    PROJECT_ACCESS_PERMISSION,
    PROJECT_MANAGE_PERMISSION,
    RECORDS_ACCESS_PERMISSION,
    SUPPORTED_CRM_PERMISSIONS,
    access_for,
    tenant_project_admin,
)
from tests.test_projects import (
    LEADS,
    MANAGE,
    MEMBERSHIP_ID,
    OTHER_ID,
    PROJECT_ACCESS,
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

ROLES_MANAGE = "roles.manage"
OTHER_MEMBERSHIP = "ffffffff-ffff-4fff-8fff-ffffffffffff"
REPLACEMENT_MEMBERSHIP = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
CATALOG = [
    "crm.lead_management.read",
    "crm.project_management.access",
    "crm.project_management.manage",
    "crm.records.access",
]


def _admin(platform: FakePlatform, tenant_id=TENANT_A, *, membership_id: str = MEMBERSHIP_ID) -> None:
    _allow(platform, tenant_id, [ROLES_MANAGE])
    platform.access_by_tenant[str(tenant_id)] = _access(tenant_id, membership_id=membership_id)


def _roles(tenant_id=TENANT_A) -> str:
    return f"/api/v1/tenants/{tenant_id}/roles"


def _create(client, name: str = "Desk leads", description: str = "Reads the desk queue") -> dict:
    created = client.post(
        _roles(),
        headers=_headers(write=True),
        json={"name": name, "description": description},
    )
    assert created.status_code == 201, created.text
    return created.json()


def _counts() -> tuple[int, int]:
    connection = connect(database_path())
    roles = connection.execute("SELECT COUNT(*) AS count FROM tenant_roles").fetchone()
    grants = connection.execute("SELECT COUNT(*) AS count FROM tenant_role_permissions").fetchone()
    connection.close()
    assert roles is not None and grants is not None
    return int(roles["count"]), int(grants["count"])


def test_tenant_admin_can_list_and_create_roles(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _admin(platform)
    client = _client(tmp_path, monkeypatch, platform)
    catalog = client.get(f"/api/v1/tenants/{TENANT_A}/crm-permissions", headers=_headers(write=False))
    assert catalog.status_code == 200
    assert catalog.json()["items"] == CATALOG
    assert list(SUPPORTED_CRM_PERMISSIONS) == [
        LEADS,
        PROJECT_ACCESS_PERMISSION,
        PROJECT_MANAGE_PERMISSION,
        RECORDS_ACCESS_PERMISSION,
    ]
    assert "roles.manage" not in catalog.text
    assert "users.update" not in catalog.text
    empty = client.get(_roles(), headers=_headers(write=False))
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    created = _create(client)
    assert created["name"] == "Desk leads"
    assert created["description"] == "Reads the desk queue"
    assert created["status"] == "active"
    assert created["tenant_id"] == str(TENANT_A)
    assert created["permissions"] == []
    assert "tenant_membership_id" not in created
    listed = client.get(_roles(), headers=_headers(write=False))
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
    duplicate = client.post(
        _roles(),
        headers=_headers(write=True),
        json={"name": "desk leads"},
    )
    assert duplicate.status_code == 409
    assert _counts() == (1, 0)
    invalid = client.post(_roles(), headers=_headers(write=True), json={"name": "  "})
    assert invalid.status_code == 422
    assert client.post(
        _roles(),
        headers=_headers(write=True),
        json={"name": "x" * 121},
    ).status_code == 422
    assert client.post(
        _roles(),
        headers=_headers(write=True),
        json={"name": "Other", "tenant_id": str(TENANT_B)},
    ).status_code == 422
    assert client.post(_roles(), headers=_headers(write=False), json={"name": "No token"}).status_code == 401
    assert _counts() == (1, 0)


def test_tenant_admin_can_update_and_deactivate_a_role(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _admin(platform)
    client = _client(tmp_path, monkeypatch, platform)
    created = _create(client, description="")
    role_id = created["id"]
    client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    updated = client.patch(
        f"{_roles()}/{role_id}",
        headers=_headers(write=True),
        json={"name": "Desk editors", "description": "Edited queue"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Desk editors"
    assert updated.json()["description"] == "Edited queue"
    assert updated.json()["permissions"] == [LEADS]
    conflict = client.post(
        _roles(),
        headers=_headers(write=True),
        json={"name": "Kept name"},
    )
    assert conflict.status_code == 201
    kept_id = conflict.json()["id"]
    rejected = client.patch(
        f"{_roles()}/{kept_id}",
        headers=_headers(write=True),
        json={"name": "DESK EDITORS"},
    )
    assert rejected.status_code == 409
    names = {
        item["id"]: item["name"]
        for item in client.get(_roles(), headers=_headers(write=False)).json()["items"]
    }
    assert names[kept_id] == "Kept name"
    assert names[role_id] == "Desk editors"
    deactivated = client.post(
        f"{_roles()}/{role_id}/deactivate",
        headers=_headers(write=True),
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["id"] == role_id
    assert deactivated.json()["status"] == "inactive"
    assert deactivated.json()["permissions"] == [LEADS]
    again = client.post(f"{_roles()}/{role_id}/deactivate", headers=_headers(write=True))
    assert again.status_code == 200
    assert again.json()["status"] == "inactive"
    connection = connect(database_path())
    stored = connection.execute(
        "SELECT status FROM tenant_roles WHERE id = ?",
        (role_id,),
    ).fetchone()
    grants = connection.execute(
        "SELECT permission_key FROM tenant_role_permissions WHERE tenant_id = ? AND role_id = ?",
        (str(TENANT_A), role_id),
    ).fetchall()
    connection.close()
    assert stored is not None
    assert stored["status"] == "inactive"
    assert [row["permission_key"] for row in grants] == [LEADS]
    blocked = client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": RECORDS_ACCESS_PERMISSION},
    )
    assert blocked.status_code == 409
    assert _counts() == (2, 1)
    visible = client.get(_roles(), headers=_headers(write=False))
    assert {item["id"] for item in visible.json()["items"]} == {role_id, kept_id}


def test_tenant_admin_can_assign_and_remove_supported_permissions(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _admin(platform)
    client = _client(tmp_path, monkeypatch, platform)
    role_id = _create(client)["id"]
    granted = client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": f"  {LEADS}  "},
    )
    assert granted.status_code == 200
    assert granted.json()["items"] == [LEADS]
    repeated = client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    assert repeated.status_code == 200
    assert repeated.json()["items"] == [LEADS]
    second = client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": PROJECT_ACCESS},
    )
    assert second.status_code == 200
    assert second.json()["items"] == [LEADS, PROJECT_ACCESS]
    listed = client.get(f"{_roles()}/{role_id}/permissions", headers=_headers(write=False))
    assert listed.status_code == 200
    assert listed.json()["items"] == [LEADS, PROJECT_ACCESS]
    assert _counts() == (1, 2)
    removed = client.post(
        f"{_roles()}/{role_id}/permissions/remove",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    assert removed.status_code == 200
    assert removed.json()["items"] == [PROJECT_ACCESS]
    missing = client.post(
        f"{_roles()}/{role_id}/permissions/remove",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    assert missing.status_code == 404
    assert client.get(_roles(), headers=_headers(write=False)).json()["items"][0]["status"] == "active"
    assert _counts() == (1, 1)


def test_unsupported_permission_identifiers_are_rejected(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _admin(platform)
    client = _client(tmp_path, monkeypatch, platform)
    role_id = _create(client)["id"]
    for key in (ROLES_MANAGE, "users.update", "platform.admin", "crm.lead_management", ""):
        rejected = client.post(
            f"{_roles()}/{role_id}/permissions",
            headers=_headers(write=True),
            json={"permission_key": key},
        )
        assert rejected.status_code == 422, key
        assert rejected.json()["error"]["message"] == "That permission is not a supported CRM permission."
        if key:
            assert key not in rejected.text
    scoped = client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": LEADS, "scope": "platform"},
    )
    assert scoped.status_code == 422
    assert _counts() == (1, 0)


def test_project_member_cannot_administer_tenant_roles(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A, [PROJECT_ACCESS])
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com", membership_id=MEMBERSHIP_ID),
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "North yard"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert created.json()["access"]["role"] == "project_manager"
    rejected_role = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "tenant_admin"},
    )
    assert rejected_role.status_code == 422
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS]
    opened = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert opened.status_code == 200
    assert opened.json()["access"]["can_manage_project"] is False
    assert opened.json()["access"]["role"] == "project_member"
    member_update = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Taken over"},
    )
    assert member_update.status_code == 403
    for method, path, body in (
        ("get", _roles(), None),
        ("get", f"/api/v1/tenants/{TENANT_A}/crm-permissions", None),
        ("post", _roles(), {"name": "Member role"}),
    ):
        response = client.request(method, path, headers=_headers(write=method == "post"), json=body)
        assert response.status_code == 403
        assert response.json()["error"]["message"] == "You do not have permission to perform this action."
        assert "North yard" not in response.text
    platform.permissions_by_tenant[str(TENANT_A)] = [MANAGE]
    manage_denied = client.post(
        _roles(),
        headers=_headers(write=True),
        json={"name": "Project admin role"},
    )
    assert manage_denied.status_code == 403
    assert _counts() == (0, 0)
    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS, ROLES_MANAGE]
    role_id = _create(client, name="Records desk")["id"]
    assigned = client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": MANAGE},
    )
    assert assigned.status_code == 200
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS]
    still_member = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Still denied"},
    )
    assert still_member.status_code == 403
    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS]
    renamed = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Manager kept it"},
    )
    assert renamed.status_code == 200
    second = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-2", "name": "Secret yard"},
    )
    assert second.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS]
    visible = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert visible.status_code == 200
    assert [item["id"] for item in visible.json()["items"]] == [project_id]
    assert "Secret yard" not in visible.text
    platform.permissions_by_tenant[str(TENANT_A)] = [ROLES_MANAGE]
    assert client.get(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=False),
    ).status_code == 403
    assert tenant_project_admin([ROLES_MANAGE]) is False
    assert tenant_project_admin([MANAGE]) is True
    manager = access_for(role="project_manager", status="active", permission_keys=[LEADS])
    member = access_for(role="project_member", status="active", permission_keys=[LEADS])
    assert manager.allows("assign_role") is True
    assert member.allows("assign_role") is False
    assert member.allows("update_project") is False
    assert ACTIONS["assign_role"] == frozenset({"project_manager"})
    assert ACTIONS["update_project"] == frozenset({"project_manager"})


def test_another_tenants_role_cannot_be_accessed_or_modified(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _admin(platform, TENANT_A)
    _admin(platform, TENANT_B, membership_id=OTHER_MEMBERSHIP)
    client = _client(tmp_path, monkeypatch, platform)
    created = _create(client, name="Tenant A desk")
    role_id = created["id"]
    client.post(
        f"{_roles(TENANT_A)}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    listed = client.get(_roles(TENANT_B), headers=_headers(write=False))
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert "Tenant A desk" not in listed.text
    stolen_name = client.patch(
        f"{_roles(TENANT_B)}/{role_id}",
        headers=_headers(write=True),
        json={"name": "Stolen"},
    )
    stolen_state = client.post(
        f"{_roles(TENANT_B)}/{role_id}/deactivate",
        headers=_headers(write=True),
    )
    stolen_read = client.get(
        f"{_roles(TENANT_B)}/{role_id}/permissions",
        headers=_headers(write=False),
    )
    for response in (stolen_name, stolen_state, stolen_read):
        assert response.status_code == 404
        assert "Tenant A desk" not in response.text
        assert LEADS not in response.text
    stolen_grant = client.post(
        f"{_roles(TENANT_B)}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": RECORDS_ACCESS_PERMISSION},
    )
    assert stolen_grant.status_code == 404
    same_name = client.post(
        _roles(TENANT_B),
        headers=_headers(write=True),
        json={"name": "Tenant A desk"},
    )
    assert same_name.status_code == 201
    assert same_name.json()["id"] != role_id
    kept = client.get(f"{_roles(TENANT_A)}/{role_id}/permissions", headers=_headers(write=False))
    assert kept.status_code == 200
    assert kept.json()["items"] == [LEADS]
    platform.access_by_tenant[str(TENANT_B)] = PlatformCallError(404)
    hidden = client.get(_roles(TENANT_B), headers=_headers(write=False))
    assert hidden.status_code == 404
    assert "Tenant A desk" not in hidden.text


def test_revoked_or_stale_membership_cannot_administer_roles(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _admin(platform)
    client = _client(tmp_path, monkeypatch, platform)
    created = _create(client)
    role_id = created["id"]
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id="")
    stale = client.post(
        _roles(),
        headers=_headers(write=True),
        json={"name": "Stale role"},
    )
    assert stale.status_code == 403
    assert stale.json()["error"]["message"] == "This sign-in is not an active member of the organization."
    assert created["name"] not in stale.text
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id="not-a-membership")
    invalid_binding = client.get(_roles(), headers=_headers(write=False))
    assert invalid_binding.status_code == 403
    platform.access_by_tenant[str(TENANT_A)] = PlatformCallError(404)
    revoked = client.patch(
        f"{_roles()}/{role_id}",
        headers=_headers(write=True),
        json={"name": "Revoked edit"},
    )
    assert revoked.status_code == 404
    assert created["name"] not in revoked.text
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=REPLACEMENT_MEMBERSHIP)
    replaced = client.patch(
        f"{_roles()}/{role_id}",
        headers=_headers(write=True),
        json={"description": "Current membership still administers the role"},
    )
    assert replaced.status_code == 200
    assert replaced.json()["description"] == "Current membership still administers the role"
    assert _counts() == (1, 0)
    platform.access_by_tenant[str(TENANT_A)] = _access(
        TENANT_A,
        available=False,
        features=(),
        membership_id=REPLACEMENT_MEMBERSHIP,
    )
    without_entitlement = client.get(
        f"/api/v1/tenants/{TENANT_A}/crm-permissions",
        headers=_headers(write=False),
    )
    assert without_entitlement.status_code == 200
    assert without_entitlement.json()["items"] == CATALOG


def test_role_permission_grant_does_not_change_project_authorization(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A, [PROJECT_ACCESS])
    client = _client(tmp_path, monkeypatch, platform)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "Bound yard"},
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    platform.permissions_by_tenant[str(TENANT_A)] = [ROLES_MANAGE]
    role_id = _create(client, name="Wide role")["id"]
    client.post(
        f"{_roles()}/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": MANAGE},
    )
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS]
    listed = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [project_id]
    stranger = str(uuid4())
    assert stranger != USER_ID
    _become(platform, stranger, "stranger@example.com")
    denied = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert denied.status_code == 404
    assert "Bound yard" not in denied.text
    assert "Wide role" not in denied.text
