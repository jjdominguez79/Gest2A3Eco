-- Fusiona los antiguos canales de cliente en un unico canal general.
-- Idempotente y serializada: el bloqueo dura toda la transaccion de arranque.
SELECT pg_advisory_xact_lock(73195482016420317::bigint);

CREATE TABLE IF NOT EXISTS msg_conversation_aliases (
    old_conversation_id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL
        REFERENCES msg_conversations(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_msg_conversation_aliases_conversation_id
    ON msg_conversation_aliases(conversation_id);
ALTER TABLE msg_conversation_aliases
    ALTER COLUMN created_at SET DEFAULT NOW();

-- Solo estas organizaciones necesitan el ajuste historico de no leidos. Esta
-- tabla queda vacia al repetir la migracion, para no marcar como leidos los
-- mensajes creados despues del despliegue inicial.
CREATE TEMP TABLE _msg_general_backfill_orgs ON COMMIT DROP AS
SELECT DISTINCT organization_id
FROM msg_conversations
WHERE kind IN ('fiscal', 'laboral');

-- Toda organizacion debe tener un canal publico. Las instalaciones nuevas o
-- parcialmente aprovisionadas pueden no tener ninguno todavia.
INSERT INTO msg_conversations (
    id, organization_id, kind, state, assigned_staff_external_id,
    started_at, created_at, updated_at
)
SELECT gen_random_uuid()::text, organization.id, 'general', 'pendiente', '',
       NULL, NOW(), NOW()
FROM msg_organizations AS organization
WHERE NOT EXISTS (
    SELECT 1 FROM msg_conversations AS conversation
    WHERE conversation.organization_id = organization.id
      AND conversation.kind IN ('general', 'fiscal', 'laboral')
);

CREATE TEMP TABLE _msg_general_merge ON COMMIT DROP AS
WITH public_conversations AS (
    SELECT
        conversation.*,
        FIRST_VALUE(conversation.id) OVER (
            PARTITION BY conversation.organization_id
            ORDER BY CASE conversation.kind
                WHEN 'general' THEN 0 WHEN 'fiscal' THEN 1 ELSE 2
            END, conversation.id
        ) AS target_id
    FROM msg_conversations AS conversation
    WHERE conversation.kind IN ('general', 'fiscal', 'laboral')
)
SELECT id AS source_id, target_id, organization_id
FROM public_conversations;

CREATE TEMP TABLE _msg_general_counts ON COMMIT DROP AS
SELECT merge.organization_id, COUNT(message.id) AS message_count
FROM _msg_general_merge AS merge
LEFT JOIN msg_messages AS message ON message.conversation_id = merge.source_id
GROUP BY merge.organization_id;

-- El estado y la asignacion proceden del canal actualizado mas recientemente;
-- las fechas abarcan todo el historico fusionado.
WITH metadata AS (
    SELECT
        merge.target_id,
        (ARRAY_AGG(conversation.state ORDER BY conversation.updated_at DESC, conversation.id))[1] AS state,
        (ARRAY_AGG(conversation.assigned_staff_external_id ORDER BY conversation.updated_at DESC, conversation.id))[1]
            AS assigned_staff_external_id,
        MIN(conversation.created_at) AS created_at,
        MIN(conversation.started_at) AS started_at,
        MAX(conversation.updated_at) AS updated_at
    FROM _msg_general_merge AS merge
    JOIN msg_conversations AS conversation ON conversation.id = merge.source_id
    GROUP BY merge.target_id
)
UPDATE msg_conversations AS target
SET state = metadata.state,
    assigned_staff_external_id = metadata.assigned_staff_external_id,
    created_at = metadata.created_at,
    started_at = metadata.started_at,
    updated_at = metadata.updated_at
FROM metadata
WHERE target.id = metadata.target_id;

-- Una clave solo era unica dentro de su conversacion. Se cambia de forma
-- determinista unicamente en los duplicados que colisionarian al fusionar.
CREATE TEMP TABLE _msg_idempotency_collisions ON COMMIT DROP AS
WITH ranked AS (
    SELECT message.id,
           merge.target_id,
           ROW_NUMBER() OVER (
               PARTITION BY merge.target_id, message.idempotency_key
               ORDER BY CASE WHEN message.conversation_id = merge.target_id THEN 0 ELSE 1 END,
                        message.created_at, message.id
           ) AS position
    FROM msg_messages AS message
    JOIN _msg_general_merge AS merge ON merge.source_id = message.conversation_id
)
SELECT id, target_id FROM ranked WHERE position > 1;

DO $$
DECLARE
    collision RECORD;
    candidate VARCHAR(80);
    attempt INTEGER;
BEGIN
    FOR collision IN SELECT id, target_id FROM _msg_idempotency_collisions LOOP
        attempt := 0;
        candidate := 'merged:' || collision.id;
        WHILE EXISTS (
            SELECT 1
            FROM msg_messages AS existing
            JOIN _msg_general_merge AS merge
              ON merge.source_id = existing.conversation_id
            WHERE merge.target_id = collision.target_id
              AND existing.id <> collision.id
              AND existing.idempotency_key = candidate
        ) LOOP
            attempt := attempt + 1;
            candidate := 'merged:' || collision.id || ':' || attempt::text;
        END LOOP;
        UPDATE msg_messages
        SET idempotency_key = candidate
        WHERE id = collision.id;
    END LOOP;
END $$;

-- Los recibos son evidencia historica. Solo se conserva el prefijo que esta
-- confirmado en todos los canales con mensajes; si falta una confirmacion en
-- cualquiera de ellos, no se fabrica un recibo para la conversacion fusionada.
CREATE TEMP TABLE _msg_safe_receipts ON COMMIT DROP AS
SELECT merge.target_id, receipt.actor_type, receipt.actor_id,
       MIN(receipt.read_through_at) AS read_through_at
FROM msg_receipts AS receipt
JOIN _msg_general_merge AS merge
  ON receipt.target_type = 'conversation' AND receipt.target_id = merge.source_id
WHERE NOT EXISTS (
    SELECT 1
    FROM _msg_general_merge AS required_source
    WHERE required_source.target_id = merge.target_id
      AND EXISTS (
          SELECT 1 FROM msg_messages AS source_message
          WHERE source_message.conversation_id = required_source.source_id
      )
      AND NOT EXISTS (
          SELECT 1 FROM msg_receipts AS required_receipt
          WHERE required_receipt.target_type = 'conversation'
            AND required_receipt.target_id = required_source.source_id
            AND required_receipt.actor_type = receipt.actor_type
            AND required_receipt.actor_id = receipt.actor_id
      )
)
GROUP BY merge.target_id, receipt.actor_type, receipt.actor_id;

DELETE FROM msg_receipts AS receipt
USING _msg_general_merge AS merge
WHERE receipt.target_type = 'conversation'
  AND receipt.target_id = merge.source_id;

INSERT INTO msg_receipts (target_type, target_id, actor_type, actor_id, read_through_at)
SELECT 'conversation', target_id, actor_type, actor_id, read_through_at
FROM _msg_safe_receipts;

-- Las marcas personales se reconstruyen despues para considerar leido todo el
-- historico, pero no se convierten en recibos de lectura.
DELETE FROM msg_reads AS reading
USING _msg_general_merge AS merge
WHERE reading.conversation_id = merge.source_id
  AND merge.source_id <> merge.target_id;

UPDATE msg_messages AS message
SET conversation_id = merge.target_id
FROM _msg_general_merge AS merge
WHERE message.conversation_id = merge.source_id
  AND merge.source_id <> merge.target_id;

UPDATE msg_events AS event
SET conversation_id = merge.target_id
FROM _msg_general_merge AS merge
WHERE event.conversation_id = merge.source_id
  AND merge.source_id <> merge.target_id;

UPDATE msg_deletion_audit AS audit
SET conversation_id = merge.target_id
FROM _msg_general_merge AS merge
WHERE audit.conversation_id = merge.source_id
  AND merge.source_id <> merge.target_id;

UPDATE msg_app_devices AS device
SET active_conversation_id = merge.target_id
FROM _msg_general_merge AS merge
WHERE device.active_conversation_id = merge.source_id
  AND merge.source_id <> merge.target_id;

UPDATE msg_app_devices AS device
SET active_target_id = merge.target_id
FROM _msg_general_merge AS merge
WHERE device.active_target_type = 'conversation'
  AND device.active_target_id = merge.source_id
  AND merge.source_id <> merge.target_id;

-- Conservar tambien alias creados con anterioridad que apuntasen a uno de los
-- canales retirados; de otro modo el borrado en cascada los eliminaria.
UPDATE msg_conversation_aliases AS alias
SET conversation_id = merge.target_id
FROM _msg_general_merge AS merge
WHERE alias.conversation_id = merge.source_id
  AND merge.source_id <> merge.target_id;

INSERT INTO msg_conversation_aliases (
    old_conversation_id, conversation_id, created_at
)
SELECT source_id, target_id, NOW()
FROM _msg_general_merge
WHERE source_id <> target_id
ON CONFLICT (old_conversation_id) DO UPDATE
SET conversation_id = EXCLUDED.conversation_id;

-- El identificador superviviente no cambia aunque antes fuese fiscal/laboral.
UPDATE msg_conversations AS conversation
SET kind = 'general'
FROM (SELECT DISTINCT target_id FROM _msg_general_merge) AS target
WHERE conversation.id = target.target_id;

-- Validar el conteo antes de retirar las filas redundantes.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM _msg_general_counts AS expected
        JOIN msg_conversations AS general
          ON general.organization_id = expected.organization_id
         AND general.kind = 'general'
        LEFT JOIN msg_messages AS message ON message.conversation_id = general.id
        GROUP BY expected.organization_id, expected.message_count
        HAVING COUNT(message.id) <> expected.message_count
    ) THEN
        RAISE EXCEPTION 'La fusion de canales alteraria el numero de mensajes';
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM _msg_general_merge AS merge
        WHERE merge.source_id <> merge.target_id
          AND (
              EXISTS (SELECT 1 FROM msg_messages WHERE conversation_id = merge.source_id)
              OR EXISTS (SELECT 1 FROM msg_reads WHERE conversation_id = merge.source_id)
              OR EXISTS (SELECT 1 FROM msg_events WHERE conversation_id = merge.source_id)
              OR EXISTS (SELECT 1 FROM msg_deletion_audit WHERE conversation_id = merge.source_id)
              OR EXISTS (SELECT 1 FROM msg_app_devices WHERE active_conversation_id = merge.source_id)
              OR EXISTS (
                  SELECT 1 FROM msg_app_devices
                  WHERE active_target_type = 'conversation'
                    AND active_target_id = merge.source_id
              )
              OR EXISTS (
                  SELECT 1 FROM msg_receipts
                  WHERE target_type = 'conversation' AND target_id = merge.source_id
              )
              OR EXISTS (
                  SELECT 1 FROM msg_conversation_aliases
                  WHERE conversation_id = merge.source_id
              )
          )
    ) THEN
        RAISE EXCEPTION 'Quedan referencias a conversaciones redundantes';
    END IF;
