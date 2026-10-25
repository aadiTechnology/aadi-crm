"""Immutable published form versions.

Draft edits stay on form_definitions and form_fields. A publish copies the
draft into form_versions and points the form at that row. Ordinary calls do
not update a published snapshot.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db import begin_immediate
from app.forms_store import DuplicateFormName, FormDefinitionRow, FormFieldRow, get_form

_FIELD_TYPES = {
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
}
_PICKLIST = {"dropdown", "multi_select", "radio"}
_FIELD_META = {"field_key", "label", "field_type", "required", "help_text", "section_name", "position"}
_VERSION_COLUMNS = (
    "id, tenant_id, project_id, form_id, version_number, schema_json, published_by, published_at"
)


class InvalidDraft(Exception):
    """The working draft cannot be published or restored."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class DuplicatePublish(Exception):
    """This draft is already the current published snapshot."""


class NoPublishedVersion(Exception):
    """The form has no published version to copy."""


@dataclass(frozen=True)
class FormVersionRow:
    id: str
    tenant_id: str
    project_id: str
    form_id: str
    version_number: int
    schema: dict[str, object]
    published_by: str
    published_at: str
    current: bool

    def as_dict(self) -> dict[str, object]:
        fields = self.schema.get("fields")
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "form_id": self.form_id,
            "version_number": self.version_number,
            "status": "current" if self.current else "published",
            "current": self.current,
            "published_by": self.published_by,
            "published_at": self.published_at,
            "name": self.schema.get("name") if isinstance(self.schema.get("name"), str) else "",
            "description": self.schema.get("description") if isinstance(self.schema.get("description"), str) else "",
            "fields": fields if isinstance(fields, list) else [],
        }


def list_versions(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    form_id: str,
) -> list[FormVersionRow] | None:
    form = get_form(connection, tenant_id, project_id, form_id)
    if form is None:
        return None
    rows = connection.execute(
        f"""
        SELECT {_VERSION_COLUMNS}
        FROM form_versions
        WHERE tenant_id = ? AND project_id = ? AND form_id = ?
        ORDER BY version_number
        """,
        (tenant_id, project_id, form_id),
    ).fetchall()
    return [_version(row, form.current_published_version_id) for row in rows]


def get_version(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    form_id: str,
    version_id: str,
) -> FormVersionRow | None:
    form = get_form(connection, tenant_id, project_id, form_id)
    if form is None:
        return None
    row = connection.execute(
        f"""
        SELECT {_VERSION_COLUMNS}
        FROM form_versions
        WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
        """,
        (tenant_id, project_id, form_id, version_id),
    ).fetchone()
    if row is None:
        return None
    return _version(row, form.current_published_version_id)


