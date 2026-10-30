"""CRM role and assignment behavior on the disposable PostgreSQL database.

The SQLite role tests remove CRM_DATABASE_URL and count every row in a blank
file. They must not be pointed at PostgreSQL. These tests use a unique tenant
per case, mock only the Control Plane, and delete rows for that tenant after
proving the connection is still aadi_crm_test on loopback port 5433.

Published form versions cannot be deleted: migration 004 installs an
immutability trigger. These tests therefore do not publish forms or insert
records. Record authorization is exercised through the records route and
authorize_record against PostgreSQL membership and role rows.
"""

from __future__ import annotations

import os
import re
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.projects import Caller, authorize_record
from app.api.shell import get_platform_client
from app.db import PostgresConnection, apply_postgres_migrations, connect, resolve_database
from app.main import create_app
from app.platform_client import PlatformCallError
from app.project_access import RecordRef
from app.roles_store import module_keys_for_member
from tests.test_postgres_support import (
    DISPOSABLE_DATABASE,
    DISPOSABLE_ROLE,
    assert_disposable_test_database,
)
from tests.test_projects import (
    LEADS,
    MANAGE,
    PROJECT_ACCESS,
    RECORDS_ACCESS,
    FakePlatform,
    _access,
    _become,
    _headers,
    _person,
)
from tests.test_roles import ROLES_MANAGE

USERS_READ = "users.read"
AUDIT_READ = "audit.read"
CATALOG = [LEADS, PROJECT_ACCESS, MANAGE, RECORDS_ACCESS]
ADMIN_KEYS = [ROLES_MANAGE, USERS_READ, LEADS, PROJECT_ACCESS, RECORDS_ACCESS, MANAGE]
PLANE_KEYS = [LEADS, PROJECT_ACCESS, RECORDS_ACCESS, MANAGE, ROLES_MANAGE, AUDIT_READ]
OWNED = (
    "tenant_role_assignments",
    "tenant_role_permissions",
    "project_memberships",
    "projects",
    "tenant_roles",
)
UNTOUCHED = (
    "form_definitions",
    "form_fields",
    "form_versions",
    "records",
    "record_values",
    "follow_ups",
    "record_activities",
    "reminder_deliveries",
    "import_jobs",
    "import_rows",
)
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _require_identity(connection) -> None:
    if not isinstance(connection, PostgresConnection):
        raise RuntimeError("Refusing to continue because the connection is not PostgreSQL.")
    row = connection.execute(
        """
        SELECT current_database() AS db, current_user AS role_name, inet_server_port() AS port
        """
    ).fetchone()
    if (
        row is None
        or row["db"] != DISPOSABLE_DATABASE
        or row["role_name"] != DISPOSABLE_ROLE
        or int(row["port"]) != 5433
    ):
        raise RuntimeError("Refusing to write because the PostgreSQL target is not the disposable test database.")


def _count(connection, table: str, tenant_id: str | None = None) -> int:
    if tenant_id is None:
        row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    else:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM {table} WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
    return int(row["count"])


def _totals(connection, tables: tuple[str, ...]) -> dict[str, int]:
    return {table: _count(connection, table) for table in tables}


def _owned_for(connection, tenant_id: str) -> dict[str, int]:
    return {table: _count(connection, table, tenant_id) for table in OWNED}


def _assert_new_tenant(tenant_id: str) -> None:
    if tenant_id == "tenant-postgres" or _UUID.fullmatch(tenant_id) is None:
        raise RuntimeError("Refusing a tenant id that is not a new UUID.")


