"""Tenant-scoped CSV/XLSX import jobs and filtered export rows.

Dry-run writes preview details on the import job only. It does not call
create_record and does not allocate a record number. Commit rechecks the
published form, the row, and possible email or mobile matches.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.form_versions import get_version
from app.forms_store import get_form
from app.records_store import (
    RecordListQuery,
    RecordValidation,
    UnpublishedForm,
    _schema_fields,
    create_record,
    get_record,
    list_records,
    validate_values,
)

MAX_EXPORT_ROWS = 1000
_DECISIONS = {"accept_new", "skip", "reject"}
_UNIMPORTABLE = {"file", "auto_number"}
_MOBILE_SPLIT = re.compile(r"[\s().-]")
_SERIAL = re.compile(r"^\d{1,6}$")


class ImportProblem(Exception):
    """The import request cannot continue."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def create_job(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    form_id: str,
    form_version_id: str,
    actor_user_id: str,
    idempotency_key: str,
    filename: str,
    content_sha256: str,
    parsed_rows: list[tuple[int, dict[str, str], list[str]]],
) -> dict[str, object]:
    """Store one logical import. The same key and file return the existing job."""

    _busy(connection)
    previous = connection.isolation_level
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing = _job_by_key(connection, tenant_id, project_id, idempotency_key)
            if existing is not None:
                if existing["content_sha256"] != content_sha256 or existing["form_id"] != form_id:
                    raise ImportProblem(
                        "This import key was already used for a different file or form.",
                        409,
                    )
                connection.rollback()
                return present_job(connection, tenant_id, project_id, str(existing["id"]))
            now = _now()
            job_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO import_jobs (
                    id, tenant_id, project_id, form_id, form_version_id, actor_user_id,
                    idempotency_key, filename, content_sha256, status, mapping_json,
                    summary_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'uploaded', NULL, NULL, ?, ?)
                """,
                (
                    job_id,
                    tenant_id,
                    project_id,
                    form_id,
                    form_version_id,
                    actor_user_id,
                    idempotency_key,
                    filename,
                    content_sha256,
                    now,
                    now,
                ),
            )
            for row_number, source, parse_errors in parsed_rows:
                connection.execute(
                    """
                    INSERT INTO import_rows (
                        id, job_id, tenant_id, project_id, row_number, source_json,
                        parse_errors_json, decision, outcome, errors_json, candidates_json,
                        values_json, record_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'stored', '[]', '[]', NULL, NULL)
                    """,
                    (
                        str(uuid4()),
                        job_id,
                        tenant_id,
                        project_id,
                        row_number,
                        json.dumps(source, ensure_ascii=False),
                        json.dumps(parse_errors, ensure_ascii=False),
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.isolation_level = previous
    return present_job(connection, tenant_id, project_id, job_id)


def present_job(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    job_id: str,
) -> dict[str, object]:
    job = _require_job(connection, tenant_id, project_id, job_id)
    rows = _rows(connection, tenant_id, project_id, job_id)
    version = get_version(connection, tenant_id, project_id, str(job["form_id"]), str(job["form_version_id"]))
    fields = _schema_fields(version.schema) if version is not None else []
    return _body(job, rows, fields)


def save_mapping(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    job_id: str,
    columns: dict[str, str | None],
) -> dict[str, object]:
    job = _require_job(connection, tenant_id, project_id, job_id)
    if _accepted_count(connection, tenant_id, project_id, job_id):
        raise ImportProblem("Mapping stays as it was after a row has been imported.", 409)
    version = _version(connection, tenant_id, project_id, job)
    fields = _schema_fields(version.schema)
    headers = _headers(connection, tenant_id, project_id, job_id)
    if set(columns) != set(headers):
        raise ImportProblem("Map every source column. Leave a column blank when it should stay unmapped.")
    chosen = [value for value in columns.values() if value]
    if len(chosen) != len(set(chosen)):
        raise ImportProblem("Each CRM field can be selected once.")
    known = {str(field["field_key"]): field for field in fields}
    for target in chosen:
        field = known.get(target)
        if field is None:
            raise ImportProblem("A selected field is not on the published form.")
        if str(field.get("field_type")) in _UNIMPORTABLE:
            label = str(field.get("label") or target)
            raise ImportProblem(f"{label} cannot be imported.")
    now = _now()
    connection.execute(
        """
        UPDATE import_jobs
        SET mapping_json = ?, status = 'mapped', updated_at = ?
        WHERE id = ? AND tenant_id = ? AND project_id = ?
        """,
        (json.dumps(columns, ensure_ascii=False), now, job_id, tenant_id, project_id),
    )
    connection.commit()
    return present_job(connection, tenant_id, project_id, job_id)


def save_decisions(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    job_id: str,
    decisions: dict[int, str],
) -> dict[str, object]:
    _require_job(connection, tenant_id, project_id, job_id)
    rows = {int(row["row_number"]): row for row in _rows(connection, tenant_id, project_id, job_id)}
    for row_number, decision in decisions.items():
        if decision not in _DECISIONS:
            raise ImportProblem("Choose accept as new, skip, or reject.")
        row = rows.get(row_number)
        if row is None:
            raise ImportProblem(f"Row {row_number} is not in this import.")
        if row["outcome"] == "accepted":
            raise ImportProblem(f"Row {row_number} is already imported.", 409)
    for row_number, decision in decisions.items():
        connection.execute(
            """
            UPDATE import_rows
            SET decision = ?
            WHERE job_id = ? AND tenant_id = ? AND project_id = ? AND row_number = ? AND outcome != 'accepted'
            """,
            (decision, job_id, tenant_id, project_id, row_number),
        )
    connection.execute(
        "UPDATE import_jobs SET updated_at = ? WHERE id = ? AND tenant_id = ? AND project_id = ?",
        (_now(), job_id, tenant_id, project_id),
    )
    connection.commit()
    return present_job(connection, tenant_id, project_id, job_id)


def preview_job(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    job_id: str,
    assignee_user_id: str | None,
    allowed: Callable[[str, str | None], bool],
) -> dict[str, object]:
    """Evaluate rows and store the preview. Records and sequences stay unchanged."""

    job = _require_job(connection, tenant_id, project_id, job_id)
    if not job["mapping_json"]:
        raise ImportProblem("Map the columns before previewing the import.")
    version = _version(connection, tenant_id, project_id, job)
    fields = _schema_fields(version.schema)
    mapping = _mapping(job)
    rows = _rows(connection, tenant_id, project_id, job_id)
    evaluations = _evaluate_all(
        connection,
        tenant_id,
        project_id,
        rows,
        mapping,
        version.schema,
        fields,
        assignee_user_id,
        allowed,
    )
    for row, evaluation in zip(rows, evaluations, strict=True):
        if row["outcome"] == "accepted":
            continue
        connection.execute(
            """
            UPDATE import_rows
            SET errors_json = ?, candidates_json = ?, values_json = ?
            WHERE id = ? AND tenant_id = ? AND project_id = ? AND outcome != 'accepted'
            """,
            (
                json.dumps(evaluation["errors"], ensure_ascii=False),
                json.dumps(evaluation["candidates"], ensure_ascii=False),
                json.dumps(evaluation["values"], ensure_ascii=False),
                row["id"],
                tenant_id,
                project_id,
            ),
        )
    preview = _count_expectations(evaluations)
    summary = _count_outcomes(rows)
    summary["preview_accepted"] = preview["accepted"]
    summary["preview_rejected"] = preview["rejected"]
    summary["preview_skipped"] = preview["skipped"]
    summary["preview_awaiting_review"] = preview["awaiting_review"]
    summary["records_created"] = 0
    connection.execute(
        """
        UPDATE import_jobs
        SET status = CASE WHEN status IN ('completed', 'partial', 'committing') THEN status ELSE 'previewed' END,
            summary_json = ?, updated_at = ?
        WHERE id = ? AND tenant_id = ? AND project_id = ?
        """,
        (json.dumps(summary, ensure_ascii=False), _now(), job_id, tenant_id, project_id),
    )
    connection.commit()
    body = present_job(connection, tenant_id, project_id, job_id)
    body["preview"] = summary
    return body


def commit_job(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    project_code: str,
    job_id: str,
    actor_user_id: str,
    assignee_user_id: str | None,
    allowed: Callable[[str, str | None], bool],
) -> dict[str, object]:
    """Create records for rows that still pass validation. A finished job is returned as stored."""

    job = _require_job(connection, tenant_id, project_id, job_id)
    if job["status"] == "completed":
        return present_job(connection, tenant_id, project_id, job_id)
    if not job["mapping_json"]:
        raise ImportProblem("Map the columns before importing.")
    _busy(connection)
    previous = connection.isolation_level
    connection.isolation_level = None
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            current = _require_job(connection, tenant_id, project_id, job_id)
            if current["status"] == "completed":
                connection.rollback()
                return present_job(connection, tenant_id, project_id, job_id)
            version = _version(connection, tenant_id, project_id, current)
            form = get_form(connection, tenant_id, project_id, str(current["form_id"]))
            if form is None or form.current_published_version_id != current["form_version_id"]:
                raise ImportProblem("The published form changed. Start a new import for the current version.", 409)
            connection.execute(
                """
                UPDATE import_jobs SET status = 'committing', updated_at = ?
                WHERE id = ? AND tenant_id = ? AND project_id = ? AND status != 'completed'
                """,
                (_now(), job_id, tenant_id, project_id),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    finally:
        connection.isolation_level = previous

    pending = [row for row in _rows(connection, tenant_id, project_id, job_id) if row["outcome"] != "accepted"]
    mapping = _mapping(job)
    fields = _schema_fields(version.schema)
    form_id = str(job["form_id"])
    evaluations = _evaluate_all(
        connection,
        tenant_id,
        project_id,
        pending,
        mapping,
        version.schema,
        fields,
        assignee_user_id,
        allowed,
    )
    for row, evaluation in zip(pending, evaluations, strict=True):
        if str(evaluation["expectation"]) != "accepted":
            _store_result(
                connection,
                tenant_id,
                project_id,
                str(row["id"]),
                str(evaluation["expectation"]),
                evaluation,
                None,
            )
            continue
        _insert_accepted(
            connection,
            tenant_id=tenant_id,
            project_id=project_id,
            project_code=project_code,
            form_id=form_id,
            actor_user_id=actor_user_id,
            evaluation=evaluation,
            row=row,
        )
    _finish(connection, tenant_id, project_id, job_id)
    return present_job(connection, tenant_id, project_id, job_id)


def error_report(connection: sqlite3.Connection, tenant_id: str, project_id: str, job_id: str) -> str:
    _require_job(connection, tenant_id, project_id, job_id)
    lines = ["row_number,field,message"]
    for row in _rows(connection, tenant_id, project_id, job_id):
        if not _reportable(row):
            continue
        errors = _json_list(row["errors_json"])
        if not errors and row["outcome"] == "skipped":
            errors = [{"field": "", "message": "Skipped during duplicate review."}]
        if not errors and row["outcome"] == "awaiting_review":
            errors = [{"field": "", "message": "Choose accept as new, skip, or reject before this row can be imported."}]
        if not errors and row["decision"] == "skip":
            errors = [{"field": "", "message": "Skipped during duplicate review."}]
        if not errors and row["decision"] == "reject":
            errors = [{"field": "", "message": "Rejected during duplicate review."}]
        for error in errors:
            field = str(error.get("field") or error.get("column") or "")
            message = str(error.get("message") or "This row needs attention.")
            lines.append(f"{int(row['row_number'])},{_csv_cell(field)},{_csv_cell(message)}")
        for candidate in _json_list(row["candidates_json"]):
            lines.append(
                f"{int(row['row_number'])},{_csv_cell(str(candidate.get('field_label') or ''))},{_csv_cell(_candidate_text(candidate))}"
            )
    return "\n".join(lines) + "\n"


def export_rows(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    query: RecordListQuery,
    allowed: Callable[[str, str | None], bool],
) -> tuple[list[str], list[list[str]], int]:
    """Return neutralized rows for the authorized filtered list, or reject an oversized export."""

    if query.form_id:
        form = get_form(connection, tenant_id, project_id, query.form_id)
        if form is None or not form.current_published_version_id:
            raise ImportProblem("Choose a published form before exporting its fields.", 409)
    bounded = RecordListQuery(
        search=query.search,
        form_id=query.form_id,
        source=query.source,
        created_from=query.created_from,
        created_to=query.created_to,
        sort=query.sort,
        direction=query.direction,
        limit=MAX_EXPORT_ROWS + 1,
        offset=0,
        assignee_user_id=query.assignee_user_id,
    )
    items, total = list_records(connection, tenant_id, project_id, bounded)
    visible = [item for item in items if allowed(str(item["id"]), str(item["assignee_user_id"]))]
    if total > MAX_EXPORT_ROWS or len(visible) > MAX_EXPORT_ROWS:
        raise ImportProblem(
            f"This export has more than {MAX_EXPORT_ROWS} records. Narrow the search and try again.",
            422,
        )
    headers, matrix = _export_matrix(connection, tenant_id, project_id, query.form_id, visible)
    return headers, matrix, len(matrix)


def _insert_accepted(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    project_code: str,
    form_id: str,
    actor_user_id: str,
    evaluation: dict[str, object],
    row: sqlite3.Row,
) -> None:
    if row["outcome"] == "accepted":
        return
    reserved = row["record_id"] or str(uuid4())
    connection.execute(
        """
        UPDATE import_rows
        SET record_id = COALESCE(record_id, ?), outcome = 'working'
        WHERE id = ? AND tenant_id = ? AND project_id = ? AND outcome != 'accepted'
        """,
        (reserved, row["id"], tenant_id, project_id),
    )
    connection.commit()
    stored = connection.execute(
        "SELECT record_id FROM import_rows WHERE id = ? AND tenant_id = ? AND project_id = ?",
        (row["id"], tenant_id, project_id),
    ).fetchone()
    record_id = str(stored["record_id"]) if stored and stored["record_id"] else reserved
    existing = get_record(connection, tenant_id, project_id, record_id)
    if existing is not None:
        _store_result(connection, tenant_id, project_id, str(row["id"]), "accepted", evaluation, record_id)
        return
    raw_values = evaluation["values"]
    if not isinstance(raw_values, dict):
        raw_values = {}
    try:
        created = create_record(
            connection,
            tenant_id=tenant_id,
            project_id=project_id,
            project_code=project_code,
            form_id=form_id,
            actor_id=actor_user_id,
            source="import",
            values=raw_values,
            record_id=record_id,
        )
    except UnpublishedForm:
        _store_result(
            connection,
            tenant_id,
            project_id,
            str(row["id"]),
            "rejected",
            _with_error(evaluation, "", "Publish this form before importing."),
            None,
        )
        return
    except RecordValidation as exc:
        _store_result(
            connection,
            tenant_id,
            project_id,
            str(row["id"]),
            "rejected",
            _with_fields(evaluation, exc.fields or {"": exc.message}),
            None,
        )
        return
    except sqlite3.IntegrityError:
        created = get_record(connection, tenant_id, project_id, record_id)
    if created is None:
        _store_result(
            connection,
            tenant_id,
            project_id,
            str(row["id"]),
            "rejected",
            _with_error(evaluation, "", "This row could not be imported."),
            None,
        )
        return
    _store_result(connection, tenant_id, project_id, str(row["id"]), "accepted", evaluation, str(created["id"]))


def _finish(connection, tenant_id: str, project_id: str, job_id: str) -> None:
    rows = _rows(connection, tenant_id, project_id, job_id)
    summary = _count_outcomes(rows)
    status = "completed" if summary["accepted"] == summary["input_rows"] else "partial"
    connection.execute(
        """
        UPDATE import_jobs
        SET status = ?, summary_json = ?, updated_at = ?
        WHERE id = ? AND tenant_id = ? AND project_id = ?
        """,
        (status, json.dumps(summary, ensure_ascii=False), _now(), job_id, tenant_id, project_id),
    )
    connection.commit()


def _store_result(connection, tenant_id, project_id, row_id, outcome, evaluation, record_id) -> None:
    connection.execute(
        """
        UPDATE import_rows
        SET outcome = ?, errors_json = ?, candidates_json = ?, values_json = ?,
            record_id = COALESCE(?, record_id)
        WHERE id = ? AND tenant_id = ? AND project_id = ?
        """,
        (
            outcome,
            json.dumps(evaluation["errors"], ensure_ascii=False),
            json.dumps(evaluation["candidates"], ensure_ascii=False),
            json.dumps(evaluation["values"], ensure_ascii=False),
            record_id,
            row_id,
            tenant_id,
            project_id,
        ),
    )
    connection.commit()


def _evaluate_all(
    connection,
    tenant_id: str,
    project_id: str,
    rows: list[sqlite3.Row],
    mapping: dict[str, str | None],
    schema: dict[str, object],
    fields: list[dict[str, object]],
    assignee_user_id: str | None,
    allowed: Callable[[str, str | None], bool],
) -> list[dict[str, object]]:
    known = {str(field["field_key"]): field for field in fields}
    prepared: list[dict[str, object]] = []
    for row in rows:
        source = _json_object(row["source_json"])
        errors: list[dict[str, str]] = [
            {"field": "", "column": "", "message": message} for message in _json_strings(row["parse_errors_json"])
        ]
        values: dict[str, object] = {}
        unmapped: dict[str, str] = {}
        row_contacts: list[tuple[str, str]] = []
        for column, raw in source.items():
            target = mapping.get(column)
            text = raw if isinstance(raw, str) else ""
            if not target:
                if text.strip():
                    unmapped[column] = text
                continue
            field = known.get(target)
            if field is None:
                errors.append({"field": target, "column": column, "message": "This field is not on the published form."})
                continue
            coerced, problem = _coerce(field, text)
            if problem:
                errors.append({"field": target, "column": column, "message": problem})
            elif coerced is not None:
                values[target] = coerced
                normalized = _normalized(str(field.get("field_type") or ""), coerced)
                if normalized:
                    row_contacts.append((str(field.get("field_type")), normalized))
        if not errors:
            try:
                values = validate_values(schema, values)
            except RecordValidation as exc:
                for key, message in (exc.fields or {"": exc.message}).items():
                    errors.append({"field": key, "column": _column_for(mapping, key), "message": message})
        prepared.append(
            {
                "row_number": int(row["row_number"]),
                "decision": row["decision"],
                "errors": errors,
                "values": values if not errors else {},
                "unmapped": unmapped,
                "contacts": row_contacts,
            }
        )
    batch: dict[tuple[str, str], list[int]] = {}
    for item in prepared:
        if item["errors"]:
            continue
        for kind, normalized in item["contacts"]:
            batch.setdefault((kind, normalized), []).append(int(item["row_number"]))
    existing = _existing_contacts(connection, tenant_id, project_id, assignee_user_id, allowed)
    evaluations: list[dict[str, object]] = []
    for item in prepared:
        candidates = _match_candidates(item, batch, existing, known)
        decision = item["decision"]
        errors = list(item["errors"])
        if decision == "reject" and not errors:
            errors.append({"field": "", "column": "", "message": "Rejected during duplicate review."})
        if errors or decision == "reject":
            expectation = "rejected"
        elif decision == "skip":
            expectation = "skipped"
        elif candidates and decision != "accept_new":
            expectation = "awaiting_review"
        else:
            expectation = "accepted"
        evaluations.append(
            {
                "expectation": expectation,
                "errors": errors,
                "candidates": candidates,
                "values": item["values"] if expectation == "accepted" else item["values"],
                "unmapped": item["unmapped"],
            }
        )
    return evaluations


def _match_candidates(item, batch, existing, known) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for kind, normalized in item["contacts"]:
        label = _kind_label(kind, item, known)
        for other in batch.get((kind, normalized), []):
            if other == item["row_number"]:
                continue
            key = ("batch", str(other))
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "kind": "batch",
                    "row_number": str(other),
                    "field_label": label,
                    "message": f"Possible match on {label} with row {other} in this file.",
                }
            )
        for record in existing.get((kind, normalized), []):
            key = ("existing", record["record_id"])
            if key in seen:
                continue
            seen.add(key)
            found.append(
                {
                    "kind": "existing",
                    "record_id": record["record_id"],
                    "public_number": record["public_number"],
                    "display_name": record["display_name"],
                    "field_label": label,
                    "message": f"Possible match on {label} with {record['public_number']}.",
                }
            )
    return found


def _kind_label(kind: str, item, known) -> str:
    for key, value in item["values"].items():
        field = known.get(key)
        if field is not None and str(field.get("field_type")) == kind and _normalized(kind, value):
            label = field.get("label")
            if isinstance(label, str) and label.strip():
                return label
    return "Email" if kind == "email" else "Mobile"


def _existing_contacts(connection, tenant_id, project_id, assignee_user_id, allowed) -> dict[tuple[str, str], list[dict[str, str]]]:
    typed = _contact_keys(connection, tenant_id, project_id)
    if not typed:
        return {}
    marks = ", ".join("?" for _ in typed)
    params: list[object] = [tenant_id, project_id, *typed.keys()]
    assignee_sql = ""
    if assignee_user_id is not None:
        assignee_sql = " AND r.assignee_user_id = ?"
        params.append(assignee_user_id)
    stored = connection.execute(
        f"""
        SELECT r.id, r.public_number, r.display_name, r.assignee_user_id, rv.field_key, rv.value_json
        FROM records r
        JOIN record_values rv
          ON rv.record_id = r.id AND rv.tenant_id = r.tenant_id AND rv.project_id = r.project_id
        WHERE r.tenant_id = ? AND r.project_id = ? AND r.deleted_at IS NULL
          AND rv.field_key IN ({marks}){assignee_sql}
        """,
        params,
    ).fetchall()
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    permitted: dict[str, bool] = {}
    for row in stored:
        record_id = str(row["id"])
        if record_id not in permitted:
            permitted[record_id] = allowed(record_id, row["assignee_user_id"])
        if not permitted[record_id]:
            continue
        try:
            value = json.loads(row["value_json"])
        except json.JSONDecodeError:
            continue
        kind = typed[str(row["field_key"])]
        normalized = _normalized(kind, value)
        if not normalized:
            continue
        grouped.setdefault((kind, normalized), []).append(
            {
                "record_id": record_id,
                "public_number": str(row["public_number"]),
                "display_name": str(row["display_name"]),
            }
        )
    return grouped


def _contact_keys(connection, tenant_id: str, project_id: str) -> dict[str, str]:
    versions = connection.execute(
        "SELECT schema_json FROM form_versions WHERE tenant_id = ? AND project_id = ?",
        (tenant_id, project_id),
    ).fetchall()
    typed: dict[str, str] = {}
    for version in versions:
        try:
            schema = json.loads(version["schema_json"])
        except json.JSONDecodeError:
            continue
        if not isinstance(schema, dict):
            continue
        try:
            fields = _schema_fields(schema)
        except RecordValidation:
            continue
        for field in fields:
            kind = str(field.get("field_type") or "")
            if kind in {"email", "mobile"}:
                typed[str(field["field_key"])] = kind
    return typed


def _coerce(field: dict[str, object], raw: str) -> tuple[object | None, str | None]:
    text = raw.strip()
    label = str(field.get("label") or field.get("field_key") or "Value")
    kind = str(field.get("field_type") or "")
    if not text:
        return None, None
    if kind == "checkbox":
        lowered = text.casefold()
        if lowered in {"true", "yes", "1"}:
            return True, None
        if lowered in {"false", "no", "0"}:
            return False, None
        return None, f"{label} must be true or false."
    if kind in {"number", "currency"}:
        if not re.fullmatch(r"-?\d+(\.\d+)?", text):
            return None, f"{label} must be a number."
        return float(text) if "." in text else int(text), None
    if kind == "multi_select":
        parts = [part.strip() for part in text.split("|")]
        if any(not part for part in parts):
            return None, f"{label} must use the listed options."
        return parts, None
    if kind in {"dropdown", "radio"}:
        options = field.get("options")
        if isinstance(options, list):
            labels = [item for item in options if isinstance(item, dict) and item.get("label") == text]
            values = [item for item in options if isinstance(item, dict) and item.get("value") == text]
            if not values and len(labels) == 1 and isinstance(labels[0].get("value"), str):
                return labels[0]["value"], None
        return text, None
    if kind == "email":
        return text.casefold(), None
    if kind == "mobile":
        return _MOBILE_SPLIT.sub("", text), None
    if kind == "date" and _SERIAL.fullmatch(text):
        serial = int(text)
        if 1 <= serial <= 60000:
            return (datetime(1899, 12, 30, tzinfo=UTC) + timedelta(days=serial)).date().isoformat(), None
    return text, None


def _normalized(kind: str, value: object) -> str:
    if kind == "email" and isinstance(value, str):
        compact = value.strip().casefold()
        return compact if "@" in compact else ""
    if kind == "mobile" and isinstance(value, str):
        return _MOBILE_SPLIT.sub("", value.strip())
    return ""


def _export_matrix(connection, tenant_id, project_id, form_id, items) -> tuple[list[str], list[list[str]]]:
    from app.records_store import _values_for

    metadata = ["public_number", "display_name", "source", "form_version_id", "created_at"]
    field_columns: list[tuple[str, str]] = []
    if form_id:
        form = get_form(connection, tenant_id, project_id, form_id)
        version = None
        if form is not None and form.current_published_version_id:
            version = get_version(connection, tenant_id, project_id, form_id, form.current_published_version_id)
        if version is not None:
            for field in _schema_fields(version.schema):
                if str(field.get("field_type")) in _UNIMPORTABLE:
                    continue
                field_columns.append((str(field["field_key"]), str(field.get("label") or field["field_key"])))
        seen = {key for key, _label in field_columns}
        values = _values_for(connection, [str(item["id"]) for item in items])
        for item in items:
            for key in values.get(str(item["id"]), {}):
                if key not in seen:
                    seen.add(key)
                    field_columns.append((key, f"{key} (previous version)"))
    else:
        values = {}
    headers = metadata + [label for _key, label in field_columns]
    matrix: list[list[str]] = []
    if form_id:
        values = _values_for(connection, [str(item["id"]) for item in items])
    for item in items:
        stored = values.get(str(item["id"]), {})
        row = [
            str(item["public_number"]),
            str(item["display_name"]),
            str(item["source"]),
            str(item["form_version_id"]),
            str(item["created_at"]),
        ]
        for key, _label in field_columns:
            row.append(_export_value(stored.get(key)))
        matrix.append(row)
    return headers, matrix


def _export_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    return str(value)


def _body(job: sqlite3.Row, rows: list[sqlite3.Row], fields: list[dict[str, object]]) -> dict[str, object]:
    mapping = _mapping(job) if job["mapping_json"] else None
    headers = list(_json_object(rows[0]["source_json"]).keys()) if rows else []
    presented = []
    for row in rows:
        presented.append(
            {
                "row_number": int(row["row_number"]),
                "source": _json_object(row["source_json"]),
                "unmapped": _unmapped(_json_object(row["source_json"]), mapping),
                "values": _json_object(row["values_json"]) if row["values_json"] else {},
                "errors": _json_list(row["errors_json"]),
                "candidates": _json_list(row["candidates_json"]),
                "decision": row["decision"],
                "outcome": row["outcome"],
                "record_id": row["record_id"],
            }
        )
    summary = _json_object(job["summary_json"]) if job["summary_json"] else _count_outcomes(rows)
    return {
        "id": job["id"],
        "project_id": job["project_id"],
        "form_id": job["form_id"],
        "form_version_id": job["form_version_id"],
        "filename": job["filename"],
        "status": job["status"],
        "idempotency_key": job["idempotency_key"],
        "headers": headers,
        "fields": [
            {
                "field_key": field["field_key"],
                "label": field.get("label") or field["field_key"],
                "field_type": field.get("field_type"),
                "required": field.get("required") is True,
                "options": field.get("options") if isinstance(field.get("options"), list) else [],
            }
            for field in fields
            if str(field.get("field_type")) not in _UNIMPORTABLE
        ],
        "unimportable_fields": [
            {"field_key": field["field_key"], "label": field.get("label") or field["field_key"], "field_type": field.get("field_type")}
            for field in fields
            if str(field.get("field_type")) in _UNIMPORTABLE
        ],
        "mapping": mapping,
        "unmapped_columns": [column for column, target in (mapping or {}).items() if not target],
        "rows": presented,
        "summary": summary,
        "header_included_in_counts": False,
    }


def _count_outcomes(rows: list[sqlite3.Row]) -> dict[str, int | bool]:
    counts = {"accepted": 0, "rejected": 0, "skipped": 0, "awaiting_review": 0, "not_committed": 0}
    for row in rows:
        outcome = str(row["outcome"])
        if outcome in counts:
            counts[outcome] += 1
        else:
            counts["not_committed"] += 1
    counts["input_rows"] = len(rows)
    counts["header_included"] = False
    return counts


def _count_expectations(evaluations: list[dict[str, object]]) -> dict[str, int | bool]:
    counts = {"accepted": 0, "rejected": 0, "skipped": 0, "awaiting_review": 0}
    for item in evaluations:
        name = str(item["expectation"])
        if name in counts:
            counts[name] += 1
    counts["input_rows"] = len(evaluations)
    counts["header_included"] = False
    return counts


def _reportable(row: sqlite3.Row) -> bool:
    if row["outcome"] in {"rejected", "skipped", "awaiting_review"}:
        return True
    if row["outcome"] != "stored":
        return False
    return bool(_json_list(row["errors_json"]) or _json_list(row["candidates_json"]) or row["decision"] in {"skip", "reject"})


def _candidate_text(candidate: dict[str, object]) -> str:
    message = candidate.get("message")
    if isinstance(message, str) and message.strip():
        return message
    return "Possible duplicate match."


def _unmapped(source: dict[str, object], mapping: dict[str, str | None] | None) -> dict[str, str]:
    if mapping is None:
        return {key: value for key, value in source.items() if isinstance(value, str) and value.strip()}
    return {
        key: value
        for key, value in source.items()
        if not mapping.get(key) and isinstance(value, str) and value.strip()
    }


def _headers(connection, tenant_id, project_id, job_id) -> list[str]:
    row = connection.execute(
        """
        SELECT source_json FROM import_rows
        WHERE tenant_id = ? AND project_id = ? AND job_id = ?
        ORDER BY row_number LIMIT 1
        """,
        (tenant_id, project_id, job_id),
    ).fetchone()
    if row is None:
        return []
    return list(_json_object(row["source_json"]).keys())


def _accepted_count(connection, tenant_id, project_id, job_id) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count FROM import_rows
        WHERE tenant_id = ? AND project_id = ? AND job_id = ? AND outcome = 'accepted'
        """,
        (tenant_id, project_id, job_id),
    ).fetchone()
    return int(row["count"]) if row is not None else 0


