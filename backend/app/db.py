"""CRM-owned project store. This is not the Control Plane database."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
POSTGRES_MIGRATIONS = MIGRATIONS / "postgres"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_COLUMNS = (
    "id, tenant_id, code, name, description, status, created_by, created_at, updated_at"
)
_MEMBER_COLUMNS = (
    "id, tenant_id, project_id, user_id, role, scope_policy, status, "
    "created_by, updated_by, created_at, updated_at, tenant_membership_id"
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


def database_url() -> str:
    """Return the configured PostgreSQL URL, or an empty string when SQLite stays selected."""

    return os.environ.get("CRM_DATABASE_URL", "").strip()


@dataclass(frozen=True)
class DatabaseTarget:
    dialect: str
    path: Path | None = None
    url: str | None = None
    sslmode: str | None = None
    database_name: str = ""

    @property
    def label(self) -> str:
        if self.dialect == "sqlite":
            assert self.path is not None
            return self.path.name
        return self.database_name


def resolve_database() -> DatabaseTarget:
    """Choose SQLite unless CRM_DATABASE_URL is set. An invalid URL is an error."""

    configured = database_url()
    if not configured:
        path = database_path()
        return DatabaseTarget(dialect="sqlite", path=path, database_name=path.name)
    return postgres_target(configured)


def postgres_target(url: str) -> DatabaseTarget:
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    if scheme in {"postgresql+psycopg", "postgresql+psycopg2"}:
        raise RuntimeError(
            "CRM_DATABASE_URL must start with postgresql://. A SQLAlchemy driver suffix is not accepted."
        )
    if scheme not in {"postgresql", "postgres"}:
        raise RuntimeError("CRM_DATABASE_URL must be a PostgreSQL URL starting with postgresql://.")
    host = parsed.hostname
    if not host:
        raise RuntimeError("CRM_DATABASE_URL must include a host.")
    database_name = parsed.path.lstrip("/")
    if not database_name or "/" in database_name:
        raise RuntimeError("CRM_DATABASE_URL must include a database name.")
    if "aadi_platform" in database_name.lower():
        raise RuntimeError("Refusing a PostgreSQL database that names the Control Plane database.")
    sslmode = _sslmode(host)
    return DatabaseTarget(
        dialect="postgresql",
        url=url,
        sslmode=sslmode,
        database_name=database_name,
    )


def connect(path: Path | None = None):
    """Open the requested SQLite file, or PostgreSQL when no file is given and a URL is set."""

    if path is not None:
        return connect_sqlite(path)
    target = resolve_database()
    if target.dialect == "sqlite":
        assert target.path is not None
        return connect_sqlite(target.path)
    return connect_postgres(target)


def connect_sqlite(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def connect_postgres(target: DatabaseTarget):
    if target.dialect != "postgresql" or not target.url or not target.sslmode:
        raise RuntimeError("PostgreSQL was requested without a usable CRM_DATABASE_URL.")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise RuntimeError(
            "PostgreSQL is configured but the psycopg package is not installed."
        ) from None
    try:
        raw = psycopg.connect(
            target.url,
            sslmode=target.sslmode,
            connect_timeout=5,
            row_factory=dict_row,
        )
    except Exception:
        raise RuntimeError(
            f"Could not connect to PostgreSQL database {target.database_name}. "
            "SQLite was not used."
        ) from None
    connection = PostgresConnection(raw)
    connection.set_lock_wait(5000)
    return connection


def begin_immediate(connection, lock_key: str | None = None) -> None:
    """Start the write transaction used for numbering and other locked updates.

    SQLite takes the reserved lock with BEGIN IMMEDIATE. PostgreSQL takes a
    transaction advisory lock when lock_key is set, and keeps the unique
    indexes as the backstop. The caller commits or rolls back.
    """

    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("BEGIN IMMEDIATE")
        return
    connection.begin_immediate(lock_key)


def set_lock_wait(connection, milliseconds: int = 5000) -> None:
    if isinstance(connection, sqlite3.Connection):
        connection.execute(f"PRAGMA busy_timeout = {int(milliseconds)}")
        return
    connection.set_lock_wait(milliseconds)


def follow_up_due_date_expr(connection) -> str:
    """Civil date of a UTC follow-up stamp after adding Asia/Kolkata's fixed offset."""

    if isinstance(connection, sqlite3.Connection):
        return "date(datetime(replace(substr(follow_ups.due_at, 1, 19), 'T', ' '), '+330 minutes'))"
    return (
        "CAST((CAST(substring(follow_ups.due_at FROM 1 FOR 19) AS timestamp) "
        "+ interval '330 minutes') AS date)"
    )


