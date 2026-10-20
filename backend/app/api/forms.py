"""Project form definitions, draft preview, and immutable published versions."""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.projects import _body, _error, _load_project, _open_module, get_connection
from app.api.shell import get_platform_client
from app.form_versions import (
    DuplicatePublish,
    InvalidDraft,
    NoPublishedVersion,
    get_version,
    list_versions,
    publish_form,
    replace_draft_from_published,
)
from app.forms_store import (
    DuplicateFieldKey,
    DuplicateFormName,
    add_field,
    create_form,
    get_form,
    list_forms,
    remove_field,
    reorder_fields,
    update_field,
    update_form,
)
from app.platform_client import PlatformClient
from app.records_store import field_has_saved_values

router = APIRouter(prefix="/api/v1", tags=["forms"])

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_OPTION_VALUE = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^\d{2}:\d{2}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_EXTENSION = re.compile(r"^[a-z0-9]{1,10}$")
_PREFIX = re.compile(r"^[A-Za-z0-9]{0,12}$")
_MOBILE = re.compile(r"^\+?[0-9]{8,15}$")

_NAME_MAX = 120
_DESCRIPTION_MAX = 2000
_LABEL_MAX = 120
_HELP_MAX = 400
_SECTION_MAX = 80

FIELD_TYPES = (
    "text",
    "long_text",
    "number",
    "mobile",
    "email",
    "url",
    "date",
    "time",
    "dropdown",
    "multi_select",
    "radio",
    "checkbox",
    "currency",
    "file",
    "auto_number",
)
_PICKLIST = {"dropdown", "multi_select", "radio"}
_NO_DEFAULT = {"multi_select", "file", "auto_number"}
_TYPE_KEYS = {
    "text": {"max_length"},
    "long_text": {"max_length"},
    "number": {"min_value", "max_value"},
    "mobile": set(),
    "email": set(),
    "url": set(),
    "date": set(),
    "time": set(),
    "dropdown": {"options"},
    "multi_select": {"options"},
    "radio": {"options"},
    "checkbox": set(),
    "currency": {"currency_code", "min_value", "max_value"},
    "file": {"max_size_mb", "extensions"},
    "auto_number": {"prefix", "pad_width"},
}


def _open_form_project(tenant_id, project_id, request, platform, connection, *, write: bool, action: str):
    opened = _open_module(tenant_id, request, platform, write=write)
    if isinstance(opened, JSONResponse):
        return opened
    loaded = _load_project(connection, tenant_id, project_id, opened, action)
    if isinstance(loaded, JSONResponse):
        return loaded
    return opened


def _form_name(value: object) -> str | JSONResponse:
    if not isinstance(value, str) or not value.strip():
        return _error(422, "Form name is required.")
    name = value.strip()
    if len(name) > _NAME_MAX:
        return _error(422, "Form name is too long.")
    return name


def _form_description(value: object) -> str | JSONResponse:
    if not isinstance(value, str):
        return _error(422, "Request validation failed.")
    text = value.strip()
    if len(text) > _DESCRIPTION_MAX:
        return _error(422, "Description is too long.")
    return text


def _field_key(value: object) -> str | JSONResponse:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        return _error(422, "Field identifier must start with a letter and use lowercase letters, numbers, or underscores.")
    return value


def _optional_text(payload: dict, key: str, max_length: int, label: str) -> str | JSONResponse:
    if key not in payload:
        return ""
    value = payload[key]
    if not isinstance(value, str):
        return _error(422, "Request validation failed.")
    text = value.strip()
    if len(text) > max_length:
        return _error(422, f"{label} is too long.")
    return text


def _number(value: object, label: str) -> int | float | JSONResponse:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _error(422, f"{label} must be a number.")
    return value


def _whole(value: object, label: str, low: int, high: int) -> int | JSONResponse:
    if isinstance(value, bool) or not isinstance(value, int):
        return _error(422, f"{label} must be a whole number.")
    if value < low or value > high:
        return _error(422, f"{label} is outside the allowed range.")
    return value


