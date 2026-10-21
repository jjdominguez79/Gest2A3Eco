-- Bandeja unificada: favoritos personales y etiquetas compartidas.
CREATE TABLE IF NOT EXISTS msg_chat_preferences (
    id VARCHAR(36) PRIMARY KEY,
    staff_external_id VARCHAR(64) NOT NULL
        REFERENCES msg_staff(external_id) ON DELETE CASCADE,
    target_type VARCHAR(24) NOT NULL,
    target_id VARCHAR(36) NOT NULL,
    favorite BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_msg_chat_preferences_target
        UNIQUE (staff_external_id, target_type, target_id),
    CONSTRAINT ck_msg_chat_preferences_target_type
        CHECK (target_type IN ('conversation', 'internal_thread'))
);

CREATE INDEX IF NOT EXISTS ix_msg_chat_preferences_staff
    ON msg_chat_preferences(staff_external_id);
CREATE INDEX IF NOT EXISTS ix_msg_chat_preferences_target
    ON msg_chat_preferences(target_type, target_id);

CREATE TABLE IF NOT EXISTS msg_chat_labels (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(80) NOT NULL UNIQUE,
    color VARCHAR(7) NOT NULL DEFAULT '#6750A4',
    created_by VARCHAR(64) NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_msg_chat_labels_active
    ON msg_chat_labels(active);
CREATE UNIQUE INDEX IF NOT EXISTS ux_msg_chat_labels_name_lower
    ON msg_chat_labels(LOWER(name));

CREATE TABLE IF NOT EXISTS msg_chat_label_links (
    id VARCHAR(36) PRIMARY KEY,
    label_id VARCHAR(36) NOT NULL
        REFERENCES msg_chat_labels(id) ON DELETE CASCADE,
    target_type VARCHAR(24) NOT NULL,
    target_id VARCHAR(36) NOT NULL,
    assigned_by VARCHAR(64) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_msg_chat_label_links_target
        UNIQUE (label_id, target_type, target_id),
    CONSTRAINT ck_msg_chat_label_links_target_type
        CHECK (target_type IN ('conversation', 'internal_thread'))
);

CREATE INDEX IF NOT EXISTS ix_msg_chat_label_links_label
    ON msg_chat_label_links(label_id);
CREATE INDEX IF NOT EXISTS ix_msg_chat_label_links_target
    ON msg_chat_label_links(target_type, target_id);
