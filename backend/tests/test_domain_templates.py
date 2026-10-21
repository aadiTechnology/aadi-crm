"""Four domain templates stay on the published-form import path.

Paneerwala is profiled and not imported. The other three worksheets are
imported on a disposable database. The shared development database is not opened.
"""

import base64
import csv
import io
import json
from collections import Counter
from pathlib import Path

from app.domain_templates import (
    HIRING,
    PANEERWALA,
    PRESCHOOL,
    SOURCE_WORKBOOK,
    SPACE_VIEW,
    paneerwala_finding,
    prepare_import,
    sheet_profile,
)
from app.imports_store import _coerce
from app.spreadsheets import SpreadsheetError, read_table
from tests.test_forms import DEV_DATABASE
from tests.test_form_versions import _publish
from tests.test_projects import OTHER_ID, TENANT_A, TENANT_B, USER_ID, _allow, _become, _client, _headers, _person

EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "sprints" / "crm-s12" / "crosswalk.json"
_DATE_FIELD = {"field_type": "date", "label": "Inquiry Date", "field_key": "inquiry_date"}


def test_excel_serial_with_a_decimal_is_not_a_date_until_normalized() -> None:
    converted, problem = _coerce(_DATE_FIELD, "46362")
    assert problem is None
    assert converted == "2026-12-06"
    unchanged, _ = _coerce(_DATE_FIELD, "46362.0")
    assert unchanged == "46362.0"
    prepared = prepare_import(PRESCHOOL)
    assert b"46362.0" not in prepared["content"]
    assert b"2026-12-06" in prepared["content"]
    assert b"2026-07-21" in prepared["content"]


def test_four_sheet_workbook_is_rejected_and_paneerwala_is_not_prepared() -> None:
    content = SOURCE_WORKBOOK.read_bytes()
    try:
        read_table(SOURCE_WORKBOOK.name, content)
    except SpreadsheetError as exc:
        assert "one worksheet" in exc.message
    else:
        raise AssertionError("The four-sheet workbook must be rejected.")
    finding = paneerwala_finding()
    assert PANEERWALA.publish is False
    assert finding["data_rows"] == 24
    assert finding["blank_data_rows"] == 0
    assert finding["merges"] == []
    assert finding["formula_cells"] == 0
    assert finding["column_a_timestamps"] == 24
    assert finding["column_a_numeric_ids"] == 0
    assert finding["column_d_text_not_dates"] == 24
    assert finding["column_e_numbers"] == 24
    assert finding["order_column_values"] == 0
    assert finding["duplicate_headers"]["next follow-up"] == ["M", "O", "Q"]
    assert finding["blank_headers"] == ["AA", "AB", "AC", "AD"]
    try:
        prepare_import(PANEERWALA)
    except RuntimeError as exc:
        assert "No Paneerwala form is published" in str(exc)
    else:
        raise AssertionError("Paneerwala must not build an import file.")
    profile = sheet_profile()
    assert profile["Preschool"]["data_rows"] == 4
    assert profile["Space View"]["data_rows"] == 12
    assert profile["Hiring"]["data_rows"] == 13
    assert profile["Hiring"]["formula_cells"] == 12
    assert profile["Preschool"]["duplicate_headers"] == ["followup comments"]