def _options(value: object) -> list[dict[str, str]] | JSONResponse:
    if not isinstance(value, list) or not value or len(value) > 30:
        return _error(422, "This field type requires at least one picklist option.")
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"value", "label"}:
            return _error(422, "Each picklist option needs a value and a label.")
        option_value = item["value"]
        label = item["label"]
        if not isinstance(option_value, str) or not _OPTION_VALUE.fullmatch(option_value):
            return _error(422, "Picklist values must start with a letter and use lowercase letters, numbers, or underscores.")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 80:
            return _error(422, "Each picklist option needs a label.")
        if option_value in seen:
            return _error(422, "Picklist values must be unique.")
        seen.add(option_value)
        options.append({"value": option_value, "label": label.strip()})
    return options


def _default_for(field_type: str, value: object, config: dict[str, object]) -> object | JSONResponse:
    if field_type in _NO_DEFAULT:
        return _error(422, "This field type does not take a default value.")
    if field_type in {"text", "long_text"}:
        if not isinstance(value, str):
            return _error(422, "Default value must be text.")
        limit = config.get("max_length")
        if isinstance(limit, int) and len(value) > limit:
            return _error(422, "Default value is longer than the maximum length.")
        return value
    if field_type == "mobile":
        if not isinstance(value, str) or not _MOBILE.fullmatch(value):
            return _error(422, "Default mobile must contain 8 to 15 digits.")
        return value
    if field_type == "email":
        if not isinstance(value, str) or len(value) > 200 or not _EMAIL.fullmatch(value):
            return _error(422, "Default email is not valid.")
        return value
    if field_type == "url":
        if not isinstance(value, str) or len(value) > 500 or not value.startswith(("http://", "https://")):
            return _error(422, "Default URL must start with http:// or https://.")
        return value
    if field_type == "date":
        if not isinstance(value, str) or not _DATE.fullmatch(value):
            return _error(422, "Default date must use YYYY-MM-DD.")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return _error(422, "Default date must use YYYY-MM-DD.")
        return value
    if field_type == "time":
        if not isinstance(value, str) or not _TIME.fullmatch(value):
            return _error(422, "Default time must use HH:MM.")
        hour, minute = int(value[:2]), int(value[3:])
        if hour > 23 or minute > 59:
            return _error(422, "Default time must use HH:MM.")
        return value
    if field_type in {"number", "currency"}:
        parsed = _number(value, "Default value")
        if isinstance(parsed, JSONResponse):
            return parsed
        minimum = config.get("min_value")
        maximum = config.get("max_value")
        if isinstance(minimum, (int, float)) and parsed < minimum:
            return _error(422, "Default value is below the minimum.")
        if isinstance(maximum, (int, float)) and parsed > maximum:
            return _error(422, "Default value is above the maximum.")
        return parsed
    if field_type in {"dropdown", "radio"}:
        if not isinstance(value, str):
            return _error(422, "Default value must be one of the picklist values.")
        options = config.get("options")
        allowed = {item["value"] for item in options} if isinstance(options, list) else set()
        if value not in allowed:
            return _error(422, "Default value must be one of the picklist values.")
        return value
    if field_type == "checkbox":
        if not isinstance(value, bool):
            return _error(422, "Checkbox default must be true or false.")
        return value
    return _error(422, "Request validation failed.")


