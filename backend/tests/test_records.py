"""Records stay on the published version that created them."""

import shutil
import threading
from pathlib import Path

from app.db import MIGRATIONS, apply_migrations, connect
from app.records_store import create_record
from tests.test_forms import DEV_DATABASE, _dropdown, _project, _text_field
from tests.test_form_versions import _add, _form, _publish
from tests.test_projects import (
    LEADS,
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


def _ready(client) -> tuple[str, str, str]:
    project_id = _project(client)
    form_id = _form(client, project_id, name="Site enquiry")
    _add(client, project_id, form_id, _text_field())
    _add(client, project_id, form_id, _dropdown())
    _add(
        client,
        project_id,
        form_id,
        {
            "field_key": "website",
            "label": "Website",
            "field_type": "url",
            "required": False,
            "section_name": "Contact",
        },
    )
    published = _publish(client, project_id, form_id)
    assert published.status_code == 201
    return project_id, form_id, published.json()["id"]


def _create(client, project_id: str, form_id: str, values: dict, **extra) -> object:
    body = {"form_id": form_id, "values": values, **extra}
    return client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=True),
        json=body,
    )


def test_record_keeps_its_published_version_through_search_edit_and_archive(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, version_1 = _ready(client)
    draft_only = _form(client, project_id, name="Still a draft")
    refused = _create(client, project_id, draft_only, {"school_name": "Nope"})
    assert refused.status_code == 409
    assert refused.json()["error"]["message"] == "Publish this form before creating a record."

    missing = _create(client, project_id, form_id, {})
    assert missing.status_code == 422
    assert missing.json()["error"]["fields"]["school_name"] == "School name is required."
    bad_choice = _create(client, project_id, form_id, {"school_name": "North", "priority": "urgent"})
    assert bad_choice.status_code == 422
    assert "listed options" in bad_choice.json()["error"]["fields"]["priority"]

    created = _create(
        client,
        project_id,
        form_id,
        {"school_name": "North school", "priority": "hot"},
        tenant_id=str(TENANT_B),
        form_version_id="99999999-9999-4999-8999-999999999999",
        created_by="attacker",
        assignee_user_id=OTHER_ID,
        public_number="FAKE-0001",
        source="manual",
    )
    assert created.status_code == 201
    record = created.json()
    assert record["public_number"] == "N-1-0001"
    assert record["public_number"] != "FAKE-0001"
    assert record["form_version_id"] == version_1
    assert record["version_number"] == 1
    assert record["created_by"] == USER_ID
    assert record["assignee_user_id"] == USER_ID
    assert record["created_by"] != "attacker"
    assert record["source"] == "manual"
    assert record["captured_at"] == record["created_at"]
    assert record["values"]["school_name"] == "North school"
    assert record["values"]["priority"] == "hot"
    assert record["fields"][0]["label"] == "School name"
    edited = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{_field_id(client, project_id, form_id, 'school_name')}",
        headers=_headers(write=True),
        json={"label": "Campus", "field_type": "text", "required": False, "max_length": 40},
    )
    assert edited.status_code == 200
    blocked_remove = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{_field_id(client, project_id, form_id, 'school_name')}/remove",
        headers=_headers(write=True),
    )
    assert blocked_remove.status_code == 409
    assert "saved record values" in blocked_remove.json()["error"]["message"]
    removed_website = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields/{_field_id(client, project_id, form_id, 'website')}/remove",
        headers=_headers(write=True),
    )
    assert removed_website.status_code == 200
    second = _publish(client, project_id, form_id)
    assert second.status_code == 201
    assert second.json()["version_number"] == 2

    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?q=",
        headers=_headers(write=False),
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["public_number"] == "N-1-0001"
    assert listed.json()["items"][0]["form_name"] == "Site enquiry"
    assert listed.json()["items"][0]["version_number"] == 1
    found = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?q=Hot",
        headers=_headers(write=False),
    )
    assert found.json()["items"][0]["id"] == record["id"]
    numbered = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?q=N-1-0001",
        headers=_headers(write=False),
    )
    assert numbered.json()["total"] == 1
    wild = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?q=%",
        headers=_headers(write=False),
    )
    assert wild.status_code == 200
    assert wild.json()["total"] == 0
    page = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?limit=1&offset=0&sort=public_number&direction=asc",
        headers=_headers(write=False),
    )
    assert page.json()["limit"] == 1
    assert len(page.json()["items"]) == 1

    detail = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}",
        headers=_headers(write=False),
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["form_version_id"] == version_1
    assert body["version_number"] == 1
    historical = next(field for field in body["fields"] if field["field_key"] == "school_name")
    assert historical["label"] == "School name"
    assert historical["required"] is True
    assert any(item["field_key"] == "website" for item in body["absent_from_draft"])
    assert "Campus" not in detail.text

    still_required = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}",
        headers=_headers(write=True),
        json={"expected_updated_at": body["updated_at"], "values": {"priority": "hot"}, "form_version_id": second.json()["id"]},
    )
    assert still_required.status_code == 422
    assert still_required.json()["error"]["fields"]["school_name"] == "School name is required."
    saved = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}",
        headers=_headers(write=True),
        json={
            "expected_updated_at": body["updated_at"],
            "values": {"school_name": "North campus", "priority": "warm"},
            "form_version_id": second.json()["id"],
            "tenant_id": str(TENANT_B),
        },
    )
    assert saved.status_code == 200
    assert saved.json()["form_version_id"] == version_1
    assert saved.json()["values"]["school_name"] == "North campus"
    assert saved.json()["values"]["priority"] == "warm"
    assert saved.json()["updated_at"] != body["updated_at"]
    stale = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}",
        headers=_headers(write=True),
        json={"expected_updated_at": body["updated_at"], "values": {"school_name": "Other"}},
    )
    assert stale.status_code == 409

    newer = _create(
        client,
        project_id,
        form_id,
        {"school_name": "After"},
        form_version_id=version_1,
    )
    assert newer.status_code == 201
    assert newer.json()["form_version_id"] == second.json()["id"]
    assert newer.json()["public_number"] == "N-1-0002"
    assert "priority" not in newer.json()["values"]

    archived = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}/archive",
        headers=_headers(write=True),
        json={"expected_updated_at": saved.json()["updated_at"]},
    )
    assert archived.status_code == 200
    hidden = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}",
        headers=_headers(write=False),
    )
    assert hidden.status_code == 404
    remaining = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert [item["public_number"] for item in remaining.json()["items"]] == ["N-1-0002"]
    third = _create(client, project_id, form_id, {"school_name": "Third"})
    assert third.json()["public_number"] == "N-1-0003"


