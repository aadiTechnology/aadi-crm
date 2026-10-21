-- Import jobs and row results for CSV/XLSX import.
-- This script adds tables and indexes. It does not drop a table or delete rows.
-- Source cells stay on the import row. Unmapped values are not copied into records.

CREATE TABLE IF NOT EXISTS import_jobs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    form_id TEXT NOT NULL,
    form_version_id TEXT NOT NULL,
    actor_user_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    filename TEXT NOT NULL,
    content_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'uploaded', 'mapped', 'previewed', 'committing',
            'completed', 'partial', 'failed'
        )
    ),
    mapping_json TEXT,
    summary_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (project_id) REFERENCES projects (id),
    FOREIGN KEY (form_id) REFERENCES form_definitions (id),
    FOREIGN KEY (form_version_id) REFERENCES form_versions (id)
);

CREATE TABLE IF NOT EXISTS import_rows (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    source_json TEXT NOT NULL,
    parse_errors_json TEXT NOT NULL,
    decision TEXT CHECK (decision IS NULL OR decision IN ('accept_new', 'skip', 'reject')),
    outcome TEXT NOT NULL CHECK (
        outcome IN ('stored', 'working', 'accepted', 'rejected', 'skipped', 'awaiting_review')
    ),
    errors_json TEXT NOT NULL,
    candidates_json TEXT NOT NULL,
    values_json TEXT,
    record_id TEXT,
    UNIQUE (job_id, row_number),
    FOREIGN KEY (job_id) REFERENCES import_jobs (id),
    FOREIGN KEY (project_id) REFERENCES projects (id)
);

CREATE INDEX IF NOT EXISTS ix_import_jobs_project
    ON import_jobs (tenant_id, project_id, updated_at, id);

CREATE INDEX IF NOT EXISTS ix_import_rows_job
    ON import_rows (tenant_id, project_id, job_id, row_number);
