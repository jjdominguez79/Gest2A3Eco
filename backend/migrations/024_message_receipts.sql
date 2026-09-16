-- Mantener las lecturas historicas aunque se marque el chat como no leido.
ALTER TABLE msg_staff ADD COLUMN IF NOT EXISTS mostrar_estados_mensajes BOOLEAN NOT NULL DEFAULT TRUE;
CREATE TABLE IF NOT EXISTS msg_receipts (
    target_type VARCHAR(24) NOT NULL,
    target_id VARCHAR(36) NOT NULL,
    actor_type VARCHAR(16) NOT NULL,
    actor_id VARCHAR(64) NOT NULL,
    read_through_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (target_type, target_id, actor_type, actor_id)
);
INSERT INTO msg_receipts (target_type, target_id, actor_type, actor_id, read_through_at)
SELECT 'conversation', r.conversation_id, r.actor_type, r.actor_id, m.created_at
FROM msg_reads r JOIN msg_messages m ON m.id = r.last_message_id AND m.conversation_id = r.conversation_id
ON CONFLICT (target_type, target_id, actor_type, actor_id) DO NOTHING;
INSERT INTO msg_receipts (target_type, target_id, actor_type, actor_id, read_through_at)
SELECT 'internal_thread', r.thread_id, 'staff', r.staff_external_id, m.created_at
FROM msg_staff_thread_reads r JOIN msg_staff_thread_messages m ON m.id = r.last_message_id AND m.thread_id = r.thread_id
ON CONFLICT (target_type, target_id, actor_type, actor_id) DO NOTHING;
