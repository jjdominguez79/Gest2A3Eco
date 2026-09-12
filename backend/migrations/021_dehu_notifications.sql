-- Bandeja central DEHu alimentada por el worker AAPP.

CREATE TABLE IF NOT EXISTS client_dehu_notifications (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    request_id VARCHAR(36)
        REFERENCES client_certificate_requests(id) ON DELETE SET NULL,
    mailbox_id VARCHAR(100) NOT NULL DEFAULT '',
    external_reference VARCHAR(300) NOT NULL,
    subject VARCHAR(500) NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    action_type VARCHAR(120) NOT NULL DEFAULT '',
    holder_tax_id VARCHAR(30) NOT NULL DEFAULT '',
    holder_name VARCHAR(300) NOT NULL DEFAULT '',
    available_date VARCHAR(32) NOT NULL DEFAULT '',
    expiration_date VARCHAR(32) NOT NULL DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    source_endpoint VARCHAR(200) NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    document_id VARCHAR(36) REFERENCES client_documents(id) ON DELETE SET NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_dehu_notification_reference
        UNIQUE (organization_id, external_reference)
);

CREATE INDEX IF NOT EXISTS ix_client_dehu_notification_org
    ON client_dehu_notifications(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_dehu_notification_request
    ON client_dehu_notifications(request_id);
CREATE INDEX IF NOT EXISTS ix_client_dehu_notification_status
    ON client_dehu_notifications(status);
CREATE INDEX IF NOT EXISTS ix_client_dehu_notification_tax_id
    ON client_dehu_notifications(holder_tax_id);
CREATE INDEX IF NOT EXISTS ix_client_dehu_notification_document
    ON client_dehu_notifications(document_id);
CREATE INDEX IF NOT EXISTS ix_client_dehu_notification_last_seen
    ON client_dehu_notifications(last_seen_at);
