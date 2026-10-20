"""Published form versions stay immutable and inside the authorized project."""

import sqlite3
import threading
from pathlib import Path

from app.db import MIGRATIONS, apply_migrations, connect
from app.form_versions import DuplicatePublish, publish_form
from app.project_access import access_for
from tests.test_forms import DEV_DATABASE, _dropdown, _project, _snapshot, _text_field
from tests.test_projects import LEADS, MANAGE, OTHER_ID, TENANT_A, TENANT_B, USER_ID, FakePlatform, _allow, _become, _client, _headers, _person


def _form(client, project_id: str, name: str = "Enquiry draft") -> str:
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": name, "description": "Internal enquiry"},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "draft"
    assert created.json()["current_published_version_id"] is None
    return created.json()["id"]


def _add(client, project_id: str, form_id: str, payload: dict) -> dict:
    response = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def _publish(client, project_id: str, form_id: str, *, body: dict | None = None):
    return client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions",
        headers=_headers(write=True),
        json=body,
    )


def _versions(path: Path) -> list[tuple]:
    connection = connect(path)
    rows = connection.execute(
        "SELECT id, version_number, schema_json, published_by FROM form_versions ORDER BY version_number"
    ).fetchall()
    pointer = connection.execute(
        "SELECT current_published_version_id FROM form_definitions"
    ).fetchall()
    connection.close()
    return [(row["id"], row["version_number"], row["schema_json"], row["published_by"]) for row in rows], [
        row["current_published_version_id"] for row in pointer
    ]


def test_publish_permissions_follow_project_role() -> None:
    manager = access_for(role="project_manager", status="active", permission_keys=[LEADS])
    member = access_for(role="project_member", status="active", permission_keys=[LEADS])
    stranger = access_for(role=None, status=None, permission_keys=[LEADS])
    assert manager.allows("preview_forms") is True
    assert manager.allows("publish_forms") is True
    assert manager.allows("render_forms") is True
    assert member.allows("render_forms") is True
    assert member.allows("preview_forms") is False
    assert member.allows("publish_forms") is False
    assert stranger.allows("render_forms") is False


