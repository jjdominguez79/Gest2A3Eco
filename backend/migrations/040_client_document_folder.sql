-- Carpeta funcional elegida al publicar un documento en el area Flutter.
-- Se separa del tipo de documento y se conserva la clasificacion historica.

ALTER TABLE client_documents
    ADD COLUMN IF NOT EXISTS folder VARCHAR(20) NOT NULL DEFAULT '';

UPDATE client_documents
SET folder = CASE
    WHEN lower(document_type) LIKE '%factura%'
      OR lower(document_type) LIKE '%invoice%' THEN 'facturas'
    WHEN lower(document_type) LIKE '%certificado%'
      OR lower(document_type) LIKE '%certificate%'
      OR lower(document_type) IN ('resguardo_aeat', 'revision_aeat')
      THEN 'certificados'
    WHEN lower(document_type) LIKE '%nomina%'
      OR lower(document_type) LIKE '%payroll%' THEN 'nominas'
    WHEN lower(document_type) LIKE '%impuesto%'
      OR lower(document_type) LIKE '%tribut%'
      OR lower(document_type) LIKE '%modelo_%'
      OR lower(document_type) LIKE '%fiscal%' THEN 'impuestos'
    WHEN lower(document_type) LIKE '%contrato%'
      OR lower(document_type) LIKE '%contract%' THEN 'contratos'
    ELSE 'otros'
END
WHERE folder = '';

ALTER TABLE client_documents
    ALTER COLUMN folder SET DEFAULT 'otros';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_client_documents_folder'
    ) THEN
        ALTER TABLE client_documents
            ADD CONSTRAINT ck_client_documents_folder
            CHECK (folder IN (
                'facturas', 'certificados', 'nominas', 'impuestos',
                'contratos', 'otros'
            ));
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS ix_client_documents_folder
    ON client_documents(folder);