def test_record_access_stays_inside_the_project_and_assignment_scope(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com"),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    other_project = _project(client, code="S-2", name="South yard")
    secret = _create(client, project_id, form_id, {"school_name": "Manager only", "priority": "hot"})
    assert secret.status_code == 201
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    own = _create(client, project_id, form_id, {"school_name": "Member school"})
    assert own.status_code == 201
    assert own.json()["assignee_user_id"] == OTHER_ID
    visible = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?q=Manager",
        headers=_headers(write=False),
    )
    assert visible.status_code == 200
    assert visible.json()["items"] == []
    assert "Manager only" not in visible.text
    denied = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{secret.json()['id']}",
        headers=_headers(write=False),
    )
    assert denied.status_code == 404
    assert "Manager only" not in denied.text
    own_list = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert [item["public_number"] for item in own_list.json()["items"]] == ["N-1-0002"]

    _become(platform, USER_ID, "manager@example.com")
    both = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?sort=public_number&direction=asc",
        headers=_headers(write=False),
    )
    assert [item["public_number"] for item in both.json()["items"]] == ["N-1-0001", "N-1-0002"]
    archived_project = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive",
        headers=_headers(write=True),
    )
    assert archived_project.status_code == 200
    blocked = _create(client, project_id, form_id, {"school_name": "Too late"})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["message"] == "This project is archived."
    still = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{own.json()['id']}",
        headers=_headers(write=False),
    )
    assert still.status_code == 200
    assert still.json()["values"]["school_name"] == "Member school"

    _become(platform, OTHER_ID, "member@example.com")
    memberships = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=False),
    )
    member_row = next(item for item in memberships.json()["items"] if item["user_id"] == OTHER_ID)
    _become(platform, USER_ID, "manager@example.com")
    client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/archive",
        headers=_headers(write=True),
    )
    removed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{member_row['id']}/remove",
        headers=_headers(write=True),
    )
    assert removed.status_code == 200
    _become(platform, OTHER_ID, "member@example.com")
    gone = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{own.json()['id']}",
        headers=_headers(write=False),
    )
    assert gone.status_code == 404
    assert "Member school" not in gone.text

    _become(platform, USER_ID, "manager@example.com")
    foreign = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{other_project}/records?q=Member",
        headers=_headers(write=False),
    )
    assert foreign.status_code == 200
    assert foreign.json()["items"] == []
    assert "Member school" not in foreign.text
    other_tenant = client.get(
        f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert other_tenant.status_code == 404
    _allow(platform, TENANT_A, keys=["users.read"])
    refused = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert refused.status_code == 403
    _allow(platform, TENANT_A, keys=[LEADS])
    missing_csrf = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers={"cookie": "aadi_session=member"},
        json={"form_id": form_id, "values": {"school_name": "X"}},
    )
    assert missing_csrf.status_code == 401