class CrmPostgres:
    def __init__(self, client: TestClient, platform: FakePlatform, baseline: dict[str, dict[str, int]]) -> None:
        self.client = client
        self.platform = platform
        self.baseline = baseline
        self.tenants: list[str] = []

    def tenant(self) -> str:
        tenant_id = str(uuid4())
        _assert_new_tenant(tenant_id)
        connection = connect()
        try:
            _require_identity(connection)
            if any(_owned_for(connection, tenant_id).values()):
                raise RuntimeError("Refusing a tenant id that already has rows.")
        finally:
            connection.rollback()
            connection.close()
        self.tenants.append(tenant_id)
        return tenant_id

    def read(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        connection = connect()
        try:
            _require_identity(connection)
            return list(connection.execute(sql, params).fetchall())
        finally:
            connection.rollback()
            connection.close()

    def update_one(self, sql: str, params: tuple[object, ...]) -> None:
        connection = connect()
        try:
            _require_identity(connection)
            cursor = connection.execute(sql, params)
            if cursor.rowcount != 1:
                connection.rollback()
                raise AssertionError("Expected to update one tenant-scoped row.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def cleanup(self) -> None:
        connection = connect()
        try:
            _require_identity(connection)
            for tenant_id in self.tenants:
                _assert_new_tenant(tenant_id)
                for table in OWNED:
                    before = _count(connection, table, tenant_id)
                    cursor = connection.execute(
                        f"DELETE FROM {table} WHERE tenant_id = ?",
                        (tenant_id,),
                    )
                    if cursor.rowcount != before:
                        connection.rollback()
                        raise AssertionError("Tenant cleanup deleted a different number of rows than it counted.")
            owned = _totals(connection, OWNED)
            untouched = _totals(connection, UNTOUCHED)
            preserved = _owned_for(connection, "tenant-postgres")
            leftover = {
                tenant_id: _owned_for(connection, tenant_id)
                for tenant_id in self.tenants
                if any(_owned_for(connection, tenant_id).values())
            }
            if (
                owned != self.baseline["owned"]
                or untouched != self.baseline["untouched"]
                or preserved != self.baseline["preserved"]
                or leftover
            ):
                connection.rollback()
                raise AssertionError("PostgreSQL cleanup would change existing rows, so it was rolled back.")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


@pytest.fixture
def crm(monkeypatch) -> CrmPostgres:
    url = os.environ.get("CRM_TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("CRM_TEST_DATABASE_URL is not set")
    assert_disposable_test_database(url)
    monkeypatch.delenv("CRM_DATABASE_PATH", raising=False)
    monkeypatch.setenv("CRM_DATABASE_URL", url)
    monkeypatch.setenv(
        "CRM_DATABASE_SSLMODE",
        os.environ.get("CRM_TEST_DATABASE_SSLMODE", "disable"),
    )
    target = resolve_database()
    if target.dialect != "postgresql" or target.database_name != DISPOSABLE_DATABASE:
        raise RuntimeError("Refusing to open a database that is not aadi_crm_test.")
    apply_postgres_migrations()
    connection = connect()
    try:
        _require_identity(connection)
        baseline = {
            "owned": _totals(connection, OWNED),
            "untouched": _totals(connection, UNTOUCHED),
            "preserved": _owned_for(connection, "tenant-postgres"),
        }
    finally:
        connection.rollback()
        connection.close()
    platform = FakePlatform()
    application = create_app()
    application.dependency_overrides[get_platform_client] = lambda: platform
    session = CrmPostgres(TestClient(application), platform, baseline)
    try:
        yield session
    finally:
        session.cleanup()


def _as_caller(
    platform: FakePlatform,
    tenant_id: str,
    user_id: str,
    email: str,
    membership_id: str,
    keys: list[str],
    features: tuple[str, ...] = ("lead_management", "project_management", "records"),
) -> None:
    platform.access_by_tenant[tenant_id] = _access(
        UUID(tenant_id),
        membership_id=membership_id,
        features=features,
    )
    platform.permissions_by_tenant[tenant_id] = list(keys)
    _become(platform, user_id, email)


def _role(client: TestClient, tenant_id: str, name: str, description: str = "") -> dict[str, object]:
    created = client.post(
        f"/api/v1/tenants/{tenant_id}/roles",
        headers=_headers(write=True),
        json={"name": name, "description": description},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["tenant_id"] == tenant_id
    assert "tenant_membership_id" not in body
    return body


def _grant(client: TestClient, tenant_id: str, role_id: str, key: str) -> None:
    granted = client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": key},
    )
    assert granted.status_code == 200, granted.text


def _assign(client: TestClient, tenant_id: str, role_id: str, user_id: str):
    return client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/assignments",
        headers=_headers(write=True),
        json={"user_id": user_id},
    )


def _assignment_rows(crm: CrmPostgres, tenant_id: str) -> list[dict[str, object]]:
    return crm.read(
        """
        SELECT role_id, user_id, status, tenant_membership_id
        FROM tenant_role_assignments
        WHERE tenant_id = ?
        ORDER BY created_at, id
        """,
        (tenant_id,),
    )


def _effective_keys(tenant_id: str, user_id: str, membership_id: str, plane: list[str]) -> list[str]:
    connection = connect()
    try:
        _require_identity(connection)
        return module_keys_for_member(
            connection,
            tenant_id=tenant_id,
            user_id=user_id,
            tenant_membership_id=membership_id,
            control_plane_keys=plane,
        )
    finally:
        connection.rollback()
        connection.close()


def test_postgres_role_lifecycle_and_permission_grants(crm: CrmPostgres) -> None:
    tenant_id = crm.tenant()
    actor = str(uuid4())
    membership_id = str(uuid4())
    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", membership_id, ADMIN_KEYS)
    catalog = crm.client.get(
        f"/api/v1/tenants/{tenant_id}/crm-permissions",
        headers=_headers(write=False),
    )
    assert catalog.status_code == 200
    assert catalog.json()["items"] == CATALOG
    assert "roles.manage" not in catalog.text
    assert "users.read" not in catalog.text
    assert "audit.read" not in catalog.text
    listed = crm.client.get(f"/api/v1/tenants/{tenant_id}/roles", headers=_headers(write=False))
    assert listed.status_code == 200
    assert listed.json()["items"] == []

    created = _role(crm.client, tenant_id, "Desk leads", "Reads the desk queue")
    role_id = str(created["id"])
    assert created["status"] == "active"
    assert created["permissions"] == []
    duplicate = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles",
        headers=_headers(write=True),
        json={"name": "desk leads"},
    )
    assert duplicate.status_code == 409
    updated = crm.client.patch(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}",
        headers=_headers(write=True),
        json={"name": "Desk editors", "description": "Edited queue"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Desk editors"
    assert updated.json()["description"] == "Edited queue"
    _grant(crm.client, tenant_id, role_id, LEADS)
    repeated = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    assert repeated.status_code == 200
    _grant(crm.client, tenant_id, role_id, PROJECT_ACCESS)
    permissions = crm.client.get(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/permissions",
        headers=_headers(write=False),
    )
    assert permissions.status_code == 200
    assert permissions.json()["items"] == [LEADS, PROJECT_ACCESS]
    removed = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/permissions/remove",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    assert removed.status_code == 200
    assert removed.json()["items"] == [PROJECT_ACCESS]
    missing = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/permissions/remove",
        headers=_headers(write=True),
        json={"permission_key": LEADS},
    )
    assert missing.status_code == 404
    deactivated = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/deactivate",
        headers=_headers(write=True),
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"
    assert deactivated.json()["permissions"] == [PROJECT_ACCESS]
    again = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/deactivate",
        headers=_headers(write=True),
    )
    assert again.status_code == 200
    blocked = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/permissions",
        headers=_headers(write=True),
        json={"permission_key": RECORDS_ACCESS},
    )
    assert blocked.status_code == 409
    stored = crm.read(
        """
        SELECT current_database() AS db, roles.status, grants.permission_key
        FROM tenant_roles AS roles
        LEFT JOIN tenant_role_permissions AS grants
          ON grants.role_id = roles.id AND grants.tenant_id = roles.tenant_id
        WHERE roles.tenant_id = ? AND roles.id = ?
        """,
        (tenant_id, role_id),
    )
    assert stored[0]["db"] == DISPOSABLE_DATABASE
    assert stored[0]["status"] == "inactive"
    assert [row["permission_key"] for row in stored] == [PROJECT_ACCESS]
    visible = crm.client.get(f"/api/v1/tenants/{tenant_id}/roles", headers=_headers(write=False))
    assert [item["id"] for item in visible.json()["items"]] == [role_id]
    assert {item["tenant_id"] for item in visible.json()["items"]} == {tenant_id}


