"""CSV/XLSX import jobs and filtered record export.

The tenant, project, and actor come from the authenticated request. A column
named tenant or project in the file is ordinary cell text and is never used
as authorization context.
"""

import base64
import hashlib
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response

from app.api.projects import _body, _error, get_connection
from app.api.records import _UUID, _allowed, _archived, _calendar_date, _open, _validation
from app.api.shell import get_platform_client
from app.forms_store import get_form
from app.imports_store import ImportProblem, commit_job, create_job, error_report, export_rows, present_job, preview_job, save_decisions, save_mapping
from app.platform_client import PlatformClient
from app.project_access import SCOPE_ASSIGNED
from app.records_store import SOURCES, RecordListQuery, pipeline_status_param
from app.spreadsheets import SpreadsheetError, read_table, write_csv, write_xlsx

router = APIRouter(prefix="/api/v1", tags=["imports"])
_KEY = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def _problem(exc: ImportProblem) -> JSONResponse:
    if exc.status_code == 404:
        return _error(404)
    if exc.status_code == 409:
        return _error(409, exc.message)
    return _validation(exc.message)


def _assignee(access, caller) -> str | None:
    if access.record_scope() == SCOPE_ASSIGNED:
        return caller.user_id
    return None


def _can_read_job(access, caller, job: dict[str, object]) -> bool:
    if job.get("actor_user_id") == caller.user_id:
        return True
    return bool(access.tenant_admin or access.role == "project_manager")


def _guard(connection, tenant_id: str, project_id: str, caller, job: dict[str, object]) -> JSONResponse | None:
    row = connection.execute(
        "SELECT actor_user_id FROM import_jobs WHERE id = ? AND tenant_id = ? AND project_id = ?",
        (job["id"], tenant_id, project_id),
    ).fetchone()
    if row is None:
        return _error(404)
    viewed = dict(job)
    viewed["actor_user_id"] = row["actor_user_id"]
    if not _can_read_job(caller_access(connection, tenant_id, project_id, caller), caller, viewed):
        return _error(404)
    return None


def caller_access(connection, tenant_id: str, project_id: str, caller):
    from app.api.projects import record_access_for_project

    return record_access_for_project(connection, tenant_id, project_id, caller)


def _permit(connection, tenant_id: str, project_id: str, caller):
    def allowed(record_id: str, assignee_user_id: str | None) -> bool:
        return _allowed(connection, tenant_id, project_id, caller, assignee_user_id)

    return allowed


def _suggest(headers: list[str], fields: list[dict[str, object]]) -> dict[str, str | None]:
    used: set[str] = set()
    suggestion: dict[str, str | None] = {}
    for header in headers:
        match = None
        folded = header.casefold()
        for field in fields:
            key = str(field["field_key"])
            label = str(field.get("label") or "")
            if key in used:
                continue
            if folded in {key.casefold(), label.casefold()}:
                match = key
                break
        suggestion[header] = match
        if match:
            used.add(match)
    return suggestion


def _public(connection, tenant_id: str, project_id: str, caller, body: dict[str, object]) -> JSONResponse | dict[str, object]:
    denied = _guard(connection, tenant_id, project_id, caller, body)
    if denied is not None:
        return denied
    body["suggested_mapping"] = _suggest(list(body.get("headers") or []), list(body.get("fields") or []))
    body.pop("idempotency_key", None)
    return body


