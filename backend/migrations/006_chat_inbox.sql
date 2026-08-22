-- Migracion 006: separar canales disponibles de conversaciones iniciadas.
-- Aditiva e idempotente. Conserva como iniciadas las conversaciones con historico.

ALTER TABLE msg_conversations
  ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;

UPDATE msg_conversations AS conversation
SET started_at = COALESCE(
  (
    SELECT MIN(message.created_at)
    FROM msg_messages AS message
    WHERE message.conversation_id = conversation.id
  ),
  conversation.updated_at
)
WHERE conversation.started_at IS NULL
  AND EXISTS (
    SELECT 1
    FROM msg_messages AS message
    WHERE message.conversation_id = conversation.id
  );

CREATE INDEX IF NOT EXISTS ix_msg_conversations_started_at
  ON msg_conversations(started_at DESC);
