"""Project KPIs use the same filters as the record list and follow-up queues."""

import json
import time
from datetime import UTC, date, datetime

from app.reporting_store import _by_due_date

from app.db import connect, database_path
from tests.test_followups import _add, _body
from tests.test_forms import _project
from tests.test_form_versions import _add as _add_field
from tests.test_form_versions import _form, _publish
from tests.test_projects import OTHER_ID, OUTSIDE_ID, TENANT_A, TENANT_B, USER_ID, _become, _headers
from tests.test_records import _create, _ready
from tests.test_followups import _platform
from tests.test_projects import _client


def test_kpis_match_authorized_lists_and_queue_boundaries(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    monkeypatch.setattr("app.followups_store.clock", lambda: datetime(2026, 10, 20, 18, 30, tzinfo=UTC))
    project_id, form_id, _version_id = _ready(client)
    created = _create(client, project_id, form_id, {"school_name": "North school", "priority": "hot"})
    assert created.status_code == 201
    record_id = created.json()["id"]
    created_day = created.json()["created_at"][:10]
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{record_id}"
    overdue = _add(client, base, due_date="2026-10-20", due_time="23:59", summary="North overdue")
    _add(client, base, due_date="2026-10-21", due_time="00:00", summary="North today")
    _add(client, base, due_date="2026-10-22", due_time="00:00", summary="North upcoming")
    _add(client, base, due_date="2026-10-22", due_time="09:00", summary="North upcoming later")
    finished = _add(client, base, due_date="2026-10-21", due_time="11:00", summary="North done")
    cancelled = _add(client, base, due_date="2026-10-21", due_time="12:00", summary="North cancelled")
    hidden = _add(
        client,
        base,
        due_date="2026-10-21",
        due_time="13:00",
        owner_user_id=OTHER_ID,
        summary="Hidden from the member",
    )
    completed = client.post(
        f"{base}/follow-ups/{finished['id']}/complete",
        headers=_headers(write=True),
        json={"expected_updated_at": finished["updated_at"], "outcome": "Spoke"},
    )
    assert completed.status_code == 200
    stopped = client.post(
        f"{base}/follow-ups/{cancelled['id']}/cancel",
        headers=_headers(write=True),
        json={"expected_updated_at": cancelled["updated_at"], "outcome": ""},
    )
    assert stopped.status_code == 200
    member_form = _form(client, project_id, name="Hiring desk")
    _add_field(client, project_id, member_form, {
        "field_key": "school_name",
        "label": "School name",
        "field_type": "text",
        "required": True,
        "help_text": "",
        "section_name": "Contact",
        "max_length": 120,
    })
    published = _publish(client, project_id, member_form)
    assert published.status_code == 201

    _become(platform, OTHER_ID, "member@example.com")
    member_record = _create(client, project_id, member_form, {"school_name": "Member school"})
    assert member_record.status_code == 201
    member_base = f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{member_record.json()['id']}"
    _add(client, member_base, due_date="2026-10-20", due_time="22:00", owner_user_id=OTHER_ID, summary="Member overdue")

    _become(platform, USER_ID, "manager@example.com")
    started = time.perf_counter()
    report = client.get(_kpi(project_id), headers=_headers(write=False))
    elapsed = time.perf_counter() - started
    assert report.status_code == 200, report.text
    assert elapsed < 2
    body = report.json()
    assert body["follow_up_timezone"] == "Asia/Kolkata"
    assert body["record_date_boundary"] == "utc_calendar_day"
    assert body["window_start"] == "2026-10-20T18:30:00.000000+00:00"
    assert body["window_end"] == "2026-10-21T18:30:00.000000+00:00"
    assert body["omitted"] == ["record_status", "trends", "targets"]
    assert body["active_records"] == 2
    assert body["records_created"] is None
    assert sum(item["count"] for item in body["records_by_form"]) == 2
    assert {item["form_name"] for item in body["records_by_form"]} == {"Site enquiry", "Hiring desk"}
    follow_ups = body["follow_ups"]
    assert follow_ups["overdue"] == 2
    assert follow_ups["today"] == 2
    assert follow_ups["upcoming"] == 2
    assert follow_ups["completed"] == 1
    assert follow_ups["overdue"] + follow_ups["today"] + follow_ups["upcoming"] == 6
    assert "North school" not in report.text
    assert "Hidden from the member" not in report.text
    owners = {item["owner_user_id"]: item for item in follow_ups["by_owner"]}
    assert owners[USER_ID] == {"owner_user_id": USER_ID, "overdue": 1, "today": 1, "upcoming": 2}
    assert owners[OTHER_ID] == {"owner_user_id": OTHER_ID, "overdue": 1, "today": 1, "upcoming": 0}
    assert sum(item["overdue"] for item in follow_ups["by_owner"]) == 2
    assert sum(item["today"] for item in follow_ups["by_owner"]) == 2
    assert sum(item["upcoming"] for item in follow_ups["by_owner"]) == 2
    dates = {(item["queue"], item["due_date"]): item["count"] for item in follow_ups["by_due_date"]}
    assert dates == {("overdue", "2026-10-20"): 2, ("today", "2026-10-21"): 2, ("upcoming", "2026-10-22"): 2}
    assert sum(dates.values()) == 6

    assert _record_total(client, project_id) == 2
    assert _record_total(client, project_id, form_id=form_id) == 1
    assert _queue_total(client, project_id, "overdue") == 2
    assert _queue_total(client, project_id, "today") == 2
    assert _queue_total(client, project_id, "upcoming") == 2
    assert _queue_total(client, project_id, "today", owner=USER_ID) == 1
    assert _queue_total(client, project_id, "today", owner=OTHER_ID) == 1
    completed_list = client.get(_completed(project_id), headers=_headers(write=False))
    assert completed_list.status_code == 200
    assert completed_list.json()["total"] == 1
    assert completed_list.json()["items"][0]["id"] == finished["id"]
    assert "summary" not in completed_list.json()["items"][0]
    assert "outcome" not in completed_list.json()["items"][0]
    assert hidden["id"] not in completed_list.text
    assert overdue["id"]

    _become(platform, OTHER_ID, "member@example.com")
    member_report = client.get(_kpi(project_id), headers=_headers(write=False))
    assert member_report.status_code == 200, member_report.text
    member_body = member_report.json()
    assert member_body["active_records"] == 1
    assert member_body["records_by_form"] == [
        {"form_id": member_form, "form_name": "Hiring desk", "count": 1}
    ]
    assert member_body["follow_ups"]["overdue"] == 1
    assert member_body["follow_ups"]["today"] == 1
    assert member_body["follow_ups"]["upcoming"] == 0
    assert member_body["follow_ups"]["completed"] == 0
    assert member_body["follow_ups"]["by_owner"] == [
        {"owner_user_id": OTHER_ID, "overdue": 1, "today": 1, "upcoming": 0}
    ]
    assert "North school" not in member_report.text
    assert "Site enquiry" not in member_report.text
    assert "Hidden from the member" not in member_report.text
    assert USER_ID not in member_report.text
    assert _record_total(client, project_id) == 1
    assert _queue_total(client, project_id, "overdue") == 1
    assert _queue_total(client, project_id, "today") == 1
    today_queue = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/follow-ups?queue=today",
        headers=_headers(write=False),
    )
    assert hidden["id"] in {item["id"] for item in today_queue.json()["items"]}
    assert "North today" not in today_queue.text
    opened_record = client.get(base, headers=_headers(write=False))
    assert opened_record.status_code == 200
    assert opened_record.json()["values"]["school_name"] == "North school"
    member_completed = client.get(_completed(project_id), headers=_headers(write=False))
    assert member_completed.json()["total"] == 0
    assert "North school" not in member_completed.text

    _become(platform, USER_ID, "manager@example.com")
    connection = connect(database_path())
    connection.execute(
        "UPDATE records SET created_at = ? WHERE id = ?",
        ("2020-01-02T00:00:00+00:00", member_record.json()["id"]),
    )
    connection.commit()
    connection.close()
    period = client.get(
        _kpi(project_id) + f"?created_from={created_day}&created_to={created_day}",
        headers=_headers(write=False),
    )
    assert period.status_code == 200, period.text
    assert period.json()["active_records"] == 2
    assert period.json()["records_created"] == 1
    assert _record_total(client, project_id, created_from=created_day, created_to=created_day) == 1
    older = client.get(
        _kpi(project_id) + "?created_from=2020-01-02&created_to=2020-01-02",
        headers=_headers(write=False),
    )
    assert older.json()["records_created"] == 1
    assert _record_total(client, project_id, created_from="2020-01-02", created_to="2020-01-02") == 1
    rejected = client.get(_kpi(project_id) + "?q=North", headers=_headers(write=False))
    assert rejected.status_code == 422

    current = client.get(base, headers=_headers(write=False))
    assert current.status_code == 200
    archived = client.post(
        f"{base}/archive",
        headers=_headers(write=True),
        json={"expected_updated_at": current.json()["updated_at"]},
    )
    assert archived.status_code == 200
    after = client.get(_kpi(project_id), headers=_headers(write=False)).json()
    assert after["active_records"] == 1
    assert after["follow_ups"]["overdue"] == 1
    assert after["follow_ups"]["today"] == 0
    assert after["follow_ups"]["upcoming"] == 0
    assert after["follow_ups"]["completed"] == 0
    assert _queue_total(client, project_id, "today") == 0


