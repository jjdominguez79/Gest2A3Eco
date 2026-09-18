-- Resguardo y certificado definitivo son documentos diferentes.
ALTER TABLE client_certificate_requests
    ADD COLUMN IF NOT EXISTS external_reference VARCHAR(60) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS certificate_result VARCHAR(16) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS receipt_document_id VARCHAR(36)
        REFERENCES client_documents(id) ON DELETE SET NULL;

ALTER TABLE client_certificate_requests
    DROP CONSTRAINT IF EXISTS ck_client_cert_request_status;
ALTER TABLE client_certificate_requests
    ADD CONSTRAINT ck_client_cert_request_status CHECK (
        status IN ('queued', 'processing', 'completed', 'needs_action',
                   'failed', 'cancelled', 'awaiting_issuance')
    );

DROP INDEX IF EXISTS uq_client_cert_request_active_type;
CREATE UNIQUE INDEX uq_client_cert_request_active_type
    ON client_certificate_requests(organization_id, certificate_type)
    WHERE status IN ('queued', 'processing', 'needs_action', 'awaiting_issuance');
