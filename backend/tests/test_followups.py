"""Follow-ups stay on the authorized record and do not use a fixed count."""

import shutil
from datetime import UTC, datetime, timedelta

from app.db import MIGRATIONS, apply_migrations, connect
from app.followups_store import QUEUE_ZONE, queue_for, queue_window, utc_due
from app.followups_store import FollowUpValidation
from tests.test_forms import DEV_DATABASE
from tests.test_projects import OTHER_ID, OUTSIDE_ID, TENANT_A, TENANT_B, USER_ID, FakePlatform, _allow, _become, _client, _headers, _person
from tests.test_records import _create, _file_snapshot, _ready


def test_due_instants_reject_gaps_and_ambiguous_times() -> None:
    kolkata = utc_due("2026-10-21", "00:00", QUEUE_ZONE)
    assert kolkata == "2026-10-20T18:30:00.000000+00:00"
    assert utc_due("2026-06-15", "09:30", "America/New_York") == "2026-06-15T13:30:00.000000+00:00"
    for due_date, due_time, zone in (
        ("2026-03-08", "02:30", "America/New_York"),
        ("2026-11-01", "01:30", "America/New_York"),
        ("2026-02-31", "09:00", QUEUE_ZONE),
        ("2026-10-21", "24:00", QUEUE_ZONE),
    ):
        try:
            utc_due(due_date, due_time, zone)
        except FollowUpValidation:
            continue
        raise AssertionError(f"{due_date} {due_time} {zone} was accepted")
    now = datetime(2026, 10, 20, 18, 30, tzinfo=UTC)
    start, end = queue_window(now, QUEUE_ZONE)
    assert start == "2026-10-20T18:30:00.000000+00:00"
    assert end == "2026-10-21T18:30:00.000000+00:00"
    one_second = "2026-10-20T18:29:59.000000+00:00"
    assert queue_for(one_second, start, end, "open") == "overdue"
    assert queue_for(start, start, end, "open") == "today"
    assert queue_for("2026-10-21T18:29:59.000000+00:00", start, end, "open") == "today"
    assert queue_for(end, start, end, "open") == "upcoming"
    assert queue_for(one_second, start, end, "completed") is None
    names = {
        queue_for(one_second, start, end, "open"),
        queue_for(start, start, end, "open"),
        queue_for(end, start, end, "open"),
    }
    assert names == {"overdue", "today", "upcoming"}