def _config_for(field_type: str, payload: dict) -> dict[str, object] | JSONResponse:
    config: dict[str, object] = {}
    if field_type in {"text", "long_text"} and "max_length" in payload:
        limit = 500 if field_type == "text" else 5000
        parsed = _whole(payload["max_length"], "Maximum length", 1, limit)
        if isinstance(parsed, JSONResponse):
            return parsed
        config["max_length"] = parsed
    if field_type in {"number", "currency"}:
        for key, label in (("min_value", "Minimum"), ("max_value", "Maximum")):
            if key not in payload:
                continue
            parsed = _number(payload[key], label)
            if isinstance(parsed, JSONResponse):
                return parsed
            config[key] = parsed
        minimum = config.get("min_value")
        maximum = config.get("max_value")
        if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float)) and minimum > maximum:
            return _error(422, "Minimum cannot be greater than maximum.")
    if field_type == "currency":
        code = payload.get("currency_code", "INR")
        if not isinstance(code, str) or not _CURRENCY.fullmatch(code):
            return _error(422, "Currency code must be three uppercase letters.")
        config["currency_code"] = code
    if field_type in _PICKLIST:
        parsed = _options(payload.get("options"))
        if isinstance(parsed, JSONResponse):
            return parsed
        config["options"] = parsed
    if field_type == "file":
        if "max_size_mb" in payload:
            parsed = _whole(payload["max_size_mb"], "Maximum file size", 1, 25)
            if isinstance(parsed, JSONResponse):
                return parsed
            config["max_size_mb"] = parsed
        if "extensions" in payload:
            extensions = payload["extensions"]
            if not isinstance(extensions, list) or len(extensions) > 12:
                return _error(422, "File extensions are not valid.")
            cleaned: list[str] = []
            for item in extensions:
                if not isinstance(item, str) or not _EXTENSION.fullmatch(item) or item in cleaned:
                    return _error(422, "File extensions are not valid.")
                cleaned.append(item)
            config["extensions"] = cleaned
    if field_type == "auto_number":
        prefix = payload.get("prefix", "")
        if not isinstance(prefix, str) or not _PREFIX.fullmatch(prefix):
            return _error(422, "Auto-number prefix must use letters or numbers.")
        pad = payload.get("pad_width", 4)
        parsed = _whole(pad, "Auto-number width", 1, 8)
        if isinstance(parsed, JSONResponse):
            return parsed
        config["prefix"] = prefix
        config["pad_width"] = parsed
    if "default_value" in payload and payload["default_value"] is not None:
        parsed = _default_for(field_type, payload["default_value"], config)
        if isinstance(parsed, JSONResponse):
            return parsed
        config["default_value"] = parsed
    return config


def _field_spec(payload: dict, *, creating: bool) -> dict[str, object] | JSONResponse:
    if not isinstance(payload, dict):
        return _error(422)
    field_type = payload.get("field_type")
    if not isinstance(field_type, str) or field_type not in FIELD_TYPES:
        return _error(422, "Field type is not supported.")
    allowed = {"label", "field_type", "required", "help_text", "section_name", "default_value"}
    allowed |= _TYPE_KEYS[field_type]
    if creating:
        allowed.add("field_key")
    elif "field_key" in payload:
        return _error(422, "Field identifier cannot be changed.")
    if not set(payload).issubset(allowed):
        return _error(422, "Request validation failed.")
    label = payload.get("label")
    if not isinstance(label, str) or not label.strip():
        return _error(422, "Field label is required.")
    if len(label.strip()) > _LABEL_MAX:
        return _error(422, "Field label is too long.")
    if not isinstance(payload.get("required"), bool):
        return _error(422, "Say whether the field is required.")
    help_text = _optional_text(payload, "help_text", _HELP_MAX, "Help text")
    if isinstance(help_text, JSONResponse):
        return help_text
    section_name = _optional_text(payload, "section_name", _SECTION_MAX, "Section")
    if isinstance(section_name, JSONResponse):
        return section_name
    config = _config_for(field_type, payload)
    if isinstance(config, JSONResponse):
        return config
    spec: dict[str, object] = {
        "label": label.strip(),
        "field_type": field_type,
        "required": payload["required"],
        "help_text": help_text,
        "section_name": section_name,
        "config": config,
    }
    if creating:
        key = _field_key(payload.get("field_key"))
        if isinstance(key, JSONResponse):
            return key
        spec["field_key"] = key
    return spec


