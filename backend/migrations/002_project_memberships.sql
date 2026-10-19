CREATE TABLE IF NOT EXISTS project_memberships (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('project_manager', 'project_member')),
    scope_policy TEXT NOT NULL CHECK (scope_policy IN ('project', 'assigned')),
    status TEXT NOT NULL CHECK (status IN ('active', 'removed')),
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects (id),
    CHECK (
        (role = 'project_manager' AND scope_policy = 'project')
        OR (role = 'project_member' AND scope_policy = 'assigned')
    ),
    CHECK (length(trim(user_id)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_memberships_one_active_user
    ON project_memberships (project_id, user_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_project_memberships_tenant_user_status
    ON project_memberships (tenant_id, user_id, status);

CREATE INDEX IF NOT EXISTS ix_project_memberships_project
    ON project_memberships (tenant_id, project_id, status);
