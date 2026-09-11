-- Los primeros documentos del worker AAPP se publicaron sin ejercicio y
-- Flutter los ocultaba al aplicar el filtro del ejercicio actual.
UPDATE client_documents
SET document_date = COALESCE(document_date, published_at),
    fiscal_year = EXTRACT(
        YEAR FROM COALESCE(document_date, published_at)
    )::INTEGER,
    updated_at = NOW()
WHERE source_system = 'aapp_worker'
  AND (fiscal_year IS NULL OR fiscal_year = 0);
