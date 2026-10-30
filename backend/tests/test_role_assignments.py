"""CRM role assignments narrow module keys and leave project roles unchanged."""

from uuid import uuid4

from app.db import MIGRATIONS, apply_migrations, connect, database_path
from app.platform_client import PlatformCallError
from app.project_access import RECORDS_ACCESS_PERMISSION, effective_module_keys
from tests.test_projects import (
    LEADS,
    MANAGE,
    MEMBERSHIP_ID,
    OTHER_ID,
    PROJECT_ACCESS,
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
from tests.test_roles import ROLES_MANAGE

USERS_READ = "users.read"
OTHER_MEMBERSHIP = "ffffffff-ffff-4fff-8fff-ffffffffffff"
REPLACEMENT_MEMBERSHIP = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
OUTSIDE_USER = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def test_effective_module_keys_follow_the_approved_intersection() -> None:
    plane = [LEADS, PROJECT_ACCESS, RECORDS_ACCESS, MANAGE, ROLES_MANAGE, "audit.read"]
    assert effective_module_keys(plane, assigned=False, granted=frozenset()) == plane
    narrowed = effective_module_keys(
        plane,
        assigned=True,
        granted=frozenset({LEADS, "roles.manage", "made.up"}),
    )
    assert narrowed == [LEADS, ROLES_MANAGE, "audit.read"]
    denied = effective_module_keys(plane, assigned=True, granted=frozenset())
    assert denied == [ROLES_MANAGE, "audit.read"]
    assert MANAGE not in effective_module_keys(
        [PROJECT_ACCESS],
        assigned=True,
        granted=frozenset({MANAGE}),
    )


def test_assignment_migration_is_additive_on_a_blank_database(tmp_path) -> None:
    script = (MIGRATIONS / "010_tenant_role_assignments.sql").read_text(encoding="utf-8")
    folded = script.lower()
    assert "drop table" not in folded
    assert "delete from" not in folded
    path = tmp_path / "blank.sqlite"
    apply_migrations(path)
    apply_migrations(path)
    connection = connect(path)
    versions = {
        row["version"]
        for row in connection.execute("SELECT version FROM crm_schema_migrations")
    }
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(tenant_role_assignments)")
    }
    connection.close()
    assert "009_tenant_roles.sql" in versions
    assert "010_tenant_role_assignments.sql" in versions
    assert {"user_id", "role_id", "tenant_id", "tenant_membership_id", "status"} <= columns


def _grant_admin(platform: FakePlatform, tenant_id=TENANT_A, *, membership_id: str = MEMBERSHIP_ID) -> None:
    _allow(
        platform,
        tenant_id,
        [ROLES_MANAGE, USERS_READ, LEADS, PROJECT_ACCESS, RECORDS_ACCESS, MANAGE],
    )
    platform.access_by_tenant[str(tenant_id)] = _access(tenant_id, membership_id=membership_id)


def _role(client, name: str = "Desk") -> str:
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/roles",
        headers=_headers(write=True),
        json={"name": name},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _grant(client, role_id: str, key: str) -> None:
    granted = client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": key},
    )
    assert granted.status_code == 200, granted.text


def _assign(client, role_id: str, user_id: str = OTHER_ID):
    return client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/assignments",
        headers=_headers(write=True),
        json={"user_id": user_id},
    )


def _assignment_rows() -> list:
    connection = connect(database_path())
    rows = connection.execute(
        """
        SELECT tenant_id, role_id, user_id, status, tenant_membership_id
        FROM tenant_role_assignments
        ORDER BY created_at, id
        """
    ).fetchall()
    connection.close()
    return rows