def test_publish_versions_stay_immutable_and_a_new_draft_copies_the_snapshot(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client)
    form_id = _form(client, project_id)
    empty = _publish(client, project_id, form_id)
    assert empty.status_code == 422
    assert empty.json()["error"]["message"] == "Add at least one field before publishing."
    _add(client, project_id, form_id, _text_field())
    _add(client, project_id, form_id, _dropdown())
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    ids = [field["id"] for field in listed.json()["fields"]]
    reordered = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/reorder",
        headers=_headers(write=True),
        json={"field_ids": [ids[1], ids[0]]},
    )
    assert [field["field_key"] for field in reordered.json()["fields"]] == ["priority", "school_name"]

    ignored = _publish(client, project_id, form_id, body={"published_by": "attacker", "tenant_id": "other"})
    assert ignored.status_code == 201
    first = ignored.json()
    assert first["version_number"] == 1
    assert first["status"] == "current"
    assert first["published_by"] == USER_ID
    assert first["published_by"] != "attacker"
    assert [field["field_key"] for field in first["fields"]] == ["priority", "school_name"]
    assert first["fields"][0]["options"][0] == {"value": "hot", "label": "Hot"}
    assert first["fields"][1]["required"] is True
    assert "id" not in first["fields"][0]

    school = next(field for field in reordered.json()["fields"] if field["field_key"] == "school_name")
    edited = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{school['id']}",
        headers=_headers(write=True),
        json={
            "label": "Campus",
            "field_type": "text",
            "required": False,
            "help_text": "Short name",
            "section_name": "Contact",
            "max_length": 40,
        },
    )
    assert edited.status_code == 200
    preview = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/preview",
        headers=_headers(write=False),
    )
    assert preview.status_code == 200
    assert preview.json()["source"] == "draft"
    preview_school = next(field for field in preview.json()["fields"] if field["field_key"] == "school_name")
    assert preview_school["label"] == "Campus"
    stored = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions/{first['id']}",
        headers=_headers(write=False),
    )
    assert stored.status_code == 200
    assert stored.json()["version_number"] == 1
    assert stored.json()["status"] == "current"
    stored_school = next(field for field in stored.json()["fields"] if field["field_key"] == "school_name")
    assert stored_school["label"] == "School name"
    assert stored_school["required"] is True
    assert stored_school["max_length"] == 120

    path = tmp_path / "projects.sqlite"
    before_rows, _pointers = _versions(path)
    second = _publish(client, project_id, form_id)
    assert second.status_code == 201
    assert second.json()["version_number"] == 2
    assert second.json()["status"] == "current"
    assert second.json()["fields"][1]["label"] == "Campus"
    again = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions/{first['id']}",
        headers=_headers(write=False),
    )
    assert again.json()["fields"][1]["label"] == "School name"
    assert again.json()["status"] == "published"
    after_rows, pointers = _versions(path)
    assert after_rows[0][2] == before_rows[0][2]
    assert pointers == [second.json()["id"]]

    duplicate = _publish(client, project_id, form_id)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["message"] == "This draft is already published."
    unchanged, _pointers = _versions(path)
    assert [row[1] for row in unchanged] == [1, 2]

    replaced = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/draft",
        headers=_headers(write=True),
    )
    assert replaced.status_code == 200
    assert [field["field_key"] for field in replaced.json()["fields"]] == ["priority", "school_name"]
    restored = next(field for field in replaced.json()["fields"] if field["field_key"] == "school_name")
    assert restored["label"] == "Campus"
    assert restored["required"] is False
    assert replaced.json()["fields"][0]["options"][2]["label"] == "Cold"
    assert replaced.json()["current_published_version_number"] == 2
    snapshot_after_replace, _pointers = _versions(path)
    assert [row[2] for row in snapshot_after_replace] == [row[2] for row in unchanged]

    blocked = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions/{first['id']}",
        headers=_headers(write=True),
        json={"name": "Changed"},
    )
    assert blocked.status_code == 405
    connection = connect(path)
    with __import__("pytest").raises(sqlite3.IntegrityError):
        connection.execute("UPDATE form_versions SET schema_json = '{}' WHERE id = ?", (first["id"],))
    with __import__("pytest").raises(sqlite3.IntegrityError):
        connection.execute("DELETE FROM form_versions WHERE id = ?", (first["id"],))
    connection.rollback()
    records = connection.execute("SELECT COUNT(*) AS count FROM records").fetchone()
    assert records["count"] == 0
    connection.close()
    final_rows, _pointers = _versions(path)
    assert final_rows[0][2] == before_rows[0][2]


def test_invalid_and_failed_publish_do_not_leave_a_version(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client)
    form_id = _form(client, project_id, name="Broken draft")
    _add(client, project_id, form_id, _dropdown())
    path = tmp_path / "projects.sqlite"
    connection = connect(path)
    connection.execute(
        "UPDATE form_fields SET config_json = '{}' WHERE form_id = ? AND field_key = 'priority'",
        (form_id,),
    )
    connection.commit()
    connection.close()
    rejected = _publish(client, project_id, form_id)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["message"] == "A picklist field needs at least one option before publishing."
    rows, pointers = _versions(path)
    assert rows == []
    assert pointers == [None]

    fixed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    field_id = fixed.json()["fields"][0]["id"]
    repaired = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{field_id}",
        headers=_headers(write=True),
        json={
            "label": "Priority",
            "field_type": "dropdown",
            "required": False,
            "section_name": "Qualification",
            "options": [
                {"value": "hot", "label": "Hot"},
                {"value": "warm", "label": "Warm"},
                {"value": "cold", "label": "Cold"},
            ],
            "default_value": "warm",
        },
    )
    assert repaired.status_code == 200

    def fail(_connection) -> None:
        raise RuntimeError("stop before commit")

    store = connect(path)
    try:
        raised = False
        try:
            publish_form(
                store,
                tenant_id=str(TENANT_A),
                project_id=project_id,
                form_id=form_id,
                actor_id=USER_ID,
                before_commit=fail,
            )
        except RuntimeError:
            raised = True
        assert raised is True
    finally:
        store.close()
    rows, pointers = _versions(path)
    assert rows == []
    assert pointers == [None]
    published = _publish(client, project_id, form_id)
    assert published.status_code == 201
    assert published.json()["version_number"] == 1