def test_follow_up_lifecycle_timeline_and_queues(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    ticker = _Ticker(datetime(2026, 10, 20, 18, 30, tzinfo=UTC))
    monkeypatch.setattr("app.followups_store.clock", ticker)
    project_id, form_id, version_id = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "North school", "priority": "hot"})
    assert created.status_code == 201
    record = created.json()
    record_id = record["id"]
    base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}"

    missing = client.post(
        f"{base}/follow-ups",
        headers=_headers(write=True),
        json=_body(call_status=None),
    )
    assert missing.status_code == 422
    assert "call status" in missing.json()["error"]["fields"]["call_status"].lower()
    invalid_day = client.post(
        f"{base}/follow-ups",
        headers=_headers(write=True),
        json=_body(task_type="note", due_date="2026-02-31", call_status=None),
    )
    assert invalid_day.status_code == 422
    assert invalid_day.json()["error"]["fields"]["due_date"]
    stranger = client.post(
        f"{base}/follow-ups",
        headers=_headers(write=True),
        json=_body(task_type="note", owner_user_id=OUTSIDE_ID, call_status=None),
    )
    assert stranger.status_code == 422
    assert "active member" in stranger.json()["error"]["fields"]["owner_user_id"]
    spoofed = client.post(
        f"{base}/follow-ups",
        headers=_headers(write=True),
        json=_body(task_type="note", tenant_id=str(TENANT_B), created_by="attacker", call_status=None),
    )
    assert spoofed.status_code == 422

    overdue = _add(client, base, due_date="2026-10-20", due_time="23:59", summary="Called yesterday")
    still_due = _add(client, base, task_type="note", due_date="2026-10-20", due_time="18:00", summary="Still open", call_status=None)
    today = _add(client, base, due_date="2026-10-21", due_time="00:00", summary="Due at midnight")
    upcoming = _add(client, base, due_date="2026-10-22", due_time="00:00", summary="Due tomorrow")
    assert overdue["created_by"] == USER_ID
    assert overdue["timezone"] == QUEUE_ZONE
    assert overdue["due_at"] == "2026-10-20T18:29:00.000000+00:00"
    assert record["form_version_id"] == version_id
    reloaded = client.get(base, headers=_headers(write=False))
    assert reloaded.status_code == 200
    assert reloaded.json()["form_version_id"] == version_id
    assert reloaded.json()["updated_at"] == record["updated_at"]
    assert reloaded.json()["values"]["school_name"] == "North school"

    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    changed = client.patch(
        f"{base}/follow-ups/{today['id']}",
        headers=_headers(write=True),
        json={
            "expected_updated_at": today["updated_at"],
            "task_type": "email",
            "owner_user_id": OTHER_ID,
            "due_date": "2026-10-21",
            "due_time": "15:00",
            "summary": "Send the note",
            "call_status": None,
        },
    )
    assert changed.status_code == 200
    edited = changed.json()
    assert edited["owner_user_id"] == OTHER_ID
    assert edited["task_type"] == "email"
    assert edited["due_time"] == "15:00"
    finished = client.post(
        f"{base}/follow-ups/{upcoming['id']}/complete",
        headers=_headers(write=True),
        json={"expected_updated_at": upcoming["updated_at"], "outcome": "Spoke with the family"},
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "completed"
    assert finished.json()["outcome"] == "Spoke with the family"
    silent = client.patch(
        f"{base}/follow-ups/{upcoming['id']}",
        headers=_headers(write=True),
        json={"expected_updated_at": finished.json()["updated_at"], "summary": "Replaced"},
    )
    assert silent.status_code == 409
    assert client.get(f"{base}/follow-ups/{upcoming['id']}", headers=_headers(write=False)).json()["outcome"] == "Spoke with the family"
    cancelled = client.post(
        f"{base}/follow-ups/{overdue['id']}/cancel",
        headers=_headers(write=True),
        json={"expected_updated_at": overdue["updated_at"], "outcome": ""},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    timeline = client.get(f"{base}/activities?limit=1&offset=0", headers=_headers(write=False))
    assert timeline.status_code == 200
    assert timeline.json()["total"] >= 4
    assert timeline.json()["items"][0]["label"]
    assert timeline.json()["items"][0]["actor_id"] == USER_ID
    second = client.get(f"{base}/activities?limit=1&offset=1", headers=_headers(write=False))
    assert second.json()["items"][0]["id"] != timeline.json()["items"][0]["id"]
    labels = {
        item["event_type"]
        for item in client.get(f"{base}/activities?limit=25", headers=_headers(write=False)).json()["items"]
    }
    assert {"follow_up.created", "follow_up.updated", "follow_up.rescheduled", "follow_up.reassigned", "follow_up.completed", "follow_up.cancelled"} <= labels

    queues = {}
    for name in ("overdue", "today", "upcoming"):
        page = client.get(
            f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/follow-ups?queue={name}",
            headers=_headers(write=False),
        )
        assert page.status_code == 200
        assert page.json()["timezone"] == QUEUE_ZONE
        queues[name] = {item["id"] for item in page.json()["items"]}
    assert still_due["id"] in queues["overdue"]
    assert overdue["id"] not in queues["overdue"]
    assert today["id"] in queues["today"]
    assert upcoming["id"] not in queues["today"]
    assert queues["upcoming"] == set()
    assert queues["overdue"].isdisjoint(queues["today"])
    assert queues["today"].isdisjoint(queues["upcoming"])

    _become(platform, OTHER_ID, "member@example.com")
    owned = client.get(f"{base}/follow-ups/{today['id']}", headers=_headers(write=False))
    assert owned.status_code == 200
    assert owned.json()["summary"] == "Send the note"
    unrelated = client.get(f"{base}/follow-ups/{still_due['id']}", headers=_headers(write=False))
    assert unrelated.status_code == 404
    assert "Still open" not in unrelated.text
    member_queue = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/follow-ups?queue=today&owner_user_id={USER_ID}",
        headers=_headers(write=False),
    )
    assert member_queue.status_code == 200
    assert member_queue.json()["total"] == 1
    assert member_queue.json()["owner_user_id"] == OTHER_ID
    assert today["id"] in {item["id"] for item in member_queue.json()["items"]}
    assert still_due["id"] not in {item["id"] for item in member_queue.json()["items"]}
    assert "Send the note" in member_queue.text


def test_many_follow_ups_have_no_count_cap(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    record_id = _create(client, project_id, form_id, {"school_name": "North school"}).json()["id"]
    base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}"
    for index in range(26):
        created = client.post(
            f"{base}/follow-ups",
            headers=_headers(write=True),
            json=_body(task_type="note", due_time=f"{index % 24:02d}:15", summary=f"Entry {index}", call_status=None),
        )
        assert created.status_code == 201
    page = client.get(f"{base}/follow-ups?limit=25&offset=0", headers=_headers(write=False))
    assert page.json()["total"] == 26
    assert len(page.json()["items"]) == 25
    rest = client.get(f"{base}/follow-ups?limit=25&offset=25", headers=_headers(write=False))
    assert len(rest.json()["items"]) == 1
    filtered = client.get(f"{base}/follow-ups?task_type=call", headers=_headers(write=False))
    assert filtered.json()["total"] == 0
    script = (MIGRATIONS / "006_followups.sql").read_text(encoding="utf-8").lower()
    assert "drop table" not in script
    assert "delete from" not in script


def test_follow_up_authorization_and_csrf(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id, form_id, _version = _ready(client)
    other_project = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": "S-2", "name": "South yard", "description": ""},
    ).json()["id"]
    record = _create(client, project_id, form_id, {"school_name": "Hidden school"}).json()
    base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record['id']}"
    follow_up = _add(client, base, task_type="note", summary="Private note", call_status=None)
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    denied = client.get(f"{base}/activities", headers=_headers(write=False))
    assert denied.status_code == 404
    assert "Private note" not in denied.text
    own = _create(client, project_id, form_id, {"school_name": "Member school"})
    assert own.status_code == 201
    own_base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{own.json()['id']}"
    visible = _add(
        client,
        own_base,
        task_type="note",
        owner_user_id=OTHER_ID,
        summary="Member note",
        call_status=None,
    )
    assert visible["owner_user_id"] == OTHER_ID
    _become(platform, USER_ID, "manager@example.com")
    removed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members/{added.json()['id']}/remove",
        headers=_headers(write=True),
    )
    assert removed.status_code == 200
    rejected = client.post(
        f"{own_base}/follow-ups",
        headers=_headers(write=True),
        json=_body(task_type="note", owner_user_id=OTHER_ID, call_status=None),
    )
    assert rejected.status_code == 422
    _become(platform, OTHER_ID, "member@example.com")
    gone = client.get(f"{own_base}/follow-ups/{visible['id']}", headers=_headers(write=False))
    assert gone.status_code == 404
    _become(platform, USER_ID, "manager@example.com")
    foreign = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{other_project}/records/{record['id']}/follow-ups/{follow_up['id']}",
        headers=_headers(write=False),
    )
    assert foreign.status_code == 404
    other_tenant = client.get(
        f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/follow-ups?queue=today",
        headers=_headers(write=False),
    )
    assert other_tenant.status_code == 404
    assert "Private note" not in other_tenant.text
    archived = client.post(f"{base}/archive", headers=_headers(write=True), json={"expected_updated_at": record["updated_at"]})
    assert archived.status_code == 200
    after_archive = client.get(f"{base}/follow-ups", headers=_headers(write=False))
    assert after_archive.status_code == 404
    missing_csrf = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{own.json()['id']}/follow-ups",
        headers={"cookie": "aadi_session=member"},
        json=_body(task_type="note", call_status=None),
    )
    assert missing_csrf.status_code == 401


