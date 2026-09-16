-- Referencias conocidas para no repetir avisos, incluidos titulares sin servicio.
-- No almacena asuntos, documentos ni contenido de notificaciones.
CREATE TABLE IF NOT EXISTS client_dehu_seen_references (
    holder_tax_id VARCHAR(30) NOT NULL,
    external_reference VARCHAR(300) NOT NULL,
    first_request_id VARCHAR(36),
    first_batch_id VARCHAR(36),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (holder_tax_id, external_reference)
);

-- Lo ya importado o enumerado en resumenes anteriores es conocido, no nuevo.
INSERT INTO client_dehu_seen_references
    (holder_tax_id, external_reference, first_seen_at)
SELECT regexp_replace(upper(holder_tax_id), '[^0-9A-Z]', '', 'g'),
       external_reference, min(first_seen_at)
FROM client_dehu_notifications
GROUP BY 1, 2
ON CONFLICT DO NOTHING;

INSERT INTO client_dehu_seen_references
    (holder_tax_id, external_reference, first_seen_at)
SELECT regexp_replace(upper(coalesce(entry->>'holder_tax_id', '')), '[^0-9A-Z]', '', 'g'),
       entry->>'reference', min(request.created_at)
FROM client_certificate_requests AS request
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_typeof(coalesce(nullif(request.parameters_json, ''), '{}')::jsonb->'_dehu_audit') = 'array'
         THEN request.parameters_json::jsonb->'_dehu_audit' ELSE '[]'::jsonb END
) AS entry
WHERE coalesce(entry->>'reference', '') <> ''
GROUP BY 1, 2
ON CONFLICT DO NOTHING;
