"""Form definitions stay inside the authorized project. Platform calls use an in-process double."""

import shutil
import sqlite3
from pathlib import Path

from app.db import MIGRATIONS, apply_migrations, connect
from app.project_access import access_for
from tests.test_projects import (
    LEADS,
    MANAGE,
    OTHER_ID,
    TENANT_A,
    TENANT_B,
    USER_ID,
    FakePlatform,
    _allow,
    _become,
    _client,
    _headers,
    _person,
)

DEV_DATABASE = Path(__file__).resolve().parents[1] / "data" / "aadi_crm.sqlite"


def _project(client, *, code: str = "N-1", name: str = "North yard") -> str:
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": code, "name": name, "description": ""},
    )
    assert created.status_code == 201
    return created.json()["id"]


def _text_field(key: str = "school_name", label: str = "School name") -> dict:
    return {
        "field_key": key,
        "label": label,
        "field_type": "text",
        "required": True,
        "help_text": "Legal name",
        "section_name": "Contact",
        "max_length": 120,
    }


def _dropdown() -> dict:
    return {
        "field_key": "priority",
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
    }


def _snapshot(path: Path) -> dict[str, list]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    projects = [
        (row["id"], row["tenant_id"], row["code"], row["status"])
        for row in connection.execute("SELECT id, tenant_id, code, status FROM projects ORDER BY id")
    ]
    memberships = [
        (row["id"], row["project_id"], row["user_id"], row["role"], row["status"])
        for row in connection.execute(
            "SELECT id, project_id, user_id, role, status FROM project_memberships ORDER BY id"
        )
    ]
    versions = [
        row["version"]
        for row in connection.execute("SELECT version FROM crm_schema_migrations ORDER BY version")
    ]
    connection.close()
    return {"projects": projects, "memberships": memberships, "versions": versions}


def test_manager_and_member_form_permissions() -> None:
    manager = access_for(role="project_manager", status="active", permission_keys=[LEADS])
    member = access_for(role="project_member", status="active", permission_keys=[LEADS])
    stranger = access_for(role=None, status=None, permission_keys=[LEADS])
    admin = access_for(role=None, status=None, permission_keys=[MANAGE])
    assert manager.allows("manage_forms") is True
    assert manager.allows("view_forms") is True
    assert manager.as_dict()["can_manage_forms"] is True
    assert member.allows("view_forms") is True
    assert member.allows("manage_forms") is False
    assert member.as_dict()["can_manage_forms"] is False
    assert stranger.allows("view_forms") is False
    assert admin.allows("manage_forms") is True


def test_form_migration_preserves_projects_memberships_and_archive_state(tmp_path) -> None:
    path = tmp_path / "before-forms.sqlite"
    connection = connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    for name in ("001_projects.sql", "002_project_memberships.sql"):
        connection.executescript((MIGRATIONS / name).read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO crm_schema_migrations (version, applied_at) VALUES (?, ?)",
            (name, "2026-10-19T00:00:00+00:00"),
        )
    connection.execute(
        """
        INSERT INTO projects (
            id, tenant_id, code, name, description, status, created_by, created_at, updated_at
        ) VALUES
            ('active-1', ?, 'LIVE', 'Live gate', '', 'active', ?, 't', 't'),
            ('archived-1', ?, 'OLD', 'Old gate', '', 'archived', ?, 't', 't')
        """,
        (str(TENANT_A), USER_ID, str(TENANT_A), USER_ID),
    )
    connection.execute(
        """
        INSERT INTO project_memberships (
            id, tenant_id, project_id, user_id, role, scope_policy, status,
            created_by, updated_by, created_at, updated_at
        ) VALUES
            ('m-1', ?, 'active-1', ?, 'project_manager', 'project', 'active', ?, ?, 't', 't'),
            ('m-2', ?, 'archived-1', ?, 'project_member', 'assigned', 'removed', ?, ?, 't', 't')
        """,
        (str(TENANT_A), USER_ID, USER_ID, USER_ID, str(TENANT_A), OTHER_ID, USER_ID, USER_ID),
    )
    connection.commit()
    connection.close()
    before = _snapshot(path)
    apply_migrations(path)
    apply_migrations(path)
    after = _snapshot(path)
    assert after["projects"] == before["projects"]
    assert after["memberships"] == before["memberships"]
    assert "003_form_definitions.sql" in after["versions"]
    checked = connect(path)
    forms = checked.execute("SELECT COUNT(*) AS count FROM form_definitions").fetchone()
    assert forms is not None
    assert forms["count"] == 0
    checked.close()


def test_development_database_copy_keeps_rows_and_leaves_the_original_unchanged(tmp_path) -> None:
    if not DEV_DATABASE.exists():
        return
    source_before = _snapshot(DEV_DATABASE)
    target = tmp_path / "dev-copy.sqlite"
    shutil.copy(DEV_DATABASE, target)
    apply_migrations(target)
    source_after = _snapshot(DEV_DATABASE)
    copied = _snapshot(target)
    assert source_after == source_before
    assert copied["projects"] == source_before["projects"]
    assert copied["memberships"] == source_before["memberships"]
    assert "003_form_definitions.sql" in copied["versions"]