def test_migration_preserves_records_and_form_versions(tmp_path) -> None:
    path = tmp_path / "before-follow-ups.sqlite"
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
        "005_records.sql",
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
            id, tenant_id, project_id, name, description, status, created_by, updated_by, created_at, updated_at
        ) VALUES ('form-1', ?, 'active-1', 'Site enquiry', '', 'draft', ?, ?, 't', 't')
        """,
        (str(TENANT_A), USER_ID, USER_ID),
    )
    snapshot = '{"name":"Site enquiry","fields":[{"field_key":"school_name"}]}'
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
        UPDATE form_definitions SET current_published_version_id = 'version-1' WHERE id = 'form-1'
        """
    )
    connection.execute(
        """
        INSERT INTO records (
            id, tenant_id, project_id, form_id, form_version_id, public_number, sequence,
            display_name, search_text, source, assignee_user_id, created_by, updated_by,
            created_at, updated_at, captured_at, deleted_at
        ) VALUES (
            'record-1', ?, 'active-1', 'form-1', 'version-1', 'LIVE-0001', 1,
            'North school', 'north school', 'manual', ?, ?, ?,
            't', 't', 't', NULL
        )
        """,
        (str(TENANT_A), USER_ID, USER_ID, USER_ID),
    )
    connection.commit()
    connection.close()
    apply_migrations(path)
    apply_migrations(path)
    connection = connect(path)
    version = connection.execute("SELECT schema_json FROM form_versions WHERE id = 'version-1'").fetchone()
    stored = connection.execute(
        "SELECT public_number, form_version_id, display_name, deleted_at FROM records WHERE id = 'record-1'"
    ).fetchone()
    follow_ups = connection.execute("SELECT COUNT(*) AS count FROM follow_ups").fetchone()
    activities = connection.execute("SELECT COUNT(*) AS count FROM record_activities").fetchone()
    applied = {row["version"] for row in connection.execute("SELECT version FROM crm_schema_migrations")}
    connection.close()
    assert version["schema_json"] == snapshot
    assert stored["public_number"] == "LIVE-0001"
    assert stored["form_version_id"] == "version-1"
    assert stored["display_name"] == "North school"
    assert stored["deleted_at"] is None
    assert follow_ups["count"] == 0
    assert activities["count"] == 0
    assert "006_followups.sql" in applied


