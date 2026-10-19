"""CRM-owned project store. This is not the Control Plane database."""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
_COLUMNS = (
    "id, tenant_id, code, name, description, status, created_by, created_at, updated_at"
)
_MEMBER_COLUMNS = (
    "id, tenant_id, project_id, user_id, role, scope_policy, status, "
    "created_by, updated_by, created_at, updated_at"
)


class DuplicateProjectCode(Exception):
    """A project code is already stored for this tenant."""


class DuplicateMembership(Exception):
    """An active membership already exists for this user on this project."""


class LastProjectManager(Exception):
    """The project would be left without an active project manager."""


class InactiveMembership(Exception):
    """The membership row is not active."""


@dataclass(frozen=True)
class ProjectRow:
    id: str
    tenant_id: str
    code: str
    name: str
    description: str
    status: str
    created_by: str | None
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def database_path() -> Path:
    configured = os.environ.get("CRM_DATABASE_PATH", "").strip()
    path = Path(configured) if configured else Path(__file__).resolve().parents[1] / "data" / "aadi_crm.sqlite"
    if "aadi_platform" in path.as_posix().lower():
        raise RuntimeError("Refusing a database path that names the Control Plane database.")
    return path


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def apply_migrations(path: Path | None = None) -> Path:
    """Apply pending CRM SQL scripts. Scripts must not drop tables or delete rows."""

    target = path or database_path()
    connection = connect(target)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM crm_schema_migrations")
        }
        for script in sorted(MIGRATIONS.glob("*.sql")):
            if script.name in applied:
                continue
            sql = script.read_text(encoding="utf-8")
            if "drop table" in sql.lower() or "delete from" in sql.lower():
                raise RuntimeError(f"Refusing destructive migration {script.name}")
            connection.executescript(sql)
            if script.name == "002_project_memberships.sql":
                _backfill_creator_memberships(connection)
            connection.execute(
                "INSERT INTO crm_schema_migrations (version, applied_at) VALUES (?, ?)",
                (script.name, _now()),
            )
            connection.commit()
    finally:
        connection.close()
    return target


