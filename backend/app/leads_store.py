"""Leads are project records the caller can already open.

There is no separate lead table. Status is a field on the published form when
that form has one. The next follow-up is the earliest open follow-up.
"""

from __future__ import annotations

from app.project_access import RecordRef
from app.records_store import SOURCES, RecordValidation, _load_schema, _schema_fields, _shown, _values_for

_STATUS_KEYS = ("lead_status", "status", "stage", "call_status", "priority", "connected")


def visible_leads(connection, tenant_id: str, caller) -> list[dict[str, object]]:
    """Return record rows in this tenant that authorize_record allows."""

    from app.api.projects import authorize_record

    rows = _rows(connection, tenant_id)
    record_ids = [str(row["id"]) for row in rows]
    values = _values_for(connection, record_ids)
    follow_ups = _next_follow_ups(connection, tenant_id, record_ids)
    shown: list[dict[str, object]] = []
    for row in rows:
        project_id = str(row["project_id"])
        assignee = str(row["assignee_user_id"])
        decision = authorize_record(
            connection,
            tenant_id=tenant_id,
            project_id=project_id,
            caller=caller,
            record=RecordRef(
                tenant_id=tenant_id,
                project_id=project_id,
                assignee_user_id=assignee,
            ),
        )
        if not decision.allowed:
            continue
        record_id = str(row["id"])
        status_label, status_value = _status(_schema(row["schema_json"]), values.get(record_id, {}))
        source = str(row["source"])
        shown.append(
            {
                "id": record_id,
                "project_id": project_id,
                "project_name": str(row["project_name"]),
                "project_code": str(row["project_code"]),
                "public_number": str(row["public_number"]),
                "display_name": str(row["display_name"]),
                "source": source,
                "source_label": SOURCES.get(source, source),
                "assignee_user_id": assignee,
                "assignee_email": None,
                "status_label": status_label,
                "status_value": status_value,
                "next_follow_up_at": follow_ups.get(record_id),
                "updated_at": str(row["updated_at"]),
            }
        )
    return shown


def _rows(connection, tenant_id: str) -> list:
    return connection.execute(
        """
        SELECT records.id, records.project_id, records.public_number, records.display_name,
               records.source, records.assignee_user_id, records.updated_at,
               projects.name AS project_name, projects.code AS project_code,
               form_versions.schema_json
        FROM records
        JOIN projects
          ON projects.id = records.project_id
         AND projects.tenant_id = records.tenant_id
        JOIN form_versions
          ON form_versions.id = records.form_version_id
         AND form_versions.tenant_id = records.tenant_id
         AND form_versions.project_id = records.project_id
        WHERE records.tenant_id = ? AND records.deleted_at IS NULL
        ORDER BY records.updated_at DESC, records.id
        """,
        (tenant_id,),
    ).fetchall()


def _next_follow_ups(connection, tenant_id: str, record_ids: list[str]) -> dict[str, str]:
    if not record_ids:
        return {}
    marks = ", ".join("?" for _ in record_ids)
    rows = connection.execute(
        f"""
        SELECT record_id, due_at
        FROM follow_ups
        WHERE tenant_id = ? AND status = 'open' AND record_id IN ({marks})
        """,
        [tenant_id, *record_ids],
    ).fetchall()
    chosen: dict[str, str] = {}
    for row in rows:
        record_id = str(row["record_id"])
        due_at = str(row["due_at"])
        current = chosen.get(record_id)
        if current is None or due_at < current:
            chosen[record_id] = due_at
    return chosen


def _schema(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        return _load_schema(raw)
    return {}


def _status(schema: dict[str, object], values: dict[str, object]) -> tuple[str | None, str | None]:
    try:
        fields = {str(field["field_key"]): field for field in _schema_fields(schema)}
    except RecordValidation:
        return None, None
    for key in _STATUS_KEYS:
        field = fields.get(key)
        if field is None or key not in values:
            continue
        shown = _shown(field, values[key])
        if not shown:
            continue
        label = field.get("label")
        return (label if isinstance(label, str) and label.strip() else key), shown
    return None, None