def test_concurrent_creates_receive_distinct_record_numbers(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    path = tmp_path / "projects.sqlite"
    barrier = threading.Barrier(2)
    numbers: list[str] = []
    guard = threading.Lock()

    def worker(name: str) -> None:
        connection = connect(path)
        try:
            barrier.wait(timeout=5)
            created = create_record(
                connection,
                tenant_id=str(TENANT_A),
                project_id=project_id,
                project_code="N-1",
                form_id=form_id,
                actor_id=USER_ID,
                source="manual",
                values={"school_name": name},
            )
            assert created is not None
            with guard:
                numbers.append(str(created["public_number"]))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=("One",)), threading.Thread(target=worker, args=("Two",))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert thread.is_alive() is False
    assert sorted(numbers) == ["N-1-0001", "N-1-0002"]


def test_record_migration_preserves_projects_forms_and_versions(tmp_path) -> None:
    path = tmp_path / "before-records.sqlite"
    connection = connect(path)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    for name in (
        "001_projects.sql",
        "002_project_memberships.sql",
        "003_form_definitions.sql",
        "004_form_versions.sql",
    ):
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
            id, tenant_id, project_id, name, description, status, created_by, updated_by,
            created_at, updated_at, current_published_version_id
        ) VALUES ('form-1', ?, 'active-1', 'Site enquiry', '', 'draft', ?, ?, 't', 't', NULL)
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
    snapshot = '{"name":"Site enquiry","description":"","fields":[{"field_key":"school_name","label":"School name"}]}'
    connection.execute(
        """
        INSERT INTO form_versions (
            id, tenant_id, project_id, form_id, version_number, schema_json, published_by, published_at
        ) VALUES ('version-1', ?, 'active-1', 'form-1', 1, ?, ?, 't')
        """,
        (str(TENANT_A), snapshot, USER_ID),
    )
    connection.execute(
        """
        UPDATE form_definitions
        SET current_published_version_id = 'version-1'
        WHERE id = 'form-1'
        """
    )
    connection.commit()
    connection.close()
    apply_migrations(path)
    apply_migrations(path)
    connection = connect(path)
    version = connection.execute("SELECT schema_json FROM form_versions WHERE id = 'version-1'").fetchone()
    project = connection.execute("SELECT name, status FROM projects WHERE id = 'active-1'").fetchone()
    applied = {row["version"] for row in connection.execute("SELECT version FROM crm_schema_migrations")}
    count = connection.execute("SELECT COUNT(*) AS count FROM records").fetchone()
    connection.close()
    assert version["schema_json"] == snapshot
    assert project["name"] == "Live gate"
    assert project["status"] == "active"
    assert "005_records.sql" in applied
    assert count["count"] == 0


def test_development_copy_gains_records_without_changing_the_original(tmp_path) -> None:
    if not DEV_DATABASE.exists():
        return
    source_before = _file_snapshot(DEV_DATABASE)
    target = tmp_path / "dev-copy.sqlite"
    shutil.copy(DEV_DATABASE, target)
    apply_migrations(target)
    assert _file_snapshot(DEV_DATABASE) == source_before
    copied = connect(target)
    versions = {row["version"] for row in copied.execute("SELECT version FROM crm_schema_migrations")}
    projects = copied.execute("SELECT COUNT(*) AS count FROM projects").fetchone()["count"]
    forms = copied.execute("SELECT COUNT(*) AS count FROM form_definitions").fetchone()["count"]
    published = copied.execute("SELECT COUNT(*) AS count FROM form_versions").fetchone()["count"]
    records = copied.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"]
    copied.close()
    original = connect(DEV_DATABASE)
    original_projects = original.execute("SELECT COUNT(*) AS count FROM projects").fetchone()["count"]
    original.close()
    assert "005_records.sql" in versions
    assert projects == original_projects
    assert forms >= 0
    assert published >= 0
    assert records >= 0


