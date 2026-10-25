"""Seed CRM projects, forms, records, follow-ups, and one import fixture.

Calls the CRM HTTP API with a Control Plane session. It does not open the
Control Plane database and does not print passwords.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path


def fail(message: str) -> None:
    print(f"FAILED {message}")
    raise SystemExit(1)


def status(action: str, subject: str) -> None:
    print(f"{action} {subject}")


def project_fields(catalog: dict, project: dict) -> list[dict]:
    return list(catalog["common_fields"]) + list(project["extra_fields"])


def field_shape(spec: dict) -> dict:
    return {
        "field_key": spec["field_key"],
        "label": spec["label"],
        "field_type": spec["field_type"],
        "required": bool(spec["required"]),
        "section_name": spec.get("section_name") or "",
        "options": [tuple(item) for item in spec.get("options") or []],
        "currency_code": spec.get("currency_code"),
    }


def api_field_shape(field: dict) -> dict:
    options = field.get("options") or []
    return {
        "field_key": field.get("field_key"),
        "label": field.get("label"),
        "field_type": field.get("field_type"),
        "required": bool(field.get("required")),
        "section_name": field.get("section_name") or "",
        "options": [(item.get("value"), item.get("label")) for item in options if isinstance(item, dict)],
        "currency_code": field.get("currency_code"),
    }


def compare_fields(existing: list[dict], desired: list[dict]) -> str:
    """Return match, prefix, or conflict. A prefix can receive the remaining fields."""

    current = [
        api_field_shape(item)
        for item in sorted(existing, key=lambda item: int(item.get("position") or 0))
    ]
    expected = [field_shape(item) for item in desired]
    if len(current) > len(expected):
        return "conflict"
    for index, spec in enumerate(expected):
        if index >= len(current):
            return "prefix"
        if current[index] != spec:
            return "conflict"
    return "match"


def field_payload(spec: dict, *, include_key: bool) -> dict:
    payload = {
        "label": spec["label"],
        "field_type": spec["field_type"],
        "required": bool(spec["required"]),
        "section_name": spec.get("section_name") or "",
    }
    if include_key:
        payload["field_key"] = spec["field_key"]
    if spec.get("options"):
        payload["options"] = [{"value": value, "label": label} for value, label in spec["options"]]
    if spec.get("currency_code"):
        payload["currency_code"] = spec["currency_code"]
    return payload


def values_match(stored: dict, desired: dict) -> bool:
    if set(stored) != set(desired):
        return False
    for key, expected in desired.items():
        actual = stored[key]
        if isinstance(expected, (int, float)) and not isinstance(expected, bool) and isinstance(actual, (int, float)):
            if float(actual) != float(expected):
                return False
        elif actual != expected:
            return False
    return True


def plan_actions(existing: set[str], desired: list[str]) -> dict[str, list[str]]:
    return {
        "create": [key for key in desired if key not in existing],
        "reuse": [key for key in desired if key in existing],
    }


def message_of(response) -> str:
    try:
        body = response.json()
    except Exception:
        return f"HTTP {response.status_code}"
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"]
    return f"HTTP {response.status_code}"


class Api:
    def __init__(self, platform: str, crm: str, email: str, password: str) -> None:
        import httpx

        self.platform = httpx.Client(base_url=platform.rstrip("/"), timeout=30.0)
        self.crm = httpx.Client(base_url=crm.rstrip("/"), timeout=30.0)
        response = self.platform.post("/api/v1/auth/login", json={"email": email, "password": password})
        if response.status_code != 200:
            fail(f"Control Plane sign-in failed: {message_of(response)}")
        self.csrf = self.platform.cookies.get("aadi_csrf")
        self.session_cookie = self.platform.cookies.get("aadi_session")
        if not self.csrf or not self.session_cookie:
            fail("Control Plane sign-in did not return session cookies.")
        for cookie in self.platform.cookies.jar:
            self.crm.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
        status("verified", "crm-sign-in")

    def close(self) -> None:
        self.platform.close()
        self.crm.close()

    def request(
        self,
        target: str,
        method: str,
        path: str,
        payload: dict | None = None,
        *,
        ok: set[int],
        params: dict | None = None,
    ):
        client = self.crm if target == "crm" else self.platform
        headers = {}
        if method.upper() != "GET":
            headers["X-CSRF-Token"] = self.csrf
        response = client.request(method, path, json=payload, headers=headers, params=params)
        if response.status_code not in ok:
            detail = message_of(response)
            fail(f"{method} {path} failed: {detail}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


def ensure_project(api: Api, tenant_id: str, project: dict) -> str:
    listing = api.request("crm", "GET", f"/api/v1/tenants/{tenant_id}/projects", ok={200})
    matches = [item for item in listing.get("items", []) if item.get("code") == project["code"]]
    if len(matches) > 1:
        fail(f"More than one project uses code {project['code']}.")
    if matches:
        current = matches[0]
        if current.get("name") != project["name"]:
            fail(f"Project {project['code']} exists with a different name. It was not changed.")
        status("reused", f"project {project['code']}")
        return str(current["id"])
    created = api.request(
        "crm",
        "POST",
        f"/api/v1/tenants/{tenant_id}/projects",
        {"code": project["code"], "name": project["name"], "description": project["description"]},
        ok={201},
    )
    status("created", f"project {project['code']}")
    return str(created["id"])


def ensure_form(api: Api, tenant_id: str, project_id: str, project: dict, fields: list[dict]) -> dict:
    listing = api.request(
        "crm", "GET", f"/api/v1/tenants/{tenant_id}/projects/{project_id}/forms", ok={200}
    )
    matches = [item for item in listing.get("items", []) if item.get("name") == project["form_name"]]
    if len(matches) > 1:
        fail(f"More than one form is named {project['form_name']}.")
    if not matches:
        form = api.request(
            "crm",
            "POST",
            f"/api/v1/tenants/{tenant_id}/projects/{project_id}/forms",
            {"name": project["form_name"], "description": project["description"]},
            ok={201},
        )
        status("created", f"form {project['form_name']}")
    else:
        form = matches[0]
        if form.get("description") != project["description"]:
            fail(f"Form {project['form_name']} exists with a different description. It was not changed.")
        status("reused", f"form {project['form_name']}")
    comparison = compare_fields(form.get("fields") or [], fields)
    if comparison == "conflict":
        fail(f"Form {project['form_name']} fields do not match the seed. They were not changed.")
    if comparison == "prefix":
        existing = len(form.get("fields") or [])
        for spec in fields[existing:]:
            form = api.request(
                "crm",
                "POST",
                f"/api/v1/tenants/{tenant_id}/projects/{project_id}/forms/{form['id']}/fields",
                field_payload(spec, include_key=True),
                ok={201},
            )
            status("created", f"field {spec['field_key']}")
        comparison = compare_fields(form.get("fields") or [], fields)
        if comparison != "match":
            fail(f"Form {project['form_name']} fields still do not match after adding missing fields.")
    else:
        for spec in fields:
            status("reused", f"field {spec['field_key']}")
    if not form.get("current_published_version_id"):
        published = api.crm.post(
            f"/api/v1/tenants/{tenant_id}/projects/{project_id}/forms/{form['id']}/versions",
            headers={"X-CSRF-Token": api.csrf},
        )
        if published.status_code == 201:
            status("created", f"form-version {project['form_name']}")
        elif published.status_code == 409 and "already published" in message_of(published):
            status("reused", f"form-version {project['form_name']}")
        else:
            fail(f"Form publish failed: {message_of(published)}")
        form = api.request(
            "crm",
            "GET",
            f"/api/v1/tenants/{tenant_id}/projects/{project_id}/forms/{form['id']}",
            ok={200},
        )
    else:
        status("reused", f"form-version {project['form_name']}")
    if not form.get("current_published_version_id"):
        fail(f"Form {project['form_name']} has no published version.")
    return form


def ensure_record(api: Api, tenant_id: str, project_id: str, form_id: str, record: dict, user_id: str) -> str:
    name = record["values"]["contact_record_name"]
    listing = api.request(
        "crm",
        "GET",
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/records",
        ok={200},
        params={"q": name, "limit": 25},
    )
    matches = [item for item in listing.get("items", []) if item.get("display_name") == name]
    if len(matches) > 1:
        fail(f"More than one record is named {name}. None was changed.")
    if matches:
        detail = api.request(
            "crm",
            "GET",
            f"/api/v1/tenants/{tenant_id}/projects/{project_id}/records/{matches[0]['id']}",
            ok={200},
        )
        if detail.get("tenant_id") != tenant_id or detail.get("project_id") != project_id:
            fail(f"Record {name} is not in the expected tenant and project.")
        if not values_match(detail.get("values") or {}, record["values"]):
            fail(f"Record {name} exists with different values. It was not changed.")
        status("reused", f"record {record['seed_key']}")
        record_id = str(detail["id"])
    else:
        created = api.request(
            "crm",
            "POST",
            f"/api/v1/tenants/{tenant_id}/projects/{project_id}/records",
            {"form_id": form_id, "source": "manual", "values": record["values"]},
            ok={201},
        )
        if created.get("tenant_id") != tenant_id or created.get("project_id") != project_id:
            fail(f"Created record {name} was not stored on the expected tenant and project.")
        status("created", f"record {record['seed_key']}")
        record_id = str(created["id"])
    follow_up = record.get("follow_up")
    if follow_up:
        ensure_follow_up(api, tenant_id, project_id, record_id, follow_up, user_id, record["seed_key"])
    return record_id


def ensure_follow_up(api: Api, tenant_id: str, project_id: str, record_id: str, follow_up: dict, user_id: str, seed_key: str) -> None:
    listing = api.request(
        "crm",
        "GET",
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups",
        ok={200},
    )
    if any(item.get("summary") == follow_up["summary"] for item in listing.get("items", [])):
        status("reused", f"follow-up {seed_key}")
        return
    payload = {
        "task_type": follow_up["task_type"],
        "owner_user_id": user_id,
        "due_date": follow_up["due_date"],
        "due_time": follow_up["due_time"],
        "summary": follow_up["summary"],
    }
    if follow_up.get("call_status"):
        payload["call_status"] = follow_up["call_status"]
    api.request(
        "crm",
        "POST",
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/records/{record_id}/follow-ups",
        payload,
        ok={201},
    )
    status("created", f"follow-up {seed_key}")


def fixture_bytes(fields: list[dict], row: dict) -> bytes:
    headers = [field["label"] for field in fields]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow({field["label"]: row[field["field_key"]] for field in fields})
    return buffer.getvalue().encode("utf-8")


def ensure_import(api: Api, tenant_id: str, project_id: str, form: dict, fields: list[dict], fixture: dict, fixture_path: Path) -> None:
    content = fixture_bytes(fields, fixture["row"])
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    if not fixture_path.is_file() or fixture_path.read_bytes() != content:
        fixture_path.write_bytes(content)
        status("created", "import-fixture")
    else:
        status("reused", "import-fixture")
    import base64

    job = api.request(
        "crm",
        "POST",
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/imports",
        {
            "form_id": form["id"],
            "idempotency_key": fixture["idempotency_key"],
            "filename": fixture["filename"],
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
        ok={201},
    )
    if job.get("status") == "completed":
        status("reused", "import")
        return
    columns = {}
    labels = {field["label"]: field["field_key"] for field in fields}
    for header in job.get("headers") or []:
        if header not in labels:
            fail(f"Import column {header} is not a seed field. The import was not committed.")
        columns[header] = labels[header]
    api.request(
        "crm",
        "PATCH",
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/imports/{job['id']}/mapping",
        {"columns": columns},
        ok={200},
    )
    api.request(
        "crm",
        "POST",
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/imports/{job['id']}/preview",
        None,
        ok={200},
    )
    finished = api.request(
        "crm",
        "POST",
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/imports/{job['id']}/commit",
        None,
        ok={200},
    )
    if finished.get("status") != "completed":
        fail("Import did not complete.")
    status("created", "import")


def seed(args: argparse.Namespace) -> None:
    password = os.environ.get("IDENTITY_PASSWORD", "")
    if not password:
        fail("IDENTITY_PASSWORD is not set.")
    state = json.loads(args.state.read_text(encoding="utf-8"))
    tenant_id = state.get("tenant_id")
    user_id = state.get("user_id")
    if not tenant_id or not user_id:
        fail("Control Plane seed state has no tenant or user.")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    api = Api(args.platform, args.crm, state.get("email") or args.email, password)
    try:
        shell = api.request("crm", "GET", f"/api/v1/shell/tenants/{tenant_id}", ok={200})
        if shell.get("available") is not True or shell.get("tenant_id") != tenant_id:
            fail("CRM shell could not obtain tenant context.")
        status("verified", "crm-shell")
        for project in catalog["projects"]:
            project_id = ensure_project(api, tenant_id, project)
            fields = project_fields(catalog, project)
            form = ensure_form(api, tenant_id, project_id, project, fields)
            for record in project["records"]:
                ensure_record(api, tenant_id, project_id, str(form["id"]), record, user_id)
            fixture = catalog.get("import_fixture")
            if fixture and fixture.get("project_code") == project["code"]:
                ensure_import(api, tenant_id, project_id, form, fields, fixture, args.fixture)
    finally:
        api.close()
    status("verified", "crm-seed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed CRM development projects and records.")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--platform", default=os.environ.get("CONTROL_PLANE_API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--crm", default=os.environ.get("CRM_API_BASE_URL", "http://localhost:8001"))
    parser.add_argument("--email", default=os.environ.get("CRM_ADMIN_EMAIL", "crm.admin@example.test"))
    args = parser.parse_args()
    seed(args)


if __name__ == "__main__":
    main()