def create_project(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    code: str,
    name: str,
    description: str,
    created_by: str | None,
) -> ProjectRow:
    project_id = str(uuid4())
    now = _now()
    try:
        connection.execute(
            f"""
            INSERT INTO projects ({_COLUMNS})
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (project_id, tenant_id, code, name, description, created_by, now, now),
        )
    except sqlite3.IntegrityError:
        connection.rollback()
        raise DuplicateProjectCode from None
    if created_by and created_by.strip():
        connection.execute(
            f"""
            INSERT INTO project_memberships ({_MEMBER_COLUMNS})
            VALUES (?, ?, ?, ?, 'project_manager', 'project', 'active', ?, ?, ?, ?)
            """,
            (str(uuid4()), tenant_id, project_id, created_by, created_by, created_by, now, now),
        )
    connection.commit()
    created = get_project(connection, tenant_id, project_id)
    if created is None:
        raise RuntimeError("The project insert did not persist.")
    return created


def list_projects(
    connection: sqlite3.Connection,
    tenant_id: str,
    *,
    query: str,
    status: str,
    member_user_id: str | None = None,
) -> list[ProjectRow]:
    clauses = ["tenant_id = ?"]
    params: list[str] = [tenant_id]
    if member_user_id is not None:
        clauses.append(
            """id IN (
                SELECT project_id FROM project_memberships
                WHERE tenant_id = ? AND user_id = ? AND status = 'active'
            )"""
        )
        params.extend([tenant_id, member_user_id])
    if query:
        like = _like(query)
        clauses.append(
            "(lower(code) LIKE ? ESCAPE '\\' OR lower(name) LIKE ? ESCAPE '\\' "
            "OR lower(description) LIKE ? ESCAPE '\\')"
        )
        params.extend([like, like, like])
    if status:
        clauses.append("status = ?")
        params.append(status)
    rows = connection.execute(
        f"""
        SELECT {_COLUMNS}
        FROM projects
        WHERE {" AND ".join(clauses)}
        ORDER BY lower(name), lower(code)
        """,
        params,
    )
    return [_row(row) for row in rows]


def get_project(connection: sqlite3.Connection, tenant_id: str, project_id: str) -> ProjectRow | None:
    row = connection.execute(
        f"SELECT {_COLUMNS} FROM projects WHERE tenant_id = ? AND id = ?",
        (tenant_id, project_id),
    ).fetchone()
    if row is None:
        return None
    return _row(row)


def update_project(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    *,
    name: str | None,
    description: str | None,
) -> ProjectRow | None:
    assignments: list[str] = []
    params: list[str] = []
    if name is not None:
        assignments.append("name = ?")
        params.append(name)
    if description is not None:
        assignments.append("description = ?")
        params.append(description)
    if not assignments:
        return get_project(connection, tenant_id, project_id)
    params.extend([_now(), tenant_id, project_id])
    cursor = connection.execute(
        f"""
        UPDATE projects
        SET {", ".join(assignments)}, updated_at = ?
        WHERE tenant_id = ? AND id = ?
        """,
        params,
    )
    connection.commit()
    if cursor.rowcount == 0:
        return None
    return get_project(connection, tenant_id, project_id)


def archive_project(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
) -> ProjectRow | None:
    existing = get_project(connection, tenant_id, project_id)
    if existing is None or existing.status == "archived":
        return existing
    connection.execute(
        """
        UPDATE projects
        SET status = 'archived', updated_at = ?
        WHERE tenant_id = ? AND id = ? AND status = 'active'
        """,
        (_now(), tenant_id, project_id),
    )
    connection.commit()
    return get_project(connection, tenant_id, project_id)


@dataclass(frozen=True)
class MembershipRow:
    id: str
    tenant_id: str
    project_id: str
    user_id: str
    role: str
    scope_policy: str
    status: str
    created_by: str | None
    updated_by: str | None
    created_at: str
    updated_at: str

    def as_dict(self, *, email: str | None) -> dict[str, str | None]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "email": email,
            "role": self.role,
            "scope_policy": self.scope_policy,
            "status": self.status,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def list_user_memberships(
    connection: sqlite3.Connection,
    tenant_id: str,
    user_id: str,
) -> list[MembershipRow]:
    rows = connection.execute(
        f"""
        SELECT {_MEMBER_COLUMNS}
        FROM project_memberships
        WHERE tenant_id = ? AND user_id = ?
        """,
        (tenant_id, user_id),
    )
    return [_member(row) for row in rows]


def list_project_memberships(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
) -> list[MembershipRow]:
    rows = connection.execute(
        f"""
        SELECT {_MEMBER_COLUMNS}
        FROM project_memberships
        WHERE tenant_id = ? AND project_id = ?
        ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at, id
        """,
        (tenant_id, project_id),
    )
    return [_member(row) for row in rows]


def get_project_membership(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    membership_id: str,
) -> MembershipRow | None:
    row = connection.execute(
        f"""
        SELECT {_MEMBER_COLUMNS}
        FROM project_memberships
        WHERE tenant_id = ? AND project_id = ? AND id = ?
        """,
        (tenant_id, project_id, membership_id),
    ).fetchone()
    if row is None:
        return None
    return _member(row)


def active_membership(
    connection: sqlite3.Connection,
    tenant_id: str,
    project_id: str,
    user_id: str,
) -> MembershipRow | None:
    row = connection.execute(
        f"""
        SELECT {_MEMBER_COLUMNS}
        FROM project_memberships
        WHERE tenant_id = ? AND project_id = ? AND user_id = ? AND status = 'active'
        """,
        (tenant_id, project_id, user_id),
    ).fetchone()
    if row is None:
        return None
    return _member(row)


def count_active_managers(connection: sqlite3.Connection, tenant_id: str, project_id: str) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM project_memberships
        WHERE tenant_id = ? AND project_id = ? AND role = 'project_manager' AND status = 'active'
        """,
        (tenant_id, project_id),
    ).fetchone()
    if row is None:
        return 0
    return int(row["count"])


