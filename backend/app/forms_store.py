"""CRM-owned form definitions and ordered fields.

The rows in this module are the working draft. Published snapshots live in
form_versions and are not updated here.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

_FORM_COLUMNS = (
    "id, tenant_id, project_id, name, description, status, created_by, updated_by, created_at, updated_at"
)
_FORM_READ = _FORM_COLUMNS + ", current_published_version_id"
_FIELD_COLUMNS = (
    "id, tenant_id, project_id, form_id, field_key, label, field_type, required, "
    "help_text, section_name, position, config_json, created_at, updated_at"
)


class DuplicateFormName(Exception):
    """A form name is already stored for this project."""


class DuplicateFieldKey(Exception):
    """A field identifier is already stored on this form."""


@dataclass(frozen=True)
class FormFieldRow:
    id: str
    tenant_id: str
    project_id: str
    form_id: str
    field_key: str
    label: str
    field_type: str
    required: bool
    help_text: str
    section_name: str
    position: int
    config: dict[str, object]
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        body: dict[str, object] = {
            "id": self.id,
            "field_key": self.field_key,
            "label": self.label,
            "field_type": self.field_type,
            "required": self.required,
            "help_text": self.help_text,
            "section_name": self.section_name,
            "position": self.position,
        }
        body.update(self.config)
        return body


@dataclass(frozen=True)
class FormDefinitionRow:
    id: str
    tenant_id: str
    project_id: str
    name: str
    description: str
    status: str
    created_by: str | None
    updated_by: str | None
    created_at: str
    updated_at: str
    fields: tuple[FormFieldRow, ...]
    current_published_version_id: str | None = None
    current_published_version_number: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_published_version_id": self.current_published_version_id,
            "current_published_version_number": self.current_published_version_number,
            "fields": [field.as_dict() for field in self.fields],
        }


def list_forms(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
) -> list[FormDefinitionRow]:
    rows = connection.execute(
        f"""
        SELECT {_FORM_READ}
        FROM form_definitions
        WHERE tenant_id = ? AND project_id = ?
        ORDER BY lower(name), id
        """,
        (tenant_id, project_id),
    ).fetchall()
    return [_form(connection, row) for row in rows]


def get_form(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    form_id: str,
) -> FormDefinitionRow | None:
    row = connection.execute(
        f"""
        SELECT {_FORM_READ}
        FROM form_definitions
        WHERE tenant_id = ? AND project_id = ? AND id = ?
        """,
        (tenant_id, project_id, form_id),
    ).fetchone()
    if row is None:
        return None
    return _form(connection, row)


def create_form(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    name: str,
    description: str,
    actor_id: str,
) -> FormDefinitionRow:
    form_id = str(uuid4())
    now = _now()
    try:
        connection.execute(
            f"""
            INSERT INTO form_definitions ({_FORM_COLUMNS})
            VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?)
            """,
            (form_id, tenant_id, project_id, name, description, actor_id, actor_id, now, now),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise DuplicateFormName from None
    created = get_form(connection, tenant_id, project_id, form_id)
    if created is None:
        raise RuntimeError("The form insert did not persist.")
    return created


def update_form(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    name: str | None,
    description: str | None,
    actor_id: str,
) -> FormDefinitionRow | None:
    current = get_form(connection, tenant_id, project_id, form_id)
    if current is None:
        return None
    next_name = current.name if name is None else name
    next_description = current.description if description is None else description
    try:
        connection.execute(
            """
            UPDATE form_definitions
            SET name = ?, description = ?, updated_by = ?, updated_at = ?
            WHERE tenant_id = ? AND project_id = ? AND id = ?
            """,
            (next_name, next_description, actor_id, _now(), tenant_id, project_id, form_id),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise DuplicateFormName from None
    return get_form(connection, tenant_id, project_id, form_id)


def add_field(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    field_key: str,
    label: str,
    field_type: str,
    required: bool,
    help_text: str,
    section_name: str,
    config: dict[str, object],
    actor_id: str,
) -> FormFieldRow | None:
    if get_form(connection, tenant_id, project_id, form_id) is None:
        return None
    field_id = str(uuid4())
    now = _now()
    try:
        position = _next_position(connection, form_id)
        connection.execute(
            f"""
            INSERT INTO form_fields ({_FIELD_COLUMNS})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                field_id,
                tenant_id,
                project_id,
                form_id,
                field_key,
                label,
                field_type,
                1 if required else 0,
                help_text,
                section_name,
                position,
                json.dumps(config, separators=(",", ":"), sort_keys=True),
                now,
                now,
            ),
        )
        connection.execute(
            """
            UPDATE form_definitions
            SET updated_by = ?, updated_at = ?
            WHERE tenant_id = ? AND project_id = ? AND id = ?
            """,
            (actor_id, now, tenant_id, project_id, form_id),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise DuplicateFieldKey from None
    created = _get_field(connection, tenant_id, project_id, form_id, field_id)
    if created is None:
        raise RuntimeError("The field insert did not persist.")
    return created


def update_field(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    field_id: str,
    label: str,
    field_type: str,
    required: bool,
    help_text: str,
    section_name: str,
    config: dict[str, object],
    actor_id: str,
) -> FormFieldRow | None:
    current = _get_field(connection, tenant_id, project_id, form_id, field_id)
    if current is None:
        return None
    now = _now()
    connection.execute(
        """
        UPDATE form_fields
        SET label = ?, field_type = ?, required = ?, help_text = ?, section_name = ?,
            config_json = ?, updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
        """,
        (
            label,
            field_type,
            1 if required else 0,
            help_text,
            section_name,
            json.dumps(config, separators=(",", ":"), sort_keys=True),
            now,
            tenant_id,
            project_id,
            form_id,
            field_id,
        ),
    )
    connection.execute(
        """
        UPDATE form_definitions
        SET updated_by = ?, updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND id = ?
        """,
        (actor_id, now, tenant_id, project_id, form_id),
    )
    connection.commit()
    return _get_field(connection, tenant_id, project_id, form_id, field_id)


def reorder_fields(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    field_ids: list[str],
    actor_id: str,
) -> FormDefinitionRow | None:
    current = get_form(connection, tenant_id, project_id, form_id)
    if current is None:
        return None
    stored = [field.id for field in current.fields]
    if stored != field_ids and sorted(stored) != sorted(field_ids):
        raise ValueError("order")
    if len(field_ids) != len(set(field_ids)):
        raise ValueError("order")
    now = _now()
    offset = _position_offset(connection, form_id)
    for index, field_id in enumerate(field_ids):
        connection.execute(
            """
            UPDATE form_fields
            SET position = ?
            WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
            """,
            (offset + index, tenant_id, project_id, form_id, field_id),
        )
    for index, field_id in enumerate(field_ids):
        connection.execute(
            """
            UPDATE form_fields
            SET position = ?, updated_at = ?
            WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
            """,
            (index, now, tenant_id, project_id, form_id, field_id),
        )
    connection.execute(
        """
        UPDATE form_definitions
        SET updated_by = ?, updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND id = ?
        """,
        (actor_id, now, tenant_id, project_id, form_id),
    )
    connection.commit()
    return get_form(connection, tenant_id, project_id, form_id)


def remove_field(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    field_id: str,
    actor_id: str,
) -> FormDefinitionRow | None:
    current = _get_field(connection, tenant_id, project_id, form_id, field_id)
    if current is None:
        return None
    now = _now()
    connection.execute(
        """
        DELETE FROM form_fields
        WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
        """,
        (tenant_id, project_id, form_id, field_id),
    )
    remaining = connection.execute(
        """
        SELECT id FROM form_fields
        WHERE tenant_id = ? AND project_id = ? AND form_id = ?
        ORDER BY position, id
        """,
        (tenant_id, project_id, form_id),
    ).fetchall()
    offset = _position_offset(connection, form_id)
    for index, row in enumerate(remaining):
        connection.execute(
            """
            UPDATE form_fields
            SET position = ?
            WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
            """,
            (offset + index, tenant_id, project_id, form_id, row["id"]),
        )
    for index, row in enumerate(remaining):
        connection.execute(
            """
            UPDATE form_fields
            SET position = ?, updated_at = ?
            WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
            """,
            (index, now, tenant_id, project_id, form_id, row["id"]),
        )
    connection.execute(
        """
        UPDATE form_definitions
        SET updated_by = ?, updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND id = ?
        """,
        (actor_id, now, tenant_id, project_id, form_id),
    )
    connection.commit()
    return get_form(connection, tenant_id, project_id, form_id)


def _position_offset(connection: sqlite3.Connection, form_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(position), -1) AS max_position FROM form_fields WHERE form_id = ?",
        (form_id,),
    ).fetchone()
    if row is None:
        return 0
    return int(row["max_position"]) + 1