@router.get("/tenants/{tenant_id}/projects/{project_id}/forms")
def read_forms(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=False, action="view_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    forms = list_forms(connection, str(tenant_id), str(project_id))
    return JSONResponse(status_code=200, content={"items": [form.as_dict() for form in forms]})


@router.post("/tenants/{tenant_id}/projects/{project_id}/forms")
async def post_form(
    tenant_id: UUID,
    project_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="manage_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if not set(payload).issubset({"name", "description"}):
        return _error(422)
    name = _form_name(payload.get("name"))
    if isinstance(name, JSONResponse):
        return name
    description = ""
    if "description" in payload:
        description = _form_description(payload["description"])
        if isinstance(description, JSONResponse):
            return description
    try:
        created = create_form(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            name=name,
            description=description,
            actor_id=opened.user_id,
        )
    except DuplicateFormName:
        return _error(409, "A form with this name already exists in the project.")
    return JSONResponse(status_code=201, content=created.as_dict())


@router.get("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}")
def read_form(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=False, action="view_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    form = get_form(connection, str(tenant_id), str(project_id), str(form_id))
    if form is None:
        return _error(404)
    return JSONResponse(status_code=200, content=form.as_dict())


@router.patch("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}")
async def patch_form(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="manage_forms"
    )
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
        parsed = _form_name(payload["name"])
        if isinstance(parsed, JSONResponse):
            return parsed
        name = parsed
    if "description" in payload:
        parsed = _form_description(payload["description"])
        if isinstance(parsed, JSONResponse):
            return parsed
        description = parsed
    try:
        updated = update_form(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            form_id=str(form_id),
            name=name,
            description=description,
            actor_id=opened.user_id,
        )
    except DuplicateFormName:
        return _error(409, "A form with this name already exists in the project.")
    if updated is None:
        return _error(404)
    return JSONResponse(status_code=200, content=updated.as_dict())


@router.post("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/fields")
async def post_field(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="manage_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    spec = _field_spec(payload, creating=True)
    if isinstance(spec, JSONResponse):
        return spec
    if get_form(connection, str(tenant_id), str(project_id), str(form_id)) is None:
        return _error(404)
    try:
        add_field(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            form_id=str(form_id),
            field_key=str(spec["field_key"]),
            label=str(spec["label"]),
            field_type=str(spec["field_type"]),
            required=bool(spec["required"]),
            help_text=str(spec["help_text"]),
            section_name=str(spec["section_name"]),
            config=spec["config"] if isinstance(spec["config"], dict) else {},
            actor_id=opened.user_id,
        )
    except DuplicateFieldKey:
        return _error(409, "Field identifier is already used on this form.")
    form = get_form(connection, str(tenant_id), str(project_id), str(form_id))
    if form is None:
        return _error(404)
    return JSONResponse(status_code=201, content=form.as_dict())


@router.patch("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/fields/{field_id}")
async def patch_field(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    field_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="manage_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    spec = _field_spec(payload, creating=False)
    if isinstance(spec, JSONResponse):
        return spec
    updated = update_field(
        connection,
        tenant_id=str(tenant_id),
        project_id=str(project_id),
        form_id=str(form_id),
        field_id=str(field_id),
        label=str(spec["label"]),
        field_type=str(spec["field_type"]),
        required=bool(spec["required"]),
        help_text=str(spec["help_text"]),
        section_name=str(spec["section_name"]),
        config=spec["config"] if isinstance(spec["config"], dict) else {},
        actor_id=opened.user_id,
    )
    if updated is None:
        return _error(404)
    form = get_form(connection, str(tenant_id), str(project_id), str(form_id))
    if form is None:
        return _error(404)
    return JSONResponse(status_code=200, content=form.as_dict())


@router.post("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/fields/reorder")
async def post_reorder(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="manage_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    payload = await _body(request)
    if isinstance(payload, JSONResponse):
        return payload
    if set(payload) != {"field_ids"} or not isinstance(payload["field_ids"], list):
        return _error(422, "Field order must include each field once.")
    field_ids: list[str] = []
    for item in payload["field_ids"]:
        if not isinstance(item, str):
            return _error(422, "Field order must include each field once.")
        try:
            field_ids.append(str(UUID(item)))
        except ValueError:
            return _error(422, "Field order must include each field once.")
    try:
        updated = reorder_fields(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            form_id=str(form_id),
            field_ids=field_ids,
            actor_id=opened.user_id,
        )
    except ValueError:
        return _error(422, "Field order must include each field once.")
    if updated is None:
        return _error(404)
    return JSONResponse(status_code=200, content=updated.as_dict())


@router.post("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/fields/{field_id}/remove")
def post_remove_field(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    field_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="manage_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    if field_has_saved_values(
        connection,
        tenant_id=str(tenant_id),
        project_id=str(project_id),
        form_id=str(form_id),
        field_id=str(field_id),
    ):
        return _error(409, "This field has saved record values and cannot be removed.")
    updated = remove_field(
        connection,
        tenant_id=str(tenant_id),
        project_id=str(project_id),
        form_id=str(form_id),
        field_id=str(field_id),
        actor_id=opened.user_id,
    )
    if updated is None:
        return _error(404)
    return JSONResponse(status_code=200, content=updated.as_dict())


def _scoped_form(connection, tenant_id: str, project_id: str, form_id: str):
    form = get_form(connection, tenant_id, project_id, form_id)
    if form is None:
        return _error(404)
    return form


@router.get("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/preview")
def read_preview(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=False, action="preview_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    form = _scoped_form(connection, str(tenant_id), str(project_id), str(form_id))
    if isinstance(form, JSONResponse):
        return form
    body = form.as_dict()
    return JSONResponse(
        status_code=200,
        content={
            "form_id": body["id"],
            "name": body["name"],
            "description": body["description"],
            "source": "draft",
            "fields": body["fields"],
        },
    )


@router.get("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/versions")
def read_versions(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=False, action="render_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    versions = list_versions(connection, str(tenant_id), str(project_id), str(form_id))
    if versions is None:
        return _error(404)
    return JSONResponse(status_code=200, content={"items": [version.as_dict() for version in versions]})


@router.post("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/versions")
def post_version(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="publish_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    try:
        published = publish_form(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            form_id=str(form_id),
            actor_id=opened.user_id,
        )
    except InvalidDraft as exc:
        return _error(422, exc.message)
    except DuplicatePublish:
        return _error(409, "This draft is already published.")
    if published is None:
        return _error(404)
    return JSONResponse(status_code=201, content=published.as_dict())


@router.get("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/versions/{version_id}")
def read_version(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    version_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=False, action="render_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    version = get_version(connection, str(tenant_id), str(project_id), str(form_id), str(version_id))
    if version is None:
        return _error(404)
    return JSONResponse(status_code=200, content=version.as_dict())


@router.post("/tenants/{tenant_id}/projects/{project_id}/forms/{form_id}/draft")
def post_draft_from_published(
    tenant_id: UUID,
    project_id: UUID,
    form_id: UUID,
    request: Request,
    platform: Annotated[PlatformClient, Depends(get_platform_client)],
    connection: Annotated[object, Depends(get_connection)],
) -> JSONResponse:
    opened = _open_form_project(
        tenant_id, project_id, request, platform, connection, write=True, action="publish_forms"
    )
    if isinstance(opened, JSONResponse):
        return opened
    try:
        updated = replace_draft_from_published(
            connection,
            tenant_id=str(tenant_id),
            project_id=str(project_id),
            form_id=str(form_id),
            actor_id=opened.user_id,
        )
    except NoPublishedVersion:
        return _error(409, "Publish a version before replacing the draft.")
    except InvalidDraft as exc:
        return _error(422, exc.message)
    except DuplicateFormName:
        return _error(409, "A form with this name already exists in the project.")
    if updated is None:
        return _error(404)
    return JSONResponse(status_code=200, content=updated.as_dict())
