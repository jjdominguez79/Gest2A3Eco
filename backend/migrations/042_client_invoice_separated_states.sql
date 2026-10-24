-- 042_client_invoice_separated_states.sql
-- Etapa 2 de la facturacion autonoma de clientes (ver docs/adr/0001).
--
-- Separa en columnas independientes lo que hoy mezcla la columna
-- ``client_invoices.status``: emision, estado fiscal, PDF, entrega y
-- contabilidad. ``status`` se conserva sin cambios por compatibilidad con
-- clientes ya desplegados.
--
-- Anade tambien ``source_system`` (preparacion para el listado combinado
-- client_app/desktop de la Etapa 10) y dos colas/outbox nuevas:
--   - client_invoice_accounting_queue: trabajo contable independiente
--     (consumido por invoice_worker desde la Etapa 3), desacoplado del
--     pipeline fiscal/PDF/email (ClientInvoiceProcessingQueue, consumido
--     por billing_worker).
--   - client_invoice_discrepancies: discrepancias de datos fiscales entre
--     el backend y el escritorio, para revision manual sin bloquear ni
--     sobrescribir facturas ya emitidas.
--
-- Idempotente: ADD COLUMN/CREATE TABLE con IF NOT EXISTS; restricciones via
-- bloques DO que comprueban pg_constraint antes de anadirlas (Postgres no
-- admite ADD CONSTRAINT IF NOT EXISTS).

ALTER TABLE client_invoices
    ADD COLUMN IF NOT EXISTS invoice_status VARCHAR(20) NOT NULL DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS fiscal_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS pdf_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS accounting_sync_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS source_system VARCHAR(20) NOT NULL DEFAULT 'client_app';

-- Retrocalcula los 5 estados separados a partir de la columna legacy
-- ``status`` para las filas existentes (facturas ya emitidas en fase piloto
-- interna/pruebas). Operacion idempotente: siempre recalcula desde ``status``.
UPDATE client_invoices SET
    invoice_status = CASE
        WHEN status = 'draft' THEN 'draft'
        WHEN status = 'cancelled' THEN 'cancelled'
        WHEN status = 'replaced' THEN 'rectified'
        ELSE 'issued'
    END,
    pdf_status = CASE
        WHEN status IN ('rendered', 'emailed') THEN 'generated'
        WHEN status = 'processing_error' THEN 'error'
        ELSE 'pending'
    END,
    delivery_status = CASE
        WHEN status = 'emailed' THEN 'sent'
        WHEN status = 'processing_error' THEN 'error'
        ELSE 'pending'
    END,
    accounting_sync_status = CASE
        WHEN status IN ('imported', 'rendered', 'emailed') THEN 'imported'
        ELSE 'pending'
    END,
    fiscal_status = 'pending';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_inv_invoice_status') THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT ck_client_inv_invoice_status
            CHECK (invoice_status IN ('draft', 'issued', 'cancelled', 'rectified'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_inv_fiscal_status') THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT ck_client_inv_fiscal_status
            CHECK (fiscal_status IN ('pending', 'processing', 'sent', 'accepted', 'rejected', 'incident'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_inv_pdf_status') THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT ck_client_inv_pdf_status
            CHECK (pdf_status IN ('pending', 'processing', 'generated', 'error'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_inv_delivery_status') THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT ck_client_inv_delivery_status
            CHECK (delivery_status IN ('pending', 'sending', 'sent', 'skipped', 'error', 'uncertain'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_inv_accounting_sync_status') THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT ck_client_inv_accounting_sync_status
            CHECK (accounting_sync_status IN ('pending', 'processing', 'imported', 'review_required', 'error'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_inv_source_system') THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT ck_client_inv_source_system
            CHECK (source_system IN ('client_app', 'desktop'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_client_invoices_invoice_status ON client_invoices(invoice_status);
CREATE INDEX IF NOT EXISTS ix_client_invoices_fiscal_status ON client_invoices(fiscal_status);
CREATE INDEX IF NOT EXISTS ix_client_invoices_pdf_status ON client_invoices(pdf_status);
CREATE INDEX IF NOT EXISTS ix_client_invoices_delivery_status ON client_invoices(delivery_status);
CREATE INDEX IF NOT EXISTS ix_client_invoices_accounting_sync_status ON client_invoices(accounting_sync_status);
CREATE INDEX IF NOT EXISTS ix_client_invoices_source_system ON client_invoices(source_system);

-- Outbox contable independiente (Etapa 3): invoice_worker reclama aqui,
-- nunca en client_invoice_processing_queue (reservada a billing_worker).
CREATE TABLE IF NOT EXISTS client_invoice_accounting_queue (
    id VARCHAR(36) PRIMARY KEY,
    invoice_id VARCHAR(36) NOT NULL REFERENCES client_invoices(id) ON DELETE CASCADE,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    -- pending | claimed | imported | review_required | completed | error
    queue_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    error_message TEXT NOT NULL DEFAULT '',
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 5,
    claimed_by VARCHAR(120) NOT NULL DEFAULT '',
    claimed_at TIMESTAMPTZ,
    lease_expires_at TIMESTAMPTZ,
    desktop_tercero_id VARCHAR(64) NOT NULL DEFAULT '',
    desktop_subcuenta VARCHAR(20) NOT NULL DEFAULT '',
    desktop_invoice_ref VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_client_inv_acc_queue_invoice UNIQUE (invoice_id)
);

CREATE INDEX IF NOT EXISTS ix_client_inv_acc_queue_status ON client_invoice_accounting_queue(queue_status);
CREATE INDEX IF NOT EXISTS ix_client_inv_acc_queue_org ON client_invoice_accounting_queue(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_inv_acc_queue_lease ON client_invoice_accounting_queue(lease_expires_at);

-- Discrepancias de datos fiscales entre backend y escritorio (seccion 3/5
-- del encargo): nunca se sobrescribe en silencio ni se bloquean facturas ya
-- emitidas; el personal revisa y resuelve.
CREATE TABLE IF NOT EXISTS client_invoice_discrepancies (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    customer_id VARCHAR(36) NOT NULL REFERENCES client_invoice_customers(id) ON DELETE CASCADE,
    field_name VARCHAR(60) NOT NULL,
    backend_value TEXT NOT NULL DEFAULT '',
    desktop_value TEXT NOT NULL DEFAULT '',
    -- open | reviewed | dismissed
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    detail TEXT NOT NULL DEFAULT '',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by VARCHAR(120) NOT NULL DEFAULT '',
    reviewed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_client_inv_discrepancies_org ON client_invoice_discrepancies(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_inv_discrepancies_customer ON client_invoice_discrepancies(customer_id);
CREATE INDEX IF NOT EXISTS ix_client_inv_discrepancies_status ON client_invoice_discrepancies(status);
