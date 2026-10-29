-- Tenant-defined CRM roles and the CRM permissions granted to them.
-- This script adds tables and indexes. It does not remove existing rows.

CREATE TABLE IF NOT EXISTS tenant_roles (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    tenant_membership_id TEXT NOT NULL,
    CHECK (length(trim(name)) > 0),
    CHECK (length(trim(tenant_membership_id)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_roles_tenant_lower_name
    ON tenant_roles (tenant_id, lower(name));

CREATE INDEX IF NOT EXISTS ix_tenant_roles_tenant_status
    ON tenant_roles (tenant_id, status);

CREATE TABLE IF NOT EXISTS tenant_role_permissions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    permission_key TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT NOT NULL,
    tenant_membership_id TEXT NOT NULL,
    FOREIGN KEY (role_id) REFERENCES tenant_roles (id),
    CHECK (length(trim(permission_key)) > 0),
    CHECK (length(trim(tenant_membership_id)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_role_permissions_role_key
    ON tenant_role_permissions (role_id, permission_key);

CREATE INDEX IF NOT EXISTS ix_tenant_role_permissions_tenant_role
    ON tenant_role_permissions (tenant_id, role_id);
