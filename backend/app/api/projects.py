"""Tenant-scoped project routes. The path tenant id is only a selector."""

import re
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.shell import get_platform_client
from app.db import (
    DuplicateMembership,
    DuplicateProjectCode,
    InactiveMembership,
    LastProjectManager,
    MembershipRow,
    ProjectRow,
    active_membership,
    apply_migrations,
    archive_project,
    connect,
    connect_sqlite,
    create_project,
    resolve_database,
    get_project,
    grant_membership,
    list_project_memberships,
    list_projects,
    list_user_memberships,
    revoke_membership,
    set_membership_role,
    update_project,
)
from app.platform_client import PlatformCallError, PlatformClient, TenantUserView
from app.project_access import (
    PROJECT_MEMBER,
    PROJECT_MANAGER,
    ProjectAccess,
    RecordDecision,
    RecordRef,
    access_for,
    decide_record_access,
    module_allowed,
    tenant_project_admin,
)

_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
_NAME_MAX = 120
_DESCRIPTION_MAX = 2000
_QUERY_MAX = 100
_ROLES = {PROJECT_MANAGER, PROJECT_MEMBER}

router = APIRouter(prefix="/api/v1", tags=["projects"])

_ERRORS = {
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have permission to perform this action."),
    404: ("RESOURCE_NOT_FOUND", "The requested resource was not found."),
    409: ("CONFLICT", "The request conflicts with the current state."),
    422: ("VALIDATION_ERROR", "Request validation failed."),
}


@dataclass(frozen=True)
class Caller:
    user_id: str
    email: str
    keys: list[str]


def get_connection() -> Iterator:
    target = resolve_database()
    if target.dialect == "sqlite":
        apply_migrations(target.path)
        connection = connect_sqlite(target.path)
    else:
        connection = connect()
    try:
        yield connection
    finally:
        connection.close()


def project_management_allowed(keys: list[str]) -> bool:
    """Module entry only. Lead read does not administer every project."""

    return module_allowed(keys)


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


def _open_module(
    tenant_id: UUID,
    request: Request,
    platform: PlatformClient,
    *,
    write: bool,
) -> Caller | JSONResponse:
    if write and not _csrf_matches(request):
        return _error(401)
    cookie = _cookie(request)
    try:
        access = platform.product_access(str(tenant_id), cookie)
    except PlatformCallError as exc:
        return _error(exc.status_code)
    if access.tenant_id != str(tenant_id):
        return _error(404)
    if not access.available:
        return _error(403)
    try:
        keys = platform.permissions(str(tenant_id), cookie)
    except PlatformCallError as exc:
        return _error(exc.status_code)
    if not project_management_allowed(keys):
        return _error(403)
    try:
        identity = platform.identity(cookie)
    except PlatformCallError as exc:
        return _error(exc.status_code)
    return Caller(user_id=identity.user_id, email=identity.email, keys=keys)


def _project_body(project: ProjectRow, access: ProjectAccess) -> dict[str, object]:
    body: dict[str, object] = dict(project.as_dict())
    body["access"] = access.as_dict()
    return body


def _access_for_user(connection, tenant_id: str, project_id: str, caller: Caller) -> ProjectAccess:
    membership = active_membership(connection, tenant_id, project_id, caller.user_id)
    return access_for(
        role=None if membership is None else membership.role,
        status=None if membership is None else membership.status,
        permission_keys=caller.keys,
    )


def _load_project(
    connection,
    tenant_id: UUID,
    project_id: UUID,
    caller: Caller,
    action: str,
) -> tuple[ProjectRow, ProjectAccess] | JSONResponse:
    project = get_project(connection, str(tenant_id), str(project_id))
    if project is None:
        return _error(404)
    access = _access_for_user(connection, str(tenant_id), str(project_id), caller)
    if not access.allows("view_project"):
        return _error(404)
    if not access.allows(action):
        return _error(403)
    return project, access


def _text(value: object, *, field: str, required: bool, max_length: int) -> str | JSONResponse:
    if not isinstance(value, str):
        return _error(422, "Request validation failed.")
    text = value.strip()
    if required and not text:
        return _error(422, f"{field} is required.")
    if len(text) > max_length:
        return _error(422, f"{field} is too long.")
    return text


def _code(value: object) -> str | JSONResponse:
    text = _text(value, field="Project code", required=True, max_length=40)
    if isinstance(text, JSONResponse):
        return text
    if not _CODE.fullmatch(text):
        return _error(422, "Project code must use letters, numbers, hyphens, or underscores.")
    return text


def _name(value: object) -> str | JSONResponse:
    return _text(value, field="Project name", required=True, max_length=_NAME_MAX)


def _description(value: object) -> str | JSONResponse:
    return _text(value, field="Description", required=False, max_length=_DESCRIPTION_MAX)


def _user_id(value: object) -> str | JSONResponse:
    if not isinstance(value, str):
        return _error(422, "Request validation failed.")
    try:
        return str(UUID(value))
    except ValueError:
        return _error(422, "User id must be a valid id.")