def publish_form(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    actor_id: str,
    before_commit=None,
) -> FormVersionRow | None:
    """Copy the current draft into the next version number.

    The version number is chosen inside an immediate transaction. A second
    publish of the same snapshot is rejected. before_commit is a test hook
    that runs after the writes and before commit.
    """

    previous = connection.isolation_level
    connection.isolation_level = None
    try:
        begin_immediate(connection, f"form-version:{form_id}")
        try:
            form = get_form(connection, tenant_id, project_id, form_id)
            if form is None:
                connection.rollback()
                return None
            problem = _draft_problem(form)
            if problem is not None:
                raise InvalidDraft(problem)
            snapshot = _snapshot(form)
            canonical = _canonical(snapshot)
            current = _current_schema(connection, form)
            if current is not None and _canonical(current) == canonical:
                raise DuplicatePublish
            version_id = str(uuid4())
            now = _now()
            number = _next_number(connection, form_id)
            try:
                connection.execute(
                    f"""
                    INSERT INTO form_versions ({_VERSION_COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version_id,
                        tenant_id,
                        project_id,
                        form_id,
                        number,
                        json.dumps(snapshot, separators=(",", ":"), sort_keys=True),
                        actor_id,
                        now,
                    ),
                )
            except sqlite3.IntegrityError:
                raise DuplicatePublish from None
            connection.execute(
                """
                UPDATE form_definitions
                SET current_published_version_id = ?, updated_by = ?, updated_at = ?
                WHERE tenant_id = ? AND project_id = ? AND id = ?
                """,
                (version_id, actor_id, now, tenant_id, project_id, form_id),
            )
            if before_commit is not None:
                before_commit(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.isolation_level = previous
    published = get_version(connection, tenant_id, project_id, form_id, version_id)
    if published is None:
        raise RuntimeError("The published version did not persist.")
    return published


def replace_draft_from_published(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    actor_id: str,
) -> FormDefinitionRow | None:
    """Copy the current published snapshot back onto the working draft.

    The published row is not updated.
    """

    previous = connection.isolation_level
    connection.isolation_level = None
    try:
        begin_immediate(connection, f"form-field:{form_id}")
        try:
            form = get_form(connection, tenant_id, project_id, form_id)
            if form is None:
                connection.rollback()
                return None
            if not form.current_published_version_id:
                raise NoPublishedVersion
            version = get_version(
                connection,
                tenant_id,
                project_id,
                form_id,
                form.current_published_version_id,
            )
            if version is None:
                raise NoPublishedVersion
            problem = _schema_problem(version.schema)
            if problem is not None:
                raise InvalidDraft(problem)
            stored = _schema_text(connection, version.id)
            _replace_draft(connection, form, version.schema, actor_id)
            if before_matches(stored, connection, version.id) is False:
                raise RuntimeError("The published snapshot changed during draft replacement.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.isolation_level = previous
    return get_form(connection, tenant_id, project_id, form_id)


def before_matches(before: str | None, connection: sqlite3.Connection, version_id: str) -> bool:
    return before == _schema_text(connection, version_id)


def _schema_text(connection: sqlite3.Connection, version_id: str) -> str | None:
    row = connection.execute(
        "SELECT schema_json FROM form_versions WHERE id = ?",
        (version_id,),
    ).fetchone()
    if row is None:
        return None
    return str(row["schema_json"])


def _replace_draft(
    connection: sqlite3.Connection,
    form: FormDefinitionRow,
    schema: dict[str, object],
    actor_id: str,
) -> None:
    name = schema["name"]
    description = schema["description"]
    fields = schema["fields"]
    if not isinstance(name, str) or not isinstance(description, str) or not isinstance(fields, list):
        raise InvalidDraft("The published schema cannot be copied.")
    now = _now()
    try:
        connection.execute(
            """
            UPDATE form_definitions
            SET name = ?, description = ?, updated_by = ?, updated_at = ?
            WHERE tenant_id = ? AND project_id = ? AND id = ?
            """,
            (name, description, actor_id, now, form.tenant_id, form.project_id, form.id),
        )
    except sqlite3.IntegrityError:
        raise DuplicateFormName from None
    connection.execute(
        """
        DELETE FROM form_fields
        WHERE tenant_id = ? AND project_id = ? AND form_id = ?
        """,
        (form.tenant_id, form.project_id, form.id),
    )
    for item in fields:
        if not isinstance(item, dict):
            raise InvalidDraft("The published schema cannot be copied.")
        config = {key: value for key, value in item.items() if key not in _FIELD_META}
        connection.execute(
            """
            INSERT INTO form_fields (
                id, tenant_id, project_id, form_id, field_key, label, field_type, required,
                help_text, section_name, position, config_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                form.tenant_id,
                form.project_id,
                form.id,
                item["field_key"],
                item["label"],
                item["field_type"],
                1 if item["required"] else 0,
                item.get("help_text") or "",
                item.get("section_name") or "",
                item["position"],
                json.dumps(config, separators=(",", ":"), sort_keys=True),
                now,
                now,
            ),
        )


def _draft_problem(form: FormDefinitionRow) -> str | None:
    if not form.fields:
        return "Add at least one field before publishing."
    for field in form.fields:
        problem = _field_problem(field)
        if problem is not None:
            return problem
    return None