def grant_membership(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    user_id: str,
    role: str,
    actor_id: str,
) -> MembershipRow | None:
    if get_project(connection, tenant_id, project_id) is None:
        return None
    if active_membership(connection, tenant_id, project_id, user_id) is not None:
        raise DuplicateMembership
    scope = _scope_for_role(role)
    membership_id = str(uuid4())
    now = _now()
    try:
        connection.execute(
            f"""
            INSERT INTO project_memberships ({_MEMBER_COLUMNS})
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
            """,
            (membership_id, tenant_id, project_id, user_id, role, scope, actor_id, actor_id, now, now),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise DuplicateMembership from None
    created = get_project_membership(connection, tenant_id, project_id, membership_id)
    if created is None:
        raise RuntimeError("The membership insert did not persist.")
    return created


def set_membership_role(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    membership_id: str,
    role: str,
    actor_id: str,
) -> MembershipRow | None:
    current = get_project_membership(connection, tenant_id, project_id, membership_id)
    if current is None:
        return None
    if current.status != "active":
        raise InactiveMembership
    if current.role == "project_manager" and role != "project_manager":
        if count_active_managers(connection, tenant_id, project_id) <= 1:
            raise LastProjectManager
    scope = _scope_for_role(role)
    connection.execute(
        """
        UPDATE project_memberships
        SET role = ?, scope_policy = ?, updated_by = ?, updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND id = ? AND status = 'active'
        """,
        (role, scope, actor_id, _now(), tenant_id, project_id, membership_id),
    )
    connection.commit()
    return get_project_membership(connection, tenant_id, project_id, membership_id)


def revoke_membership(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    membership_id: str,
    actor_id: str,
) -> MembershipRow | None:
    current = get_project_membership(connection, tenant_id, project_id, membership_id)
    if current is None:
        return None
    if current.status == "removed":
        return current
    if current.role == "project_manager" and count_active_managers(connection, tenant_id, project_id) <= 1:
        raise LastProjectManager
    connection.execute(
        """
        UPDATE project_memberships
        SET status = 'removed', updated_by = ?, updated_at = ?
        WHERE tenant_id = ? AND project_id = ? AND id = ? AND status = 'active'
        """,
        (actor_id, _now(), tenant_id, project_id, membership_id),
    )
    connection.commit()
    return get_project_membership(connection, tenant_id, project_id, membership_id)


def _backfill_creator_memberships(connection: sqlite3.Connection) -> None:
    """Give each existing project creator one active manager membership.

    Runs once, when the membership migration is first applied. A later removal
    is not restored on the next process start.
    """

    rows = connection.execute(
        """
        SELECT id, tenant_id, created_by, created_at
        FROM projects
        WHERE created_by IS NOT NULL AND length(trim(created_by)) > 0
        """
    ).fetchall()
    for row in rows:
        existing = connection.execute(
            """
            SELECT id FROM project_memberships
            WHERE project_id = ? AND user_id = ?
            """,
            (row["id"], row["created_by"]),
        ).fetchone()
        if existing is not None:
            continue
        connection.execute(
            f"""
            INSERT INTO project_memberships ({_MEMBER_COLUMNS})
            VALUES (?, ?, ?, ?, 'project_manager', 'project', 'active', ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                row["tenant_id"],
                row["id"],
                row["created_by"],
                row["created_by"],
                row["created_by"],
                row["created_at"],
                row["created_at"],
            ),
        )


def _scope_for_role(role: str) -> str:
    if role == "project_manager":
        return "project"
    if role == "project_member":
        return "assigned"
    raise ValueError(role)


def _member(row: sqlite3.Row) -> MembershipRow:
    return MembershipRow(
        id=row["id"],
        tenant_id=row["tenant_id"],
        project_id=row["project_id"],
        user_id=row["user_id"],
        role=row["role"],
        scope_policy=row["scope_policy"],
        status=row["status"],
        created_by=row["created_by"],
        updated_by=row["updated_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row(row: sqlite3.Row) -> ProjectRow:
    return ProjectRow(
        id=row["id"],
        tenant_id=row["tenant_id"],
        code=row["code"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _like(term: str) -> str:
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
