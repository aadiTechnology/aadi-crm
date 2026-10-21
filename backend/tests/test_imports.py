"""Import jobs stay idempotent, and exports stay inside the caller's records."""

import base64
import threading
from io import BytesIO
from zipfile import ZipFile

from app.db import connect
from app.imports_store import commit_job
from app.spreadsheets import neutralize, read_table, write_csv, write_xlsx
from tests.test_forms import _dropdown, _project, _text_field
from tests.test_form_versions import _add, _form, _publish
from tests.test_projects import OTHER_ID, TENANT_A, TENANT_B, USER_ID, _allow, _become, _client, _headers, _person
from tests.test_records import _create


def _setup(tmp_path, monkeypatch):
    from tests.test_projects import FakePlatform

    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com"),
    ]
    client = _client(tmp_path, monkeypatch, platform)
    project_id = _project(client)
    form_id = _form(client, project_id, name="Import enquiry")
    _add(client, project_id, form_id, _text_field())
    _add(
        client,
        project_id,
        form_id,
        {
            "field_key": "email",
            "label": "Email",
            "field_type": "email",
            "required": False,
            "section_name": "Contact",
        },
    )
    _add(
        client,
        project_id,
        form_id,
        {
            "field_key": "mobile",
            "label": "Mobile",
            "field_type": "mobile",
            "required": False,
            "section_name": "Contact",
        },
    )
    _add(client, project_id, form_id, _dropdown())
    published = _publish(client, project_id, form_id)
    assert published.status_code == 201
    return platform, client, project_id, form_id


def _encoded(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _upload(client, project_id: str, form_id: str, text: str, key: str = "batch-0001", filename: str = "leads.csv"):
    return client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports",
        headers=_headers(write=True),
        json={
            "form_id": form_id,
            "idempotency_key": key,
            "filename": filename,
            "content_base64": _encoded(text),
            "tenant_id": str(TENANT_B),
        },
    )


def _mapping(headers: list[str]) -> dict[str, str | None]:
    aliases = {
        "school name": "school_name",
        "email": "email",
        "mobile": "mobile",
        "priority": "priority",
    }
    return {header: aliases.get(header.casefold()) for header in headers}


def _map(client, project_id: str, job_id: str, headers: list[str]):
    return client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/mapping",
        headers=_headers(write=True),
        json={"columns": _mapping(headers)},
    )


def _counts(tmp_path) -> tuple[int, int]:
    connection = connect(tmp_path / "projects.sqlite")
    try:
        records = connection.execute("SELECT COUNT(*) AS count FROM records").fetchone()["count"]
        sequence = connection.execute("SELECT COALESCE(MAX(sequence), 0) AS sequence FROM records").fetchone()["sequence"]
        return int(records), int(sequence)
    finally:
        connection.close()


def _reconciles(summary: dict) -> None:
    assert summary["header_included"] is False
    assert summary["input_rows"] == (
        summary["accepted"]
        + summary["rejected"]
        + summary["skipped"]
        + summary["awaiting_review"]
        + summary["not_committed"]
    )


def test_csv_and_xlsx_parse_limits_and_formula_cells() -> None:
    headers, rows = read_table("leads.csv", b"School name,Email\nNorth,north@example.com\n")
    assert headers == ["School name", "Email"]
    assert rows[0][0] == 2
    assert rows[0][1]["Email"] == "north@example.com"
    try:
        read_table("leads.csv", b"School name,School name\nA,B\n")
        raise AssertionError("duplicate headers were accepted")
    except Exception as exc:
        assert "repeated" in exc.message
    try:
        read_table("empty.csv", b"")
        raise AssertionError("empty file was accepted")
    except Exception as exc:
        assert "empty" in exc.message.lower()
    sheet = write_xlsx(["School name"], [["=1+1"]])
    parsed = read_table("records.xlsx", sheet)
    assert parsed[1][0][1]["School name"].startswith("'=")
    formula = _formula_workbook()
    loaded = read_table("formula.xlsx", formula)
    assert loaded[1][0][2]
    assert "formula" in loaded[1][0][2][0].lower()
    exported = write_csv(["School name"], [["=cmd"]])
    assert b"'=cmd" in exported


def test_formula_limit_uses_the_configured_ceiling(monkeypatch) -> None:
    monkeypatch.setattr("app.spreadsheets.MAX_BYTES", 10)
    try:
        read_table("leads.csv", b"School name\nNorth school\n")
        raise AssertionError("the patched ceiling was ignored")
    except Exception as exc:
        assert "1 MB" in exc.message