def test_postgres_assignment_refreshes_membership_and_keeps_revoked_history(crm: CrmPostgres) -> None:
    tenant_id = crm.tenant()
    actor = str(uuid4())
    subject = str(uuid4())
    actor_membership = str(uuid4())
    subject_membership = str(uuid4())
    stale_membership = str(uuid4())
    crm.platform.users_by_tenant[tenant_id] = [
        _person(actor, "actor@example.com", membership_id=actor_membership),
        _person(subject, "subject@example.com", membership_id=subject_membership),
    ]
    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", actor_membership, ADMIN_KEYS)
    role_id = str(_role(crm.client, tenant_id, "Projects")["id"])
    _grant(crm.client, tenant_id, role_id, PROJECT_ACCESS)
    created = _assign(crm.client, tenant_id, role_id, subject)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "active"
    assert "tenant_membership_id" not in created.text
    assert _assignment_rows(crm, tenant_id)[0]["tenant_membership_id"] == subject_membership
    again = _assign(crm.client, tenant_id, role_id, subject)
    assert again.status_code == 200
    assert len([row for row in _assignment_rows(crm, tenant_id) if row["status"] == "active"]) == 1
    crm.update_one(
        """
        UPDATE tenant_role_assignments
        SET tenant_membership_id = ?
        WHERE tenant_id = ? AND role_id = ? AND user_id = ?
        """,
        (stale_membership, tenant_id, role_id, subject),
    )
    refreshed = _assign(crm.client, tenant_id, role_id, subject)
    assert refreshed.status_code == 200
    assert _assignment_rows(crm, tenant_id)[0]["tenant_membership_id"] == subject_membership
    revoked = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/assignments/remove",
        headers=_headers(write=True),
        json={"user_id": subject},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    assert (
        crm.client.post(
            f"/api/v1/tenants/{tenant_id}/roles/{role_id}/assignments/remove",
            headers=_headers(write=True),
            json={"user_id": subject},
        ).status_code
        == 404
    )
    rows = _assignment_rows(crm, tenant_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "revoked"
    assert rows[0]["tenant_membership_id"] == subject_membership
    database = crm.read("SELECT current_database() AS db")
    assert database[0]["db"] == DISPOSABLE_DATABASE


def test_postgres_assignment_rejects_invalid_targets_and_missing_users_read(crm: CrmPostgres) -> None:
    tenant_id = crm.tenant()
    other_tenant = crm.tenant()
    actor = str(uuid4())
    subject = str(uuid4())
    outsider = str(uuid4())
    actor_membership = str(uuid4())
    subject_membership = str(uuid4())
    outsider_membership = str(uuid4())
    crm.platform.users_by_tenant[tenant_id] = [
        _person(subject, "subject@example.com", membership_id=subject_membership),
    ]
    crm.platform.users_by_tenant[other_tenant] = [
        _person(outsider, "outsider@example.com", membership_id=outsider_membership),
    ]
    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", actor_membership, ADMIN_KEYS)
    _as_caller(crm.platform, other_tenant, actor, "actor@example.com", outsider_membership, ADMIN_KEYS)
    role_id = str(_role(crm.client, tenant_id, "Tenant desk")["id"])
    _grant(crm.client, tenant_id, role_id, LEADS)

    extra = _assign_body(crm, tenant_id, role_id, subject, {"tenant_membership_id": outsider_membership})
    assert extra.status_code == 422
    crm.platform.users_by_tenant[tenant_id] = [
        _person(subject, "subject@example.com", active=False, membership_id=subject_membership),
    ]
    assert _assign(crm.client, tenant_id, role_id, subject).status_code == 422
    crm.platform.users_by_tenant[tenant_id] = [
        _person(subject, "subject@example.com", status="inactive", membership_id=subject_membership),
    ]
    assert _assign(crm.client, tenant_id, role_id, subject).status_code == 422
    crm.platform.users_by_tenant[tenant_id] = [
        _person(subject, "subject@example.com", membership_id=""),
    ]
    assert _assign(crm.client, tenant_id, role_id, subject).status_code == 422
    assert _assignment_rows(crm, tenant_id) == []

    crm.platform.users_by_tenant[tenant_id] = [
        _person(subject, "subject@example.com", membership_id=subject_membership),
    ]
    missing_user = _assign(crm.client, tenant_id, role_id, outsider)
    assert missing_user.status_code == 404
    assert "outsider@example.com" not in missing_user.text
    foreign = _assign(crm.client, other_tenant, role_id, outsider)
    assert foreign.status_code == 404
    assert "Tenant desk" not in foreign.text

    crm.platform.permissions_by_tenant[tenant_id] = [ROLES_MANAGE]
    crm.platform.user_lookups.clear()
    denied = _assign(crm.client, tenant_id, role_id, subject)
    assert denied.status_code == 403
    assert crm.platform.user_lookups == []
    crm.platform.permissions_by_tenant[tenant_id] = [ROLES_MANAGE, USERS_READ]
    crm.platform.users_by_tenant[tenant_id] = PlatformCallError(403)
    assert _assign(crm.client, tenant_id, role_id, subject).status_code == 403
    crm.platform.users_by_tenant[tenant_id] = [
        _person(subject, "subject@example.com", membership_id=subject_membership),
    ]
    deactivated = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/deactivate",
        headers=_headers(write=True),
    )
    assert deactivated.status_code == 200
    inactive = _assign(crm.client, tenant_id, role_id, subject)
    assert inactive.status_code == 409
    assert inactive.json()["error"]["message"] == "This role is inactive."
    assert _assignment_rows(crm, tenant_id) == []
    assert _assignment_rows(crm, other_tenant) == []


