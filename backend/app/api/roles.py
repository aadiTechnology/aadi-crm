"""Tenant role administration. Project membership does not grant these routes."""

import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.projects import Caller, get_connection
from app.api.shell import get_platform_client
from app.db import MissingTenantMembership
from app.platform_client import PlatformCallError, PlatformClient, TenantUserView
from app.project_access import SUPPORTED_CRM_PERMISSIONS
from app.roles_store import (
    DuplicateTenantRoleName,
    InactiveTenantRole,
    TenantRole,
    TenantRoleAssignment,
    assign_tenant_role,
    create_tenant_role,
    deactivate_tenant_role,
    get_tenant_role,
    grant_tenant_role_permission,
    list_role_assignments,
    list_tenant_roles,
    permission_granted,
    revoke_tenant_role_assignment,
    revoke_tenant_role_permission,
    update_tenant_role,
)

ROLES_MANAGE_PERMISSION = "roles.manage"
USERS_READ_PERMISSION = "users.read"
_NAME_MAX = 120
_DESCRIPTION_MAX = 2000
_SUPPORTED = frozenset(SUPPORTED_CRM_PERMISSIONS)

router = APIRouter(prefix="/api/v1", tags=["roles"])

_ERRORS = {
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have permission to perform this action."),
    404: ("RESOURCE_NOT_FOUND", "The requested resource was not found."),
    409: ("CONFLICT", "The request conflicts with the current state."),
    422: ("VALIDATION_ERROR", "Request validation failed."),
}


def _error(status_code: int, message: str | None = None) -> JSONResponse:
    if status_code in _ERRORS:
        code, default = _ERRORS[status_code]
        http_status = status_code
    else:
        code, default = ("INTERNAL_ERROR", "The platform request could not be completed.")
        http_status = 502
    return JSONResponse(
        status_code=http_status,
        content={"error": {"code": code, "message": message or default}},
    )


def _cookie(request: Request) -> str | None:
    header = request.headers.get("cookie")
    if header is None or not header.strip():
        return None
    return header


def _csrf_matches(request: Request) -> bool:
    cookie = request.cookies.get("aadi_csrf")
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or len(cookie) != len(header):
        return False
    return secrets.compare_digest(cookie, header)


