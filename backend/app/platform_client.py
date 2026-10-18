"""Server-side calls to the Control Plane. The CRM process does not issue sessions."""

from dataclasses import dataclass

import httpx

PRODUCT_KEY = "crm"


class PlatformCallError(Exception):
    """Control Plane status that the shell maps to a generic response."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"platform status {status_code}")


@dataclass(frozen=True)
class ProductAccessView:
    tenant_id: str
    tenant_name: str
    product_name: str
    available: bool


class PlatformClient:
    """Forwards the caller cookie. A tenant id in a CRM body is never sent."""

    def __init__(self, base_url: str, timeout_seconds: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def product_access(self, tenant_id: str, cookie: str | None) -> ProductAccessView:
        payload = self._get(
            f"/api/v1/tenants/{tenant_id}/products/{PRODUCT_KEY}/access",
            cookie,
        )
        tenant = payload.get("tenant_id")
        name = payload.get("tenant_name")
        product_name = payload.get("product_name")
        available = payload.get("available")
        product_key = payload.get("product_key")
        if (
            not isinstance(tenant, str)
            or not isinstance(name, str)
            or not isinstance(product_name, str)
            or not isinstance(available, bool)
            or product_key != PRODUCT_KEY
        ):
            raise PlatformCallError(502)
        return ProductAccessView(
            tenant_id=tenant,
            tenant_name=name,
            product_name=product_name,
            available=available,
        )

    def permissions(self, tenant_id: str, cookie: str | None) -> list[str]:
        payload = self._get(f"/api/v1/tenants/{tenant_id}/permissions", cookie)
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise PlatformCallError(502)
        return payload

    def _get(self, path: str, cookie: str | None) -> dict | list:
        headers = {}
        if cookie:
            headers["cookie"] = cookie
        try:
            response = httpx.get(
                f"{self._base_url}{path}",
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError:
            raise PlatformCallError(502) from None
        if response.status_code != 200:
            raise PlatformCallError(response.status_code)
        try:
            body = response.json()
        except ValueError:
            raise PlatformCallError(502) from None
        if not isinstance(body, (dict, list)):
            raise PlatformCallError(502)
        return body