def _next_position(connection: sqlite3.Connection, form_id: str) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 AS next_position FROM form_fields WHERE form_id = ?",
        (form_id,),
    ).fetchone()
    if row is None:
        return 0
    return int(row["next_position"])


def _get_field(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    form_id: str,
    field_id: str,
) -> FormFieldRow | None:
    row = connection.execute(
        f"""
        SELECT {_FIELD_COLUMNS}
        FROM form_fields
        WHERE tenant_id = ? AND project_id = ? AND form_id = ? AND id = ?
        """,
        (tenant_id, project_id, form_id, field_id),
    ).fetchone()
    if row is None:
        return None
    return _field(row)


def _form(connection: sqlite3.Connection, row: sqlite3.Row) -> FormDefinitionRow:
    field_rows = connection.execute(
        f"""
        SELECT {_FIELD_COLUMNS}
        FROM form_fields
        WHERE tenant_id = ? AND project_id = ? AND form_id = ?
        ORDER BY position, id
        """,
        (row["tenant_id"], row["project_id"], row["id"]),
    ).fetchall()
    return FormDefinitionRow(
        id=row["id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        created_by=row["created_by"],
        updated_by=row["updated_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        fields=tuple(_field(item) for item in field_rows),
        current_published_version_id=row["current_published_version_id"],
        current_published_version_number=_published_number(connection, row["current_published_version_id"]),
    )


def _published_number(connection: sqlite3.Connection, version_id: str | None) -> int | None:
    if not version_id:
        return None
    found = connection.execute(
        "SELECT version_number FROM form_versions WHERE id = ?",
        (version_id,),
    ).fetchone()
    if found is None:
        return None
    return int(found["version_number"])


def _field(row: sqlite3.Row) -> FormFieldRow:
    parsed = json.loads(row["config_json"])
    if not isinstance(parsed, dict):
        parsed = {}
    return FormFieldRow(
        id=row["id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        form_id=row["form_id"],
        field_key=row["field_key"],
        label=row["label"],
        field_type=row["field_type"],
        required=bool(row["required"]),
        help_text=row["help_text"],
        section_name=row["section_name"],
        position=int(row["position"]),
        config=parsed,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()
