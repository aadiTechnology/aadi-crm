"""CRM records bound to one immutable published form version.

A new record uses the form's current published version. Later edits keep that
same version. Draft edits and newer publications do not rewrite stored values.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.form_versions import get_version
from app.forms_store import get_form

SOURCES = {
    "manual": "Manual",
    "website": "Website",
    "phone_call": "Phone Call",
    "justdial": "JustDial",
    "meta_ad": "Meta Ad",
    "referral": "Referral",
    "import": "Import",
    "other": "Other",
}
_SORTS = {"created_at": "created_at", "updated_at": "updated_at", "public_number": "public_number"}
_TEXT = {"text", "long_text", "email", "url", "mobile", "date", "time"}
_PICKLIST = {"dropdown", "multi_select", "radio"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^\d{2}:\d{2}$")
_MOBILE = re.compile(r"^\+?[0-9]{8,15}$")
_RECORD_COLUMNS = (
    "id, tenant_id, project_id, form_id, form_version_id, public_number, sequence, "
    "display_name, search_text, source, assignee_user_id, created_by, updated_by, "
    "created_at, updated_at, captured_at, deleted_at"
)


class RecordValidation(Exception):
    """Field values do not match the published schema."""

    def __init__(self, message: str, fields: dict[str, str] | None = None) -> None:
        self.message = message
        self.fields = fields or {}
        super().__init__(message)


class UnpublishedForm(Exception):
    """The form has no published version a record can use."""

    def __init__(self) -> None:
        self.message = "Publish this form before creating a record."
        super().__init__(self.message)


class StaleRecord(Exception):
    """Another update was stored after this edit was loaded."""

    def __init__(self) -> None:
        self.message = "This record was updated. Reload it and try again."
        super().__init__(self.message)


@dataclass(frozen=True)
class RecordListQuery:
    search: str = ""
    form_id: str = ""
    source: str = ""
    created_from: str = ""
    created_to: str = ""
    sort: str = "created_at"
    direction: str = "desc"
    limit: int = 25
    offset: int = 0
    assignee_user_id: str | None = None


def field_has_saved_values(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    field_id: str,
) -> bool:
    """True when a stored record still has a value for this draft field."""

    row = connection.execute(
        """
        SELECT field_key FROM form_fields
        WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
        """,
        (tenant_id, project_id, form_id, field_id),
    ).fetchone()
    if row is None:
        return False
    used = connection.execute(
        """
        SELECT 1
        FROM record_values
        WHERE tenant_id = ? AND project_id = ? AND field_key = ?
          AND record_id IN (
              SELECT id FROM records
              WHERE tenant_id = ? AND project_id = ? AND form_id = ?
          )
        LIMIT 1
        """,
        (tenant_id, project_id, row["field_key"], tenant_id, project_id, form_id),
    ).fetchone()
    return used is not None


def create_record(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    project_code: str,
    form_id: str,
    actor_id: str,
    source: str,
    values: dict[str, object],
) -> dict[str, object] | None:
    """Insert one record on the form's current published version.

    The record number is chosen inside an immediate transaction. The caller is
    stored as the assignee so the existing assigned-record policy can authorize
    the creator. Reassignment is not part of this store.
    """

    previous = connection.isolation_level
    connection.isolation_level = None
    record_id = str(uuid4())
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        try:
            form = get_form(connection, tenant_id, project_id, form_id)
            if form is None:
                connection.rollback()
                return None
            if not form.current_published_version_id:
                raise UnpublishedForm
            version = get_version(
                connection,
                tenant_id,
                project_id,
                form_id,
                form.current_published_version_id,
            )
            if version is None:
                raise UnpublishedForm
            cleaned = validate_values(version.schema, values)
            now = _now()
            sequence = _next_sequence(connection, project_id)
            public_number = f"{project_code}-{sequence:04d}"
            display_name = _display_name(version.schema, cleaned, public_number)
            search_text = _search_text(version.schema, cleaned, public_number, display_name, source)
            connection.execute(
                f"""
                INSERT INTO records ({_RECORD_COLUMNS})
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    record_id,
                    tenant_id,
                    project_id,
                    form_id,
                    version.id,
                    public_number,
                    sequence,
                    display_name,
                    search_text,
                    source,
                    actor_id,
                    actor_id,
                    actor_id,
                    now,
                    now,
                    now,
                ),
            )
            _insert_values(connection, record_id, tenant_id, project_id, cleaned)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.isolation_level = previous
    return get_record(connection, tenant_id, project_id, record_id)


