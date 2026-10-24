-- 043_client_invoice_catalog.sql
-- Etapa 4 de la facturacion autonoma de clientes (ver docs/adr/0001).
--
-- Catalogo de productos y servicios por organizacion, usado para rellenar
-- lineas de factura desde Flutter. Baja logica unicamente: nunca se borra
-- fisicamente un articulo que ya se haya usado en una linea.

CREATE TABLE IF NOT EXISTS client_catalog_items (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    -- product | service
    item_type VARCHAR(10) NOT NULL DEFAULT 'service',
    code VARCHAR(40) NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    unit VARCHAR(20) NOT NULL DEFAULT '',
    unit_price NUMERIC(15, 4) NOT NULL DEFAULT 0,
    vat_rate NUMERIC(5, 2) NOT NULL DEFAULT 21.00,
    withholding_rate NUMERIC(5, 2) NOT NULL DEFAULT 0,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_client_catalog_item_type') THEN
        ALTER TABLE client_catalog_items
            ADD CONSTRAINT ck_client_catalog_item_type
            CHECK (item_type IN ('product', 'service'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_client_catalog_items_org ON client_catalog_items(organization_id);
CREATE INDEX IF NOT EXISTS ix_client_catalog_items_active ON client_catalog_items(active);
CREATE INDEX IF NOT EXISTS ix_client_catalog_items_code ON client_catalog_items(code);
-- Busqueda por descripcion (seccion 7: "busqueda y paginacion").
CREATE INDEX IF NOT EXISTS ix_client_catalog_items_description
    ON client_catalog_items USING gin (to_tsvector('simple', description));

-- Snapshot del articulo copiado a la linea en el momento de anadirlo
-- (seccion 7: modificar el articulo despues no debe alterar borradores ya
-- confirmados ni facturas emitidas). catalog_item_id se conserva solo como
-- referencia de origen, nunca como fuente de verdad tras la copia.
ALTER TABLE client_invoice_lines
    ADD COLUMN IF NOT EXISTS catalog_item_id VARCHAR(36) NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_client_invoice_lines_catalog_item
    ON client_invoice_lines(catalog_item_id);