def test_list_filters_sort_and_pages_stay_inside_the_project(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    first = _create(client, project_id, form_id, {"school_name": "Alpha", "priority": "hot"}, source="manual")
    second = _create(client, project_id, form_id, {"school_name": "Beta", "priority": "warm"}, source="website")
    third = _create(client, project_id, form_id, {"school_name": "Gamma", "priority": "cold"}, source="manual")
    assert first.status_code == second.status_code == third.status_code == 201
    day = first.json()["created_at"][:10]
    base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records"
    headers = _headers(write=False)

    combined = client.get(
        f"{base}?source=manual&created_from={day}&created_to={day}&sort=public_number&direction=asc",
        headers=headers,
    )
    assert combined.status_code == 200
    assert [item["public_number"] for item in combined.json()["items"]] == ["N-1-0001", "N-1-0003"]
    assert combined.json()["total"] == 2

    empty_search = client.get(f"{base}?q=", headers=headers)
    assert empty_search.json()["total"] == 3
    later = client.get(f"{base}?created_from=2999-01-01", headers=headers)
    assert later.json()["total"] == 0
    assert later.json()["items"] == []

    for query in (
        "sort=status",
        "direction=sideways",
        "source=nope",
        "form_id=not-a-uuid",
        "created_from=13-01-2026",
        "created_to=2026-13-01",
        "created_from=2026-10-22&created_to=2026-10-01",
        "limit=0",
        "limit=101",
        "offset=-1",
    ):
        rejected = client.get(f"{base}?{query}", headers=headers)
        assert rejected.status_code == 422, query

    page = client.get(f"{base}?limit=1&offset=1&sort=public_number&direction=asc", headers=headers)
    assert page.json()["items"][0]["public_number"] == "N-1-0002"
    assert page.json()["total"] == 3
    past = client.get(f"{base}?limit=1&offset=50&sort=public_number&direction=asc", headers=headers)
    assert past.status_code == 200
    assert past.json()["items"] == []
    assert past.json()["total"] == 3

    connection = connect(tmp_path / "projects.sqlite")
    connection.execute(
        "UPDATE records SET created_at = ? WHERE project_id = ?",
        ("2026-10-20T00:00:00+00:00", project_id),
    )
    connection.commit()
    connection.close()
    tied = client.get(f"{base}?sort=created_at&direction=asc&limit=10", headers=headers)
    assert [item["id"] for item in tied.json()["items"]] == sorted(
        item["id"] for item in tied.json()["items"]
    )
    assert len(tied.json()["items"]) == 3


def test_custom_fields_validate_on_the_published_schema_without_consuming_a_number(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client)
    form_id = _form(client, project_id, name="Typed enquiry")
    _add(client, project_id, form_id, _text_field())
    _add(
        client,
        project_id,
        form_id,
        {"field_key": "contact_email", "label": "Email", "field_type": "email", "required": False, "section_name": "Contact"},
    )
    _add(
        client,
        project_id,
        form_id,
        {
            "field_key": "seats",
            "label": "Seats",
            "field_type": "number",
            "required": False,
            "section_name": "Value",
            "min_value": 1,
            "max_value": 10,
        },
    )
    _add(
        client,
        project_id,
        form_id,
        {"field_key": "phone", "label": "Mobile", "field_type": "mobile", "required": False, "section_name": "Contact"},
    )
    _add(
        client,
        project_id,
        form_id,
        {"field_key": "visit_date", "label": "Visit date", "field_type": "date", "required": False, "section_name": "Contact"},
    )
    _add(
        client,
        project_id,
        form_id,
        {
            "field_key": "consent",
            "label": "Consent",
            "field_type": "checkbox",
            "required": True,
            "section_name": "Contact",
        },
    )
    _add(
        client,
        project_id,
        form_id,
        {
            "field_key": "tags",
            "label": "Tags",
            "field_type": "multi_select",
            "required": False,
            "section_name": "Choice",
            "options": [{"value": "north", "label": "North"}, {"value": "south", "label": "South"}],
        },
    )
    published = _publish(client, project_id, form_id)
    assert published.status_code == 201
    refused = _create(client, project_id, form_id, {"school_name": "North", "contact_email": "not-an-email"})
    assert refused.status_code == 422
    assert "email" in refused.json()["error"]["fields"]["contact_email"]
    low = _create(client, project_id, form_id, {"school_name": "North", "consent": True, "seats": 0})
    assert low.status_code == 422
    assert "minimum" in low.json()["error"]["fields"]["seats"]
    bad_tags = _create(client, project_id, form_id, {"school_name": "North", "consent": True, "tags": ["later"]})
    assert bad_tags.status_code == 422
    unknown = _create(client, project_id, form_id, {"school_name": "North", "consent": True, "nickname": "X"})
    assert unknown.status_code == 422
    connection = connect(tmp_path / "projects.sqlite")
    assert connection.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"] == 0
    connection.close()
    created = _create(
        client,
        project_id,
        form_id,
        {
            "school_name": "North school",
            "contact_email": "office@example.com",
            "seats": 4,
            "phone": "9876543210",
            "visit_date": "2026-10-20",
            "consent": True,
            "tags": ["north", "south"],
        },
        public_number="FAKE-0009",
    )
    assert created.status_code == 201
    assert created.json()["public_number"] == "N-1-0001"
    assert created.json()["values"]["seats"] == 4
    assert created.json()["values"]["tags"] == ["north", "south"]
    assert created.json()["values"]["consent"] is True

    blocked = _form(client, project_id, name="Blocked types")
    _add(
        client,
        project_id,
        blocked,
        {"field_key": "upload", "label": "Upload", "field_type": "file", "required": True, "section_name": "Files"},
    )
    _add(
        client,
        project_id,
        blocked,
        {"field_key": "serial", "label": "Serial", "field_type": "auto_number", "required": True, "section_name": "Files"},
    )
    assert _publish(client, project_id, blocked).status_code == 201
    file_row = _create(client, project_id, blocked, {})
    assert file_row.status_code == 422
    assert "File upload" in file_row.json()["error"]["fields"]["upload"]
    assert "Auto-number" in file_row.json()["error"]["fields"]["serial"]


def test_archive_can_be_repeated_without_changing_the_deletion_time(tmp_path, monkeypatch) -> None:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com"),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "Keep me", "priority": "hot"})
    assert created.status_code == 201
    record_id = created.json()["id"]
    archived = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}/archive",
        headers=_headers(write=True),
        json={"expected_updated_at": created.json()["updated_at"]},
    )
    assert archived.status_code == 200
    connection = connect(tmp_path / "projects.sqlite")
    stamp = connection.execute("SELECT deleted_at FROM records WHERE id = ?", (record_id,)).fetchone()["deleted_at"]
    connection.close()
    assert stamp
    again = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}/archive",
        headers=_headers(write=True),
        json={"expected_updated_at": created.json()["updated_at"]},
    )
    assert again.status_code == 404
    edited = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}",
        headers=_headers(write=True),
        json={"expected_updated_at": created.json()["updated_at"], "values": {"school_name": "Changed"}},
    )
    assert edited.status_code == 404
    connection = connect(tmp_path / "projects.sqlite")
    row = connection.execute(
        "SELECT deleted_at, form_version_id, public_number FROM records WHERE id = ?",
        (record_id,),
    ).fetchone()
    values = connection.execute("SELECT COUNT(*) AS count FROM record_values WHERE record_id = ?", (record_id,)).fetchone()
    connection.close()
    assert row["deleted_at"] == stamp
    assert row["form_version_id"] == created.json()["form_version_id"]
    assert row["public_number"] == created.json()["public_number"]
    assert values["count"] >= 1
    hidden = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?q=Keep",
        headers=_headers(write=False),
    )
    assert hidden.json()["total"] == 0

    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    own = _create(client, project_id, form_id, {"school_name": "Member row"})
    assert own.status_code == 201
    _become(platform, USER_ID, "manager@example.com")
    manager_row = _create(client, project_id, form_id, {"school_name": "Manager row"})
    assert manager_row.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    stolen = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{manager_row.json()['id']}",
        headers=_headers(write=True),
        json={"expected_updated_at": manager_row.json()["updated_at"], "values": {"school_name": "Stolen"}},
    )
    assert stolen.status_code == 404
    assert "Manager row" not in stolen.text
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == own.json()["id"]


def _field_id(client, project_id: str, form_id: str, key: str) -> str:
    form = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    return next(field["id"] for field in form.json()["fields"] if field["field_key"] == key)


def _file_snapshot(path: Path) -> bytes:
    return path.read_bytes()
