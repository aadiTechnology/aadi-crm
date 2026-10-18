"""Shell isolation against a platform double. No database and no live Control Plane."""

from uuid import UUID

from fastapi.testclient import TestClient

from app.api.shell import get_platform_client
from app.main import create_app
from app.platform_client import PlatformCallError, ProductAccessView

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")
LEADS = "crm.lead_management.read"


class FakePlatform:
    def __init__(self) -> None:
        self.access_calls: list[str] = []
        self.permission_calls: list[str] = []
        self.access_by_tenant: dict[str, ProductAccessView | PlatformCallError] = {}
        self.permissions_by_tenant: dict[str, list[str] | PlatformCallError] = {}
        self.cookies: list[str | None] = []

    def product_access(self, tenant_id: str, cookie: str | None) -> ProductAccessView:
        self.access_calls.append(tenant_id)
        self.cookies.append(cookie)
        result = self.access_by_tenant[tenant_id]
        if isinstance(result, PlatformCallError):
            raise result
        return result

    def permissions(self, tenant_id: str, cookie: str | None) -> list[str]:
        self.permission_calls.append(tenant_id)
        self.cookies.append(cookie)
        result = self.permissions_by_tenant[tenant_id]
        if isinstance(result, PlatformCallError):
            raise result
        return result


def _access(tenant_id: UUID, *, available: bool, name: str = "Aadi Technology") -> ProductAccessView:
    return ProductAccessView(
        tenant_id=str(tenant_id),
        tenant_name=name,
        product_name="CRM",
        available=available,
    )


def _client(platform: FakePlatform) -> TestClient:
    application = create_app()
    application.dependency_overrides[get_platform_client] = lambda: platform
    return TestClient(application)


def test_unauthenticated_shell_is_rejected_without_tenant_fields() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = PlatformCallError(401)
    response = _client(platform).get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "UNAUTHORIZED", "message": "Authentication is required."}
    }
    assert "Aadi" not in response.text


def test_inactive_membership_returns_not_found_without_foreign_name() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = PlatformCallError(404)
    response = _client(platform).get(
        f"/api/v1/shell/tenants/{TENANT_A}",
        headers={"cookie": "aadi_session=member"},
    )
    assert response.status_code == 404
    assert "Other Org" not in response.text
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_platform_tenant_mismatch_hides_the_other_tenant() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = ProductAccessView(
        tenant_id=str(TENANT_B),
        tenant_name="Other Org",
        product_name="CRM",
        available=True,
    )
    response = _client(platform).get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert response.status_code == 404
    assert "Other Org" not in response.text
    assert str(TENANT_B) not in response.text


def test_query_and_body_tenant_ids_do_not_select_the_platform_tenant() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=True)
    response = _client(platform).request(
        "GET",
        f"/api/v1/shell/tenants/{TENANT_A}",
        params={"tenant_id": str(TENANT_B)},
        json={"tenant_id": str(TENANT_B)},
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(TENANT_A)
    assert platform.access_calls == [str(TENANT_A)]


def test_unavailable_entitlement_denies_leads_and_keeps_the_shell_readable() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=False)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS]
    client = _client(platform)
    shell = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    leads = client.get(f"/api/v1/shell/tenants/{TENANT_A}/leads")
    assert shell.status_code == 200
    assert shell.json()["available"] is False
    assert leads.status_code == 403
    assert leads.json()["error"]["code"] == "FORBIDDEN"
    assert "items" not in leads.text


def test_missing_permission_denies_leads_when_the_product_is_available() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=True)
    platform.permissions_by_tenant[str(TENANT_A)] = ["crm.lead_management"]
    response = _client(platform).get(f"/api/v1/shell/tenants/{TENANT_A}/leads")
    assert response.status_code == 403
    assert platform.permission_calls == [str(TENANT_A)]


def test_authorized_leads_stub_is_empty() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=True)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS, "users.read"]
    response = _client(platform).get(
        f"/api/v1/shell/tenants/{TENANT_A}/leads",
        headers={"cookie": "aadi_session=member"},
    )
    assert response.status_code == 200
    assert response.json() == {"module": "leads", "items": []}
    assert platform.cookies[0] == "aadi_session=member"


def test_cross_tenant_leads_call_does_not_use_the_other_tenant() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = PlatformCallError(404)
    platform.access_by_tenant[str(TENANT_B)] = _access(TENANT_B, available=True, name="Other Org")
    platform.permissions_by_tenant[str(TENANT_B)] = [LEADS]
    response = _client(platform).get(f"/api/v1/shell/tenants/{TENANT_A}/leads")
    assert response.status_code == 404
    assert "Other Org" not in response.text
    assert platform.access_calls == [str(TENANT_A)]
    assert platform.permission_calls == []