def test_assign_and_revoke_bind_the_current_membership(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _grant_admin(platform)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com", membership_id=MEMBERSHIP_ID),
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    role_id = _role(client)
    _grant(client, role_id, PROJECT_ACCESS)
    missing_directory = client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/assignments",
        headers=_headers(write=False),
        json={"user_id": OTHER_ID},
    )
    assert missing_directory.status_code == 401
    assert platform.user_lookups == []
    created = _assign(client, role_id)
    assert created.status_code == 201, created.text
    assert created.json()["user_id"] == OTHER_ID
    assert created.json()["role_id"] == role_id
    assert created.json()["status"] == "active"
    assert "tenant_membership_id" not in created.text
    assert platform.user_lookups == [(str(TENANT_A), OTHER_ID)]
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/assignments",
        headers=_headers(write=False),
    )
    assert listed.status_code == 200
    assert [item["user_id"] for item in listed.json()["items"]] == [OTHER_ID]
    stored = _assignment_rows()
    assert stored[0]["tenant_membership_id"] == OTHER_MEMBERSHIP
    assert stored[0]["tenant_id"] == str(TENANT_A)
    again = _assign(client, role_id)
    assert again.status_code == 200
    assert len([row for row in _assignment_rows() if row["status"] == "active"]) == 1
    connection = connect(database_path())
    connection.execute(
        "UPDATE tenant_role_assignments SET tenant_membership_id = ? WHERE user_id = ?",
        (REPLACEMENT_MEMBERSHIP, OTHER_ID),
    )
    connection.commit()
    connection.close()
    refreshed = _assign(client, role_id)
    assert refreshed.status_code == 200
    assert _assignment_rows()[0]["tenant_membership_id"] == OTHER_MEMBERSHIP
    revoked = client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/assignments/remove",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/assignments/remove",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID},
    ).status_code == 404
    assert len(_assignment_rows()) == 1
    assert _assignment_rows()[0]["status"] == "revoked"


def test_assignment_rejects_stale_inactive_and_cross_tenant_targets(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _grant_admin(platform)
    _grant_admin(platform, TENANT_B, membership_id=OTHER_MEMBERSHIP)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
    ]
    platform.users_by_tenant[str(TENANT_B)] = [
        _person(OUTSIDE_USER, "other@example.com", membership_id=REPLACEMENT_MEMBERSHIP),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    role_id = _role(client, "Tenant A desk")
    _grant(client, role_id, LEADS)
    inactive_person = client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/assignments",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "tenant_membership_id": REPLACEMENT_MEMBERSHIP},
    )
    assert inactive_person.status_code == 422
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(OTHER_ID, "member@example.com", active=False, membership_id=OTHER_MEMBERSHIP),
    ]
    inactive_identity = _assign(client, role_id)
    assert inactive_identity.status_code == 422
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(OTHER_ID, "member@example.com", status="inactive", membership_id=OTHER_MEMBERSHIP),
    ]
    inactive_membership = _assign(client, role_id)
    assert inactive_membership.status_code == 422
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(OTHER_ID, "member@example.com", membership_id=""),
    ]
    blank_membership = _assign(client, role_id)
    assert blank_membership.status_code == 422
    assert _assignment_rows() == []
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
    ]
    missing_user = _assign(client, role_id, OUTSIDE_USER)
    assert missing_user.status_code == 404
    assert "other@example.com" not in missing_user.text
    foreign_role = client.post(
        f"/api/v1/tenants/{TENANT_B}/roles/{role_id}/assignments",
        headers=_headers(write=True),
        json={"user_id": OUTSIDE_USER},
    )
    assert foreign_role.status_code == 404
    assert "Tenant A desk" not in foreign_role.text
    client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{role_id}/deactivate",
        headers=_headers(write=True),
    )
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
    ]
    inactive_role = _assign(client, role_id)
    assert inactive_role.status_code == 409
    assert inactive_role.json()["error"]["message"] == "This role is inactive."
    assert _assignment_rows() == []
    platform.permissions_by_tenant[str(TENANT_A)] = [ROLES_MANAGE]
    platform.user_lookups.clear()
    denied = _assign(client, role_id)
    assert denied.status_code == 403
    assert platform.user_lookups == []
    platform.permissions_by_tenant[str(TENANT_A)] = [ROLES_MANAGE, USERS_READ]
    platform.users_by_tenant[str(TENANT_A)] = PlatformCallError(403)
    controlled = _assign(client, role_id)
    assert controlled.status_code == 403
    assert _assignment_rows() == []