def test_preview_does_not_create_records_and_commit_reconciles(tmp_path, monkeypatch) -> None:
    _platform, client, project_id, form_id = _setup(tmp_path, monkeypatch)
    _create(client, project_id, form_id, {"school_name": "Existing", "email": "north@example.com", "mobile": "9876543210"})
    before = _counts(tmp_path)
    text = "\n".join(
        [
            "School name,Email,Mobile,Priority,Notes",
            "North,North@Example.com,98765-43210,hot,keep me",
            ",bad-email,123,urgent,missing name",
            "Second,second@example.com,9123456789,warm,unique",
        ]
    )
    uploaded = _upload(client, project_id, form_id, text)
    assert uploaded.status_code == 201
    body = uploaded.json()
    assert "tenant_id" not in body["rows"][0]["source"] or body["rows"][0]["source"].get("tenant_id") is None
    assert body["unmapped_columns"] == []
    mapped = _map(client, project_id, body["id"], body["headers"])
    assert mapped.status_code == 200
    assert "Notes" in mapped.json()["unmapped_columns"]
    preview = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{body['id']}/preview",
        headers=_headers(write=True),
    )
    assert preview.status_code == 200
    first = preview.json()
    assert _counts(tmp_path) == before
    again = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{body['id']}/preview",
        headers=_headers(write=True),
    )
    assert again.status_code == 200
    assert _counts(tmp_path) == before
    summary = first["summary"]
    _reconciles(summary)
    assert summary["accepted"] == 0
    assert summary["records_created"] == 0
    assert summary["preview_accepted"] + summary["preview_rejected"] + summary["preview_skipped"] + summary["preview_awaiting_review"] == summary["input_rows"]
    duplicate = next(row for row in first["rows"] if row["row_number"] == 2)
    invalid = next(row for row in first["rows"] if row["row_number"] == 3)
    clean = next(row for row in first["rows"] if row["row_number"] == 4)
    assert duplicate["candidates"]
    assert duplicate["candidates"][0]["public_number"]
    assert "Existing" == duplicate["candidates"][0]["display_name"]
    assert invalid["errors"]
    assert clean["candidates"] == []
    assert duplicate["unmapped"]["Notes"] == "keep me"
    decided = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{body['id']}/decisions",
        headers=_headers(write=True),
        json={"rows": [{"row_number": 2, "decision": "skip"}, {"row_number": 4, "decision": "accept_new"}]},
    )
    assert decided.status_code == 200
    committed = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{body['id']}/commit",
        headers=_headers(write=True),
    )
    assert committed.status_code == 200
    done = committed.json()
    _reconciles(done["summary"])
    assert done["summary"]["accepted"] == 1
    assert done["summary"]["rejected"] == 1
    assert done["summary"]["skipped"] == 1
    assert done["summary"]["awaiting_review"] == 0
    assert done["summary"]["not_committed"] == 0
    assert done["status"] == "partial"
    assert _counts(tmp_path) == (before[0] + 1, before[1] + 1)
    report = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{body['id']}/errors",
        headers=_headers(write=False),
    )
    assert report.status_code == 200
    assert "row_number,field,message" in report.text
    assert "bad-email" not in report.text or "email" in report.text.lower()
    assert "secret" not in report.text.lower()
    repeated = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{body['id']}/commit",
        headers=_headers(write=True),
    )
    assert repeated.status_code == 200
    assert repeated.json()["summary"]["accepted"] == 1
    assert _counts(tmp_path) == (before[0] + 1, before[1] + 1)
    retried = _upload(client, project_id, form_id, text, key="batch-0001")
    assert retried.status_code == 201
    assert retried.json()["id"] == body["id"]
    assert _counts(tmp_path) == (before[0] + 1, before[1] + 1)


def test_same_file_key_does_not_create_a_second_record_under_two_commits(tmp_path, monkeypatch) -> None:
    _platform, client, project_id, form_id = _setup(tmp_path, monkeypatch)
    text = "School name,Email\nOnly one,only@example.com\n"
    uploaded = _upload(client, project_id, form_id, text, key="batch-repeat")
    job_id = uploaded.json()["id"]
    assert _map(client, project_id, job_id, uploaded.json()["headers"]).status_code == 200
    first = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/commit",
        headers=_headers(write=True),
    )
    second = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/commit",
        headers=_headers(write=True),
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["summary"]["accepted"] == 1
    assert second.json()["summary"] == first.json()["summary"]
    assert _counts(tmp_path) == (1, 1)
    conflict = _upload(
        client,
        project_id,
        form_id,
        "School name\nDifferent\n",
        key="batch-repeat",
    )
    assert conflict.status_code == 409


