-- 009_client_documents.sql
-- Tablas para el area documental del cliente y cola de publicacion.
-- Idempotente: CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS client_documents (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    document_type VARCHAR(40) NOT NULL,
    source_system VARCHAR(30) NOT NULL,
    source_id VARCHAR(120) NOT NULL,
    source_version INTEGER NOT NULL DEFAULT 1,
    display_name VARCHAR(300) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    document_date TIMESTAMPTZ,
    fiscal_year INTEGER NOT NULL DEFAULT 0,
    amount NUMERIC(15,2),
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(120) NOT NULL DEFAULT 'application/pdf',
    file_size INTEGER NOT NULL DEFAULT 0,
    sha256 VARCHAR(64) NOT NULL,
    blob_key VARCHAR(500) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL DEFAULT 'published',
    replaced_by_id VARCHAR(36) REFERENCES client_documents(id) ON DELETE SET NULL,
    withdrawal_reason TEXT NOT NULL DEFAULT '',
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    withdrawn_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_documents_source
        UNIQUE (organization_id, source_system, source_id, source_version)
);

CREATE INDEX IF NOT EXISTS ix_client_documents_org
    ON client_documents(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_documents_type
    ON client_documents(document_type);
CREATE INDEX IF NOT EXISTS ix_client_documents_source_system
    ON client_documents(source_system);
CREATE INDEX IF NOT EXISTS ix_client_documents_source_id
    ON client_documents(source_id);
CREATE INDEX IF NOT EXISTS ix_client_documents_fiscal_year
    ON client_documents(fiscal_year);
CREATE INDEX IF NOT EXISTS ix_client_documents_status
    ON client_documents(status);

CREATE TABLE IF NOT EXISTS client_document_reads (
    id VARCHAR(36) PRIMARY KEY,
    document_id VARCHAR(36) NOT NULL REFERENCES client_documents(id) ON DELETE CASCADE,
    client_id VARCHAR(36) NOT NULL REFERENCES msg_clients(id) ON DELETE CASCADE,
    read_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_doc_read UNIQUE (document_id, client_id)
);

CREATE INDEX IF NOT EXISTS ix_client_document_reads_doc
    ON client_document_reads(document_id);
CREATE INDEX IF NOT EXISTS ix_client_document_reads_client
    ON client_document_reads(client_id);

CREATE TABLE IF NOT EXISTS desktop_publication_queue (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    source_type VARCHAR(30) NOT NULL,
    source_id VARCHAR(120) NOT NULL,
    source_version INTEGER NOT NULL DEFAULT 1,
    local_pdf_path VARCHAR(500) NOT NULL,
    display_name VARCHAR(300) NOT NULL,
    document_date TIMESTAMPTZ,
    fiscal_year INTEGER NOT NULL DEFAULT 0,
    amount NUMERIC(15,2),
    customer_tax_id VARCHAR(20) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message TEXT NOT NULL DEFAULT '',
    blocked_reason TEXT NOT NULL DEFAULT '',
    document_id VARCHAR(36) REFERENCES client_documents(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_desktop_pub_queue_org
    ON desktop_publication_queue(organization_id);
CREATE INDEX IF NOT EXISTS ix_desktop_pub_queue_status
    ON desktop_publication_queue(status);
