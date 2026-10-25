-- CRM records store the published form version used at creation.
-- Values stay on that version when a newer draft or version is published.
-- Soft delete sets deleted_at. This script does not drop a table or delete rows.

CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    form_id TEXT NOT NULL,
    form_version_id TEXT NOT NULL,
    public_number TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    display_name TEXT NOT NULL,
    search_text TEXT NOT NULL,
    source TEXT NOT NULL,
    assignee_user_id TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    deleted_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id),
    FOREIGN KEY (form_id) REFERENCES form_definitions (id),
    FOREIGN KEY (form_version_id) REFERENCES form_versions (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_records_project_number
    ON records (project_id, public_number);

CREATE UNIQUE INDEX IF NOT EXISTS uq_records_project_sequence
    ON records (project_id, sequence);

CREATE INDEX IF NOT EXISTS ix_records_scope
    ON records (tenant_id, project_id, deleted_at, created_at);

CREATE INDEX IF NOT EXISTS ix_records_assignee
    ON records (tenant_id, project_id, assignee_user_id, deleted_at);

CREATE TABLE IF NOT EXISTS record_values (
    id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    value_json TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_record_values_key
    ON record_values (record_id, field_key);

CREATE INDEX IF NOT EXISTS ix_record_values_scope
    ON record_values (tenant_id, project_id, field_key);
