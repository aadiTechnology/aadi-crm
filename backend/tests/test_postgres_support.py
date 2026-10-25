"""PostgreSQL configuration, schema, and concurrency checks.

Integration tests run only when CRM_TEST_DATABASE_URL points at a disposable
PostgreSQL database. They are skipped otherwise. The SQLite suite does not
use that variable.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from uuid import uuid4

import pytest

from app.db import (
    POSTGRES_MIGRATIONS,
    apply_postgres_migrations,
    begin_immediate,
    connect,
    create_project,
    follow_up_due_date_expr,
    resolve_database,
    split_sql,
    translate_placeholders,
)
from app.followups_store import create_follow_up
from app.form_versions import _next_number, publish_form
from app.forms_store import add_field, create_form
from app.migrate import main
from app.records_store import create_record
from app.reminders_store import _claim, sync_follow_up_reminders

TENANT = "tenant-postgres"
USER = "user-postgres"


def test_sqlite_is_the_default_without_a_postgres_url(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CRM_DATABASE_URL", raising=False)
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "projects.sqlite"))
    target = resolve_database()
    assert target.dialect == "sqlite"
    assert target.label == "projects.sqlite"


def test_database_url_variable_does_not_select_postgres(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CRM_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://USER:secret-value@127.0.0.1:5432/aadi_platform")
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "projects.sqlite"))
    target = resolve_database()
    assert target.dialect == "sqlite"
    assert "secret-value" not in target.label


def test_explicit_postgres_url_selects_postgres(monkeypatch) -> None:
    monkeypatch.setenv("CRM_DATABASE_URL", "postgresql://USER:secret-value@127.0.0.1:5432/crm")
    monkeypatch.setenv("CRM_DATABASE_SSLMODE", "disable")
    target = resolve_database()
    assert target.dialect == "postgresql"
    assert target.database_name == "crm"
    assert target.sslmode == "disable"
    assert target.label == "crm"
    assert "secret-value" not in target.label


def test_invalid_postgres_configuration_fails_clearly(monkeypatch) -> None:
    monkeypatch.setenv("CRM_DATABASE_URL", "mysql://USER:secret-value@127.0.0.1:5432/crm")
    with pytest.raises(RuntimeError) as caught:
        resolve_database()
    assert "postgresql://" in str(caught.value)
    assert "secret-value" not in str(caught.value)


def test_sqlalchemy_postgres_url_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("CRM_DATABASE_URL", "postgresql+psycopg://USER:secret-value@127.0.0.1:5432/crm")
    with pytest.raises(RuntimeError) as caught:
        resolve_database()
    assert "postgresql://" in str(caught.value)
    assert "secret-value" not in str(caught.value)


def test_disable_ssl_is_rejected_for_a_remote_host(monkeypatch) -> None:
    monkeypatch.setenv("CRM_DATABASE_URL", "postgresql://USER:secret-value@db.example.com:5432/crm")
    monkeypatch.setenv("CRM_DATABASE_SSLMODE", "disable")
    with pytest.raises(RuntimeError) as caught:
        resolve_database()
    assert "loopback" in str(caught.value)
    assert "secret-value" not in str(caught.value)


def test_control_plane_database_name_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("CRM_DATABASE_URL", "postgresql://USER:secret-value@127.0.0.1:5432/aadi_platform")
    monkeypatch.setenv("CRM_DATABASE_SSLMODE", "disable")
    with pytest.raises(RuntimeError) as caught:
        resolve_database()
    assert "Control Plane" in str(caught.value)
    assert "secret-value" not in str(caught.value)


def test_connection_failure_does_not_fall_back_to_sqlite(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CRM_DATABASE_URL", "postgresql://USER:secret-value@127.0.0.1:1/crm")
    monkeypatch.setenv("CRM_DATABASE_SSLMODE", "disable")
    monkeypatch.setenv("CRM_DATABASE_PATH", str(tmp_path / "fallback.sqlite"))
    with pytest.raises(RuntimeError) as caught:
        connect()
    assert "SQLite was not used" in str(caught.value)
    assert "secret-value" not in str(caught.value)
    assert (tmp_path / "fallback.sqlite").exists() is False


def test_api_connection_does_not_migrate_when_postgres_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("CRM_DATABASE_URL", "postgresql://USER:secret-value@127.0.0.1:1/crm")
    monkeypatch.setenv("CRM_DATABASE_SSLMODE", "disable")
    calls = {"sqlite": 0, "postgres": 0}
    monkeypatch.setattr("app.api.projects.apply_migrations", lambda *_args, **_kwargs: calls.__setitem__("sqlite", 1))
    monkeypatch.setattr(
        "app.db.apply_postgres_migrations",
        lambda *_args, **_kwargs: calls.__setitem__("postgres", 1),
    )
    from app.api.projects import get_connection

    with pytest.raises(RuntimeError) as caught:
        next(get_connection())
    assert calls == {"sqlite": 0, "postgres": 0}
    assert "secret-value" not in str(caught.value)


def test_migrate_command_refuses_to_run_without_a_postgres_url(monkeypatch) -> None:
    monkeypatch.delenv("CRM_DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as caught:
        main()
    assert "SQLite was not opened" in str(caught.value)


def test_placeholder_translation_ignores_quoted_question_marks() -> None:
    assert translate_placeholders("SELECT ? WHERE note = '?'") == "SELECT %s WHERE note = '?'"


def test_postgres_migration_script_splits_the_trigger_function() -> None:
    script = (POSTGRES_MIGRATIONS / "004_form_versions.sql").read_text(encoding="utf-8")
    statements = split_sql(script)
    functions = [
        statement
        for statement in statements
        if "crm_form_versions_immutable" in statement and "RAISE EXCEPTION" in statement
    ]
    assert len(functions) == 1
    assert "RAISE(ABORT" not in script


def test_sqlite_due_date_uses_the_kolkata_offset(tmp_path) -> None:
    connection = connect(tmp_path / "due.sqlite")
    connection.execute("CREATE TABLE follow_ups (due_at TEXT)")
    connection.execute(
        "INSERT INTO follow_ups (due_at) VALUES (?)",
        ("2026-10-20T18:30:00.000000+00:00",),
    )
    row = connection.execute(
        f"SELECT {follow_up_due_date_expr(connection)} AS due_date FROM follow_ups"
    ).fetchone()
    assert row is not None
    assert row["due_date"] == "2026-10-21"
    connection.close()


@pytest.fixture
def postgres_connection(monkeypatch):
    url = os.environ.get("CRM_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("CRM_TEST_DATABASE_URL is not set")
    monkeypatch.setenv("CRM_DATABASE_URL", url)
    monkeypatch.setenv("CRM_DATABASE_SSLMODE", os.environ.get("CRM_TEST_DATABASE_SSLMODE", "disable"))
    apply_postgres_migrations()
    apply_postgres_migrations()
    connection = connect()
    try:
        yield connection
    finally:
        connection.close()


def test_postgres_schema_tracks_migrations_and_constraints(postgres_connection) -> None:
    versions = [
        row["version"]
        for row in postgres_connection.execute(
            "SELECT version FROM crm_schema_migrations ORDER BY version"
        )
    ]
    assert versions == [
        "001_projects.sql",
        "002_project_memberships.sql",
        "003_form_definitions.sql",
        "004_form_versions.sql",
        "005_records.sql",
        "006_followups.sql",
        "007_reminders.sql",
        "008_imports.sql",
    ]
    partial = postgres_connection.execute(
        """
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'uq_project_memberships_one_active_user'
        """
    ).fetchone()
    assert partial is not None
    assert "status" in partial["indexdef"] and "active" in partial["indexdef"]
    folded = postgres_connection.execute(
        """
        SELECT indexdef FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'uq_projects_tenant_lower_code'
        """
    ).fetchone()
    assert folded is not None
    assert "lower" in folded["indexdef"].lower()
    triggers = postgres_connection.execute(
        """
        SELECT tgname FROM pg_trigger
        WHERE tgname IN ('form_versions_immutable_update', 'form_versions_immutable_delete')
        ORDER BY tgname
        """
    ).fetchall()
    assert [row["tgname"] for row in triggers] == [
        "form_versions_immutable_delete",
        "form_versions_immutable_update",
    ]
    with pytest.raises(sqlite3.IntegrityError):
        postgres_connection.execute(
            """
            INSERT INTO project_memberships (
                id, tenant_id, project_id, user_id, role, scope_policy, status,
                created_by, updated_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'project_manager', 'project', 'active', ?, ?, ?, ?)
            """,
            ("mem-missing", TENANT, "missing-project", USER, USER, USER, "2026-10-22T00:00:00+00:00", "2026-10-22T00:00:00+00:00"),
        )
    postgres_connection.rollback()


def test_postgres_published_form_version_is_immutable(postgres_connection) -> None:
    project = create_project(
        postgres_connection,
        tenant_id=TENANT,
        code=f"IMM-{uuid4().hex[:8]}",
        name="Immutable",
        description="",
        created_by=USER,
    )
    form = create_form(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        name=f"Form {uuid4().hex[:8]}",
        description="",
        actor_id=USER,
    )
    add_field(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        form_id=form.id,
        field_key="school_name",
        label="School",
        field_type="text",
        required=True,
        help_text="",
        section_name="",
        config={},
        actor_id=USER,
    )
    published = publish_form(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        form_id=form.id,
        actor_id=USER,
    )
    assert published is not None
    with pytest.raises(Exception) as update_error:
        postgres_connection.execute(
            "UPDATE form_versions SET schema_json = ? WHERE id = ?",
            ('{"changed":true}', published.id),
        )
    assert "published form version is immutable" in str(update_error.value)
    postgres_connection.rollback()
    with pytest.raises(Exception) as delete_error:
        postgres_connection.execute("DELETE FROM form_versions WHERE id = ?", (published.id,))
    assert "published form version is immutable" in str(delete_error.value)
    postgres_connection.rollback()


def test_postgres_concurrent_record_numbers(postgres_connection) -> None:
    project = create_project(
        postgres_connection,
        tenant_id=TENANT,
        code=f"N{uuid4().hex[:6]}",
        name="Numbers",
        description="",
        created_by=USER,
    )
    form = create_form(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        name="Number form",
        description="",
        actor_id=USER,
    )
    add_field(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        form_id=form.id,
        field_key="school_name",
        label="School",
        field_type="text",
        required=True,
        help_text="",
        section_name="",
        config={},
        actor_id=USER,
    )
    published = publish_form(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        form_id=form.id,
        actor_id=USER,
    )
    assert published is not None
    barrier = threading.Barrier(2)
    numbers: list[str] = []
    errors: list[BaseException] = []
    guard = threading.Lock()

    def worker(name: str) -> None:
        connection = connect()
        try:
            barrier.wait(timeout=5)
            created = create_record(
                connection,
                tenant_id=TENANT,
                project_id=project.id,
                project_code=project.code,
                form_id=form.id,
                actor_id=USER,
                source="manual",
                values={"school_name": name},
            )
            assert created is not None
            with guard:
                numbers.append(str(created["public_number"]))
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=("One",)), threading.Thread(target=worker, args=("Two",))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == []
    assert sorted(numbers) == [f"{project.code}-0001", f"{project.code}-0002"]


def test_postgres_concurrent_form_version_numbers(postgres_connection) -> None:
    project = create_project(
        postgres_connection,
        tenant_id=TENANT,
        code=f"VER-{uuid4().hex[:6]}",
        name="Versions",
        description="",
        created_by=USER,
    )
    form = create_form(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        name=f"Version form {uuid4().hex[:6]}",
        description="",
        actor_id=USER,
    )
    barrier = threading.Barrier(2)
    numbers: list[int] = []
    errors: list[BaseException] = []

    def worker(marker: str) -> None:
        connection = connect()
        previous = connection.isolation_level
        connection.isolation_level = None
        try:
            barrier.wait(timeout=5)
            begin_immediate(connection, f"form-version:{form.id}")
            number = _next_number(connection, form.id)
            connection.execute(
                """
                INSERT INTO form_versions (
                    id, tenant_id, project_id, form_id, version_number, schema_json, published_by, published_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    TENANT,
                    project.id,
                    form.id,
                    number,
                    f'{{"name":"{marker}"}}',
                    USER,
                    "2026-10-22T00:00:00+00:00",
                ),
            )
            connection.commit()
            numbers.append(number)
        except BaseException as exc:
            errors.append(exc)
            connection.rollback()
        finally:
            connection.isolation_level = previous
            connection.close()

    threads = [threading.Thread(target=worker, args=("one",)), threading.Thread(target=worker, args=("two",))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == []
    assert sorted(numbers) == [1, 2]


def test_postgres_concurrent_reminder_claim_is_single_winner(postgres_connection) -> None:
    project = create_project(
        postgres_connection,
        tenant_id=TENANT,
        code=f"REM-{uuid4().hex[:6]}",
        name="Reminders",
        description="",
        created_by=USER,
    )
    form = create_form(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        name=f"Reminder form {uuid4().hex[:6]}",
        description="",
        actor_id=USER,
    )
    add_field(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        form_id=form.id,
        field_key="school_name",
        label="School",
        field_type="text",
        required=True,
        help_text="",
        section_name="",
        config={},
        actor_id=USER,
    )
    publish_form(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        form_id=form.id,
        actor_id=USER,
    )
    record = create_record(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        project_code=project.code,
        form_id=form.id,
        actor_id=USER,
        source="manual",
        values={"school_name": "North"},
    )
    assert record is not None
    follow_up = create_follow_up(
        postgres_connection,
        tenant_id=TENANT,
        project_id=project.id,
        record_id=str(record["id"]),
        actor_id=USER,
        task_type="note",
        owner_user_id=USER,
        due_date="2026-10-21",
        due_time="10:00",
        summary="Call the school",
        call_status=None,
    )
    assert follow_up is not None
    sync_follow_up_reminders(
        postgres_connection,
        tenant_id=TENANT,
        follow_up=follow_up,
        recipient_email=None,
    )
    kept = postgres_connection.execute(
        """
        SELECT id FROM reminder_deliveries
        WHERE tenant_id = ? AND state = 'pending'
        ORDER BY id
        LIMIT 1
        """,
        (TENANT,),
    ).fetchone()
    assert kept is not None
    postgres_connection.execute(
        """
        UPDATE reminder_deliveries
        SET state = 'sent'
        WHERE tenant_id = ? AND id <> ? AND state = 'pending'
        """,
        (TENANT, kept["id"]),
    )
    postgres_connection.commit()
    barrier = threading.Barrier(2)
    claimed: list[str | None] = []
    errors: list[BaseException] = []

    def worker() -> None:
        connection = connect()
        try:
            barrier.wait(timeout=5)
            row = _claim(connection, TENANT, "2999-01-01T00:00:00.000000+00:00", "recipient_user_id = ?", [USER], [])
            claimed.append(None if row is None else str(row["id"]))
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert errors == []
    assert sorted(claimed, key=lambda value: value is None) == [kept["id"], None]


def test_postgres_due_date_uses_the_kolkata_offset(postgres_connection) -> None:
    expression = follow_up_due_date_expr(postgres_connection).replace("follow_ups.due_at", "?")
    assert "330 minutes" in expression

    def civil_date(stamp: str) -> str:
        row = postgres_connection.execute(
            f"SELECT ({expression})::text AS due_date",
            (stamp,),
        ).fetchone()
        assert row is not None
        return str(row["due_date"])

    assert civil_date("2026-10-20T18:30:00.000000+00:00") == "2026-10-21"
    assert civil_date("2026-10-20T18:29:00.000000+00:00") == "2026-10-20"
    postgres_connection.rollback()
