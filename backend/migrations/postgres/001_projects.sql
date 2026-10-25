CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    created_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (length(trim(code)) > 0),
    CHECK (length(trim(name)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_tenant_lower_code
    ON projects (tenant_id, lower(code));

CREATE INDEX IF NOT EXISTS ix_projects_tenant_status
    ON projects (tenant_id, status);