def _require_job(connection, tenant_id, project_id, job_id) -> sqlite3.Row:
    job = connection.execute(
        """
        SELECT * FROM import_jobs
        WHERE id = ? AND tenant_id = ? AND project_id = ?
        """,
        (job_id, tenant_id, project_id),
    ).fetchone()
    if job is None:
        raise ImportProblem("This import was not found.", 404)
    return job


def _job_by_key(connection, tenant_id, project_id, idempotency_key) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT * FROM import_jobs
        WHERE tenant_id = ? AND project_id = ? AND idempotency_key = ?
        """,
        (tenant_id, project_id, idempotency_key),
    ).fetchone()


def _rows(connection, tenant_id, project_id, job_id) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            """
            SELECT * FROM import_rows
            WHERE tenant_id = ? AND project_id = ? AND job_id = ?
            ORDER BY row_number
            """,
            (tenant_id, project_id, job_id),
        )
    )


def _version(connection, tenant_id, project_id, job):
    version = get_version(connection, tenant_id, project_id, str(job["form_id"]), str(job["form_version_id"]))
    if version is None:
        raise ImportProblem("The published form for this import is no longer available.", 409)
    return version


def _mapping(job) -> dict[str, str | None]:
    parsed = json.loads(job["mapping_json"])
    if not isinstance(parsed, dict):
        raise ImportProblem("The column mapping is not valid.")
    mapping: dict[str, str | None] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not (value is None or isinstance(value, str)):
            raise ImportProblem("The column mapping is not valid.")
        mapping[key] = value or None
    return mapping


def _column_for(mapping: dict[str, str | None], field_key: str) -> str:
    for column, target in mapping.items():
        if target == field_key:
            return column
    return ""


def _with_error(evaluation, field: str, message: str) -> dict[str, object]:
    copied = dict(evaluation)
    copied["errors"] = [*list(evaluation["errors"]), {"field": field, "column": "", "message": message}]
    copied["expectation"] = "rejected"
    return copied


def _with_fields(evaluation, fields: dict[str, str]) -> dict[str, object]:
    copied = dict(evaluation)
    copied["errors"] = [*list(evaluation["errors"]), *[{"field": key, "column": "", "message": message} for key, message in fields.items()]]
    copied["expectation"] = "rejected"
    return copied


def _json_object(raw: object) -> dict[str, object]:
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, str) or not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _json_strings(raw: object) -> list[str]:
    if not isinstance(raw, str) or not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str)]


def _csv_cell(value: str) -> str:
    text = value.replace("\r", " ").replace("\n", " ")
    if text[:1] in {"=", "+", "-", "@", "\t"}:
        text = "'" + text
    if any(character in text for character in [",", '"']):
        return '"' + text.replace('"', '""') + '"'
    return text


def _busy(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA busy_timeout = 5000")


def _now() -> str:
    return datetime.now(UTC).isoformat()
