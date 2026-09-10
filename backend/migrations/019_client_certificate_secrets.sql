-- Custodia central de certificados de cliente.
-- El blob contiene un sobre AES-256-GCM; PostgreSQL solo conserva metadatos.

CREATE TABLE IF NOT EXISTS client_certificate_secrets (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL UNIQUE
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    encrypted_blob_key VARCHAR(500) NOT NULL UNIQUE,
    pfx_sha256 VARCHAR(64) NOT NULL,
    file_name VARCHAR(255) NOT NULL DEFAULT 'certificado.pfx',
    common_name VARCHAR(300) NOT NULL DEFAULT '',
    tax_id VARCHAR(30) NOT NULL DEFAULT '',
    issuer VARCHAR(300) NOT NULL DEFAULT '',
    serial_number VARCHAR(100) NOT NULL DEFAULT '',
    valid_from TIMESTAMPTZ,
    valid_until TIMESTAMPTZ,
    version INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    uploaded_by VARCHAR(100) NOT NULL DEFAULT 'desktop',
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_client_cert_secret_valid_until
    ON client_certificate_secrets(valid_until);
CREATE INDEX IF NOT EXISTS ix_client_cert_secret_active
    ON client_certificate_secrets(active);