def _membership_id(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    try:
        return str(UUID(text))
    except ValueError:
        return None


def _open_role_admin(
    tenant_id: UUID,
    request: Request,
    platform: PlatformClient,
    *,
    write: bool,
) -> Caller | JSONResponse:
    """Authorize a tenant administrator for this path tenant.

    The path tenant is a selector. Product access must return that same tenant
    and a current Control Plane membership id. ``roles.manage`` is the existing
    permission that administers tenant roles. A project role does not.
    """

    if write and not _csrf_matches(request):
        return _error(401)
    cookie = _cookie(request)
    try:
        access = platform.product_access(str(tenant_id), cookie)
    except PlatformCallError as exc:
        return _error(exc.status_code)
    if access.tenant_id != str(tenant_id):
        return _error(404)
    membership_id = _membership_id(access.membership_id)
    if membership_id is None:
        return _error(403, "This sign-in is not an active member of the organization.")
    try:
        keys = platform.permissions(str(tenant_id), cookie)
    except PlatformCallError as exc:
        return _error(exc.status_code)
    if ROLES_MANAGE_PERMISSION not in keys:
        return _error(403)
    try:
        identity = platform.identity(cookie)
    except PlatformCallError as exc:
        return _error(exc.status_code)
    return Caller(
        user_id=identity.user_id,
        email=identity.email,
        keys=keys,
        tenant_membership_id=membership_id,
    )


def _open_assignment_admin(
    tenant_id: UUID,
    request: Request,
    platform: PlatformClient,
    *,
    write: bool,
) -> Caller | JSONResponse:
    """Role administration plus the Control Plane directory permission.

    ``users.read`` is checked from the permission set the Control Plane already
    returned. The lookup route enforces that same key again. This does not
    treat a CRM role as a substitute for it.
    """

    opened = _open_role_admin(tenant_id, request, platform, write=write)
    if isinstance(opened, JSONResponse):
        return opened
    if USERS_READ_PERMISSION not in opened.keys:
        return _error(403)
    return opened


def _text(value: object, *, field: str, required: bool, max_length: int) -> str | JSONResponse:
    if not isinstance(value, str):
        return _error(422, "Request validation failed.")
    text = value.strip()
    if required and not text:
        return _error(422, f"{field} is required.")
    if len(text) > max_length:
        return _error(422, f"{field} is too long.")
    return text


def _name(value: object) -> str | JSONResponse:
    return _text(value, field="Role name", required=True, max_length=_NAME_MAX)


def _description(value: object) -> str | JSONResponse:
    return _text(value, field="Description", required=False, max_length=_DESCRIPTION_MAX)


def _user_id(value: object) -> str | JSONResponse:
    if not isinstance(value, str):
        return _error(422, "Request validation failed.")
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return _error(422, "User id must be a valid id.")


def _permission_key(value: object) -> str | JSONResponse:
    if not isinstance(value, str):
        return _error(422, "Request validation failed.")
    key = value.strip()
    if key not in _SUPPORTED:
        return _error(422, "That permission is not a supported CRM permission.")
    return key


async def _body(request: Request) -> dict[str, object] | JSONResponse:
    try:
        payload = await request.json()
    except ValueError:
        return _error(422)
    if not isinstance(payload, dict):
        return _error(422)
    return payload


def _role_response(role: TenantRole, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=role.as_dict())


def _catalog() -> list[str]:
    return sorted(SUPPORTED_CRM_PERMISSIONS)


@router.get("/tenants/{tenant_id}/crm-permissions")
def read_crm_permissions(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    return JSONResponse(status_code=200, content={"items": _catalog()})


@router.get("/tenants/{tenant_id}/roles")
def read_roles(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    roles = list_tenant_roles(connection, str(tenant_id))
    return JSONResponse(status_code=200, content={"items": [role.as_dict() for role in roles]})


@router.post("/tenants/{tenant_id}/roles")
async def post_role(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not set(payload).issubset({"name", "description"}):
        return _error(422)
    name = _name(payload.get("name", ""))
    if isinstance(name, JSONResponse):
        return name
    description = _description(payload.get("description", ""))
    if isinstance(description, JSONResponse):
        return description
    try:
        created = create_tenant_role(
            connection,
            tenant_id=str(tenant_id),
            name=name,
            description=description,
            actor_id=opened.user_id,
            tenant_membership_id=opened.tenant_membership_id,
        )
    except MissingTenantMembership:
        return _error(403, "This sign-in is not an active member of the organization.")
    except DuplicateTenantRoleName:
        return _error(409, "A role with this name already exists in this organization.")
    return _role_response(created, 201)


@router.patch("/tenants/{tenant_id}/roles/{role_id}")
async def patch_role(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not payload or not set(payload).issubset({"name", "description"}):
        return _error(422)
    name: str | None = None
    description: str | None = None
    if "name" in payload:
        parsed_name = _name(payload["name"])
        if isinstance(parsed_name, JSONResponse):
            return parsed_name
        name = parsed_name
    if "description" in payload:
        parsed_description = _description(payload["description"])
        if isinstance(parsed_description, JSONResponse):
            return parsed_description
        description = parsed_description
    try:
        updated = update_tenant_role(
            connection,
            tenant_id=str(tenant_id),
            role_id=str(role_id),
            name=name,
            description=description,
            actor_id=opened.user_id,
        )
    except DuplicateTenantRoleName:
        return _error(409, "A role with this name already exists in this organization.")
    if updated is None:
        return _error(404)
    return _role_response(updated, 200)


@router.post("/tenants/{tenant_id}/roles/{role_id}/deactivate")
def post_deactivate_role(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    deactivated = deactivate_tenant_role(
        connection,
        tenant_id=str(tenant_id),
        role_id=str(role_id),
        actor_id=opened.user_id,
    )
    if deactivated is None:
        return _error(404)
    return _role_response(deactivated, 200)


@router.get("/tenants/{tenant_id}/roles/{role_id}/permissions")
def read_role_permissions(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    role = get_tenant_role(connection, str(tenant_id), str(role_id))
    if role is None:
        return _error(404)
    return JSONResponse(status_code=200, content={"items": list(role.permissions)})


@router.post("/tenants/{tenant_id}/roles/{role_id}/permissions")
async def post_role_permission(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if set(payload) != {"permission_key"}:
        return _error(422)
    permission_key = _permission_key(payload.get("permission_key"))
    if isinstance(permission_key, JSONResponse):
        return permission_key
    try:
        granted = grant_tenant_role_permission(
            connection,
            tenant_id=str(tenant_id),
            role_id=str(role_id),
            permission_key=permission_key,
            actor_id=opened.user_id,
            tenant_membership_id=opened.tenant_membership_id,
        )
    except MissingTenantMembership:
        return _error(403, "This sign-in is not an active member of the organization.")
    except InactiveTenantRole:
        return _error(409, "This role is inactive.")
    if granted is None:
        return _error(404)
    return JSONResponse(status_code=200, content={"items": list(granted.permissions)})


@router.post("/tenants/{tenant_id}/roles/{role_id}/permissions/remove")
async def post_remove_role_permission(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_role_admin(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if set(payload) != {"permission_key"}:
        return _error(422)
    permission_key = _permission_key(payload.get("permission_key"))
    if isinstance(permission_key, JSONResponse):
        return permission_key
    if get_tenant_role(connection, str(tenant_id), str(role_id)) is None:
        return _error(404)
    if not permission_granted(connection, str(tenant_id), str(role_id), permission_key):
        return _error(404, "That permission is not granted to this role.")
    revoked = revoke_tenant_role_permission(
        connection,
        tenant_id=str(tenant_id),
        role_id=str(role_id),
        permission_key=permission_key,
    )
    if revoked is None:
        return _error(404)
    return JSONResponse(status_code=200, content={"items": list(revoked.permissions)})


def _assignment_response(assignment: TenantRoleAssignment, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=assignment.as_dict())


def _active_target(user: TenantUserView) -> JSONResponse | None:
    if not user.identity_active or user.membership_status != "active":
        return _error(422, "That user does not have an active organization membership.")
    if _membership_id(user.membership_id) is None:
        return _error(422, "That user does not have an active organization membership.")
    return None


@router.get("/tenants/{tenant_id}/roles/{role_id}/assignments")
def read_role_assignments(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_assignment_admin(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    if get_tenant_role(connection, str(tenant_id), str(role_id)) is None:
        return _error(404)
    items = list_role_assignments(connection, str(tenant_id), str(role_id))
    return JSONResponse(status_code=200, content={"items": [item.as_dict() for item in items]})


@router.post("/tenants/{tenant_id}/roles/{role_id}/assignments")
async def post_role_assignment(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_assignment_admin(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if set(payload) != {"user_id"}:
        return _error(422)
    user_id = _user_id(payload.get("user_id"))
    if isinstance(user_id, JSONResponse):
        return user_id
    try:
        user = platform.get_tenant_user(str(tenant_id), user_id, _cookie(request))
    except PlatformCallError as exc:
        if exc.status_code == 404:
            return _error(404, "That user is not a member of this organization.")
        return _error(exc.status_code)
    rejected = _active_target(user)
    if rejected is not None:
        return rejected
    try:
        stored = assign_tenant_role(
            connection,
            tenant_id=str(tenant_id),
            role_id=str(role_id),
            user_id=user.user_id,
            tenant_membership_id=user.membership_id,
            actor_id=opened.user_id,
        )
    except InactiveTenantRole:
        return _error(409, "This role is inactive.")
    if stored is None:
        return _error(404)
    assignment, created = stored
    return _assignment_response(assignment, 201 if created else 200)


@router.post("/tenants/{tenant_id}/roles/{role_id}/assignments/remove")
async def post_remove_role_assignment(
    tenant_id: UUID,
    role_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_assignment_admin(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if set(payload) != {"user_id"}:
        return _error(422)
    user_id = _user_id(payload.get("user_id"))
    if isinstance(user_id, JSONResponse):
        return user_id
    if get_tenant_role(connection, str(tenant_id), str(role_id)) is None:
        return _error(404)
    revoked = revoke_tenant_role_assignment(
        connection,
        tenant_id=str(tenant_id),
        role_id=str(role_id),
        user_id=user_id,
        actor_id=opened.user_id,
    )
    if revoked is None:
        return _error(404, "That user does not have this role.")
    return _assignment_response(revoked, 200)