def _role(value: object) -> str | JSONResponse:
    if not isinstance(value, str) or value not in _ROLES:
        return _error(422, "Project role must be project manager or project member.")
    return value


async def _body(request: Request) -> dict[str, object] | JSONResponse:
    try:
        payload = await request.json()
    except ValueError:
        return _error(422)
    if not isinstance(payload, dict):
        return _error(422)
    return payload


def _memberships_by_project(connection, tenant_id: str, user_id: str) -> dict[str, MembershipRow]:
    chosen: dict[str, MembershipRow] = {}
    for membership in list_user_memberships(connection, tenant_id, user_id):
        current = chosen.get(membership.project_id)
        if current is None or (current.status != "active" and membership.status == "active"):
            chosen[membership.project_id] = membership
    return chosen


def _member_email(member: MembershipRow, caller: Caller, emails: dict[str, str]) -> str | None:
    if member.user_id == caller.user_id:
        return caller.email
    return emails.get(member.user_id)


def _directory(
    platform: PlatformClient,
    tenant_id: UUID,
    request: Request,
) -> list[TenantUserView] | JSONResponse:
    try:
        return platform.list_tenant_users(str(tenant_id), _cookie(request))
    except PlatformCallError as exc:
        if exc.status_code == 403:
            return _error(403, "You cannot look up organization members with this sign-in.")
        return _error(exc.status_code)


def _lookup_user(
    platform: PlatformClient,
    tenant_id: UUID,
    user_id: str,
    request: Request,
) -> TenantUserView | JSONResponse:
    try:
        user = platform.get_tenant_user(str(tenant_id), user_id, _cookie(request))
    except PlatformCallError as exc:
        if exc.status_code == 403:
            return _error(403, "You cannot look up organization members with this sign-in.")
        if exc.status_code == 404:
            return _error(404, "That user is not a member of this organization.")
        return _error(exc.status_code)
    if user.user_id != user_id:
        return _error(404, "That user is not a member of this organization.")
    if not user.identity_active or user.membership_status != "active":
        return _error(422, "That user is not an active member of this organization.")
    return user


def _emails(
    platform: PlatformClient,
    tenant_id: UUID,
    request: Request,
) -> tuple[dict[str, str], bool] | JSONResponse:
    try:
        users = platform.list_tenant_users(str(tenant_id), _cookie(request))
    except PlatformCallError as exc:
        if exc.status_code == 401:
            return _error(401)
        return {}, False
    return {user.user_id: user.email for user in users}, True