@router.post("/tenants/{tenant_id}/projects/{project_id}/imports")
async def post_import(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    if not _allowed(connection, str(tenant_id), str(project_id), caller, caller.user_id):
        return _error(403)
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    form_id = payload.get("form_id")
    if not isinstance(form_id, str) or not _UUID.fullmatch(form_id):
        return _validation("Choose a published form.")
    key = payload.get("idempotency_key")
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        return _validation("Choose an import key of 8 to 80 letters, numbers, hyphens, or underscores.")
    filename = payload.get("filename")
    if not isinstance(filename, str) or not filename.strip() or len(filename) > 200:
        return _validation("Choose a .csv or .xlsx file.")
    encoded = payload.get("content_base64")
    if not isinstance(encoded, str) or not encoded.strip():
        return _validation("The file contents are missing.")
    if len(encoded) > 2_000_000:
        return _validation("The file is larger than 1 MB.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except ValueError:
        return _validation("The file contents could not be read.")
    form = get_form(connection, str(tenant_id), str(project_id), form_id)
    if form is None or not form.current_published_version_id:
        return _error(409, "Publish this form before importing records.")
    try:
        _headers, parsed = read_table(filename.strip(), content)
    except SpreadsheetError as exc:
        return _validation(exc.message)
    digest = hashlib.sha256(content).hexdigest()
    try:
        body = create_job(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            form_id=form_id,
            form_version_id=form.current_published_version_id,
            actor_user_id=caller.user_id,
            idempotency_key=key,
            filename=filename.strip(),
            content_sha256=digest,
            parsed_rows=parsed,
        )
    except ImportProblem as exc:
        return _problem(exc)
    published = _public(connection, str(tenant_id), str(project_id), caller, body)
    if isinstance(published, JSONResponse):
        return published
    del access
    return JSONResponse(status_code=201, content=published)


@router.get("/tenants/{tenant_id}/projects/{project_id}/imports/{job_id}")
def read_import(
    tenant_id: UUID,
    project_id: UUID,
    job_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, _loaded = opened
    try:
        body = present_job(connection, str(tenant_id), str(project_id), str(job_id))
    except ImportProblem as exc:
        return _problem(exc)
    published = _public(connection, str(tenant_id), str(project_id), caller, body)
    if isinstance(published, JSONResponse):
        return published
    return JSONResponse(status_code=200, content=published)


@router.patch("/tenants/{tenant_id}/projects/{project_id}/imports/{job_id}/mapping")
async def patch_mapping(
    tenant_id: UUID,
    project_id: UUID,
    job_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, _access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    columns = payload.get("columns")
    if not isinstance(columns, dict):
        return _validation("Map every source column.")
    cleaned: dict[str, str | None] = {}
    for key, value in columns.items():
        if not isinstance(key, str) or not (value is None or isinstance(value, str)):
            return _validation("Map every source column.")
        cleaned[key] = value or None
    try:
        visible = _public(
            connection,
            str(tenant_id),
            str(project_id),
            caller,
            present_job(connection, str(tenant_id), str(project_id), str(job_id)),
        )
        if isinstance(visible, JSONResponse):
            return visible
        body = save_mapping(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            job_id=str(job_id),
            columns=cleaned,
        )
    except ImportProblem as exc:
        return _problem(exc)
    published = _public(connection, str(tenant_id), str(project_id), caller, body)
    if isinstance(published, JSONResponse):
        return published
    return JSONResponse(status_code=200, content=published)


@router.post("/tenants/{tenant_id}/projects/{project_id}/imports/{job_id}/preview")
def post_preview(
    tenant_id: UUID,
    project_id: UUID,
    job_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    try:
        visible = _public(
            connection,
            str(tenant_id),
            str(project_id),
            caller,
            present_job(connection, str(tenant_id), str(project_id), str(job_id)),
        )
        if isinstance(visible, JSONResponse):
            return visible
        body = preview_job(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            job_id=str(job_id),
            assignee_user_id=_assignee(access, caller),
            allowed=_permit(connection, str(tenant_id), str(project_id), caller),
        )
    except ImportProblem as exc:
        return _problem(exc)
    published = _public(connection, str(tenant_id), str(project_id), caller, body)
    if isinstance(published, JSONResponse):
        return published
    return JSONResponse(status_code=200, content=published)


@router.patch("/tenants/{tenant_id}/projects/{project_id}/imports/{job_id}/decisions")
async def patch_decisions(
    tenant_id: UUID,
    project_id: UUID,
    job_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, _access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    raw = payload.get("rows")
    if not isinstance(raw, list):
        return _validation("Choose a decision for each row that needs review.")
    decisions: dict[int, str] = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("row_number"), int) or not isinstance(item.get("decision"), str):
            return _validation("Choose accept as new, skip, or reject.")
        decisions[item["row_number"]] = item["decision"]
    try:
        visible = _public(
            connection,
            str(tenant_id),
            str(project_id),
            caller,
            present_job(connection, str(tenant_id), str(project_id), str(job_id)),
        )
        if isinstance(visible, JSONResponse):
            return visible
        body = save_decisions(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            job_id=str(job_id),
            decisions=decisions,
        )
    except ImportProblem as exc:
        return _problem(exc)
    published = _public(connection, str(tenant_id), str(project_id), caller, body)
    if isinstance(published, JSONResponse):
        return published
    return JSONResponse(status_code=200, content=published)


@router.post("/tenants/{tenant_id}/projects/{project_id}/imports/{job_id}/commit")
def post_commit(
    tenant_id: UUID,
    project_id: UUID,
    job_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open(tenant_id, project_id, request, platform, connection, write=True)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (project, access) = opened
    archived = _archived(project)
    if archived is not None:
        return archived
    if not _allowed(connection, str(tenant_id), str(project_id), caller, caller.user_id):
        return _error(403)
    try:
        visible = _public(
            connection,
            str(tenant_id),
            str(project_id),
            caller,
            present_job(connection, str(tenant_id), str(project_id), str(job_id)),
        )
        if isinstance(visible, JSONResponse):
            return visible
        body = commit_job(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            project_code=project.code,
            job_id=str(job_id),
            actor_user_id=caller.user_id,
            assignee_user_id=_assignee(access, caller),
            allowed=_permit(connection, str(tenant_id), str(project_id), caller),
        )
    except ImportProblem as exc:
        return _problem(exc)
    published = _public(connection, str(tenant_id), str(project_id), caller, body)
    if isinstance(published, JSONResponse):
        return published
    return JSONResponse(status_code=200, content=published)


@router.get("/tenants/{tenant_id}/projects/{project_id}/imports/{job_id}/errors")
def read_errors(
    tenant_id: UUID,
    project_id: UUID,
    job_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> Response:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, _loaded = opened
    try:
        body = present_job(connection, str(tenant_id), str(project_id), str(job_id))
        published = _public(connection, str(tenant_id), str(project_id), caller, body)
        if isinstance(published, JSONResponse):
            return published
        report = error_report(connection, str(tenant_id), str(project_id), str(job_id))
    except ImportProblem as exc:
        return _problem(exc)
    return Response(
        content=report.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="import-errors.csv"'},
    )


@router.get("/tenants/{tenant_id}/projects/{project_id}/record-exports")
def read_export(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
    file_format: str = Query(default="csv", alias="format"),
    q: str = "",
    form_id: str = "",
    source: str = "",
    created_from: str = "",
    created_to: str = "",
    status: str = "",
    sort: str = "created_at",
    direction: str = "desc",
) -> Response:
    opened = _open(tenant_id, project_id, request, platform, connection, write=False)
    if isinstance(opened, JSONResponse):
        return opened
    caller, (_project, access) = opened
    if file_format not in {"csv", "xlsx"}:
        return _validation("Choose a CSV or XLSX export.")
    if form_id and not _UUID.fullmatch(form_id):
        return _validation("Form filter is not valid.")
    if source and source not in SOURCES:
        return _validation("Source filter is not valid.")
    if created_from and not _calendar_date(created_from):
        return _validation("Created-from must use YYYY-MM-DD.")
    if created_to and not _calendar_date(created_to):
        return _validation("Created-to must use YYYY-MM-DD.")
    if created_from and created_to and created_from > created_to:
        return _validation("Created-from cannot be after created-to.")
    try:
        status = pipeline_status_param(status)
    except ValueError:
        return _validation("Status filter is not valid.")
    if sort not in {"created_at", "updated_at", "public_number"}:
        return _validation("Sort is not valid.")
    if direction not in {"asc", "desc"}:
        return _validation("Sort direction is not valid.")
    try:
        headers, matrix, count = export_rows(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            query=RecordListQuery(
                search=q.strip(),
                form_id=form_id,
                source=source,
                created_from=created_from,
                created_to=created_to,
                status=status,
                sort=sort,
                direction=direction,
                assignee_user_id=_assignee(access, caller),
            ),
            allowed=_permit(connection, str(tenant_id), str(project_id), caller),
        )
    except ImportProblem as exc:
        return _problem(exc)
    if file_format == "xlsx":
        payload = write_xlsx(headers, matrix)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "records.xlsx"
    else:
        payload = write_csv(headers, matrix)
        media = "text/csv; charset=utf-8"
        filename = "records.csv"
    return Response(
        content=payload,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-CRM-Export-Rows": str(count),
        },
    )