def test_multiple_roles_union_and_invalid_rows_do_not_restore_control_plane_keys(
    tmp_path, monkeypatch
) -> None:
    platform = FakePlatform()
    _grant_admin(platform)
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
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    leads_role = _role(client, "Leads")
    records_role = _role(client, "Records")
    _grant(client, leads_role, LEADS)
    _grant(client, records_role, RECORDS_ACCESS)
    assert _assign(client, leads_role).status_code == 201
    assert _assign(client, records_role).status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS, PROJECT_ACCESS, RECORDS_ACCESS, MANAGE]
    opened = client.get(f"/api/v1/shell/tenants/{TENANT_A}/leads", headers=_headers(write=False))
    assert opened.status_code == 200
    records = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert records.status_code == 200
    projects = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert projects.status_code == 403
    assert "North yard" not in projects.text
    managed = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Taken"},
    )
    assert managed.status_code == 403
    connection = connect(database_path())
    connection.execute(
        """
        UPDATE tenant_role_assignments
        SET tenant_membership_id = ?
        WHERE role_id = ? AND user_id = ?
        """,
        (REPLACEMENT_MEMBERSHIP, records_role, OTHER_ID),
    )
    connection.commit()
    connection.close()
    leads_remain = client.get(
        f"/api/v1/shell/tenants/{TENANT_A}/leads",
        headers=_headers(write=False),
    )
    assert leads_remain.status_code == 200
    records_hidden = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert records_hidden.status_code == 403
    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    _grant_admin(platform)
    client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{leads_role}/deactivate",
        headers=_headers(write=True),
    )
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS, PROJECT_ACCESS, RECORDS_ACCESS, MANAGE]
    leads_closed = client.get(
        f"/api/v1/shell/tenants/{TENANT_A}/leads",
        headers=_headers(write=False),
    )
    assert leads_closed.status_code == 403
    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    _grant_admin(platform)
    removed = client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{leads_role}/assignments/remove",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID},
    )
    assert removed.status_code == 200
    client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{records_role}/assignments/remove",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID},
    )
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS, PROJECT_ACCESS, RECORDS_ACCESS, MANAGE]
    fallback = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert fallback.status_code == 403
    assert "North yard" not in fallback.text


def test_unassigned_users_keep_access_and_features_still_gate_assigned_users(
    tmp_path, monkeypatch
) -> None:
    platform = FakePlatform()
    _grant_admin(platform)
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
    project_id = created.json()["id"]
    before = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert before.status_code == 200
    assert before.json()["access"]["role"] == "project_manager"
    role_id = _role(client, "Projects")
    _grant(client, role_id, PROJECT_ACCESS)
    assert _assign(client, role_id, USER_ID).status_code == 201
    kept = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Manager kept it"},
    )
    assert kept.status_code == 200
    platform.access_by_tenant[str(TENANT_A)] = _access(
        TENANT_A,
        features=("lead_management", "records"),
    )
    denied = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert denied.status_code == 403
    assert "Manager kept it" not in denied.text
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    stranger_role = _role(client, "Manage only inside CRM")
    _grant(client, stranger_role, PROJECT_ACCESS)
    _grant(client, stranger_role, MANAGE)
    assert _assign(client, stranger_role).status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS]
    hidden = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []
    assert "Manager kept it" not in hidden.text
    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS, ROLES_MANAGE, USERS_READ]
    still_manager = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Still the manager"},
    )
    assert still_manager.status_code == 200
    connection = connect(database_path())
    connection.execute(
        """
        UPDATE project_memberships
        SET tenant_membership_id = ?
        WHERE project_id = ? AND user_id = ?
        """,
        (REPLACEMENT_MEMBERSHIP, project_id, USER_ID),
    )
    connection.commit()
    connection.close()
    rebound = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert rebound.status_code == 404
    assert "Still the manager" not in rebound.text


