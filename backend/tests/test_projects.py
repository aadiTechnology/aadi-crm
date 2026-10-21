"""Tenant-scoped project API. Platform calls use an in-process double."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.projects import Caller, authorize_record, project_management_allowed
from app.api.shell import get_platform_client
from app.db import DuplicateProjectCode, apply_migrations, connect, create_project, database_path
from app.main import create_app
from app.platform_client import IdentityView, PlatformCallError, ProductAccessView, TenantUserView
from app.project_access import RecordRef, access_for, decide_record_access, tenant_project_admin

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
OUTSIDE_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
LEADS = "crm.lead_management.read"
MANAGE = "crm.project_management.manage"


class FakePlatform:
    def __init__(self) -> None:
        self.access_calls: list[str] = []
        self.permission_calls: list[str] = []
        self.identity_calls = 0
        self.access_by_tenant: dict[str, ProductAccessView | PlatformCallError] = {}
        self.permissions_by_tenant: dict[str, list[str] | PlatformCallError] = {}
        self.identity_result: IdentityView | PlatformCallError = IdentityView(
            user_id=USER_ID,
            email="member@example.com",
        )
        self.users_by_tenant: dict[str, list[TenantUserView] | PlatformCallError] = {}
        self.user_lookups: list[tuple[str, str]] = []
        self.audit_by_tenant: dict[str, list[dict[str, object]] | PlatformCallError] = {}
        self.audit_calls: list[tuple[str, int]] = []

    def product_access(self, tenant_id: str, cookie: str | None) -> ProductAccessView:
        self.access_calls.append(tenant_id)
        result = self.access_by_tenant[tenant_id]
        if isinstance(result, PlatformCallError):
            raise result
        return result

    def permissions(self, tenant_id: str, cookie: str | None) -> list[str]:
        self.permission_calls.append(tenant_id)
        result = self.permissions_by_tenant[tenant_id]
        if isinstance(result, PlatformCallError):
            raise result
        return result

    def identity(self, cookie: str | None) -> IdentityView:
        self.identity_calls += 1
        if isinstance(self.identity_result, PlatformCallError):
            raise self.identity_result
        return self.identity_result

    def list_tenant_users(self, tenant_id: str, cookie: str | None) -> list[TenantUserView]:
        result = self.users_by_tenant.get(tenant_id, [])
        if isinstance(result, PlatformCallError):
            raise result
        return result

    def get_tenant_user(self, tenant_id: str, user_id: str, cookie: str | None) -> TenantUserView:
        self.user_lookups.append((tenant_id, user_id))
        result = self.users_by_tenant.get(tenant_id, [])
        if isinstance(result, PlatformCallError):
            raise result
        for user in result:
            if user.user_id == user_id:
                return user
        raise PlatformCallError(404)

    def list_audit_events(self, tenant_id: str, cookie: str | None, *, limit: int) -> list[dict[str, object]]:
        del cookie
        self.audit_calls.append((tenant_id, limit))
        result = self.audit_by_tenant.get(tenant_id, [])
        if isinstance(result, PlatformCallError):
            raise result
        return result[:limit]


def _access(tenant_id: UUID, *, available: bool = True, name: str = "Aadi Technology") -> ProductAccessView:
    return ProductAccessView(
        tenant_id=str(tenant_id),
        tenant_name=name,
        product_name="CRM",
        available=available,
    )


def _client(tmp_path, monkeypatch, platform: FakePlatform) -> TestClient:
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "projects.sqlite"))
    application = create_app()
    application.dependency_overrides[get_platform_client] = lambda: platform
    return TestClient(application)


def _allow(platform: FakePlatform, tenant_id: UUID, keys: list[str] | None = None) -> None:
    platform.access_by_tenant[str(tenant_id)] = _access(tenant_id)
    platform.permissions_by_tenant[str(tenant_id)] = keys if keys is not None else [LEADS]


def _headers(*, write: bool) -> dict[str, str]:
    headers = {"cookie": "aadi_session=member; aadi_csrf=csrf-token"}
    if write:
        headers["x-csrf-token"] = "csrf-token"
    return headers


def test_migration_is_repeatable_and_codes_are_unique_per_tenant(tmp_path) -> None:
    path = tmp_path / "disposable.sqlite"
    apply_migrations(path)
    apply_migrations(path)
    connection = connect(path)
    first = create_project(
        connection,
        tenant_id=str(TENANT_A),
        code="North",
        name="North",
        description="",
        created_by=USER_ID,
    )
    other = create_project(
        connection,
        tenant_id=str(TENANT_B),
        code="north",
        name="Other North",
        description="",
        created_by=USER_ID,
    )
    assert first.tenant_id != other.tenant_id
    try:
        create_project(
            connection,
            tenant_id=str(TENANT_A),
            code="NORTH",
            name="Duplicate",
            description="",
            created_by=USER_ID,
        )
    except DuplicateProjectCode:
        pass
    else:
        raise AssertionError("duplicate code was stored")
    remaining = connection.execute("SELECT COUNT(*) AS count FROM projects").fetchone()
    assert remaining is not None
    assert remaining["count"] == 2
    connection.close()


def test_database_path_refuses_the_control_plane_name(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "aadi_platform.sqlite"))
    try:
        database_path()
    except RuntimeError as exc:
        assert "Control Plane" in str(exc)
    else:
        raise AssertionError("control plane path was accepted")


def test_project_permission_policy_rejects_product_access_alone() -> None:
    assert project_management_allowed([LEADS]) is True
    assert project_management_allowed([MANAGE]) is True
    assert project_management_allowed(["users.read", "roles.manage"]) is False
    assert project_management_allowed([]) is False


def test_create_requires_csrf_and_rejects_invalid_fields(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    missing_csrf = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers={"cookie": "aadi_session=member"},
        json={"code": "N-1", "name": "North"},
    )
    assert missing_csrf.status_code == 401
    assert platform.access_calls == []
    invalid = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "", "name": "North", "tenant_id": str(TENANT_B)},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    listed = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert listed.status_code == 200
    assert listed.json() == {"items": []}


def test_create_list_edit_archive_and_search(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    client = _client(tmp_path, monkeypatch, platform)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "North yard", "description": "Recording yard"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["tenant_id"] == str(TENANT_A)
    assert body["code"] == "N-1"
    assert body["status"] == "active"
    assert body["created_by"] == USER_ID
    assert body["created_at"]
    assert body["updated_at"]
    project_id = body["id"]
    other = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "S-1", "name": "South yard", "description": "Other"},
    )
    assert other.status_code == 201
    duplicate = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "n-1", "name": "Again"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CONFLICT"
    edited = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "North gate", "description": "Updated yard"},
    )
    assert edited.status_code == 200
    assert edited.json()["code"] == "N-1"
    assert edited.json()["name"] == "North gate"
    assert edited.json()["description"] == "Updated yard"
    code_change = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"code": "Z-9"},
    )
    assert code_change.status_code == 422
    found = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects?q=gate",
        headers=_headers(write=False),
    )
    assert found.status_code == 200
    assert [item["code"] for item in found.json()["items"]] == ["N-1"]
    wildcard = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects?q=%",
        headers=_headers(write=False),
    )
    assert wildcard.json()["items"] == []
    archived = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive",
        headers=_headers(write=True),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    again = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive",
        headers=_headers(write=True),
    )
    assert again.status_code == 200
    assert again.json()["id"] == project_id
    active = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects?status=active",
        headers=_headers(write=False),
    )
    assert [item["code"] for item in active.json()["items"]] == ["S-1"]
    only_archived = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects?status=archived",
        headers=_headers(write=False),
    )
    assert [item["name"] for item in only_archived.json()["items"]] == ["North gate"]
    removed = client.delete(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
    )
    assert removed.status_code == 405
    still_there = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert still_there.status_code == 200
    assert still_there.json()["status"] == "archived"


def test_cross_tenant_read_and_mutation_are_hidden(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A, [MANAGE])
    _allow(platform, TENANT_B, [MANAGE])
    platform.access_by_tenant[str(TENANT_B)] = _access(TENANT_B, name="Other Org")
    client = _client(tmp_path, monkeypatch, platform)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "Secret North"},
    )
    project_id = created.json()["id"]
    listed = client.get(f"/api/v1/tenants/{TENANT_B}/projects", headers=_headers(write=False))
    assert listed.status_code == 200
    assert listed.json()["items"] == []
    assert "Secret North" not in listed.text
    for method, path in (
        ("GET", f"/api/v1/tenants/{TENANT_B}/projects/{project_id}"),
        ("PATCH", f"/api/v1/tenants/{TENANT_B}/projects/{project_id}"),
        ("POST", f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/archive"),
    ):
        response = client.request(method, path, headers=_headers(write=method != "GET"), json={"name": "Stolen"})
        assert response.status_code == 404
        assert "Secret North" not in response.text
        assert "Other Org" not in response.text
    untouched = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert untouched.json()["name"] == "Secret North"
    assert untouched.json()["status"] == "active"


def test_authentication_and_permission_boundaries(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = PlatformCallError(401)
    client = _client(tmp_path, monkeypatch, platform)
    anonymous = client.get(f"/api/v1/tenants/{TENANT_A}/projects")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "UNAUTHORIZED"
    _allow(platform, TENANT_A, ["users.read"])
    connection = connect(database_path())
    create_project(
        connection,
        tenant_id=str(TENANT_A),
        code="N-1",
        name="Secret North",
        description="",
        created_by=USER_ID,
    )
    connection.close()
    denied = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert denied.status_code == 403
    assert "Secret North" not in denied.text
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=False)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS, MANAGE]
    unavailable = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert unavailable.status_code == 403
    assert "items" not in unavailable.text
    platform.access_by_tenant[str(TENANT_A)] = ProductAccessView(
        tenant_id=str(TENANT_B),
        tenant_name="Other Org",
        product_name="CRM",
        available=True,
    )
    mismatch = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects?tenant_id={TENANT_B}",
        headers=_headers(write=False),
    )
    assert mismatch.status_code == 404
    assert "Other Org" not in mismatch.text
    assert platform.access_calls[-1] == str(TENANT_A)


def test_leads_stub_remains_unchanged(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    response = client.get(
        f"/api/v1/shell/tenants/{TENANT_A}/leads",
        headers=_headers(write=False),
    )
    assert response.status_code == 200
    assert response.json() == {"module": "leads", "items": []}


def test_missing_name_and_bad_status_are_rejected(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    missing_name = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": " "},
    )
    assert missing_name.status_code == 422
    assert missing_name.json()["error"]["message"] == "Project name is required."
    bad_status = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects?status=deleted",
        headers=_headers(write=False),
    )
    assert bad_status.status_code == 422
    unknown = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{uuid4()}",
        headers=_headers(write=False),
    )
    assert unknown.status_code == 404


def _person(user_id: str, email: str, *, active: bool = True, status: str = "active") -> TenantUserView:
    return TenantUserView(
        user_id=user_id,
        email=email,
        identity_active=active,
        membership_status=status,
    )


def _become(platform: FakePlatform, user_id: str, email: str) -> None:
    platform.identity_result = IdentityView(user_id=user_id, email=email)


def test_record_scope_contract_denies_non_members() -> None:
    assert project_management_allowed([LEADS]) is True
    assert tenant_project_admin([LEADS]) is False
    assert tenant_project_admin([MANAGE]) is True
    assert tenant_project_admin(["users.read", "roles.manage"]) is False
    manager = access_for(role="project_manager", status="active", permission_keys=[LEADS])
    member = access_for(role="project_member", status="active", permission_keys=[LEADS])
    removed = access_for(role="project_manager", status="removed", permission_keys=[LEADS])
    stranger = access_for(role=None, status=None, permission_keys=[LEADS])
    admin = access_for(role=None, status=None, permission_keys=[MANAGE])
    assert manager.allows("access_records") is True
    assert manager.record_scope() == "project"
    assert manager.allows("add_member") is True
    assert member.record_scope() == "assigned"
    assert member.allows("archive_project") is False
    assert member.allows("add_member") is False
    assert removed.allows("view_project") is False
    assert removed.record_scope() is None
    assert stranger.allows("view_project") is False
    assert admin.allows("archive_project") is True
    assert admin.record_scope() == "project"
    own = RecordRef(tenant_id=str(TENANT_A), project_id="project-a", assignee_user_id=OTHER_ID)
    other_assignee = RecordRef(tenant_id=str(TENANT_A), project_id="project-a", assignee_user_id=USER_ID)
    unassigned = RecordRef(tenant_id=str(TENANT_A), project_id="project-a", assignee_user_id=None)
    other_project = RecordRef(tenant_id=str(TENANT_A), project_id="project-b", assignee_user_id=OTHER_ID)
    other_tenant = RecordRef(tenant_id=str(TENANT_B), project_id="project-a", assignee_user_id=OTHER_ID)
    manager_decision = decide_record_access(
        caller_user_id=USER_ID,
        authorized_tenant_id=str(TENANT_A),
        authorized_project_id="project-a",
        access=manager,
        record=other_assignee,
    )
    assert manager_decision.allowed is True
    assert manager_decision.scope == "project"
    assigned = decide_record_access(
        caller_user_id=OTHER_ID,
        authorized_tenant_id=str(TENANT_A),
        authorized_project_id="project-a",
        access=member,
        record=own,
    )
    assert assigned.allowed is True
    assert assigned.scope == "assigned"
    for record in (other_assignee, unassigned, other_project, other_tenant):
        denied = decide_record_access(
            caller_user_id=OTHER_ID,
            authorized_tenant_id=str(TENANT_A),
            authorized_project_id="project-a",
            access=member,
            record=record,
        )
        assert denied.allowed is False
        assert denied.scope is None
    removed_decision = decide_record_access(
        caller_user_id=USER_ID,
        authorized_tenant_id=str(TENANT_A),
        authorized_project_id="project-a",
        access=removed,
        record=other_assignee,
    )
    assert removed_decision.allowed is False
    stranger_decision = decide_record_access(
        caller_user_id=OTHER_ID,
        authorized_tenant_id=str(TENANT_A),
        authorized_project_id="project-a",
        access=stranger,
        record=own,
    )
    assert stranger_decision.allowed is False


def test_membership_migration_preserves_archived_projects(tmp_path) -> None:
    from pathlib import Path

    path = tmp_path / "legacy.sqlite"
    connection = connect(path)
    script = Path(__file__).resolve().parents[1] / "migrations" / "001_projects.sql"
    connection.executescript(script.read_text(encoding="utf-8"))
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO crm_schema_migrations (version, applied_at)
        VALUES ('001_projects.sql', '2026-10-19T00:00:00+00:00')
        """
    )
    connection.execute(
        """
        INSERT INTO projects (
            id, tenant_id, code, name, description, status, created_by, created_at, updated_at
        )
        VALUES ('p-legacy', ?, 'S2-REC', 'Recording gate', 'Kept', 'archived', ?, ?, ?)
        """,
        (str(TENANT_A), USER_ID, "2026-10-19T00:00:00+00:00", "2026-10-19T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()
    apply_migrations(path)
    apply_migrations(path)
    connection = connect(path)
    versions = [row["version"] for row in connection.execute("SELECT version FROM crm_schema_migrations ORDER BY version")]
    assert versions == [
        "001_projects.sql",
        "002_project_memberships.sql",
        "003_form_definitions.sql",
        "004_form_versions.sql",
        "005_records.sql",
        "006_followups.sql",
        "007_reminders.sql",
        "008_imports.sql",
    ]
    assert connection.execute("SELECT COUNT(*) AS count FROM reminder_deliveries").fetchone()["count"] == 0
    assert connection.execute("SELECT COUNT(*) AS count FROM import_jobs").fetchone()["count"] == 0
    assert connection.execute("SELECT COUNT(*) AS count FROM import_rows").fetchone()["count"] == 0
    assert connection.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"] == 0
    assert connection.execute("SELECT COUNT(*) AS count FROM follow_ups").fetchone()["count"] == 0
    assert connection.execute("SELECT COUNT(*) AS count FROM form_definitions").fetchone()["count"] == 0
    stored = connection.execute("SELECT name, status FROM projects").fetchone()
    assert stored is not None
    assert stored["name"] == "Recording gate"
    assert stored["status"] == "archived"
    assert connection.execute("SELECT COUNT(*) AS count FROM projects").fetchone()["count"] == 1
    memberships = list(connection.execute("SELECT user_id, role, status, scope_policy FROM project_memberships"))
    assert len(memberships) == 1
    assert memberships[0]["user_id"] == USER_ID
    assert memberships[0]["role"] == "project_manager"
    assert memberships[0]["status"] == "active"
    assert memberships[0]["scope_policy"] == "project"
    connection.close()


def test_project_membership_roles_and_scope(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "other@example.com"),
        _person(OUTSIDE_ID, "inactive@example.com", status="inactive"),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "Secret North"},
    )
    assert created.status_code == 201
    assert created.json()["access"]["role"] == "project_manager"
    assert created.json()["access"]["record_scope"] == "project"
    project_id = created.json()["id"]
    members = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=False),
    )
    assert members.status_code == 200
    assert members.json()["items"][0]["user_id"] == USER_ID
    assert members.json()["items"][0]["role"] == "project_manager"
    assert members.json()["items"][0]["status"] == "active"
    assert members.json()["items"][0]["email"] == "member@example.com"

    _become(platform, OTHER_ID, "other@example.com")
    hidden = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []
    denied = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert denied.status_code == 404
    assert "Secret North" not in denied.text
    for method, path in (
        ("PATCH", f"/api/v1/tenants/{TENANT_A}/projects/{project_id}"),
        ("POST", f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive"),
        ("POST", f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members"),
    ):
        response = client.request(
            method,
            path,
            headers=_headers(write=True),
            json={"name": "Stolen", "user_id": OTHER_ID, "role": "project_manager"},
        )
        assert response.status_code == 404
        assert "Secret North" not in response.text
    foreign = client.post(
        f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert foreign.status_code == 404
    assert "Secret North" not in foreign.text

    _become(platform, USER_ID, "manager@example.com")
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    assert added.json()["role"] == "project_member"
    assert added.json()["scope_policy"] == "assigned"
    assert added.json()["email"] == "other@example.com"
    membership_id = added.json()["id"]
    duplicate = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_manager"},
    )
    assert duplicate.status_code == 409
    outside = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": str(uuid4()), "role": "project_member"},
    )
    assert outside.status_code == 404
    assert outside.json()["error"]["message"] == "That user is not a member of this organization."
    inactive = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OUTSIDE_ID, "role": "project_member"},
    )
    assert inactive.status_code == 422
    missing_csrf = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers={"cookie": "aadi_session=member"},
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert missing_csrf.status_code == 401
    lookups_before_directory_block = len(platform.user_lookups)

    _become(platform, OTHER_ID, "other@example.com")
    viewed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert viewed.status_code == 200
    assert viewed.json()["access"]["role"] == "project_member"
    assert viewed.json()["access"]["can_manage_members"] is False
    assert viewed.json()["access"]["record_scope"] == "assigned"
    blocked = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": "Stolen"},
    )
    assert blocked.status_code == 403
    assert client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive",
        headers=_headers(write=True),
    ).status_code == 403
    assert client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": USER_ID, "role": "project_member"},
    ).status_code == 403
    untouched = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert untouched.json()["name"] == "Secret North"

    _become(platform, USER_ID, "manager@example.com")
    promoted = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{membership_id}",
        headers=_headers(write=True),
        json={"role": "project_manager"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "project_manager"
    assert promoted.json()["scope_policy"] == "project"
    creator = members.json()["items"][0]["id"]
    removed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{creator}/remove",
        headers=_headers(write=True),
    )
    assert removed.status_code == 200
    assert removed.json()["status"] == "removed"
    _become(platform, USER_ID, "manager@example.com")
    lost = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert lost.status_code == 404
    _become(platform, OTHER_ID, "other@example.com")
    kept = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert kept.status_code == 200
    last = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{membership_id}/remove",
        headers=_headers(write=True),
    )
    assert last.status_code == 409
    assert last.json()["error"]["message"] == "This project needs an active project manager."
    assert client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    ).status_code == 200
    history = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=False),
    )
    statuses = {(item["user_id"], item["status"]) for item in history.json()["items"]}
    assert (USER_ID, "removed") in statuses
    assert (OTHER_ID, "active") in statuses

    platform.users_by_tenant[str(TENANT_A)] = PlatformCallError(403)
    blocked_directory = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/eligible-users",
        headers=_headers(write=False),
    )
    assert blocked_directory.status_code == 403
    assert blocked_directory.json()["error"]["message"] == (
        "You cannot look up organization members with this sign-in."
    )
    refused = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": USER_ID, "role": "project_member"},
    )
    assert refused.status_code == 403
    assert len(platform.user_lookups) >= lookups_before_directory_block
    connection = connect(database_path())
    manager = Caller(user_id=OTHER_ID, email="other@example.com", keys=[LEADS])
    assigned_record = RecordRef(tenant_id=str(TENANT_A), project_id=project_id, assignee_user_id=USER_ID)
    allowed = authorize_record(
        connection,
        tenant_id=str(TENANT_A),
        project_id=project_id,
        caller=manager,
        record=assigned_record,
    )
    assert allowed.allowed is True
    assert allowed.scope == "project"
    removed_caller = Caller(user_id=USER_ID, email="manager@example.com", keys=[LEADS])
    blocked = authorize_record(
        connection,
        tenant_id=str(TENANT_A),
        project_id=project_id,
        caller=removed_caller,
        record=assigned_record,
    )
    assert blocked.allowed is False
    foreign_record = authorize_record(
        connection,
        tenant_id=str(TENANT_A),
        project_id=project_id,
        caller=manager,
        record=RecordRef(tenant_id=str(TENANT_B), project_id=project_id, assignee_user_id=OTHER_ID),
    )
    assert foreign_record.allowed is False
    connection.close()


def test_invalid_role_does_not_create_a_membership(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    platform.users_by_tenant[str(TENANT_A)] = [_person(OTHER_ID, "other@example.com")]
    client = _client(tmp_path, monkeypatch, platform)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "North"},
    )
    project_id = created.json()["id"]
    invalid = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "tenant_admin"},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["message"] == "Project role must be project manager or project member."
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=False),
    )
    assert [item["user_id"] for item in listed.json()["items"]] == [USER_ID]


def test_manage_permission_sees_projects_without_membership_and_lead_read_does_not(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A, [LEADS])
    client = _client(tmp_path, monkeypatch, platform)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "Secret North"},
    )
    project_id = created.json()["id"]
    _become(platform, OTHER_ID, "other@example.com")
    assert client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False)).json()["items"] == []
    platform.permissions_by_tenant[str(TENANT_A)] = [MANAGE]
    listed = client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [project_id]
    opened = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert opened.status_code == 200
    assert opened.json()["access"]["can_manage_project"] is True
    assert opened.json()["name"] == "Secret North"
