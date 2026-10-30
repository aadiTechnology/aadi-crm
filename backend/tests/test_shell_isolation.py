"""Shell isolation against a platform double. No database and no live Control Plane."""

import logging
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.shell import get_platform_client
from app.main import create_app
from app.platform_client import IdentityView, PlatformCallError, ProductAccessView

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

    def identity(self, cookie: str | None) -> IdentityView:
        del cookie
        return IdentityView(
            user_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            email="member@example.com",
        )


def _access(
    tenant_id: UUID,
    *,
    available: bool,
    name: str = "Aadi Technology",
    features: tuple[str, ...] = ("lead_management", "project_management", "records"),
) -> ProductAccessView:
    return ProductAccessView(
        tenant_id=str(tenant_id),
        tenant_name=name,
        product_name="CRM",
        available=available,
        features=features,
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
    assert "module_permissions" not in response.text
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


def test_query_and_body_tenant_ids_do_not_select_the_platform_tenant(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CRM_DATABASE_URL", raising=False)
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "shell.sqlite"))
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=True)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS, "roles.manage", "users.read", "audit.read"]
    response = _client(platform).request(
        "GET",
        f"/api/v1/shell/tenants/{TENANT_A}",
        params={"tenant_id": str(TENANT_B)},
        json={"tenant_id": str(TENANT_B)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == str(TENANT_A)
    assert body["module_permissions"] == [LEADS]
    assert "roles.manage" not in body["module_permissions"]
    assert "users.read" not in body["module_permissions"]
    assert "audit.read" not in body["module_permissions"]
    assert platform.access_calls == [str(TENANT_A)]


def test_unavailable_entitlement_denies_leads_and_keeps_the_shell_readable() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=False)
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS]
    client = _client(platform)
    shell = client.get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert shell.status_code == 200
    assert shell.json()["available"] is False
    assert shell.json()["module_permissions"] == []
    assert platform.permission_calls == []
    leads = client.get(f"/api/v1/shell/tenants/{TENANT_A}/leads")
    assert leads.status_code == 403
    assert leads.json()["error"]["code"] == "FORBIDDEN"
    assert "items" not in leads.text


def test_shell_omits_a_feature_the_subscription_does_not_include(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CRM_DATABASE_URL", raising=False)
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "shell.sqlite"))
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(
        TENANT_A,
        available=True,
        features=("project_management", "records"),
    )
    platform.permissions_by_tenant[str(TENANT_A)] = [
        LEADS,
        "crm.project_management.access",
        "crm.project_management.manage",
        "crm.records.access",
        "roles.manage",
    ]
    response = _client(platform).get(f"/api/v1/shell/tenants/{TENANT_A}")
    assert response.status_code == 200
    assert response.json()["module_permissions"] == [
        "crm.project_management.access",
        "crm.project_management.manage",
        "crm.records.access",
    ]


def test_missing_lead_feature_denies_leads_when_the_permission_is_present() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(
        TENANT_A,
        available=True,
        features=("project_management", "records"),
    )
    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS]
    response = _client(platform).get(f"/api/v1/shell/tenants/{TENANT_A}/leads")
    assert response.status_code == 403
    assert "items" not in response.text


def test_product_access_rejects_a_payload_without_features(monkeypatch) -> None:
    import httpx

    from app.platform_client import PlatformCallError, PlatformClient

    def fake_get(url: str, headers: dict | None = None, timeout: float | None = None) -> httpx.Response:
        del headers, timeout
        if url.endswith("/access"):
            return httpx.Response(
                200,
                json={
                    "tenant_id": str(TENANT_A),
                    "tenant_name": "Aadi Technology",
                    "product_key": "crm",
                    "product_name": "CRM",
                    "available": True,
                },
            )
        return httpx.Response(500)

    monkeypatch.setattr(httpx, "get", fake_get)
    try:
        PlatformClient("http://platform.test").product_access(str(TENANT_A), "aadi_session=member")
    except PlatformCallError as exc:
        assert exc.status_code == 502
    else:
        raise AssertionError("A product-access payload without features was accepted.")


def test_missing_permission_denies_leads_when_the_product_is_available() -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = _access(TENANT_A, available=True)
    platform.permissions_by_tenant[str(TENANT_A)] = ["crm.lead_management"]
    response = _client(platform).get(f"/api/v1/shell/tenants/{TENANT_A}/leads")
    assert response.status_code == 403
    assert platform.permission_calls == [str(TENANT_A)]


def test_authorized_leads_stub_is_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CRM_DATABASE_URL", raising=False)
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "shell.sqlite"))
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


def _capture(caplog, level: int):
    logger = logging.getLogger("aadi_crm")
    caplog.set_level(level, logger="aadi_crm")
    logger.addHandler(caplog.handler)
    return logger


def test_authentication_denial_is_logged_without_the_session_cookie(caplog) -> None:
    platform = FakePlatform()
    platform.access_by_tenant[str(TENANT_A)] = PlatformCallError(401)
    logger = _capture(caplog, logging.INFO)
    try:
        response = _client(platform).get(
            f"/api/v1/shell/tenants/{TENANT_A}",
            headers={"cookie": "aadi_session=super-secret-cookie", "x-request-id": "bad id"},
        )
    finally:
        logger.removeHandler(caplog.handler)
    assert response.status_code == 401
    request_id = response.headers["x-request-id"]
    assert request_id != "bad id"
    assert " " not in request_id
    assert "super-secret-cookie" not in caplog.text
    assert "status=401" in caplog.text
    assert request_id in caplog.text


def test_unhandled_error_hides_the_exception_text(caplog) -> None:
    application = create_app()

    @application.get("/api/v1/diagnostics-probe")
    def probe() -> None:
        raise RuntimeError("session=super-secret-cookie")

    logger = _capture(caplog, logging.ERROR)
    try:
        response = TestClient(application, raise_server_exceptions=False).get("/api/v1/diagnostics-probe")
    finally:
        logger.removeHandler(caplog.handler)
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "The request could not be completed."}
    }
    assert "Traceback" not in response.text
    assert "super-secret-cookie" not in response.text
    assert "super-secret-cookie" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert response.headers["x-request-id"]