END $$;

DELETE FROM msg_conversations AS conversation
USING _msg_general_merge AS merge
WHERE conversation.id = merge.source_id
  AND merge.source_id <> merge.target_id;

-- Asegurar el segundo canal sin tocar nunca su contenido.
INSERT INTO msg_conversations (
    id, organization_id, kind, state, assigned_staff_external_id,
    started_at, created_at, updated_at
)
SELECT gen_random_uuid()::text, organization.id, 'private', 'pendiente', '',
       NULL, NOW(), NOW()
FROM msg_organizations AS organization
WHERE NOT EXISTS (
    SELECT 1 FROM msg_conversations AS conversation
    WHERE conversation.organization_id = organization.id
      AND conversation.kind = 'private'
);

-- El historico queda sin pendientes para todas las identidades ya existentes.
INSERT INTO msg_reads (
    conversation_id, actor_type, actor_id, last_message_id, read_at
)
SELECT general.id, 'client', client.id,
       COALESCE(last_message.id, ''), NOW()
FROM msg_conversations AS general
JOIN _msg_general_backfill_orgs AS backfill
  ON backfill.organization_id = general.organization_id
JOIN msg_clients AS client ON client.organization_id = general.organization_id
LEFT JOIN LATERAL (
    SELECT message.id
    FROM msg_messages AS message
    WHERE message.conversation_id = general.id
    ORDER BY message.created_at DESC, message.id DESC
    LIMIT 1
) AS last_message ON TRUE
WHERE general.kind = 'general'
ON CONFLICT (conversation_id, actor_type, actor_id) DO UPDATE
SET last_message_id = EXCLUDED.last_message_id, read_at = EXCLUDED.read_at;