def _assign_body(crm: CrmPostgres, tenant_id: str, role_id: str, user_id: str, extra: dict[str, str]):
    return crm.client.post(
        f"/api/v1/tenants/{tenant_id}/roles/{role_id}/assignments",
        headers=_headers(write=True),
        json={"user_id": user_id, **extra},
    )


def test_postgres_role_grants_intersect_and_invalid_assignments_do_not_restore_keys(
    crm: CrmPostgres,
) -> None:
    tenant_id = crm.tenant()
    actor = str(uuid4())
    subject = str(uuid4())
    actor_membership = str(uuid4())
    subject_membership = str(uuid4())
    stale_membership = str(uuid4())
    crm.platform.users_by_tenant[tenant_id] = [
        _person(actor, "actor@example.com", membership_id=actor_membership),
        _person(subject, "subject@example.com", membership_id=subject_membership),
    ]
    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", actor_membership, ADMIN_KEYS)
    created = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "North yard"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    added = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/members",
        headers=_headers(write=True),
        json={"user_id": subject, "role": "project_member"},
    )
    assert added.status_code == 201, added.text
    leads_role = str(_role(crm.client, tenant_id, "Leads")["id"])
    records_role = str(_role(crm.client, tenant_id, "Records")["id"])
    _grant(crm.client, tenant_id, leads_role, LEADS)
    _grant(crm.client, tenant_id, records_role, RECORDS_ACCESS)
    assert _assign(crm.client, tenant_id, leads_role, subject).status_code == 201
    assert _assign(crm.client, tenant_id, records_role, subject).status_code == 201

    _as_caller(crm.platform, tenant_id, subject, "subject@example.com", subject_membership, PLANE_KEYS)
    assert _leads(crm, tenant_id) == 200
    assert _records(crm, tenant_id, project_id) == 200
    projects = crm.client.get(f"/api/v1/tenants/{tenant_id}/projects", headers=_headers(write=False))
    assert projects.status_code == 403
    assert "North yard" not in projects.text
    assert _rename(crm, tenant_id, project_id, "Taken") == 403
    secret = _decide(tenant_id, project_id, subject, subject_membership, PLANE_KEYS, actor)
    own = _decide(tenant_id, project_id, subject, subject_membership, PLANE_KEYS, subject)
    assert secret.allowed is False
    assert own.allowed is True
    assert own.scope == "assigned"

    _as_caller(
        crm.platform,
        tenant_id,
        subject,
        "subject@example.com",
        subject_membership,
        PLANE_KEYS,
        features=("lead_management", "project_management"),
    )
    assert _records(crm, tenant_id, project_id) == 403
    _as_caller(crm.platform, tenant_id, subject, "subject@example.com", subject_membership, PLANE_KEYS)
    crm.update_one(
        """
        UPDATE tenant_role_assignments
        SET tenant_membership_id = ?
        WHERE tenant_id = ? AND role_id = ? AND user_id = ?
        """,
        (stale_membership, tenant_id, records_role, subject),
    )
    assert _leads(crm, tenant_id) == 200
    assert _records(crm, tenant_id, project_id) == 403
    assert _effective_keys(tenant_id, subject, subject_membership, PLANE_KEYS) == [
        LEADS,
        ROLES_MANAGE,
        AUDIT_READ,
    ]

    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", actor_membership, ADMIN_KEYS)
    assert (
        crm.client.post(
            f"/api/v1/tenants/{tenant_id}/roles/{leads_role}/deactivate",
            headers=_headers(write=True),
        ).status_code
        == 200
    )
    _as_caller(crm.platform, tenant_id, subject, "subject@example.com", subject_membership, PLANE_KEYS)
    assert _leads(crm, tenant_id) == 403

    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", actor_membership, ADMIN_KEYS)
    for role_id in (leads_role, records_role):
        removed = crm.client.post(
            f"/api/v1/tenants/{tenant_id}/roles/{role_id}/assignments/remove",
            headers=_headers(write=True),
            json={"user_id": subject},
        )
        assert removed.status_code == 200
        assert removed.json()["status"] == "revoked"
    _as_caller(crm.platform, tenant_id, subject, "subject@example.com", subject_membership, PLANE_KEYS)
    assert _effective_keys(tenant_id, subject, subject_membership, PLANE_KEYS) == [ROLES_MANAGE, AUDIT_READ]
    assert _leads(crm, tenant_id) == 403
    assert _records(crm, tenant_id, project_id) == 403
    hidden = crm.client.get(
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert hidden.status_code == 403
    assert "North yard" not in hidden.text
    assert _rename(crm, tenant_id, project_id, "Taken") == 403
    database = crm.read("SELECT current_database() AS db")
    assert database[0]["db"] == DISPOSABLE_DATABASE


def test_postgres_unassigned_access_and_project_binding_stay_enforced(crm: CrmPostgres) -> None:
    tenant_id = crm.tenant()
    actor = str(uuid4())
    subject = str(uuid4())
    actor_membership = str(uuid4())
    subject_membership = str(uuid4())
    stale_membership = str(uuid4())
    crm.platform.users_by_tenant[tenant_id] = [
        _person(actor, "actor@example.com", membership_id=actor_membership),
        _person(subject, "subject@example.com", membership_id=subject_membership),
    ]
    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", actor_membership, ADMIN_KEYS)
    created = crm.client.post(
        f"/api/v1/tenants/{tenant_id}/projects",
        headers=_headers(write=True),
        json={"code": "N-1", "name": "North yard"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    before = crm.client.get(
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert before.status_code == 200
    assert before.json()["access"]["role"] == "project_manager"
    assert _effective_keys(tenant_id, actor, actor_membership, ADMIN_KEYS) == ADMIN_KEYS

    role_id = str(_role(crm.client, tenant_id, "Projects")["id"])
    _grant(crm.client, tenant_id, role_id, PROJECT_ACCESS)
    assert _assign(crm.client, tenant_id, role_id, actor).status_code == 201
    assert _rename(crm, tenant_id, project_id, "Manager kept it") == 200
    _as_caller(
        crm.platform,
        tenant_id,
        actor,
        "actor@example.com",
        actor_membership,
        ADMIN_KEYS,
        features=("lead_management", "records"),
    )
    denied = crm.client.get(f"/api/v1/tenants/{tenant_id}/projects", headers=_headers(write=False))
    assert denied.status_code == 403
    assert "Manager kept it" not in denied.text

    _as_caller(crm.platform, tenant_id, actor, "actor@example.com", actor_membership, ADMIN_KEYS)
    stranger_role = str(_role(crm.client, tenant_id, "Manage only inside CRM")["id"])
    _grant(crm.client, tenant_id, stranger_role, PROJECT_ACCESS)
    _grant(crm.client, tenant_id, stranger_role, MANAGE)
    assert _assign(crm.client, tenant_id, stranger_role, subject).status_code == 201
    _as_caller(
        crm.platform,
        tenant_id,
        subject,
        "subject@example.com",
        subject_membership,
        [PROJECT_ACCESS],
    )
    hidden = crm.client.get(f"/api/v1/tenants/{tenant_id}/projects", headers=_headers(write=False))
    assert hidden.status_code == 200
    assert hidden.json()["items"] == []
    assert "Manager kept it" not in hidden.text
    assert MANAGE not in _effective_keys(tenant_id, subject, subject_membership, [PROJECT_ACCESS, MANAGE])

    _as_caller(
        crm.platform,
        tenant_id,
        actor,
        "actor@example.com",
        actor_membership,
        [PROJECT_ACCESS, ROLES_MANAGE, USERS_READ],
    )
    assert _rename(crm, tenant_id, project_id, "Still the manager") == 200
    crm.update_one(
        """
        UPDATE project_memberships
        SET tenant_membership_id = ?
        WHERE tenant_id = ? AND project_id = ? AND user_id = ?
        """,
        (stale_membership, tenant_id, project_id, actor),
    )
    rebound = crm.client.get(
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}",
        headers=_headers(write=False),
    )
    assert rebound.status_code == 404
    assert "Still the manager" not in rebound.text
    database = crm.read("SELECT current_database() AS db")
    assert database[0]["db"] == DISPOSABLE_DATABASE


def _leads(crm: CrmPostgres, tenant_id: str) -> int:
    return crm.client.get(
        f"/api/v1/shell/tenants/{tenant_id}/leads",
        headers=_headers(write=False),
    ).status_code


def _records(crm: CrmPostgres, tenant_id: str, project_id: str) -> int:
    return crm.client.get(
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}/records",
        headers=_headers(write=False),
    ).status_code


def _rename(crm: CrmPostgres, tenant_id: str, project_id: str, name: str) -> int:
    return crm.client.patch(
        f"/api/v1/tenants/{tenant_id}/projects/{project_id}",
        headers=_headers(write=True),
        json={"name": name},
    ).status_code


def _decide(
    tenant_id: str,
    project_id: str,
    user_id: str,
    membership_id: str,
    plane: list[str],
    assignee_user_id: str,
):
    connection = connect()
    try:
        _require_identity(connection)
        keys = module_keys_for_member(
            connection,
            tenant_id=tenant_id,
            user_id=user_id,
            tenant_membership_id=membership_id,
            control_plane_keys=plane,
        )
        return authorize_record(
            connection,
            tenant_id=tenant_id,
            project_id=project_id,
            caller=Caller(
                user_id=user_id,
                email="subject@example.com",
                keys=keys,
                tenant_membership_id=membership_id,
            ),
            record=RecordRef(
                tenant_id=tenant_id,
                project_id=project_id,
                assignee_user_id=assignee_user_id,
            ),
        )
    finally:
        connection.rollback()
        connection.close()