def test_concurrent_publish_cannot_duplicate_the_version_number(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client)
    form_id = _form(client, project_id, name="Concurrent")
    _add(client, project_id, form_id, _text_field())
    path = tmp_path / "projects.sqlite"
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    guard = threading.Lock()

    def worker() -> None:
        connection = connect(path)
        try:
            barrier.wait(timeout=5)
            try:
                publish_form(
                    connection,
                    tenant_id=str(TENANT_A),
                    project_id=project_id,
                    form_id=form_id,
                    actor_id=USER_ID,
                )
                outcome = "ok"
            except DuplicatePublish:
                outcome = "dup"
            with guard:
                outcomes.append(outcome)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert thread.is_alive() is False
    assert sorted(outcomes) == ["dup", "ok"]
    rows, pointers = _versions(path)
    assert [row[1] for row in rows] == [1]
    assert pointers == [rows[0][0]]
    connection = connect(path)
    try:
        connection.execute(
            """
            INSERT INTO form_versions (
                id, tenant_id, project_id, form_id, version_number, schema_json, published_by, published_at
            ) VALUES ('other-version', ?, ?, ?, 1, '{"name":"x","description":"","fields":[]}', ?, 't')
            """,
            (str(TENANT_A), project_id, form_id, USER_ID),
        )
        inserted = True
    except sqlite3.IntegrityError:
        inserted = False
    connection.rollback()
    connection.close()
    assert inserted is False
    rows_after, pointers_after = _versions(path)
    assert rows_after == rows
    assert pointers_after == pointers


def test_render_is_limited_to_the_authorized_project(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com"),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client, name="Secret North")
    other_project = _project(client, code="S-2", name="South yard")
    form_id = _form(client, project_id, name="Secret form")
    _add(client, project_id, form_id, _text_field("secret_key", "Secret label"))
    published = _publish(client, project_id, form_id)
    version_id = published.json()["id"]
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    membership_id = added.json()["id"]

    _become(platform, OTHER_ID, "member@example.com")
    rendered = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions/{version_id}",
        headers=_headers(write=False),
    )
    assert rendered.status_code == 200
    assert rendered.json()["fields"][0]["label"] == "Secret label"
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions",
        headers=_headers(write=False),
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["version_number"] == 1
    preview = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/preview",
        headers=_headers(write=False),
    )
    assert preview.status_code == 403
    assert "Secret label" not in preview.text
    publish = _publish(client, project_id, form_id)
    assert publish.status_code == 403
    assert "Secret form" not in publish.text
    draft = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/draft",
        headers=_headers(write=True),
    )
    assert draft.status_code == 403
    still = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    assert still.status_code == 200
    assert still.json()["fields"][0]["field_key"] == "secret_key"

    _become(platform, USER_ID, "manager@example.com")
    archived = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive",
        headers=_headers(write=True),
    )
    assert archived.status_code == 200
    _add(client, project_id, form_id, _text_field("gate_note", "Gate note"))
    archived_publish = _publish(client, project_id, form_id)
    assert archived_publish.status_code == 201
    assert archived_publish.json()["version_number"] == 2
    _become(platform, OTHER_ID, "member@example.com")
    member_archived = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions/{version_id}",
        headers=_headers(write=False),
    )
    assert member_archived.status_code == 200
    assert member_archived.json()["fields"][0]["label"] == "Secret label"
    member_publish = _publish(client, project_id, form_id)
    assert member_publish.status_code == 403

    _become(platform, USER_ID, "manager@example.com")
    removed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{membership_id}/remove",
        headers=_headers(write=True),
    )
    assert removed.status_code == 200
    _become(platform, OTHER_ID, "member@example.com")
    hidden = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions/{version_id}",
        headers=_headers(write=False),
    )
    assert hidden.status_code == 404
    assert "Secret form" not in hidden.text
    assert "Secret label" not in hidden.text

    _become(platform, "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "stranger@example.com")
    stranger = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions/{version_id}",
        headers=_headers(write=False),
    )
    assert stranger.status_code == 404
    assert "Secret label" not in stranger.text

    _become(platform, USER_ID, "manager@example.com")
    cross_project = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{other_project}/forms/{form_id}/versions/{version_id}",
        headers=_headers(write=False),
    )
    assert cross_project.status_code == 404
    assert "Secret form" not in cross_project.text
    cross_tenant = client.get(
        f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/forms/{form_id}/versions/{version_id}",
        headers=_headers(write=False),
    )
    assert cross_tenant.status_code == 404
    assert "Secret North" not in cross_tenant.text
    platform.permissions_by_tenant[str(TENANT_A)] = ["users.read"]
    _become(platform, USER_ID, "manager@example.com")
    denied = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions",
        headers=_headers(write=False),
    )
    assert denied.status_code == 403
    assert "Secret form" not in denied.text

    missing = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/versions",
        headers={"cookie": "aadi_session=member"},
    )
    assert missing.status_code == 401


