-- Estado de integracion de clientes creados desde Flutter con el escritorio.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'client_invoice_customers'
          AND column_name = 'desktop_tercero_id'
          AND data_type <> 'character varying'
    ) THEN
        ALTER TABLE client_invoice_customers
            ALTER COLUMN desktop_tercero_id TYPE VARCHAR(64)
            USING desktop_tercero_id::text;
    END IF;
END $$;

ALTER TABLE client_invoice_customers
    ADD COLUMN IF NOT EXISTS desktop_sync_status VARCHAR(20) NOT NULL DEFAULT 'synced',
    ADD COLUMN IF NOT EXISTS desktop_sync_error TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS desktop_claimed_by VARCHAR(120) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS desktop_claimed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS desktop_lease_expires_at TIMESTAMPTZ;

UPDATE client_invoice_customers
SET desktop_sync_status = 'pending'
WHERE pending_desktop_import IS TRUE;

CREATE INDEX IF NOT EXISTS ix_client_customers_desktop_lease
    ON client_invoice_customers(desktop_lease_expires_at);