def test_development_copy_gains_follow_ups_without_changing_the_original(tmp_path) -> None:
    if not DEV_DATABASE.exists():
        return
    source_before = _file_snapshot(DEV_DATABASE)
    target = tmp_path / "dev-copy.sqlite"
    shutil.copy(DEV_DATABASE, target)
    apply_migrations(target)
    assert _file_snapshot(DEV_DATABASE) == source_before
    copied = connect(target)
    versions = {row["version"] for row in copied.execute("SELECT version FROM crm_schema_migrations")}
    records = copied.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"]
    versions_count = copied.execute("SELECT COUNT(*) AS count FROM form_versions").fetchone()["count"]
    follow_ups = copied.execute("SELECT COUNT(*) AS count FROM follow_ups").fetchone()["count"]
    activities = copied.execute("SELECT COUNT(*) AS count FROM record_activities").fetchone()["count"]
    copied.close()
    original = connect(DEV_DATABASE)
    original_records = original.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"]
    original_follow_ups = original.execute("SELECT COUNT(*) AS count FROM follow_ups").fetchone()["count"]
    original_activities = original.execute("SELECT COUNT(*) AS count FROM record_activities").fetchone()["count"]
    original.close()
    assert "006_followups.sql" in versions
    assert records == original_records
    assert versions_count >= 0
    assert follow_ups == original_follow_ups
    assert activities == original_activities


class _Ticker:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        current = self.moment
        self.moment = current + timedelta(minutes=1)
        return current


def _platform() -> FakePlatform:
    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com"),
        _person(OUTSIDE_ID, "outside@example.com"),
    ]
    return platform


def _body(**overrides) -> dict:
    body = {
        "task_type": "call",
        "owner_user_id": USER_ID,
        "due_date": "2026-10-21",
        "due_time": "10:00",
        "summary": "Discuss the visit",
        "call_status": "connected",
    }
    body.update(overrides)
    return body


def _add(client, base: str, **overrides) -> dict:
    created = client.post(f"{base}/follow-ups", headers=_headers(write=True), json=_body(**overrides))
    assert created.status_code == 201
    return created.json()


def test_follow_up_owner_can_open_only_the_related_record(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    monkeypatch.setattr("app.followups_store.clock", _Ticker(datetime(2026, 10, 20, 18, 30, tzinfo=UTC)))
    project_id, form_id, _version = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "Owned school", "priority": "hot"})
    other = _create(client, project_id, form_id, {"school_name": "Hidden school", "priority": "warm"})
    assert created.status_code == 201
    assert other.status_code == 201
    record_id = created.json()["id"]
    hidden_id = other.json()["id"]
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}"
    follow_up = _add(client, base, owner_user_id=OTHER_ID, task_type="note", call_status=None, summary="Call the school")
    _become(platform, OTHER_ID, "member@example.com")
    opened = client.get(base, headers=_headers(write=False))
    assert opened.status_code == 200
    assert opened.json()["values"]["school_name"] == "Owned school"
    hidden = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{hidden_id}",
        headers=_headers(write=False),
    )
    assert hidden.status_code == 404
    assert "Hidden school" not in hidden.text
    edited = client.patch(
        base,
        headers=_headers(write=True),
        json={"expected_updated_at": opened.json()["updated_at"], "values": {"school_name": "Changed"}},
    )
    assert edited.status_code == 404
    assert "Changed" not in edited.text
    _become(platform, USER_ID, "manager@example.com")
    finished = client.post(
        f"{base}/follow-ups/{follow_up['id']}/complete",
        headers=_headers(write=True),
        json={"expected_updated_at": follow_up["updated_at"], "outcome": "Done"},
    )
    assert finished.status_code == 200
    _become(platform, OTHER_ID, "member@example.com")
    closed = client.get(base, headers=_headers(write=False))
    assert closed.status_code == 404
    assert "Owned school" not in closed.text