def test_record_scope_survives_a_control_plane_manage_key(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A, [LEADS, PROJECT_ACCESS, RECORDS_ACCESS])
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com", membership_id=MEMBERSHIP_ID),
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    secret = _create(client, project_id, form_id, {"school_name": "Manager only", "priority": "hot"})
    assert secret.status_code == 201
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS, RECORDS_ACCESS, MANAGE]
    seen = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{secret.json()['id']}",
        headers=_headers(write=False),
    )
    assert seen.status_code == 200
    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    platform.permissions_by_tenant[str(TENANT_A)] = [
        ROLES_MANAGE,
        USERS_READ,
        PROJECT_ACCESS,
        RECORDS_ACCESS,
    ]
    role_id = _role(client, "Records desk")
    _grant(client, role_id, RECORDS_ACCESS_PERMISSION)
    assert _assign(client, role_id).status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [PROJECT_ACCESS, RECORDS_ACCESS, MANAGE]
    hidden = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{secret.json()['id']}",
        headers=_headers(write=False),
    )
    assert hidden.status_code == 404
    assert "Manager only" not in hidden.text
    own = _create(client, project_id, form_id, {"school_name": "Member school"})
    assert own.status_code == 201
    visible = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert [item["id"] for item in visible.json()["items"]] == [own.json()["id"]]
    member_update = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Member cannot rename"},
    )
    assert member_update.status_code == 403


def test_shell_module_permissions_follow_effective_role_rules(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _grant_admin(platform)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com", membership_id=MEMBERSHIP_ID),
        _person(OTHER_ID, "member@example.com", membership_id=OTHER_MEMBERSHIP),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    unassigned = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert unassigned.status_code == 200
    assert unassigned.json()["module_permissions"] == [
        LEADS,
        PROJECT_ACCESS,
        MANAGE,
        RECORDS_ACCESS,
    ]
    platform.access_by_tenant[str(TENANT_A)] = _access(
        TENANT_A,
        membership_id=MEMBERSHIP_ID,
        features=("lead_management", "project_management"),
    )
    without_records = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert without_records.status_code == 200
    assert without_records.json()["module_permissions"] == [LEADS, PROJECT_ACCESS, MANAGE]
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)

    leads_role = _role(client, "Leads desk")
    project_role = _role(client, "Project desk")
    _grant(client, leads_role, LEADS)
    _grant(client, project_role, PROJECT_ACCESS)
    _grant(client, project_role, RECORDS_ACCESS)
    assert _assign(client, leads_role).status_code == 201
    assert _assign(client, project_role).status_code == 201

    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [
        LEADS,
        PROJECT_ACCESS,
        RECORDS_ACCESS,
        MANAGE,
        ROLES_MANAGE,
        USERS_READ,
        "audit.read",
    ]
    combined = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert combined.status_code == 200
    assert combined.json()["module_permissions"] == [LEADS, PROJECT_ACCESS, RECORDS_ACCESS]

    _become(platform, USER_ID, "manager@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=MEMBERSHIP_ID)
    platform.permissions_by_tenant[str(TENANT_A)] = [
        ROLES_MANAGE,
        USERS_READ,
        LEADS,
        PROJECT_ACCESS,
        RECORDS_ACCESS,
        MANAGE,
    ]
    revoked = client.post(
        f"/api/v1/tenants/{TENANT_A}/roles/{leads_role}/assignments/remove",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID},
    )
    assert revoked.status_code == 200
    _become(platform, OTHER_ID, "member@example.com")
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, membership_id=OTHER_MEMBERSHIP)
    platform.permissions_by_tenant[str(TENANT_A)] = [
        LEADS,
        PROJECT_ACCESS,
        RECORDS_ACCESS,
        MANAGE,
        ROLES_MANAGE,
    ]
    narrowed = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert narrowed.json()["module_permissions"] == [PROJECT_ACCESS, RECORDS_ACCESS]
    assert client.get(f"/api/v1/shell/tenants/{TENANT_A}/leads").status_code == 403

    connection = connect(database_path())
    connection.execute(
        "UPDATE tenant_role_assignments SET tenant_membership_id = ? WHERE user_id = ?",
        (REPLACEMENT_MEMBERSHIP, OTHER_ID),
    )
    connection.commit()
    connection.close()
    stale = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert stale.status_code == 200
    assert stale.json()["module_permissions"] == []
    assert client.get(f"/api/v1/shell/tenants/{TENANT_A}/leads").status_code == 403

    platform.access_by_tenant[str(TENANT_A)] = PlatformCallError(404)
    missing = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert missing.status_code == 404
    assert "module_permissions" not in missing.text
