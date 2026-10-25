-- CRM reminder deliveries for follow-up assignment and due times.
-- This script adds one table and indexes. It does not drop a table or delete rows.
-- Record assignment reminders are not stored here. That workflow is not in this schema.

CREATE TABLE IF NOT EXISTS reminder_deliveries (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    follow_up_id TEXT NOT NULL,
    recipient_user_id TEXT NOT NULL,
    recipient_email TEXT,
    channel TEXT NOT NULL CHECK (channel IN ('in_app', 'email')),
    kind TEXT NOT NULL CHECK (kind IN ('follow_up_assigned', 'follow_up_due')),
    due_at TEXT NOT NULL,
    eligible_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (
        state IN ('pending', 'processing', 'sent', 'recorded', 'retryable', 'failed', 'suppressed')
    ),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    last_error TEXT,
    next_retry_at TEXT,
    read_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects (id),
    FOREIGN KEY (record_id) REFERENCES records (id),
    FOREIGN KEY (follow_up_id) REFERENCES follow_ups (id)
);

CREATE INDEX IF NOT EXISTS ix_reminder_inbox
    ON reminder_deliveries (tenant_id, recipient_user_id, channel, state, updated_at, id);

CREATE INDEX IF NOT EXISTS ix_reminder_delivery
    ON reminder_deliveries (tenant_id, state, eligible_at, next_retry_at, id);

CREATE INDEX IF NOT EXISTS ix_reminder_project
    ON reminder_deliveries (tenant_id, project_id, state, updated_at, id);
