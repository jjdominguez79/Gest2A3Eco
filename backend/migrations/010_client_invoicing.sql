-- 010_client_invoicing.sql
-- Tablas para facturacion online del cliente.
-- Idempotente: CREATE TABLE IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS client_invoice_series (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    fiscal_year INTEGER NOT NULL,
    series_code VARCHAR(10) NOT NULL DEFAULT 'WEB',
    next_number INTEGER NOT NULL DEFAULT 1,
    description VARCHAR(200) NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_inv_series
        UNIQUE (organization_id, fiscal_year, series_code)
);

CREATE INDEX IF NOT EXISTS ix_client_inv_series_org
    ON client_invoice_series(organization_id);

CREATE TABLE IF NOT EXISTS client_invoice_customers (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    tax_id VARCHAR(20) NOT NULL,
    tax_id_normalized VARCHAR(20) NOT NULL,
    legal_name VARCHAR(200) NOT NULL,
    address VARCHAR(300) NOT NULL DEFAULT '',
    postal_code VARCHAR(10) NOT NULL DEFAULT '',
    city VARCHAR(100) NOT NULL DEFAULT '',
    province VARCHAR(100) NOT NULL DEFAULT '',
    country VARCHAR(60) NOT NULL DEFAULT 'ES',
    email VARCHAR(254) NOT NULL DEFAULT '',
    phone VARCHAR(30) NOT NULL DEFAULT '',
    default_vat_rate NUMERIC(5,2) NOT NULL DEFAULT 21.00,
    desktop_tercero_id INTEGER,
    desktop_subcuenta VARCHAR(20) NOT NULL DEFAULT '',
    pending_desktop_import BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_inv_customer_nif
        UNIQUE (organization_id, tax_id_normalized)
);

CREATE INDEX IF NOT EXISTS ix_client_inv_customers_org
    ON client_invoice_customers(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_inv_customers_nif
    ON client_invoice_customers(tax_id_normalized);

CREATE TABLE IF NOT EXISTS client_invoices (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    customer_id VARCHAR(36) NOT NULL REFERENCES client_invoice_customers(id) ON DELETE RESTRICT,
    fiscal_year INTEGER NOT NULL,
    series_code VARCHAR(10) NOT NULL DEFAULT 'WEB',
    invoice_number INTEGER,
    invoice_date TIMESTAMPTZ,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    subtotal NUMERIC(15,2) NOT NULL DEFAULT 0,
    total_vat NUMERIC(15,2) NOT NULL DEFAULT 0,
    withholding_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
    withholding_amount NUMERIC(15,2) NOT NULL DEFAULT 0,
    total NUMERIC(15,2) NOT NULL DEFAULT 0,
    currency VARCHAR(3) NOT NULL DEFAULT 'EUR',
    payment_method VARCHAR(100) NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    recipient_email VARCHAR(254) NOT NULL DEFAULT '',
    issued_snapshot TEXT NOT NULL DEFAULT '',
    idempotency_key VARCHAR(80) NOT NULL DEFAULT '',
    created_by_client_id VARCHAR(36) REFERENCES msg_clients(id) ON DELETE SET NULL DEFAULT '',
    document_id VARCHAR(36),
    verifactu_hash VARCHAR(64) NOT NULL DEFAULT '',
    verifactu_chain_hash VARCHAR(64) NOT NULL DEFAULT '',
    verifactu_qr_data TEXT NOT NULL DEFAULT '',
    verifactu_registration_id VARCHAR(100) NOT NULL DEFAULT '',
    software_id VARCHAR(100) NOT NULL DEFAULT 'Gest2A3Eco',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    issued_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_invoice_number
        UNIQUE (organization_id, fiscal_year, series_code, invoice_number)
);

CREATE INDEX IF NOT EXISTS ix_client_invoices_org
    ON client_invoices(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_invoices_status
    ON client_invoices(status);
CREATE INDEX IF NOT EXISTS ix_client_invoices_fiscal_year
    ON client_invoices(fiscal_year);
CREATE INDEX IF NOT EXISTS ix_client_invoices_idempotency
    ON client_invoices(idempotency_key);

CREATE TABLE IF NOT EXISTS client_invoice_lines (
    id VARCHAR(36) PRIMARY KEY,
    invoice_id VARCHAR(36) NOT NULL REFERENCES client_invoices(id) ON DELETE CASCADE,
    line_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    quantity NUMERIC(15,4) NOT NULL DEFAULT 1,
    unit_price NUMERIC(15,4) NOT NULL DEFAULT 0,
    discount_percent NUMERIC(5,2) NOT NULL DEFAULT 0,
    vat_rate NUMERIC(5,2) NOT NULL DEFAULT 21.00,
    line_total NUMERIC(15,2) NOT NULL DEFAULT 0,
    vat_amount NUMERIC(15,2) NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_client_invoice_lines_inv
    ON client_invoice_lines(invoice_id);

CREATE TABLE IF NOT EXISTS client_invoice_events (
    id SERIAL PRIMARY KEY,
    invoice_id VARCHAR(36) NOT NULL REFERENCES client_invoices(id) ON DELETE CASCADE,
    event_type VARCHAR(40) NOT NULL,
    status_before VARCHAR(30) NOT NULL DEFAULT '',
    status_after VARCHAR(30) NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    actor_type VARCHAR(16) NOT NULL DEFAULT '',
    actor_id VARCHAR(64) NOT NULL DEFAULT '',
    event_hash VARCHAR(64) NOT NULL DEFAULT '',
    chain_hash VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_client_inv_events_inv
    ON client_invoice_events(invoice_id);
CREATE INDEX IF NOT EXISTS ix_client_inv_events_type
    ON client_invoice_events(event_type);
CREATE INDEX IF NOT EXISTS ix_client_inv_events_created
    ON client_invoice_events(created_at);

CREATE TABLE IF NOT EXISTS client_invoice_processing_queue (
    id VARCHAR(36) PRIMARY KEY,
    invoice_id VARCHAR(36) NOT NULL REFERENCES client_invoices(id) ON DELETE CASCADE,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    queue_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    error_message TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 5,
    claimed_by VARCHAR(120) NOT NULL DEFAULT '',
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    pdf_blob_key VARCHAR(500) NOT NULL DEFAULT '',
    pdf_sha256 VARCHAR(64) NOT NULL DEFAULT '',
    pdf_file_size INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_inv_queue_invoice UNIQUE (invoice_id)
);

ALTER TABLE client_invoice_processing_queue
    ADD COLUMN IF NOT EXISTS pdf_file_size INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS ix_client_inv_queue_status
    ON client_invoice_processing_queue(queue_status);
CREATE INDEX IF NOT EXISTS ix_client_inv_queue_org
    ON client_invoice_processing_queue(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_inv_queue_lease
    ON client_invoice_processing_queue(lease_expires_at);