def test_version_migration_preserves_drafts_and_leaves_room_for_a_record_reference(tmp_path) -> None:
    path = tmp_path / "before-versions.sqlite"
    connection = connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    for name in ("001_projects.sql", "002_project_memberships.sql", "003_form_definitions.sql"):
        connection.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO crm_schema_migrations (version, applied_at) VALUES (?, ?)",
            (name, "2026-10-20T00:00:00+00:00"),
        )
    connection.execute(
        """
        INSERT INTO projects (
            id, tenant_id, code, name, description, status, created_by, created_at, updated_at
        ) VALUES ('active-1', ?, 'LIVE', 'Live gate', '', 'active', ?, 't', 't')
        """,
        (str(TENANT_A), USER_ID),
    )
    connection.execute(
        """
        INSERT INTO form_definitions (
            id, tenant_id, project_id, name, description, status, created_by, updated_by, created_at, updated_at
        ) VALUES ('form-1', ?, 'active-1', 'Enquiry draft', '', 'draft', ?, ?, 't', 't')
        """,
        (str(TENANT_A), USER_ID, USER_ID),
    )
    connection.execute(
        """
        INSERT INTO form_fields (
            id, tenant_id, project_id, form_id, field_key, label, field_type, required,
            help_text, section_name, position, config_json, created_at, updated_at
        ) VALUES (
            'field-1', ?, 'active-1', 'form-1', 'school_name', 'School name', 'text', 1,
            '', 'Contact', 0, '{"max_length":120}', 't', 't'
        )
        """,
        (str(TENANT_A),),
    )
    connection.commit()
    connection.close()
    apply_migrations(path)
    apply_migrations(path)
    connection = connect(path)
    form = connection.execute(
        "SELECT name, status, current_published_version_id FROM form_definitions WHERE id = 'form-1'"
    ).fetchone()
    field = connection.execute("SELECT field_key, position FROM form_fields WHERE id = 'field-1'").fetchone()
    versions = connection.execute("SELECT COUNT(*) AS count FROM form_versions").fetchone()
    applied = {
        row["version"]
        for row in connection.execute("SELECT version FROM crm_schema_migrations")
    }
    record_count = connection.execute("SELECT COUNT(*) AS count FROM records").fetchone()
    connection.close()
    assert form["name"] == "Enquiry draft"
    assert form["status"] == "draft"
    assert form["current_published_version_id"] is None
    assert field["field_key"] == "school_name"
    assert field["position"] == 0
    assert versions["count"] == 0
    assert "004_form_versions.sql" in applied
    assert "005_records.sql" in applied
    assert record_count["count"] == 0


def test_development_copy_gains_versions_without_changing_the_original(tmp_path) -> None:
    if not DEV_DATABASE.exists():
        return
    source_before = _snapshot(DEV_DATABASE)
    source_forms = _form_ids(DEV_DATABASE)
    target = tmp_path / "dev-copy.sqlite"
    import shutil

    shutil.copy(DEV_DATABASE, target)
    apply_migrations(target)
    source_after = _snapshot(DEV_DATABASE)
    assert source_after == source_before
    assert _form_ids(DEV_DATABASE) == source_forms
    copied = connect(target)
    versions = {
        row["version"]
        for row in copied.execute("SELECT version FROM crm_schema_migrations")
    }
    copied_forms = [row["id"] for row in copied.execute("SELECT id FROM form_definitions ORDER BY id")]
    copied.close()
    assert "004_form_versions.sql" in versions
    assert copied_forms == source_forms


def _form_ids(path: Path) -> list[str]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    tables = {
        row["name"]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if "form_definitions" not in tables:
        connection.close()
        return []
    rows = [row["id"] for row in connection.execute("SELECT id FROM form_definitions ORDER BY id")]
    connection.close()
    return rows