def test_templates_reconcile_on_a_disposable_database(tmp_path, monkeypatch) -> None:
    before = DEV_DATABASE.stat()
    platform, client = _opened(tmp_path, monkeypatch)
    crosswalk = []
    summaries = {}
    for template in (PRESCHOOL, SPACE_VIEW, HIRING):
        prepared = prepare_import(template)
        project_id = _project(client, code=template.project_code, name=template.project_name)
        form_id, version_id = _publish_template(client, project_id, template)
        assert _record_total(client, project_id) == 0
        uploaded = _upload(client, project_id, form_id, template, prepared)
        assert uploaded.status_code == 201, uploaded.text
        job_id = uploaded.json()["id"]
        mapped = client.patch(
            f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/mapping",
            headers=_headers(write=True),
            json={"columns": prepared["mapping"]},
        )
        assert mapped.status_code == 200, mapped.text
        preview = client.post(
            f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/preview",
            headers=_headers(write=True),
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["status"] == "previewed"
        assert _record_total(client, project_id) == 0
        committed = _commit(client, project_id, job_id)
        assert committed.status_code == 200, committed.text
        body = committed.json()
        summary = body["summary"]
        _assert_equation(summary)
        assert summary["accepted"] == prepared["predicted_accepted"]
        assert summary["rejected"] == prepared["predicted_rejected"]
        assert summary["skipped"] == 0
        assert summary["awaiting_review"] == 0
        assert summary["not_committed"] == 0
        assert summary["input_rows"] == prepared["submitted_rows"]
        assert body["status"] == ("completed" if summary["rejected"] == 0 else "partial")
        assert _record_total(client, project_id) == summary["accepted"]
        repeated = _commit(client, project_id, job_id)
        assert repeated.status_code == 200
        assert repeated.json()["summary"] == summary
        assert _record_total(client, project_id) == summary["accepted"]
        replay = _upload(client, project_id, form_id, template, prepared)
        assert replay.status_code == 201
        assert replay.json()["id"] == job_id
        assert _record_total(client, project_id) == summary["accepted"]
        field_counts, links = _reconcile(client, project_id, version_id, template, prepared, body)
        crosswalk.extend(links)
        summaries[template.key] = {
            "project_id": project_id,
            "project_code": template.project_code,
            "form_id": form_id,
            "form_version_id": version_id,
            "import_job_id": job_id,
            "source_file": SOURCE_WORKBOOK.name,
            "worksheet": template.sheet_name,
            "mapping_version": template.idempotency_key,
            "source_data_rows": prepared["source_data_rows"],
            "excluded_before_import": prepared["excluded_rows"],
            "submitted_rows": prepared["submitted_rows"],
            "formula_cells_materialized": prepared["formula_cells"],
            "summary": summary,
            "target_records": summary["accepted"],
            "fields": field_counts,
        }
        foreign = client.get(
            f"/api/v1/tenants/{TENANT_B}/projects/{project_id}/imports/{job_id}",
            headers=_headers(write=False),
        )
        assert foreign.status_code == 404
        report = client.get(
            f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/errors",
            headers=_headers(write=False),
        )
        assert report.status_code == 200
        if template.key == "space_view":
            assert "2,inquiry_date,INQUIRY DATE must use YYYY-MM-DD." in report.text
    names = {
        item["name"]
        for item in client.get(f"/api/v1/tenants/{TENANT_A}/projects", headers=_headers(write=False)).json()["items"]
    }
    assert names == {"Preschool", "Space View", "Hiring"}
    preschool = summaries["preschool"]
    added = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{preschool['project_id']}/members",
        headers=_headers(write=True),
        json={"user_id": OTHER_ID, "role": "project_member"},
    )
    assert added.status_code == 201
    _become(platform, OTHER_ID, "member@example.com")
    denied = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{preschool['project_id']}/imports/{preschool['import_job_id']}/errors",
        headers=_headers(write=False),
    )
    assert denied.status_code == 404
    assert preschool["form_version_id"] not in denied.text
    _become(platform, USER_ID, "manager@example.com")
    hiring = summaries["hiring"]
    missing = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{hiring['project_id']}/imports/{hiring['import_job_id']}/commit",
        headers={"cookie": "aadi_session=member"},
    )
    assert missing.status_code == 401
    assert summaries["space_view"]["fields"]["sr_no"]["duplicate_values"] == 2
    assert summaries["preschool"]["fields"]["lead_id"]["duplicate_values"] == 0
    assert summaries["hiring"]["fields"]["lead_id"]["duplicate_values"] == 0
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps({"datasets": summaries, "crosswalk": crosswalk}, indent=2), encoding="utf-8")
    after = DEV_DATABASE.stat()
    assert after.st_size == before.st_size
    assert after.st_mtime_ns == before.st_mtime_ns


