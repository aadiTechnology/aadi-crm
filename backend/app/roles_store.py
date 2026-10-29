"""Tenant-defined CRM roles. These rows are not Control Plane roles or project roles."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.db import MissingTenantMembership

_ROLE_COLUMNS = (
    "id, tenant_id, name, description, status, created_by, updated_by, "
    "created_at, updated_at, tenant_membership_id"
)


class DuplicateTenantRoleName(Exception):
    """This tenant already has a role with this name."""


class InactiveTenantRole(Exception):
    """A deactivated role cannot receive new permissions."""


@dataclass(frozen=True)
class TenantRole:
    id: str
    tenant_id: str
    name: str
    description: str
    status: str
    created_at: str
    updated_at: str
    permissions: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "permissions": list(self.permissions),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def list_tenant_roles(connection: sqlite3.Connection, tenant_id: str) -> list[TenantRole]:
    rows = connection.execute(
        f"""
        SELECT {_ROLE_COLUMNS}
        FROM tenant_roles
        WHERE tenant_id = ?
        ORDER BY lower(name), id
        """,
        (tenant_id,),
    ).fetchall()
    granted = _permissions_by_role(connection, tenant_id, [row["id"] for row in rows])
    return [_role(row, granted.get(row["id"], ())) for row in rows]


def get_tenant_role(
    connection: sqlite3.Connection,
    tenant_id: str,
    role_id: str,
) -> TenantRole | None:
    row = connection.execute(
        f"""
        SELECT {_ROLE_COLUMNS}
        FROM tenant_roles
        WHERE tenant_id = ? AND id = ?
        """,
        (tenant_id, role_id),
    ).fetchone()
    if row is None:
        return None
    granted = _permissions_by_role(connection, tenant_id, [role_id])
    return _role(row, granted.get(role_id, ()))


def create_tenant_role(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    name: str,
    description: str,
    actor_id: str,
    tenant_membership_id: str,
) -> TenantRole:
    _require_membership(tenant_membership_id)
    if _name_taken(connection, tenant_id, name, exclude_id=None):
        raise DuplicateTenantRoleName
    role_id = str(uuid4())
    now = _now()
    try:
        connection.execute(
            f"""
            INSERT INTO tenant_roles ({_ROLE_COLUMNS})
            VALUES (?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
            """,
            (
                role_id,
                tenant_id,
                name,
                description,
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
        raise DuplicateTenantRoleName from None
    created = get_tenant_role(connection, tenant_id, role_id)
    if created is None:
        raise RuntimeError("The role was not stored.")
    return created


def update_tenant_role(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    role_id: str,
    name: str | None,
    description: str | None,
    actor_id: str,
) -> TenantRole | None:
    current = get_tenant_role(connection, tenant_id, role_id)
    if current is None:
        return None
    next_name = current.name if name is None else name
    next_description = current.description if description is None else description
    if _name_taken(connection, tenant_id, next_name, exclude_id=role_id):
        raise DuplicateTenantRoleName
    try:
        connection.execute(
            """
            UPDATE tenant_roles
            SET name = ?, description = ?, updated_by = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ?
            """,
            (next_name, next_description, actor_id, _now(), tenant_id, role_id),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        raise DuplicateTenantRoleName from None
    return get_tenant_role(connection, tenant_id, role_id)


def deactivate_tenant_role(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    role_id: str,
    actor_id: str,
) -> TenantRole | None:
    """Mark the role inactive. The row and its permission grants stay in place."""

    current = get_tenant_role(connection, tenant_id, role_id)
    if current is None:
        return None
    if current.status == "active":
        connection.execute(
            """
            UPDATE tenant_roles
            SET status = 'inactive', updated_by = ?, updated_at = ?
            WHERE tenant_id = ? AND id = ? AND status = 'active'
            """,
            (actor_id, _now(), tenant_id, role_id),
        )
        connection.commit()
    return get_tenant_role(connection, tenant_id, role_id)


def grant_tenant_role_permission(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    role_id: str,
    permission_key: str,
    actor_id: str,
    tenant_membership_id: str,
) -> TenantRole | None:
    _require_membership(tenant_membership_id)
    current = get_tenant_role(connection, tenant_id, role_id)
    if current is None:
        return None
    if current.status != "active":
        raise InactiveTenantRole
    if permission_key in current.permissions:
        return current
    try:
        connection.execute(
            """
            INSERT INTO tenant_role_permissions (
                id, tenant_id, role_id, permission_key, created_by, created_at, tenant_membership_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                tenant_id,
                role_id,
                permission_key,
                actor_id,
                _now(),
                tenant_membership_id,
            ),
        )
        connection.commit()
    except sqlite3.IntegrityError:
        connection.rollback()
        stored = get_tenant_role(connection, tenant_id, role_id)
        if stored is None or permission_key not in stored.permissions:
            raise
        return stored
    granted = get_tenant_role(connection, tenant_id, role_id)
    if granted is None:
        raise RuntimeError("The role permission was not stored.")
    return granted


def revoke_tenant_role_permission(
    connection: sqlite3.Connection,
    *,
    tenant_id: str,
    role_id: str,
    permission_key: str,
) -> TenantRole | None:
    """Remove one grant. A missing role returns None. The role row stays."""

    current = get_tenant_role(connection, tenant_id, role_id)
    if current is None:
        return None
    if permission_key not in current.permissions:
        return current
    connection.execute(
        """
        DELETE FROM tenant_role_permissions
        WHERE tenant_id = ? AND role_id = ? AND permission_key = ?
        """,
        (tenant_id, role_id, permission_key),
    )
    connection.commit()
    return get_tenant_role(connection, tenant_id, role_id)


def permission_granted(
    connection: sqlite3.Connection,
    tenant_id: str,
    role_id: str,
    permission_key: str,
) -> bool:
    row = connection.execute(
        """
        SELECT id
        FROM tenant_role_permissions
        WHERE tenant_id = ? AND role_id = ? AND permission_key = ?
        """,
        (tenant_id, role_id, permission_key),
    ).fetchone()
    return row is not None


def _name_taken(
    connection: sqlite3.Connection,
    tenant_id: str,
    name: str,
    *,
    exclude_id: str | None,
) -> bool:
    row = connection.execute(
        """
        SELECT id
        FROM tenant_roles
        WHERE tenant_id = ? AND lower(name) = lower(?)
        """,
        (tenant_id, name),
    ).fetchone()
    if row is None:
        return False
    return exclude_id is None or row["id"] != exclude_id


def _permissions_by_role(
    connection: sqlite3.Connection,
    tenant_id: str,
    role_ids: list[str],
) -> dict[str, tuple[str, ...]]:
    if not role_ids:
        return {}
    placeholders = ", ".join("?" for _ in role_ids)
    rows = connection.execute(
        f"""
        SELECT role_id, permission_key
        FROM tenant_role_permissions
        WHERE tenant_id = ? AND role_id IN ({placeholders})
        ORDER BY permission_key
        """,
        (tenant_id, *role_ids),
    ).fetchall()
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row["role_id"], []).append(row["permission_key"])
    return {role_id: tuple(keys) for role_id, keys in grouped.items()}


def _role(row: sqlite3.Row, permissions: tuple[str, ...]) -> TenantRole:
    return TenantRole(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        description=row["description"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        permissions=permissions,
    )


def _require_membership(tenant_membership_id: str) -> None:
    if not str(tenant_membership_id).strip():
        raise MissingTenantMembership


def _now() -> str:
    return datetime.now(UTC).isoformat()
