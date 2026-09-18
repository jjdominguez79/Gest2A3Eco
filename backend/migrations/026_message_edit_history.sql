-- Texto actual publico; versiones anteriores accesibles solo por su propietario.
ALTER TABLE msg_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;
ALTER TABLE msg_staff_thread_messages ADD COLUMN IF NOT EXISTS edited_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS msg_message_versions (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(36) REFERENCES msg_messages(id) ON DELETE CASCADE,
    internal_message_id VARCHAR(36) REFERENCES msg_staff_thread_messages(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    version_created_at TIMESTAMPTZ NOT NULL,
    replaced_at TIMESTAMPTZ NOT NULL,
    edited_by VARCHAR(64) NOT NULL,
    edited_by_type VARCHAR(16) NOT NULL,
    CONSTRAINT ck_msg_message_versions_single_parent CHECK (
        (message_id IS NOT NULL AND internal_message_id IS NULL) OR
        (message_id IS NULL AND internal_message_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS ix_msg_message_versions_message_id ON msg_message_versions(message_id);
CREATE INDEX IF NOT EXISTS ix_msg_message_versions_internal_message_id ON msg_message_versions(internal_message_id);