def test_synthetic_duplicate_review_and_formula_export(tmp_path, monkeypatch) -> None:
    _platform, client = _opened(tmp_path, monkeypatch)
    project_id = _project(client, code="SYNTH", name="Synthetic preschool")
    form_id, _version_id = _publish_template(client, project_id, PRESCHOOL)
    headers = [column.derived_header for column in PRESCHOOL.columns]
    content = _synthetic_csv(headers)
    uploaded = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports",
        headers=_headers(write=True),
        json={
            "form_id": form_id,
            "idempotency_key": "synthetic-preschool-v1",
            "filename": "synthetic-preschool.csv",
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    job_id = uploaded.json()["id"]
    mapped = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/mapping",
        headers=_headers(write=True),
        json={"columns": {column.derived_header: column.field_key for column in PRESCHOOL.columns}},
    )
    assert mapped.status_code == 200, mapped.text
    preview = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/preview",
        headers=_headers(write=True),
    )
    assert preview.status_code == 200, preview.text
    assert _record_total(client, project_id) == 0
    outcomes = {row["row_number"]: row["outcome"] for row in preview.json()["rows"]}
    assert outcomes[2] == "stored"
    assert any(row["candidates"] for row in preview.json()["rows"] if row["row_number"] == 2)
    decided = client.patch(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/decisions",
        headers=_headers(write=True),
        json={"rows": [{"row_number": 2, "decision": "accept_new"}, {"row_number": 4, "decision": "skip"}]},
    )
    assert decided.status_code == 200, decided.text
    committed = _commit(client, project_id, job_id)
    assert committed.status_code == 200, committed.text
    summary = committed.json()["summary"]
    _assert_equation(summary)
    assert summary["accepted"] == 1
    assert summary["rejected"] == 1
    assert summary["skipped"] == 1
    assert summary["awaiting_review"] == 0
    assert _record_total(client, project_id) == 1
    repeated = _commit(client, project_id, job_id)
    assert repeated.json()["summary"]["accepted"] == 1
    assert _record_total(client, project_id) == 1
    exported = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/record-exports?format=csv&form_id={form_id}",
        headers=_headers(write=False),
    )
    assert exported.status_code == 200
    assert "'=Example note" in exported.text
    assert "Example West" not in exported.text


def _opened(tmp_path, monkeypatch):
    from tests.test_projects import FakePlatform

    platform = FakePlatform()
    _allow(platform, TENANT_A)
    _allow(platform, TENANT_B)
    platform.users_by_tenant[str(TENANT_A)] = [
        _person(USER_ID, "manager@example.com"),
        _person(OTHER_ID, "member@example.com"),
    ]
    return platform, _client(tmp_path, monkeypatch, platform)


def _project(client, *, code: str, name: str) -> str:
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects",
        headers=_headers(write=True),
        json={"code": code, "name": name, "description": ""},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _publish_template(client, project_id: str, template) -> tuple[str, str]:
    created = client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms",
        headers=_headers(write=True),
        json={"name": template.form_name, "description": template.description},
    )
    assert created.status_code == 201, created.text
    form_id = created.json()["id"]
    for field in template.fields:
        added = client.post(
            f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}/fields",
            headers=_headers(write=True),
            json=dict(field),
        )
        assert added.status_code == 201, added.text
    published = _publish(client, project_id, form_id)
    assert published.status_code == 201, published.text
    assert published.json()["version_number"] == 1
    loaded = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/forms/{form_id}",
        headers=_headers(write=False),
    )
    assert loaded.status_code == 200
    fields = loaded.json()["fields"]
    assert [field["field_key"] for field in fields] == [field["field_key"] for field in template.fields]
    for actual, expected in zip(fields, template.fields, strict=True):
        assert actual["label"] == expected["label"]
        assert actual["field_type"] == expected["field_type"]
        assert actual["required"] is expected["required"]
        if "options" in expected:
            assert [item["value"] for item in actual["options"]] == [item["value"] for item in expected["options"]]
    assert loaded.json()["current_published_version_id"] == published.json()["id"]
    return form_id, published.json()["id"]


def _upload(client, project_id: str, form_id: str, template, prepared):
    return client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports",
        headers=_headers(write=True),
        json={
            "form_id": form_id,
            "idempotency_key": template.idempotency_key,
            "filename": prepared["filename"],
            "content_base64": base64.b64encode(prepared["content"]).decode("ascii"),
        },
    )


def _commit(client, project_id: str, job_id: str):
    return client.post(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/imports/{job_id}/commit",
        headers=_headers(write=True),
    )


def _record_total(client, project_id: str) -> int:
    listed = client.get(
        f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records",
        headers=_headers(write=False),
    )
    assert listed.status_code == 200, listed.text
    return int(listed.json()["total"])


def _assert_equation(summary: dict) -> None:
    assert summary["header_included"] is False
    assert summary["input_rows"] == (
        summary["accepted"]
        + summary["rejected"]
        + summary["skipped"]
        + summary["awaiting_review"]
        + summary["not_committed"]
    )


