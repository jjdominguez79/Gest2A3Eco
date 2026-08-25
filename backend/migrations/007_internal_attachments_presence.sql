-- Migracion 007: adjuntos de chats internos y presencia de empleados.
-- Aditiva e idempotente para PostgreSQL.

ALTER TABLE msg_attachments
  ALTER COLUMN message_id DROP NOT NULL,
  ADD COLUMN IF NOT EXISTS internal_message_id VARCHAR(36)
    REFERENCES msg_staff_thread_messages(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_msg_attachments_internal_message_id
  ON msg_attachments(internal_message_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'ck_msg_attachments_single_parent'
  ) THEN
    ALTER TABLE msg_attachments ADD CONSTRAINT ck_msg_attachments_single_parent
      CHECK (
        (message_id IS NOT NULL AND internal_message_id IS NULL) OR
        (message_id IS NULL AND internal_message_id IS NOT NULL)
      );
  END IF;
END $$;

ALTER TABLE msg_websocket_tickets
  ADD COLUMN IF NOT EXISTS staff_session_id VARCHAR(36)
    REFERENCES msg_staff_sessions(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_msg_websocket_tickets_staff_session_id
  ON msg_websocket_tickets(staff_session_id);

CREATE TABLE IF NOT EXISTS msg_staff_presence_connections (
  id VARCHAR(36) PRIMARY KEY,
  staff_external_id VARCHAR(64) NOT NULL
    REFERENCES msg_staff(external_id) ON DELETE CASCADE,
  staff_session_id VARCHAR(36) NOT NULL
    REFERENCES msg_staff_sessions(id) ON DELETE CASCADE,
  connected_until TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_msg_staff_presence_connections_staff_external_id
  ON msg_staff_presence_connections(staff_external_id);
CREATE INDEX IF NOT EXISTS ix_msg_staff_presence_connections_staff_session_id
  ON msg_staff_presence_connections(staff_session_id);
CREATE INDEX IF NOT EXISTS ix_msg_staff_presence_connections_connected_until
  ON msg_staff_presence_connections(connected_until);