def list_records(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    query: RecordListQuery,
) -> tuple[list[dict[str, object]], int]:
    clauses = ["records.tenant_id = ?", "records.project_id = ?", "records.deleted_at IS NULL"]
    params: list[object] = [tenant_id, project_id]
    if query.assignee_user_id is not None:
        clauses.append("records.assignee_user_id = ?")
        params.append(query.assignee_user_id)
    if query.form_id:
        clauses.append("records.form_id = ?")
        params.append(query.form_id)
    if query.source:
        clauses.append("records.source = ?")
        params.append(query.source)
    if query.created_from:
        clauses.append("substr(records.created_at, 1, 10) >= ?")
        params.append(query.created_from)
    if query.created_to:
        clauses.append("substr(records.created_at, 1, 10) <= ?")
        params.append(query.created_to)
    if query.search:
        clauses.append("records.search_text LIKE ? ESCAPE '\\'")
        params.append(_like(query.search))
    where = " AND ".join(clauses)
    sort = _SORTS[query.sort]
    direction = "ASC" if query.direction == "asc" else "DESC"
    total_row = connection.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM records
        JOIN form_versions
          ON form_versions.id = records.form_version_id
         AND form_versions.tenant_id = records.tenant_id
         AND form_versions.project_id = records.project_id
        WHERE {where}
        """,
        params,
    ).fetchone()
    total = int(total_row["count"]) if total_row is not None else 0
    rows = connection.execute(
        f"""
        SELECT records.id, records.form_id, records.form_version_id, records.public_number,
               records.display_name, records.source, records.created_at, records.updated_at,
               records.assignee_user_id, form_versions.version_number, form_versions.schema_json
        FROM records
        JOIN form_versions
          ON form_versions.id = records.form_version_id
         AND form_versions.tenant_id = records.tenant_id
         AND form_versions.project_id = records.project_id
        WHERE {where}
        ORDER BY records.{sort} {direction}, records.id
        LIMIT ? OFFSET ?
        """,
        [*params, query.limit, query.offset],
    ).fetchall()
    values = _values_for(connection, [row["id"] for row in rows])
    items = [_list_item(row, values.get(row["id"], {})) for row in rows]
    return items, total


def get_record(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    record_id: str,
) -> dict[str, object] | None:
    row = connection.execute(
        f"""
        SELECT {_RECORD_COLUMNS}
        FROM records
        WHERE tenant_id = ? AND project_id = ? AND id = ? AND deleted_at IS NULL
        """,
        (tenant_id, project_id, record_id),
    ).fetchone()
    if row is None:
        return None
    version = get_version(connection, tenant_id, project_id, row["form_id"], row["form_version_id"])
    if version is None:
        return None
    stored = _values_for(connection, [record_id]).get(record_id, {})
    form = get_form(connection, tenant_id, project_id, row["form_id"])
    draft_keys = {field.field_key for field in form.fields} if form is not None else set()
    return _detail(row, version.schema, version.version_number, stored, draft_keys)


def update_record(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    actor_id: str,
    expected_updated_at: str,
    values: dict[str, object],
) -> dict[str, object] | None:
    """Replace values without changing the original form version."""

    previous = connection.isolation_level
    connection.isolation_level = None
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                f"""
                SELECT {_RECORD_COLUMNS}
                FROM records
                WHERE tenant_id = ? AND project_id = ? AND id = ? AND deleted_at IS NULL
                """,
                (tenant_id, project_id, record_id),
            ).fetchone()
            if row is None:
                connection.rollback()
                return None
            if row["updated_at"] != expected_updated_at:
                raise StaleRecord
            version = get_version(connection, tenant_id, project_id, row["form_id"], row["form_version_id"])
            if version is None:
                connection.rollback()
                return None
            cleaned = validate_values(version.schema, values)
            now = _now()
            display_name = _display_name(version.schema, cleaned, row["public_number"])
            search_text = _search_text(
                version.schema,
                cleaned,
                row["public_number"],
                display_name,
                row["source"],
            )
            connection.execute(
                """
                DELETE FROM record_values
                WHERE record_id = ? AND tenant_id = ? AND project_id = ?
                """,
                (record_id, tenant_id, project_id),
            )
            _insert_values(connection, record_id, tenant_id, project_id, cleaned)
            connection.execute(
                """
                UPDATE records
                SET display_name = ?, search_text = ?, updated_by = ?, updated_at = ?
                WHERE tenant_id = ? AND project_id = ? AND id = ? AND deleted_at IS NULL
                """,
                (display_name, search_text, actor_id, now, tenant_id, project_id, record_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.isolation_level = previous
    return get_record(connection, tenant_id, project_id, record_id)


def archive_record(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    record_id: str,
    actor_id: str,
    expected_updated_at: str,
) -> bool:
    """Hide a record. The row and its values stay for the original form version."""

    previous = connection.isolation_level
    connection.isolation_level = None
    try:
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                """
                SELECT updated_at FROM records
                WHERE tenant_id = ? AND project_id = ? AND id = ? AND deleted_at IS NULL
                """,
                (tenant_id, project_id, record_id),
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            if row["updated_at"] != expected_updated_at:
                raise StaleRecord
            now = _now()
            connection.execute(
                """
                UPDATE records
                SET deleted_at = ?, updated_by = ?, updated_at = ?
                WHERE tenant_id = ? AND project_id = ? AND id = ? AND deleted_at IS NULL
                """,
                (now, actor_id, now, tenant_id, project_id, record_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.isolation_level = previous
    return True


def validate_values(schema: dict[str, object], values: dict[str, object]) -> dict[str, object]:
    fields = _schema_fields(schema)
    known = {str(field["field_key"]) for field in fields}
    errors: dict[str, str] = {}
    for key in values:
        if key not in known:
            errors[key] = "This field is not part of this form version."
    cleaned: dict[str, object] = {}
    for field in fields:
        key = str(field["field_key"])
        label = str(field.get("label") or key)
        field_type = str(field.get("field_type") or "")
        required = field.get("required") is True
        raw = values.get(key, None)
        present = key in values and raw is not None and raw != ""
        if field_type in {"file", "auto_number"}:
            if present:
                errors[key] = (
                    "File upload is not available."
                    if field_type == "file"
                    else "Auto-number is not issued on a record."
                )
            elif required:
                errors[key] = (
                    "File upload is not available."
                    if field_type == "file"
                    else "Auto-number is not issued on a record."
                )
            continue
        if field_type == "checkbox":
            if key not in values:
                if required:
                    errors[key] = f"{label} is required."
                else:
                    cleaned[key] = False
                continue
            if not isinstance(raw, bool):
                errors[key] = f"{label} must be true or false."
                continue
            if required and raw is not True:
                errors[key] = f"{label} is required."
                continue
            cleaned[key] = raw
            continue
        if field_type == "multi_select" and isinstance(raw, list) and not raw:
            if required:
                errors[key] = f"{label} is required."
            continue
        if field_type == "multi_select":
            if not present:
                if required:
                    errors[key] = f"{label} is required."
                continue
            parsed = _multi(raw, field, label)
            if isinstance(parsed, str):
                errors[key] = parsed
            else:
                cleaned[key] = parsed
            continue
        if field_type in {"number", "currency"}:
            if not present:
                if required:
                    errors[key] = f"{label} is required."
                continue
            parsed = _number_value(raw, field, label)
            if isinstance(parsed, str):
                errors[key] = parsed
            else:
                cleaned[key] = parsed
            continue
        if field_type not in _TEXT and field_type not in {"dropdown", "radio"}:
            errors[key] = "Field type is not supported."
            continue
        if not present:
            if required:
                errors[key] = f"{label} is required."
            continue
        if not isinstance(raw, str):
            errors[key] = f"{label} must be text."
            continue
        text = raw.strip()
        if not text:
            if required:
                errors[key] = f"{label} is required."
            continue
        problem = _text_problem(field_type, text, field, label)
        if problem is not None:
            errors[key] = problem
            continue
        cleaned[key] = text
    if errors:
        message = next(iter(errors.values())) if len(errors) == 1 else "Some fields need attention."
        raise RecordValidation(message, errors)
    return cleaned


def _schema_fields(schema: dict[str, object]) -> list[dict[str, object]]:
    raw = schema.get("fields")
    if not isinstance(raw, list):
        raise RecordValidation("This form version cannot be used.")
    fields: list[dict[str, object]] = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("field_key"), str):
            raise RecordValidation("This form version cannot be used.")
        fields.append(item)
    return sorted(fields, key=lambda item: item.get("position") if isinstance(item.get("position"), int) else 0)


def _text_problem(field_type: str, text: str, field: dict[str, object], label: str) -> str | None:
    limit = field.get("max_length")
    default_limit = 5000 if field_type == "long_text" else 500
    cap = limit if isinstance(limit, int) and not isinstance(limit, bool) else default_limit
    if field_type in {"text", "long_text"} and len(text) > cap:
        return f"{label} is too long."
    if field_type == "email" and (len(text) > 200 or not _EMAIL.fullmatch(text)):
        return f"{label} must be an email address."
    if field_type == "url" and (len(text) > 500 or not text.startswith(("http://", "https://"))):
        return f"{label} must start with http:// or https://."
    if field_type == "mobile" and not _MOBILE.fullmatch(text):
        return f"{label} must contain 8 to 15 digits."
    if field_type == "date":
        if not _DATE.fullmatch(text):
            return f"{label} must use YYYY-MM-DD."
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError:
            return f"{label} must use YYYY-MM-DD."
    if field_type == "time":
        if not _TIME.fullmatch(text):
            return f"{label} must use HH:MM."
        hour, minute = int(text[:2]), int(text[3:])
        if hour > 23 or minute > 59:
            return f"{label} must use HH:MM."
    if field_type in {"dropdown", "radio"} and text not in _option_values(field):
        return f"{label} must use one of the listed options."
    return None


def _number_value(raw: object, field: dict[str, object], label: str) -> float | int | str:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return f"{label} must be a number."
    if isinstance(raw, float) and not math.isfinite(raw):
        return f"{label} must be a number."
    minimum = field.get("min_value")
    maximum = field.get("max_value")
    if isinstance(minimum, (int, float)) and not isinstance(minimum, bool) and raw < minimum:
        return f"{label} is below the minimum."
    if isinstance(maximum, (int, float)) and not isinstance(maximum, bool) and raw > maximum:
        return f"{label} is above the maximum."
    return raw


def _multi(raw: object, field: dict[str, object], label: str) -> list[str] | str:
    if not isinstance(raw, list) or not raw:
        return f"{label} is required." if field.get("required") is True else f"{label} must use the listed options."
    allowed = _option_values(field)
    chosen: list[str] = []
    for item in raw:
        if not isinstance(item, str) or item not in allowed or item in chosen:
            return f"{label} must use the listed options."
        chosen.append(item)
    return chosen


def _option_values(field: dict[str, object]) -> set[str]:
    options = field.get("options")
    if not isinstance(options, list):
        return set()
    return {
        item["value"]
        for item in options
        if isinstance(item, dict) and isinstance(item.get("value"), str)
    }


def _option_label(field: dict[str, object], value: str) -> str:
    options = field.get("options")
    if isinstance(options, list):
        for item in options:
            if isinstance(item, dict) and item.get("value") == value and isinstance(item.get("label"), str):
                return item["label"]
    return value


def _display_name(schema: dict[str, object], values: dict[str, object], public_number: str) -> str:
    for field in _schema_fields(schema):
        if field.get("field_type") not in {"text", "long_text"}:
            continue
        value = values.get(str(field["field_key"]))
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    return public_number


def _search_text(
    schema: dict[str, object],
    values: dict[str, object],
    public_number: str,
    display_name: str,
    source: str,
) -> str:
    parts = [public_number, display_name, SOURCES.get(source, source)]
    fields = {str(field["field_key"]): field for field in _schema_fields(schema)}
    for key, value in values.items():
        field = fields.get(key)
        if field is None:
            continue
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
            parts.extend(_option_label(field, str(item)) for item in value)
        elif isinstance(value, bool):
            parts.append("yes" if value else "no")
        else:
            parts.append(str(value))
            if field.get("field_type") in _PICKLIST:
                parts.append(_option_label(field, str(value)))
    return " ".join(part.lower() for part in parts if part)[:8000]


def _summary(schema: dict[str, object], values: dict[str, object]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for field in _schema_fields(schema):
        key = str(field["field_key"])
        if key not in values or field.get("field_type") in {"file", "auto_number"}:
            continue
        shown = _shown(field, values[key])
        if not shown:
            continue
        label = field.get("label")
        items.append({"label": label if isinstance(label, str) else key, "value": shown})
        if len(items) == 3:
            break
    return items


def _shown(field: dict[str, object], value: object) -> str:
    field_type = field.get("field_type")
    if field_type == "checkbox":
        return "Yes" if value is True else "No"
    if field_type in {"dropdown", "radio"} and isinstance(value, str):
        return _option_label(field, value)
    if field_type == "multi_select" and isinstance(value, list):
        return ", ".join(_option_label(field, item) for item in value if isinstance(item, str))
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _list_item(row: sqlite3.Row, values: dict[str, object]) -> dict[str, object]:
    schema = _load_schema(row["schema_json"])
    name = schema.get("name")
    return {
        "id": row["id"],
        "public_number": row["public_number"],
        "form_id": row["form_id"],
        "form_name": name if isinstance(name, str) else "",
        "form_version_id": row["form_version_id"],
        "version_number": int(row["version_number"]),
        "display_name": row["display_name"],
        "source": row["source"],
        "source_label": SOURCES.get(row["source"], row["source"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "assignee_user_id": row["assignee_user_id"],
        "summary": _summary(schema, values),
    }


def _detail(
    row: sqlite3.Row,
    schema: dict[str, object],
    version_number: int,
    values: dict[str, object],
    draft_keys: set[str],
) -> dict[str, object]:
    fields = _schema_fields(schema)
    name = schema.get("name")
    description = schema.get("description")
    absent = [
        {"field_key": str(field["field_key"]), "label": str(field.get("label") or field["field_key"])}
        for field in fields
        if str(field["field_key"]) not in draft_keys
    ]
    known = {str(field["field_key"]) for field in fields}
    unmapped = [{"field_key": key, "value": value} for key, value in values.items() if key not in known]
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "project_id": row["project_id"],
        "form_id": row["form_id"],
        "form_version_id": row["form_version_id"],
        "version_number": version_number,
        "form_name": name if isinstance(name, str) else "",
        "form_description": description if isinstance(description, str) else "",
        "public_number": row["public_number"],
        "display_name": row["display_name"],
        "source": row["source"],
        "source_label": SOURCES.get(row["source"], row["source"]),
        "assignee_user_id": row["assignee_user_id"],
        "created_by": row["created_by"],
        "updated_by": row["updated_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "captured_at": row["captured_at"],
        "fields": fields,
        "values": values,
        "absent_from_draft": absent,
        "unmapped_values": unmapped,
    }


def _insert_values(
    connection: sqlite3.Connection,
    record_id: str,
    tenant_id: str,
    project_id: str,
    values: dict[str, object],
) -> None:
    for key, value in values.items():
        connection.execute(
            """
            INSERT INTO record_values (id, record_id, tenant_id, project_id, field_key, value_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                record_id,
                tenant_id,
                project_id,
                key,
                json.dumps(value, separators=(",", ":"), sort_keys=True),
            ),
        )


def _values_for(connection: sqlite3.Connection, record_ids: list[str]) -> dict[str, dict[str, object]]:
    if not record_ids:
        return {}
    marks = ", ".join("?" for _ in record_ids)
    rows = connection.execute(
        f"""
        SELECT record_id, field_key, value_json
        FROM record_values
        WHERE record_id IN ({marks})
        """,
        record_ids,
    ).fetchall()
    grouped: dict[str, dict[str, object]] = {}
    for row in rows:
        grouped.setdefault(row["record_id"], {})[row["field_key"]] = json.loads(row["value_json"])
    return grouped


def _load_schema(raw: str) -> dict[str, object]:
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _next_sequence(connection: sqlite3.Connection, project_id: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
        FROM records
        WHERE project_id = ?
        """,
        (project_id,),
    ).fetchone()
    if row is None:
        return 1
    return int(row["next_sequence"])


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _like(term: str) -> str:
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
