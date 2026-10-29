"""Server-side calls to the Control Plane. The CRM process does not issue sessions."""

from dataclasses import dataclass
from uuid import UUID

import httpx

PRODUCT_KEY = "crm"
_AUDIT_FIELDS = (
    "id",
    "occurred_at",
    "action",
    "resource_type",
    "resource_id",
    "summary",
    "outcome",
    "actor_user_id",
)


def _uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


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
    features: tuple[str, ...] = ()
    membership_id: str = ""


@dataclass(frozen=True)
class IdentityView:
    user_id: str
    email: str


@dataclass(frozen=True)
class TenantUserView:
    """Safe directory fields. Password and session data are never read."""

    user_id: str
    email: str
    identity_active: bool
    membership_status: str
    membership_id: str = ""


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
        features = payload.get("features")
        membership_id = payload.get("membership_id")
        if (
            not isinstance(tenant, str)
            or not isinstance(name, str)
            or not isinstance(product_name, str)
            or not isinstance(available, bool)
            or product_key != PRODUCT_KEY
            or not isinstance(features, list)
            or any(not isinstance(item, str) or not item.strip() for item in features)
            or not isinstance(membership_id, str)
            or not _uuid(membership_id)
        ):
            raise PlatformCallError(502)
        return ProductAccessView(
            tenant_id=tenant,
            tenant_name=name,
            product_name=product_name,
            available=available,
            features=tuple(item.strip() for item in features),
            membership_id=membership_id,
        )

    def permissions(self, tenant_id: str, cookie: str | None) -> list[str]:
        payload = self._get(f"/api/v1/tenants/{tenant_id}/permissions", cookie)
        if not isinstance(payload, list) or not all(isinstance(item, str) for item in payload):
            raise PlatformCallError(502)
        return payload

    def identity(self, cookie: str | None) -> IdentityView:
        payload = self._get("/api/v1/auth/me", cookie)
        if not isinstance(payload, dict):
            raise PlatformCallError(502)
        user_id = payload.get("id")
        email = payload.get("email")
        if not isinstance(user_id, str) or not isinstance(email, str) or not email.strip():
            raise PlatformCallError(502)
        try:
            UUID(user_id)
        except ValueError:
            raise PlatformCallError(502) from None
        return IdentityView(user_id=user_id, email=email)

    def list_product_members(self, tenant_id: str, cookie: str | None) -> list[TenantUserView]:
        """Forward the product member list. It does not require users.read."""

        payload = self._get(
            f"/api/v1/tenants/{tenant_id}/products/{PRODUCT_KEY}/members",
            cookie,
        )
        if not isinstance(payload, list):
            raise PlatformCallError(502)
        return [_product_member(item) for item in payload]

    def list_tenant_users(self, tenant_id: str, cookie: str | None) -> list[TenantUserView]:
        """Forward `GET /tenants/{id}/users`. The Control Plane requires `users.read`."""

        payload = self._get(f"/api/v1/tenants/{tenant_id}/users", cookie)
        if not isinstance(payload, list):
            raise PlatformCallError(502)
        return [_tenant_user(item) for item in payload]

    def get_tenant_user(self, tenant_id: str, user_id: str, cookie: str | None) -> TenantUserView:
        """Forward `GET /tenants/{id}/users/{user_id}`. Another tenant's user is 404."""

        payload = self._get(f"/api/v1/tenants/{tenant_id}/users/{user_id}", cookie)
        if not isinstance(payload, dict):
            raise PlatformCallError(502)
        user = _tenant_user(payload)
        if user.user_id != user_id:
            raise PlatformCallError(502)
        return user

    def list_audit_events(self, tenant_id: str, cookie: str | None, *, limit: int) -> list[dict[str, object]]:
        """Forward `GET /tenants/{id}/audit-events`. Metadata is not returned."""

        if limit < 1 or limit > 100:
            raise PlatformCallError(502)
        payload = self._get(f"/api/v1/tenants/{tenant_id}/audit-events?limit={limit}", cookie)
        if not isinstance(payload, list):
            raise PlatformCallError(502)
        return visible_audit_events(payload)

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


def _product_member(payload: object) -> TenantUserView:
    if not isinstance(payload, dict) or set(payload) != {"id", "email", "membership_id"}:
        raise PlatformCallError(502)
    user_id = payload.get("id")
    email = payload.get("email")
    membership_id = payload.get("membership_id")
    if (
        not isinstance(user_id, str)
        or not isinstance(email, str)
        or not email.strip()
        or not isinstance(membership_id, str)
        or not _uuid(user_id)
        or not _uuid(membership_id)
    ):
        raise PlatformCallError(502)
    return TenantUserView(
        user_id=user_id,
        email=email,
        identity_active=True,
        membership_status="active",
        membership_id=membership_id,
    )


def _tenant_user(payload: object) -> TenantUserView:
    if not isinstance(payload, dict):
        raise PlatformCallError(502)
    user_id = payload.get("id")
    email = payload.get("email")
    identity_active = payload.get("identity_active")
    membership_status = payload.get("membership_status")
    membership_id = payload.get("membership_id")
    if (
        not isinstance(user_id, str)
        or not isinstance(email, str)
        or not email.strip()
        or not isinstance(identity_active, bool)
        or membership_status not in {"active", "inactive"}
        or not isinstance(membership_id, str)
        or not _uuid(membership_id)
    ):
        raise PlatformCallError(502)
    try:
        UUID(user_id)
    except ValueError:
        raise PlatformCallError(502) from None
    return TenantUserView(
        user_id=user_id,
        email=email,
        identity_active=identity_active,
        membership_status=membership_status,
        membership_id=membership_id,
    )


def visible_audit_events(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        raise PlatformCallError(502)
    return [_audit_event(item) for item in payload]


def _audit_event(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise PlatformCallError(502)
    event_id = payload.get("id")
    occurred_at = payload.get("occurred_at")
    action = payload.get("action")
    resource_type = payload.get("resource_type")
    summary = payload.get("summary")
    outcome = payload.get("outcome")
    if (
        not isinstance(event_id, str)
        or not event_id.strip()
        or not isinstance(occurred_at, str)
        or not occurred_at.strip()
        or not isinstance(action, str)
        or not action.strip()
        or not isinstance(resource_type, str)
        or not resource_type.strip()
        or not isinstance(summary, str)
        or outcome not in {"success", "failure"}
    ):
        raise PlatformCallError(502)
    resource_id = payload.get("resource_id")
    actor_user_id = payload.get("actor_user_id")
    if resource_id is not None and not isinstance(resource_id, str):
        raise PlatformCallError(502)
    if actor_user_id is not None and not isinstance(actor_user_id, str):
        raise PlatformCallError(502)
    visible = {
        "id": event_id,
        "occurred_at": occurred_at,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "summary": summary[:500],
        "outcome": outcome,
        "actor_user_id": actor_user_id,
    }
    if set(visible) != set(_AUDIT_FIELDS):
        raise PlatformCallError(502)
    return visible
