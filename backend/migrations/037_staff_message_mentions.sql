-- Menciones estructuradas en los chats internos de grupo.
CREATE TABLE IF NOT EXISTS msg_staff_thread_mentions (
    id VARCHAR(36) PRIMARY KEY,
    internal_message_id VARCHAR(36) NOT NULL
        REFERENCES msg_staff_thread_messages(id) ON DELETE CASCADE,
    mentioned_staff_external_id VARCHAR(64) NOT NULL
        REFERENCES msg_staff(external_id) ON DELETE CASCADE,
    display_name VARCHAR(160) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_msg_staff_thread_mention
        UNIQUE (internal_message_id, mentioned_staff_external_id)
);

CREATE INDEX IF NOT EXISTS ix_msg_staff_thread_mentions_message
    ON msg_staff_thread_mentions(internal_message_id);
CREATE INDEX IF NOT EXISTS ix_msg_staff_thread_mentions_staff
    ON msg_staff_thread_mentions(mentioned_staff_external_id);
