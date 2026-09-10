-- Cola central para solicitudes de certificados AEAT/TGSS.

ALTER TABLE msg_organizations
    ADD COLUMN IF NOT EXISTS client_certificates_enabled BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS client_certificate_requests (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    requester_type VARCHAR(16) NOT NULL,
    requester_id VARCHAR(64) NOT NULL DEFAULT '',
    certificate_type VARCHAR(50) NOT NULL,
    parameters_json TEXT NOT NULL DEFAULT '{}',
    idempotency_key VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ,
    claimed_at TIMESTAMPTZ,
    claim_token VARCHAR(64) NOT NULL DEFAULT '',
    error_code VARCHAR(60) NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    result_summary TEXT NOT NULL DEFAULT '',
    document_id VARCHAR(36) REFERENCES client_documents(id) ON DELETE SET NULL,
    completed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_cert_request_idempotency
        UNIQUE (organization_id, idempotency_key),
    CONSTRAINT ck_client_cert_requester_type
        CHECK (requester_type IN ('client', 'desktop', 'staff')),
    CONSTRAINT ck_client_cert_request_status
        CHECK (status IN ('queued', 'processing', 'completed', 'needs_action', 'failed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS ix_client_cert_request_org
    ON client_certificate_requests(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_cert_request_status
    ON client_certificate_requests(status);
CREATE INDEX IF NOT EXISTS ix_client_cert_request_type
    ON client_certificate_requests(certificate_type);
CREATE INDEX IF NOT EXISTS ix_client_cert_request_next_attempt
    ON client_certificate_requests(next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_client_cert_request_document
    ON client_certificate_requests(document_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_client_cert_request_active_type
    ON client_certificate_requests(organization_id, certificate_type)
    WHERE status IN ('queued', 'processing', 'needs_action');