@router.get("/tenants/{tenant_id}/projects")
def read_projects(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    q: str = "",
    status: str = "",
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    query = q.strip()
    if len(query) > _QUERY_MAX or status not in {"", "active", "archived"}:
        return _error(422)
    member_user_id = None if tenant_project_admin(opened.keys) else opened.user_id
    items = list_projects(
        connection,
        str(tenant_id),
        query=query,
        status=status,
        member_user_id=member_user_id,
    )
    owned = _memberships_by_project(connection, str(tenant_id), opened.user_id)
    payload = []
    for item in items:
        membership = owned.get(item.id)
        access = access_for(
            role=None if membership is None else membership.role,
            status=None if membership is None else membership.status,
            permission_keys=opened.keys,
        )
        payload.append(_project_body(item, access))
    return JSONResponse(status_code=200, content={"items": payload})


@router.post("/tenants/{tenant_id}/projects")
async def post_project(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not set(payload).issubset({"code", "name", "description"}):
        return _error(422)
    code = _code(payload.get("code", ""))
    if isinstance(code, JSONResponse):
        return code
    name = _name(payload.get("name", ""))
    if isinstance(name, JSONResponse):
        return name
    description = _description(payload.get("description", ""))
    if isinstance(description, JSONResponse):
        return description
    try:
        created = create_project(
            connection,
            tenant_id=str(tenant_id),
            code=code,
            name=name,
            description=description,
            created_by=opened.user_id,
        )
    except DuplicateProjectCode:
        return _error(409, "A project with this code already exists in this organization.")
    access = _access_for_user(connection, str(tenant_id), created.id, opened)
    return JSONResponse(status_code=201, content=_project_body(created, access))


@router.get("/tenants/{tenant_id}/projects/{project_id}")
def read_project(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "view_project")
    if isinstance(loaded, JSONResponse):
        return loaded
    project, access = loaded
    return JSONResponse(status_code=200, content=_project_body(project, access))


@router.patch("/tenants/{tenant_id}/projects/{project_id}")
async def patch_project(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "update_project")
    if isinstance(loaded, JSONResponse):
        return loaded
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not payload or not set(payload).issubset({"name", "description"}):
        return _error(422)
    name: str | None = None
    description: str | None = None
    if "name" in payload:
        parsed = _name(payload["name"])
        if isinstance(parsed, JSONResponse):
            return parsed
        name = parsed
    if "description" in payload:
        parsed = _description(payload["description"])
        if isinstance(parsed, JSONResponse):
            return parsed
        description = parsed
    updated = update_project(
        connection,
        str(tenant_id),
        str(project_id),
        name=name,
        description=description,
    )
    if updated is None:
        return _error(404)
    access = _access_for_user(connection, str(tenant_id), updated.id, opened)
    return JSONResponse(status_code=200, content=_project_body(updated, access))


@router.post("/tenants/{tenant_id}/projects/{project_id}/archive")
def post_archive(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "archive_project")
    if isinstance(loaded, JSONResponse):
        return loaded
    archived = archive_project(connection, str(tenant_id), str(project_id))
    if archived is None:
        return _error(404)
    access = _access_for_user(connection, str(tenant_id), archived.id, opened)
    return JSONResponse(status_code=200, content=_project_body(archived, access))


@router.get("/tenants/{tenant_id}/projects/{project_id}/members")
def read_members(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "list_members")
    if isinstance(loaded, JSONResponse):
        return loaded
    directory = _emails(platform, tenant_id, request)
    if isinstance(directory, JSONResponse):
        return directory
    emails, directory_available = directory
    items = [
        member.as_dict(email=_member_email(member, opened, emails))
        for member in list_project_memberships(connection, str(tenant_id), str(project_id))
    ]
    return JSONResponse(
        status_code=200,
        content={"items": items, "directory_available": directory_available},
    )


@router.get("/tenants/{tenant_id}/projects/{project_id}/eligible-users")
def read_eligible_users(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "add_member")
    if isinstance(loaded, JSONResponse):
        return loaded
    directory = _directory(platform, tenant_id, request)
    if isinstance(directory, JSONResponse):
        return directory
    active_ids = {
        member.user_id
        for member in list_project_memberships(connection, str(tenant_id), str(project_id))
        if member.status == "active"
    }
    items = [
        {"id": user.user_id, "email": user.email}
        for user in sorted(directory, key=lambda user: user.email.lower())
        if user.identity_active and user.membership_status == "active" and user.user_id not in active_ids
    ]
    return JSONResponse(status_code=200, content={"items": items})


@router.post("/tenants/{tenant_id}/projects/{project_id}/members")
async def post_member(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "add_member")
    if isinstance(loaded, JSONResponse):
        return loaded
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not set(payload).issubset({"user_id", "role"}):
        return _error(422)
    user_id = _user_id(payload.get("user_id", ""))
    if isinstance(user_id, JSONResponse):
        return user_id
    role = _role(payload.get("role", ""))
    if isinstance(role, JSONResponse):
        return role
    user = _lookup_user(platform, tenant_id, user_id, request)
    if isinstance(user, JSONResponse):
        return user
    try:
        created = grant_membership(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            user_id=user_id,
            role=role,
            actor_id=opened.user_id,
        )
    except DuplicateMembership:
        return _error(409, "This user is already a member of this project.")
    if created is None:
        return _error(404)
    return JSONResponse(status_code=201, content=created.as_dict(email=user.email))


@router.patch("/tenants/{tenant_id}/projects/{project_id}/members/{membership_id}")
async def patch_member(
    tenant_id: UUID,
    project_id: UUID,
    membership_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "assign_role")
    if isinstance(loaded, JSONResponse):
        return loaded
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if set(payload) != {"role"}:
        return _error(422)
    role = _role(payload.get("role"))
    if isinstance(role, JSONResponse):
        return role
    try:
        updated = set_membership_role(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            membership_id=str(membership_id),
            role=role,
            actor_id=opened.user_id,
        )
    except InactiveMembership:
        return _error(409, "This membership is not active.")
    except LastProjectManager:
        return _error(409, "This project needs an active project manager.")
    if updated is None:
        return _error(404)
    return JSONResponse(status_code=200, content=updated.as_dict(email=None))


@router.post("/tenants/{tenant_id}/projects/{project_id}/members/{membership_id}/remove")
def post_remove_member(
    tenant_id: UUID,
    project_id: UUID,
    membership_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_module(tenant_id, request, platform, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, "remove_member")
    if isinstance(loaded, JSONResponse):
        return loaded
    try:
        removed = revoke_membership(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            membership_id=str(membership_id),
            actor_id=opened.user_id,
        )
    except LastProjectManager:
        return _error(409, "This project needs an active project manager.")
    if removed is None:
        return _error(404)
    return JSONResponse(status_code=200, content=removed.as_dict(email=None))


def record_access_for_project(connection, tenant_id: str, project_id: str, caller: Caller) -> ProjectAccess:
    """Membership loaded for this request. Record routes must not cache it."""

    return _access_for_user(connection, tenant_id, project_id, caller)


def authorize_record(
    connection,
    *,
    tenant_id: str,
    project_id: str,
    caller: Caller,
    record: RecordRef,
) -> RecordDecision:
    """Policy a future record route must call. No record module exists yet."""

    access = record_access_for_project(connection, tenant_id, project_id, caller)
    return decide_record_access(
        caller_user_id=caller.user_id,
        authorized_tenant_id=tenant_id,
        authorized_project_id=project_id,
        access=access,
        record=record,
    )
