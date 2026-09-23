-- Buzon DGT/DEV: programacion e historico incremental por cliente.

CREATE TABLE IF NOT EXISTS client_dev_mailbox_configs (
    organization_id VARCHAR(36) PRIMARY KEY
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    mailbox_id VARCHAR(100) NOT NULL DEFAULT '',
    mailbox_name VARCHAR(300) NOT NULL DEFAULT 'DGT / DEV',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    periodicity VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    daily_sync_time VARCHAR(5) NOT NULL DEFAULT '',
    notification_email VARCHAR(254) NOT NULL DEFAULT '',
    registration_status VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    registration_message TEXT NOT NULL DEFAULT '',
    activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    next_sync_at TIMESTAMPTZ,
    last_enqueued_at TIMESTAMPTZ,
    last_request_id VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_client_dev_mailbox_active
    ON client_dev_mailbox_configs(active);
CREATE INDEX IF NOT EXISTS ix_client_dev_mailbox_periodicity
    ON client_dev_mailbox_configs(periodicity);
CREATE INDEX IF NOT EXISTS ix_client_dev_mailbox_next_sync
    ON client_dev_mailbox_configs(next_sync_at);

CREATE TABLE IF NOT EXISTS client_dev_notifications (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    request_id VARCHAR(36)
        REFERENCES client_certificate_requests(id) ON DELETE SET NULL,
    mailbox_id VARCHAR(100) NOT NULL DEFAULT '',
    external_reference VARCHAR(300) NOT NULL,
    subject VARCHAR(500) NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    issuing_body VARCHAR(500) NOT NULL DEFAULT 'DGT',
    action_type VARCHAR(120) NOT NULL DEFAULT 'NOTIFICACION',
    holder_tax_id VARCHAR(30) NOT NULL DEFAULT '',
    holder_name VARCHAR(300) NOT NULL DEFAULT '',
    available_date VARCHAR(32) NOT NULL DEFAULT '',
    expiration_date VARCHAR(32) NOT NULL DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    source_endpoint VARCHAR(200) NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_dev_notification_reference
        UNIQUE (organization_id, external_reference)
);

CREATE INDEX IF NOT EXISTS ix_client_dev_notification_org
    ON client_dev_notifications(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_dev_notification_request
    ON client_dev_notifications(request_id);
CREATE INDEX IF NOT EXISTS ix_client_dev_notification_status
    ON client_dev_notifications(status);
CREATE INDEX IF NOT EXISTS ix_client_dev_notification_tax_id
    ON client_dev_notifications(holder_tax_id);
CREATE INDEX IF NOT EXISTS ix_client_dev_notification_last_seen
    ON client_dev_notifications(last_seen_at);
