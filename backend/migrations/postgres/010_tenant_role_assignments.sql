-- Assigns tenant-defined CRM roles to Control Plane users.
-- The user id and tenant membership id are references, not local identities.
-- This script adds a table and indexes. It does not remove existing rows.

CREATE TABLE IF NOT EXISTS tenant_role_assignments (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked')),
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    tenant_membership_id TEXT NOT NULL,
    FOREIGN KEY (role_id) REFERENCES tenant_roles (id),
    CHECK (length(trim(user_id)) > 0),
    CHECK (length(trim(tenant_membership_id)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_role_assignments_one_active_role
    ON tenant_role_assignments (tenant_id, user_id, role_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_tenant_role_assignments_tenant_user
    ON tenant_role_assignments (tenant_id, user_id, status);