def _field_problem(field: FormFieldRow) -> str | None:
    if field.field_type not in _FIELD_TYPES:
        return "Field type is not supported."
    if not field.field_key.strip() or not field.label.strip():
        return "Each field needs an identifier and a label before publishing."
    if field.field_type in _PICKLIST:
        options = field.config.get("options")
        if not isinstance(options, list) or not options:
            return "A picklist field needs at least one option before publishing."
    minimum = field.config.get("min_value")
    maximum = field.config.get("max_value")
    if (
        isinstance(minimum, (int, float))
        and isinstance(maximum, (int, float))
        and not isinstance(minimum, bool)
        and not isinstance(maximum, bool)
        and minimum > maximum
    ):
        return "Minimum cannot be greater than maximum."
    return None


def _schema_problem(schema: dict[str, object]) -> str | None:
    name = schema.get("name")
    description = schema.get("description")
    fields = schema.get("fields")
    if not isinstance(name, str) or not name.strip():
        return "The published schema cannot be copied."
    if not isinstance(description, str) or not isinstance(fields, list) or not fields:
        return "The published schema cannot be copied."
    positions: list[int] = []
    keys: list[str] = []
    for item in fields:
        if not isinstance(item, dict):
            return "The published schema cannot be copied."
        field_type = item.get("field_type")
        field_key = item.get("field_key")
        label = item.get("label")
        required = item.get("required")
        position = item.get("position")
        if not isinstance(field_type, str) or field_type not in _FIELD_TYPES:
            return "Field type is not supported."
        if not isinstance(field_key, str) or not field_key.strip():
            return "The published schema cannot be copied."
        if not isinstance(label, str) or not label.strip():
            return "The published schema cannot be copied."
        if not isinstance(required, bool) or isinstance(position, bool) or not isinstance(position, int):
            return "The published schema cannot be copied."
        if field_type in _PICKLIST:
            options = item.get("options")
            if not isinstance(options, list) or not options:
                return "A picklist field needs at least one option before publishing."
        positions.append(position)
        keys.append(field_key.lower())
    if len(set(positions)) != len(positions) or sorted(positions) != list(range(len(positions))):
        return "The published schema cannot be copied."
    if len(set(keys)) != len(keys):
        return "The published schema cannot be copied."
    return None


def _snapshot(form: FormDefinitionRow) -> dict[str, object]:
    fields: list[dict[str, object]] = []
    for field in form.fields:
        body = field.as_dict()
        body.pop("id", None)
        fields.append(body)
    return {"name": form.name, "description": form.description, "fields": fields}


def _current_schema(connection: sqlite3.Connection, form: FormDefinitionRow) -> dict[str, object] | None:
    if not form.current_published_version_id:
        return None
    row = connection.execute(
        """
        SELECT schema_json FROM form_versions
        WHERE id = ? AND tenant_id = ? AND project_id = ? AND form_id = ?
        """,
        (form.current_published_version_id, form.tenant_id, form.project_id, form.id),
    ).fetchone()
    if row is None:
        return None
    parsed = json.loads(row["schema_json"])
    if not isinstance(parsed, dict):
        return None
    return parsed


def _canonical(schema: dict[str, object]) -> str:
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def _next_number(connection: sqlite3.Connection, form_id: str) -> int:
    row = connection.execute(
        """
        SELECT COALESCE(MAX(version_number), 0) + 1 AS next_number
        FROM form_versions
        WHERE form_id = ?
        """,
        (form_id,),
    ).fetchone()
    if row is None:
        return 1
    return int(row["next_number"])


def _version(row: sqlite3.Row, current_id: str | None) -> FormVersionRow:
    parsed = json.loads(row["schema_json"])
    if not isinstance(parsed, dict):
        parsed = {}
    return FormVersionRow(
        id=row["id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        form_id=row["form_id"],
        version_number=int(row["version_number"]),
        schema=parsed,
        published_by=row["published_by"],
        published_at=row["published_at"],
        current=row["id"] == current_id,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