def apply_postgres_migrations() -> str:
    """Apply pending PostgreSQL scripts. This does not open or modify SQLite."""

    if not database_url():
        raise RuntimeError(
            "CRM_DATABASE_URL is not set. PostgreSQL migrations were not applied and SQLite was not opened."
        )
    target = resolve_database()
    if target.dialect != "postgresql":
        raise RuntimeError("CRM_DATABASE_URL did not select PostgreSQL.")
    connection = connect_postgres(target)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS crm_schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM crm_schema_migrations")
        }
        for script in sorted(POSTGRES_MIGRATIONS.glob("*.sql")):
            if script.name in applied:
                continue
            sql = script.read_text(encoding="utf-8")
            if "drop table" in sql.lower() or "delete from" in sql.lower():
                raise RuntimeError(f"Refusing destructive migration {script.name}")
            try:
                for statement in split_sql(sql):
                    connection.execute(statement)
                if script.name == "002_project_memberships.sql":
                    _backfill_creator_memberships(connection)
                connection.execute(
                    "INSERT INTO crm_schema_migrations (version, applied_at) VALUES (?, ?)",
                    (script.name, _now()),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
    finally:
        connection.close()
    return target.database_name


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
    tenant_membership_id: str | None = None,
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
            VALUES (?, ?, ?, ?, 'project_manager', 'project', 'active', ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                tenant_id,
                project_id,
                created_by,
                created_by,
                created_by,
                now,
                now,
                tenant_membership_id,
            ),
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
    tenant_membership_id: str | None = None

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
    tenant_membership_id: str | None = None,
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
            VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                membership_id,
                tenant_id,
                project_id,
                user_id,
                role,
                scope,
                actor_id,
                actor_id,
                now,
                now,
                tenant_membership_id,
            ),
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
            """
            INSERT INTO project_memberships (
                id, tenant_id, project_id, user_id, role, scope_policy, status,
                created_by, updated_by, created_at, updated_at
            )
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
        tenant_membership_id=row["tenant_membership_id"],
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


class PostgresConnection:
    """Small psycopg wrapper with the connection methods the stores already use."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def execute(self, sql: str, parameters=None):
        import psycopg

        translated = translate_placeholders(sql)
        try:
            if parameters is None:
                return self._connection.execute(translated)
            return self._connection.execute(translated, parameters)
        except psycopg.errors.IntegrityError as exc:
            constraint = ""
            if exc.diag is not None and exc.diag.constraint_name:
                constraint = exc.diag.constraint_name
            raise sqlite3.IntegrityError(constraint or "integrity constraint failed") from None

    def begin_immediate(self, lock_key: str | None = None) -> None:
        if self._connection.autocommit:
            self._connection.autocommit = False
        if lock_key:
            self.execute("SELECT pg_advisory_xact_lock(?)", (advisory_lock_key(lock_key),))

    def set_lock_wait(self, milliseconds: int) -> None:
        self.execute("SELECT set_config('lock_timeout', ?, false)", (f"{int(milliseconds)}ms",))

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    @property
    def isolation_level(self):
        if self._connection.autocommit:
            return None
        return ""

    @isolation_level.setter
    def isolation_level(self, value) -> None:
        autocommit = value is None
        if self._connection.autocommit == autocommit:
            return
        if autocommit and _postgres_transaction_open(self._connection):
            self._connection.commit()
        self._connection.autocommit = autocommit


def translate_placeholders(sql: str) -> str:
    """Replace SQLite qmark placeholders with psycopg placeholders, outside quotes."""

    parts: list[str] = []
    in_single = False
    index = 0
    length = len(sql)
    while index < length:
        character = sql[index]
        if in_single:
            parts.append(character)
            if character == "'":
                if index + 1 < length and sql[index + 1] == "'":
                    parts.append("'")
                    index += 2
                    continue
                in_single = False
            index += 1
            continue
        if character == "'":
            in_single = True
            parts.append(character)
            index += 1
            continue
        if character == "?":
            parts.append("%s")
            index += 1
            continue
        parts.append(character)
        index += 1
    return "".join(parts)


def split_sql(script: str) -> list[str]:
    """Split a migration script on semicolons that are outside quotes and dollar quotes."""

    statements: list[str] = []
    current: list[str] = []
    index = 0
    length = len(script)
    in_single = False
    dollar: str | None = None
    while index < length:
        if dollar is not None:
            if script.startswith(dollar, index):
                current.append(dollar)
                index += len(dollar)
                dollar = None
                continue
            current.append(script[index])
            index += 1
            continue
        if in_single:
            current.append(script[index])
            if script[index] == "'":
                if index + 1 < length and script[index + 1] == "'":
                    current.append("'")
                    index += 2
                    continue
                in_single = False
            index += 1
            continue
        if script[index] == "'":
            in_single = True
            current.append("'")
            index += 1
            continue
        if script[index] == "$":
            end = index + 1
            while end < length and (script[end].isalnum() or script[end] == "_"):
                end += 1
            if end < length and script[end] == "$":
                dollar = script[index : end + 1]
                current.append(dollar)
                index = end + 1
                continue
        if script[index] == "-" and index + 1 < length and script[index + 1] == "-":
            newline = script.find("\n", index)
            if newline == -1:
                break
            current.append("\n")
            index = newline + 1
            continue
        if script[index] == ";":
            text = "".join(current).strip()
            if text:
                statements.append(text)
            current = []
            index += 1
            continue
        current.append(script[index])
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def advisory_lock_key(name: str) -> int:
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


def _sslmode(host: str) -> str:
    configured = os.environ.get("CRM_DATABASE_SSLMODE", "").strip().lower()
    if not configured:
        configured = "verify-full"
    if configured == "disable":
        if host not in _LOOPBACK_HOSTS:
            raise RuntimeError(
                "CRM_DATABASE_SSLMODE=disable is only allowed for a loopback PostgreSQL host."
            )
        return "disable"
    if configured != "verify-full":
        raise RuntimeError(
            "CRM_DATABASE_SSLMODE must be verify-full, or disable for a loopback host."
        )
    return configured


def _postgres_transaction_open(connection) -> bool:
    from psycopg.pq import TransactionStatus

    return connection.info.transaction_status != TransactionStatus.IDLE