def _reconcile(client, project_id: str, version_id: str, template, prepared, job: dict):
    by_row = {row["row_number"]: row for row in job["rows"]}
    counts = {
        column.field_key: {"checked": 0, "exact": 0, "normalized": 0, "mismatch": 0, "missing": 0, "blank": 0}
        for column in template.columns
    }
    links = []
    identifiers: Counter[object] = Counter()
    title_key = {"preschool": "school_name", "space_view": "name", "hiring": "contact_person"}[template.key]
    for expected in prepared["expectations"]:
        row = by_row[expected["source_row"]]
        if expected["rejected"]:
            assert row["outcome"] == "rejected"
            assert row["record_id"] is None
            links.append(
                {
                    "template": template.key,
                    "source_row": expected["source_row"],
                    "source_identifier": expected["identifier"],
                    "import_job_id": job["id"],
                    "import_row": row["row_number"],
                    "record_id": None,
                    "public_number": None,
                    "outcome": "rejected",
                    "form_version_id": version_id,
                }
            )
            continue
        assert row["outcome"] == "accepted", row
        detail = client.get(
            f"/api/v1/tenants/{TENANT_A}/projects/{project_id}/records/{row['record_id']}",
            headers=_headers(write=False),
        )
        assert detail.status_code == 200, detail.text
        body = detail.json()
        assert body["form_version_id"] == version_id
        assert body["project_id"] == project_id
        assert body["source"] == "import"
        assert body["version_number"] == 1
        values = body["values"]
        assert body["display_name"] == values[title_key]
        identifiers[values[template.identifier_field]] += 1
        for column in template.columns:
            raw = str(expected["raw"][column.field_key])
            bucket = counts[column.field_key]
            if not raw.strip():
                assert column.field_key not in values
                bucket["blank"] += 1
                continue
            bucket["checked"] += 1
            actual = values.get(column.field_key)
            if actual is None:
                bucket["missing"] += 1
                continue
            kind = _match(column.transform, raw, actual, expected["stored"][column.field_key])
            assert kind != "mismatch", (template.key, expected["source_row"], column.field_key, kind)
            bucket[kind] += 1
        links.append(
            {
                "template": template.key,
                "source_row": expected["source_row"],
                "source_identifier": expected["identifier"],
                "import_job_id": job["id"],
                "import_row": row["row_number"],
                "record_id": row["record_id"],
                "public_number": body["public_number"],
                "outcome": "accepted",
                "form_version_id": version_id,
            }
        )
    for bucket in counts.values():
        assert bucket["mismatch"] == 0
        assert bucket["missing"] == 0
    counts[template.identifier_field]["duplicate_values"] = sum(1 for count in identifiers.values() if count > 1)
    return counts, links


def _match(transform: str, raw: str, actual: object, expected: object) -> str:
    if actual != expected:
        return "mismatch"
    if transform == "text":
        return "exact" if actual == raw else "normalized"
    if transform == "email":
        return "exact" if actual == raw.strip() else "normalized"
    if transform == "url":
        return "exact" if actual == raw.strip() else "normalized"
    if transform == "label":
        return "normalized"
    if transform == "whole_number":
        return "exact" if raw.strip() == str(expected) else "normalized"
    if transform in {"date", "mobile"}:
        return "exact" if raw.strip() == str(expected) else "normalized"
    return "mismatch"


def _synthetic_csv(headers: list[str]) -> bytes:
    def row(**values: str) -> list[str]:
        base = {header: "" for header in headers}
        base.update(values)
        return [base[header] for header in headers]

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(headers)
    writer.writerow(
        row(
            **{
                "Lead ID": "1",
                "Inquiry Date": "2026-10-01",
                "School Name": "Example North",
                "Mobile Number": "919800000099",
                "Email ID": "ada@example.com",
                "Selling Point": "=Example note",
            }
        )
    )
    writer.writerow(
        row(
            **{
                "Lead ID": "2",
                "Inquiry Date": "7351093.0",
                "School Name": "Example South",
                "Email ID": "not-an-email",
            }
        )
    )
    writer.writerow(
        row(
            **{
                "Lead ID": "3",
                "Inquiry Date": "2026-10-02",
                "School Name": "Example West",
                "Mobile Number": "919800000099",
                "Email ID": "west@example.com",
            }
        )
    )
    return buffer.getvalue().encode("utf-8")
