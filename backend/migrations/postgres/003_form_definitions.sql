CREATE TABLE IF NOT EXISTS form_definitions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status = 'draft'),
    created_by TEXT,
    updated_by TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects (id),
    CHECK (length(trim(name)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_form_definitions_project_lower_name
    ON form_definitions (project_id, lower(name));

CREATE INDEX IF NOT EXISTS ix_form_definitions_tenant_project
    ON form_definitions (tenant_id, project_id);

CREATE TABLE IF NOT EXISTS form_fields (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    form_id TEXT NOT NULL,
    field_key TEXT NOT NULL,
    label TEXT NOT NULL,
    field_type TEXT NOT NULL,
    required INTEGER NOT NULL CHECK (required IN (0, 1)),
    help_text TEXT NOT NULL DEFAULT '',
    section_name TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL CHECK (position >= 0),
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (form_id) REFERENCES form_definitions (id),
    CHECK (length(trim(field_key)) > 0),
    CHECK (length(trim(label)) > 0),
    CHECK (
        field_type IN (
            'text', 'long_text', 'number', 'mobile', 'email', 'url',
            'date', 'time', 'dropdown', 'multi_select', 'radio', 'checkbox',
            'currency', 'file', 'auto_number'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_form_fields_form_lower_key
    ON form_fields (form_id, lower(field_key));

CREATE UNIQUE INDEX IF NOT EXISTS uq_form_fields_form_position
    ON form_fields (form_id, position);

CREATE INDEX IF NOT EXISTS ix_form_fields_scope
    ON form_fields (tenant_id, project_id, form_id);