def test_authorization_duplicate_visibility_and_export_filters(tmp_path, monkeypatch) -> None:
    platform, client, project_id, form_id = _setup(tmp_path, monkeypatch)
    created = _create(
        client,
        project_id,
        form_id,
        {"school_name": "=Hidden school", "email": "hidden@example.com"},
    )
    assert created.status_code == 201
    other_project = _project(client, code="N-2", name="Other yard")
    other_form = _form(client, other_project, name="Other form")
    _add(client, other_project, other_form, _text_field())
    _add(
        client,
        other_project,
        other_form,
        {"field_key": "email", "label": "Email", "field_type": "email", "required": False, "section_name": "Contact"},
    )
    assert _publish(client, other_project, other_form).status_code == 201
    assert _create(client, other_project, other_form, {"school_name": "Other project", "email": "hidden@example.com"}).status_code == 201
    uploaded = _upload(
        client,
        project_id,
        form_id,
        "School name,Email\nVisible,hidden@example.com\n",
        key="batch-scope",
    )
    job_id = uploaded.json()["id"]
    assert _map(client, project_id, job_id, uploaded.json()["headers"]).status_code == 200
    preview = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/preview",
        headers=_headers(write=True),
    )
    candidates = preview.json()["rows"][0]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["display_name"] == "=Hidden school"
    assert "Other project" not in preview.text
    missing = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports",
        headers={"cookie": "aadi_session=member"},
        json={"form_id": form_id, "idempotency_key": "batch-csrf1", "filename": "leads.csv", "content_base64": _encoded("School name\nA\n")},
    )
    assert missing.status_code == 401
    foreign = client.post(
        f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/imports",
        headers=_headers(write=True),
        json={"form_id": form_id, "idempotency_key": "batch-foreign", "filename": "leads.csv", "content_base64": _encoded("School name\nA\n")},
    )
    assert foreign.status_code == 404
    assert "=Hidden school" not in foreign.text
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    denied_job = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}",
        headers=_headers(write=False),
    )
    assert denied_job.status_code == 404
    assert "hidden@example.com" not in denied_job.text
    denied_report = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/errors",
        headers=_headers(write=False),
    )
    assert denied_report.status_code == 404
    member_preview = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/preview",
        headers=_headers(write=True),
    )
    assert member_preview.status_code == 404
    _become(platform, USER_ID, "manager@example.com")
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records?q=%3DHidden",
        headers=_headers(write=False),
    )
    assert listed.status_code == 200
    exported = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/record-exports?format=csv&q=%3DHidden&form_id={form_id}",
        headers=_headers(write=False),
    )
    assert exported.status_code == 200
    assert exported.headers["x-crm-export-rows"] == str(listed.json()["total"])
    assert b"'=Hidden school" in exported.content
    assert "Other project" not in exported.text
    empty = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/record-exports?format=csv&q=no-such-record&form_id={form_id}",
        headers=_headers(write=False),
    )
    assert empty.status_code == 200
    assert empty.headers["x-crm-export-rows"] == "0"
    workbook = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/record-exports?format=xlsx&form_id={form_id}&source=manual",
        headers=_headers(write=False),
    )
    assert workbook.status_code == 200
    reread = read_table("records.xlsx", workbook.content)
    assert any(row[1]["School name"].startswith("'=") for row in reread[1])
    _become(platform, OTHER_ID, "member@example.com")
    member_export = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/record-exports?format=csv&form_id={form_id}",
        headers=_headers(write=False),
    )
    assert member_export.status_code == 200
    assert "=Hidden school" not in member_export.text
    assert member_export.headers["x-crm-export-rows"] == "0"


def test_concurrent_commit_inserts_one_record(tmp_path, monkeypatch) -> None:
    _platform, client, project_id, form_id = _setup(tmp_path, monkeypatch)
    uploaded = _upload(client, project_id, form_id, "School name\nConcurrent\n", key="batch-race")
    job_id = uploaded.json()["id"]
    assert _map(client, project_id, job_id, uploaded.json()["headers"]).status_code == 200
    barrier = threading.Barrier(2)
    failures: list[BaseException] = []

    def run() -> None:
        connection = connect(tmp_path / "projects.sqlite")
        try:
            barrier.wait(timeout=5)
            commit_job(
                connection,
                tenant_id=str(TENANT_A),
                project_id=project_id,
                project_code="N-1",
                job_id=job_id,
                actor_user_id=USER_ID,
                assignee_user_id=None,
                allowed=lambda _record_id, _assignee: True,
            )
        except BaseException as exc:
            failures.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert failures == []
    assert _counts(tmp_path) == (1, 1)


def test_malformed_files_are_rejected(tmp_path, monkeypatch) -> None:
    _platform, client, project_id, form_id = _setup(tmp_path, monkeypatch)
    rejected = _upload(client, project_id, form_id, "", key="batch-empty")
    assert rejected.status_code == 422
    workbook = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports",
        headers=_headers(write=True),
        json={
            "form_id": form_id,
            "idempotency_key": "batch-bad-xlsx",
            "filename": "leads.xlsx",
            "content_base64": base64.b64encode(b"not-a-workbook").decode("ascii"),
        },
    )
    assert workbook.status_code == 422
    assert _counts(tmp_path) == (0, 0)
    assert neutralize("=1+1").startswith("'")
    assert neutralize("North") == "North"


def _formula_workbook() -> bytes:
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1"><c r="A1" t="inlineStr"><is><t>School name</t></is></c></row>
    <row r="2"><c r="A2"><f>1+1</f><v>2</v></c></row>
  </sheetData>
</worksheet>"""
    payload = BytesIO()
    with ZipFile(payload, "w") as package:
        package.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        package.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        package.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Records" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        package.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        package.writestr("xl/worksheets/sheet1.xml", sheet)
    return payload.getvalue()
