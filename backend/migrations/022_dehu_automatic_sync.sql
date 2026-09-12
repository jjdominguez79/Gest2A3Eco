-- Programacion central y lotes de resumen para consultas automaticas DEHu.

CREATE TABLE IF NOT EXISTS client_dehu_sync_batches (
    id VARCHAR(36) PRIMARY KEY,
    notification_email VARCHAR(254) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    total_mailboxes INTEGER NOT NULL DEFAULT 0,
    email_error TEXT NOT NULL DEFAULT '',
    completed_at TIMESTAMPTZ,
    email_sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_client_dehu_sync_batch_status
    ON client_dehu_sync_batches(status);
CREATE INDEX IF NOT EXISTS ix_client_dehu_sync_batch_created
    ON client_dehu_sync_batches(created_at);

CREATE TABLE IF NOT EXISTS client_dehu_mailbox_configs (
    organization_id VARCHAR(36) PRIMARY KEY
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    mailbox_id VARCHAR(100) NOT NULL DEFAULT '',
    mailbox_name VARCHAR(300) NOT NULL DEFAULT 'DEHu',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    periodicity VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    notification_email VARCHAR(254) NOT NULL DEFAULT '',
    next_sync_at TIMESTAMPTZ,
    last_enqueued_at TIMESTAMPTZ,
    last_request_id VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_client_dehu_mailbox_active
    ON client_dehu_mailbox_configs(active);
CREATE INDEX IF NOT EXISTS ix_client_dehu_mailbox_periodicity
    ON client_dehu_mailbox_configs(periodicity);
CREATE INDEX IF NOT EXISTS ix_client_dehu_mailbox_next_sync
    ON client_dehu_mailbox_configs(next_sync_at);

ALTER TABLE client_certificate_requests
    ADD COLUMN IF NOT EXISTS dehu_batch_id VARCHAR(36)
        REFERENCES client_dehu_sync_batches(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS ix_client_cert_request_dehu_batch
    ON client_certificate_requests(dehu_batch_id);

ALTER TABLE client_dehu_notifications
    ADD COLUMN IF NOT EXISTS issuing_body VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE client_dehu_notifications
    ADD COLUMN IF NOT EXISTS issuing_body_source VARCHAR(500) NOT NULL DEFAULT '';
