-- 045_verifactu_chain_and_rectification.sql
-- Etapa 7 de la facturacion autonoma de clientes (ver docs/adr/0001 y
-- services/verifactu/README.md).
--
-- Corrige el encadenamiento Veri*FACTU: hasta ahora cada factura encadenaba
-- siempre contra una cadena vacia (""), nunca contra el hash real anterior.
-- Esta tabla guarda, por organizacion (= un obligado tributario/SIF en este
-- sistema), el ultimo hash real de la cadena, con bloqueo de fila al anadir
-- un registro nuevo.
--
-- Anade tambien las columnas necesarias para rectificativas y anulaciones
-- (seccion 15 del encargo): una factura emitida nunca se edita ni se
-- elimina; las correcciones son un registro nuevo que referencia al
-- original.

CREATE TABLE IF NOT EXISTS client_verifactu_chain_state (
    organization_id VARCHAR(36) PRIMARY KEY
        REFERENCES msg_organizations(id) ON DELETE CASCADE,
    last_hash VARCHAR(64) NOT NULL DEFAULT '',
    last_invoice_id VARCHAR(36) NOT NULL DEFAULT '',
    -- Serie+numero y fecha de expedicion del ultimo registro encadenado,
    -- necesarios para rellenar RegistroAnterior en el siguiente XML (el
    -- hash en si solo depende de last_hash, no de estos dos campos).
    last_num_serie VARCHAR(40) NOT NULL DEFAULT '',
    last_fecha_expedicion VARCHAR(10) NOT NULL DEFAULT '',
    sequence_number INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE client_invoices
    ADD COLUMN IF NOT EXISTS verifactu_xml TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS verifactu_fiscal_error TEXT NOT NULL DEFAULT '',
    -- El registro de anulacion es un registro fiscal propio, distinto del
    -- de alta: nunca se sobrescribe verifactu_hash/verifactu_xml (ese
    -- sigue siendo el registro de alta original, inmutable).
    ADD COLUMN IF NOT EXISTS verifactu_anulacion_hash VARCHAR(64) NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS verifactu_anulacion_xml TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS rectifies_invoice_id VARCHAR(36),
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS cancellation_reason TEXT NOT NULL DEFAULT '';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_client_invoices_rectifies'
    ) THEN
        ALTER TABLE client_invoices
            ADD CONSTRAINT fk_client_invoices_rectifies
            FOREIGN KEY (rectifies_invoice_id)
            REFERENCES client_invoices(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_client_invoices_rectifies ON client_invoices(rectifies_invoice_id);
