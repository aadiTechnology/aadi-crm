"""Tenant-scoped project API. Platform calls use an in-process double."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.projects import project_management_allowed
from app.api.shell import get_platform_client
from app.db import DuplicateProjectCode, apply_migrations, connect, create_project, database_path
from app.main import create_app
from app.platform_client import IdentityView, PlatformCallError, ProductAccessView

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
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