INSERT INTO msg_reads (
    conversation_id, actor_type, actor_id, last_message_id, read_at
)
SELECT general.id, 'staff', staff.external_id,
       COALESCE(last_message.id, ''), NOW()
FROM msg_conversations AS general
JOIN _msg_general_backfill_orgs AS backfill
  ON backfill.organization_id = general.organization_id
CROSS JOIN msg_staff AS staff
LEFT JOIN LATERAL (
    SELECT message.id
    FROM msg_messages AS message
    WHERE message.conversation_id = general.id
    ORDER BY message.created_at DESC, message.id DESC
    LIMIT 1
) AS last_message ON TRUE
WHERE general.kind = 'general'
ON CONFLICT (conversation_id, actor_type, actor_id) DO UPDATE
SET last_message_id = EXCLUDED.last_message_id, read_at = EXCLUDED.read_at;

UPDATE msg_campaigns SET channel = 'general'
WHERE channel IN ('laboral', 'fiscal');
ALTER TABLE msg_campaigns ALTER COLUMN channel SET DEFAULT 'general';

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM msg_organizations AS organization
        LEFT JOIN msg_conversations AS conversation
          ON conversation.organization_id = organization.id
        GROUP BY organization.id
        HAVING COUNT(*) FILTER (WHERE conversation.kind = 'general') <> 1
            OR COUNT(*) FILTER (WHERE conversation.kind = 'private') <> 1
            OR COUNT(*) FILTER (
                WHERE conversation.kind NOT IN ('general', 'private')
            ) <> 0
    ) THEN
        RAISE EXCEPTION 'La mensajeria no ha quedado en general + private';
    END IF;
END $$;
