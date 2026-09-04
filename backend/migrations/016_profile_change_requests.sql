-- Solicitudes de modificacion de datos propuestas desde Flutter.
-- Los datos maestros solo se aplican posteriormente desde el escritorio.

CREATE TABLE IF NOT EXISTS msg_profile_change_requests (
    id VARCHAR(36) PRIMARY KEY,
    organization_id VARCHAR(36) NOT NULL REFERENCES msg_organizations(id) ON DELETE CASCADE,
    client_id VARCHAR(36) NOT NULL REFERENCES msg_clients(id) ON DELETE CASCADE,
    message_id VARCHAR(36) REFERENCES msg_messages(id) ON DELETE SET NULL,
    changes_json TEXT NOT NULL DEFAULT '{}',
    current_values_json TEXT NOT NULL DEFAULT '{}',
    notes TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    review_note TEXT NOT NULL DEFAULT '',
    reviewed_by VARCHAR(64) NOT NULL DEFAULT '',
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_msg_profile_change_requests_org
    ON msg_profile_change_requests(organization_id);
CREATE INDEX IF NOT EXISTS ix_msg_profile_change_requests_client
    ON msg_profile_change_requests(client_id);
CREATE INDEX IF NOT EXISTS ix_msg_profile_change_requests_status
    ON msg_profile_change_requests(status);
CREATE INDEX IF NOT EXISTS ix_msg_profile_change_requests_created
    ON msg_profile_change_requests(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_msg_profile_change_requests_message
    ON msg_profile_change_requests(message_id);
