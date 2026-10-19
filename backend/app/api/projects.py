"""Tenant-scoped project routes. The path tenant id is only a selector."""

import re
import secrets
import sqlite3
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.shell import get_platform_client
from app.db import (
    DuplicateProjectCode,
    apply_migrations,
    archive_project,
    connect,
    create_project,
    database_path,
    get_project,
    list_projects,
    update_project,
)
from app.platform_client import PlatformCallError, PlatformClient

PROJECT_MANAGE_PERMISSION = "crm.project_management.manage"
REGISTERED_CRM_PERMISSION = "crm.lead_management.read"
_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
_NAME_MAX = 120
_DESCRIPTION_MAX = 2000
_QUERY_MAX = 100

router = APIRouter(prefix="/api/v1", tags=["projects"])

_ERRORS = {
    401: ("UNAUTHORIZED", "Authentication is required."),
    403: ("FORBIDDEN", "You do not have permission to perform this action."),
    404: ("RESOURCE_NOT_FOUND", "The requested resource was not found."),
    409: ("CONFLICT", "The request conflicts with the current state."),
    422: ("VALIDATION_ERROR", "Request validation failed."),
}


def get_connection() -> Iterator[sqlite3.Connection]:
    apply_migrations()
    connection = connect(database_path())
    try:
        yield connection
    finally:
        connection.close()


def project_management_allowed(keys: list[str]) -> bool:
    """Allow the sprint-plan key, or the only CRM key on the current registration.

    Product access alone is not project administration. Platform-only keys are not either.
    """

    return PROJECT_MANAGE_PERMISSION in keys or REGISTERED_CRM_PERMISSION in keys


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


def _authorize(
    tenant_id: UUID,
    request: Request,
    platform: PlatformClient,
    *,
    write: bool,
) -> JSONResponse | None:
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
    return None


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


async def _body(request: Request) -> dict[str, object] | JSONResponse:
    try:
        payload = await request.json()
    except ValueError:
        return _error(422)
    if not isinstance(payload, dict):
        return _error(422)
    return payload


@router.get("/tenants/{tenant_id}/projects")
def read_projects(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[sqlite3.Connection, Depends(get_connection)],
    q: str = "",
    status: str = "",
) -> JSONResponse:
    failure = _authorize(tenant_id, request, platform, write=False)
    if failure is not None:
        return failure
    query = q.strip()
    if len(query) > _QUERY_MAX or status not in {"", "active", "archived"}:
        return _error(422)
    items = list_projects(connection, str(tenant_id), query=query, status=status)
    return JSONResponse(status_code=200, content={"items": [item.as_dict() for item in items]})


@router.post("/tenants/{tenant_id}/projects")
async def post_project(
    tenant_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[sqlite3.Connection, Depends(get_connection)],
) -> JSONResponse:
    failure = _authorize(tenant_id, request, platform, write=True)
    if failure is not None:
        return failure
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
        identity = platform.identity(_cookie(request))
    except PlatformCallError as exc:
        return _error(exc.status_code)
    try:
        created = create_project(
            connection,
            tenant_id=str(tenant_id),
            code=code,
            name=name,
            description=description,
            created_by=identity.user_id,
        )
    except DuplicateProjectCode:
        return _error(409, "A project with this code already exists in this organization.")
    return JSONResponse(status_code=201, content=created.as_dict())


@router.get("/tenants/{tenant_id}/projects/{project_id}")
def read_project(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[sqlite3.Connection, Depends(get_connection)],
) -> JSONResponse:
    failure = _authorize(tenant_id, request, platform, write=False)
    if failure is not None:
        return failure
    project = get_project(connection, str(tenant_id), str(project_id))
    if project is None:
        return _error(404)
    return JSONResponse(status_code=200, content=project.as_dict())


@router.patch("/tenants/{tenant_id}/projects/{project_id}")
async def patch_project(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[sqlite3.Connection, Depends(get_connection)],
) -> JSONResponse:
    failure = _authorize(tenant_id, request, platform, write=True)
    if failure is not None:
        return failure
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
    return JSONResponse(status_code=200, content=updated.as_dict())


@router.post("/tenants/{tenant_id}/projects/{project_id}/archive")
def post_archive(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[sqlite3.Connection, Depends(get_connection)],
) -> JSONResponse:
    failure = _authorize(tenant_id, request, platform, write=True)
    if failure is not None:
        return failure
    archived = archive_project(connection, str(tenant_id), str(project_id))
    if archived is None:
        return _error(404)
    return JSONResponse(status_code=200, content=archived.as_dict())