def test_empty_project_and_cross_tenant_kpis_stay_closed(tmp_path, monkeypatch) -> None:
    platform = _platform()
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client, code="EMPTY", name="Empty yard")
    report = client.get(_kpi(project_id), headers=_headers(write=False))
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["active_records"] == 0
    assert body["records_created"] is None
    assert body["records_by_form"] == []
    assert body["follow_ups"] == {
        "overdue": 0,
        "today": 0,
        "upcoming": 0,
        "completed": 0,
        "by_owner": [],
        "by_due_date": [],
    }
    foreign = client.get(
        f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/kpis",
        headers=_headers(write=False),
    )
    assert foreign.status_code == 404
    _become(platform, OUTSIDE_ID, "outside@example.com")
    denied = client.get(_kpi(project_id), headers=_headers(write=False))
    assert denied.status_code == 404
    assert "Empty yard" not in denied.text


def test_kpi_due_dates_stay_json_strings_when_postgres_returns_dates() -> None:
    """PostgreSQL CAST AS date is a datetime.date. The KPI body must still encode."""

    class Rows:
        def execute(self, _sql, _params):
            return self

        def fetchall(self):
            return [
                {"queue": "overdue", "due_date": date(2026, 10, 1), "count": 1},
                {"queue": "upcoming", "due_date": "2026-11-20", "count": 1},
            ]

    rows = _by_due_date(
        Rows(),
        "tenant",
        "project",
        None,
        "2026-10-26T18:30:00.000000+00:00",
        "2026-10-27T18:30:00.000000+00:00",
    )
    assert rows == [
        {"queue": "overdue", "due_date": "2026-10-01", "count": 1},
        {"queue": "upcoming", "due_date": "2026-11-20", "count": 1},
    ]
    json.dumps({"follow_ups": {"by_due_date": rows}})


def _kpi(project_id: str) -> str:
    return f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/kpis"


def _completed(project_id: str) -> str:
    return f"{_kpi(project_id)}/completed-follow-ups"


def _record_total(client, project_id: str, *, form_id: str = "", created_from: str = "", created_to: str = "") -> int:
    params = []
    if form_id:
        params.append(f"form_id={form_id}")
    if created_from:
        params.append(f"created_from={created_from}")
    if created_to:
        params.append(f"created_to={created_to}")
    suffix = f"?{'&'.join(params)}" if params else ""
    response = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records{suffix}",
        headers=_headers(write=False),
    )
    assert response.status_code == 200, response.text
    return response.json()["total"]


def _queue_total(client, project_id: str, queue: str, owner: str = "") -> int:
    suffix = f"?queue={queue}"
    if owner:
        suffix += f"&owner_user_id={owner}"
    response = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/follow-ups{suffix}",
        headers=_headers(write=False),
    )
    assert response.status_code == 200, response.text
    return response.json()["total"]
