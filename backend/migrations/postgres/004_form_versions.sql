-- Published form versions are immutable snapshots. The working draft stays in
-- form_definitions and form_fields. A later record table can store
-- form_version_id referencing form_versions.id. This sprint does not create
-- that record table.

CREATE TABLE IF NOT EXISTS form_versions (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    form_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK (version_number >= 1),
    schema_json TEXT NOT NULL CHECK (length(schema_json) > 2),
    published_by TEXT NOT NULL CHECK (length(trim(published_by)) > 0),
    published_at TEXT NOT NULL,
    FOREIGN KEY (form_id) REFERENCES form_definitions (id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_form_versions_form_number
    ON form_versions (form_id, version_number);

CREATE INDEX IF NOT EXISTS ix_form_versions_scope
    ON form_versions (tenant_id, project_id, form_id);

ALTER TABLE form_definitions ADD COLUMN current_published_version_id TEXT
    REFERENCES form_versions (id);

CREATE OR REPLACE FUNCTION crm_form_versions_immutable()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'published form version is immutable';
END;
$$;

DROP TRIGGER IF EXISTS form_versions_immutable_update ON form_versions;
CREATE TRIGGER form_versions_immutable_update
BEFORE UPDATE ON form_versions
FOR EACH ROW
EXECUTE FUNCTION crm_form_versions_immutable();

DROP TRIGGER IF EXISTS form_versions_immutable_delete ON form_versions;
CREATE TRIGGER form_versions_immutable_delete
BEFORE DELETE ON form_versions
FOR EACH ROW
EXECUTE FUNCTION crm_form_versions_immutable();