def test_create_fields_reorder_reload_and_validation(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client)
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": "Enquiry draft", "description": "Internal enquiry"},
    )
    assert created.status_code == 201
    form = created.json()
    assert form["status"] == "draft"
    assert form["fields"] == []
    form_id = form["id"]
    duplicate_name = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": "enquiry draft"},
    )
    assert duplicate_name.status_code == 409
    missing_name = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": "  "},
    )
    assert missing_name.status_code == 422
    first = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json=_text_field(),
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json=_dropdown(),
    )
    assert second.status_code == 201
    assert [field["field_key"] for field in second.json()["fields"]] == ["school_name", "priority"]
    assert second.json()["fields"][1]["options"][0]["label"] == "Hot"
    assert second.json()["fields"][1]["default_value"] == "warm"
    duplicate_key = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json=_text_field(),
    )
    assert duplicate_key.status_code == 409
    assert duplicate_key.json()["error"]["message"] == "Field identifier is already used on this form."
    invalid_type = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json={**_text_field("source", "Source"), "field_type": "workflow"},
    )
    assert invalid_type.status_code == 422
    assert invalid_type.json()["error"]["message"] == "Field type is not supported."
    empty_options = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json={
            "field_key": "source",
            "label": "Source",
            "field_type": "dropdown",
            "required": True,
            "options": [],
        },
    )
    assert empty_options.status_code == 422
    bad_range = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json={
            "field_key": "amount",
            "label": "Amount",
            "field_type": "number",
            "required": False,
            "min_value": 10,
            "max_value": 2,
        },
    )
    assert bad_range.status_code == 422
    ids = [field["id"] for field in second.json()["fields"]]
    reordered = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/reorder",
        headers=_headers(write=True),
        json={"field_ids": [ids[1], ids[0]]},
    )
    assert reordered.status_code == 200
    assert [field["field_key"] for field in reordered.json()["fields"]] == ["priority", "school_name"]
    assert [field["position"] for field in reordered.json()["fields"]] == [0, 1]
    partial = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/reorder",
        headers=_headers(write=True),
        json={"field_ids": [ids[0]]},
    )
    assert partial.status_code == 422
    reloaded = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    assert reloaded.status_code == 200
    assert [field["field_key"] for field in reloaded.json()["fields"]] == ["priority", "school_name"]
    school = next(field for field in reloaded.json()["fields"] if field["field_key"] == "school_name")
    changed_key = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{school['id']}",
        headers=_headers(write=True),
        json={**_text_field("renamed", "School"), "field_key": "renamed"},
    )
    assert changed_key.status_code == 422
    assert changed_key.json()["error"]["message"] == "Field identifier cannot be changed."
    edited = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{school['id']}",
        headers=_headers(write=True),
        json={
            "label": "School",
            "field_type": "text",
            "required": True,
            "help_text": "Campus name",
            "section_name": "Contact",
            "max_length": 80,
        },
    )
    assert edited.status_code == 200
    school = next(field for field in edited.json()["fields"] if field["field_key"] == "school_name")
    assert school["label"] == "School"
    assert school["max_length"] == 80
    removed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{school['id']}/remove",
        headers=_headers(write=True),
    )
    assert removed.status_code == 200
    assert [field["field_key"] for field in removed.json()["fields"]] == ["priority"]
    assert removed.json()["fields"][0]["position"] == 0
    renamed = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=True),
        json={"name": "Enquiry", "description": "Updated"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Enquiry"
    missing_csrf = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers={"cookie": "aadi_session=member"},
        json={"name": "Other"},
    )
    assert missing_csrf.status_code == 401


def test_member_archived_and_scope_boundaries(tmp_path, monkeypatch) -> None:
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
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": "Secret form"},
    )
    form_id = created.json()["id"]
    client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json=_text_field("secret_key", "Secret label"),
    )
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201

    _become(platform, OTHER_ID, "member@example.com")
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=False),
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["name"] == "Secret form"
    blocked = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": "Member form"},
    )
    assert blocked.status_code == 403
    assert "Secret form" not in blocked.text
    blocked_field = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
        headers=_headers(write=True),
        json=_text_field("member_key", "Member label"),
    )
    assert blocked_field.status_code == 403
    still = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    assert [field["field_key"] for field in still.json()["fields"]] == ["secret_key"]

    _become(platform, "dddddddd-dddd-4ddd-8ddd-dddddddddddd", "stranger@example.com")
    hidden = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    assert hidden.status_code == 404
    assert "Secret form" not in hidden.text
    assert "Secret label" not in hidden.text

    _become(platform, USER_ID, "manager@example.com")
    cross_project = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{other_project}/forms/{form_id}",
        headers=_headers(write=False),
    )
    assert cross_project.status_code == 404
    assert "Secret form" not in cross_project.text
    assert "secret_key" not in cross_project.text
    other_list = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{other_project}/forms",
        headers=_headers(write=False),
    )
    assert other_list.status_code == 200
    assert other_list.json()["items"] == []

    cross_tenant = client.get(
        f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    assert cross_tenant.status_code == 404
    assert "Secret form" not in cross_tenant.text
    assert "Secret North" not in cross_tenant.text

    platform.permissions_by_tenant[str(TENANT_A)] = ["users.read"]
    denied = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=False),
    )
    assert denied.status_code == 403
    assert "Secret form" not in denied.text

    platform.permissions_by_tenant[str(TENANT_A)] = [LEADS]
    archived = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive",
        headers=_headers(write=True),
    )
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
    still_managed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": "Archived draft"},
    )
    assert still_managed.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    member_archived = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/reorder",
        headers=_headers(write=True),
        json={"field_ids": []},
    )
    assert member_archived.status_code == 403
    readable = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=False),
    )
    assert readable.status_code == 200
    assert "Archived draft" in {item["name"] for item in readable.json()["items"]}
