-- Follow-ups and the record activity timeline.
-- This script adds tables and indexes. It does not drop a table or delete rows.
-- There is no fixed follow-up count.

CREATE TABLE IF NOT EXISTS follow_ups (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    task_type TEXT NOT NULL CHECK (task_type IN ('call', 'whatsapp', 'email', 'meeting', 'note')),
    owner_user_id TEXT NOT NULL,
    due_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'completed', 'cancelled')),
    call_status TEXT CHECK (
        call_status IS NULL
        OR call_status IN ('connected', 'busy', 'not_connected', 'switched_off', 'not_valid')
    ),
    summary TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_by TEXT NOT NULL,
    updated_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    cancelled_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects (id),
    FOREIGN KEY (record_id) REFERENCES records (id)
);

CREATE INDEX IF NOT EXISTS ix_follow_ups_record
    ON follow_ups (tenant_id, project_id, record_id, created_at, id);

CREATE INDEX IF NOT EXISTS ix_follow_ups_queue
    ON follow_ups (tenant_id, project_id, status, due_at, id);

CREATE INDEX IF NOT EXISTS ix_follow_ups_owner
    ON follow_ups (tenant_id, project_id, owner_user_id, status, due_at, id);

CREATE TABLE IF NOT EXISTS record_activities (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    follow_up_id TEXT,
    actor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES records (id),
    FOREIGN KEY (follow_up_id) REFERENCES follow_ups (id)
);

CREATE INDEX IF NOT EXISTS ix_record_activities_timeline
    ON record_activities (tenant_id, project_id, record_id, occurred_at, id);
